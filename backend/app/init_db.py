from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from . import models  # noqa: F401  (ensure models are registered on Base.metadata)
from .database import Base, engine

logger = logging.getLogger("dumbbureau.init_db")

# Lightweight additive migration: this project has no Alembic (or similar)
# migration tool, and Base.metadata.create_all() only creates missing
# TABLES - it never alters an existing table's columns. Without this, an
# already-deployed instance would keep an old `passkeys` table missing the
# newly added `name`/`last_used_at` columns and crash the first time any
# code touches them. Each entry is (table, column, DDL-safe column def);
# only ever ADD columns here, never rename/drop - SQLite's ALTER TABLE
# support is limited to that anyway, and it keeps this safe to run
# unconditionally on every startup.
_ADDITIVE_MIGRATIONS: list[tuple[str, str, str]] = [
    ("passkeys", "name", "VARCHAR(100) NOT NULL DEFAULT 'Passkey'"),
    ("passkeys", "last_used_at", "DATETIME"),
]


def _run_additive_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, coldef in _ADDITIVE_MIGRATIONS:
            if table not in existing_tables:
                # Table doesn't exist yet at all - create_all() below will
                # create it fresh, already including this column.
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            logger.info("Migrating: adding %s.%s", table, column)
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}"))


def init_db() -> None:
    _run_additive_migrations()
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
