from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Cliente, Cotizacion, CuentaPorCobrar, Obra
from app.tracks.riomaipo.deps import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_cxc = db.scalar(select(func.coalesce(func.sum(CuentaPorCobrar.saldo), 0))) or 0
    total_facturado = db.scalar(select(func.coalesce(func.sum(CuentaPorCobrar.monto), 0))) or 0
    total_abonado = db.scalar(select(func.coalesce(func.sum(CuentaPorCobrar.abonado), 0))) or 0
    cot_count = db.scalar(select(func.count()).select_from(Cotizacion)) or 0
    clientes_activos = db.scalar(
        select(func.count()).select_from(Cliente).where(Cliente.activo.is_(True))
    ) or 0
    obras = db.scalars(select(Obra).order_by(Obra.nombre)).all()
    cotizaciones = db.scalars(
        select(Cotizacion).order_by(Cotizacion.fecha.desc()).limit(5)
    ).all()
    cuentas = db.scalars(
        select(CuentaPorCobrar).order_by(CuentaPorCobrar.fecha_emision.desc()).limit(5)
    ).all()

    estados = {
        "pendiente": db.scalar(
            select(func.count())
            .select_from(CuentaPorCobrar)
            .where(CuentaPorCobrar.estado == "pendiente")
        )
        or 0,
        "parcial": db.scalar(
            select(func.count())
            .select_from(CuentaPorCobrar)
            .where(CuentaPorCobrar.estado == "parcial")
        )
        or 0,
        "pagado": db.scalar(
            select(func.count())
            .select_from(CuentaPorCobrar)
            .where(CuentaPorCobrar.estado == "pagado")
        )
        or 0,
    }

    return render(
        request,
        "riomaipo/dashboard.html",
        active="dashboard",
        total_cxc=total_cxc,
        total_facturado=total_facturado,
        total_abonado=total_abonado,
        cot_count=cot_count,
        clientes_activos=clientes_activos,
        obras=obras,
        cotizaciones=cotizaciones,
        cuentas=cuentas,
        estados=estados,
    )
