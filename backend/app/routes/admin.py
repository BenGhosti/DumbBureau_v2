from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..auth_utils import generate_token, hash_token, utcnow
from ..config import settings
from ..crypto import decrypt as _decrypt
from ..database import get_db
from ..dependencies import require_admin
from ..models import AuditLog, InviteToken, Task, User
from .tasks import _month_range, _serialize

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ArchiveRequest(BaseModel):
    reason: str | None = None


def _username_map(db: Session) -> dict[str, str]:
    return {u.id: u.username for u in db.query(User).all()}


@router.get("/users")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    task_counts = dict(
        db.query(Task.user_id, func.count(Task.id))
        .filter(Task.archived_at.is_(None))
        .group_by(Task.user_id)
        .all()
    )
    users = db.query(User).order_by(User.created_at.asc()).all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_admin": u.is_admin,
                "created_at": u.created_at,
                "archived_at": u.archived_at,
                "task_count": task_counts.get(u.id, 0),
            }
            for u in users
        ]
    }


@router.get("/audit-log")
def audit_log(
    limit: int = 100,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    names = _username_map(db)
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": names.get(log.user_id),
                "action": log.action,
                "target_user_id": log.target_user_id,
                "target_username": names.get(log.target_user_id),
                "details": _parse_details(log.details),
                "timestamp": log.timestamp,
            }
            for log in logs
        ]
    }


def _parse_details(details: str | None) -> dict | None:
    if not details:
        return None
    try:
        return json.loads(_decrypt(details))
    except (ValueError, TypeError):
        return {"raw": details}


@router.get("/user/{user_id}/tasks")
def admin_view_tasks(
    user_id: str,
    month: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    query = db.query(Task).filter(Task.user_id == user_id, Task.archived_at.is_(None))
    if month:
        start, end = _month_range(month)
        query = query.filter(Task.date >= start, Task.date < end)

    tasks = query.order_by(Task.date.desc(), Task.created_at.desc()).all()

    log_audit(
        db,
        action="admin_viewed_tasks",
        user_id=admin.id,
        target_user_id=user_id,
        details={"month": month},
    )
    db.commit()

    return {"tasks": [_serialize(t) for t in tasks]}


@router.post("/user/{user_id}/archive")
def archive_user(
    user_id: str,
    body: ArchiveRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot archive yourself"
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if target.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User already archived"
        )

    target.archived_at = utcnow()
    log_audit(
        db,
        action="user_archived",
        user_id=admin.id,
        target_user_id=user_id,
        details={"reason": body.reason},
    )
    db.commit()
    return {"archived": True, "user_id": user_id}


@router.post("/user/{user_id}/unarchive")
def unarchive_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if target.archived_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User not archived"
        )

    target.archived_at = None
    log_audit(
        db,
        action="user_unarchived",
        user_id=admin.id,
        target_user_id=user_id,
    )
    db.commit()
    return {"archived": False, "user_id": user_id}


@router.post("/invites")
def create_invite(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    raw_token = generate_token()
    invite = InviteToken(
        token_hash=hash_token(raw_token),
        created_by=admin.id,
        expires_at=utcnow() + timedelta(days=settings.invite_token_ttl_days),
    )
    db.add(invite)
    log_audit(
        db,
        action="invite_created",
        user_id=admin.id,
        details={"invite_id": invite.id},
    )
    db.commit()
    return {"invite_token": raw_token, "expires_at": invite.expires_at}


@router.get("/invites")
def list_invites(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    names = _username_map(db)
    invites = db.query(InviteToken).order_by(InviteToken.created_at.desc()).all()
    return {
        "invites": [
            {
                "id": invite.id,
                "created_by": invite.created_by,
                "created_by_username": names.get(invite.created_by),
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
                "used_at": invite.used_at,
            }
            for invite in invites
        ]
    }
