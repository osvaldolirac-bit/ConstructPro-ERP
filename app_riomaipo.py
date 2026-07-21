"""
ERP Master — Río Maipo
Inspirado en SOLUERP, con gestión mejorada:
- Flujo cotización → aprobación → cuenta por cobrar
- Aging de cobranza y alertas de mora/vencimiento
- Catálogo de productos, proveedores y vista 360 del cliente
"""

from __future__ import annotations

import base64
import sqlite3
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "riomaipo_erp.db"
LOGO_PATH = BASE_DIR / "static" / "logo_erpmaster.png"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="ERP Master · Río Maipo",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    # st.html keeps <style>/<link>; st.markdown strips them and dumps CSS as text.
    st.html(
        """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #eef2f7;
    --bg-soft: #f7f9fc;
    --panel: #ffffff;
    --panel-soft: #f3f6fb;
    --line: #d7e0ea;
    --line-strong: #c3cfdb;
    --text: #1a2b3c;
    --muted: #5b6b7c;
    --brand: #163a5f;
    --accent: #2f6fed;
    --accent-soft: #e8f0fe;
    --ok: #1f8a65;
    --ok-bg: #e8f7f1;
    --warn: #9a6b12;
    --warn-bg: #fff6e5;
    --danger: #b42318;
    --danger-bg: #fdecea;
    --shadow: 0 8px 24px rgba(22, 58, 95, 0.08);
    --radius: 14px;
    --font-display: "Source Serif 4", Georgia, serif;
    --font-body: "Manrope", "Segoe UI", sans-serif;
  }

  html, body, [data-testid="stAppViewContainer"], .stApp {
    background:
      linear-gradient(180deg, #e8eef6 0%, var(--bg) 28%, var(--bg-soft) 100%) !important;
    color: var(--text);
    font-family: var(--font-body) !important;
  }

  [data-testid="stHeader"] {
    background: transparent !important;
    color: var(--brand) !important;
  }
  /* Keep toolbar/header so the sidebar expand control stays reachable */
  #MainMenu, footer { visibility: hidden; }
  [data-testid="stToolbar"] {
    visibility: visible !important;
    height: auto !important;
  }
  /* Hide deploy/chrome chrome, but NEVER the sidebar reopen button */
  [data-testid="stToolbar"] [data-testid="stAppDeployButton"],
  [data-testid="stToolbar"] [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  [data-testid="stToolbarActions"] {
    display: none !important;
  }
  [data-testid="stExpandSidebarButton"],
  [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    position: fixed !important;
    left: .65rem !important;
    top: .65rem !important;
    z-index: 100000 !important;
    width: 2.4rem !important;
    height: 2.4rem !important;
    border-radius: 10px !important;
    background: #ffffff !important;
    border: 1px solid var(--line-strong) !important;
    box-shadow: var(--shadow) !important;
    color: var(--brand) !important;
  }
  .block-container {
    padding-top: 1.1rem !important;
    padding-bottom: 2.4rem !important;
    max-width: 1240px;
  }

  section[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid var(--line);
    box-shadow: 4px 0 24px rgba(22, 58, 95, 0.04);
  }
  section[data-testid="stSidebar"] * { font-family: var(--font-body) !important; color: var(--text); }
  section[data-testid="stSidebar"] .stRadio > label { display: none; }
  section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: .62rem .8rem;
    margin-bottom: .2rem;
    transition: .15s ease;
    color: var(--text) !important;
  }
  section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
    background: var(--panel-soft);
  }
  section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label[data-checked="true"],
  section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
    background: var(--accent-soft);
    border-color: #bfd4fb;
    box-shadow: inset 3px 0 0 var(--accent);
  }

  h1,h2,h3,h4 {
    font-family: var(--font-display) !important;
    font-weight: 700 !important;
    letter-spacing: -.015em;
    color: var(--brand) !important;
  }
  p, label, span, div { font-family: var(--font-body); }
  [data-testid="stMarkdownContainer"] p { color: var(--muted); }
  [data-testid="stMarkdownContainer"] strong { color: var(--text); }

  .rm-hero {
    position: relative; overflow: hidden;
    background:
      linear-gradient(120deg, #163a5f 0%, #1f4f86 55%, #2f6fed 120%);
    border: 1px solid #13406d;
    border-radius: 16px;
    padding: 1.2rem 1.35rem 1.15rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow);
    animation: rise .45s ease both;
  }
  .rm-hero::after {
    content: ""; position: absolute; inset: auto -8% -55% auto; width: 260px; height: 260px;
    background: radial-gradient(circle, rgba(255,255,255,.18), transparent 68%);
    pointer-events: none;
  }
  .rm-kicker {
    display:inline-block; font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
    color: #d7e6ff; margin-bottom: .3rem; font-weight: 700;
  }
  .rm-hero h1 {
    margin: 0; font-size: clamp(1.55rem, 2.3vw, 2.1rem);
    color: #ffffff !important; line-height: 1.15;
  }
  .rm-hero p { margin: .35rem 0 0; color: #dce8f8; max-width: 64ch; }
  .rm-chip {
    display:inline-flex; gap:.45rem; align-items:center; margin-top:.65rem;
    padding:.28rem .7rem; border-radius:999px; font-size:.78rem; color: #fff;
    background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.28);
  }

  .rm-page-head { margin: .15rem 0 .95rem; animation: fade-up .4s ease both; }
  .rm-page-head h2 {
    margin: 0; font-size: clamp(1.35rem, 1.9vw, 1.75rem); color: var(--brand) !important;
  }
  .rm-page-head p { margin: .28rem 0 0; color: var(--muted); }

  .kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: .7rem;
    margin: 0 0 1rem; animation: fade-up .45s ease both;
  }
  .kpi {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: .95rem 1rem;
    box-shadow: var(--shadow);
    border-left: 4px solid var(--accent);
    transition: transform .15s ease, border-color .15s ease;
  }
  .kpi:hover { transform: translateY(-2px); border-color: var(--line-strong); }
  .kpi.danger { border-left-color: var(--danger); }
  .kpi.warn { border-left-color: #d59a1b; }
  .kpi.ok { border-left-color: var(--ok); }
  .kpi span {
    display:block; color: var(--muted); font-size: .75rem;
    letter-spacing: .04em; text-transform: uppercase; font-weight: 700;
  }
  .kpi strong {
    display:block; margin-top: .35rem; font-family: var(--font-body);
    font-size: 1.35rem; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums;
  }
  .kpi.danger strong { color: var(--danger); }
  .kpi.warn strong { color: #9a6b12; }
  .kpi.ok strong { color: var(--ok); }

  .panel {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 1rem 1.05rem; margin-bottom: .85rem; box-shadow: var(--shadow);
    animation: fade-up .45s ease both;
  }
  .panel h3 { margin: 0 0 .7rem; font-size: 1.1rem; color: var(--brand) !important; }

  .alert-box {
    border-radius: 12px; padding: .8rem .95rem; margin: .35rem 0;
    border: 1px solid var(--line); animation: fade-up .3s ease both;
    font-size: .92rem; line-height: 1.35;
  }
  .alert-danger { background: var(--danger-bg); border-color: #f3c1bc; color: #7a1a14; }
  .alert-warn { background: var(--warn-bg); border-color: #f0d59a; color: #6f4d0c; }
  .alert-ok { background: var(--ok-bg); border-color: #b7e2d1; color: #145c44; }

  .badge {
    display:inline-flex; align-items:center; padding: .16rem .55rem; border-radius: 999px;
    font-size: .74rem; border: 1px solid var(--line); background: var(--panel-soft);
    font-weight: 700; text-transform: capitalize;
  }
  .badge.ok { color: var(--ok); background: var(--ok-bg); border-color: #b7e2d1; }
  .badge.warn { color: #9a6b12; background: var(--warn-bg); border-color: #f0d59a; }
  .badge.danger { color: var(--danger); background: var(--danger-bg); border-color: #f3c1bc; }
  .badge.muted { color: var(--muted); }

  .sb-brand { padding: .35rem .15rem .9rem; animation: rise .4s ease both; }
  .sb-brand .k {
    color: var(--accent); font-size: .68rem; letter-spacing: .14em;
    text-transform: uppercase; font-weight: 800;
  }
  .sb-brand h2 {
    margin: .2rem 0 0; font-family: var(--font-display);
    font-size: 1.55rem; color: var(--brand) !important; line-height: 1.05;
  }
  .sb-brand p { margin: .35rem 0 0; color: var(--muted); font-size: .84rem; }

  div[data-testid="stMetric"] {
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: .7rem .85rem; box-shadow: var(--shadow);
  }
  div[data-testid="stMetricValue"] {
    font-family: var(--font-body) !important; font-size: 1.3rem !important;
    font-weight: 800 !important; color: var(--text) !important;
  }
  div[data-testid="stMetricLabel"] { color: var(--muted) !important; font-weight: 700 !important; }

  .stTabs [data-baseweb="tab-list"] {
    gap: .25rem; background: var(--panel);
    border: 1px solid var(--line); border-radius: 12px; padding: .25rem;
    margin-bottom: .55rem;
  }
  .stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 9px; color: var(--muted);
    padding: .55rem .9rem; font-weight: 700;
  }
  .stTabs [aria-selected="true"] {
    background: var(--accent-soft) !important;
    color: var(--brand) !important;
  }

  .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
  .stSelectbox div[data-baseweb="select"] > div, .stMultiSelect div[data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid var(--line-strong) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
  }
  .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(47,111,237,.15) !important;
  }
  label, [data-testid="stWidgetLabel"] p {
    color: var(--text) !important; font-weight: 700 !important; font-size: .88rem !important;
  }
  .stButton > button {
    border-radius: 10px !important; border: 1px solid var(--line-strong) !important;
    background: #ffffff !important; color: var(--brand) !important;
    font-weight: 700 !important; transition: .15s ease !important;
  }
  .stButton > button:hover {
    transform: translateY(-1px);
    border-color: var(--accent) !important;
    color: var(--accent) !important;
  }
  .stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
    background: var(--accent) !important;
    color: #ffffff !important;
    border: 1px solid #255ed4 !important;
  }
  .stButton > button[kind="primary"]:hover,
  .stButton > button[data-testid="baseButton-primary"]:hover {
    background: #255ed4 !important; color: #fff !important;
  }
  [data-testid="stForm"] {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: 1rem; box-shadow: var(--shadow);
  }
  [data-testid="stDataFrame"] {
    border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
    background: #ffffff;
    box-shadow: var(--shadow);
  }
  .stAlert { border-radius: 12px !important; }

  .empty-state {
    border: 1px dashed var(--line-strong);
    border-radius: 14px;
    padding: 1.35rem 1.15rem;
    text-align: center;
    color: var(--muted);
    background: var(--panel);
    margin: .35rem 0 .95rem;
  }
  .split-title {
    display: flex; align-items: baseline; justify-content: space-between; gap: 1rem;
    margin: .15rem 0 .75rem;
  }
  .split-title h3 {
    margin: 0; font-family: var(--font-display); font-size: 1.12rem; color: var(--brand) !important;
  }
  .split-title span { color: var(--muted); font-size: .82rem; }
  .stat-pill {
    display:inline-flex; align-items:center; gap:.4rem;
    padding:.3rem .7rem; border-radius:999px; font-size:.76rem; font-weight: 700;
    background: var(--accent-soft); border: 1px solid #bfd4fb; color: var(--brand);
  }
  .chart-wrap {
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: .85rem 1rem 1rem; margin-bottom: .85rem; box-shadow: var(--shadow);
  }
  .chart-wrap h3 { margin: 0 0 .6rem; font-size: 1.05rem; color: var(--brand) !important; }
  .soft-hr {
    border: 0; height: 1px; margin: 1rem 0;
    background: linear-gradient(90deg, transparent, var(--line-strong), transparent);
  }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    font-family: var(--font-display) !important; color: var(--brand) !important;
  }
  .stCaption, [data-testid="stCaptionContainer"] { color: var(--muted) !important; }
  iframe { border-radius: 10px; }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: var(--muted) !important; }

  .rm-footer-mark {
    margin: 2.4rem 0 .4rem;
    padding: 1.1rem 0 .2rem;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: flex-end;
    gap: .25rem;
    opacity: .18;
    pointer-events: none;
    user-select: none;
    border-top: 1px solid var(--line);
    text-align: right;
  }
  .rm-footer-mark img {
    width: min(210px, 52vw);
    height: auto;
    display: block;
    margin-left: auto;
  }
  .rm-footer-mark span {
    font-size: .68rem;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--brand);
    font-weight: 700;
  }

  @keyframes fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes rise {
    from { opacity: 0; transform: translateX(-6px); }
    to { opacity: 1; transform: translateX(0); }
  }
</style>
        """
    )
    # If the menu was collapsed, reopen it (CSS previously hid the toggle).
    components.html(
        """
<script>
(() => {
  const doc = window.parent.document;
  const clickExpand = () => {
    const btn =
      doc.querySelector('[data-testid="stExpandSidebarButton"]') ||
      doc.querySelector('[data-testid="collapsedControl"]') ||
      doc.querySelector('[data-testid="stSidebarCollapsedControl"]');
    if (btn) btn.click();
  };
  clickExpand();
  setTimeout(clickExpand, 300);
  setTimeout(clickExpand, 900);
})();
</script>
        """,
        height=0,
        width=0,
    )


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_footer() -> None:
    src = logo_data_uri()
    if not src:
        return
    st.html(
        f"""
        <div class="rm-footer-mark" aria-hidden="true">
          <img src="{src}" alt="ERP Master" />
          <span>Integración &amp; control inteligente</span>
        </div>
        """
    )


