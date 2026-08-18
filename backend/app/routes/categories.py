from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Category, Task, User

router = APIRouter(prefix="/api/categories", tags=["categories"])

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    color: str = "#4B5563"


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    color: str | None = None


def _validate_color(color: str) -> None:
    if not _COLOR_RE.match(color):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="color must be #RRGGBB",
        )


def _serialize(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "color": category.color,
        "created_at": category.created_at,
    }


@router.post("")
def create_category(
    body: CategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Name required"
        )
    _validate_color(body.color)

    category = Category(
        user_id=user.id,
        name=name,
        description=body.description,
        color=body.color,
    )
    db.add(category)
    db.flush()
    log_audit(
        db,
        action="category_created",
        user_id=user.id,
        details={"category_id": category.id},
    )
    db.commit()
    return {"category_id": category.id}


@router.get("")
def list_categories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    categories = (
        db.query(Category)
        .filter(Category.user_id == user.id)
        .order_by(Category.name.asc())
        .all()
    )
    return {"categories": [_serialize(c) for c in categories]}


@router.put("/{category_id}")
def update_category(
    category_id: str,
    body: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    if category.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        if not data["name"].strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Name required"
            )
        category.name = data["name"].strip()
    if "description" in data:
        category.description = data["description"]
    if "color" in data:
        _validate_color(data["color"])
        category.color = data["color"]

    log_audit(
        db,
        action="category_updated",
        user_id=user.id,
        target_user_id=category.user_id if category.user_id != user.id else None,
        details={"category_id": category.id},
    )
    db.commit()
    return {"category_id": category.id}


@router.delete("/{category_id}")
def delete_category(
    category_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    if category.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    db.query(Task).filter(Task.category_id == category.id).update(
        {Task.category_id: None}
    )

    log_audit(
        db,
        action="category_deleted",
        user_id=user.id,
        target_user_id=category.user_id if category.user_id != user.id else None,
        details={"category_id": category.id},
    )
    db.delete(category)
    db.commit()
    return {"deleted": True}
