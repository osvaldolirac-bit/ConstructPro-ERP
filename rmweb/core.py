"""Núcleo Río Maipo Web: SQLite, auth, formatos y PDF (misma BD que Streamlit)."""

from __future__ import annotations

import hashlib
import hmac
import re
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
# Logos pueden estar en /static del proyecto o en rmweb/static
LOGO_RIOMAIPO = next(
    (
        p
        for p in (
            STATIC_DIR / "logo_riomaipo.png",
            Path(__file__).resolve().parent / "static" / "logo_riomaipo.png",
        )
        if p.exists()
    ),
    STATIC_DIR / "logo_riomaipo.png",
)
LOGO_ERP = next(
    (
        p
        for p in (
            STATIC_DIR / "logo_erpmaster.png",
            Path(__file__).resolve().parent / "static" / "logo_erpmaster.png",
        )
        if p.exists()
    ),
    STATIC_DIR / "logo_erpmaster.png",
)

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
    scrub_import_labels(c)
    sync_cuenta_cotizacion_links(c)

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


def ensure_cxc_from_cotizacion(c: sqlite3.Connection, cot_id: int) -> str | None:
    """
    Si la cotización está aprobada y aún no tiene CxC, crea el documento.
    Retorna el código del documento creado, o None si no correspondía crear.
    """
    cot = c.execute(
        """
        SELECT id, folio, cliente_id, estado, total, cxc_id, asunto, titulo, proyecto
        FROM cotizaciones WHERE id=?
        """,
        (cot_id,),
    ).fetchone()
    if not cot:
        return None
    if (cot["estado"] or "") != "aprobada":
        return None
    if cot["cxc_id"]:
        return None
    if not cot["cliente_id"]:
        return None

    dias = int(param(c, "dias_credito", 30))
    doc = next_code(c, "cuentas", "documento", "EP")
    concepto = f"Desde cotización {cot['folio']}"
    titulo = (cot["titulo"] or cot["asunto"] or cot["proyecto"] or "").strip()
    if titulo:
        concepto = f"{concepto} · {titulo[:80]}"
    monto = float(cot["total"] or 0)
    cur = c.cursor()
    cur.execute(
        """
        INSERT INTO cuentas
        (documento, cliente_id, cotizacion_id, tipo_doc, concepto,
         fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado, facturado)
        VALUES (?,?,?,?,?,?,?,?,0,?, 'pendiente', 0)
        """,
        (
            doc,
            cot["cliente_id"],
            cot["id"],
            "EP",
            concepto,
            date.today().isoformat(),
            (date.today() + timedelta(days=dias)).isoformat(),
            monto,
            monto,
        ),
    )
    cxc_id = cur.lastrowid
    cur.execute("UPDATE cotizaciones SET cxc_id=? WHERE id=?", (cxc_id, cot["id"]))
    return doc


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
    s = str(value or "")
    # Evita "?" por guiones tipográficos / bullets fuera de latin-1
    s = (
        s.replace("—", "-")
        .replace("–", "-")
        .replace("•", "-")
        .replace("·", "|")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )
    return s.encode("latin-1", "replace").decode("latin-1")


def scrub_import_labels(c: sqlite3.Connection) -> dict:
    """Elimina textos 'importado' / 'SOLUERP' de conceptos, notas y medios."""
    stats = {"cuentas": 0, "abonos_nota": 0, "abonos_medio": 0, "cotizaciones": 0}

    # Cuentas: "Importado SOLUERP 254" → vacío (el Nº queda en num_factura)
    cur = c.execute(
        """
        UPDATE cuentas
        SET concepto=NULL
        WHERE concepto IS NOT NULL
          AND (
            lower(concepto) LIKE '%importad%'
            OR lower(concepto) LIKE '%soluerp%'
          )
        """
    )
    stats["cuentas"] = cur.rowcount if cur.rowcount is not None else 0

    cur = c.execute(
        """
        UPDATE abonos
        SET nota=NULL
        WHERE nota IS NOT NULL
          AND (
            lower(nota) LIKE '%importad%'
            OR lower(nota) LIKE '%soluerp%'
          )
        """
    )
    stats["abonos_nota"] = cur.rowcount if cur.rowcount is not None else 0

    cur = c.execute(
        """
        UPDATE abonos
        SET medio='Transferencia'
        WHERE medio IS NOT NULL
          AND (
            lower(medio) LIKE '%importad%'
            OR lower(medio) LIKE '%soluerp%'
          )
        """
    )
    stats["abonos_medio"] = cur.rowcount if cur.rowcount is not None else 0

    cur = c.execute(
        """
        UPDATE cotizaciones
        SET notas=NULL
        WHERE notas IS NOT NULL
          AND (
            lower(notas) LIKE '%importad%'
            OR lower(notas) LIKE '%soluerp%'
          )
        """
    )
    stats["cotizaciones"] = cur.rowcount if cur.rowcount is not None else 0

    c.commit()
    return stats