def page_header(title: str, subtitle: str = "") -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="rm-page-head"><h2>{title}</h2>{sub}</div>',
        unsafe_allow_html=True,
    )


def kpi_cards(items: list[tuple[str, str, str]]) -> None:
    # items: (label, value, tone) tone in '', 'ok', 'warn', 'danger'
    cards = "".join(
        f'<article class="kpi {tone}"><span>{label}</span><strong>{value}</strong></article>'
        for label, value, tone in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def readable_bars(
    df: pd.DataFrame,
    category: str,
    value: str,
    *,
    color: str = "#2f6fed",
    value_format: str = ",.0f",
    height: int = 280,
) -> None:
    """Horizontal bars with larger, darker labels for dashboard readability."""
    chart_df = df.copy()
    chart_df[category] = chart_df[category].astype(str)
    chart_df[value] = pd.to_numeric(chart_df[value], errors="coerce").fillna(0)
    # Keep input order
    order = chart_df[category].tolist()

    base = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusEnd=6, size=22)
        .encode(
            y=alt.Y(
                f"{category}:N",
                sort=order,
                title=None,
                axis=alt.Axis(
                    labelFontSize=13,
                    labelFontWeight=600,
                    labelColor="#1a2b3c",
                    labelLimit=220,
                    labelPadding=8,
                    ticks=False,
                    domain=False,
                ),
            ),
            x=alt.X(
                f"{value}:Q",
                title=None,
                axis=alt.Axis(
                    labelFontSize=12,
                    labelColor="#5b6b7c",
                    grid=True,
                    gridColor="#e2e8f0",
                    ticks=False,
                    domainColor="#c3cfdb",
                    format=value_format,
                ),
            ),
            color=alt.value(color),
            tooltip=[
                alt.Tooltip(f"{category}:N", title="Categoría"),
                alt.Tooltip(f"{value}:Q", title="Valor", format=value_format),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(
            align="left",
            baseline="middle",
            dx=8,
            fontSize=13,
            fontWeight=700,
            color="#163a5f",
        )
        .encode(
            y=alt.Y(f"{category}:N", sort=order),
            x=alt.X(f"{value}:Q"),
            text=alt.Text(f"{value}:Q", format=value_format),
        )
    )
    chart = (
        (base + labels)
        .properties(height=height)
        .configure_view(strokeWidth=0)
        .configure_axis(labelFont="Manrope, Segoe UI, sans-serif", titleFont="Manrope, Segoe UI, sans-serif")
    )
    st.altair_chart(chart, use_container_width=True)


def alert_line(nivel: str, msg: str) -> None:
    st.markdown(f'<div class="alert-box alert-{nivel}">{msg}</div>', unsafe_allow_html=True)


def empty_state(msg: str) -> None:
    st.markdown(f'<div class="empty-state">{msg}</div>', unsafe_allow_html=True)


inject_styles()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def clp(v) -> str:
    try:
        return f"${int(round(float(v or 0))):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def dparse(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def days_between(a: date | None, b: date | None) -> int | None:
    if not a or not b:
        return None
    return (a - b).days


def init_db() -> None:
    c = conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS empresa (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            rut TEXT, razon_social TEXT, telefono TEXT, email TEXT,
            direccion TEXT, region TEXT, pais TEXT DEFAULT 'Chile'
        );
        CREATE TABLE IF NOT EXISTS parametros (
            clave TEXT PRIMARY KEY,
            nombre TEXT, valor TEXT, unidad TEXT
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE, razon_social TEXT NOT NULL,
            contacto TEXT, telefono TEXT, email TEXT,
            direccion TEXT, comuna TEXT, activo INTEGER DEFAULT 1,
            creado_en TEXT
        );
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE, razon_social TEXT NOT NULL,
            contacto TEXT, telefono TEXT, email TEXT,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE, nombre TEXT NOT NULL,
            unidad TEXT DEFAULT 'un', precio REAL DEFAULT 0,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE, cliente_id INTEGER,
            asunto TEXT, proyecto TEXT, estado TEXT DEFAULT 'borrador',
            fecha TEXT, validez_dias INTEGER DEFAULT 30,
            subtotal REAL DEFAULT 0, iva REAL DEFAULT 0, total REAL DEFAULT 0,
            notas TEXT, cxc_id INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS cotizacion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER NOT NULL,
            producto_id INTEGER, descripcion TEXT NOT NULL,
            unidad TEXT DEFAULT 'un', cantidad REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0, total REAL DEFAULT 0,
            FOREIGN KEY(cotizacion_id) REFERENCES cotizaciones(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT UNIQUE, cliente_id INTEGER,
            cotizacion_id INTEGER, tipo_doc TEXT DEFAULT 'EP',
            concepto TEXT, fecha_emision TEXT, fecha_vencimiento TEXT,
            monto REAL DEFAULT 0, abonado REAL DEFAULT 0, saldo REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS abonos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cuenta_id INTEGER NOT NULL, fecha TEXT, monto REAL,
            medio TEXT, nota TEXT,
            FOREIGN KEY(cuenta_id) REFERENCES cuentas(id) ON DELETE CASCADE
        );
        """
    )
    if c.execute("SELECT COUNT(*) FROM empresa").fetchone()[0] == 0:
        c.execute(
            """
            INSERT INTO empresa (id, rut, razon_social, telefono, email, direccion, region, pais)
            VALUES (1, '76.073.876-K', 'Constructora Rio Maipo S.A.', '56990798992',
                    'osvaldolira@constructorariomaipo.cl', 'Parcela El Sauce lote 4, Paine',
                    'Metropolitana', 'Chile')
            """
        )
    if c.execute("SELECT COUNT(*) FROM parametros").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO parametros (clave, nombre, valor, unidad) VALUES (?,?,?,?)",
            [
                ("iva", "IVA", "19", "%"),
                ("validez_cotizacion", "Validez cotización", "30", "días"),
                ("dias_credito", "Días crédito CxC", "30", "días"),
                ("alerta_mora", "Alerta mora desde", "1", "días"),
            ],
        )
    if c.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
        today = date.today().isoformat()
        c.executemany(
            """
            INSERT INTO clientes (rut, razon_social, contacto, telefono, email, direccion, comuna, creado_en)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "76.123.456-7",
                    "Inmobiliaria Valle Sur SpA",
                    "Carolina Méndez",
                    "+56 9 8765 4321",
                    "compras@vallesur.cl",
                    "Av. Las Condes 12000",
                    "Santiago",
                    today,
                ),
                (
                    "77.987.654-3",
                    "Constructora Andes Ltda.",
                    "Pedro Rojas",
                    "+56 2 2345 6789",
                    "admin@andesltda.cl",
                    "Camino El Alba 450",
                    "Puente Alto",
                    today,
                ),
            ],
        )
        c.executemany(
            "INSERT INTO proveedores (rut, razon_social, contacto, telefono, email) VALUES (?,?,?,?,?)",
            [
                ("76.555.111-2", "Cementos del Sur SpA", "Luis Pérez", "+56 2 2000 1000", "ventas@cementosur.cl"),
                ("76.222.333-4", "Aceros Maipo Ltda.", "Ana Soto", "+56 9 7000 2000", "contacto@acerosmaipo.cl"),
            ],
        )
        c.executemany(
            "INSERT INTO productos (codigo, nombre, unidad, precio) VALUES (?,?,?,?)",
            [
                ("HOR-H25", "Hormigón H25 m3", "m3", 95000),
                ("RAD-M2", "Radier hormigón m2", "m2", 18500),
                ("EST-M2", "Estuco exterior m2", "m2", 9200),
                ("MO-MAESTRO", "Hora maestro", "h", 5000),
            ],
        )
        # Cotización ejemplo
        cur = c.cursor()
        cur.execute(
            """
            INSERT INTO cotizaciones (folio, cliente_id, asunto, proyecto, estado, fecha, validez_dias, subtotal, iva, total, notas)
            VALUES ('COT-0001', 1, 'Etapa 1 terminaciones', 'Condominio Río Maipo', 'enviada', ?, 30, 15692000, 2981480, 18673480, 'Referencia SOLUERP')
            """,
            (date.today().isoformat(),),
        )
        cid = cur.lastrowid
        cur.executemany(
            """
            INSERT INTO cotizacion_items (cotizacion_id, producto_id, descripcion, unidad, cantidad, precio_unitario, total)
            VALUES (?,?,?,?,?,?,?)
            """,
            [
                (cid, 2, "Radier hormigón m2", "m2", 420, 18500, 7770000),
                (cid, 3, "Estuco exterior m2", "m2", 860, 9200, 7912000),
            ],
        )
        # CxC ejemplo
        em = date.today() - timedelta(days=25)
        ve = date.today() - timedelta(days=5)
        cur.execute(
            """
            INSERT INTO cuentas (documento, cliente_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
            VALUES ('EP-0001', 1, 'EP', 'Estado de pago N°1', ?, ?, 15000000, 5000000, 10000000, 'parcial')
            """,
            (em.isoformat(), ve.isoformat()),
        )
        cxc = cur.lastrowid
        cur.execute(
            "INSERT INTO abonos (cuenta_id, fecha, monto, medio, nota) VALUES (?,?,?,?,?)",
            (cxc, (date.today() - timedelta(days=10)).isoformat(), 5000000, "transferencia", "Abono parcial"),
        )
        em2 = date.today() - timedelta(days=5)
        ve2 = date.today() + timedelta(days=25)
        c.execute(
            """
            INSERT INTO cuentas (documento, cliente_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
            VALUES ('EP-0002', 2, 'EP', 'Estado de pago N°1', ?, ?, 8000000, 0, 8000000, 'pendiente')
            """,
            (em2.isoformat(), ve2.isoformat()),
        )
    c.commit()
    c.close()


