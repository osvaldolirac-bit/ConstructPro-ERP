#!/usr/bin/env bash
# Arranca SOLO el carril Río Maipo en el puerto 8010.
# No usar puertos de La Concepción (Streamlit 85xx) ni demo.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${RIOMAIPO_PORT:-8010}"
export RIOMAIPO_PREFIX="${RIOMAIPO_PREFIX:-/riomaipo}"

if command -v ss >/dev/null 2>&1; then
  if ss -ltn | grep -q ":${PORT} "; then
    echo "ERROR: el puerto ${PORT} ya está en uso."
    echo "Río Maipo debe usar 8010. No lo apuntes al puerto de La Concepción/demo."
    ss -ltnp | grep ":${PORT} " || true
    exit 1
  fi
fi

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Iniciando Río Maipo en 127.0.0.1:${PORT}${RIOMAIPO_PREFIX}/"
exec uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
