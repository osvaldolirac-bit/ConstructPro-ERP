"""Núcleo Río Maipo Web: SQLite, auth, formatos y PDF (misma BD que Streamlit)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "riomaipo_erp.db"
# En VPS se puede apuntar con env RIOMAIPO_DB
import os

DB_PATH = Path(os.getenv("RIOMAIPO_DB", str(DB_PATH)))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STATIC_DIR = BASE_DIR / "static"
LOGO_RIOMAIPO = STATIC_DIR / "logo_riomaipo.png"
LOGO_ERP = STATIC_DIR / "logo_erpmaster.png"

DEFAULT_ACCESO = "osvaldolira@constructorariomaipo.cl"
DEFAULT_CLAVE = "9083"
TIPOS_USUARIO = ["Administrador", "Operador", "Consulta"]
COT_PDF_ROWS = 24

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


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


def _ensure_columns(c: sqlite3.Connection, table: str, columns: list[tuple[str, str]]) -> None:
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in columns:
        if name not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


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
            clave TEXT PRIMARY KEY, nombre TEXT, valor TEXT, unidad TEXT
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE, razon_social TEXT NOT NULL,
            contacto TEXT, telefono TEXT, email TEXT,
            direccion TEXT, comuna TEXT, activo INTEGER DEFAULT 1, creado_en TEXT
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE, nombre TEXT NOT NULL,
            unidad TEXT DEFAULT 'un', precio REAL DEFAULT 0, activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE, cliente_id INTEGER,
            asunto TEXT, proyecto TEXT, estado TEXT DEFAULT 'borrador',
            fecha TEXT, validez_dias INTEGER DEFAULT 30,
            version TEXT DEFAULT '1', titulo TEXT,
            gg_pct REAL DEFAULT 5, utilidad_pct REAL DEFAULT 15,
            gg_monto REAL DEFAULT 0, utilidad_monto REAL DEFAULT 0, valor_neto REAL DEFAULT 0,
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
            facturado INTEGER DEFAULT 0, num_factura TEXT,
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
            salt TEXT NOT NULL, clave_hash TEXT NOT NULL,
            nombre TEXT, tipo TEXT NOT NULL DEFAULT 'Administrador',
            activo INTEGER DEFAULT 1
        );
        """
    )
    _ensure_columns(c, "usuarios", [("tipo", "TEXT NOT NULL DEFAULT 'Administrador'")])
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
    _ensure_columns(c, "cotizacion_items", [("obs", "TEXT"), ("orden", "INTEGER DEFAULT 0")])
    _ensure_columns(c, "cuentas", [("facturado", "INTEGER DEFAULT 0"), ("num_factura", "TEXT")])

    if c.execute("SELECT COUNT(*) FROM empresa").fetchone()[0] == 0:
        c.execute(
            """
            INSERT INTO empresa (id, rut, razon_social, telefono, email, direccion, region, pais)
            VALUES (1, '76.073.876-K', 'Constructora Rio Maipo S.A.', '56990798992',
                    'osvaldolira@constructorariomaipo.cl', 'Parcela El Sauce lote 4, Paine',
                    'Metropolitana', 'Chile')
            """
        )
    for clave, nombre, valor, unidad in [
        ("iva", "IVA", "19", "%"),
        ("validez_cotizacion", "Validez cotización", "30", "días"),
        ("gg_pct", "Gastos generales", "5", "%"),
        ("utilidad_pct", "Utilidad", "15", "%"),
        ("dias_credito", "Días crédito CxC", "30", "días"),
    ]:
        c.execute(
            """
            INSERT INTO parametros (clave, nombre, valor, unidad) VALUES (?,?,?,?)
            ON CONFLICT(clave) DO NOTHING
            """,
            (clave, nombre, valor, unidad),
        )

    # Usuario por defecto
    salt, digest = hash_password(DEFAULT_CLAVE)
    row = c.execute(
        "SELECT id FROM usuarios WHERE lower(usuario)=lower(?)", (DEFAULT_ACCESO,)
    ).fetchone()
    if not row:
        c.execute(
            """
            INSERT INTO usuarios (usuario, salt, clave_hash, nombre, tipo, activo)
            VALUES (?,?,?,?,?,1)
            """,
            (DEFAULT_ACCESO, salt, digest, "Osvaldo Lira", "Administrador"),
        )
    c.commit()
    c.close()


