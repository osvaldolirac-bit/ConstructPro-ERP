"""Helpers de formato CLP y fechas."""

from __future__ import annotations

from datetime import date, datetime


def clp(value: float | int | None) -> str:
    amount = int(round(float(value or 0)))
    return f"${amount:,.0f}".replace(",", ".") + " CLP"


def fecha_corta(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")