def extract_num_factura(*texts) -> str | None:
    """Extrae Nº de factura exacto desde documento/asunto/concepto."""
    blob = " ".join(str(t or "") for t in texts).strip()
    if not blob:
        return None
    if re.fullmatch(r"\d+", blob):
        return blob
    patterns = [
        r"\bfactura\s+(\d+)\b",
        r"\bfact\.?\s+(\d+)\b",
        r"\bsoluerp\s+(\d+)\b",
        r"\bFAC[- ]?(\d+)\b",
        r"^(?:FAC|FA|EP|ND)[- ]?(\d+)$",
    ]
    for pat in patterns:
        m = re.search(pat, blob, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1)
    return None


def sync_cuenta_cotizacion_links(c: sqlite3.Connection) -> int:
    """Rellena num_factura y enlaza cuentas <-> cotizaciones por Nº de factura."""
    cuentas = c.execute(
        """
        SELECT id, documento, concepto, num_factura, cotizacion_id, cliente_id
        FROM cuentas
        """
    ).fetchall()
    for cu in cuentas:
        num = (cu["num_factura"] or "").strip()
        if not num:
            num = extract_num_factura(cu["documento"], cu["concepto"]) or ""
            if num:
                c.execute(
                    "UPDATE cuentas SET num_factura=?, facturado=1 WHERE id=?",
                    (num, cu["id"]),
                )

    cuentas = c.execute(
        """
        SELECT id, documento, concepto, num_factura, cotizacion_id, cliente_id
        FROM cuentas
        """
    ).fetchall()
    cots = c.execute(
        """
        SELECT id, folio, asunto, titulo, proyecto, cxc_id, cliente_id
        FROM cotizaciones
        """
    ).fetchall()

    cot_by_fac: dict[tuple[int, str], sqlite3.Row] = {}
    for cot in cots:
        num = extract_num_factura(cot["asunto"], cot["titulo"], cot["proyecto"])
        if not num or not cot["cliente_id"]:
            continue
        key = (int(cot["cliente_id"]), str(num))
        # Si hay varias, preferir la ya enlazada a esta factura / la más antigua
        if key not in cot_by_fac:
            cot_by_fac[key] = cot

    linked = 0

    def _link(cu_id: int, cot_id: int, num: str | None) -> None:
        nonlocal linked
        if num:
            c.execute(
                """
                UPDATE cuentas
                SET cotizacion_id=?, num_factura=?, facturado=1
                WHERE id=?
                """,
                (cot_id, num, cu_id),
            )
        else:
            c.execute("UPDATE cuentas SET cotizacion_id=? WHERE id=?", (cot_id, cu_id))
        c.execute("UPDATE cotizaciones SET cxc_id=? WHERE id=?", (cu_id, cot_id))
        linked += 1

    for cu in cuentas:
        if not cu["cliente_id"]:
            continue
        num = (cu["num_factura"] or "").strip() or extract_num_factura(cu["documento"], cu["concepto"]) or ""
        if not num:
            continue
        cot = cot_by_fac.get((int(cu["cliente_id"]), str(num)))
        if not cot:
            continue
        if cu["cotizacion_id"] and int(cu["cotizacion_id"]) != int(cot["id"]):
            continue
        if cot["cxc_id"] and int(cot["cxc_id"]) != int(cu["id"]):
            continue
        _link(int(cu["id"]), int(cot["id"]), num)

    # Segundo paso: cuentas y cotizaciones aún libres, mismo cliente y monto,
    # emparejadas por fecha (útil para arriendos mensuales sin "factura N" en el título).
    free_cuentas = c.execute(
        """
        SELECT id, cliente_id, monto, fecha_emision, fecha_vencimiento, num_factura, documento, concepto
        FROM cuentas
        WHERE cotizacion_id IS NULL AND cliente_id IS NOT NULL
        ORDER BY COALESCE(fecha_emision, fecha_vencimiento, ''), id
        """
    ).fetchall()
    free_cots = c.execute(
        """
        SELECT id, cliente_id, total, fecha, asunto, titulo, proyecto
        FROM cotizaciones
        WHERE cxc_id IS NULL AND cliente_id IS NOT NULL
        ORDER BY COALESCE(fecha, ''), id
        """
    ).fetchall()
    used_cots: set[int] = set()
    for cu in free_cuentas:
        cid = int(cu["cliente_id"])
        monto = round(float(cu["monto"] or 0), 2)
        match = None
        for cot in free_cots:
            if int(cot["id"]) in used_cots:
                continue
            if int(cot["cliente_id"]) != cid:
                continue
            if round(float(cot["total"] or 0), 2) != monto:
                continue
            # No reutilizar cotizaciones que ya tienen Nº factura distinto
            cot_fac = extract_num_factura(cot["asunto"], cot["titulo"], cot["proyecto"])
            cu_fac = (cu["num_factura"] or "").strip() or extract_num_factura(cu["documento"], cu["concepto"]) or ""
            if cot_fac and cu_fac and str(cot_fac) != str(cu_fac):
                continue
            match = cot
            break
        if not match:
            continue
        used_cots.add(int(match["id"]))
        num = (cu["num_factura"] or "").strip() or extract_num_factura(cu["documento"], cu["concepto"]) or ""
        _link(int(cu["id"]), int(match["id"]), num or None)

    c.commit()
    return linked


