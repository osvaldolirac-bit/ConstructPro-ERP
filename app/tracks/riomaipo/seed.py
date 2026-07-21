"""Datos iniciales del carril Río Maipo (solo si la BD está vacía)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cliente, Cotizacion, CotizacionItem, CuentaPorCobrar, Obra, Parametro


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Cliente.id).limit(1)):
        return

    clientes = [
        Cliente(
            rut="76.123.456-7",
            razon_social="Inmobiliaria Valle Sur SpA",
            giro="Desarrollo inmobiliario",
            contacto="Carolina Méndez",
            email="compras@vallesur.cl",
            telefono="+56 9 8765 4321",
            direccion="Av. Las Condes 12000, Santiago",
        ),
        Cliente(
            rut="77.987.654-3",
            razon_social="Constructora Andes Ltda.",
            giro="Obras civiles",
            contacto="Pedro Rojas",
            email="admin@andesltda.cl",
            telefono="+56 2 2345 6789",
            direccion="Camino El Alba 450, Puente Alto",
        ),
    ]
    db.add_all(clientes)
    db.flush()

    db.add_all(
        [
            Obra(
                codigo="RM-001",
                nombre="Condominio Río Maipo",
                ubicacion="Buin",
                estado="activa",
                avance=62.0,
            ),
            Obra(
                codigo="RM-002",
                nombre="Bodega Central",
                ubicacion="San Bernardo",
                estado="activa",
                avance=38.0,
            ),
        ]
    )

    db.add_all(
        [
            Parametro(
                clave="precio_cemento_saco",
                nombre="Precio saco cemento",
                valor="4500",
                tipo="numero",
                unidad="CLP",
                descripcion="Precio de referencia para APU",
            ),
            Parametro(
                clave="costo_hora_maestro",
                nombre="Costo hora maestro",
                valor="5000",
                tipo="numero",
                unidad="CLP/h",
                descripcion="Mano de obra calificada",
            ),
            Parametro(
                clave="porcentaje_retencion",
                nombre="Retención anticipo",
                valor="10",
                tipo="porcentaje",
                unidad="%",
                descripcion="Retención por defecto en estados de pago",
            ),
            Parametro(
                clave="iva",
                nombre="IVA",
                valor="19",
                tipo="porcentaje",
                unidad="%",
                descripcion="Impuesto al valor agregado",
            ),
        ]
    )

    cot = Cotizacion(
        folio="COT-RM-0001",
        cliente_id=clientes[0].id,
        obra="Condominio Río Maipo",
        descripcion="Hormigón y terminaciones etapa 1",
        estado="enviada",
        fecha=date.today() - timedelta(days=12),
    )
    items = [
        CotizacionItem(
            partida="Radier hormigón H25",
            unidad="m2",
            cantidad=420,
            precio_unitario=18500,
            total=420 * 18500,
        ),
        CotizacionItem(
            partida="Estuco exterior",
            unidad="m2",
            cantidad=860,
            precio_unitario=9200,
            total=860 * 9200,
        ),
    ]
    cot.subtotal = sum(i.total for i in items)
    cot.iva = round(cot.subtotal * 0.19)
    cot.total = cot.subtotal + cot.iva
    cot.items = items
    db.add(cot)

    cxc_rows = [
        CuentaPorCobrar(
            documento="EP-001",
            cliente_id=clientes[0].id,
            obra="Condominio Río Maipo",
            concepto="Estado de pago N°1",
            fecha_emision=date.today() - timedelta(days=40),
            fecha_vencimiento=date.today() - timedelta(days=10),
            monto=15_000_000,
            retenido=1_500_000,
            abonado=8_000_000,
        ),
        CuentaPorCobrar(
            documento="EP-002",
            cliente_id=clientes[1].id,
            obra="Bodega Central",
            concepto="Estado de pago N°1",
            fecha_emision=date.today() - timedelta(days=20),
            fecha_vencimiento=date.today() + timedelta(days=10),
            monto=8_000_000,
            retenido=800_000,
            abonado=0,
        ),
    ]
    for row in cxc_rows:
        row.recalcular()
    db.add_all(cxc_rows)
    db.commit()
