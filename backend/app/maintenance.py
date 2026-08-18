from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from .auth_utils import utcnow
from .database import SessionLocal
from .models import Task

logger = logging.getLogger("dumbbureau.maintenance")


def archive_old_tasks(db, years: int = 1) -> int:
    cutoff = (utcnow() - timedelta(days=365 * years)).date()
    tasks = (
        db.query(Task)
        .filter(Task.date < cutoff, Task.archived_at.is_(None))
        .all()
    )
    for task in tasks:
        task.archived_at = utcnow()
    db.commit()
    return len(tasks)


async def run_daily_maintenance() -> None:
    """Background loop that runs archive_old_tasks once every 24h.

    This is documented in FEATURES.md ("python -m app.maintenance archives
    tasks > 1 year") but nothing ever invoked it automatically - no cron
    container, no scheduler. Without an operator manually running the
    command on a recurring basis, tasks older than a year simply never get
    archived. Started from the FastAPI lifespan so it runs for the lifetime
    of the backend process without needing extra infrastructure.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                count = archive_old_tasks(db)
                if count:
                    logger.info("Daily maintenance: archived %d task(s) older than 1 year.", count)
            finally:
                db.close()
        except Exception:
            logger.exception("Daily maintenance run failed")
        try:
            from .backup import backup_database

            backup_database()
        except Exception:
            logger.exception("Daily database backup failed")
        await asyncio.sleep(24 * 60 * 60)


if __name__ == "__main__":
    db = SessionLocal()
    count = archive_old_tasks(db)
    db.close()
    print(f"Archived {count} old tasks.")