def param(c: sqlite3.Connection, clave: str, default: float = 0.0) -> float:
    row = c.execute("SELECT valor FROM parametros WHERE clave=?", (clave,)).fetchone()
    if not row:
        return default
    try:
        return float(row["valor"])
    except ValueError:
        return default


def next_code(c: sqlite3.Connection, table: str, field: str, prefix: str) -> str:
    n = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] + 1
    return f"{prefix}-{n:04d}"


def recalc_cuenta(c: sqlite3.Connection, cuenta_id: int) -> None:
    row = c.execute("SELECT monto FROM cuentas WHERE id=?", (cuenta_id,)).fetchone()
    abonado = c.execute(
        "SELECT COALESCE(SUM(monto),0) AS s FROM abonos WHERE cuenta_id=?", (cuenta_id,)
    ).fetchone()["s"]
    monto = float(row["monto"])
    saldo = max(0.0, monto - float(abonado))
    estado = "pagado" if saldo <= 0 else ("parcial" if abonado > 0 else "pendiente")
    c.execute(
        "UPDATE cuentas SET abonado=?, saldo=?, estado=? WHERE id=?",
        (abonado, saldo, estado, cuenta_id),
    )


def aging_bucket(venc: date | None, hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    if not venc:
        return "sin fecha"
    d = (hoy - venc).days
    if d < 0:
        return "por vencer"
    if d == 0:
        return "vence hoy"
    if d <= 30:
        return "1-30 días mora"
    if d <= 60:
        return "31-60 días mora"
    return "+60 días mora"


init_db()
db = conn()
empresa = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()

# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
razon = empresa["razon_social"] if empresa else "Constructora Río Maipo"
rut_emp = empresa["rut"] if empresa else "—"

MODULOS = [
    "Dashboard",
    "Clientes",
    "Proveedores",
    "Productos",
    "Cotizaciones",
    "Cuentas por cobrar",
    "Administración",
]
with st.sidebar:
    st.markdown(
        f"""
        <div class="sb-brand">
          <div class="k">ERP Master</div>
          <h2>Río Maipo</h2>
          <p>{razon}<br/>RUT {rut_emp}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="soft-hr">', unsafe_allow_html=True)
    modulo = st.radio("Navegación", MODULOS, label_visibility="collapsed")
    st.markdown('<hr class="soft-hr">', unsafe_allow_html=True)
    st.caption("Control comercial · cobranza · catálogo · vista 360")
    st.markdown(
        '<span class="stat-pill">erpmaster.cl/riomaipo</span>',
        unsafe_allow_html=True,
    )

if modulo == "Dashboard":
    st.markdown(
        f"""
        <div class="rm-hero">
          <div class="rm-kicker">ERP Master</div>
          <h1>{razon}</h1>
          <p>Panel comercial y cobranza: saldos, mora, embudo de cotizaciones y aging.</p>
          <span class="rm-chip">RUT {rut_emp} · actualizado {date.today().strftime('%d/%m/%Y')}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div class="rm-hero" style="padding:1rem 1.25rem;">
          <div class="rm-kicker">ERP Master · Río Maipo</div>
          <h1 style="font-size:clamp(1.35rem,2vw,1.75rem);">{modulo}</h1>
          <p style="margin-top:.25rem;">{razon}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ===========================================================================
# DASHBOARD
# ===========================================================================
if modulo == "Dashboard":
    page_header("Dashboard de gestión", "Salud de cartera, embudo comercial y aging de cobranza.")
    hoy = date.today()

    cotas = db.execute("SELECT estado, COUNT(*) n, COALESCE(SUM(total),0) t FROM cotizaciones GROUP BY estado").fetchall()
    por_estado = {r["estado"]: (r["n"], r["t"]) for r in cotas}
    cuentas = db.execute("SELECT * FROM cuentas").fetchall()
    n_clientes = db.execute("SELECT COUNT(*) n FROM clientes WHERE activo=1").fetchone()["n"]
    saldo_total = sum(float(x["saldo"]) for x in cuentas)
    vencido = 0.0
    por_vencer_7 = 0.0
    for x in cuentas:
        if float(x["saldo"]) <= 0:
            continue
        ve = dparse(x["fecha_vencimiento"])
        if ve and ve < hoy:
            vencido += float(x["saldo"])
        elif ve and 0 <= (ve - hoy).days <= 7:
            por_vencer_7 += float(x["saldo"])

    kpi_cards(
        [
            ("Saldo por cobrar", clp(saldo_total), ""),
            ("Vencido (mora)", clp(vencido), "danger" if vencido > 0 else "ok"),
            ("Vence en 7 días", clp(por_vencer_7), "warn" if por_vencer_7 > 0 else "ok"),
            ("Cotiz. aprobadas", str(por_estado.get("aprobada", (0, 0))[0]), "ok"),
            ("Clientes activos", str(n_clientes), ""),
        ]
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('<div class="chart-wrap"><h3>Embudo de cotizaciones</h3>', unsafe_allow_html=True)
        funnel = pd.DataFrame(
            [
                {"Etapa": "Borrador", "Cantidad": por_estado.get("borrador", (0, 0))[0]},
                {"Etapa": "Enviada", "Cantidad": por_estado.get("enviada", (0, 0))[0]},
                {"Etapa": "Aprobada", "Cantidad": por_estado.get("aprobada", (0, 0))[0]},
                {"Etapa": "Rechazada", "Cantidad": por_estado.get("rechazada", (0, 0))[0]},
            ]
        )
        readable_bars(funnel, "Etapa", "Cantidad", color="#2f6fed", value_format=",.0f", height=260)
        st.markdown("</div>", unsafe_allow_html=True)
    with col_b:
        st.markdown('<div class="chart-wrap"><h3>Aging cuentas por cobrar</h3>', unsafe_allow_html=True)
        buckets = {
            "Por vencer": 0.0,
            "Vence hoy": 0.0,
            "1-30 días mora": 0.0,
            "31-60 días mora": 0.0,
            "+60 días mora": 0.0,
            "Sin fecha": 0.0,
        }
        label_map = {
            "por vencer": "Por vencer",
            "vence hoy": "Vence hoy",
            "1-30 días mora": "1-30 días mora",
            "31-60 días mora": "31-60 días mora",
            "+60 días mora": "+60 días mora",
            "sin fecha": "Sin fecha",
        }
        for x in cuentas:
            if float(x["saldo"]) <= 0:
                continue
            b = aging_bucket(dparse(x["fecha_vencimiento"]), hoy)
            key = label_map.get(b, b)
            buckets[key] = buckets.get(key, 0) + float(x["saldo"])
        aging_df = pd.DataFrame({"Tramo": list(buckets.keys()), "Saldo": list(buckets.values())})
        readable_bars(aging_df, "Tramo", "Saldo", color="#163a5f", value_format=",.0f", height=300)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="split-title"><h3>Top clientes por deuda</h3><span>Concentración de riesgo de cobranza</span></div>',
        unsafe_allow_html=True,
    )
    top = pd.read_sql_query(
        """
        SELECT cl.razon_social AS Cliente,
               COUNT(cu.id) AS Docs,
               SUM(cu.saldo) AS Saldo
        FROM cuentas cu
        JOIN clientes cl ON cl.id = cu.cliente_id
        WHERE cu.saldo > 0
        GROUP BY cl.id
        ORDER BY Saldo DESC
        LIMIT 8
        """,
        db,
    )
    if not top.empty:
        top["Saldo"] = top["Saldo"].map(clp)
        st.dataframe(top, use_container_width=True, hide_index=True)
    else:
        empty_state("No hay saldos abiertos en cartera.")

# ===========================================================================
# CLIENTES
# ===========================================================================
elif modulo == "Clientes":
    page_header("Clientes", "Maestro comercial con búsqueda rápida y vista 360 de deuda y cotizaciones.")
    tab_list, tab_new, tab_360 = st.tabs(["Listado", "Nuevo / editar", "Vista 360"])

    with tab_list:
        q = st.text_input("Buscar", placeholder="RUT, razón social, email…")
        sql = "SELECT id, rut AS RUT, razon_social AS Cliente, contacto AS Contacto, telefono AS Teléfono, email AS Email, comuna AS Comuna, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS Estado FROM clientes"
        params: list = []
        if q.strip():
            sql += " WHERE rut LIKE ? OR razon_social LIKE ? OR email LIKE ? OR contacto LIKE ?"
            like = f"%{q.strip()}%"
            params = [like, like, like, like]
        sql += " ORDER BY razon_social"
        df = pd.read_sql_query(sql, db, params=params)
        if df.empty:
            empty_state("No hay clientes para mostrar. Crea el primero en la pestaña Nuevo / editar.")
        else:
            st.dataframe(df.drop(columns=["id"], errors="ignore"), use_container_width=True, hide_index=True)

    with tab_new:
        clientes = db.execute("SELECT id, razon_social FROM clientes ORDER BY razon_social").fetchall()
        modo = st.radio("Acción", ["Crear", "Editar"], horizontal=True)
        row = None
        if modo == "Editar" and clientes:
            cid = st.selectbox("Cliente", options=[c["id"] for c in clientes], format_func=lambda i: next(c["razon_social"] for c in clientes if c["id"] == i))
            row = db.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone()
        with st.form("f_cli"):
            rut = st.text_input("RUT", value=row["rut"] if row else "")
            razon = st.text_input("Razón social", value=row["razon_social"] if row else "")
            contacto = st.text_input("Contacto", value=(row["contacto"] or "") if row else "")
            telefono = st.text_input("Teléfono", value=(row["telefono"] or "") if row else "")
            email = st.text_input("Email", value=(row["email"] or "") if row else "")
            direccion = st.text_input("Dirección", value=(row["direccion"] or "") if row else "")
            comuna = st.text_input("Comuna / Ciudad", value=(row["comuna"] or "") if row else "")
            activo = st.checkbox("Activo", value=bool(row["activo"]) if row else True)
            ok = st.form_submit_button("Guardar")
        if ok and razon.strip():
            try:
                if row:
                    db.execute(
                        """UPDATE clientes SET rut=?, razon_social=?, contacto=?, telefono=?, email=?, direccion=?, comuna=?, activo=? WHERE id=?""",
                        (rut.strip(), razon.strip(), contacto, telefono, email, direccion, comuna, int(activo), row["id"]),
                    )
                else:
                    db.execute(
                        """INSERT INTO clientes (rut, razon_social, contacto, telefono, email, direccion, comuna, activo, creado_en)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (rut.strip(), razon.strip(), contacto, telefono, email, direccion, comuna, int(activo), date.today().isoformat()),
                    )
                db.commit()
                st.success("Cliente guardado")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("RUT duplicado")

    with tab_360:
        clientes = db.execute("SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social").fetchall()
        if clientes:
            cid = st.selectbox("Cliente", options=[c["id"] for c in clientes], format_func=lambda i: next(c["razon_social"] for c in clientes if c["id"] == i), key="c360")
            deuda = db.execute("SELECT COALESCE(SUM(saldo),0) s FROM cuentas WHERE cliente_id=?", (cid,)).fetchone()["s"]
            ncot = db.execute("SELECT COUNT(*) n FROM cotizaciones WHERE cliente_id=?", (cid,)).fetchone()["n"]
            kpi_cards(
                [
                    ("Deuda abierta", clp(deuda), "danger" if float(deuda) > 0 else "ok"),
                    ("Cotizaciones", str(ncot), ""),
                    ("Estado", "Con saldo" if float(deuda) > 0 else "Al día", "warn" if float(deuda) > 0 else "ok"),
                ]
            )
            st.markdown(
                '<div class="split-title"><h3>Cotizaciones</h3><span>Historial comercial del cliente</span></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(
                pd.read_sql_query(
                    "SELECT folio, fecha, estado, total FROM cotizaciones WHERE cliente_id=? ORDER BY id DESC",
                    db,
                    params=(cid,),
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown(
                '<div class="split-title"><h3>Cuentas por cobrar</h3><span>Documentos y saldos</span></div>',
                unsafe_allow_html=True,
            )
            st.dataframe(
                pd.read_sql_query(
                    "SELECT documento, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado FROM cuentas WHERE cliente_id=? ORDER BY id DESC",
                    db,
                    params=(cid,),
                ),
                use_container_width=True,
                hide_index=True,
            )

# ===========================================================================
# PROVEEDORES
# ===========================================================================
elif modulo == "Proveedores":
    page_header("Proveedores", "Registro de proveedores para compras y control de contrapartes.")
    df_prov = pd.read_sql_query(
        "SELECT rut AS RUT, razon_social AS Proveedor, contacto, telefono, email, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS estado FROM proveedores ORDER BY razon_social",
        db,
    )
    if df_prov.empty:
        empty_state("Aún no hay proveedores. Crea el primero con el formulario de abajo.")
    else:
        st.dataframe(df_prov, use_container_width=True, hide_index=True)
    with st.form("f_prov"):
        st.markdown("**Nuevo proveedor**")
        rut = st.text_input("RUT")
        razon_p = st.text_input("Razón social")
        contacto = st.text_input("Contacto")
        telefono = st.text_input("Teléfono")
        email = st.text_input("Email")
        if st.form_submit_button("Crear", type="primary") and razon_p.strip():
            try:
                db.execute(
                    "INSERT INTO proveedores (rut, razon_social, contacto, telefono, email) VALUES (?,?,?,?,?)",
                    (rut.strip(), razon_p.strip(), contacto, telefono, email),
                )
                db.commit()
                st.success("Proveedor creado")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("RUT duplicado")

# ===========================================================================
# PRODUCTOS
# ===========================================================================
elif modulo == "Productos":
    page_header("Productos / partidas", "Catálogo reutilizable al armar cotizaciones, con precio y unidad.")
    df_prod = pd.read_sql_query(
        "SELECT codigo AS Código, nombre AS Nombre, unidad AS Un, precio AS Precio, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS Estado FROM productos ORDER BY nombre",
        db,
    )
    if df_prod.empty:
        empty_state("Sin productos. Agrega partidas para cotizar más rápido.")
    else:
        show_prod = df_prod.copy()
        show_prod["Precio"] = show_prod["Precio"].map(clp)
        st.dataframe(show_prod, use_container_width=True, hide_index=True)
    with st.form("f_prod"):
        st.markdown("**Nuevo producto**")
        codigo = st.text_input("Código", placeholder="RAD-M2")
        nombre = st.text_input("Nombre")
        unidad = st.text_input("Unidad", "m2")
        precio = st.number_input("Precio venta", min_value=0.0, step=100.0)
        if st.form_submit_button("Crear", type="primary") and nombre.strip():
            try:
                db.execute(
                    "INSERT INTO productos (codigo, nombre, unidad, precio) VALUES (?,?,?,?)",
                    (codigo.strip().upper() or None, nombre.strip(), unidad.strip() or "un", float(precio)),
                )
                db.commit()
                st.success("Producto creado")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Código duplicado")

# ===========================================================================
# COTIZACIONES
# ===========================================================================
elif modulo == "Cotizaciones":
    page_header("Cotizaciones", "Flujo completo: crear, enviar, aprobar y generar cuenta por cobrar.")
    tab_list, tab_new, tab_gestion = st.tabs(["Listado", "Nueva", "Gestión / estados"])

    with tab_list:
        f_estado = st.multiselect("Filtrar estado", ["borrador", "enviada", "aprobada", "rechazada"], default=[])
        sql = """
            SELECT c.id, c.folio AS Folio, c.fecha AS Fecha, cl.razon_social AS Cliente,
                   c.asunto AS Asunto, c.proyecto AS Proyecto, c.estado AS Estado, c.total AS Total
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id
        """
        if f_estado:
            sql += " WHERE c.estado IN (" + ",".join("?" * len(f_estado)) + ")"
            df = pd.read_sql_query(sql + " ORDER BY c.id DESC", db, params=f_estado)
        else:
            df = pd.read_sql_query(sql + " ORDER BY c.id DESC", db)
        if not df.empty:
            show = df.drop(columns=["id"])
            show["Total"] = show["Total"].map(clp)
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            empty_state("Sin cotizaciones todavía. Crea la primera en la pestaña Nueva.")

    with tab_new:
        clientes = db.execute("SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social").fetchall()
        productos = db.execute("SELECT id, codigo, nombre, unidad, precio FROM productos WHERE activo=1 ORDER BY nombre").fetchall()
        iva_pct = param(db, "iva", 19) / 100
        validez_def = int(param(db, "validez_cotizacion", 30))
        if not clientes:
            empty_state("Crea clientes primero para poder emitir cotizaciones.")
        else:
            with st.form("f_cot"):
                cliente_id = st.selectbox(
                    "Cliente",
                    options=[c["id"] for c in clientes],
                    format_func=lambda i: next(x["razon_social"] for x in clientes if x["id"] == i),
                )
                asunto = st.text_input("Asunto / nombre interno")
                proyecto = st.text_input("Proyecto / obra", "Condominio Río Maipo")
                validez = st.number_input("Validez (días)", min_value=1, value=validez_def)
                estado = st.selectbox("Estado inicial", ["borrador", "enviada"])
                st.markdown("**Ítems** (elige producto o escribe descripción)")
                items = []
                for i in range(4):
                    cols = st.columns([2.2, 2.2, 0.7, 0.8, 1])
                    with cols[0]:
                        prod_opt = st.selectbox(
                            f"Producto {i+1}",
                            options=[0] + [p["id"] for p in productos],
                            format_func=lambda x: "— manual —" if x == 0 else next(f"{p['codigo']} · {p['nombre']}" for p in productos if p["id"] == x),
                            key=f"prod_{i}",
                        )
                    with cols[1]:
                        desc = st.text_input("Descripción", key=f"desc_{i}", value="")
                    with cols[2]:
                        un = st.text_input("Un", value="m2", key=f"un_{i}")
                    with cols[3]:
                        cant = st.number_input("Cant", min_value=0.0, value=0.0, key=f"cant_{i}")
                    with cols[4]:
                        pu = st.number_input("P.Unit", min_value=0.0, value=0.0, key=f"pu_{i}")
                    items.append((prod_opt, desc, un, cant, pu))
                notas = st.text_area("Notas")
                guardar = st.form_submit_button("Guardar cotización", type="primary")

            if guardar:
                lineas = []
                for prod_opt, desc, un, cant, pu in items:
                    if cant <= 0:
                        continue
                    pid = prod_opt if prod_opt else None
                    if pid:
                        p = next(x for x in productos if x["id"] == pid)
                        descripcion = desc.strip() or p["nombre"]
                        unidad = un.strip() or p["unidad"]
                        precio = float(pu) if pu > 0 else float(p["precio"])
                    else:
                        if not desc.strip():
                            continue
                        descripcion = desc.strip()
                        unidad = un.strip() or "un"
                        precio = float(pu)
                    total = float(cant) * precio
                    lineas.append((pid, descripcion, unidad, float(cant), precio, total))
                if not lineas:
                    st.error("Agrega al menos un ítem con cantidad > 0")
                else:
                    subtotal = sum(x[5] for x in lineas)
                    iva = round(subtotal * iva_pct)
                    total = subtotal + iva
                    folio = next_code(db, "cotizaciones", "folio", "COT")
                    cur = db.cursor()
                    cur.execute(
                        """
                        INSERT INTO cotizaciones (folio, cliente_id, asunto, proyecto, estado, fecha, validez_dias, subtotal, iva, total, notas)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            folio,
                            cliente_id,
                            asunto.strip() or None,
                            proyecto.strip() or None,
                            estado,
                            date.today().isoformat(),
                            int(validez),
                            subtotal,
                            iva,
                            total,
                            notas.strip() or None,
                        ),
                    )
                    cot_id = cur.lastrowid
                    cur.executemany(
                        """
                        INSERT INTO cotizacion_items (cotizacion_id, producto_id, descripcion, unidad, cantidad, precio_unitario, total)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                        [(cot_id, *ln) for ln in lineas],
                    )
                    db.commit()
                    st.success(f"{folio} creada · total {clp(total)} (IVA {iva_pct*100:.0f}%)")
                    st.rerun()

    with tab_gestion:
        rows = db.execute(
            """
            SELECT c.*, cl.razon_social
            FROM cotizaciones c LEFT JOIN clientes cl ON cl.id=c.cliente_id
            ORDER BY c.id DESC
            """
        ).fetchall()
        if not rows:
            empty_state("Sin cotizaciones para gestionar.")
        else:
            sel = st.selectbox(
                "Cotización",
                options=[r["id"] for r in rows],
                format_func=lambda i: next(f"{r['folio']} · {r['razon_social'] or '—'} · {r['estado']} · {clp(r['total'])}" for r in rows if r["id"] == i),
            )
            cot = next(r for r in rows if r["id"] == sel)
            st.markdown(
                f"""
                <div class="panel">
                  <div class="split-title" style="margin:0;">
                    <h3>{cot['folio']}</h3>
                    <span class="badge {'ok' if cot['estado']=='aprobada' else 'warn' if cot['estado']=='enviada' else 'muted'}">{cot['estado']}</span>
                  </div>
                  <p style="margin:.45rem 0 0;color:var(--muted);">{cot['proyecto'] or '—'} · {cot['asunto'] or 'Sin asunto'} · Total {clp(cot['total'])}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.dataframe(
                pd.read_sql_query(
                    "SELECT descripcion, unidad, cantidad, precio_unitario, total FROM cotizacion_items WHERE cotizacion_id=?",
                    db,
                    params=(sel,),
                ),
                use_container_width=True,
                hide_index=True,
            )
            nuevo_estado = st.selectbox(
                "Cambiar estado",
                ["borrador", "enviada", "aprobada", "rechazada"],
                index=["borrador", "enviada", "aprobada", "rechazada"].index(cot["estado"]) if cot["estado"] in ["borrador", "enviada", "aprobada", "rechazada"] else 0,
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Actualizar estado"):
                    db.execute("UPDATE cotizaciones SET estado=? WHERE id=?", (nuevo_estado, sel))
                    db.commit()
                    st.success("Estado actualizado")
                    st.rerun()
            with col2:
                if cot["estado"] == "aprobada" and not cot["cxc_id"]:
                    if st.button("Generar cuenta por cobrar", type="primary"):
                        dias = int(param(db, "dias_credito", 30))
                        doc = next_code(db, "cuentas", "documento", "EP")
                        cur = db.cursor()
                        cur.execute(
                            """
                            INSERT INTO cuentas (documento, cliente_id, cotizacion_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
                            VALUES (?,?,?,?,?,?,?,?,0,?, 'pendiente')
                            """,
                            (
                                doc,
                                cot["cliente_id"],
                                sel,
                                "EP",
                                f"Desde cotización {cot['folio']}",
                                date.today().isoformat(),
                                (date.today() + timedelta(days=dias)).isoformat(),
                                float(cot["total"]),
                                float(cot["total"]),
                            ),
                        )
                        cxc_id = cur.lastrowid
                        cur.execute("UPDATE cotizaciones SET cxc_id=? WHERE id=?", (cxc_id, sel))
                        db.commit()
                        st.success(f"CxC {doc} creada por {clp(cot['total'])}")
                        st.rerun()
                elif cot["cxc_id"]:
                    alert_line("ok", f"Ya tiene CxC vinculada (id {cot['cxc_id']}).")
                else:
                    st.caption("Aprueba la cotización para poder generar la CxC.")

# ===========================================================================
# CUENTAS POR COBRAR
# ===========================================================================
elif modulo == "Cuentas por cobrar":
    page_header("Cuentas por cobrar", "Cartera con mora, aging y registro de abonos en un solo flujo.")
    tab_list, tab_new, tab_abono = st.tabs(["Cartera", "Nuevo documento", "Registrar abono"])

    hoy = date.today()
    with tab_list:
        filtro = st.selectbox("Vista", ["Todas", "Con saldo", "Vencidas", "Al día"])
        df = pd.read_sql_query(
            """
            SELECT cu.id, cu.documento AS Documento, cl.razon_social AS Cliente, cu.tipo_doc AS Tipo,
                   cu.fecha_emision AS Emisión, cu.fecha_vencimiento AS Vence,
                   cu.monto AS Total, cu.abonado AS Abonos, cu.saldo AS Saldo, cu.estado AS Estado
            FROM cuentas cu
            LEFT JOIN clientes cl ON cl.id = cu.cliente_id
            ORDER BY cu.id DESC
            """,
            db,
        )
        if not df.empty:
            moras = []
            aging = []
            for _, r in df.iterrows():
                ve = dparse(r["Vence"])
                saldo = float(r["Saldo"] or 0)
                if saldo <= 0 or not ve:
                    moras.append(0)
                    aging.append("pagado" if saldo <= 0 else "sin fecha")
                else:
                    moras.append(max(0, (hoy - ve).days))
                    aging.append(aging_bucket(ve, hoy))
            df["Días mora"] = moras
            df["Aging"] = aging
            view = df.copy()
            if filtro == "Con saldo":
                view = view[view["Saldo"] > 0]
            elif filtro == "Vencidas":
                view = view[view["Días mora"] > 0]
            elif filtro == "Al día":
                view = view[(view["Saldo"] > 0) & (view["Días mora"] == 0)]
            show = view.drop(columns=["id"])
            for col in ["Total", "Abonos", "Saldo"]:
                show[col] = show[col].map(clp)
            st.dataframe(show, use_container_width=True, hide_index=True)
            kpi_cards([("Saldo filtrado", clp(float(view["Saldo"].sum())), "warn" if float(view["Saldo"].sum()) > 0 else "ok")])
        else:
            empty_state("Sin documentos en cartera.")

    with tab_new:
        clientes = db.execute("SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social").fetchall()
        dias = int(param(db, "dias_credito", 30))
        with st.form("f_cxc"):
            cliente_id = st.selectbox(
                "Cliente",
                options=[c["id"] for c in clientes] if clientes else [],
                format_func=lambda i: next(c["razon_social"] for c in clientes if c["id"] == i),
            )
            tipo = st.selectbox("Tipo documento", ["EP", "FAC", "ND"])
            concepto = st.text_input("Concepto", "Estado de pago")
            monto = st.number_input("Monto", min_value=1.0, value=1000000.0, step=1000.0)
            venc = st.date_input("Vencimiento", value=date.today() + timedelta(days=dias))
            if st.form_submit_button("Guardar", type="primary") and clientes:
                doc = next_code(db, "cuentas", "documento", "EP")
                db.execute(
                    """
                    INSERT INTO cuentas (documento, cliente_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
                    VALUES (?,?,?,?,?,?,?,0,?, 'pendiente')
                    """,
                    (
                        doc,
                        cliente_id,
                        tipo,
                        concepto,
                        date.today().isoformat(),
                        venc.isoformat(),
                        float(monto),
                        float(monto),
                    ),
                )
                db.commit()
                st.success(f"Documento {doc} creado")
                st.rerun()

    with tab_abono:
        abiertas = db.execute(
            """
            SELECT cu.id, cu.documento, cu.saldo, cl.razon_social
            FROM cuentas cu LEFT JOIN clientes cl ON cl.id=cu.cliente_id
            WHERE cu.saldo > 0 ORDER BY cu.id DESC
            """
        ).fetchall()
        if not abiertas:
            alert_line("ok", "<strong>No hay saldos pendientes.</strong> Toda la cartera está cobrada.")
        else:
            with st.form("f_abono"):
                cuenta_id = st.selectbox(
                    "Documento",
                    options=[a["id"] for a in abiertas],
                    format_func=lambda i: next(f"{a['documento']} · {a['razon_social']} · saldo {clp(a['saldo'])}" for a in abiertas if a["id"] == i),
                )
                monto = st.number_input("Monto abono", min_value=1.0, step=1000.0)
                medio = st.selectbox("Medio", ["transferencia", "cheque", "efectivo", "tarjeta", "otro"])
                nota = st.text_input("Nota")
                if st.form_submit_button("Registrar abono", type="primary"):
                    db.execute(
                        "INSERT INTO abonos (cuenta_id, fecha, monto, medio, nota) VALUES (?,?,?,?,?)",
                        (cuenta_id, date.today().isoformat(), float(monto), medio, nota),
                    )
                    recalc_cuenta(db, cuenta_id)
                    db.commit()
                    st.success("Abono registrado")
                    st.rerun()

# ===========================================================================
# ADMINISTRACIÓN
# ===========================================================================
else:
    page_header("Administración", "Datos de la empresa y parámetros operativos del ERP.")
    tab_emp, tab_par = st.tabs(["Mi empresa", "Parámetros"])

    with tab_emp:
        e = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()
        with st.form("f_emp"):
            rut = st.text_input("RUT", e["rut"] or "")
            razon_f = st.text_input("Razón social", e["razon_social"] or "")
            telefono = st.text_input("Teléfono", e["telefono"] or "")
            email = st.text_input("Email", e["email"] or "")
            direccion = st.text_input("Dirección", e["direccion"] or "")
            region = st.text_input("Región", e["region"] or "")
            pais = st.text_input("País", e["pais"] or "Chile")
            if st.form_submit_button("Guardar empresa", type="primary"):
                db.execute(
                    """UPDATE empresa SET rut=?, razon_social=?, telefono=?, email=?, direccion=?, region=?, pais=? WHERE id=1""",
                    (rut, razon_f, telefono, email, direccion, region, pais),
                )
                db.commit()
                st.success("Empresa actualizada")
                st.rerun()

    with tab_par:
        params = pd.read_sql_query("SELECT clave, nombre, valor, unidad FROM parametros ORDER BY nombre", db)
        st.dataframe(params, use_container_width=True, hide_index=True)
        with st.form("f_par"):
            clave = st.selectbox("Parámetro", options=params["clave"].tolist())
            valor = st.text_input("Nuevo valor", value=str(params.loc[params.clave == clave, "valor"].values[0]))
            if st.form_submit_button("Actualizar", type="primary"):
                db.execute("UPDATE parametros SET valor=? WHERE clave=?", (valor.strip(), clave))
                db.commit()
                st.success("Parámetro actualizado")
                st.rerun()

render_footer()
db.close()
