from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import RIOMAIPO_PREFIX
from app.core.database import get_db
from app.models import Cliente, CuentaPorCobrar, Parametro
from app.tracks.riomaipo.deps import next_folio, render, set_flash

router = APIRouter(prefix="/cuentas-por-cobrar")


def _retencion_rate(db: Session) -> float:
    param = db.scalar(select(Parametro).where(Parametro.clave == "porcentaje_retencion"))
    return (param.as_float() / 100.0) if param else 0.10


@router.get("/", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(CuentaPorCobrar)
        .options(joinedload(CuentaPorCobrar.cliente))
        .order_by(CuentaPorCobrar.fecha_emision.desc())
    ).unique().all()
    saldo_total = sum(r.saldo for r in rows)
    return render(
        request,
        "riomaipo/cuentas/lista.html",
        active="cuentas",
        cuentas=rows,
        saldo_total=saldo_total,
    )


@router.get("/nueva", response_class=HTMLResponse)
def nueva(request: Request, db: Session = Depends(get_db)):
    clientes = db.scalars(
        select(Cliente).where(Cliente.activo.is_(True)).order_by(Cliente.razon_social)
    ).all()
    return render(
        request,
        "riomaipo/cuentas/form.html",
        active="cuentas",
        clientes=clientes,
        retencion_pct=_retencion_rate(db) * 100,
    )


@router.post("/nueva")
def crear(
    request: Request,
    cliente_id: int = Form(...),
    obra: str = Form(...),
    concepto: str = Form(""),
    monto: float = Form(...),
    aplicar_retencion: str = Form("si"),
    dias_vencimiento: int = Form(30),
    db: Session = Depends(get_db),
):
    retenido = round(monto * _retencion_rate(db), 0) if aplicar_retencion == "si" else 0.0
    row = CuentaPorCobrar(
        documento=next_folio(db, CuentaPorCobrar, "documento", "EP-RM"),
        cliente_id=cliente_id,
        obra=obra.strip(),
        concepto=concepto.strip() or None,
        fecha_emision=date.today(),
        fecha_vencimiento=date.today() + timedelta(days=dias_vencimiento),
        monto=float(monto),
        retenido=retenido,
        abonado=0.0,
    )
    row.recalcular()
    db.add(row)
    db.commit()
    set_flash(request, f"Documento {row.documento} registrado.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/cuentas-por-cobrar/", status_code=303)


@router.post("/{cuenta_id}/abono")
def registrar_abono(
    cuenta_id: int,
    request: Request,
    abono: float = Form(...),
    db: Session = Depends(get_db),
):
    row = db.get(CuentaPorCobrar, cuenta_id)
    if row:
        row.abonado = float(row.abonado) + max(0.0, float(abono))
        row.recalcular()
        db.commit()
        set_flash(request, f"Abono registrado en {row.documento}.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/cuentas-por-cobrar/", status_code=303)
