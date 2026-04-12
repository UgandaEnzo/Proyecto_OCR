from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True, nullable=False)
    cedula = Column(String, unique=True, index=True, nullable=False)
    telefono = Column(String, index=True, nullable=True)

    # Relación bidireccional: desde un cliente se puede acceder a sus pagos
    pagos = relationship("Pago", back_populates="cliente")

class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    referencia = Column(String, index=True) # Ej: 123456
    banco = Column(String, index=True)      # Campo unificado para el banco (Origen/Emisor)
    banco_destino = Column(String, nullable=True) # Ej: Banesco
    monto = Column(Float)                   # Ej: 100.50
    monto_usd = Column(Float, nullable=True, default=0.0)
    tasa_momento = Column(Float, nullable=True, default=1.0)
    tasa_cambio = Column(Float, nullable=True, default=1.0)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())
    ruta_imagen = Column(String)            # Guardamos dónde quedó la foto
    file_hash = Column(String, index=True, unique=True, nullable=True)
    estado = Column(String, default="no_verificado", server_default="no_verificado", index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    # Relación bidireccional: desde un pago se accede al cliente
    cliente = relationship("Cliente", back_populates="pagos")


class PagoHistory(Base):
    __tablename__ = "pagos_history"

    id = Column(Integer, primary_key=True, index=True)
    pago_id = Column(Integer, index=True)
    accion = Column(String)  # 'edit' | 'delete' | 'create' | 'update_status'
    detalles = Column(String)  # JSON pequeño con cambios o razón
    usuario = Column(String, nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())


class TasaCambio(Base):
    __tablename__ = "tasas_cambio"

    id = Column(Integer, primary_key=True, index=True)
    proveedor = Column(String, default="BCV")
    monto_tasa = Column(Float, nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
