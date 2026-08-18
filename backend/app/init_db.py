from __future__ import annotations

from . import models  # noqa: F401  (ensure models are registered on Base.metadata)
from .database import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