def clp(v) -> str:
    try:
        return f"${int(round(float(v or 0))):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def fmt_dmy(s) -> str:
    if not s:
        return "—"
    try:
        return date.fromisoformat(str(s)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(s)


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


def get_user_if_valid(usuario: str, clave: str):
    c = conn()
    row = c.execute(
        """
        SELECT id, usuario, salt, clave_hash, nombre, tipo, activo
        FROM usuarios WHERE lower(usuario)=lower(?) AND activo=1
        """,
        (usuario.strip(),),
    ).fetchone()
    c.close()
    if not row:
        return None
    if not verify_password(clave, row["salt"], row["clave_hash"]):
        return None
    return dict(row)


def calc_cotizacion_totales(subtotal: float, gg_pct: float, utilidad_pct: float, iva_pct: float) -> dict:
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


def estado_label_cot(estado: str | None) -> str:
    return {
        "borrador": "Ingresada",
        "enviada": "Ingresada",
        "aprobada": "Aprobada",
        "rechazada": "Rechazada",
    }.get(estado or "", estado or "—")


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
    if FPDF is None:
        raise RuntimeError("FPDF no está instalado")
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    logo = LOGO_RIOMAIPO if LOGO_RIOMAIPO.exists() else LOGO_ERP
    if logo.exists():
        pdf.image(str(logo), x=128, y=4, w=40)
    else:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, _pdf_txt("RIO MAIPO Constructora"), align="C", ln=1)

    title = _pdf_txt(cotizacion_titulo_pdf(cot))
    pdf.set_xy(18, 28)
    pdf.set_fill_color(210, 210, 210)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(261, 6, title, border=1, align="C", fill=True)

    headers = ["ITEM", "ESPECIFICACIÓN", "OBS", "UND", "CANTIDAD", "VALOR", "TOTAL"]
    widths = [14, 74, 58, 16, 24, 37, 38]
    x0, row_h = 18, 4.0
    pdf.set_xy(x0, 36)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, widths):
        pdf.cell(w, row_h, h, border=1, align="C", fill=True)
    pdf.ln(row_h)

    subtotal = float(cot["subtotal"] or 0) or sum(float(it["total"] or 0) for it in items)
    pdf.set_x(x0)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(widths[0], row_h, "1.0", border=1, align="C")
    for w in widths[1:-1]:
        pdf.cell(w, row_h, "", border=1)
    pdf.cell(widths[-1], row_h, _pdf_txt(f"$ {fmt_clp_plain(subtotal)}"), border=1, align="R")
    pdf.ln(row_h)

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
            pdf.cell(widths[0], row_h, code, border=1, align="C")
            pdf.cell(widths[1], row_h, _pdf_txt(it["descripcion"])[:46], border=1)
            pdf.cell(widths[2], row_h, _pdf_txt(it["obs"] if "obs" in it.keys() else "")[:34], border=1)
            pdf.cell(widths[3], row_h, _pdf_txt(it["unidad"] or ""), border=1, align="C")
            pdf.cell(widths[4], row_h, fmt_cant_pdf(it["cantidad"]), border=1, align="R")
            pdf.cell(widths[5], row_h, _pdf_txt(f"$ {fmt_clp_plain(it['precio_unitario'])}"), border=1, align="R")
            pdf.cell(widths[6], row_h, _pdf_txt(f"$ {fmt_clp_plain(it['total'])}"), border=1, align="R")
        pdf.ln(row_h)

    gg_pct = float(cot["gg_pct"] if "gg_pct" in cot.keys() and cot["gg_pct"] is not None else 5)
    util_pct = float(cot["utilidad_pct"] if "utilidad_pct" in cot.keys() and cot["utilidad_pct"] is not None else 15)
    gg = float(cot["gg_monto"] if "gg_monto" in cot.keys() and cot["gg_monto"] is not None else round(subtotal * gg_pct / 100))
    util = float(cot["utilidad_monto"] if "utilidad_monto" in cot.keys() and cot["utilidad_monto"] is not None else round(subtotal * util_pct / 100))
    neto = float(cot["valor_neto"] if "valor_neto" in cot.keys() and cot["valor_neto"] is not None else subtotal + gg + util)
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
        pdf.cell(label_w, row_h, _pdf_txt(lab), border=1)
        pdf.cell(val_w, row_h, _pdf_txt(val), border=1, align="R")

    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


