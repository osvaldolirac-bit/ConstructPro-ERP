"""Carril independiente Río Maipo: erpmaster.cl/riomaipo."""

from __future__ import annotations

from fastapi import APIRouter

from app.tracks.riomaipo import administracion, cotizaciones, cuentas_por_cobrar, dashboard

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(cotizaciones.router)
router.include_router(cuentas_por_cobrar.router)
router.include_router(administracion.router)
