"""
ERP Master — Río Maipo
Inspirado en SOLUERP, con gestión mejorada:
- Flujo cotización → aprobación → cuenta por cobrar
- Aging de cobranza y alertas de mora/vencimiento
- Catálogo de productos, proveedores y vista 360 del cliente
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "riomaipo_erp.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="ERP Río Maipo",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      .rm-hero {
        background: linear-gradient(120deg, #102833 0%, #1a3d4d 55%, #245a4a 100%);
        border: 1px solid rgba(212,163,92,.35);
        border-radius: 16px; padding: 1.1rem 1.3rem; margin-bottom: .9rem; color: #f4efe6;
      }
      .rm-hero h1 { margin: 0; font-size: 1.65rem; font-weight: 700; }
      .rm-hero p { margin: .3rem 0 0; opacity: .88; }
      .rm-chip {
        display:inline-block; margin-top:.55rem; padding:.2rem .65rem; border-radius:999px;
        background:rgba(212,163,92,.18); border:1px solid rgba(212,163,92,.4); font-size:.78rem;
      }
      .alert-box {
        border-radius: 12px; padding: .75rem 1rem; margin: .35rem 0;
        border: 1px solid rgba(255,255,255,.12);
      }
      .alert-danger { background: rgba(224,122,109,.15); }
      .alert-warn { background: rgba(226,183,101,.15); }
      .alert-ok { background: rgba(125,207,182,.12); }
      div[data-testid="stMetricValue"] { font-size: 1.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
st.markdown(
    f"""
    <div class="rm-hero">
      <h1>ERP Master · {empresa['razon_social'] if empresa else 'Río Maipo'}</h1>
      <p>Gestión comercial y cobranza — inspirado en SOLUERP, con control y alertas mejoradas</p>
      <span class="rm-chip">erpmaster.cl/riomaipo · RUT {empresa['rut'] if empresa else '—'}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    st.markdown("### Menú")
    modulo = st.radio("Navegación", MODULOS, label_visibility="collapsed")
    st.caption("Mejoras vs SOLUERP: aging, alertas, flujo cotización→CxC, vista 360")

