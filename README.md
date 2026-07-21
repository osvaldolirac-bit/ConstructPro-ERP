# ConstructPro ERP — Carril Río Maipo

URL pública: **https://erpmaster.cl/riomaipo/**

## Problema actual en el VPS

Nginx está mandando `/riomaipo` a **La Concepción**:

```
https://erpmaster.cl/riomaipo  →  302  →  /laconcepcion/
```

Eso no es un bug de esta app: falta el `location /riomaipo/` en nginx y el proceso en el **puerto 8010**.

### Puertos (no mezclar)

| Carril | Stack | Puerto interno |
|--------|--------|----------------|
| La Concepción | Streamlit | 85xx (ej. 8501) |
| Demo | Streamlit | otro 85xx |
| **Río Maipo** | **FastAPI / uvicorn** | **8010** |

Si apuntas `/riomaipo` al puerto de La Concepción, verás ese ERP.

## Módulos

- Dashboard
- Cotizaciones
- Cuentas por cobrar
- Administración (clientes, parámetros, obras)

Datos aislados en tablas `riomaipo_*`.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/start_riomaipo.sh
# o: uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Abrir: http://127.0.0.1:8010/riomaipo/

Verificar identidad: http://127.0.0.1:8010/riomaipo/health  
Debe responder `"track": "riomaipo"` (nunca La Concepción).

## Despliegue VPS (nginx + uvicorn)

1. Clonar/actualizar el repo en el servidor (ej. `/var/www/erpmaster/constructpro-erp`).
2. Crear venv e instalar `requirements.txt`.
3. Ajustar rutas en `deploy/riomaipo.service` y activar:

```bash
sudo cp deploy/riomaipo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now riomaipo
sudo systemctl status riomaipo
```

4. Incluir el bloque nginx **antes** del redirect a `/laconcepcion/`:

```bash
# revisar/editar rutas del include
sudo nano /etc/nginx/sites-available/erpmaster.cl
# include .../deploy/nginx-riomaipo.conf;
sudo nginx -t && sudo systemctl reload nginx
```

5. Probar:

```bash
curl -sI https://erpmaster.cl/riomaipo/     # debe ser 200, NO 302 a laconcepcion
curl -s https://erpmaster.cl/riomaipo/health
```

Archivos de referencia:

- `deploy/nginx-riomaipo.conf`
- `deploy/riomaipo.service`
- `scripts/start_riomaipo.sh`

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RIOMAIPO_PREFIX` | `/riomaipo` | Prefijo público |
| `RIOMAIPO_PORT` | `8010` | Puerto uvicorn (exclusivo) |
| `DATABASE_URL` | SQLite `data/riomaipo.db` | MySQL opcional |
| `SECRET_KEY` | valor de desarrollo | Sesiones |

## Nota

`app_streamlit.py` es solo laboratorio local. **No** usarlo para publicar `/riomaipo` en el VPS.
