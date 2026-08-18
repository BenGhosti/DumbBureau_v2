from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text

from .config import settings
from .database import engine
from .init_db import init_db
from .maintenance import run_daily_maintenance
from .routes import admin, auth, categories, pdf, tasks, templates

logging.basicConfig(
    level=getattr(logging, str(settings.log_level).upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("dumbbureau")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    if len(settings.secret_key) < 32 or settings.secret_key in {
        "change-me-in-production",
        "LOCKED_UNTIL_ENV",
        "",
    }:
        logger.warning(
            "SECRET_KEY is weak or default. Set a strong (>=32 byte) secret in production."
        )
    if settings.admin_recovery_secret in {"LOCKED_UNTIL_ENV", ""}:
        logger.warning(
            "ADMIN_RECOVERY_SECRET is unset. First-user bootstrap is disabled until it is configured."
        )
    maintenance_task = asyncio.create_task(run_daily_maintenance())
    try:
        yield
    finally:
        maintenance_task.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance_task


app = FastAPI(title="DumbBureau", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": "Internal server error"}
    )


app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(categories.router)
app.include_router(templates.router)
app.include_router(pdf.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "error", "detail": "database unreachable"})
    return JSONResponse(status_code=200, content={"status": "ok"})
