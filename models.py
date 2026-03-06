from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from database import Base

class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    referencia = Column(String, index=True) # Ej: 123456
    banco_origen = Column(String)           # Ej: Banco Venezuela
    monto = Column(Float)                   # Ej: 100.50
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())
    ruta_imagen = Column(String)            # Guardamos dónde quedó la foto
    file_hash = Column(String, index=True, unique=True, nullable=True)


class PagoHistory(Base):
    __tablename__ = "pagos_history"

    id = Column(Integer, primary_key=True, index=True)
    pago_id = Column(Integer, index=True)
    accion = Column(String)  # 'edit' | 'delete' | 'create'
    detalles = Column(String)  # JSON pequeño con cambios o razón
    usuario = Column(String, nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
