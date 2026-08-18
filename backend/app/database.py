from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.database_url.startswith("sqlite")

_connect_args = {}
if _is_sqlite:
    # busy_timeout (ms) lets a connection wait for a lock instead of
    # immediately raising "database is locked" under concurrent access.
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.database_url, connect_args=_connect_args)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        # WAL: readers no longer block writers and vice versa - the single
        # biggest fix for "database is locked" errors with multiple users.
        cursor.execute("PRAGMA journal_mode=WAL")
        # Belt-and-braces: also wait (ms) at the SQLite level before erroring.
        cursor.execute("PRAGMA busy_timeout=30000")
        # NORMAL is safe (and fast) in WAL mode; still durable across app crashes.
        cursor.execute("PRAGMA synchronous=NORMAL")
        # NOTE: intentionally NOT enabling "PRAGMA foreign_keys=ON" here.
        # auth_challenges.user_id deliberately stores a provisional id before
        # the referenced user row exists (see routes/auth.py), so strict FK
        # enforcement would break the registration/login challenge flow.
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
