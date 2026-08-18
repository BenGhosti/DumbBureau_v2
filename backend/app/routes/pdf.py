from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import pdf_generator
from ..audit import log_audit
from ..auth_utils import utcnow
from ..config import settings
from ..crypto import decrypt as _decrypt
from ..database import get_db
from ..dependencies import get_current_user
from ..models import PdfExport, Task, Template, User

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


class ExportRequest(BaseModel):
    month: str
    template_id: str | None = None
    include_archived: bool = False
    user_id: str | None = None


def _month_range(month: str) -> tuple[date, date]:
    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="month must be YYYY-MM"
        )
    if first.month == 12:
        end = date(first.year + 1, 1, 1)
    else:
        end = date(first.year, first.month + 1, 1)
    return first, end


def _task_dict(task: Task) -> dict:
    return {
        "date": task.date.isoformat(),
        "category": task.category.name if task.category else None,
        "description": _decrypt(task.description),
        "fisi_area": task.fisi_area,
    }


@router.post("/export")
def export_pdf(
    body: ExportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_user = user
    if body.user_id is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
            )
        target_user = db.get(User, body.user_id)
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

    start, end = _month_range(body.month)

    query = db.query(Task).filter(
        Task.user_id == target_user.id,
        Task.date >= start,
        Task.date < end,
    )
    if not body.include_archived:
        query = query.filter(Task.archived_at.is_(None))
    tasks = query.order_by(Task.date.asc()).all()

    template: Template | None = None
    if body.template_id:
        template = db.get(Template, body.template_id)
        if template is None or template.user_id != target_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
            )
    else:
        template = (
            db.query(Template)
            .filter(
                Template.user_id == target_user.id,
                Template.is_default.is_(True),
            )
            .first()
        )

    if template is not None:
        try:
            html_source = Path(template.html_file).read_text(encoding="utf-8")
        except OSError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Template file missing",
            )
    else:
        html_source = pdf_generator.DEFAULT_TEMPLATE

    context = {
        "user": {"username": target_user.username, "email": target_user.email},
        "month": body.month,
        "tasks": [_task_dict(t) for t in tasks],
        "generated_at": utcnow().isoformat(),
    }

    try:
        html = pdf_generator.render_template(html_source, context)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template rendering failed: {exc}",
        )

    pdf_id = uuid.uuid4().hex
    user_dir = settings.exports_dir / target_user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = user_dir / f"{pdf_id}.pdf"

    try:
        pdf_generator.generate_pdf(html, pdf_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )

    export = PdfExport(
        id=pdf_id,
        user_id=target_user.id,
        month=body.month,
        template_id=template.id if template else None,
        pdf_file=str(pdf_path),
    )
    db.add(export)
    db.flush()

    log_audit(
        db,
        action="pdf_exported",
        user_id=user.id,
        target_user_id=target_user.id if target_user.id != user.id else None,
        details={"pdf_id": pdf_id, "month": body.month},
    )

    db.commit()

    return {
        "pdf_url": f"/api/pdf/{pdf_id}",
        "pdf_id": pdf_id,
        "exported_at": export.exported_at,
    }


@router.get("/{pdf_id}")
def download_pdf(
    pdf_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    export = db.get(PdfExport, pdf_id)
    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="PDF not found"
        )
    if export.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed"
        )

    # The DB row can outlive the file (volume misconfiguration, manual
    # cleanup, disk issue). Without this check, FileResponse raises an
    # unhandled FileNotFoundError that the global handler turns into a
    # misleading 500 instead of an honest, actionable 404.
    if not Path(export.pdf_file).is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file no longer available on disk",
        )

    filename = f"berichtsheft-{export.month}.pdf"
    return FileResponse(export.pdf_file, media_type="application/pdf", filename=filename)
