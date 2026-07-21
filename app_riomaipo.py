"""
ERP Master — Río Maipo
Inspirado en SOLUERP, con gestión mejorada:
- Flujo cotización → aprobación → cuenta por cobrar
- Aging de cobranza y alertas de mora/vencimiento
- Catálogo de productos, proveedores y vista 360 del cliente
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "riomaipo_erp.db"
LOGO_PATH = BASE_DIR / "static" / "logo_erpmaster.png"
LOGO_RIOMAIPO_PATH = BASE_DIR / "static" / "logo_riomaipo.png"
BG_LOGIN_PATH = BASE_DIR / "static" / "bg_login_plano.png"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "static").mkdir(parents=True, exist_ok=True)
COT_ITEM_SLOTS = 12
COT_PDF_ROWS = 24

st.set_page_config(
    page_title="ERP Master · Río Maipo",
    page_icon="◆",
    layout="wide",
    # auto: oculto en móvil/iPhone, visible en escritorio
    initial_sidebar_state="auto",
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

  .cot-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: .65rem;
    margin: 0 0 1rem;
  }
  @media (max-width: 1100px) {
    .cot-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 640px) {
    .cot-kpi-grid { grid-template-columns: 1fr; }
  }
  .cot-kpi {
    border-radius: 12px;
    padding: .85rem .95rem;
    color: #fff;
    box-shadow: 0 8px 22px rgba(22,58,95,.12);
    min-height: 92px;
  }
  .cot-kpi .label { font-size: .78rem; font-weight: 700; opacity: .95; }
  .cot-kpi .value { font-size: 1.15rem; font-weight: 800; margin-top: .35rem; line-height: 1.2; }
  .cot-kpi .hint { font-size: .78rem; margin-top: .25rem; opacity: .9; }
  .cot-kpi.ing { background: linear-gradient(135deg, #1f4b99, #2f6fed); }
  .cot-kpi.apr { background: linear-gradient(135deg, #0f8fa8, #22b8cf); }
  .cot-kpi.rec { background: linear-gradient(135deg, #c23a6b, #e85d8a); }
  .cot-kpi.an { background: linear-gradient(135deg, #1f8a65, #2fbf71); }
  .cot-kpi.mes { background: linear-gradient(135deg, #c46a12, #f0a202); }

  .cot-filters {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: .85rem .9rem .55rem;
    margin-bottom: .85rem;
    box-shadow: var(--shadow);
  }
  .cot-table {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 12px;
    box-shadow: var(--shadow);
    overflow: hidden;
    margin-bottom: 1rem;
  }
  .cot-table-head, .cot-table-row {
    display: grid;
    grid-template-columns: 40px 1fr .9fr 2fr 1fr .9fr 170px;
    gap: .4rem;
    align-items: center;
    padding: .55rem .75rem;
  }
  .cot-table-head {
    background: #f3f6fb;
    border-bottom: 1px solid var(--line);
    font-size: .7rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .04em;
    color: var(--muted);
  }
  .cot-table-row {
    border-bottom: 1px solid #e8eef5;
    font-size: .86rem;
  }
  .cot-table-row:nth-child(even) { background: #fafcff; }
  .cot-table-row:last-child { border-bottom: 0; }
  .cot-num { color: #2f6fed; font-weight: 800; }
  .cot-cli strong { display:block; color: var(--text); }
  .cot-cli span { display:block; color: var(--muted); font-size: .78rem; margin-top: .1rem; }
  .cot-estado {
    display:inline-flex; align-items:center; gap:.35rem;
    font-weight: 700; font-size: .8rem; text-transform: capitalize;
  }
  .cot-estado.aprobada { color: #1f8a65; }
  .cot-estado.rechazada { color: #b42318; }
  .cot-estado.enviada, .cot-estado.borrador { color: #1a2b3c; }
  .cot-dot {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; background: #2b2f36;
  }
  .cot-dot.ok { background: #1f8a65; }
  .cot-dot.warn { background: #d59a1b; }
  .cot-dot.muted { background: #2b2f36; }
  .cot-dot.danger { background: #b42318; }

  .cxc-estado { font-weight: 800; font-size: .82rem; text-transform: capitalize; }
  .cxc-estado.pendiente { color: #b42318; }
  .cxc-estado.abonado, .cxc-estado.parcial { color: #0b6e99; }
  .cxc-estado.pagado { color: #1f8a65; }
  .cxc-total-row {
    background: #eef3f9;
    border-top: 1px solid var(--line);
    padding: .65rem .2rem;
    font-weight: 800;
    color: var(--brand);
    margin-top: .35rem;
  }

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
    # Desktop: reopen if collapsed. Mobile/iPhone: keep/force sidebar hidden.
    components.html(
        """
<script>
(() => {
  const doc = window.parent.document;
  const win = window.parent;
  const isMobile = () => {
    const ua = (win.navigator.userAgent || "").toLowerCase();
    const phone = /iphone|ipod|android.+mobile|windows phone|mobile/.test(ua);
    const narrow = win.matchMedia && win.matchMedia("(max-width: 768px)").matches;
    return phone || narrow;
  };
  const clickExpand = () => {
    const btn =
      doc.querySelector('[data-testid="stExpandSidebarButton"]') ||
      doc.querySelector('[data-testid="collapsedControl"]') ||
      doc.querySelector('[data-testid="stSidebarCollapsedControl"]');
    if (btn) btn.click();
  };
  const clickCollapse = () => {
    const btn =
      doc.querySelector('[data-testid="stSidebarCollapseButton"]') ||
      doc.querySelector('[data-testid="stSidebarCollapse"] button') ||
      doc.querySelector('section[data-testid="stSidebar"] button[kind="header"]');
    if (btn) btn.click();
  };
  const syncSidebar = () => {
    if (isMobile()) clickCollapse();
    else clickExpand();
  };
  syncSidebar();
  setTimeout(syncSidebar, 300);
  setTimeout(syncSidebar, 900);
})();
</script>
        """,
        height=0,
        width=0,
    )


@lru_cache(maxsize=2)
def file_data_uri(path_str: str, mime: str) -> str:
    path = Path(path_str)
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def logo_data_uri() -> str:
    return file_data_uri(str(LOGO_PATH), "image/png")


def login_bg_data_uri() -> str:
    return file_data_uri(str(BG_LOGIN_PATH), "image/png")


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


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, digest: str) -> bool:
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()
    return hmac.compare_digest(check, digest)


DEFAULT_ACCESO = "osvaldolira@constructorariomaipo.cl"
DEFAULT_CLAVE = "9083"
TIPOS_USUARIO = ["Administrador", "Operador", "Consulta"]


def migrate_usuarios_schema(c: sqlite3.Connection) -> None:
    cols = {r["name"] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()}
    if "tipo" not in cols:
        c.execute(
            "ALTER TABLE usuarios ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Administrador'"
        )
    c.execute(
        """
        UPDATE usuarios
        SET tipo='Administrador'
        WHERE tipo IS NULL OR TRIM(tipo)=''
        """
    )


def _ensure_columns(c: sqlite3.Connection, table: str, columns: list[tuple[str, str]]) -> None:
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in columns:
        if name not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def migrate_cotizaciones_schema(c: sqlite3.Connection) -> None:
    _ensure_columns(
        c,
        "cotizaciones",
        [
            ("version", "TEXT DEFAULT '1'"),
            ("titulo", "TEXT"),
            ("gg_pct", "REAL DEFAULT 5"),
            ("utilidad_pct", "REAL DEFAULT 15"),
            ("gg_monto", "REAL DEFAULT 0"),
            ("utilidad_monto", "REAL DEFAULT 0"),
            ("valor_neto", "REAL DEFAULT 0"),
        ],
    )
    _ensure_columns(
        c,
        "cotizacion_items",
        [
            ("obs", "TEXT"),
            ("orden", "INTEGER DEFAULT 0"),
        ],
    )
    for clave, nombre, valor, unidad in [
        ("gg_pct", "Gastos generales", "5", "%"),
        ("utilidad_pct", "Utilidad", "15", "%"),
    ]:
        c.execute(
            """
            INSERT INTO parametros (clave, nombre, valor, unidad)
            VALUES (?,?,?,?)
            ON CONFLICT(clave) DO NOTHING
            """,
            (clave, nombre, valor, unidad),
        )


def ensure_default_user(c: sqlite3.Connection) -> None:
    """Asegura el usuario principal y aplica la clave inicial una sola vez."""
    migrate_usuarios_schema(c)
    salt, digest = hash_password(DEFAULT_CLAVE)
    row = c.execute(
        "SELECT id FROM usuarios WHERE lower(usuario)=lower(?)",
        (DEFAULT_ACCESO,),
    ).fetchone()
    if row:
        flag = c.execute(
            "SELECT valor FROM parametros WHERE clave='auth_seed'"
        ).fetchone()
        if not flag or flag["valor"] != "osvaldo_9083":
            c.execute(
                """
                UPDATE usuarios
                SET salt=?, clave_hash=?, nombre=?, tipo=?, activo=1
                WHERE id=?
                """,
                (salt, digest, "Osvaldo Lira", "Administrador", row["id"]),
            )
            c.execute(
                """
                INSERT INTO parametros (clave, nombre, valor, unidad)
                VALUES ('auth_seed', 'Semilla acceso', 'osvaldo_9083', '')
                ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
                """
            )
    else:
        c.execute(
            """
            INSERT INTO usuarios (usuario, salt, clave_hash, nombre, tipo, activo)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (DEFAULT_ACCESO, salt, digest, "Osvaldo Lira", "Administrador"),
        )
        c.execute(
            """
            INSERT INTO parametros (clave, nombre, valor, unidad)
            VALUES ('auth_seed', 'Semilla acceso', 'osvaldo_9083', '')
            ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor
            """
        )


def list_accesos() -> list[str]:
    c = conn()
    rows = c.execute(
        """
        SELECT usuario FROM usuarios
        WHERE activo=1
        ORDER BY CASE WHEN lower(usuario)=lower(?) THEN 0 ELSE 1 END, usuario
        """,
        (DEFAULT_ACCESO,),
    ).fetchall()
    c.close()
    users = [r["usuario"] for r in rows]
    if DEFAULT_ACCESO not in users:
        users.insert(0, DEFAULT_ACCESO)
    return users


