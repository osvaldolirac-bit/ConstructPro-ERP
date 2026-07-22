#!/bin/bash
# Restaura /riomaipo en nginx si falta. Ejecutar como root.
set -euo pipefail
CFG=/etc/nginx/sites-available/erpmaster.cl
SRC=/root/erpmaster.cl.nginx.conf
if ! grep -q 'location /riomaipo/' "$CFG" 2>/dev/null; then
  logger -t riomaipo-nginx "MISSING /riomaipo — restoring from $SRC"
  chattr -i "$CFG" 2>/dev/null || true
  cp -a "$SRC" "$CFG"
  nginx -t
  systemctl reload nginx
fi
if grep -q 'location /riomaipo/' "$CFG"; then
  chattr +i "$CFG" 2>/dev/null || true
fi
