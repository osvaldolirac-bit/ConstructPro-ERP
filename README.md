# ConstructPro ERP

ERP para construcción con carriles independientes en el VPS.

## Carril Río Maipo

URL pública prevista: **https://erpmaster.cl/riomaipo**

Módulos:

- **Dashboard** — resumen de cobranza, cotizaciones y obras
- **Cotizaciones** — emisión con partidas / APU
- **Cuentas por cobrar** — estados de pago, retenciones y abonos
- **Administración** — clientes, parámetros y obras

Este carril corre separado de otros entornos (producción / demo): usa tablas con prefijo `riomaipo_` y rutas bajo `/riomaipo`.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abrir: http://127.0.0.1:8000/riomaipo/

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `RIOMAIPO_PREFIX` | `/riomaipo` | Prefijo de ruta del carril |
| `DATABASE_URL` | SQLite en `data/riomaipo.db` | Ej. MySQL: `mysql+pymysql://user:pass@localhost/constructpro_riomaipo` |
| `SECRET_KEY` | valor de desarrollo | Clave de sesión |

## Despliegue VPS (Passenger / cPanel)

1. Subir el código al document root o app root de Python.
2. Configurar la aplicación Passenger con `passenger_wsgi.py`.
3. Definir **Application URL / Base URI** como `/riomaipo` (o alias `erpmaster.cl/riomaipo`).
4. Instalar dependencias del `requirements.txt` en el entorno Python del hosting.
5. (Opcional) Crear BD MySQL y setear `DATABASE_URL`.

La raíz `/` responde JSON con el mapa de carriles; la UI del producto está en `/riomaipo`.

## Prototipo Streamlit (laboratorio)

```bash
streamlit run app_streamlit.py --server.port 8501
```

No forma parte del carril `riomaipo` en producción.