def cuenta_doc_factura_display(cuenta) -> tuple[str, str]:
    """Devuelve (documento visible, Nº factura). Documento = COT si está enlazada."""
    keys = set(cuenta.keys()) if hasattr(cuenta, "keys") else set(cuenta)
    folio = str(cuenta["cot_folio"]).strip() if "cot_folio" in keys and cuenta["cot_folio"] else ""
    doc = str(cuenta["documento"] or "").strip() if "documento" in keys else ""
    concepto = cuenta["concepto"] if "concepto" in keys else ""
    num = ""
    if "num_factura" in keys and cuenta["num_factura"]:
        num = str(cuenta["num_factura"]).strip()
    if not num:
        num = extract_num_factura(doc, concepto) or ""
    return (folio or doc or "-"), (num or "-")


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
    version = version.lstrip("Vv") or "1"
    titulo = ""
    for key in ("titulo", "asunto", "proyecto"):
        if key in cot.keys() and cot[key]:
            titulo = str(cot[key]).strip()
            if titulo:
                break
    if not titulo and "razon_social" in cot.keys() and cot["razon_social"]:
        titulo = str(cot["razon_social"]).strip()
    if not titulo:
        titulo = "COTIZACION"
    return f"V{version} COTIZACIÓN {titulo}".upper()


def _pct_from_text(text: str | None, default: float | None = None) -> float | None:
    import re

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text or "")
    if not m:
        return default
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return default


def _is_gg_line(desc: str | None) -> bool:
    import re

    d = (desc or "").strip().lower()
    if not d:
        return False
    return bool(re.match(r"^(gg\b|g\.?\s*g\.?\b|gastos?\s+generales\b)", d))


def _is_util_line(desc: str | None) -> bool:
    import re

    d = (desc or "").strip().lower()
    if not d:
        return False
    return bool(re.match(r"^(utilidad(es)?\b|util\b)", d))


def _split_cotizacion_items(items):
    """Separa ítems de trabajo vs filas GG/Utilidad (datos históricos)."""
    work = []
    gg_it = None
    util_it = None
    for it in items:
        desc = it["descripcion"] if "descripcion" in it.keys() else ""
        if _is_gg_line(desc):
            gg_it = it
        elif _is_util_line(desc):
            util_it = it
        else:
            work.append(it)
    return work, gg_it, util_it


