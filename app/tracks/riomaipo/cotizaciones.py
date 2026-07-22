from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import RIOMAIPO_PREFIX
from app.core.database import get_db
from app.models import Cliente, Cotizacion, CotizacionItem, Parametro
from app.tracks.riomaipo.deps import next_folio, render, set_flash

router = APIRouter(prefix="/cotizaciones")


def _iva_rate(db: Session) -> float:
    param = db.scalar(select(Parametro).where(Parametro.clave == "iva"))
    return (param.as_float() / 100.0) if param else 0.19


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


@router.get("/", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Cotizacion)
        .options(joinedload(Cotizacion.cliente))
        .order_by(Cotizacion.fecha.desc(), Cotizacion.id.desc())
    ).unique().all()
    return render(
        request,
        "riomaipo/cotizaciones/lista.html",
        active="cotizaciones",
        cotizaciones=rows,
    )


@router.get("/nueva", response_class=HTMLResponse)
def nueva(request: Request, db: Session = Depends(get_db)):
    clientes = db.scalars(
        select(Cliente).where(Cliente.activo.is_(True)).order_by(Cliente.razon_social)
    ).all()
    cemento = db.scalar(select(Parametro).where(Parametro.clave == "precio_cemento_saco"))
    maestro = db.scalar(select(Parametro).where(Parametro.clave == "costo_hora_maestro"))
    return render(
        request,
        "riomaipo/cotizaciones/form.html",
        active="cotizaciones",
        clientes=clientes,
        cotizacion=None,
        precio_cemento=cemento.as_float() if cemento else 4500,
        costo_maestro=maestro.as_float() if maestro else 5000,
    )


@router.post("/nueva")
async def crear(
    request: Request,
    cliente_id: int = Form(...),
    obra: str = Form(...),
    descripcion: str = Form(""),
    estado: str = Form("borrador"),
    db: Session = Depends(get_db),
):
    form = await request.form()
    partidas = _as_list(form.getlist("partida"))
    unidades = _as_list(form.getlist("unidad"))
    cantidades = _as_list(form.getlist("cantidad"))
    precios = _as_list(form.getlist("precio_unitario"))

    iva_rate = _iva_rate(db)
    items: list[CotizacionItem] = []
    subtotal = 0.0
    for p, u, c, pu in zip(partidas, unidades, cantidades, precios):
        if not str(p).strip():
            continue
        total = float(c) * float(pu)
        subtotal += total
        items.append(
            CotizacionItem(
                partida=str(p).strip(),
                unidad=str(u).strip() or "m2",
                cantidad=float(c),
                precio_unitario=float(pu),
                total=total,
            )
        )

    cot = Cotizacion(
        folio=next_folio(db, Cotizacion, "folio", "COT-RM"),
        cliente_id=cliente_id,
        obra=obra.strip(),
        descripcion=descripcion.strip() or None,
        estado=estado,
        fecha=date.today(),
        subtotal=subtotal,
        iva=round(subtotal * iva_rate),
        total=subtotal + round(subtotal * iva_rate),
        items=items,
    )
    db.add(cot)
    db.commit()
    set_flash(request, f"Cotización {cot.folio} creada.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/cotizaciones/{cot.id}", status_code=303)


@router.get("/{cotizacion_id}", response_class=HTMLResponse)
def detalle(cotizacion_id: int, request: Request, db: Session = Depends(get_db)):
    cot = db.scalar(
        select(Cotizacion)
        .options(joinedload(Cotizacion.cliente), joinedload(Cotizacion.items))
        .where(Cotizacion.id == cotizacion_id)
    )
    if not cot:
        set_flash(request, "Cotización no encontrada.", "error")
        return RedirectResponse(f"{RIOMAIPO_PREFIX}/cotizaciones/", status_code=303)
    return render(
        request,
        "riomaipo/cotizaciones/detalle.html",
        active="cotizaciones",
        cotizacion=cot,
    )


@router.post("/{cotizacion_id}/estado")
def cambiar_estado(
    cotizacion_id: int,
    request: Request,
    estado: str = Form(...),
    db: Session = Depends(get_db),
):
    cot = db.get(Cotizacion, cotizacion_id)
    if cot:
        cot.estado = estado
        db.commit()
        set_flash(request, f"Estado actualizado a «{estado}».")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/cotizaciones/{cotizacion_id}", status_code=303)
