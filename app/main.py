"""ConstructPro ERP — punto de entrada FastAPI (Passenger / VPS)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import BASE_DIR, RIOMAIPO_PREFIX, SECRET_KEY
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
    title="ConstructPro ERP",
    description=(
        "Sistema de Gestión para la Construcción. "
        "Carril Río Maipo en /riomaipo (dashboard, cotizaciones, CxC y administración)."
    ),
    version="1.1.0",
    lifespan=lifespan,
    root_path="",  # PassengerBaseURI se refleja vía SCRIPT_NAME
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
    return {
        "estado": "En línea",
        "mensaje": "ConstructPro-ERP operativo.",
        "carriles": {
            "riomaipo": {
                "url": RIOMAIPO_PREFIX,
                "publico": "https://erpmaster.cl/riomaipo",
                "modulos": [
                    "dashboard",
                    "cotizaciones",
                    "cuentas-por-cobrar",
                    "administracion",
                ],
            }
        },
    }


@app.get("/health")
def health():
    return {"ok": True, "track": "constructpro", "riomaipo": RIOMAIPO_PREFIX}