def _cotizacion_planilla_totales(cot, items, iva_pct: float = 0.19) -> dict:
    """Arma subtotal/GG/Utilidad/IVA ordenados para la planilla PDF."""
    work, gg_it, util_it = _split_cotizacion_items(items)
    subtotal = sum(float(it["total"] or 0) for it in work)

    gg_pct = float(cot["gg_pct"] if "gg_pct" in cot.keys() and cot["gg_pct"] is not None else 5)
    util_pct = float(
        cot["utilidad_pct"] if "utilidad_pct" in cot.keys() and cot["utilidad_pct"] is not None else 15
    )
    if gg_it is not None:
        gg = float(gg_it["total"] or 0)
        desc_pct = _pct_from_text(gg_it["descripcion"], None)
        if desc_pct is not None:
            gg_pct = desc_pct
        # si el ítem histórico no trae %, se mantiene el % configurado solo como etiqueta
    else:
        stored_gg = float(cot["gg_monto"] or 0) if "gg_monto" in cot.keys() else 0.0
        gg = stored_gg if stored_gg > 0 else float(round(subtotal * gg_pct / 100.0))

    if util_it is not None:
        util = float(util_it["total"] or 0)
        desc_pct = _pct_from_text(util_it["descripcion"], None)
        if desc_pct is not None:
            util_pct = desc_pct
    else:
        stored_util = float(cot["utilidad_monto"] or 0) if "utilidad_monto" in cot.keys() else 0.0
        util = stored_util if stored_util > 0 else float(round(subtotal * util_pct / 100.0))

    neto = float(round(subtotal + gg + util))
    stored_iva = float(cot["iva"] or 0) if "iva" in cot.keys() else 0.0
    stored_total = float(cot["total"] or 0) if "total" in cot.keys() else 0.0
    stored_neto = float(cot["valor_neto"] or 0) if "valor_neto" in cot.keys() else 0.0

    if stored_neto > 0 and abs(stored_neto - neto) <= 1 and stored_iva >= 0:
        iva = stored_iva
        total = stored_total if stored_total > 0 else neto + iva
    elif stored_total > 0 and stored_iva > 0 and abs(stored_total - stored_iva - neto) <= 2:
        # Legacy: a veces el neto coincidía con total-iva
        iva = stored_iva
        total = stored_total
    else:
        iva = float(round(neto * float(iva_pct or 0.19)))
        total = neto + iva

    return {
        "work_items": work,
        "subtotal": subtotal,
        "gg_pct": gg_pct,
        "util_pct": util_pct,
        "gg": gg,
        "util": util,
        "neto": neto,
        "iva": iva,
        "iva_pct": float(iva_pct or 0.19) * 100.0,
        "total": total,
    }


