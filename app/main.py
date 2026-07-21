"""ConstructPro ERP — punto de entrada FastAPI (nginx + uvicorn en VPS)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import (
    BASE_DIR,
    RIOMAIPO_PORT,
    RIOMAIPO_PREFIX,
    SECRET_KEY,
    TRACK_NAME,
    TRACK_SLUG,
)
from app.core.database import SessionLocal, init_db
from app.tracks.riomaipo.router import router as riomaipo_router
from app.tracks.riomaipo.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=f"ERP Master — {TRACK_NAME}",
    description=(
        f"Carril independiente {TRACK_NAME} en {RIOMAIPO_PREFIX or '/'}. "
        "No comparte proceso ni puerto con La Concepción / demo."
    ),
    version="1.1.1",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

_static_path = f"{RIOMAIPO_PREFIX}/static" if RIOMAIPO_PREFIX else "/static"
app.mount(
    _static_path,
    StaticFiles(directory=str(BASE_DIR / "app" / "static" / "riomaipo")),
    name="riomaipo-static",
)
app.include_router(riomaipo_router, prefix=RIOMAIPO_PREFIX or "")


@app.get("/")
def inicio():
    """Evita caer en otros ERP: la raíz del proceso apunta al carril Río Maipo."""
    target = f"{RIOMAIPO_PREFIX}/" if RIOMAIPO_PREFIX else "/"
    return RedirectResponse(url=target, status_code=302)


@app.get("/health")
def health_root():
    return {
        "ok": True,
        "track": TRACK_SLUG,
        "nombre": TRACK_NAME,
        "prefix": RIOMAIPO_PREFIX,
        "port": RIOMAIPO_PORT,
        "nota": "Si ves La Concepción, nginx está mal enrutando /riomaipo",
    }


# Health también bajo el prefijo público (útil detrás de nginx)
if RIOMAIPO_PREFIX:

    @app.get(f"{RIOMAIPO_PREFIX}/health")
    def health_prefixed():
        return health_root()
