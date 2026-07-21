import os
import sys

# Raíz del proyecto en el path de Python (cPanel / Passenger)
sys.path.insert(0, os.path.dirname(__file__))

# Prefijo público: https://erpmaster.cl/riomaipo
# - Si el proxy reenvía la ruta completa, dejar RIOMAIPO_PREFIX=/riomaipo (default).
# - Si Passenger monta la app DENTRO de /riomaipo y recorta el prefijo,
#   definir en el hosting: RIOMAIPO_PREFIX=
os.environ.setdefault("RIOMAIPO_PREFIX", "/riomaipo")

from app.main import app as application  # noqa: E402
