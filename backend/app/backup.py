from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import settings
from .database import engine

logger = logging.getLogger("dumbbureau.backup")


def _db_path() -> Path:
    """Resolve the on-disk SQLite file from the SQLAlchemy engine URL."""
    url = engine.url
    if url.drivername != "sqlite":
        raise RuntimeError("Online backup is only supported for SQLite")
    database = url.database
    if not database or database == ":memory:":
        raise RuntimeError("Cannot back up an in-memory database")
    return Path(database)


def backup_database() -> Path | None:
    """Create a consistent online snapshot of the SQLite database.

    Uses SQLite's backup API (``sqlite3.Connection.backup``) so it is safe to
    run while the app is live — unlike copying the raw file, it is not subject
    to WAL races or partial pages. Backups are written to
    ``<appdata>/backups/db-<timestamp>.sqlite`` and old ones are pruned to the
    configured retention count.
    """
    src_path = _db_path()
    if not src_path.exists():
        logger.warning("Backup skipped: database file %s does not exist yet.", src_path)
        return None

    from .auth_utils import utcnow

    dest_dir = settings.backups_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"db-{utcnow():%Y%m%d-%H%M%S}.sqlite"

    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    _prune_backups(dest_dir)
    logger.info("Database backup written to %s", dest)
    return dest


def _prune_backups(dest_dir: Path) -> None:
    retention = max(1, settings.backup_retention)
    backups = sorted(dest_dir.glob("db-*.sqlite"), key=lambda p: p.stat().st_mtime)
    for stale in backups[:-retention]:
        try:
            stale.unlink()
            logger.info("Pruned old backup %s", stale)
        except OSError:
            logger.warning("Could not prune old backup %s", stale)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = backup_database()
    if result is not None:
        print(f"Backup written: {result}")
