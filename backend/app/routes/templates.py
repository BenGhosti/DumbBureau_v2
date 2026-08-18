from __future__ import annotations

import re
import uuid
from pathlib import Path

import bleach
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..auth_utils import utcnow
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Template, User

router = APIRouter(prefix="/api/templates", tags=["templates"])

MAX_TEMPLATE_SIZE = 1_000_000  # 1 MB

_JINJA_PATTERN = re.compile(r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})", re.DOTALL)

_ALLOWED_TAGS = [
    "a", "b", "br", "blockquote", "caption", "col", "colgroup", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p",
    "pre", "span", "strong", "table", "tbody", "td", "tfoot", "th", "thead",
    "tr", "ul", "u", "small", "sub", "sup", "section", "header", "footer",
    "article", "main", "aside", "style",
]

_ALLOWED_ATTRS = {
    "*": ["class", "id", "title", "style"],
    "a": ["href", "target"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan", "align", "valign"],
    "th": ["colspan", "rowspan", "align", "valign"],
    "table": ["border", "cellpadding", "cellspacing", "width"],
    "col": ["width", "span"],
}

_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_template_html(html: str) -> str:
    tokens: list[str] = []

    def _protect(match: re.Match) -> str:
        tokens.append(match.group(0))
        return f"__JINJA_{len(tokens) - 1}__"

    protected = _JINJA_PATTERN.sub(_protect, html)
    cleaned = bleach.clean(
        protected,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    for i, token in enumerate(tokens):
        cleaned = cleaned.replace(f"__JINJA_{i}__", token)
    return cleaned


def _serialize(template: Template) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "is_default": template.is_default,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _user_templates_dir(user_id: str):
    directory = settings.templates_dir / user_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _clear_defaults(db: Session, user_id: str, exclude_id: str | None = None) -> None:
    query = db.query(Template).filter(
        Template.user_id == user_id, Template.is_default.is_(True)
    )
    if exclude_id:
        query = query.filter(Template.id != exclude_id)
    for template in query.all():
        template.is_default = False


@router.post("")
async def upload_template(
    name: str = Form(...),
    description: str | None = Form(None),
    is_default: bool = Form(False),
    html_file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await html_file.read()
    if len(content) > MAX_TEMPLATE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template too large (max 1 MB)",
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template must be UTF-8 encoded",
        )

    template_id = uuid.uuid4().hex
    path = _user_templates_dir(user.id) / f"{template_id}.html"
    path.write_bytes(sanitize_template_html(text).encode("utf-8"))

    if is_default:
        _clear_defaults(db, user.id)

    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Name required"
        )
    if len(clean_name) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Name too long"
        )

    template = Template(
        id=template_id,
        user_id=user.id,
        name=clean_name,
        description=description,
        html_file=str(path),
        is_default=is_default,
    )
    db.add(template)
    db.flush()

    log_audit(
        db,
        action="template_uploaded",
        user_id=user.id,
        details={"template_id": template.id, "name": name},
    )

    db.commit()
    return {"template_id": template.id, "file_path": template.html_file}


@router.get("")
def list_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    templates = (
        db.query(Template)
        .filter(Template.user_id == user.id)
        .order_by(Template.created_at.desc())
        .all()
    )
    return {"templates": [_serialize(t) for t in templates]}


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    name: str | None = Form(None),
    description: str | None = Form(None),
    is_default: bool | None = Form(None),
    html_file: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.get(Template, template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    if template.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    if name is not None:
        if not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Name required"
            )
        if len(name.strip()) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Name too long"
            )
        template.name = name.strip()
    if description is not None:
        template.description = description

    if html_file is not None:
        content = await html_file.read()
        if len(content) > MAX_TEMPLATE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template too large (max 1 MB)",
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template must be UTF-8 encoded",
            )
        Path(template.html_file).write_bytes(
            sanitize_template_html(text).encode("utf-8")
        )

    if is_default is not None:
        if is_default:
            _clear_defaults(db, template.user_id, exclude_id=template.id)
        template.is_default = is_default

    template.updated_at = utcnow()

    log_audit(
        db,
        action="template_updated",
        user_id=user.id,
        target_user_id=template.user_id if template.user_id != user.id else None,
        details={"template_id": template.id},
    )

    db.commit()
    return {"template_id": template.id, "updated_at": template.updated_at}


@router.delete("/{template_id}")
def delete_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.get(Template, template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    if template.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    file_path = template.html_file
    log_audit(
        db,
        action="template_deleted",
        user_id=user.id,
        target_user_id=template.user_id if template.user_id != user.id else None,
        details={"template_id": template.id},
    )
    db.delete(template)
    db.commit()

    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        pass

    return {"deleted": True}
