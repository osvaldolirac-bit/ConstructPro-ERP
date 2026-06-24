# ConstructPro-ERP

A construction-industry ERP (Spanish/Chilean market). Two Python entry points:

- **FastAPI backend** — `app/main.py` (`app` object). Production hosting uses `passenger_wsgi.py` (Passenger/cPanel). Currently a skeleton with a single `GET /` welcome route.
- **Streamlit prototype** — `app_streamlit.py`. Interactive demo UI with simulated data (Dashboard, Cotizaciones/APU calculator, Estados de Pago).

## Cursor Cloud specific instructions

- Dependencies are installed into a virtualenv at `.venv` (created by the update script). Use `.venv/bin/...` to run tools, or `source .venv/bin/activate`.
- `streamlit` is required by `app_streamlit.py` but was historically missing from `requirements.txt`; it has been added there. Keep it in `requirements.txt`.
- Run the services (dev mode):
  - FastAPI: `.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (root `GET /`, docs at `/docs`).
  - Streamlit: `.venv/bin/streamlit run app_streamlit.py --server.port 8501 --server.address 0.0.0.0 --server.headless true` (UI at `:8501`).
- No database is needed currently. `sqlalchemy`/`pymysql`/`cryptography` are forward-looking placeholders — no models, connection code, or config exist yet, so MySQL/MariaDB is not required to run either service.
- There are no automated tests, linters, or build steps configured in this repo.