def check_login(usuario: str, clave: str) -> bool:
    return get_user_if_valid(usuario, clave) is not None


def get_user_if_valid(usuario: str, clave: str) -> sqlite3.Row | None:
    c = conn()
    row = c.execute(
        """
        SELECT id, usuario, salt, clave_hash, nombre, tipo, activo
        FROM usuarios WHERE lower(usuario)=lower(?)
        """,
        (usuario.strip(),),
    ).fetchone()
    c.close()
    if not row or int(row["activo"] or 0) != 1:
        return None
    if not verify_password(clave, row["salt"], row["clave_hash"]):
        return None
    return row


def current_user_tipo() -> str:
    return st.session_state.get("auth_tipo") or "Consulta"


def is_admin_user() -> bool:
    return current_user_tipo() == "Administrador"


def inject_login_styles() -> None:
    bg = login_bg_data_uri()
    bg_css = f"url('{bg}') center center / cover no-repeat fixed" if bg else "#0f3a66"
    st.html(
        f"""
<style>
  [data-testid="stSidebar"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="stExpandSidebarButton"],
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  #MainMenu, footer {{
    display: none !important;
    visibility: hidden !important;
  }}
  html, body, [data-testid="stAppViewContainer"], .stApp {{
    background:
      linear-gradient(165deg, rgba(8,36,72,.28), rgba(12,52,98,.30) 50%, rgba(18,70,120,.26)),
      {bg_css} !important;
    min-height: 100vh;
  }}
  [data-testid="stHeader"] {{
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    pointer-events: none !important;
  }}
  [data-testid="stHeader"] * {{
    pointer-events: none !important;
  }}
  .block-container {{
    max-width: 100% !important;
    padding-top: 1.1rem !important;
    padding-left: 1.1rem !important;
    padding-right: 1.1rem !important;
    padding-bottom: 1rem !important;
  }}
  /* Asegura el botón Acceso por encima del plano */
  div[data-testid="stPopover"] {{
    position: relative;
    z-index: 20;
  }}
  .login-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .35rem;
  }}
  .login-brand {{
    display: flex;
    align-items: center;
    gap: .7rem;
    opacity: .92;
  }}
  .login-brand img {{
    width: 148px;
    height: auto;
    filter: drop-shadow(0 6px 16px rgba(0,0,0,.25));
  }}
  .login-brand .txt {{
    color: #ffffff;
    font-family: Manrope, Segoe UI, sans-serif;
  }}
  .login-brand .txt strong {{
    display: block;
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: .02em;
  }}
  .login-brand .txt span {{
    display: block;
    font-size: .78rem;
    opacity: .9;
  }}
  /* Botón Acceso (popover) arriba derecha */
  div[data-testid="stPopover"] > button {{
    background: rgba(255,255,255,.94) !important;
    color: #163a5f !important;
    border: 1px solid rgba(255,255,255,.7) !important;
    border-radius: 12px !important;
    font-weight: 800 !important;
    box-shadow: 0 10px 28px rgba(8,30,60,.22) !important;
    min-height: 2.6rem !important;
  }}
  div[data-testid="stPopover"] > button:hover {{
    background: #ffffff !important;
    border-color: #2f6fed !important;
    color: #2f6fed !important;
  }}
  [data-testid="stPopoverBody"],
  [data-testid="stExpanderDetails"] {{
    background: rgba(255,255,255,.97) !important;
  }}
  [data-testid="stForm"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: .15rem 0 0 !important;
  }}
  .stTextInput input,
  .stSelectbox div[data-baseweb="select"] > div {{
    background: #fff !important;
    border: 1px solid #c3cfdb !important;
    border-radius: 10px !important;
    color: #1a2b3c !important;
  }}
  .stButton > button[kind="primary"],
  .stButton > button[data-testid="baseButton-primary"] {{
    background: #2f6fed !important;
    color: #fff !important;
    border: 1px solid #255ed4 !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    width: 100%;
  }}
  label, [data-testid="stWidgetLabel"] p {{
    color: #1a2b3c !important;
    font-weight: 700 !important;
  }}
  div[data-testid="stCheckbox"] label p {{
    font-weight: 600 !important;
    color: #31485c !important;
  }}
</style>
        """
    )


def _restore_remembered_acceso() -> None:
    """Si hay acceso guardado en localStorage, lo refleja en la URL una vez."""
    components.html(
        """
<script>
(() => {
  const win = window.parent;
  const params = new URLSearchParams(win.location.search);
  if (params.get("rm_sync") === "1") return;
  const remember = win.localStorage.getItem("rm_remember") === "1";
  const acceso = win.localStorage.getItem("rm_acceso") || "";
  if (!remember || !acceso) return;
  if (params.get("acceso") === acceso && params.get("remember") === "1") return;
  params.set("acceso", acceso);
  params.set("remember", "1");
  params.set("rm_sync", "1");
  win.location.search = params.toString();
})();
</script>
        """,
        height=0,
        width=0,
    )


def _persist_remember(acceso: str, recordar: bool) -> None:
    # Solo recuerda el usuario (nunca la clave).
    if recordar:
        components.html(
            f"""
<script>
(() => {{
  const win = window.parent;
  win.localStorage.setItem("rm_remember", "1");
  win.localStorage.setItem("rm_acceso", {json.dumps(acceso)});
  win.localStorage.removeItem("rm_clave");
}})();
</script>
            """,
            height=0,
            width=0,
        )
        st.query_params["acceso"] = acceso
        st.query_params["remember"] = "1"
    else:
        components.html(
            """
<script>
(() => {
  const win = window.parent;
  win.localStorage.removeItem("rm_remember");
  win.localStorage.removeItem("rm_acceso");
  win.localStorage.removeItem("rm_clave");
})();
</script>
            """,
            height=0,
            width=0,
        )
        for key in ("acceso", "remember", "rm_sync"):
            if key in st.query_params:
                del st.query_params[key]


def render_login() -> None:
    inject_login_styles()
    _restore_remembered_acceso()

    accesos = list_accesos()
    qp_acceso = st.query_params.get("acceso", DEFAULT_ACCESO)
    if qp_acceso not in accesos:
        qp_acceso = DEFAULT_ACCESO if DEFAULT_ACCESO in accesos else accesos[0]
    remember_default = st.query_params.get("remember", "") == "1"

    logo = logo_data_uri()
    logo_img = f'<img src="{logo}" alt="ERP Master" />' if logo else ""

    top_left, top_right = st.columns([3.4, 1.1], vertical_alignment="center")
    with top_left:
        st.html(
            f"""
            <div class="login-brand">
              {logo_img}
              <div class="txt">
                <strong>Río Maipo</strong>
                <span>ERP Master · plano de obra</span>
              </div>
            </div>
            """
        )
    with top_right:
        with st.popover("Acceso", use_container_width=True):
            with st.form("login_form", clear_on_submit=False):
                usuario = st.selectbox(
                    "Usuario",
                    options=accesos,
                    index=accesos.index(qp_acceso),
                )
                clave = st.text_input("Clave", type="password", placeholder="••••")
                recordar = st.checkbox("Recordar usuario", value=remember_default)
                ingresar = st.form_submit_button(
                    "Ingresar", type="primary", use_container_width=True
                )
            if ingresar:
                user_row = get_user_if_valid(usuario, clave)
                if user_row:
                    _persist_remember(usuario, bool(recordar))
                    st.session_state.auth_ok = True
                    st.session_state.auth_user = user_row["usuario"]
                    st.session_state.auth_tipo = user_row["tipo"] or "Consulta"
                    st.session_state.auth_nombre = user_row["nombre"] or user_row["usuario"]
                    st.rerun()
                else:
                    st.error("Usuario o clave incorrectos")


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


def estado_dot_class(estado: str) -> str:
    if estado == "aprobada":
        return "ok"
    if estado == "enviada":
        return "warn"
    if estado == "rechazada":
        return "danger"
    return "muted"


def estado_label_soluerp(estado: str) -> str:
    mapping = {
        "borrador": "Ingresada",
        "enviada": "Ingresada",
        "aprobada": "Aprobada",
        "rechazada": "Rechazada",
    }
    return mapping.get(estado or "", estado or "—")


def fetch_cotizacion(db: sqlite3.Connection, cot_id: int):
    return db.execute(
        """
        SELECT c.*, cl.razon_social, cl.rut AS cliente_rut,
               cl.email AS cliente_email, cl.telefono AS cliente_telefono
        FROM cotizaciones c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.id=?
        """,
        (cot_id,),
    ).fetchone()


def fetch_cotizacion_items(db: sqlite3.Connection, cot_id: int):
    return db.execute(
        """
        SELECT id, producto_id, descripcion, COALESCE(obs,'') AS obs,
               unidad, cantidad, precio_unitario, total, COALESCE(orden,0) AS orden
        FROM cotizacion_items
        WHERE cotizacion_id=?
        ORDER BY COALESCE(orden,0), id
        """,
        (cot_id,),
    ).fetchall()


def delete_cotizacion(db: sqlite3.Connection, cot_id: int) -> str | None:
    row = fetch_cotizacion(db, cot_id)
    if not row:
        return "Cotización no encontrada"
    if row["cxc_id"]:
        return "No se puede eliminar: tiene una cuenta por cobrar vinculada"
    db.execute("DELETE FROM cotizacion_items WHERE cotizacion_id=?", (cot_id,))
    db.execute("DELETE FROM cotizaciones WHERE id=?", (cot_id,))
    db.commit()
    return None


def _pdf_txt(value) -> str:
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def fmt_clp_plain(v) -> str:
    try:
        return f"{int(round(float(v or 0))):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def fmt_cant_pdf(v) -> str:
    try:
        return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0,00"


def calc_cotizacion_totales(subtotal: float, gg_pct: float, utilidad_pct: float, iva_pct: float) -> dict:
    """Totales estilo planilla Río Maipo: GG/Utilidad sobre subtotal, IVA sobre valor neto."""
    sub = float(subtotal or 0)
    gg = int(round(sub * float(gg_pct or 0) / 100.0))
    util = int(round(sub * float(utilidad_pct or 0) / 100.0))
    neto = int(round(sub + gg + util))
    iva = int(round(neto * float(iva_pct or 0)))
    return {
        "subtotal": sub,
        "gg_monto": gg,
        "utilidad_monto": util,
        "valor_neto": neto,
        "iva": iva,
        "total": neto + iva,
    }


