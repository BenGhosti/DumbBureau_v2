from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .crypto import encrypt as _encrypt
from .models import AuditLog


def log_audit(
    db: Session,
    *,
    action: str,
    user_id: str | None = None,
    target_user_id: str | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        action=action,
        user_id=user_id,
        target_user_id=target_user_id,
        details=_encrypt(json.dumps(details, ensure_ascii=False)) if details else None,
    )
    db.add(entry)
    db.flush()
