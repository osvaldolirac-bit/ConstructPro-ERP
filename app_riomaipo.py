"""
ERP Master — Carril Río Maipo (Streamlit)
Misma forma de alojamiento que /laconcepcion y /demo.
Puerto exclusivo: 8505  |  baseUrlPath: riomaipo
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "riomaipo_streamlit.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="ERP Río Maipo",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE NOT NULL,
            razon_social TEXT NOT NULL,
            giro TEXT,
            contacto TEXT,
            email TEXT,
            telefono TEXT,
            activo INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS parametros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            valor TEXT NOT NULL,
            tipo TEXT DEFAULT 'numero',
            unidad TEXT
        );
        CREATE TABLE IF NOT EXISTS obras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            ubicacion TEXT,
            estado TEXT DEFAULT 'activa',
            avance REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL,
            cliente_id INTEGER,
            obra TEXT NOT NULL,
            descripcion TEXT,
            estado TEXT DEFAULT 'borrador',
            fecha TEXT,
            subtotal REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            total REAL DEFAULT 0,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS cotizacion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER NOT NULL,
            partida TEXT NOT NULL,
            unidad TEXT DEFAULT 'm2',
            cantidad REAL DEFAULT 1,
            precio_unitario REAL DEFAULT 0,
            total REAL DEFAULT 0,
            FOREIGN KEY(cotizacion_id) REFERENCES cotizaciones(id)
        );
        CREATE TABLE IF NOT EXISTS cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento TEXT UNIQUE NOT NULL,
            cliente_id INTEGER,
            obra TEXT NOT NULL,
            concepto TEXT,
            fecha_emision TEXT,
            fecha_vencimiento TEXT,
            monto REAL DEFAULT 0,
            retenido REAL DEFAULT 0,
            abonado REAL DEFAULT 0,
            saldo REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );
        """
    )
    if cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO clientes (rut, razon_social, giro, contacto, email, telefono) VALUES (?,?,?,?,?,?)",
            [
                (
                    "76.123.456-7",
                    "Inmobiliaria Valle Sur SpA",
                    "Desarrollo inmobiliario",
                    "Carolina Méndez",
                    "compras@vallesur.cl",
                    "+56 9 8765 4321",
                ),
                (
                    "77.987.654-3",
                    "Constructora Andes Ltda.",
                    "Obras civiles",
                    "Pedro Rojas",
                    "admin@andesltda.cl",
                    "+56 2 2345 6789",
                ),
            ],
        )
        cur.executemany(
            "INSERT INTO parametros (clave, nombre, valor, tipo, unidad) VALUES (?,?,?,?,?)",
            [
                ("precio_cemento_saco", "Precio saco cemento", "4500", "numero", "CLP"),
                ("costo_hora_maestro", "Costo hora maestro", "5000", "numero", "CLP/h"),
                ("porcentaje_retencion", "Retención anticipo", "10", "porcentaje", "%"),
                ("iva", "IVA", "19", "porcentaje", "%"),
            ],
        )
        cur.executemany(
            "INSERT INTO obras (codigo, nombre, ubicacion, estado, avance) VALUES (?,?,?,?,?)",
            [
                ("RM-001", "Condominio Río Maipo", "Buin", "activa", 62),
                ("RM-002", "Bodega Central", "San Bernardo", "activa", 38),
            ],
        )
        cur.execute(
            """
            INSERT INTO cotizaciones (folio, cliente_id, obra, descripcion, estado, fecha, subtotal, iva, total)
            VALUES ('COT-RM-0001', 1, 'Condominio Río Maipo', 'Hormigón etapa 1', 'enviada', ?, 15692000, 2981480, 18673480)
            """,
            (date.today().isoformat(),),
        )
        cid = cur.lastrowid
        cur.executemany(
            "INSERT INTO cotizacion_items (cotizacion_id, partida, unidad, cantidad, precio_unitario, total) VALUES (?,?,?,?,?,?)",
            [
                (cid, "Radier hormigón H25", "m2", 420, 18500, 7770000),
                (cid, "Estuco exterior", "m2", 860, 9200, 7912000),
            ],
        )
        for doc, cliente_id, obra, monto, retenido, abonado in [
            ("EP-RM-0001", 1, "Condominio Río Maipo", 15_000_000, 1_500_000, 8_000_000),
            ("EP-RM-0002", 2, "Bodega Central", 8_000_000, 800_000, 0),
        ]:
            saldo = max(0, monto - retenido - abonado)
            estado = "pagado" if saldo <= 0 else ("parcial" if abonado or retenido else "pendiente")
            cur.execute(
                """
                INSERT INTO cuentas
                (documento, cliente_id, obra, concepto, fecha_emision, fecha_vencimiento,
                 monto, retenido, abonado, saldo, estado)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    doc,
                    cliente_id,
                    obra,
                    "Estado de pago",
                    (date.today() - timedelta(days=20)).isoformat(),
                    (date.today() + timedelta(days=10)).isoformat(),
                    monto,
                    retenido,
                    abonado,
                    saldo,
                    estado,
                ),
            )
    conn.commit()
    conn.close()


def clp(value: float | int | None) -> str:
    return f"${int(round(float(value or 0))):,.0f}".replace(",", ".") + " CLP"


def param(conn: sqlite3.Connection, clave: str, default: float = 0.0) -> float:
    row = conn.execute("SELECT valor FROM parametros WHERE clave=?", (clave,)).fetchone()
    if not row:
        return default
    try:
        return float(row["valor"])
    except ValueError:
        return default


def next_folio(conn: sqlite3.Connection, table: str, field: str, prefix: str) -> str:
    n = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"] + 1
    return f"{prefix}-{n:04d}"


init_db()

# ---------------------------------------------------------------------------
# UI shell — identidad clara (NO La Concepción)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      .rm-banner {
        background: linear-gradient(120deg, #163040, #0f1c24 55%, #2a4a3a);
        border: 1px solid rgba(212,163,92,.35);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        color: #f3efe6;
      }
      .rm-banner h1 { margin: 0; font-size: 1.7rem; }
      .rm-banner p { margin: .25rem 0 0; opacity: .85; }
      .rm-chip {
        display:inline-block; margin-top:.55rem; padding:.2rem .6rem;
        border-radius:999px; background:rgba(212,163,92,.2);
        border:1px solid rgba(212,163,92,.45); font-size:.8rem;
      }
    </style>
    <div class="rm-banner">
      <h1>ERP Master · Río Maipo</h1>
      <p>Carril independiente — no es La Concepción ni Demo</p>
      <span class="rm-chip">erpmaster.cl/riomaipo · puerto 8505</span>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Río Maipo")
    st.caption("Carril aparte de La Concepción")
    modulo = st.radio(
        "Módulos",
        [
            "Dashboard",
            "Cotizaciones",
            "Cuentas por cobrar",
            "Administración",
        ],
        label_visibility="collapsed",
    )

conn = get_conn()

# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
if modulo == "Dashboard":
    st.subheader("Dashboard")
    saldo = conn.execute("SELECT COALESCE(SUM(saldo),0) FROM cuentas").fetchone()[0]
    facturado = conn.execute("SELECT COALESCE(SUM(monto),0) FROM cuentas").fetchone()[0]
    abonado = conn.execute("SELECT COALESCE(SUM(abonado),0) FROM cuentas").fetchone()[0]
    clientes_n = conn.execute("SELECT COUNT(*) FROM clientes WHERE activo=1").fetchone()[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo por cobrar", clp(saldo))
    c2.metric("Facturado", clp(facturado))
    c3.metric("Abonado", clp(abonado))
    c4.metric("Clientes activos", clientes_n)

    obras = pd.read_sql_query("SELECT nombre AS Obra, avance AS Avance FROM obras ORDER BY nombre", conn)
    if not obras.empty:
        st.markdown("#### Avance de obras")
        st.bar_chart(obras.set_index("Obra"))

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Últimas cotizaciones")
        st.dataframe(
            pd.read_sql_query(
                "SELECT folio, obra, estado, total FROM cotizaciones ORDER BY id DESC LIMIT 8",
                conn,
            ),
            use_container_width=True,
            hide_index=True,
        )
    with col_b:
        st.markdown("#### Cuentas recientes")
        st.dataframe(
            pd.read_sql_query(
                "SELECT documento, obra, saldo, estado FROM cuentas ORDER BY id DESC LIMIT 8",
                conn,
            ),
            use_container_width=True,
            hide_index=True,
        )

# ---------------------------------------------------------------------------
# COTIZACIONES
# ---------------------------------------------------------------------------
elif modulo == "Cotizaciones":
    st.subheader("Cotizaciones")
    tab_list, tab_new = st.tabs(["Listado", "Nueva cotización"])

    with tab_list:
        df = pd.read_sql_query(
            """
            SELECT c.folio, c.fecha, cl.razon_social AS cliente, c.obra, c.estado, c.total
            FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id = c.cliente_id
            ORDER BY c.id DESC
            """,
            conn,
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_new:
        clientes = conn.execute(
            "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
        ).fetchall()
        if not clientes:
            st.warning("Crea clientes en Administración primero.")
        else:
            cemento = param(conn, "precio_cemento_saco", 4500)
            maestro = param(conn, "costo_hora_maestro", 5000)
            iva_pct = param(conn, "iva", 19) / 100
            ref = (cemento * 0.5) + (maestro * 2)
            st.info(f"Referencia APU m²: {clp(ref)} (cemento/maestro desde parámetros)")

            with st.form("nueva_cot"):
                cliente_id = st.selectbox(
                    "Cliente",
                    options=[c["id"] for c in clientes],
                    format_func=lambda i: next(c["razon_social"] for c in clientes if c["id"] == i),
                )
                obra = st.text_input("Obra", "Condominio Río Maipo")
                descripcion = st.text_area("Descripción", "")
                estado = st.selectbox("Estado", ["borrador", "enviada", "aprobada"])
                st.markdown("**Partidas**")
                p1 = st.text_input("Partida 1", "Radier hormigón")
                u1 = st.text_input("Unidad 1", "m2")
                c1 = st.number_input("Cantidad 1", value=100.0, min_value=0.0)
                pu1 = st.number_input("P. unitario 1", value=float(int(ref)), min_value=0.0)
                p2 = st.text_input("Partida 2 (opcional)", "")
                u2 = st.text_input("Unidad 2", "m2")
                c2 = st.number_input("Cantidad 2", value=0.0, min_value=0.0)
                pu2 = st.number_input("P. unitario 2", value=0.0, min_value=0.0)
                ok = st.form_submit_button("Guardar cotización")

            if ok:
                items = []
                if p1.strip():
                    items.append((p1.strip(), u1 or "m2", float(c1), float(pu1), float(c1) * float(pu1)))
                if p2.strip() and c2 > 0:
                    items.append((p2.strip(), u2 or "m2", float(c2), float(pu2), float(c2) * float(pu2)))
                subtotal = sum(i[4] for i in items)
                iva = round(subtotal * iva_pct)
                total = subtotal + iva
                folio = next_folio(conn, "cotizaciones", "folio", "COT-RM")
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO cotizaciones
                    (folio, cliente_id, obra, descripcion, estado, fecha, subtotal, iva, total)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        folio,
                        cliente_id,
                        obra.strip(),
                        descripcion.strip() or None,
                        estado,
                        date.today().isoformat(),
                        subtotal,
                        iva,
                        total,
                    ),
                )
                cot_id = cur.lastrowid
                cur.executemany(
                    """
                    INSERT INTO cotizacion_items
                    (cotizacion_id, partida, unidad, cantidad, precio_unitario, total)
                    VALUES (?,?,?,?,?,?)
                    """,
                    [(cot_id, *it) for it in items],
                )
                conn.commit()
                st.success(f"Cotización {folio} creada — total {clp(total)}")
                st.rerun()

# ---------------------------------------------------------------------------
# CUENTAS POR COBRAR
# ---------------------------------------------------------------------------
elif modulo == "Cuentas por cobrar":
    st.subheader("Cuentas por cobrar")
    tab_list, tab_new = st.tabs(["Listado / abonos", "Nuevo documento"])

    with tab_list:
        df = pd.read_sql_query(
            """
            SELECT cu.id, cu.documento, cl.razon_social AS cliente, cu.obra,
                   cu.monto, cu.retenido, cu.abonado, cu.saldo, cu.estado,
                   cu.fecha_vencimiento
            FROM cuentas cu
            LEFT JOIN clientes cl ON cl.id = cu.cliente_id
            ORDER BY cu.id DESC
            """,
            conn,
        )
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
        abiertas = df[df["estado"] != "pagado"]
        if not abiertas.empty:
            with st.form("abono_form"):
                doc_id = st.selectbox(
                    "Documento a abonar",
                    options=abiertas["id"].tolist(),
                    format_func=lambda i: f"{df.loc[df.id==i,'documento'].values[0]} (saldo {clp(df.loc[df.id==i,'saldo'].values[0])})",
                )
                monto_abono = st.number_input("Monto abono", min_value=1, step=1000)
                if st.form_submit_button("Registrar abono"):
                    row = conn.execute("SELECT * FROM cuentas WHERE id=?", (doc_id,)).fetchone()
                    abonado = float(row["abonado"]) + float(monto_abono)
                    saldo = max(0.0, float(row["monto"]) - float(row["retenido"]) - abonado)
                    estado = "pagado" if saldo <= 0 else "parcial"
                    conn.execute(
                        "UPDATE cuentas SET abonado=?, saldo=?, estado=? WHERE id=?",
                        (abonado, saldo, estado, doc_id),
                    )
                    conn.commit()
                    st.success("Abono registrado")
                    st.rerun()

    with tab_new:
        clientes = conn.execute(
            "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
        ).fetchall()
        ret_pct = param(conn, "porcentaje_retencion", 10)
        with st.form("nueva_cxc"):
            cliente_id = st.selectbox(
                "Cliente",
                options=[c["id"] for c in clientes] if clientes else [],
                format_func=lambda i: next(c["razon_social"] for c in clientes if c["id"] == i),
            )
            obra = st.text_input("Obra", "Condominio Río Maipo")
            concepto = st.text_input("Concepto", "Estado de pago")
            monto = st.number_input("Monto facturado", min_value=1, value=1_000_000, step=1000)
            aplicar = st.checkbox(f"Aplicar retención {ret_pct:.0f}%", value=True)
            dias = st.number_input("Días a vencimiento", min_value=1, value=30)
            if st.form_submit_button("Guardar documento") and clientes:
                retenido = round(monto * ret_pct / 100) if aplicar else 0
                saldo = max(0, monto - retenido)
                doc = next_folio(conn, "cuentas", "documento", "EP-RM")
                conn.execute(
                    """
                    INSERT INTO cuentas
                    (documento, cliente_id, obra, concepto, fecha_emision, fecha_vencimiento,
                     monto, retenido, abonado, saldo, estado)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        doc,
                        cliente_id,
                        obra.strip(),
                        concepto.strip(),
                        date.today().isoformat(),
                        (date.today() + timedelta(days=int(dias))).isoformat(),
                        float(monto),
                        float(retenido),
                        0.0,
                        float(saldo),
                        "pendiente" if saldo > 0 else "pagado",
                    ),
                )
                conn.commit()
                st.success(f"Documento {doc} creado")
                st.rerun()