def _pdf_header_portrait(pdf, empresa_row, subtitle: str) -> None:
    logo = LOGO_RIOMAIPO if LOGO_RIOMAIPO.exists() else LOGO_ERP
    if logo.exists():
        pdf.image(str(logo), x=12, y=8, w=28)
    pdf.set_xy(45, 10)
    pdf.set_font("Helvetica", "B", 13)
    razon = ""
    if empresa_row and "razon_social" in empresa_row.keys() and empresa_row["razon_social"]:
        razon = empresa_row["razon_social"]
    pdf.cell(0, 6, _pdf_txt(razon or "RIO MAIPO Constructora"), ln=1)
    pdf.set_x(45)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    bits = []
    if empresa_row:
        if empresa_row["rut"]:
            bits.append(f"RUT {empresa_row['rut']}")
        if empresa_row["telefono"]:
            bits.append(str(empresa_row["telefono"]))
        if empresa_row["email"]:
            bits.append(str(empresa_row["email"]))
    pdf.cell(0, 5, _pdf_txt(" · ".join(bits)), ln=1)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(28)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_txt(subtitle), ln=1)
    pdf.ln(2)


def cuenta_pdf_bytes(cuenta, abonos, empresa_row) -> bytes:
    """PDF vertical de un documento CxC con historial de abonos."""
    if FPDF is None:
        raise RuntimeError("FPDF no está instalado")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    doc = cuenta["documento"] if "documento" in cuenta.keys() else "CxC"
    _pdf_header_portrait(pdf, empresa_row, f"Documento {doc}")

    pdf.set_font("Helvetica", "", 10)
    lines = [
        ("Cliente", cuenta["razon_social"] if "razon_social" in cuenta.keys() else "—"),
        ("RUT cliente", cuenta["cliente_rut"] if "cliente_rut" in cuenta.keys() else "—"),
        (
            "Tipo",
            cuenta["tipo"]
            if "tipo" in cuenta.keys() and cuenta["tipo"]
            else (cuenta["tipo_doc"] if "tipo_doc" in cuenta.keys() else "—"),
        ),
        ("Nº Factura", cuenta["num_factura"] if "num_factura" in cuenta.keys() and cuenta["num_factura"] else "—"),
        ("Emisión", fmt_dmy(cuenta["fecha_emision"] if "fecha_emision" in cuenta.keys() else None)),
        ("Vencimiento", fmt_dmy(cuenta["fecha_vencimiento"] if "fecha_vencimiento" in cuenta.keys() else None)),
        ("Estado", cxc_estado_label(cuenta["estado"] if "estado" in cuenta.keys() else None)),
        ("Concepto", cuenta["concepto"] if "concepto" in cuenta.keys() and cuenta["concepto"] else "—"),
    ]
    for lab, val in lines:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, _pdf_txt(lab), border=0)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 6, _pdf_txt(val), border=0)

    pdf.ln(3)
    pdf.set_fill_color(238, 243, 249)
    pdf.set_font("Helvetica", "B", 9)
    for lab, val in [
        ("Total", f"$ {fmt_clp_plain(cuenta['monto'] if 'monto' in cuenta.keys() else 0)}"),
        ("Abonos", f"$ {fmt_clp_plain(cuenta['abonado'] if 'abonado' in cuenta.keys() else 0)}"),
        ("Saldo", f"$ {fmt_clp_plain(cuenta['saldo'] if 'saldo' in cuenta.keys() else 0)}"),
    ]:
        pdf.cell(40, 7, _pdf_txt(lab), border=1, fill=True)
        pdf.cell(50, 7, _pdf_txt(val), border=1, align="R", ln=1)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_txt("Abonos registrados"), ln=1)
    headers = ["Fecha", "Monto", "Medio", "Nota"]
    widths = [28, 35, 35, 92]
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    if not abonos:
        pdf.cell(sum(widths), 6, _pdf_txt("Sin abonos"), border=1, ln=1)
    else:
        for a in abonos:
            pdf.cell(widths[0], 6, _pdf_txt(fmt_dmy(a["fecha"])), border=1)
            pdf.cell(widths[1], 6, _pdf_txt(f"$ {fmt_clp_plain(a['monto'])}"), border=1, align="R")
            pdf.cell(widths[2], 6, _pdf_txt(a["medio"] if "medio" in a.keys() else ""), border=1)
            nota = a["nota"] if "nota" in a.keys() else ""
            pdf.cell(widths[3], 6, _pdf_txt(nota)[:48], border=1, ln=1)

    pdf.ln(8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, _pdf_txt(f"Generado {date.today().strftime('%d/%m/%Y')} · ERP Master · Río Maipo"), ln=1)
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)


