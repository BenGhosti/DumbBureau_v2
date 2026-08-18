from __future__ import annotations

from datetime import date as _date
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..auth_utils import utcnow
from ..crypto import decrypt as _decrypt, encrypt as _encrypt
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Category, Task, User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    date: _date
    category_id: str | None = None
    description: str = Field(..., max_length=10000)
    fisi_area: str | None = Field(None, max_length=255)


class TaskUpdate(BaseModel):
    date: _date | None = None
    category_id: str | None = None
    description: str | None = Field(None, max_length=10000)
    fisi_area: str | None = Field(None, max_length=255)


def _serialize(task: Task) -> dict:
    return {
        "id": task.id,
        "date": task.date,
        "category_id": task.category_id,
        "category": task.category.name if task.category else None,
        "category_color": task.category.color if task.category else None,
        "description": _decrypt(task.description),
        "fisi_area": task.fisi_area,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _validate_category(db: Session, user_id: str, category_id: str | None) -> None:
    if category_id is None:
        return
    category = db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found"
        )


def _month_range(month: str) -> tuple[_date, _date]:
    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="month must be YYYY-MM"
        )
    if first.month == 12:
        end = _date(first.year + 1, 1, 1)
    else:
        end = _date(first.year, first.month + 1, 1)
    return first, end


@router.post("")
def create_task(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    description = body.description.strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Description required"
        )

    _validate_category(db, user.id, body.category_id)

    task = Task(
        user_id=user.id,
        date=body.date,
        category_id=body.category_id,
        description=_encrypt(description),
        fisi_area=body.fisi_area,
    )
    db.add(task)
    db.flush()

    if user.is_admin:
        log_audit(
            db,
            action="task_created",
            user_id=user.id,
            details={"task_id": task.id},
        )

    db.commit()
    return {"task_id": task.id, "created_at": task.created_at}


@router.get("")
def list_tasks(
    month: str | None = None,
    user_id: str | None = None,
    start: _date | None = None,
    end: _date | None = None,
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Cap the page size regardless of what the client requests - an
    # unbounded limit lets a single request pull an entire user's task
    # history into memory (and onto the wire) at once.
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    query = db.query(Task).filter(Task.archived_at.is_(None))

    if user_id is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
            )
        query = query.filter(Task.user_id == user_id)
    else:
        query = query.filter(Task.user_id == user.id)

    if start is not None:
        query = query.filter(Task.date >= start)
    if end is not None:
        query = query.filter(Task.date < end)
    if month:
        month_start, month_end = _month_range(month)
        query = query.filter(Task.date >= month_start, Task.date < month_end)

    tasks = (
        query.order_by(Task.date.desc(), Task.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"tasks": [_serialize(t) for t in tasks]}


@router.put("/{task_id}")
def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    if task.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    is_admin_on_other = task.user_id != user.id and user.is_admin

    data = body.model_dump(exclude_unset=True)
    if "date" in data:
        task.date = data["date"]
    if "category_id" in data:
        _validate_category(db, task.user_id, data["category_id"])
        task.category_id = data["category_id"]
    if "description" in data:
        if not data["description"].strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Description required"
            )
        task.description = _encrypt(data["description"].strip())
    if "fisi_area" in data:
        task.fisi_area = data["fisi_area"]

    task.updated_at = utcnow()

    if is_admin_on_other:
        log_audit(
            db,
            action="task_updated",
            user_id=user.id,
            target_user_id=task.user_id,
            details={"task_id": task.id},
        )

    db.commit()
    return {"task_id": task.id, "updated_at": task.updated_at}


@router.delete("/{task_id}")
def delete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    if task.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    task.archived_at = utcnow()
    log_audit(
        db,
        action="task_deleted",
        user_id=user.id,
        target_user_id=task.user_id,
        details={"task_id": task.id},
    )

    db.commit()
    return {"deleted": True}
