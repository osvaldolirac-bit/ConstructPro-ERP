#!/usr/bin/env bash
# Arranca Río Maipo en modo Streamlit (igual que demo / La Concepción).
# Puerto 8503 — NUNCA el de La Concepción.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${RIOMAIPO_PORT:-8503}"

if command -v ss >/dev/null 2>&1; then
  if ss -ltn | grep -q ":${PORT} "; then
    echo "ERROR: puerto ${PORT} ocupado. Río Maipo usa 8503; La Concepción/demo otros 85xx."
    ss -ltnp | grep ":${PORT} " || true
    exit 1
  fi
fi

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
echo "Río Maipo → http://127.0.0.1:${PORT}/riomaipo/"
exec streamlit run app_riomaipo.py \
  --server.address 127.0.0.1 \
  --server.port "${PORT}" \
  --server.baseUrlPath riomaipo \
  --server.headless true \
  --browser.gatherUsageStats false
