from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum

class EstadoPago(str, Enum):
    no_verificado = "no_verificado"
    verificado = "verificado"
    falso = "falso"

class EstadoUpdate(BaseModel):
    estado: EstadoPago

class VisionBankDetectionRequest(BaseModel):
    image_base64: str

class ClienteBase(BaseModel):
    nombre: str
    cedula: str
    telefono: Optional[str] = None

    @field_validator('cedula', 'telefono')
    @classmethod
    def check_numeric(cls, v):
        if v is not None and v != "":
            v = v.strip()
            if not v.isdigit():
                raise ValueError('Este campo debe contener solo números')
        return v

class Cliente(ClienteBase):
    id: int
    class Config:
        from_attributes = True

class PagoParaCliente(BaseModel):
    id: int
    referencia: str
    monto: float
    monto_usd: Optional[float] = None
    tasa_cambio: Optional[float] = None
    fecha_registro: datetime
    estado: str
    class Config:
        from_attributes = True

class PagoResponse(BaseModel):
    id: int
    referencia: str
    banco: str
    banco_destino: Optional[str] = None
    monto: float
    monto_usd: Optional[float] = None
    tasa_momento: Optional[float] = None
    tasa_cambio: Optional[float] = None
    fecha_registro: datetime
    estado: str
    cliente_id: Optional[int] = None
    cliente: Optional[Cliente] = None
    ruta_imagen: Optional[str] = None
    es_chatbot: bool = False
    class Config:
        from_attributes = True

class ClienteConPagos(Cliente):
    pagos: List[PagoParaCliente] = []
    total_bs: float = 0.0
    total_usd: float = 0.0
    total_pagos: int = 0

class ReporteResumen(BaseModel):
    periodo: str
    desde: datetime
    hasta: datetime
    total_bs: float
    total_usd: float
    conteo: int

class ReporteResponse(BaseModel):
    tipo_reporte: str
    resultados: List[ReporteResumen]
    total_bs: float
    total_usd: float
    total_pagos: int

class PagosResponse(BaseModel):
    items: List[PagoResponse]
    total: int
    page: int
    pages: int

class PagoManual(BaseModel):
    banco: str
    referencia: str
    monto: float
    cliente_id: Optional[int] = None

    @field_validator('banco', 'referencia', mode='before')
    def validar_texto_requerido(cls, valor, info):
        if isinstance(valor, str):
            valor = valor.strip()
        if not valor:
            field_name = info.field_name.capitalize()
            raise ValueError(f"{field_name} es obligatorio y no puede estar vacío.")
        return valor

    @field_validator('referencia')
    def validar_referencia(cls, valor):
        if isinstance(valor, str) and not valor.isdigit():
            raise ValueError("La referencia debe contener solo números.")
        return valor

    @field_validator('monto')
    def validar_monto(cls, valor):
        if valor is None:
            raise ValueError("El monto es obligatorio y debe ser un número mayor a cero.")
        try:
            monto = float(valor)
        except (TypeError, ValueError):
            raise ValueError("El monto debe ser un número válido mayor a cero.")
        if monto <= 0:
            raise ValueError("El monto debe ser mayor a cero.")
        return monto

class ConversionRequest(BaseModel):
    monto_bs: float

class ConversionResponse(BaseModel):
    monto_bs: float
    tasa_bcv: float
    fecha_consulta: datetime
    monto_usd: float
    origen: str
    es_fallback: bool = False

class GestionApiKey(BaseModel):
    api_key: str

class GestionCredentials(BaseModel):
    admin_user: str
    admin_pass: str

class ConfirmBody(BaseModel):
    confirm: bool

class TasaBCVUpdate(BaseModel):
    tasa_bcv: float

class ChatQuery(BaseModel):
    pregunta: str