# ===========================================================================
# DASHBOARD
# ===========================================================================
if modulo == "Dashboard":
    st.subheader("Dashboard de gestión")
    hoy = date.today()
    iva = param(db, "iva", 19)

    cotas = db.execute("SELECT estado, COUNT(*) n, COALESCE(SUM(total),0) t FROM cotizaciones GROUP BY estado").fetchall()
    por_estado = {r["estado"]: (r["n"], r["t"]) for r in cotas}
    cuentas = db.execute("SELECT * FROM cuentas").fetchall()
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

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Saldo por cobrar", clp(saldo_total))
    c2.metric("Vencido (mora)", clp(vencido))
    c3.metric("Vence en 7 días", clp(por_vencer_7))
    c4.metric("Cotiz. aprobadas", por_estado.get("aprobada", (0, 0))[0])
    c5.metric("Cotiz. enviadas", por_estado.get("enviada", (0, 0))[0])

    # Alertas
    st.markdown("#### Alertas de gestión")
    alertas = []
    for x in cuentas:
        if float(x["saldo"]) <= 0:
            continue
        ve = dparse(x["fecha_vencimiento"])
        cli = db.execute("SELECT razon_social FROM clientes WHERE id=?", (x["cliente_id"],)).fetchone()
        nombre = cli["razon_social"] if cli else "Cliente"
        if ve and ve < hoy:
            alertas.append(
                ("danger", f"Mora { (hoy-ve).days } días · {x['documento']} · {nombre} · saldo {clp(x['saldo'])}")
            )
        elif ve and 0 <= (ve - hoy).days <= 7:
            alertas.append(
                ("warn", f"Por vencer en {(ve-hoy).days} días · {x['documento']} · {nombre} · {clp(x['saldo'])}")
            )
    for cot in db.execute("SELECT * FROM cotizaciones WHERE estado IN ('enviada','borrador')").fetchall():
        f = dparse(cot["fecha"])
        if not f:
            continue
        vence = f + timedelta(days=int(cot["validez_dias"] or 30))
        if vence < hoy and cot["estado"] == "enviada":
            alertas.append(("warn", f"Cotización {cot['folio']} vencida sin respuesta (validez {cot['validez_dias']}d)"))
    if not alertas:
        st.markdown('<div class="alert-box alert-ok">Sin alertas críticas. Cartera al día.</div>', unsafe_allow_html=True)
    else:
        for nivel, msg in alertas[:12]:
            st.markdown(f'<div class="alert-box alert-{nivel}">⚠ {msg}</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Embudo de cotizaciones")
        funnel = pd.DataFrame(
            [
                {"Etapa": "Borrador", "Cantidad": por_estado.get("borrador", (0, 0))[0]},
                {"Etapa": "Enviada", "Cantidad": por_estado.get("enviada", (0, 0))[0]},
                {"Etapa": "Aprobada", "Cantidad": por_estado.get("aprobada", (0, 0))[0]},
                {"Etapa": "Rechazada", "Cantidad": por_estado.get("rechazada", (0, 0))[0]},
            ]
        )
        st.bar_chart(funnel.set_index("Etapa"))
    with col_b:
        st.markdown("#### Aging cuentas por cobrar")
        buckets = {"por vencer": 0.0, "vence hoy": 0.0, "1-30 días mora": 0.0, "31-60 días mora": 0.0, "+60 días mora": 0.0, "sin fecha": 0.0}
        for x in cuentas:
            if float(x["saldo"]) <= 0:
                continue
            b = aging_bucket(dparse(x["fecha_vencimiento"]), hoy)
            buckets[b] = buckets.get(b, 0) + float(x["saldo"])
        aging_df = pd.DataFrame({"Tramo": list(buckets.keys()), "Saldo": list(buckets.values())})
        st.bar_chart(aging_df.set_index("Tramo"))

    st.markdown("#### Top clientes por deuda")
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
        st.info("No hay saldos abiertos.")

# ===========================================================================
# CLIENTES
# ===========================================================================
elif modulo == "Clientes":
    st.subheader("Clientes")
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
            a, b = st.columns(2)
            a.metric("Deuda abierta", clp(deuda))
            b.metric("Cotizaciones", ncot)
            st.markdown("**Cotizaciones**")
            st.dataframe(
                pd.read_sql_query(
                    "SELECT folio, fecha, estado, total FROM cotizaciones WHERE cliente_id=? ORDER BY id DESC",
                    db,
                    params=(cid,),
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.markdown("**Cuentas por cobrar**")
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
    st.subheader("Proveedores")
    st.dataframe(
        pd.read_sql_query(
            "SELECT rut AS RUT, razon_social AS Proveedor, contacto, telefono, email, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS estado FROM proveedores ORDER BY razon_social",
            db,
        ),
        use_container_width=True,
        hide_index=True,
    )
    with st.form("f_prov"):
        st.markdown("**Nuevo proveedor**")
        rut = st.text_input("RUT")
        razon = st.text_input("Razón social")
        contacto = st.text_input("Contacto")
        telefono = st.text_input("Teléfono")
        email = st.text_input("Email")
        if st.form_submit_button("Crear") and razon.strip():
            try:
                db.execute(
                    "INSERT INTO proveedores (rut, razon_social, contacto, telefono, email) VALUES (?,?,?,?,?)",
                    (rut.strip(), razon.strip(), contacto, telefono, email),
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
    st.subheader("Productos / partidas")
    st.caption("Catálogo usable al armar cotizaciones (mejora vs cargar todo a mano).")
    st.dataframe(
        pd.read_sql_query(
            "SELECT codigo AS Código, nombre AS Nombre, unidad AS Un, precio AS Precio, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS Estado FROM productos ORDER BY nombre",
            db,
        ),
        use_container_width=True,
        hide_index=True,
    )
    with st.form("f_prod"):
        st.markdown("**Nuevo producto**")
        codigo = st.text_input("Código", placeholder="RAD-M2")
        nombre = st.text_input("Nombre")
        unidad = st.text_input("Unidad", "m2")
        precio = st.number_input("Precio venta", min_value=0.0, step=100.0)
        if st.form_submit_button("Crear") and nombre.strip():
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
    st.subheader("Cotizaciones")
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
            st.info("Sin cotizaciones")

    with tab_new:
        clientes = db.execute("SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social").fetchall()
        productos = db.execute("SELECT id, codigo, nombre, unidad, precio FROM productos WHERE activo=1 ORDER BY nombre").fetchall()
        iva_pct = param(db, "iva", 19) / 100
        validez_def = int(param(db, "validez_cotizacion", 30))
        if not clientes:
            st.warning("Crea clientes primero")
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
                guardar = st.form_submit_button("Guardar cotización")

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
            st.info("Sin cotizaciones")
        else:
            sel = st.selectbox(
                "Cotización",
                options=[r["id"] for r in rows],
                format_func=lambda i: next(f"{r['folio']} · {r['razon_social'] or '—'} · {r['estado']} · {clp(r['total'])}" for r in rows if r["id"] == i),
            )
            cot = next(r for r in rows if r["id"] == sel)
            st.write(f"**{cot['folio']}** · {cot['proyecto'] or ''} · {cot['asunto'] or ''}")
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
                    st.info(f"Ya tiene CxC vinculada (id {cot['cxc_id']})")
                else:
                    st.caption("Aprueba la cotización para poder generar la CxC.")

# ===========================================================================
# CUENTAS POR COBRAR
# ===========================================================================
elif modulo == "Cuentas por cobrar":
    st.subheader("Cuentas por cobrar / Cobranza")
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
            st.metric("Saldo filtrado", clp(float(view["Saldo"].sum())))
        else:
            st.info("Sin documentos")

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
            if st.form_submit_button("Guardar") and clientes:
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
            st.success("No hay saldos pendientes")
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
                if st.form_submit_button("Registrar abono"):
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
    st.subheader("Administración")
    tab_emp, tab_par = st.tabs(["Mi empresa", "Parámetros"])

    with tab_emp:
        e = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()
        with st.form("f_emp"):
            rut = st.text_input("RUT", e["rut"] or "")
            razon = st.text_input("Razón social", e["razon_social"] or "")
            telefono = st.text_input("Teléfono", e["telefono"] or "")
            email = st.text_input("Email", e["email"] or "")
            direccion = st.text_input("Dirección", e["direccion"] or "")
            region = st.text_input("Región", e["region"] or "")
            pais = st.text_input("País", e["pais"] or "Chile")
            if st.form_submit_button("Guardar empresa"):
                db.execute(
                    """UPDATE empresa SET rut=?, razon_social=?, telefono=?, email=?, direccion=?, region=?, pais=? WHERE id=1""",
                    (rut, razon, telefono, email, direccion, region, pais),
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
            if st.form_submit_button("Actualizar"):
                db.execute("UPDATE parametros SET valor=? WHERE clave=?", (valor.strip(), clave))
                db.commit()
                st.success("Parámetro actualizado")
                st.rerun()

db.close()
