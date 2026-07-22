from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CuentaPorCobrar(Base):
    __tablename__ = "riomaipo_cuentas_por_cobrar"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    documento: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("riomaipo_clientes.id"), nullable=True)
    obra: Mapped[str] = mapped_column(String(200))
    concepto: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_emision: Mapped[date] = mapped_column(Date, default=date.today)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    monto: Mapped[float] = mapped_column(Float, default=0.0)
    retenido: Mapped[float] = mapped_column(Float, default=0.0)
    abonado: Mapped[float] = mapped_column(Float, default=0.0)
    saldo: Mapped[float] = mapped_column(Float, default=0.0)
    estado: Mapped[str] = mapped_column(String(40), default="pendiente")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="cuentas")

    def recalcular(self) -> None:
        self.saldo = max(0.0, float(self.monto) - float(self.retenido) - float(self.abonado))
        if self.saldo <= 0:
            self.estado = "pagado"
        elif self.abonado > 0 or self.retenido > 0:
            self.estado = "parcial"
        else:
            self.estado = "pendiente"