def estado_cuenta_pdf_bytes(cliente, cuentas, abonos, cots, deuda, empresa_row) -> bytes:
    """PDF Vista 360 / estado de cuenta del cliente."""
    if FPDF is None:
        raise RuntimeError("FPDF no está instalado")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    nombre = cliente["razon_social"] if cliente else "Cliente"
    _pdf_header_portrait(pdf, empresa_row, "Estado de cuenta")

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, _pdf_txt(nombre), ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(
        0,
        5,
        _pdf_txt(
            f"RUT {cliente['rut'] if cliente and cliente['rut'] else '—'} · "
            f"{cliente['telefono'] if cliente and cliente['telefono'] else '—'} · "
            f"{cliente['email'] if cliente and cliente['email'] else '—'}"
        ),
        ln=1,
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    if float(deuda or 0) > 0:
        pdf.set_fill_color(255, 235, 235)
    else:
        pdf.set_fill_color(230, 245, 235)
    pdf.cell(60, 8, _pdf_txt("Deuda abierta"), border=1, fill=True)
    pdf.cell(50, 8, _pdf_txt(f"$ {fmt_clp_plain(deuda)}"), border=1, align="R", fill=True, ln=1)

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_txt("Cuentas por cobrar"), ln=1)
    widths = [32, 28, 28, 32, 32, 28]
    headers = ["Documento", "Factura", "Vence", "Total", "Saldo", "Estado"]
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    if not cuentas:
        pdf.cell(sum(widths), 6, _pdf_txt("Sin documentos"), border=1, ln=1)
    else:
        for x in cuentas:
            pdf.cell(widths[0], 6, _pdf_txt(x["documento"]), border=1)
            pdf.cell(widths[1], 6, _pdf_txt(x["num_factura"] if "num_factura" in x.keys() and x["num_factura"] else "—"), border=1)
            pdf.cell(widths[2], 6, _pdf_txt(fmt_dmy(x["fecha_vencimiento"] if "fecha_vencimiento" in x.keys() else None)), border=1)
            pdf.cell(widths[3], 6, _pdf_txt(f"$ {fmt_clp_plain(x['monto'])}"), border=1, align="R")
            pdf.cell(widths[4], 6, _pdf_txt(f"$ {fmt_clp_plain(x['saldo'])}"), border=1, align="R")
            pdf.cell(widths[5], 6, _pdf_txt(cxc_estado_label(x["estado"])), border=1, ln=1)

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_txt("Últimos abonos"), ln=1)
    aw = [28, 40, 35, 77]
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(["Fecha", "Documento", "Monto", "Medio"], aw):
        pdf.cell(w, 6, h, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    if not abonos:
        pdf.cell(sum(aw), 6, _pdf_txt("Sin abonos"), border=1, ln=1)
    else:
        for a in abonos:
            pdf.cell(aw[0], 6, _pdf_txt(fmt_dmy(a["fecha"])), border=1)
            pdf.cell(aw[1], 6, _pdf_txt(a["documento"] if "documento" in a.keys() else ""), border=1)
            pdf.cell(aw[2], 6, _pdf_txt(f"$ {fmt_clp_plain(a['monto'])}"), border=1, align="R")
            pdf.cell(aw[3], 6, _pdf_txt(a["medio"] if "medio" in a.keys() else ""), border=1, ln=1)

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_txt("Cotizaciones"), ln=1)
    cw = [30, 28, 70, 28, 24]
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(["Folio", "Fecha", "Título", "Estado", "Total"], cw):
        pdf.cell(w, 6, h, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    if not cots:
        pdf.cell(sum(cw), 6, _pdf_txt("Sin cotizaciones"), border=1, ln=1)
    else:
        for c in cots:
            pdf.cell(cw[0], 6, _pdf_txt(c["folio"]), border=1)
            pdf.cell(cw[1], 6, _pdf_txt(fmt_dmy(c["fecha"] if "fecha" in c.keys() else None)), border=1)
            titulo = c["titulo"] if "titulo" in c.keys() else ""
            pdf.cell(cw[2], 6, _pdf_txt(titulo)[:40], border=1)
            pdf.cell(cw[3], 6, _pdf_txt(estado_label_cot(c["estado"] if "estado" in c.keys() else None)), border=1)
            pdf.cell(cw[4], 6, _pdf_txt(f"$ {fmt_clp_plain(c['total'] if 'total' in c.keys() else 0)}"), border=1, align="R", ln=1)

    pdf.ln(8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, _pdf_txt(f"Generado {date.today().strftime('%d/%m/%Y')} · ERP Master · Río Maipo"), ln=1)
    raw = pdf.output(dest="S")
    return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)
