"""Configuración del ERP y del carril Río Maipo."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Prefijo público en el VPS: https://erpmaster.cl/riomaipo
# Vacío ("") si Passenger ya monta la app dentro de /riomaipo.
_raw_prefix = os.getenv("RIOMAIPO_PREFIX", "/riomaipo").strip()
RIOMAIPO_PREFIX = "" if _raw_prefix in {"", "/"} else _raw_prefix.rstrip("/")

# SQLite por defecto (portable). En producción puede ser MySQL:
# DATABASE_URL=mysql+pymysql://user:pass@localhost/constructpro_riomaipo
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'riomaipo.db'}",
)

SECRET_KEY = os.getenv("SECRET_KEY", "riomaipo-dev-change-me")
APP_NAME = "ERP Master"
TRACK_NAME = "Río Maipo"
TRACK_SLUG = "riomaipo"

# Puerto exclusivo del carril (VPS). NO reutilizar el de La Concepción (Streamlit 85xx).
RIOMAIPO_PORT = int(os.getenv("RIOMAIPO_PORT", "8010"))