def cotizacion_titulo_pdf(cot) -> str:
    version = str(cot["version"] if "version" in cot.keys() else "1") or "1"
    version = version.lstrip("Vv")
    titulo = ""
    if "titulo" in cot.keys() and cot["titulo"]:
        titulo = str(cot["titulo"]).strip()
    if not titulo:
        parts = [cot["proyecto"] or "", cot["asunto"] or "", cot["razon_social"] or ""]
        titulo = " ".join(p for p in parts if p).strip() or "COTIZACION"
    return f"V{version} COTIZACIÓN {titulo}".upper()


def cotizacion_pdf_bytes(cot, items, empresa_row) -> bytes:
    """PDF horizontal estilo Agrocastilla / Río Maipo Constructora."""
    if FPDF is None:
        raise RuntimeError("FPDF no está instalado en el servidor")

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # Logo centrado (compacto para dejar espacio a la grilla)
    logo = LOGO_RIOMAIPO_PATH if LOGO_RIOMAIPO_PATH.exists() else LOGO_PATH
    if logo.exists():
        pdf.image(str(logo), x=128, y=4, w=40)
    else:
        pdf.set_text_color(180, 30, 30)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(0, 10)
        pdf.cell(297, 6, _pdf_txt("RIO MAIPO"), align="C", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(297, 5, _pdf_txt("Constructora"), align="C", ln=1)
        pdf.set_text_color(0, 0, 0)

    # Barra título
    title = _pdf_txt(cotizacion_titulo_pdf(cot))
    pdf.set_xy(18, 28)
    pdf.set_fill_color(210, 210, 210)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(261, 6, title, border=1, align="C", fill=True)

    # Tabla
    headers = ["ITEM", "ESPECIFICACIÓN", "OBS", "UND", "CANTIDAD", "VALOR", "TOTAL"]
    widths = [14, 74, 58, 16, 24, 37, 38]
    x0, y0 = 18, 36
    row_h = 4.0
    pdf.set_xy(x0, y0)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, widths):
        pdf.cell(w, row_h, h, border=1, align="C", fill=True)
    pdf.ln(row_h)

    subtotal = float(cot["subtotal"] or 0)
    if not subtotal and items:
        subtotal = sum(float(it["total"] or 0) for it in items)

    # Fila sección 1.0
    pdf.set_x(x0)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(widths[0], row_h, "1.0", border=1, align="C")
    for w in widths[1:-1]:
        pdf.cell(w, row_h, "", border=1)
    pdf.cell(widths[-1], row_h, _pdf_txt(f"$ {fmt_clp_plain(subtotal)}"), border=1, align="R")
    pdf.ln(row_h)

    # Ítems 1.1 .. N + vacíos hasta COT_PDF_ROWS
    filled = list(items)[:COT_PDF_ROWS]
    while len(filled) < COT_PDF_ROWS:
        filled.append(None)

    pdf.set_font("Helvetica", "", 8)
    for idx, it in enumerate(filled, start=1):
        pdf.set_x(x0)
        code = f"1.{idx}"
        if it is None:
            pdf.cell(widths[0], row_h, code, border=1, align="C")
            for w in widths[1:-1]:
                pdf.cell(w, row_h, "", border=1)
            pdf.cell(widths[-1], row_h, "$ -", border=1, align="R")
        else:
            desc = _pdf_txt(it["descripcion"])[:46]
            obs = _pdf_txt(it["obs"] if "obs" in it.keys() else "")[:34]
            und = _pdf_txt(it["unidad"] or "")
            cant = fmt_cant_pdf(it["cantidad"])
            valor = _pdf_txt(f"$ {fmt_clp_plain(it['precio_unitario'])}")
            total = _pdf_txt(f"$ {fmt_clp_plain(it['total'])}")
            pdf.cell(widths[0], row_h, code, border=1, align="C")
            pdf.cell(widths[1], row_h, desc, border=1)
            pdf.cell(widths[2], row_h, obs, border=1)
            pdf.cell(widths[3], row_h, und, border=1, align="C")
            pdf.cell(widths[4], row_h, cant, border=1, align="R")
            pdf.cell(widths[5], row_h, valor, border=1, align="R")
            pdf.cell(widths[6], row_h, total, border=1, align="R")
        pdf.ln(row_h)

    # Resumen inferior derecho
    gg_pct = float(cot["gg_pct"] if "gg_pct" in cot.keys() and cot["gg_pct"] is not None else 5)
    util_pct = float(
        cot["utilidad_pct"] if "utilidad_pct" in cot.keys() and cot["utilidad_pct"] is not None else 15
    )
    gg = float(cot["gg_monto"] if "gg_monto" in cot.keys() and cot["gg_monto"] is not None else round(subtotal * gg_pct / 100))
    util = float(
        cot["utilidad_monto"]
        if "utilidad_monto" in cot.keys() and cot["utilidad_monto"] is not None
        else round(subtotal * util_pct / 100)
    )
    neto = float(
        cot["valor_neto"] if "valor_neto" in cot.keys() and cot["valor_neto"] is not None else subtotal + gg + util
    )
    iva = float(cot["iva"] or 0)
    total = float(cot["total"] or 0)

    summary = [
        ("SUB TOTAL", f"$ {fmt_clp_plain(subtotal)}", False),
        (f"GG {gg_pct:g}%", f"$ {fmt_clp_plain(gg)}", False),
        (f"UTILIDAD {util_pct:g}%", f"$ {fmt_clp_plain(util)}", False),
        ("VALOR NETO", f"$ {fmt_clp_plain(neto)}", True),
        ("IVA", f"$ {fmt_clp_plain(iva)}", False),
        ("TOTAL", f"$ {fmt_clp_plain(total)}", True),
    ]
    label_w, val_w = 40, 38
    sx = x0 + sum(widths) - label_w - val_w
    sy = pdf.get_y() + 2
    for i, (lab, val, bold) in enumerate(summary):
        pdf.set_xy(sx, sy + i * row_h)
        pdf.set_font("Helvetica", "B" if bold else "", 8)
        border = 1
        pdf.cell(label_w, row_h, _pdf_txt(lab), border=border)
        pdf.cell(val_w, row_h, _pdf_txt(val), border=border, align="R")

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return bytes(raw)


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
            version TEXT DEFAULT '1', titulo TEXT,
            gg_pct REAL DEFAULT 5, utilidad_pct REAL DEFAULT 15,
            gg_monto REAL DEFAULT 0, utilidad_monto REAL DEFAULT 0,
            valor_neto REAL DEFAULT 0,
            subtotal REAL DEFAULT 0, iva REAL DEFAULT 0, total REAL DEFAULT 0,
            notas TEXT, cxc_id INTEGER,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS cotizacion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER NOT NULL,
            producto_id INTEGER, descripcion TEXT NOT NULL,
            obs TEXT, orden INTEGER DEFAULT 0,
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
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            clave_hash TEXT NOT NULL,
            nombre TEXT,
            tipo TEXT NOT NULL DEFAULT 'Administrador',
            activo INTEGER DEFAULT 1
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
                ("gg_pct", "Gastos generales", "5", "%"),
                ("utilidad_pct", "Utilidad", "15", "%"),
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
    migrate_cotizaciones_schema(c)
    ensure_default_user(c)
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


def cxc_estado_label(estado: str | None) -> str:
    e = (estado or "").lower()
    if e in ("pagado", "pagada"):
        return "Pagado"
    if e in ("parcial", "abonado", "abonada"):
        return "Abonado"
    return "Pendiente"


def cxc_estado_class(estado: str | None) -> str:
    e = (estado or "").lower()
    if e in ("pagado", "pagada"):
        return "pagado"
    if e in ("parcial", "abonado", "abonada"):
        return "abonado"
    return "pendiente"


def cxc_tipo_label(tipo: str | None, cotizacion_id=None) -> str:
    if cotizacion_id:
        return "Cotización"
    t = (tipo or "").upper()
    if t in ("FAC", "FACTURA", "FA"):
        return "Factura"
    if t in ("ND", "NOTA"):
        return "Nota de débito"
    if t in ("EP",):
        return "EP"
    return tipo or "—"


def fmt_dmy(s: str | None) -> str:
    if not s:
        return "—"
    d = dparse(str(s))
    return d.strftime("%d/%m/%Y") if d else str(s)


def list_cxc_documentos(c: sqlite3.Connection, busqueda: str | None = None):
    sql = """
        SELECT cu.id, cu.documento, cu.tipo_doc, cu.concepto,
               cu.fecha_emision, cu.fecha_vencimiento,
               cu.monto, cu.abonado, cu.saldo, cu.estado,
               cu.cotizacion_id, cl.razon_social AS cliente
        FROM cuentas cu
        LEFT JOIN clientes cl ON cl.id = cu.cliente_id
        WHERE 1=1
    """
    params: list = []
    if busqueda and busqueda.strip():
        like = f"%{busqueda.strip()}%"
        sql += " AND (cl.razon_social LIKE ? OR cu.documento LIKE ? OR cu.concepto LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY cu.id DESC"
    return c.execute(sql, params).fetchall()


def cxc_kpis(docs) -> dict:
    total_docs = len(docs)
    total_monto = sum(float(d["monto"] or 0) for d in docs)
    pend = [d for d in docs if cxc_estado_class(d["estado"]) == "pendiente"]
    abon = [d for d in docs if cxc_estado_class(d["estado"]) == "abonado"]
    pag = [d for d in docs if cxc_estado_class(d["estado"]) == "pagado"]
    return {
        "total_docs": total_docs,
        "total_monto": total_monto,
        "pend_n": len(pend),
        "pend_m": sum(float(d["monto"] or 0) for d in pend),
        "abon_n": len(abon),
        "abon_m": sum(float(d["monto"] or 0) for d in abon),
        "pag_n": len(pag),
        "pag_m": sum(float(d["monto"] or 0) for d in pag),
        "tasa": (len(pag) / total_docs * 100) if total_docs else 0.0,
    }


