#!/usr/bin/env python3
"""Importa datos exportados de SOLUERP al SQLite de Río Maipo."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path


def norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def money_ok(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def find_cliente_id(cur: sqlite3.Cursor, nombre: str, cache: dict[str, int]) -> int:
    key = norm_name(nombre)
    if key in cache:
        return cache[key]
    # exact
    row = cur.execute(
        "SELECT id, razon_social FROM clientes WHERE lower(razon_social)=?",
        (key,),
    ).fetchone()
    if row:
        cache[key] = row[0]
        return row[0]
    # contains / startswith
    rows = cur.execute("SELECT id, razon_social FROM clientes").fetchall()
    for cid, rs in rows:
        n = norm_name(rs)
        if n and (n in key or key in n or key.startswith(n) or n.startswith(key[:20])):
            cache[key] = cid
            return cid
    # create
    cur.execute(
        """
        INSERT INTO clientes (rut, razon_social, contacto, telefono, email, direccion, comuna, activo, creado_en)
        VALUES (?,?,?,?,?,?,?,1,?)
        """,
        (None, nombre.strip()[:200], None, None, None, None, None, date.today().isoformat()),
    )
    cache[key] = cur.lastrowid
    return cur.lastrowid


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: import_soluerp.py <parsed.json> <cot_items.json> [db_path]")
        return 2
    parsed_path = Path(sys.argv[1])
    items_path = Path(sys.argv[2])
    db_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("data/riomaipo_erp.db")

    data = json.loads(parsed_path.read_text(encoding="utf-8"))
    items_by_solu = json.loads(items_path.read_text(encoding="utf-8"))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")

    # Wipe transactional/master data (keep schema)
    for table in [
        "abonos",
        "cotizacion_items",
        "cuentas",
        "cotizaciones",
        "productos",
        "proveedores",
        "clientes",
    ]:
        cur.execute(f"DELETE FROM {table}")

    # Empresa
    emp = data.get("empresa") or {}
    cur.execute(
        """
        INSERT INTO empresa (id, rut, razon_social, telefono, email, direccion, region, pais)
        VALUES (1,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          rut=excluded.rut, razon_social=excluded.razon_social, telefono=excluded.telefono,
          email=excluded.email, direccion=excluded.direccion, region=excluded.region, pais=excluded.pais
        """,
        (
            emp.get("rut"),
            emp.get("razon_social") or "Constructora Rio Maipo S.A.",
            emp.get("telefono"),
            emp.get("email"),
            emp.get("direccion"),
            emp.get("region"),
            emp.get("pais") or "Chile",
        ),
    )

    # Ensure parametros exist
    if cur.execute("SELECT COUNT(*) FROM parametros").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO parametros (clave, nombre, valor, unidad) VALUES (?,?,?,?)",
            [
                ("iva", "IVA", "19", "%"),
                ("validez_cotizacion", "Validez cotización", "30", "días"),
                ("dias_credito", "Días crédito CxC", "30", "días"),
                ("alerta_mora", "Alerta mora desde", "1", "días"),
            ],
        )

    cache: dict[str, int] = {}
    # Clientes
    for c in data.get("clientes") or []:
        rut = (c.get("rut") or "").strip() or None
        razon = (c.get("razon_social") or "").strip()
        if not razon:
            continue
        try:
            cur.execute(
                """
                INSERT INTO clientes (rut, razon_social, contacto, telefono, email, direccion, comuna, activo, creado_en)
                VALUES (?,?,?,?,?,?,?,1,?)
                """,
                (
                    rut,
                    razon,
                    c.get("contacto") or None,
                    c.get("telefono") or None,
                    c.get("email") or None,
                    c.get("direccion") or None,
                    c.get("comuna") or None,
                    date.today().isoformat(),
                ),
            )
        except sqlite3.IntegrityError:
            cur.execute(
                """
                UPDATE clientes SET razon_social=?, contacto=?, telefono=?, email=?, direccion=?, comuna=?, activo=1
                WHERE rut=?
                """,
                (
                    razon,
                    c.get("contacto") or None,
                    c.get("telefono") or None,
                    c.get("email") or None,
                    c.get("direccion") or None,
                    c.get("comuna") or None,
                    rut,
                ),
            )
        row = cur.execute("SELECT id FROM clientes WHERE razon_social=?", (razon,)).fetchone()
        if row:
            cache[norm_name(razon)] = row[0]

    # Proveedores / productos (si vienen)
    for p in data.get("proveedores") or []:
        if not p.get("razon_social"):
            continue
        cur.execute(
            """
            INSERT OR IGNORE INTO proveedores (rut, razon_social, contacto, telefono, email, activo)
            VALUES (?,?,?,?,?,1)
            """,
            (
                p.get("rut") or None,
                p["razon_social"],
                p.get("contacto"),
                p.get("telefono"),
                p.get("email"),
            ),
        )

    for p in data.get("productos") or []:
        if not p.get("nombre"):
            continue
        codigo = (p.get("codigo") or "").strip() or None
        cur.execute(
            """
            INSERT OR IGNORE INTO productos (codigo, nombre, unidad, precio, activo)
            VALUES (?,?,?,?,1)
            """,
            (codigo, p["nombre"], "un", money_ok(p.get("precio"))),
        )

    # Map solu cotizacion id -> our folio via parsed list
    solu_id_to_cot = {}
    for cot in data.get("cotizaciones") or []:
        cliente_nombre = cot.get("cliente") or "Cliente SOLUERP"
        cliente_id = find_cliente_id(cur, cliente_nombre, cache)
        folio = cot.get("folio") or f"COT-{cot.get('numero')}"
        # extract asunto/proyecto from cliente field if long description
        asunto = cliente_nombre
        proyecto = None
        estado = cot.get("estado") or "enviada"
        total = money_ok(cot.get("total"))
        # reconstruct subtotal/iva approx 19%
        subtotal = round(total / 1.19) if total else 0
        iva = round(total - subtotal)
        cur.execute(
            """
            INSERT INTO cotizaciones (folio, cliente_id, asunto, proyecto, estado, fecha, validez_dias, subtotal, iva, total, notas)
            VALUES (?,?,?,?,?,?,30,?,?,?,?)
            """,
            (
                folio,
                cliente_id,
                asunto[:200],
                proyecto,
                estado,
                cot.get("fecha") or date.today().isoformat(),
                subtotal,
                iva,
                total,
                "Importado desde SOLUERP",
            ),
        )
        our_id = cur.lastrowid
        for sid in set(cot.get("solu_ids") or []):
            solu_id_to_cot[str(sid)] = our_id

        # line items
        lineas = []
        for sid in set(cot.get("solu_ids") or []):
            detail = items_by_solu.get(str(sid)) or {}
            if detail.get("lineas"):
                lineas = detail["lineas"]
                break
        if lineas:
            for ln in lineas:
                cur.execute(
                    """
                    INSERT INTO cotizacion_items (cotizacion_id, producto_id, descripcion, unidad, cantidad, precio_unitario, total)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        our_id,
                        None,
                        (ln.get("descripcion") or "Ítem")[:300],
                        ln.get("unidad") or "un",
                        money_ok(ln.get("cantidad")) or 1,
                        money_ok(ln.get("precio_unitario")),
                        money_ok(ln.get("total")),
                    ),
                )
        else:
            # single summary item
            if total:
                cur.execute(
                    """
                    INSERT INTO cotizacion_items (cotizacion_id, producto_id, descripcion, unidad, cantidad, precio_unitario, total)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (our_id, None, asunto[:200], "gl", 1, total, total),
                )

    # Cuentas
    seen_docs = set()
    for cu in data.get("cuentas") or []:
        doc = (cu.get("documento") or "").strip()
        if not doc or doc in seen_docs:
            # uniquify
            base = doc or "DOC"
            i = 2
            while f"{base}-{i}" in seen_docs:
                i += 1
            doc = f"{base}-{i}" if doc in seen_docs else base
        seen_docs.add(doc)
        cliente_id = find_cliente_id(cur, cu.get("cliente") or "Cliente SOLUERP", cache)
        monto = money_ok(cu.get("monto"))
        abonado = money_ok(cu.get("abonado"))
        saldo = money_ok(cu.get("saldo"))
        if saldo <= 0 and abonado <= 0 and monto > 0:
            saldo = monto
        estado = cu.get("estado") or ("pagado" if saldo <= 0 else "pendiente")
        if saldo <= 0:
            estado = "pagado"
        elif abonado > 0:
            estado = "parcial"
        cur.execute(
            """
            INSERT INTO cuentas (documento, cliente_id, cotizacion_id, tipo_doc, concepto, fecha_emision, fecha_vencimiento, monto, abonado, saldo, estado)
            VALUES (?,?,NULL,?,?,?,?,?,?,?,?)
            """,
            (
                doc[:60],
                cliente_id,
                (cu.get("tipo_doc") or "FAC")[:20],
                f"Importado SOLUERP {cu.get('numero') or ''}".strip(),
                cu.get("fecha_emision") or date.today().isoformat(),
                cu.get("fecha_vencimiento"),
                monto,
                abonado,
                saldo,
                estado,
            ),
        )
        cuenta_id = cur.lastrowid
        if abonado > 0:
            cur.execute(
                "INSERT INTO abonos (cuenta_id, fecha, monto, medio, nota) VALUES (?,?,?,?,?)",
                (
                    cuenta_id,
                    cu.get("fecha_emision") or date.today().isoformat(),
                    abonado,
                    "importado",
                    "Saldo/abono importado desde SOLUERP",
                ),
            )

    con.commit()

    stats = {
        "clientes": cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
        "cotizaciones": cur.execute("SELECT COUNT(*) FROM cotizaciones").fetchone()[0],
        "items": cur.execute("SELECT COUNT(*) FROM cotizacion_items").fetchone()[0],
        "cuentas": cur.execute("SELECT COUNT(*) FROM cuentas").fetchone()[0],
        "abonos": cur.execute("SELECT COUNT(*) FROM abonos").fetchone()[0],
        "proveedores": cur.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0],
        "productos": cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0],
        "empresa": cur.execute("SELECT razon_social FROM empresa WHERE id=1").fetchone()[0],
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
