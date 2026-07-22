# ConstructPro ERP — Carril Río Maipo

URL: **https://erpmaster.cl/riomaipo/**

## Plataforma

Río Maipo corre en **Flask + Bootstrap 5 + DataTables** (UI tipo SOLUERP), no Streamlit.

| Ruta | App | Puerto |
|------|-----|--------|
| `/laconcepcion/` | Streamlit La Concepción | 85xx |
| `/demo/` | Streamlit Demo | otro 85xx |
| **`/riomaipo/`** | **Flask Río Maipo (`rmweb`)** | **8505** |

Misma base SQLite de producción: `data/riomaipo_erp.db`.

## Módulos

- Dashboard
- Clientes
- Cotizaciones (KPIs, DataTables, Ver/PDF/Edit/Del, PDF formato Agrocastilla)
- Cuentas por cobrar (KPIs, factura, abonos, Vista 360)
- Administración (empresa / parámetros)

## Local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD
export RIOMAIPO_DB=$PWD/data/riomaipo_erp.db
gunicorn -b 127.0.0.1:8505 -w 2 rmweb.wsgi:app
```

Abrir: http://127.0.0.1:8505/login

## VPS

Servicio: `erp-riomaipo` → gunicorn  
Nginx: `location /riomaipo/` → `proxy_pass http://127.0.0.1:8505/;` + `X-Forwarded-Prefix /riomaipo`

```bash
systemctl status erp-riomaipo
curl -sI https://erpmaster.cl/riomaipo/login
```

Acceso: `osvaldolira@constructorariomaipo.cl` / clave `9083`

## Nota

`app_riomaipo.py` (Streamlit) queda como referencia histórica; la app activa es `rmweb/`.
