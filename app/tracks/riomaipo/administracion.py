from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import RIOMAIPO_PREFIX
from app.core.database import get_db
from app.models import Cliente, Obra, Parametro
from app.tracks.riomaipo.deps import render, set_flash

router = APIRouter(prefix="/administracion")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "riomaipo/administracion/index.html",
        active="administracion",
        clientes_count=len(db.scalars(select(Cliente)).all()),
        parametros_count=len(db.scalars(select(Parametro)).all()),
        obras_count=len(db.scalars(select(Obra)).all()),
    )


@router.get("/clientes", response_class=HTMLResponse)
def clientes(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Cliente).order_by(Cliente.razon_social)).all()
    return render(
        request,
        "riomaipo/administracion/clientes.html",
        active="administracion",
        clientes=rows,
    )


@router.post("/clientes")
def crear_cliente(
    request: Request,
    rut: str = Form(...),
    razon_social: str = Form(...),
    giro: str = Form(""),
    contacto: str = Form(""),
    email: str = Form(""),
    telefono: str = Form(""),
    direccion: str = Form(""),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Cliente).where(Cliente.rut == rut.strip()))
    if exists:
        set_flash(request, "Ya existe un cliente con ese RUT.", "error")
        return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/clientes", status_code=303)

    db.add(
        Cliente(
            rut=rut.strip(),
            razon_social=razon_social.strip(),
            giro=giro.strip() or None,
            contacto=contacto.strip() or None,
            email=email.strip() or None,
            telefono=telefono.strip() or None,
            direccion=direccion.strip() or None,
        )
    )
    db.commit()
    set_flash(request, "Cliente creado correctamente.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/clientes", status_code=303)


@router.post("/clientes/{cliente_id}/toggle")
def toggle_cliente(cliente_id: int, request: Request, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if cliente:
        cliente.activo = not cliente.activo
        db.commit()
        set_flash(request, f"Cliente «{cliente.razon_social}» actualizado.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/clientes", status_code=303)


@router.get("/parametros", response_class=HTMLResponse)
def parametros(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Parametro).order_by(Parametro.nombre)).all()
    return render(
        request,
        "riomaipo/administracion/parametros.html",
        active="administracion",
        parametros=rows,
    )


@router.post("/parametros")
def crear_parametro(
    request: Request,
    clave: str = Form(...),
    nombre: str = Form(...),
    valor: str = Form(...),
    tipo: str = Form("texto"),
    unidad: str = Form(""),
    descripcion: str = Form(""),
    db: Session = Depends(get_db),
):
    clave_norm = clave.strip().lower().replace(" ", "_")
    exists = db.scalar(select(Parametro).where(Parametro.clave == clave_norm))
    if exists:
        set_flash(request, "Ya existe un parámetro con esa clave.", "error")
        return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/parametros", status_code=303)

    db.add(
        Parametro(
            clave=clave_norm,
            nombre=nombre.strip(),
            valor=valor.strip(),
            tipo=tipo,
            unidad=unidad.strip() or None,
            descripcion=descripcion.strip() or None,
        )
    )
    db.commit()
    set_flash(request, "Parámetro creado.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/parametros", status_code=303)


@router.post("/parametros/{parametro_id}")
def actualizar_parametro(
    parametro_id: int,
    request: Request,
    valor: str = Form(...),
    db: Session = Depends(get_db),
):
    param = db.get(Parametro, parametro_id)
    if param:
        param.valor = valor.strip()
        db.commit()
        set_flash(request, f"Parámetro «{param.nombre}» actualizado.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/parametros", status_code=303)


@router.get("/obras", response_class=HTMLResponse)
def obras(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Obra).order_by(Obra.nombre)).all()
    return render(
        request,
        "riomaipo/administracion/obras.html",
        active="administracion",
        obras=rows,
    )


@router.post("/obras")
def crear_obra(
    request: Request,
    codigo: str = Form(...),
    nombre: str = Form(...),
    ubicacion: str = Form(""),
    estado: str = Form("activa"),
    avance: float = Form(0),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Obra).where(Obra.codigo == codigo.strip()))
    if exists:
        set_flash(request, "Ya existe una obra con ese código.", "error")
        return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/obras", status_code=303)

    db.add(
        Obra(
            codigo=codigo.strip().upper(),
            nombre=nombre.strip(),
            ubicacion=ubicacion.strip() or None,
            estado=estado,
            avance=max(0.0, min(100.0, float(avance))),
        )
    )
    db.commit()
    set_flash(request, "Obra registrada.")
    return RedirectResponse(f"{RIOMAIPO_PREFIX}/administracion/obras", status_code=303)