def fetch_cuenta(c: sqlite3.Connection, cuenta_id: int):
    return c.execute(
        """
        SELECT cu.*, cl.razon_social
        FROM cuentas cu
        LEFT JOIN clientes cl ON cl.id = cu.cliente_id
        WHERE cu.id=?
        """,
        (cuenta_id,),
    ).fetchone()


def delete_cuenta(c: sqlite3.Connection, cuenta_id: int) -> str | None:
    row = c.execute("SELECT id FROM cuentas WHERE id=?", (cuenta_id,)).fetchone()
    if not row:
        return "Documento no encontrado"
    c.execute("UPDATE cotizaciones SET cxc_id=NULL WHERE cxc_id=?", (cuenta_id,))
    c.execute("DELETE FROM abonos WHERE cuenta_id=?", (cuenta_id,))
    c.execute("DELETE FROM cuentas WHERE id=?", (cuenta_id,))
    c.commit()
    return None


init_db()

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = ""
if "auth_tipo" not in st.session_state:
    st.session_state.auth_tipo = ""
if "auth_nombre" not in st.session_state:
    st.session_state.auth_nombre = ""

if not st.session_state.auth_ok:
    render_login()
    st.stop()

inject_styles()

db = conn()
migrate_usuarios_schema(db)
db.commit()
empresa = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()

# Hidrata tipo/nombre si la sesión venía de un login anterior
if st.session_state.auth_ok and st.session_state.auth_user and not st.session_state.auth_tipo:
    urow = db.execute(
        "SELECT tipo, nombre FROM usuarios WHERE lower(usuario)=lower(?)",
        (st.session_state.auth_user,),
    ).fetchone()
    if urow:
        st.session_state.auth_tipo = urow["tipo"] or "Administrador"
        st.session_state.auth_nombre = urow["nombre"] or st.session_state.auth_user

# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
razon = empresa["razon_social"] if empresa else "Constructora Río Maipo"
rut_emp = empresa["rut"] if empresa else "—"
auth_user = st.session_state.get("auth_user") or "usuario"
auth_tipo = st.session_state.get("auth_tipo") or "Consulta"

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
    st.caption(f"Sesión: {auth_user}")
    st.caption(f"Tipo: {auth_tipo}")
    st.caption("Control comercial · cobranza · catálogo · vista 360")
    st.markdown(
        '<span class="stat-pill">erpmaster.cl/riomaipo</span>',
        unsafe_allow_html=True,
    )
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state.auth_ok = False
        st.session_state.auth_user = ""
        st.session_state.auth_tipo = ""
        st.session_state.auth_nombre = ""
        st.rerun()

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
    page_header("Cotizaciones", "Gestión comercial con indicadores, filtros y acciones rápidas.")

    if "cot_mode" not in st.session_state:
        st.session_state.cot_mode = "list"
    if "cot_focus_id" not in st.session_state:
        st.session_state.cot_focus_id = None
    if "cot_pdf_id" not in st.session_state:
        st.session_state.cot_pdf_id = None
    if "cot_delete_id" not in st.session_state:
        st.session_state.cot_delete_id = None

    def _cot_back_list():
        st.session_state.cot_mode = "list"
        st.session_state.cot_focus_id = None
        st.session_state.cot_pdf_id = None
        st.session_state.cot_delete_id = None

    clientes = db.execute(
        "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
    ).fetchall()
    productos = db.execute(
        "SELECT id, codigo, nombre, unidad, precio FROM productos WHERE activo=1 ORDER BY nombre"
    ).fetchall()
    iva_pct = param(db, "iva", 19) / 100
    validez_def = int(param(db, "validez_cotizacion", 30))
    gg_pct_def = param(db, "gg_pct", 5)
    utilidad_pct_def = param(db, "utilidad_pct", 15)

    # ----- PDF download banner -----
    if st.session_state.cot_pdf_id:
        cot_pdf = fetch_cotizacion(db, int(st.session_state.cot_pdf_id))
        if cot_pdf:
            items_pdf = fetch_cotizacion_items(db, int(st.session_state.cot_pdf_id))
            try:
                pdf_bytes = cotizacion_pdf_bytes(cot_pdf, items_pdf, empresa)
                st.download_button(
                    f"Descargar PDF {cot_pdf['folio']}",
                    data=pdf_bytes,
                    file_name=f"{cot_pdf['folio']}.pdf",
                    mime="application/pdf",
                    type="primary",
                    key=f"dl_pdf_{cot_pdf['id']}",
                )
            except Exception as exc:
                st.error(f"No se pudo generar el PDF: {exc}")
        if st.button("Cerrar PDF", key="close_pdf"):
            st.session_state.cot_pdf_id = None
            st.rerun()

    # ----- Confirm delete -----
    if st.session_state.cot_delete_id:
        cot_del = fetch_cotizacion(db, int(st.session_state.cot_delete_id))
        if cot_del:
            alert_line(
                "warn",
                f"¿Eliminar la cotización <strong>{cot_del['folio']}</strong> de "
                f"{cot_del['razon_social'] or 'cliente'}?",
            )
            d1, d2 = st.columns(2)
            with d1:
                if st.button("Confirmar eliminación", type="primary", key="confirm_del_cot"):
                    err = delete_cotizacion(db, int(st.session_state.cot_delete_id))
                    st.session_state.cot_delete_id = None
                    if err:
                        st.error(err)
                    else:
                        st.success("Cotización eliminada")
                        st.rerun()
            with d2:
                if st.button("Cancelar", key="cancel_del_cot"):
                    st.session_state.cot_delete_id = None
                    st.rerun()

    mode = st.session_state.cot_mode

    # =====================================================================
    # LISTADO + CREAR + ACCIONES
    # =====================================================================
    if mode == "list":
        # ----- KPIs tipo SOLUERP -----
        all_rows = db.execute(
            """
            SELECT id, folio, fecha, estado, total, cliente_id, asunto, proyecto
            FROM cotizaciones
            """
        ).fetchall()
        hoy = date.today()
        n_total = len(all_rows)
        sum_total = sum(float(r["total"] or 0) for r in all_rows)
        aprobadas = [r for r in all_rows if r["estado"] == "aprobada"]
        rechazadas = [r for r in all_rows if r["estado"] == "rechazada"]
        n_apr = len(aprobadas)
        n_rec = len(rechazadas)
        sum_apr = sum(float(r["total"] or 0) for r in aprobadas)
        sum_rec = sum(float(r["total"] or 0) for r in rechazadas)
        conv_anual = (n_apr / n_total * 100) if n_total else 0.0

        mes_rows = []
        for r in all_rows:
            f = dparse(r["fecha"])
            if f and f.year == hoy.year and f.month == hoy.month:
                mes_rows.append(r)
        n_mes = len(mes_rows)
        n_mes_apr = sum(1 for r in mes_rows if r["estado"] == "aprobada")
        conv_mes = (n_mes_apr / n_mes * 100) if n_mes else 0.0

        st.markdown(
            f"""
            <div class="cot-kpi-grid">
              <div class="cot-kpi ing">
                <div class="label">Ingresadas</div>
                <div class="value">{n_total} Cotizaciones</div>
                <div class="hint">{clp(sum_total)}</div>
              </div>
              <div class="cot-kpi apr">
                <div class="label">Aprobadas</div>
                <div class="value">{n_apr} Cotizaciones</div>
                <div class="hint">{clp(sum_apr)}</div>
              </div>
              <div class="cot-kpi rec">
                <div class="label">Rechazadas</div>
                <div class="value">{n_rec} Cotizaciones</div>
                <div class="hint">{clp(sum_rec)}</div>
              </div>
              <div class="cot-kpi an">
                <div class="label">Conversión anual</div>
                <div class="value">{conv_anual:.1f} %</div>
                <div class="hint">{n_apr} de {n_total}</div>
              </div>
              <div class="cot-kpi mes">
                <div class="label">Conversión mes actual</div>
                <div class="value">{conv_mes:.0f} %</div>
                <div class="hint">{n_mes_apr} de {n_mes}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ----- Filtros -----
        st.markdown('<div class="cot-filters">', unsafe_allow_html=True)
        f1, f2, f3, f4, f5, f6 = st.columns([1.1, 1.1, 1.6, 1.1, 0.9, 1])
        with f1:
            desde = st.date_input("Desde", value=date(2020, 1, 1), format="DD/MM/YYYY", key="cot_desde")
        with f2:
            hasta = st.date_input("Hasta", value=date.today(), format="DD/MM/YYYY", key="cot_hasta")
        with f3:
            q = st.text_input("Número, cliente", placeholder="COT-1000 o cliente…", key="cot_q")
        with f4:
            est_filtro = st.selectbox(
                "Estado",
                ["Todos", "Ingresada", "Aprobada", "Rechazada"],
                key="cot_est_filtro",
            )
        with f5:
            st.write("")
            st.write("")
            st.button("Buscar", use_container_width=True, key="cot_buscar")
        with f6:
            st.write("")
            st.write("")
            if st.button("+ Nueva", type="primary", use_container_width=True, key="cot_crear"):
                st.session_state.cot_mode = "new"
                st.session_state.cot_focus_id = None
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        sql = """
            SELECT c.id, c.folio, c.fecha, cl.razon_social AS cliente,
                   c.asunto, c.proyecto, c.estado, c.total
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id
            WHERE 1=1
        """
        params: list = []
        if isinstance(desde, date):
            sql += " AND (c.fecha IS NULL OR c.fecha >= ?)"
            params.append(desde.isoformat())
        if isinstance(hasta, date):
            sql += " AND (c.fecha IS NULL OR c.fecha <= ?)"
            params.append(hasta.isoformat())
        if q and q.strip():
            like = f"%{q.strip()}%"
            sql += " AND (c.folio LIKE ? OR cl.razon_social LIKE ? OR c.asunto LIKE ? OR c.proyecto LIKE ?)"
            params.extend([like, like, like, like])
        if est_filtro == "Aprobada":
            sql += " AND c.estado = 'aprobada'"
        elif est_filtro == "Rechazada":
            sql += " AND c.estado = 'rechazada'"
        elif est_filtro == "Ingresada":
            sql += " AND c.estado IN ('borrador','enviada')"
        rows = db.execute(sql + " ORDER BY c.id DESC", params).fetchall()

        st.caption(f"Mostrando {len(rows)} cotizaciones")

        if not rows:
            empty_state("No hay cotizaciones para estos filtros. Prueba + Nueva.")
        else:
            head = st.columns([0.35, 0.9, 0.85, 2.0, 0.95, 0.9, 1.9])
            headers = ["#", "Número", "Fecha", "Cliente", "Monto", "Estado", "Acciones"]
            for col, title in zip(head, headers):
                col.markdown(
                    f"<div style='font-size:.7rem;font-weight:800;text-transform:uppercase;"
                    f"letter-spacing:.04em;color:#5b6b7c;padding:.2rem 0;'>{title}</div>",
                    unsafe_allow_html=True,
                )
            for idx, r in enumerate(rows, start=1):
                cid = int(r["id"])
                est = r["estado"] or ""
                dot = estado_dot_class(est)
                label = estado_label_soluerp(est)
                desc = (r["asunto"] or r["proyecto"] or "").strip()
                cliente = r["cliente"] or "—"
                c_n, c_num, c_fec, c_cli, c_mon, c_est, c_act = st.columns(
                    [0.35, 0.9, 0.85, 2.0, 0.95, 0.9, 1.9],
                    vertical_alignment="center",
                )
                zebra = "#fafcff" if idx % 2 == 0 else "#ffffff"
                with c_n:
                    st.markdown(
                        f"<div style='background:{zebra};padding:.35rem 0;'>{idx}</div>",
                        unsafe_allow_html=True,
                    )
                with c_num:
                    st.markdown(
                        f"<div class='cot-num' style='background:{zebra};padding:.35rem 0;'>{r['folio']}</div>",
                        unsafe_allow_html=True,
                    )
                with c_fec:
                    fec = r["fecha"] or "—"
                    if fec and fec != "—":
                        try:
                            fec = date.fromisoformat(str(fec)).strftime("%d/%m/%Y")
                        except ValueError:
                            pass
                    st.markdown(f"<div style='padding:.35rem 0;'>{fec}</div>", unsafe_allow_html=True)
                with c_cli:
                    st.markdown(
                        f"<div class='cot-cli'><strong>{cliente}</strong><span>{desc or '—'}</span></div>",
                        unsafe_allow_html=True,
                    )
                with c_mon:
                    st.markdown(f"<div><strong>{clp(r['total'])}</strong></div>", unsafe_allow_html=True)
                with c_est:
                    st.markdown(
                        f"<div class='cot-estado {est}'><span class='cot-dot {dot}'></span>{label}</div>",
                        unsafe_allow_html=True,
                    )
                with c_act:
                    a1, a2, a3, a4 = st.columns(4)
                    with a1:
                        if st.button("Ver", key=f"cot_ver_{cid}", use_container_width=True, help="Visualizar"):
                            st.session_state.cot_mode = "view"
                            st.session_state.cot_focus_id = cid
                            st.rerun()
                    with a2:
                        if st.button("PDF", key=f"cot_pdf_{cid}", use_container_width=True, help="PDF"):
                            st.session_state.cot_pdf_id = cid
                            st.rerun()
                    with a3:
                        if st.button("Editar", key=f"cot_edit_{cid}", use_container_width=True, help="Modificar"):
                            st.session_state.cot_mode = "edit"
                            st.session_state.cot_focus_id = cid
                            st.rerun()
                    with a4:
                        if st.button("Borrar", key=f"cot_del_{cid}", use_container_width=True, help="Eliminar"):
                            st.session_state.cot_delete_id = cid
                            st.rerun()

    # =====================================================================
    # VISUALIZAR
    # =====================================================================
    elif mode == "view":
        if st.button("← Volver al listado", key="back_view"):
            _cot_back_list()
            st.rerun()
        cot = fetch_cotizacion(db, int(st.session_state.cot_focus_id or 0))
        if not cot:
            st.error("Cotización no encontrada")
            _cot_back_list()
        else:
            badge = (
                "ok" if cot["estado"] == "aprobada"
                else "warn" if cot["estado"] == "enviada"
                else "muted"
            )
            st.markdown(
                f"""
                <div class="panel">
                  <div class="split-title" style="margin:0;">
                    <h3>{cot['folio']}</h3>
                    <span class="badge {badge}">{cot['estado']}</span>
                  </div>
                  <p style="margin:.45rem 0 0;color:var(--muted);">
                    {cot['razon_social'] or '—'} · {cot['proyecto'] or '—'} · {cot['asunto'] or 'Sin asunto'} · Total {clp(cot['total'])}
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            gg_p = float(cot["gg_pct"] if cot["gg_pct"] is not None else gg_pct_def)
            util_p = float(cot["utilidad_pct"] if cot["utilidad_pct"] is not None else utilidad_pct_def)
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Subtotal", clp(cot["subtotal"]))
            m2.metric(f"GG {gg_p:g}%", clp(cot["gg_monto"]))
            m3.metric(f"Utilidad {util_p:g}%", clp(cot["utilidad_monto"]))
            m4.metric("Valor neto", clp(cot["valor_neto"] or 0))
            m5.metric("IVA", clp(cot["iva"]))
            m6.metric("Total", clp(cot["total"]))
            st.dataframe(
                pd.read_sql_query(
                    """
                    SELECT descripcion AS Especificación,
                           COALESCE(obs,'') AS Obs,
                           unidad AS Und,
                           cantidad AS Cantidad,
                           precio_unitario AS Valor,
                           total AS Total
                    FROM cotizacion_items
                    WHERE cotizacion_id=?
                    ORDER BY COALESCE(orden,0), id
                    """,
                    db,
                    params=(cot["id"],),
                ),
                use_container_width=True,
                hide_index=True,
            )
            if cot["notas"]:
                st.info(cot["notas"])

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("PDF", key="view_pdf", use_container_width=True):
                    st.session_state.cot_pdf_id = cot["id"]
                    st.rerun()
            with b2:
                if st.button("Modificar", key="view_edit", use_container_width=True):
                    st.session_state.cot_mode = "edit"
                    st.session_state.cot_focus_id = cot["id"]
                    st.rerun()
            with b3:
                if st.button("Eliminar", key="view_del", use_container_width=True):
                    st.session_state.cot_delete_id = cot["id"]
                    st.session_state.cot_mode = "list"
                    st.rerun()

            st.markdown("#### Gestión")
            nuevo_estado = st.selectbox(
                "Cambiar estado",
                ["borrador", "enviada", "aprobada", "rechazada"],
                index=["borrador", "enviada", "aprobada", "rechazada"].index(cot["estado"])
                if cot["estado"] in ["borrador", "enviada", "aprobada", "rechazada"] else 0,
            )
            g1, g2 = st.columns(2)
            with g1:
                if st.button("Actualizar estado", key="view_estado"):
                    db.execute("UPDATE cotizaciones SET estado=? WHERE id=?", (nuevo_estado, cot["id"]))
                    db.commit()
                    st.success("Estado actualizado")
                    st.rerun()
            with g2:
                if cot["estado"] == "aprobada" and not cot["cxc_id"]:
                    if st.button("Generar cuenta por cobrar", type="primary", key="view_cxc"):
                        dias = int(param(db, "dias_credito", 30))
                        doc = next_code(db, "cuentas", "documento", "EP")
                        cur = db.cursor()
                        cur.execute(
                            """
                            INSERT INTO cuentas (documento, cliente_id, cotizacion_id, tipo_doc, concepto,
                                fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
                            VALUES (?,?,?,?,?,?,?,?,0,?, 'pendiente')
                            """,
                            (
                                doc,
                                cot["cliente_id"],
                                cot["id"],
                                "EP",
                                f"Desde cotización {cot['folio']}",
                                date.today().isoformat(),
                                (date.today() + timedelta(days=dias)).isoformat(),
                                float(cot["total"]),
                                float(cot["total"]),
                            ),
                        )
                        cxc_id = cur.lastrowid
                        cur.execute("UPDATE cotizaciones SET cxc_id=? WHERE id=?", (cxc_id, cot["id"]))
                        db.commit()
                        st.success(f"CxC {doc} creada por {clp(cot['total'])}")
                        st.rerun()
                elif cot["cxc_id"]:
                    alert_line("ok", f"Ya tiene CxC vinculada (id {cot['cxc_id']}).")
                else:
                    st.caption("Aprueba la cotización para poder generar la CxC.")

    # =====================================================================
    # NUEVA / EDITAR
    # =====================================================================
    elif mode in ("new", "edit"):
        if st.button("← Volver al listado", key="back_form"):
            _cot_back_list()
            st.rerun()

        edit_cot = None
        edit_items = []
        if mode == "edit":
            edit_cot = fetch_cotizacion(db, int(st.session_state.cot_focus_id or 0))
            if not edit_cot:
                st.error("Cotización no encontrada")
                _cot_back_list()
                st.rerun()
            edit_items = fetch_cotizacion_items(db, int(edit_cot["id"]))
            st.subheader(f"Modificar {edit_cot['folio']}")
        else:
            st.subheader("Nueva cotización")

        if not clientes:
            empty_state("Crea clientes primero para poder emitir cotizaciones.")
        else:
            cli_ids = [c["id"] for c in clientes]
            cli_default = 0
            if edit_cot and edit_cot["cliente_id"] in cli_ids:
                cli_default = cli_ids.index(edit_cot["cliente_id"])
            with st.form("f_cot"):
                st.caption("Formato Río Maipo: ítems + OBS + GG + Utilidad + IVA (como cotización Agrocastilla).")
                h1, h2, h3 = st.columns([0.7, 2.2, 1.4])
                with h1:
                    version = st.text_input(
                        "Versión",
                        value=(edit_cot["version"] or "1") if edit_cot else "1",
                        help="Aparece como V1, V2… en el PDF",
                    )
                with h2:
                    titulo = st.text_input(
                        "Título cotización (barra PDF)",
                        value=(edit_cot["titulo"] or "") if edit_cot else "",
                        placeholder="AGROCASTILLA BODEGA ENOLOGIA SOMBREADERO",
                    )
                with h3:
                    cliente_id = st.selectbox(
                        "Cliente",
                        options=cli_ids,
                        index=cli_default,
                        format_func=lambda i: next(x["razon_social"] for x in clientes if x["id"] == i),
                    )
                p1, p2, p3, p4 = st.columns(4)
                with p1:
                    proyecto = st.text_input(
                        "Proyecto / obra",
                        value=(edit_cot["proyecto"] or "") if edit_cot else "",
                        placeholder="Pirque · Sombreador",
                    )
                with p2:
                    asunto = st.text_input(
                        "Asunto / nombre interno",
                        value=(edit_cot["asunto"] or "") if edit_cot else "",
                    )
                with p3:
                    validez = st.number_input(
                        "Validez (días)",
                        min_value=1,
                        value=int(edit_cot["validez_dias"] or validez_def) if edit_cot else validez_def,
                    )
                with p4:
                    estados = ["borrador", "enviada", "aprobada", "rechazada"]
                    est_val = edit_cot["estado"] if edit_cot and edit_cot["estado"] in estados else "borrador"
                    estado = st.selectbox("Estado", estados, index=estados.index(est_val))

                g1, g2 = st.columns(2)
                with g1:
                    gg_pct = st.number_input(
                        "GG %",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(edit_cot["gg_pct"] if edit_cot and edit_cot["gg_pct"] is not None else gg_pct_def),
                        step=0.5,
                    )
                with g2:
                    utilidad_pct = st.number_input(
                        "Utilidad %",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(
                            edit_cot["utilidad_pct"]
                            if edit_cot and edit_cot["utilidad_pct"] is not None
                            else utilidad_pct_def
                        ),
                        step=0.5,
                    )

                st.markdown("**Ítems** · Especificación · Obs · Und · Cantidad · Valor unitario")
                head = st.columns([0.45, 2.1, 1.4, 0.7, 0.8, 1.0])
                for col, label in zip(head, ["Item", "Especificación", "Obs", "Und", "Cant", "Valor"]):
                    col.caption(label)

                items = []
                for i in range(COT_ITEM_SLOTS):
                    base = edit_items[i] if i < len(edit_items) else None
                    cols = st.columns([0.45, 2.1, 1.4, 0.7, 0.8, 1.0])
                    with cols[0]:
                        st.text_input(
                            "item",
                            value=f"1.{i+1}",
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"itemcode_{mode}_{i}",
                        )
                    with cols[1]:
                        desc = st.text_input(
                            "Especificación",
                            key=f"desc_{mode}_{i}",
                            value=(base["descripcion"] if base else ""),
                            label_visibility="collapsed",
                            placeholder="excavaciones",
                        )
                    with cols[2]:
                        obs = st.text_input(
                            "Obs",
                            key=f"obs_{mode}_{i}",
                            value=(base["obs"] if base else ""),
                            label_visibility="collapsed",
                            placeholder="100x100x180",
                        )
                    with cols[3]:
                        un = st.text_input(
                            "Und",
                            value=(base["unidad"] if base else "un"),
                            key=f"un_{mode}_{i}",
                            label_visibility="collapsed",
                        )
                    with cols[4]:
                        cant = st.number_input(
                            "Cant",
                            min_value=0.0,
                            value=float(base["cantidad"]) if base else 0.0,
                            key=f"cant_{mode}_{i}",
                            label_visibility="collapsed",
                            step=1.0,
                        )
                    with cols[5]:
                        pu = st.number_input(
                            "Valor",
                            min_value=0.0,
                            value=float(base["precio_unitario"]) if base else 0.0,
                            key=f"pu_{mode}_{i}",
                            label_visibility="collapsed",
                            step=1000.0,
                        )
                    items.append((desc, obs, un, cant, pu))

                notas = st.text_area(
                    "Notas internas",
                    value=(edit_cot["notas"] or "") if edit_cot else "",
                )
                guardar = st.form_submit_button(
                    "Guardar cambios" if mode == "edit" else "Guardar cotización",
                    type="primary",
                )

            if guardar:
                lineas = []
                for orden, (desc, obs, un, cant, pu) in enumerate(items, start=1):
                    if float(cant or 0) <= 0 or not str(desc or "").strip():
                        continue
                    descripcion = str(desc).strip()
                    unidad = str(un or "un").strip() or "un"
                    precio = float(pu or 0)
                    total_ln = float(cant) * precio
                    lineas.append(
                        (
                            None,
                            descripcion,
                            str(obs or "").strip() or None,
                            orden,
                            unidad,
                            float(cant),
                            precio,
                            total_ln,
                        )
                    )
                if not lineas:
                    st.error("Agrega al menos un ítem con especificación y cantidad > 0")
                else:
                    subtotal = sum(x[7] for x in lineas)
                    tots = calc_cotizacion_totales(subtotal, gg_pct, utilidad_pct, iva_pct)
                    cur = db.cursor()
                    ver = (version or "1").strip().lstrip("Vv") or "1"
                    tit = (titulo or "").strip() or None
                    if mode == "edit" and edit_cot:
                        cur.execute(
                            """
                            UPDATE cotizaciones
                            SET cliente_id=?, asunto=?, proyecto=?, estado=?, validez_dias=?,
                                version=?, titulo=?, gg_pct=?, utilidad_pct=?,
                                gg_monto=?, utilidad_monto=?, valor_neto=?,
                                subtotal=?, iva=?, total=?, notas=?
                            WHERE id=?
                            """,
                            (
                                cliente_id,
                                asunto.strip() or None,
                                proyecto.strip() or None,
                                estado,
                                int(validez),
                                ver,
                                tit,
                                float(gg_pct),
                                float(utilidad_pct),
                                tots["gg_monto"],
                                tots["utilidad_monto"],
                                tots["valor_neto"],
                                tots["subtotal"],
                                tots["iva"],
                                tots["total"],
                                notas.strip() or None,
                                edit_cot["id"],
                            ),
                        )
                        cur.execute("DELETE FROM cotizacion_items WHERE cotizacion_id=?", (edit_cot["id"],))
                        cot_id = edit_cot["id"]
                        folio = edit_cot["folio"]
                    else:
                        folio = next_code(db, "cotizaciones", "folio", "COT")
                        cur.execute(
                            """
                            INSERT INTO cotizaciones
                            (folio, cliente_id, asunto, proyecto, estado, fecha, validez_dias,
                             version, titulo, gg_pct, utilidad_pct,
                             gg_monto, utilidad_monto, valor_neto,
                             subtotal, iva, total, notas)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                folio,
                                cliente_id,
                                asunto.strip() or None,
                                proyecto.strip() or None,
                                estado,
                                date.today().isoformat(),
                                int(validez),
                                ver,
                                tit,
                                float(gg_pct),
                                float(utilidad_pct),
                                tots["gg_monto"],
                                tots["utilidad_monto"],
                                tots["valor_neto"],
                                tots["subtotal"],
                                tots["iva"],
                                tots["total"],
                                notas.strip() or None,
                            ),
                        )
                        cot_id = cur.lastrowid
                    cur.executemany(
                        """
                        INSERT INTO cotizacion_items
                        (cotizacion_id, producto_id, descripcion, obs, orden, unidad, cantidad, precio_unitario, total)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        [(cot_id, *ln) for ln in lineas],
                    )
                    db.commit()
                    st.success(f"{folio} guardada · total {clp(tots['total'])}")
                    st.session_state.cot_mode = "view"
                    st.session_state.cot_focus_id = cot_id
                    st.rerun()

# ===========================================================================
# CUENTAS POR COBRAR (estilo SOLUERP)
# ===========================================================================
elif modulo == "Cuentas por cobrar":
    page_header("Cuentas por cobrar", "Documentos, saldos y cobranza con acciones rápidas.")

    if "cxc_mode" not in st.session_state:
        st.session_state.cxc_mode = "list"
    if "cxc_focus_id" not in st.session_state:
        st.session_state.cxc_focus_id = None
    if "cxc_delete_id" not in st.session_state:
        st.session_state.cxc_delete_id = None
    if "cxc_busqueda" not in st.session_state:
        st.session_state.cxc_busqueda = ""

    def _cxc_back_list():
        st.session_state.cxc_mode = "list"
        st.session_state.cxc_focus_id = None
        st.session_state.cxc_delete_id = None

    clientes = db.execute(
        "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
    ).fetchall()
    dias_credito = int(param(db, "dias_credito", 30))

    # ----- Confirm delete -----
    if st.session_state.cxc_delete_id:
        cxc_del = fetch_cuenta(db, int(st.session_state.cxc_delete_id))
        if cxc_del:
            alert_line(
                "warn",
                f"¿Eliminar el documento <strong>{cxc_del['documento']}</strong> de "
                f"{cxc_del['razon_social'] or 'cliente'}?",
            )
            d1, d2 = st.columns(2)
            with d1:
                if st.button("Confirmar eliminación", type="primary", key="confirm_del_cxc"):
                    err = delete_cuenta(db, int(st.session_state.cxc_delete_id))
                    st.session_state.cxc_delete_id = None
                    if err:
                        st.error(err)
                    else:
                        st.success("Documento eliminado")
                        st.rerun()
            with d2:
                if st.button("Cancelar", key="cancel_del_cxc"):
                    st.session_state.cxc_delete_id = None
                    st.rerun()

    mode = st.session_state.cxc_mode

    # =====================================================================
    # LISTADO
    # =====================================================================
    if mode == "list":
        busq = st.session_state.get("cxc_busqueda", "").strip()
        docs = list_cxc_documentos(db, busqueda=busq or None)
        kpis = cxc_kpis(docs)

        st.markdown(
            f"""
            <div class="cot-kpi-grid">
              <div class="cot-kpi ing">
                <div class="label">Total documentos</div>
                <div class="value">{kpis['total_docs']} Documentos</div>
                <div class="hint">{clp(kpis['total_monto'])}</div>
              </div>
              <div class="cot-kpi rec">
                <div class="label">Pendientes</div>
                <div class="value">{kpis['pend_n']} Documentos</div>
                <div class="hint">{clp(kpis['pend_m'])}</div>
              </div>
              <div class="cot-kpi apr">
                <div class="label">Abonados</div>
                <div class="value">{kpis['abon_n']} Documentos</div>
                <div class="hint">{clp(kpis['abon_m'])}</div>
              </div>
              <div class="cot-kpi an">
                <div class="label">Pagados</div>
                <div class="value">{kpis['pag_n']} Documentos</div>
                <div class="hint">{clp(kpis['pag_m'])}</div>
              </div>
              <div class="cot-kpi mes">
                <div class="label">Tasa de Cobranza</div>
                <div class="value">{kpis['tasa']:.1f} %</div>
                <div class="hint">{kpis['pag_n']} de {kpis['total_docs']}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="cot-filters">', unsafe_allow_html=True)
        f1, f2, f3 = st.columns([2.4, 0.9, 1])
        with f1:
            razon_q = st.text_input(
                "Razón social",
                value=st.session_state.cxc_busqueda,
                placeholder="Buscar por cliente…",
                key="cxc_razon_input",
            )
        with f2:
            st.write("")
            st.write("")
            if st.button("Buscar", use_container_width=True, key="cxc_buscar"):
                st.session_state.cxc_busqueda = razon_q or ""
                st.rerun()
        with f3:
            st.write("")
            st.write("")
            if st.button("+ Nuevo", type="primary", use_container_width=True, key="cxc_crear"):
                st.session_state.cxc_mode = "new"
                st.session_state.cxc_focus_id = None
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.caption(f"Mostrando {len(docs)} documentos")

        if not docs:
            empty_state("No hay documentos en cartera. Prueba + Nuevo.")
        else:
            head = st.columns([0.35, 1.7, 0.75, 0.85, 0.85, 0.85, 0.95, 0.95, 0.95, 0.85, 1.5])
            headers = [
                "#", "Cliente", "T.Doc", "Núm.", "F.Emisión", "F.Vence",
                "Total", "Abonos", "Saldo", "Estado", "Acciones",
            ]
            for col, title in zip(head, headers):
                col.markdown(
                    f"<div style='font-size:.68rem;font-weight:800;text-transform:uppercase;"
                    f"letter-spacing:.04em;color:#5b6b7c;padding:.2rem 0;'>{title}</div>",
                    unsafe_allow_html=True,
                )

            sum_total = sum_abonos = sum_saldo = 0.0
            for idx, r in enumerate(docs, start=1):
                cid = int(r["id"])
                est_cls = cxc_estado_class(r["estado"])
                est_lbl = cxc_estado_label(r["estado"])
                tipo_lbl = cxc_tipo_label(r["tipo_doc"], r["cotizacion_id"])
                total_v = float(r["monto"] or 0)
                abon_v = float(r["abonado"] or 0)
                saldo_v = float(r["saldo"] or 0)
                sum_total += total_v
                sum_abonos += abon_v
                sum_saldo += saldo_v
                cols = st.columns(
                    [0.35, 1.7, 0.75, 0.85, 0.85, 0.85, 0.95, 0.95, 0.95, 0.85, 1.5],
                    vertical_alignment="center",
                )
                zebra = "#fafcff" if idx % 2 == 0 else "#ffffff"
                vals = [
                    str(idx),
                    r["cliente"] or "—",
                    tipo_lbl,
                    r["documento"] or "—",
                    fmt_dmy(r["fecha_emision"]),
                    fmt_dmy(r["fecha_vencimiento"]),
                    clp(total_v),
                    clp(abon_v),
                    clp(saldo_v),
                ]
                for i, v in enumerate(vals):
                    with cols[i]:
                        if i == 3 and r["cotizacion_id"]:
                            st.markdown(
                                f"<div class='cot-num' style='background:{zebra};padding:.3rem 0;'>{v}</div>",
                                unsafe_allow_html=True,
                            )
                        elif i == 1:
                            st.markdown(
                                f"<div style='background:{zebra};padding:.3rem 0;font-weight:700;'>{v}</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f"<div style='background:{zebra};padding:.3rem 0;'>{v}</div>",
                                unsafe_allow_html=True,
                            )
                with cols[9]:
                    st.markdown(
                        f"<div class='cxc-estado {est_cls}' style='background:{zebra};padding:.3rem 0;'>{est_lbl}</div>",
                        unsafe_allow_html=True,
                    )
                with cols[10]:
                    a1, a2, a3 = st.columns(3)
                    with a1:
                        if st.button("Ver", key=f"cxc_ver_{cid}", use_container_width=True, help="Visualizar"):
                            st.session_state.cxc_mode = "view"
                            st.session_state.cxc_focus_id = cid
                            st.rerun()
                    with a2:
                        if st.button("Edit", key=f"cxc_edit_{cid}", use_container_width=True, help="Modificar"):
                            st.session_state.cxc_mode = "edit"
                            st.session_state.cxc_focus_id = cid
                            st.rerun()
                    with a3:
                        if st.button("Del", key=f"cxc_del_{cid}", use_container_width=True, help="Eliminar"):
                            st.session_state.cxc_delete_id = cid
                            st.rerun()

            tcols = st.columns([0.35, 1.7, 0.75, 0.85, 0.85, 0.85, 0.95, 0.95, 0.95, 0.85, 1.5])
            with tcols[5]:
                st.markdown("<div class='cxc-total-row'>Totales</div>", unsafe_allow_html=True)
            with tcols[6]:
                st.markdown(f"<div class='cxc-total-row'>{clp(sum_total)}</div>", unsafe_allow_html=True)
            with tcols[7]:
                st.markdown(f"<div class='cxc-total-row'>{clp(sum_abonos)}</div>", unsafe_allow_html=True)
            with tcols[8]:
                st.markdown(f"<div class='cxc-total-row'>{clp(sum_saldo)}</div>", unsafe_allow_html=True)

    # =====================================================================
    # VISUALIZAR
    # =====================================================================
    elif mode == "view":
        if st.button("← Volver al listado", key="cxc_back_view"):
            _cxc_back_list()
            st.rerun()
        cuenta = fetch_cuenta(db, int(st.session_state.cxc_focus_id or 0))
        if not cuenta:
            st.error("Documento no encontrado")
            _cxc_back_list()
        else:
            est_cls = cxc_estado_class(cuenta["estado"])
            badge = "ok" if est_cls == "pagado" else ("warn" if est_cls == "abonado" else "muted")
            st.markdown(
                f"""
                <div class="panel">
                  <div class="split-title" style="margin:0;">
                    <h3>{cuenta['documento']}</h3>
                    <span class="badge {badge}">{cxc_estado_label(cuenta['estado'])}</span>
                  </div>
                  <p style="margin:.45rem 0 0;color:var(--muted);">
                    {cuenta['razon_social'] or '—'} ·
                    {cxc_tipo_label(cuenta['tipo_doc'], cuenta['cotizacion_id'])} ·
                    {cuenta['concepto'] or 'Sin concepto'}
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total", clp(cuenta["monto"]))
            m2.metric("Abonos", clp(cuenta["abonado"]))
            m3.metric("Saldo", clp(cuenta["saldo"]))
            m4.metric("Vence", fmt_dmy(cuenta["fecha_vencimiento"]))

            abonos_df = pd.read_sql_query(
                """
                SELECT fecha AS Fecha, monto AS Monto, medio AS Medio, COALESCE(nota,'') AS Nota
                FROM abonos WHERE cuenta_id=? ORDER BY id DESC
                """,
                db,
                params=(cuenta["id"],),
            )
            st.markdown("#### Abonos")
            if abonos_df.empty:
                empty_state("Sin abonos registrados.")
            else:
                show = abonos_df.copy()
                show["Fecha"] = show["Fecha"].map(fmt_dmy)
                show["Monto"] = show["Monto"].map(clp)
                st.dataframe(show, use_container_width=True, hide_index=True)

            b1, b2, b3, b4 = st.columns(4)
            with b1:
                if st.button("Editar", key="cxc_view_edit", use_container_width=True):
                    st.session_state.cxc_mode = "edit"
                    st.session_state.cxc_focus_id = cuenta["id"]
                    st.rerun()
            with b2:
                if float(cuenta["saldo"] or 0) > 0:
                    if st.button("Registrar abono", type="primary", key="cxc_view_abono", use_container_width=True):
                        st.session_state.cxc_mode = "abono"
                        st.session_state.cxc_focus_id = cuenta["id"]
                        st.rerun()
            with b3:
                if st.button("Eliminar", key="cxc_view_del", use_container_width=True):
                    st.session_state.cxc_delete_id = cuenta["id"]
                    st.session_state.cxc_mode = "list"
                    st.rerun()
            with b4:
                if st.button("Volver", key="cxc_view_back2", use_container_width=True):
                    _cxc_back_list()
                    st.rerun()

    # =====================================================================
    # NUEVO / EDITAR
    # =====================================================================
    elif mode in ("new", "edit"):
        if st.button("← Volver al listado", key="cxc_back_form"):
            _cxc_back_list()
            st.rerun()

        edit_row = None
        if mode == "edit":
            edit_row = fetch_cuenta(db, int(st.session_state.cxc_focus_id or 0))
            if not edit_row:
                st.error("Documento no encontrado")
                _cxc_back_list()
                st.rerun()
            st.subheader(f"Modificar {edit_row['documento']}")
        else:
            st.subheader("Nuevo documento")

        if not clientes:
            empty_state("Crea clientes primero para emitir documentos.")
        else:
            cli_ids = [c["id"] for c in clientes]
            cli_default = 0
            if edit_row and edit_row["cliente_id"] in cli_ids:
                cli_default = cli_ids.index(edit_row["cliente_id"])
            tipos = ["EP", "FAC", "ND"]
            tipo_default = 0
            if edit_row and (edit_row["tipo_doc"] or "").upper() in tipos:
                tipo_default = tipos.index((edit_row["tipo_doc"] or "").upper())
            em_default = dparse(edit_row["fecha_emision"]) if edit_row else date.today()
            ve_default = (
                dparse(edit_row["fecha_vencimiento"])
                if edit_row
                else date.today() + timedelta(days=dias_credito)
            )
            with st.form("f_cxc"):
                cliente_id = st.selectbox(
                    "Cliente",
                    options=cli_ids,
                    index=cli_default,
                    format_func=lambda i: next(x["razon_social"] for x in clientes if x["id"] == i),
                )
                tipo = st.selectbox("Tipo documento", tipos, index=tipo_default)
                concepto = st.text_input(
                    "Concepto",
                    value=(edit_row["concepto"] or "Estado de pago") if edit_row else "Estado de pago",
                )
                monto = st.number_input(
                    "Monto",
                    min_value=1.0,
                    value=float(edit_row["monto"]) if edit_row else 1000000.0,
                    step=1000.0,
                )
                emision = st.date_input("Fecha emisión", value=em_default or date.today())
                venc = st.date_input("Fecha vencimiento", value=ve_default or date.today())
                guardar = st.form_submit_button(
                    "Guardar cambios" if mode == "edit" else "Guardar documento",
                    type="primary",
                )

            if guardar:
                if mode == "edit" and edit_row:
                    db.execute(
                        """
                        UPDATE cuentas
                        SET cliente_id=?, tipo_doc=?, concepto=?, fecha_emision=?,
                            fecha_vencimiento=?, monto=?
                        WHERE id=?
                        """,
                        (
                            cliente_id,
                            tipo,
                            concepto.strip() or None,
                            emision.isoformat(),
                            venc.isoformat(),
                            float(monto),
                            edit_row["id"],
                        ),
                    )
                    recalc_cuenta(db, int(edit_row["id"]))
                    db.commit()
                    st.success(f"{edit_row['documento']} actualizado")
                    st.session_state.cxc_mode = "view"
                    st.session_state.cxc_focus_id = edit_row["id"]
                    st.rerun()
                else:
                    pref = tipo if tipo in ("EP", "FAC", "ND") else "EP"
                    doc = next_code(db, "cuentas", "documento", pref)
                    cur = db.cursor()
                    cur.execute(
                        """
                        INSERT INTO cuentas
                        (documento, cliente_id, tipo_doc, concepto, fecha_emision,
                         fecha_vencimiento, monto, abonado, saldo, estado)
                        VALUES (?,?,?,?,?,?,?,0,?, 'pendiente')
                        """,
                        (
                            doc,
                            cliente_id,
                            tipo,
                            concepto.strip() or None,
                            emision.isoformat(),
                            venc.isoformat(),
                            float(monto),
                            float(monto),
                        ),
                    )
                    new_id = cur.lastrowid
                    db.commit()
                    st.success(f"Documento {doc} creado")
                    st.session_state.cxc_mode = "view"
                    st.session_state.cxc_focus_id = new_id
                    st.rerun()

    # =====================================================================
    # REGISTRAR ABONO
    # =====================================================================
    elif mode == "abono":
        if st.button("← Volver", key="cxc_back_abono"):
            st.session_state.cxc_mode = "view"
            st.rerun()
        cuenta = fetch_cuenta(db, int(st.session_state.cxc_focus_id or 0))
        if not cuenta:
            st.error("Documento no encontrado")
            _cxc_back_list()
        elif float(cuenta["saldo"] or 0) <= 0:
            alert_line("ok", "Este documento ya está pagado.")
            if st.button("Volver al documento"):
                st.session_state.cxc_mode = "view"
                st.rerun()
        else:
            st.subheader(f"Abono · {cuenta['documento']}")
            st.caption(
                f"{cuenta['razon_social'] or '—'} · Saldo {clp(cuenta['saldo'])}"
            )
            with st.form("f_abono_cxc"):
                monto = st.number_input(
                    "Monto abono",
                    min_value=1.0,
                    max_value=float(cuenta["saldo"]),
                    value=float(cuenta["saldo"]),
                    step=1000.0,
                )
                medio = st.selectbox(
                    "Medio",
                    ["transferencia", "cheque", "efectivo", "tarjeta", "otro"],
                )
                nota = st.text_input("Nota")
                if st.form_submit_button("Registrar abono", type="primary"):
                    db.execute(
                        "INSERT INTO abonos (cuenta_id, fecha, monto, medio, nota) VALUES (?,?,?,?,?)",
                        (
                            cuenta["id"],
                            date.today().isoformat(),
                            float(monto),
                            medio,
                            nota.strip() or None,
                        ),
                    )
                    recalc_cuenta(db, int(cuenta["id"]))
                    db.commit()
                    st.success("Abono registrado")
                    st.session_state.cxc_mode = "view"
                    st.rerun()

# ===========================================================================
# ADMINISTRACIÓN
# ===========================================================================
else:
    page_header("Administración", "Empresa, parámetros y gestión de usuarios del sistema.")
    tab_emp, tab_par, tab_usuarios = st.tabs(["Mi empresa", "Parámetros", "Usuarios"])

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

    with tab_usuarios:
        st.markdown(
            '<div class="split-title"><h3>Usuarios</h3>'
            "<span>Gestión de accesos, claves y tipo de usuario</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Sesión actual: {auth_user} · {auth_tipo}")

        users_df = pd.read_sql_query(
            """
            SELECT id AS ID,
                   usuario AS Usuario,
                   COALESCE(nombre,'') AS Nombre,
                   COALESCE(tipo,'Administrador') AS Tipo,
                   CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS Estado
            FROM usuarios
            ORDER BY Tipo, usuario
            """,
            db,
        )
        if users_df.empty:
            empty_state("No hay usuarios registrados.")
        else:
            st.dataframe(users_df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        st.markdown("#### Mi clave")
        with st.form("f_clave_propia"):
            actual = st.text_input("Clave actual", type="password")
            nueva = st.text_input("Nueva clave", type="password")
            nueva2 = st.text_input("Repetir nueva clave", type="password")
            if st.form_submit_button("Cambiar mi clave", type="primary"):
                if not check_login(auth_user, actual):
                    st.error("La clave actual no es correcta")
                elif len(nueva.strip()) < 4:
                    st.error("La nueva clave debe tener al menos 4 caracteres")
                elif nueva != nueva2:
                    st.error("Las claves nuevas no coinciden")
                else:
                    salt, digest = hash_password(nueva.strip())
                    db.execute(
                        "UPDATE usuarios SET salt=?, clave_hash=? WHERE lower(usuario)=lower(?)",
                        (salt, digest, auth_user),
                    )
                    db.commit()
                    st.success("Clave actualizada")

        if not is_admin_user():
            alert_line(
                "warn",
                "Solo un usuario <strong>Administrador</strong> puede crear o editar otros usuarios.",
            )
        else:
            tab_nuevo, tab_editar = st.tabs(["Nuevo usuario", "Editar usuario"])

            with tab_nuevo:
                with st.form("f_user_new"):
                    u_nuevo = st.text_input("Usuario / email")
                    n_nuevo = st.text_input("Nombre")
                    t_nuevo = st.selectbox("Tipo de usuario", TIPOS_USUARIO, index=0)
                    c_nuevo = st.text_input("Clave inicial", type="password")
                    c_nuevo2 = st.text_input("Repetir clave", type="password")
                    if st.form_submit_button("Crear usuario", type="primary"):
                        if not u_nuevo.strip():
                            st.error("Ingrese un usuario")
                        elif len(c_nuevo.strip()) < 4:
                            st.error("La clave debe tener al menos 4 caracteres")
                        elif c_nuevo != c_nuevo2:
                            st.error("Las claves no coinciden")
                        else:
                            try:
                                salt, digest = hash_password(c_nuevo.strip())
                                db.execute(
                                    """
                                    INSERT INTO usuarios (usuario, salt, clave_hash, nombre, tipo, activo)
                                    VALUES (?,?,?,?,?,1)
                                    """,
                                    (
                                        u_nuevo.strip(),
                                        salt,
                                        digest,
                                        n_nuevo.strip() or None,
                                        t_nuevo,
                                    ),
                                )
                                db.commit()
                                st.success(f"Usuario {u_nuevo.strip()} creado")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Ese usuario ya existe")

            with tab_editar:
                rows = db.execute(
                    """
                    SELECT id, usuario, nombre, tipo, activo
                    FROM usuarios
                    ORDER BY usuario
                    """
                ).fetchall()
                if not rows:
                    empty_state("No hay usuarios para editar.")
                else:
                    sel_id = st.selectbox(
                        "Usuario a editar",
                        options=[r["id"] for r in rows],
                        format_func=lambda i: next(
                            f"{r['usuario']} · {r['tipo'] or 'Administrador'} · "
                            f"{'activo' if r['activo'] else 'inactivo'}"
                            for r in rows
                            if r["id"] == i
                        ),
                        key="edit_user_sel",
                    )
                    row = next(r for r in rows if r["id"] == sel_id)
                    tipo_actual = row["tipo"] if row["tipo"] in TIPOS_USUARIO else "Administrador"
                    with st.form("f_user_edit"):
                        n_edit = st.text_input("Nombre", value=row["nombre"] or "")
                        t_edit = st.selectbox(
                            "Tipo de usuario",
                            TIPOS_USUARIO,
                            index=TIPOS_USUARIO.index(tipo_actual),
                        )
                        activo_edit = st.checkbox("Activo", value=bool(row["activo"]))
                        reset_clave = st.text_input(
                            "Nueva clave (opcional)",
                            type="password",
                            help="Déjela vacía para no cambiar la clave",
                        )
                        reset_clave2 = st.text_input("Repetir nueva clave", type="password")
                        if st.form_submit_button("Guardar cambios", type="primary"):
                            if row["usuario"] == auth_user and not activo_edit:
                                st.error("No puedes desactivarte a ti mismo")
                            elif reset_clave and len(reset_clave.strip()) < 4:
                                st.error("La nueva clave debe tener al menos 4 caracteres")
                            elif reset_clave and reset_clave != reset_clave2:
                                st.error("Las claves nuevas no coinciden")
                            else:
                                db.execute(
                                    """
                                    UPDATE usuarios
                                    SET nombre=?, tipo=?, activo=?
                                    WHERE id=?
                                    """,
                                    (
                                        n_edit.strip() or None,
                                        t_edit,
                                        int(activo_edit),
                                        sel_id,
                                    ),
                                )
                                if reset_clave.strip():
                                    salt, digest = hash_password(reset_clave.strip())
                                    db.execute(
                                        "UPDATE usuarios SET salt=?, clave_hash=? WHERE id=?",
                                        (salt, digest, sel_id),
                                    )
                                db.commit()
                                if row["usuario"] == auth_user:
                                    st.session_state.auth_tipo = t_edit
                                    st.session_state.auth_nombre = n_edit.strip() or auth_user
                                st.success("Usuario actualizado")
                                st.rerun()

render_footer()
db.close()
