"""Dependencias compartidas del carril Río Maipo."""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse

from app.core.config import APP_NAME, BASE_DIR, RIOMAIPO_PREFIX, TRACK_NAME
from app.core.formatting import clp, fecha_corta

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def base_context(request: Request, **extra):
    return {
        "app_name": APP_NAME,
        "track_name": TRACK_NAME,
        "prefix": RIOMAIPO_PREFIX,
        "clp": clp,
        "fecha_corta": fecha_corta,
        "flash": request.session.pop("flash", None) if hasattr(request, "session") else None,
        **extra,
    }


def render(request: Request, name: str, **extra) -> HTMLResponse:
    return templates.TemplateResponse(request, name, base_context(request, **extra))


def set_flash(request: Request, message: str, level: str = "ok") -> None:
    request.session["flash"] = {"message": message, "level": level}


def next_folio(db: Session, model, field_name: str, prefix: str) -> str:
    from sqlalchemy import func, select

    count = db.scalar(select(func.count()).select_from(model)) or 0
    return f"{prefix}-{count + 1:04d}"