def cotizacion_pdf_bytes(cot, items, empresa_row, iva_pct: float = 0.19) -> bytes:
    """PDF horizontal estilo planilla Río Maipo / Agrocastilla, columnas alineadas."""
    if FPDF is None:
        raise RuntimeError("FPDF no está instalado")

    plan = _cotizacion_planilla_totales(cot, items, iva_pct=iva_pct)
    work = plan["work_items"]

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    logo = LOGO_RIOMAIPO if LOGO_RIOMAIPO.exists() else LOGO_ERP
    if logo.exists():
        pdf.image(str(logo), x=128, y=4, w=40)
    else:
        pdf.set_text_color(180, 30, 30)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(0, 8)
        pdf.cell(297, 6, _pdf_txt("RIO MAIPO"), align="C", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(297, 5, _pdf_txt("Constructora"), align="C", ln=1)
        pdf.set_text_color(0, 0, 0)

    folio = cot["folio"] if "folio" in cot.keys() and cot["folio"] else ""
    if folio:
        pdf.set_xy(220, 12)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(59, 5, _pdf_txt(folio), align="R")

    title = _pdf_txt(cotizacion_titulo_pdf(cot))
    x0, table_w, row_h = 18, 261, 4.0
    pdf.set_xy(x0, 26)
    pdf.set_fill_color(210, 210, 210)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(table_w, 6, title, border=1, align="C", fill=True)

    headers = ["ITEM", "ESPECIFICACIÓN", "OBS", "UND", "CANTIDAD", "VALOR", "TOTAL"]
    # Anchos alineados a la barra título (261 mm)
    widths = [14, 90, 42, 14, 24, 38, 39]

    def draw_row(y: float, cells, fill: bool = False, bold: bool = False):
        pdf.set_xy(x0, y)
        if fill:
            pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Helvetica", "B" if bold else "", 8)
        for (text, align), w in zip(cells, widths):
            pdf.cell(w, row_h, _pdf_txt(text), border=1, align=align, fill=fill)

    y = 34.0
    draw_row(y, [(h, "C") for h in headers], fill=True, bold=True)
    y += row_h

    draw_row(
        y,
        [
            ("1.0", "C"),
            ("", "L"),
            ("", "L"),
            ("", "C"),
            ("", "R"),
            ("", "R"),
            (f"$ {fmt_clp_plain(plan['subtotal'])}", "R"),
        ],
        bold=True,
    )
    y += row_h

    filled = list(work)[:COT_PDF_ROWS]
    while len(filled) < COT_PDF_ROWS:
        filled.append(None)

    for idx, it in enumerate(filled, start=1):
        code = f"1.{idx}"
        if it is None:
            draw_row(
                y,
                [
                    (code, "C"),
                    ("", "L"),
                    ("", "L"),
                    ("", "C"),
                    ("", "R"),
                    ("", "R"),
                    ("$ -", "R"),
                ],
            )
        else:
            desc = str(it["descripcion"] or "")
            obs = str(it["obs"] if "obs" in it.keys() and it["obs"] else "")
            und = str(it["unidad"] or "")
            cant = float(it["cantidad"] or 0)
            pu = float(it["precio_unitario"] or 0)
            tot = float(it["total"] or 0)
            is_section = tot == 0 and pu == 0
            if is_section:
                draw_row(
                    y,
                    [
                        (code, "C"),
                        (desc[:58], "L"),
                        ("", "L"),
                        ("", "C"),
                        ("", "R"),
                        ("", "R"),
                        ("", "R"),
                    ],
                    bold=True,
                )
            else:
                draw_row(
                    y,
                    [
                        (code, "C"),
                        (desc[:58], "L"),
                        (obs[:28], "L"),
                        (und[:6], "C"),
                        (fmt_cant_pdf(cant), "R"),
                        (f"$ {fmt_clp_plain(pu)}", "R"),
                        (f"$ {fmt_clp_plain(tot)}", "R"),
                    ],
                )
        y += row_h

    summary = [
        ("SUBTOTAL", f"$ {fmt_clp_plain(plan['subtotal'])}", False),
        (f"GG {plan['gg_pct']:g}%", f"$ {fmt_clp_plain(plan['gg'])}", False),
        (f"UTILIDAD {plan['util_pct']:g}%", f"$ {fmt_clp_plain(plan['util'])}", False),
        ("VALOR NETO", f"$ {fmt_clp_plain(plan['neto'])}", True),
        (f"IVA {plan['iva_pct']:g}%", f"$ {fmt_clp_plain(plan['iva'])}", False),
        ("TOTAL", f"$ {fmt_clp_plain(plan['total'])}", True),
    ]
    label_w, val_w = 40, 38
    sx = x0 + sum(widths) - label_w - val_w
    sy = y + 2
    for i, (lab, val, bold) in enumerate(summary):
        pdf.set_xy(sx, sy + i * row_h)
        pdf.set_font("Helvetica", "B" if bold else "", 8)
        if bold:
            pdf.set_fill_color(235, 235, 235)
            pdf.cell(label_w, row_h, _pdf_txt(lab), border=1, fill=True)
            pdf.cell(val_w, row_h, _pdf_txt(val), border=1, align="R", fill=True)
        else:
            pdf.cell(label_w, row_h, _pdf_txt(lab), border=1)
            pdf.cell(val_w, row_h, _pdf_txt(val), border=1, align="R")

    pdf.set_xy(x0, sy)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(90, 90, 90)
    cliente = cot["razon_social"] if "razon_social" in cot.keys() and cot["razon_social"] else ""
    pdf.multi_cell(
        120,
        4,
        _pdf_txt(
            f"{folio} · {cliente}\n"
            f"Planilla cotización · {date.today().strftime('%d/%m/%Y')} · ERP Master Río Maipo"
        ),
        border=0,
    )
    pdf.set_text_color(0, 0, 0)

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
            f"RUT {cliente['rut'] if cliente and cliente['rut'] else '-'} | "
            f"{cliente['telefono'] if cliente and cliente['telefono'] else '-'} | "
            f"{cliente['email'] if cliente and cliente['email'] else '-'}"
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
    widths = [34, 28, 28, 32, 32, 26]
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
            doc_disp, fac_disp = cuenta_doc_factura_display(x)
            pdf.cell(widths[0], 6, _pdf_txt(doc_disp), border=1)
            pdf.cell(widths[1], 6, _pdf_txt(fac_disp), border=1, align="C")
            pdf.cell(widths[2], 6, _pdf_txt(fmt_dmy(x["fecha_vencimiento"] if "fecha_vencimiento" in x.keys() else None)), border=1)
            pdf.cell(widths[3], 6, _pdf_txt(f"$ {fmt_clp_plain(x['monto'])}"), border=1, align="R")
            pdf.cell(widths[4], 6, _pdf_txt(f"$ {fmt_clp_plain(x['saldo'])}"), border=1, align="R")
            pdf.cell(widths[5], 6, _pdf_txt(cxc_estado_label(x["estado"])), border=1, ln=1)

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_txt("Abonos"), ln=1)
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
