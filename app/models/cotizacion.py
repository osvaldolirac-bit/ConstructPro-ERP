from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Cotizacion(Base):
    __tablename__ = "riomaipo_cotizaciones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    folio: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("riomaipo_clientes.id"), nullable=True)
    obra: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(40), default="borrador")
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    validez_dias: Mapped[int] = mapped_column(Integer, default=30)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    iva: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="cotizaciones")
    items = relationship(
        "CotizacionItem",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        order_by="CotizacionItem.id",
    )


class CotizacionItem(Base):
    __tablename__ = "riomaipo_cotizacion_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("riomaipo_cotizaciones.id"))
    partida: Mapped[str] = mapped_column(String(200))
    unidad: Mapped[str] = mapped_column(String(20), default="m2")
    cantidad: Mapped[float] = mapped_column(Float, default=1.0)
    precio_unitario: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)

    cotizacion = relationship("Cotizacion", back_populates="items")
