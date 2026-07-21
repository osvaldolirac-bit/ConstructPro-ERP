from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Parametro(Base):
    """Parámetros de negocio (precios base, % retención, etc.)."""

    __tablename__ = "riomaipo_parametros"
    __table_args__ = (UniqueConstraint("clave", name="uq_riomaipo_parametro_clave"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(80), index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    valor: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str] = mapped_column(String(20), default="texto")  # texto | numero | porcentaje
    unidad: Mapped[str | None] = mapped_column(String(40), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def as_float(self) -> float:
        try:
            return float(self.valor)
        except (TypeError, ValueError):
            return 0.0


class Obra(Base):
    """Obras / proyectos del carril Río Maipo."""

    __tablename__ = "riomaipo_obras"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado: Mapped[str] = mapped_column(String(40), default="activa")
    avance: Mapped[float] = mapped_column(Float, default=0.0)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
