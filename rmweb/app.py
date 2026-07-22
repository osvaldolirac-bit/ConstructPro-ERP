"""ERP Master · Río Maipo — Flask + Bootstrap + DataTables (reemplazo de Streamlit)."""

from __future__ import annotations

import os
from datetime import date, timedelta
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from io import BytesIO

from rmweb import core

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)
app.secret_key = os.getenv("SECRET_KEY", "riomaipo-web-change-me")

# Prefijo público detrás de nginx (/riomaipo)
try:
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
except Exception:  # pragma: no cover
    pass


@app.before_request
def _boot():
    # Cuando nginx recorta /riomaipo/ y envía X-Forwarded-Prefix
    prefix = (request.headers.get("X-Forwarded-Prefix") or os.getenv("RIOMAIPO_PREFIX") or "").rstrip("/")
    if prefix:
        request.environ["SCRIPT_NAME"] = prefix
    if not getattr(g, "_db_ready", False):
        core.init_db()
        g._db_ready = True


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("auth_ok"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_globals():
    return {
        "clp": core.clp,
        "fmt_dmy": core.fmt_dmy,
        "estado_label_cot": core.estado_label_cot,
        "cxc_estado_label": core.cxc_estado_label,
        "cxc_estado_class": core.cxc_estado_class,
        "auth_user": session.get("auth_user", ""),
        "auth_nombre": session.get("auth_nombre", ""),
        "auth_tipo": session.get("auth_tipo", ""),
        "app_name": "ERP Master",
        "track_name": "Río Maipo",
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("auth_ok"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        user = core.get_user_if_valid(
            request.form.get("usuario", ""),
            request.form.get("clave", ""),
        )
        if user:
            session["auth_ok"] = True
            session["auth_user"] = user["usuario"]
            session["auth_nombre"] = user["nombre"] or user["usuario"]
            session["auth_tipo"] = user["tipo"] or "Consulta"
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Usuario o clave incorrectos"
    return render_template("login.html", error=error, default_user=core.DEFAULT_ACCESO)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    db = core.conn()
    cotas = db.execute(
        "SELECT estado, COUNT(*) n, COALESCE(SUM(total),0) t FROM cotizaciones GROUP BY estado"
    ).fetchall()
    n_cot = sum(r["n"] for r in cotas)
    sum_cot = sum(float(r["t"]) for r in cotas)
    n_apr = sum(r["n"] for r in cotas if r["estado"] == "aprobada")
    saldo = db.execute("SELECT COALESCE(SUM(saldo),0) s FROM cuentas").fetchone()["s"]
    pend = db.execute(
        "SELECT COUNT(*) n FROM cuentas WHERE saldo > 0"
    ).fetchone()["n"]
    venc = db.execute(
        """
        SELECT COUNT(*) n FROM cuentas
        WHERE saldo > 0 AND fecha_vencimiento IS NOT NULL AND fecha_vencimiento < date('now')
        """
    ).fetchone()["n"]
    top = db.execute(
        """
        SELECT cl.razon_social, COALESCE(SUM(cu.saldo),0) saldo
        FROM cuentas cu LEFT JOIN clientes cl ON cl.id=cu.cliente_id
        GROUP BY cu.cliente_id
        HAVING saldo > 0
        ORDER BY saldo DESC LIMIT 8
        """
    ).fetchall()
    db.close()
    return render_template(
        "dashboard.html",
        active="dashboard",
        n_cot=n_cot,
        sum_cot=sum_cot,
        n_apr=n_apr,
        saldo=saldo,
        pend=pend,
        venc=venc,
        top=top,
        cotas=cotas,
    )


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
@app.route("/clientes/")
@login_required
def clientes_list():
    q = (request.args.get("q") or "").strip()
    db = core.conn()
    sql = """
        SELECT id, rut, razon_social, contacto, telefono, email, comuna, activo
        FROM clientes WHERE 1=1
    """
    params: list = []
    if q:
        like = f"%{q}%"
        sql += " AND (rut LIKE ? OR razon_social LIKE ? OR email LIKE ? OR contacto LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY razon_social"
    rows = db.execute(sql, params).fetchall()
    db.close()
    return render_template("clientes/lista.html", active="clientes", rows=rows, q=q)


@app.route("/clientes/nuevo", methods=["GET", "POST"])
@app.route("/clientes/<int:cid>/editar", methods=["GET", "POST"])
@login_required
def clientes_form(cid: int | None = None):
    db = core.conn()
    row = db.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone() if cid else None
    if request.method == "POST":
        data = (
            request.form.get("rut", "").strip() or None,
            request.form.get("razon_social", "").strip(),
            request.form.get("contacto", "").strip() or None,
            request.form.get("telefono", "").strip() or None,
            request.form.get("email", "").strip() or None,
            request.form.get("direccion", "").strip() or None,
            request.form.get("comuna", "").strip() or None,
            1 if request.form.get("activo") else 0,
        )
        if not data[1]:
            flash("La razón social es obligatoria", "danger")
        else:
            try:
                if row:
                    db.execute(
                        """
                        UPDATE clientes SET rut=?, razon_social=?, contacto=?, telefono=?,
                        email=?, direccion=?, comuna=?, activo=? WHERE id=?
                        """,
                        (*data, row["id"]),
                    )
                else:
                    db.execute(
                        """
                        INSERT INTO clientes
                        (rut, razon_social, contacto, telefono, email, direccion, comuna, activo, creado_en)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (*data, date.today().isoformat()),
                    )
                db.commit()
                flash("Cliente guardado", "ok")
                db.close()
                return redirect(url_for("clientes_list"))
            except Exception as exc:
                flash(f"No se pudo guardar: {exc}", "danger")
    db.close()
    return render_template("clientes/form.html", active="clientes", row=row)


# ---------------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------------
@app.route("/cotizaciones/")
@login_required
def cotizaciones_list():
    db = core.conn()
    rows = db.execute(
        """
        SELECT c.id, c.folio, c.fecha, c.estado, c.total, c.asunto, c.proyecto, c.titulo,
               cl.razon_social AS cliente
        FROM cotizaciones c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        ORDER BY COALESCE(c.fecha,'') DESC, c.id DESC
        """
    ).fetchall()
    n_total = len(rows)
    sum_total = sum(float(r["total"] or 0) for r in rows)
    n_apr = sum(1 for r in rows if r["estado"] == "aprobada")
    n_rec = sum(1 for r in rows if r["estado"] == "rechazada")
    sum_apr = sum(float(r["total"] or 0) for r in rows if r["estado"] == "aprobada")
    sum_rec = sum(float(r["total"] or 0) for r in rows if r["estado"] == "rechazada")
    conv = (n_apr / n_total * 100) if n_total else 0
    db.close()
    return render_template(
        "cotizaciones/lista.html",
        active="cotizaciones",
        rows=rows,
        kpis={
            "n_total": n_total,
            "sum_total": sum_total,
            "n_apr": n_apr,
            "sum_apr": sum_apr,
            "n_rec": n_rec,
            "sum_rec": sum_rec,
            "conv": conv,
        },
    )


@app.route("/cotizaciones/nueva", methods=["GET", "POST"])
@app.route("/cotizaciones/<int:cot_id>/editar", methods=["GET", "POST"])
@login_required
def cotizaciones_form(cot_id: int | None = None):
    db = core.conn()
    clientes = db.execute(
        "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
    ).fetchall()
    edit = None
    items = []
    if cot_id:
        edit = db.execute(
            """
            SELECT c.*, cl.razon_social FROM cotizaciones c
            LEFT JOIN clientes cl ON cl.id=c.cliente_id WHERE c.id=?
            """,
            (cot_id,),
        ).fetchone()
        if not edit:
            flash("Cotización no encontrada", "danger")
            db.close()
            return redirect(url_for("cotizaciones_list"))
        items = db.execute(
            """
            SELECT * FROM cotizacion_items WHERE cotizacion_id=?
            ORDER BY COALESCE(orden,0), id
            """,
            (cot_id,),
        ).fetchall()

    iva_pct = core.param(db, "iva", 19) / 100
    gg_def = core.param(db, "gg_pct", 5)
    util_def = core.param(db, "utilidad_pct", 15)
    validez_def = int(core.param(db, "validez_cotizacion", 30))

    if request.method == "POST":
        cliente_id = int(request.form["cliente_id"])
        version = (request.form.get("version") or "1").strip().lstrip("Vv") or "1"
        titulo = (request.form.get("titulo") or "").strip() or None
        proyecto = (request.form.get("proyecto") or "").strip() or None
        asunto = (request.form.get("asunto") or "").strip() or None
        estado = request.form.get("estado") or "borrador"
        validez = int(request.form.get("validez") or validez_def)
        gg_pct = float(request.form.get("gg_pct") or gg_def)
        utilidad_pct = float(request.form.get("utilidad_pct") or util_def)
        notas = (request.form.get("notas") or "").strip() or None

        descs = request.form.getlist("desc")
        obss = request.form.getlist("obs")
        unds = request.form.getlist("und")
        cants = request.form.getlist("cant")
        valores = request.form.getlist("valor")
        lineas = []
        for i, desc in enumerate(descs):
            if not str(desc).strip():
                continue
            cant = float(cants[i] or 0)
            if cant <= 0:
                continue
            pu = float(valores[i] or 0)
            total = cant * pu
            lineas.append(
                (
                    None,
                    desc.strip(),
                    (obss[i] if i < len(obss) else "").strip() or None,
                    i + 1,
                    (unds[i] if i < len(unds) else "un").strip() or "un",
                    cant,
                    pu,
                    total,
                )
            )
        if not lineas:
            flash("Agrega al menos un ítem con cantidad > 0", "danger")
        else:
            tots = core.calc_cotizacion_totales(
                sum(x[7] for x in lineas), gg_pct, utilidad_pct, iva_pct
            )
            if edit:
                db.execute(
                    """
                    UPDATE cotizaciones SET
                      cliente_id=?, asunto=?, proyecto=?, estado=?, validez_dias=?,
                      version=?, titulo=?, gg_pct=?, utilidad_pct=?,
                      gg_monto=?, utilidad_monto=?, valor_neto=?,
                      subtotal=?, iva=?, total=?, notas=?
                    WHERE id=?
                    """,
                    (
                        cliente_id, asunto, proyecto, estado, validez,
                        version, titulo, gg_pct, utilidad_pct,
                        tots["gg_monto"], tots["utilidad_monto"], tots["valor_neto"],
                        tots["subtotal"], tots["iva"], tots["total"], notas, edit["id"],
                    ),
                )
                db.execute("DELETE FROM cotizacion_items WHERE cotizacion_id=?", (edit["id"],))
                cid = edit["id"]
                folio = edit["folio"]
            else:
                folio = core.next_code(db, "cotizaciones", "folio", "COT")
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO cotizaciones
                    (folio, cliente_id, asunto, proyecto, estado, fecha, validez_dias,
                     version, titulo, gg_pct, utilidad_pct,
                     gg_monto, utilidad_monto, valor_neto, subtotal, iva, total, notas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        folio, cliente_id, asunto, proyecto, estado,
                        date.today().isoformat(), validez,
                        version, titulo, gg_pct, utilidad_pct,
                        tots["gg_monto"], tots["utilidad_monto"], tots["valor_neto"],
                        tots["subtotal"], tots["iva"], tots["total"], notas,
                    ),
                )
                cid = cur.lastrowid
            db.executemany(
                """
                INSERT INTO cotizacion_items
                (cotizacion_id, producto_id, descripcion, obs, orden, unidad, cantidad, precio_unitario, total)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [(cid, *ln) for ln in lineas],
            )
            db.commit()
            flash(f"{folio} guardada · total {core.clp(tots['total'])}", "ok")
            db.close()
            return redirect(url_for("cotizaciones_detalle", cot_id=cid))

    # defaults for new form title from first client
    titulo_default = ""
    if not edit and clientes:
        titulo_default = (clientes[0]["razon_social"] or "").upper()
    if edit and edit["titulo"]:
        titulo_default = edit["titulo"]

    db.close()
    return render_template(
        "cotizaciones/form.html",
        active="cotizaciones",
        edit=edit,
        items=items,
        clientes=clientes,
        titulo_default=titulo_default,
        gg_def=gg_def,
        util_def=util_def,
        validez_def=validez_def,
        slots=12,
    )


@app.route("/cotizaciones/<int:cot_id>")
@login_required
def cotizaciones_detalle(cot_id: int):
    db = core.conn()
    cot = db.execute(
        """
        SELECT c.*, cl.razon_social, cl.rut AS cliente_rut
        FROM cotizaciones c LEFT JOIN clientes cl ON cl.id=c.cliente_id
        WHERE c.id=?
        """,
        (cot_id,),
    ).fetchone()
    if not cot:
        flash("Cotización no encontrada", "danger")
        db.close()
        return redirect(url_for("cotizaciones_list"))
    items = db.execute(
        """
        SELECT * FROM cotizacion_items WHERE cotizacion_id=?
        ORDER BY COALESCE(orden,0), id
        """,
        (cot_id,),
    ).fetchall()
    db.close()
    return render_template(
        "cotizaciones/detalle.html",
        active="cotizaciones",
        cot=cot,
        items=items,
    )


@app.route("/cotizaciones/<int:cot_id>/pdf")
@login_required
def cotizaciones_pdf(cot_id: int):
    db = core.conn()
    cot = db.execute(
        """
        SELECT c.*, cl.razon_social, cl.rut AS cliente_rut
        FROM cotizaciones c LEFT JOIN clientes cl ON cl.id=c.cliente_id
        WHERE c.id=?
        """,
        (cot_id,),
    ).fetchone()
    items = db.execute(
        """
        SELECT descripcion, COALESCE(obs,'') AS obs, unidad, cantidad, precio_unitario, total
        FROM cotizacion_items WHERE cotizacion_id=? ORDER BY COALESCE(orden,0), id
        """,
        (cot_id,),
    ).fetchall()
    empresa = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()
    db.close()
    if not cot:
        flash("Cotización no encontrada", "danger")
        return redirect(url_for("cotizaciones_list"))
    pdf = core.cotizacion_pdf_bytes(cot, items, empresa)
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{cot['folio']}.pdf",
    )


@app.route("/cotizaciones/<int:cot_id>/borrar", methods=["POST"])
@login_required
def cotizaciones_borrar(cot_id: int):
    db = core.conn()
    row = db.execute("SELECT folio, cxc_id FROM cotizaciones WHERE id=?", (cot_id,)).fetchone()
    if not row:
        flash("No encontrada", "danger")
    elif row["cxc_id"]:
        flash("No se puede eliminar: tiene CxC vinculada", "danger")
    else:
        db.execute("DELETE FROM cotizacion_items WHERE cotizacion_id=?", (cot_id,))
        db.execute("DELETE FROM cotizaciones WHERE id=?", (cot_id,))
        db.commit()
        flash(f"{row['folio']} eliminada", "ok")
    db.close()
    return redirect(url_for("cotizaciones_list"))


@app.route("/cotizaciones/<int:cot_id>/estado", methods=["POST"])
@login_required
def cotizaciones_estado(cot_id: int):
    estado = request.form.get("estado") or "borrador"
    db = core.conn()
    db.execute("UPDATE cotizaciones SET estado=? WHERE id=?", (estado, cot_id))
    db.commit()
    db.close()
    flash("Estado actualizado", "ok")
    return redirect(url_for("cotizaciones_detalle", cot_id=cot_id))


# ---------------------------------------------------------------------------
# Cuentas por cobrar
# ---------------------------------------------------------------------------
@app.route("/cuentas/")
@login_required
def cuentas_list():
    q = (request.args.get("q") or "").strip()
    db = core.conn()
    sql = """
        SELECT cu.*, cl.razon_social AS cliente
        FROM cuentas cu LEFT JOIN clientes cl ON cl.id=cu.cliente_id
        WHERE 1=1
    """
    params: list = []
    if q:
        like = f"%{q}%"
        sql += " AND (cl.razon_social LIKE ? OR cu.documento LIKE ? OR cu.num_factura LIKE ? OR cu.concepto LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY cu.id DESC"
    rows = db.execute(sql, params).fetchall()
    docs = [dict(r) for r in rows]
    total_docs = len(docs)
    total_monto = sum(float(d["monto"] or 0) for d in docs)
    pend = [d for d in docs if core.cxc_estado_class(d["estado"]) == "pendiente"]
    abon = [d for d in docs if core.cxc_estado_class(d["estado"]) == "abonado"]
    pag = [d for d in docs if core.cxc_estado_class(d["estado"]) == "pagado"]
    kpis = {
        "total_docs": total_docs,
        "total_monto": total_monto,
        "pend_n": len(pend),
        "pend_m": sum(float(d["monto"] or 0) for d in pend),
        "abon_n": len(abon),
        "abon_m": sum(float(d["monto"] or 0) for d in abon),
        "pag_n": len(pag),
        "pag_m": sum(float(d["monto"] or 0) for d in pag),
        "tasa": (len(pag) / total_docs * 100) if total_docs else 0,
        "sum_total": sum(float(d["monto"] or 0) for d in docs),
        "sum_abonos": sum(float(d["abonado"] or 0) for d in docs),
        "sum_saldo": sum(float(d["saldo"] or 0) for d in docs),
    }
    db.close()
    return render_template(
        "cuentas/lista.html",
        active="cuentas",
        rows=docs,
        kpis=kpis,
        q=q,
    )


@app.route("/cuentas/360")
@login_required
def cuentas_360():
    db = core.conn()
    clientes = db.execute(
        "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
    ).fetchall()
    cid = request.args.get("cliente_id", type=int)
    if not cid and clientes:
        cid = clientes[0]["id"]
    cli = db.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone() if cid else None
    cuentas = []
    abonos = []
    cots = []
    deuda = 0.0
    if cid:
        cuentas = db.execute(
            "SELECT * FROM cuentas WHERE cliente_id=? ORDER BY id DESC", (cid,)
        ).fetchall()
        deuda = sum(float(x["saldo"] or 0) for x in cuentas)
        abonos = db.execute(
            """
            SELECT a.fecha, cu.documento, a.monto, a.medio, a.nota
            FROM abonos a JOIN cuentas cu ON cu.id=a.cuenta_id
            WHERE cu.cliente_id=? ORDER BY a.id DESC LIMIT 20
            """,
            (cid,),
        ).fetchall()
        cots = db.execute(
            """
            SELECT folio, fecha, estado, total, COALESCE(titulo, asunto, proyecto,'') AS titulo
            FROM cotizaciones WHERE cliente_id=? ORDER BY COALESCE(fecha,'') DESC, id DESC
            """,
            (cid,),
        ).fetchall()
    db.close()
    return render_template(
        "cuentas/vista360.html",
        active="cuentas",
        clientes=clientes,
        cid=cid,
        cli=cli,
        cuentas=cuentas,
        abonos=abonos,
        cots=cots,
        deuda=deuda,
    )


@app.route("/cuentas/nueva", methods=["GET", "POST"])
@app.route("/cuentas/<int:cuenta_id>/editar", methods=["GET", "POST"])
@login_required
def cuentas_form(cuenta_id: int | None = None):
    db = core.conn()
    clientes = db.execute(
        "SELECT id, razon_social FROM clientes WHERE activo=1 ORDER BY razon_social"
    ).fetchall()
    dias = int(core.param(db, "dias_credito", 30))
    edit = db.execute("SELECT * FROM cuentas WHERE id=?", (cuenta_id,)).fetchone() if cuenta_id else None
    if cuenta_id and not edit:
        flash("Documento no encontrado", "danger")
        db.close()
        return redirect(url_for("cuentas_list"))

    if request.method == "POST":
        cliente_id = int(request.form["cliente_id"])
        tipo = request.form.get("tipo_doc") or "EP"
        concepto = (request.form.get("concepto") or "").strip() or None
        monto = float(request.form.get("monto") or 0)
        emision = request.form.get("fecha_emision") or date.today().isoformat()
        venc = request.form.get("fecha_vencimiento") or (date.today() + timedelta(days=dias)).isoformat()
        facturado = 1 if request.form.get("facturado") else 0
        num_factura = (request.form.get("num_factura") or "").strip() or None
        if facturado and not num_factura:
            flash("Ingresa el número de factura", "danger")
        else:
            if facturado or num_factura:
                facturado = 1
            if facturado and tipo == "EP":
                tipo = "FAC"
            if edit:
                db.execute(
                    """
                    UPDATE cuentas SET cliente_id=?, tipo_doc=?, concepto=?, fecha_emision=?,
                      fecha_vencimiento=?, monto=?, facturado=?, num_factura=?
                    WHERE id=?
                    """,
                    (cliente_id, tipo, concepto, emision, venc, monto, facturado, num_factura, edit["id"]),
                )
                core.recalc_cuenta(db, edit["id"])
                db.commit()
                flash("Documento actualizado", "ok")
                db.close()
                return redirect(url_for("cuentas_detalle", cuenta_id=edit["id"]))
            else:
                doc = core.next_code(db, "cuentas", "documento", tipo if tipo in ("EP", "FAC", "ND") else "EP")
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO cuentas
                    (documento, cliente_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento,
                     monto, abonado, saldo, estado, facturado, num_factura)
                    VALUES (?,?,?,?,?,?,?,0,?, 'pendiente', ?, ?)
                    """,
                    (doc, cliente_id, tipo, concepto, emision, venc, monto, monto, facturado, num_factura),
                )
                new_id = cur.lastrowid
                db.commit()
                flash(f"Documento {doc} creado", "ok")
                db.close()
                return redirect(url_for("cuentas_detalle", cuenta_id=new_id))

    db.close()
    return render_template(
        "cuentas/form.html",
        active="cuentas",
        edit=edit,
        clientes=clientes,
        dias=dias,
        today=date.today().isoformat(),
        vence_default=(date.today() + timedelta(days=dias)).isoformat(),
    )


@app.route("/cuentas/<int:cuenta_id>")
@login_required
def cuentas_detalle(cuenta_id: int):
    db = core.conn()
    cuenta = db.execute(
        """
        SELECT cu.*, cl.razon_social FROM cuentas cu
        LEFT JOIN clientes cl ON cl.id=cu.cliente_id WHERE cu.id=?
        """,
        (cuenta_id,),
    ).fetchone()
    if not cuenta:
        flash("No encontrado", "danger")
        db.close()
        return redirect(url_for("cuentas_list"))
    abonos = db.execute(
        "SELECT * FROM abonos WHERE cuenta_id=? ORDER BY id DESC", (cuenta_id,)
    ).fetchall()
    db.close()
    return render_template(
        "cuentas/detalle.html",
        active="cuentas",
        cuenta=cuenta,
        abonos=abonos,
    )


@app.route("/cuentas/<int:cuenta_id>/abono", methods=["GET", "POST"])
@login_required
def cuentas_abono(cuenta_id: int):
    db = core.conn()
    cuenta = db.execute(
        """
        SELECT cu.*, cl.razon_social FROM cuentas cu
        LEFT JOIN clientes cl ON cl.id=cu.cliente_id WHERE cu.id=?
        """,
        (cuenta_id,),
    ).fetchone()
    if not cuenta:
        flash("No encontrado", "danger")
        db.close()
        return redirect(url_for("cuentas_list"))
    if float(cuenta["saldo"] or 0) <= 0:
        flash("Documento ya pagado", "ok")
        db.close()
        return redirect(url_for("cuentas_detalle", cuenta_id=cuenta_id))
    if request.method == "POST":
        monto = float(request.form.get("monto") or 0)
        medio = request.form.get("medio") or "transferencia"
        nota = (request.form.get("nota") or "").strip() or None
        if monto <= 0 or monto > float(cuenta["saldo"]):
            flash("Monto inválido", "danger")
        else:
            db.execute(
                "INSERT INTO abonos (cuenta_id, fecha, monto, medio, nota) VALUES (?,?,?,?,?)",
                (cuenta_id, date.today().isoformat(), monto, medio, nota),
            )
            core.recalc_cuenta(db, cuenta_id)
            db.commit()
            flash("Abono registrado", "ok")
            db.close()
            return redirect(url_for("cuentas_detalle", cuenta_id=cuenta_id))
    db.close()
    return render_template("cuentas/abono.html", active="cuentas", cuenta=cuenta)


@app.route("/cuentas/<int:cuenta_id>/borrar", methods=["POST"])
@login_required
def cuentas_borrar(cuenta_id: int):
    db = core.conn()
    db.execute("UPDATE cotizaciones SET cxc_id=NULL WHERE cxc_id=?", (cuenta_id,))
    db.execute("DELETE FROM abonos WHERE cuenta_id=?", (cuenta_id,))
    db.execute("DELETE FROM cuentas WHERE id=?", (cuenta_id,))
    db.commit()
    db.close()
    flash("Documento eliminado", "ok")
    return redirect(url_for("cuentas_list"))


# ---------------------------------------------------------------------------
# Administración simple
# ---------------------------------------------------------------------------
@app.route("/admin/")
@login_required
def admin():
    db = core.conn()
    empresa = db.execute("SELECT * FROM empresa WHERE id=1").fetchone()
    params = db.execute("SELECT * FROM parametros ORDER BY nombre").fetchall()
    db.close()
    return render_template("admin.html", active="admin", empresa=empresa, params=params)


@app.route("/admin/empresa", methods=["POST"])
@login_required
def admin_empresa():
    db = core.conn()
    db.execute(
        """
        UPDATE empresa SET rut=?, razon_social=?, telefono=?, email=?, direccion=?, region=?, pais=?
        WHERE id=1
        """,
        (
            request.form.get("rut"),
            request.form.get("razon_social"),
            request.form.get("telefono"),
            request.form.get("email"),
            request.form.get("direccion"),
            request.form.get("region"),
            request.form.get("pais") or "Chile",
        ),
    )
    db.commit()
    db.close()
    flash("Empresa actualizada", "ok")
    return redirect(url_for("admin"))


def create_app():
    core.init_db()
    return app


if __name__ == "__main__":
    core.init_db()
    port = int(os.getenv("PORT", "8505"))
    app.run(host="0.0.0.0", port=port, debug=True)