# ---------------------------------------------------------------------------
# ADMINISTRACIÓN
# ---------------------------------------------------------------------------
else:
    st.subheader("Administración")
    tab_cli, tab_par, tab_obr = st.tabs(["Clientes", "Parámetros", "Obras"])

    with tab_cli:
        st.dataframe(
            pd.read_sql_query(
                "SELECT rut, razon_social, contacto, email, telefono, CASE activo WHEN 1 THEN 'activo' ELSE 'inactivo' END AS estado FROM clientes ORDER BY razon_social",
                conn,
            ),
            use_container_width=True,
            hide_index=True,
        )
        with st.form("nuevo_cliente"):
            rut = st.text_input("RUT")
            razon = st.text_input("Razón social")
            giro = st.text_input("Giro")
            contacto = st.text_input("Contacto")
            email = st.text_input("Email")
            telefono = st.text_input("Teléfono")
            if st.form_submit_button("Crear cliente"):
                if rut.strip() and razon.strip():
                    try:
                        conn.execute(
                            """
                            INSERT INTO clientes (rut, razon_social, giro, contacto, email, telefono)
                            VALUES (?,?,?,?,?,?)
                            """,
                            (rut.strip(), razon.strip(), giro, contacto, email, telefono),
                        )
                        conn.commit()
                        st.success("Cliente creado")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Ya existe un cliente con ese RUT")

    with tab_par:
        params = pd.read_sql_query(
            "SELECT id, nombre, clave, valor, tipo, unidad FROM parametros ORDER BY nombre",
            conn,
        )
        st.dataframe(params.drop(columns=["id"]), use_container_width=True, hide_index=True)
        if not params.empty:
            with st.form("edit_param"):
                pid = st.selectbox(
                    "Parámetro",
                    options=params["id"].tolist(),
                    format_func=lambda i: params.loc[params.id == i, "nombre"].values[0],
                )
                nuevo = st.text_input(
                    "Nuevo valor",
                    value=str(params.loc[params.id == pid, "valor"].values[0]),
                )
                if st.form_submit_button("Actualizar"):
                    conn.execute("UPDATE parametros SET valor=? WHERE id=?", (nuevo.strip(), pid))
                    conn.commit()
                    st.success("Parámetro actualizado")
                    st.rerun()
        with st.form("nuevo_param"):
            st.markdown("**Nuevo parámetro**")
            clave = st.text_input("Clave", placeholder="precio_acero_kg")
            nombre = st.text_input("Nombre")
            valor = st.text_input("Valor")
            tipo = st.selectbox("Tipo", ["numero", "porcentaje", "texto"])
            unidad = st.text_input("Unidad", "CLP")
            if st.form_submit_button("Crear parámetro"):
                try:
                    conn.execute(
                        "INSERT INTO parametros (clave, nombre, valor, tipo, unidad) VALUES (?,?,?,?,?)",
                        (clave.strip().lower().replace(" ", "_"), nombre.strip(), valor.strip(), tipo, unidad),
                    )
                    conn.commit()
                    st.success("Parámetro creado")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Clave duplicada")

    with tab_obr:
        st.dataframe(
            pd.read_sql_query(
                "SELECT codigo, nombre, ubicacion, estado, avance FROM obras ORDER BY nombre",
                conn,
            ),
            use_container_width=True,
            hide_index=True,
        )
        with st.form("nueva_obra"):
            codigo = st.text_input("Código", "RM-003")
            nombre = st.text_input("Nombre")
            ubicacion = st.text_input("Ubicación")
            estado = st.selectbox("Estado", ["activa", "pausada", "cerrada"])
            avance = st.slider("Avance %", 0, 100, 0)
            if st.form_submit_button("Registrar obra"):
                try:
                    conn.execute(
                        "INSERT INTO obras (codigo, nombre, ubicacion, estado, avance) VALUES (?,?,?,?,?)",
                        (codigo.strip().upper(), nombre.strip(), ubicacion, estado, float(avance)),
                    )
                    conn.commit()
                    st.success("Obra registrada")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Código de obra duplicado")

conn.close()
