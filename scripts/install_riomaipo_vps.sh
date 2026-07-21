#!/usr/bin/env bash
# Instala Río Maipo en el VPS al estilo /demo y /laconcepcion.
# DEBE ejecutarse EN EL SERVIDOR (erpmaster.cl), con sudo.
#
#   cd /var/www/erpmaster/constructpro-erp   # o la ruta real del repo
#   sudo bash scripts/install_riomaipo_vps.sh
#
set -euo pipefail

PORT=8503
BASE_PATH="riomaipo"
APP_FILE="app_riomaipo.py"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="riomaipo"
SNIPPET_NAME="riomaipo-location.conf"

echo "==> ERP Master · instalación Río Maipo"
echo "    App:  ${ROOT}/${APP_FILE}"
echo "    Puerto exclusivo: ${PORT} (NO usar el de La Concepción)"
echo

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: ejecuta con sudo."
  exit 1
fi

# 1) Dependencias Python
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
mkdir -p data
chown -R www-data:www-data "$ROOT/data" 2>/dev/null || true

# 2) Liberar / verificar puerto
if command -v ss >/dev/null 2>&1; then
  if ss -ltnp | grep -q ":${PORT} "; then
    echo "AVISO: puerto ${PORT} en uso. Se reiniciará el servicio ${SERVICE_NAME}."
  fi
fi

# 3) Systemd
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=ERP Master - Rio Maipo (Streamlit :${PORT})
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${ROOT}
Environment=STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ExecStart=${ROOT}/.venv/bin/streamlit run ${APP_FILE} \\
  --server.address 127.0.0.1 \\
  --server.port ${PORT} \\
  --server.baseUrlPath ${BASE_PATH} \\
  --server.headless true \\
  --browser.gatherUsageStats false
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
sleep 2
systemctl --no-pager --full status "${SERVICE_NAME}" | head -20 || true

# 4) Snippet nginx
SNIPPET="/etc/nginx/snippets/${SNIPPET_NAME}"
cat > "$SNIPPET" <<EOF
# Generado por install_riomaipo_vps.sh — NO redirigir a La Concepción
location = /riomaipo {
    return 301 /riomaipo/;
}
location /riomaipo/ {
    proxy_pass http://127.0.0.1:${PORT}/riomaipo/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
    proxy_buffering off;
}
location /riomaipo/_stcore/ {
    proxy_pass http://127.0.0.1:${PORT}/riomaipo/_stcore/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host \$host;
    proxy_read_timeout 86400;
}
EOF

# 5) Insertar include en el server de erpmaster.cl (antes del catch-all)
NGINX_FILE=""
for candidate in \
  /etc/nginx/sites-available/erpmaster.cl \
  /etc/nginx/sites-available/erpmaster \
  /etc/nginx/sites-enabled/erpmaster.cl \
  /etc/nginx/sites-enabled/default \
  /etc/nginx/conf.d/erpmaster.conf
do
  if [[ -f "$candidate" ]]; then
    NGINX_FILE="$candidate"
    break
  fi
done

if [[ -z "$NGINX_FILE" ]]; then
  NGINX_FILE="$(rg -l -g'*.conf' 'laconcepcion|erpmaster\.cl' /etc/nginx 2>/dev/null | head -1 || true)"
fi

if [[ -z "$NGINX_FILE" ]]; then
  echo
  echo "ERROR: no encontré el vhost de nginx."
  echo "Agrega MANUALMENTE esta línea DENTRO del server { } de erpmaster.cl,"
  echo "ANTES de cualquier 'return 302 /laconcepcion':"
  echo "    include ${SNIPPET};"
  exit 2
fi

echo "==> Vhost nginx: ${NGINX_FILE}"
cp -a "$NGINX_FILE" "${NGINX_FILE}.bak.riomaipo.$(date +%Y%m%d%H%M%S)"

INCLUDE_LINE="    include ${SNIPPET};"

if rg -q "snippets/${SNIPPET_NAME}|${SNIPPET_NAME}" "$NGINX_FILE"; then
  echo "    include ya presente."
else
  # Insertar justo después de la línea 'server {' del primer server block
  # o antes del primer return/redirect a laconcepcion
  if rg -q 'laconcepcion' "$NGINX_FILE"; then
    # Insertar ANTES de la primera mención a laconcepcion
    python3 - <<PY
from pathlib import Path
path = Path("${NGINX_FILE}")
text = path.read_text()
line = "${INCLUDE_LINE}\n"
if "snippets/${SNIPPET_NAME}" in text:
    raise SystemExit(0)
idx = text.lower().find("laconcepcion")
if idx == -1:
    # fallback: after first server {
    idx2 = text.find("server {")
    if idx2 == -1:
        raise SystemExit("no server block")
    # insert after opening brace line
    nl = text.find("\n", idx2)
    text = text[: nl + 1] + line + text[nl + 1 :]
else:
    # find start of that line
    start = text.rfind("\n", 0, idx) + 1
    text = text[:start] + line + text[start:]
path.write_text(text)
print("    include insertado ANTES de la regla laconcepcion")
PY
  else
    python3 - <<PY
from pathlib import Path
path = Path("${NGINX_FILE}")
text = path.read_text()
line = "${INCLUDE_LINE}\n"
idx2 = text.find("server {")
nl = text.find("\n", idx2)
text = text[: nl + 1] + line + text[nl + 1 :]
path.write_text(text)
print("    include insertado tras server {")
PY
  fi
fi

nginx -t
systemctl reload nginx

echo
echo "==> Pruebas locales"
curl -sI "http://127.0.0.1:${PORT}/${BASE_PATH}/" | head -5 || true
curl -sI -H "Host: erpmaster.cl" "http://127.0.0.1/riomaipo/" | head -8 || true

echo
echo "LISTO. Abre: https://erpmaster.cl/riomaipo/"
echo "Debe decir 'ERP Master · Río Maipo' — si ves La Concepción, el include quedó DESPUÉS del redirect."
echo "Revisa: sudo nginx -T 2>/dev/null | less  (busca location /riomaipo)"
