import os
import sys
import shutil
import uuid
import logging
import hashlib
import traceback
import io
from enum import Enum
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import requests

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Header, Body
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from logging.handlers import RotatingFileHandler
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, exc as sa_exc, text
from datetime import datetime
from pydantic import BaseModel, field_validator

from exchange import get_tasa_bcv, convertir_payments, TasaNoDisponibleError

# Carga las variables de entorno desde un archivo .env ANTES de importar módulos locales
base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
dotenv_path = base_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Importamos tus módulos (ahora database.py es más robusto)
from database import engine, get_db, Base
import models
import ocr_engine  # Tu motor de OCR
import bank_rules
def _setup_logging() -> logging.Logger:
    """Configura un logger robusto que escribe en consola y en archivos rotativos."""
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("ocr_api")
    if logger.handlers:
        return logger

    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    file_handler = RotatingFileHandler(
        os.path.join("logs", "app.log"),
        maxBytes=2 * 1024 * 1024, # Archivos de 2MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    return logger

logger = _setup_logging()

# --- MEJORA: Uso de Lifespan para inicialización limpia ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el inicio y cierre de la aplicación de forma segura."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Sistema de Base de Datos inicializado: Tablas verificadas.")
        
        logger.info("🚀 [SISTEMA] Arquitectura OCR: RapidOCR (Motor Único)")
    except Exception as e:
        logger.error("❌ Error crítico al inicializar la base de datos: %s", e)
    yield

# --- MEJORA: Mover la documentación de la API para liberar la raíz ---
app = FastAPI(
    docs_url="/api/docs", 
    redoc_url=None, 
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# --- MEJORA: Manejadores de errores de base de datos ---
@app.exception_handler(sa_exc.OperationalError)
def handle_db_operational_error(request, exc):
    logger.critical("Error de conexión con la base de datos: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Base de datos no disponible. Revisa la configuración en tu .env."},
    )

@app.exception_handler(UnicodeDecodeError)
def handle_db_unicode_decode_error(request, exc):
    logger.critical("Error de codificación con la base de datos (común en Windows): %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Error de codificación con la BD. Revisa credenciales y considera definir PGCLIENTENCODING en .env."},
    )

# Montar carpetas estáticas
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- RUTA PARA FAVICON ---
@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    else:
        # Si no tienes un favicon, devuelve una respuesta vacía para evitar el error 404 en los logs.
        # El navegador no volverá a pedirlo en esta sesión.
        return Response(status_code=204)

# --- MEJORA: Endpoint de Health Check ---
@app.get("/healthz", include_in_schema=False)
def healthz():
    """Verifica que el servidor está en línea."""
    return {"status": "ok"}

# --- MEJORA: Función para requerir API Key opcional ---
def require_api_key(x_api_key: Optional[str] = Header(None)):
    configured_key = os.getenv("API_KEY")
    if configured_key and (not x_api_key or x_api_key != configured_key):
        raise HTTPException(status_code=401, detail="API key inválida o no proporcionada")
    return True

# --- MODELOS PYDANTIC (Para validar datos que entran) ---

# Modelo para el estado del pago, asegura que solo se usen valores válidos
class EstadoPago(str, Enum):
    no_verificado = "no_verificado"
    verificado = "verificado"
    falso = "falso"

class EstadoUpdate(BaseModel):
    estado: EstadoPago

# Modelos para Clientes
class ClienteBase(BaseModel):
    nombre: str
    cedula: str
    telefono: Optional[str] = None

    @field_validator('cedula', 'telefono')
    @classmethod
    def check_numeric(cls, v):
        if v is not None and v != "" and not v.isdigit():
            raise ValueError('Este campo debe contener solo números')
        return v

class Cliente(ClienteBase):
    id: int
    class Config:
        from_attributes = True

# Modelo para mostrar un pago dentro de la lista de historial de un cliente
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

# Modelo para un pago con datos completos y filtros de banco
class PagoResponse(BaseModel):
    id: int
    referencia: str
    banco: str
    banco_destino: Optional[str] = None
    monto: float
    monto_usd: Optional[float] = None
    tasa_cambio: Optional[float] = None
    fecha_registro: datetime
    estado: str
    cliente_id: Optional[int] = None
    cliente: Optional[Cliente] = None

    class Config:
        from_attributes = True

# Modelo de respuesta para un cliente con su historial de pagos
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

class ConversionRequest(BaseModel):
    monto_bs: float

class ConversionResponse(BaseModel):
    monto_bs: float
    tasa_bcv: float
    fecha_consulta: datetime
    monto_usd: float
    origen: str
    es_fallback: bool = False

class TasaBCVUpdate(BaseModel):
    tasa_bcv: float

class ChatQuery(BaseModel):
    pregunta: str

# --- FUNCIONES AUXILIARES ---
def registrar_auditoria(db: Session, pago_id: int, accion: str, detalles: str):
    """Función para ahorrar trabajo: registra movimientos en el historial"""
    nuevo_historial = models.PagoHistory(
        pago_id=pago_id,
        accion=accion,
        detalles=detalles,
        usuario="sistema_ia"
    )
    db.add(nuevo_historial)
    db.commit()

# --- RUTAS ---

# Redirecciones útiles para la UI del frontend
@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirige a la interfaz web estática."""
    return RedirectResponse(url="/static/index.html")


@app.get("/panel")
async def panel_redirect():
    """Endpoint visible en la documentación que abre la vista del panel web."""
    return RedirectResponse(url="/static/index.html")

# --- NUEVAS RUTAS PARA CLIENTES ---

@app.post("/clientes/", response_model=Cliente, status_code=201)
def crear_cliente(cliente: ClienteBase, db: Session = Depends(get_db)):
    """Crea un nuevo cliente en la base de datos."""
    db_cliente = db.query(models.Cliente).filter(models.Cliente.cedula == cliente.cedula).first()
    if db_cliente:
        raise HTTPException(status_code=409, detail=f"Un cliente con la cédula {cliente.cedula} ya existe.")
    
    nuevo_cliente = models.Cliente(nombre=cliente.nombre, cedula=cliente.cedula, telefono=cliente.telefono)
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    return nuevo_cliente

@app.get("/clientes/", response_model=List[Cliente])
def leer_clientes(q: Optional[str] = None, db: Session = Depends(get_db)):
    """Obtiene una lista de todos los clientes, opcionalmente filtrada."""
    query = db.query(models.Cliente)
    if q:
        query = query.filter(
            (models.Cliente.nombre.ilike(f"%{q}%")) | 
            (models.Cliente.cedula.ilike(f"%{q}%")) |
            (models.Cliente.telefono.ilike(f"%{q}%"))
        )
    return query.all()

@app.put("/clientes/{cliente_id}", response_model=Cliente)
def actualizar_cliente(cliente_id: int, cliente_data: ClienteBase, db: Session = Depends(get_db)):
    db_cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    db_cliente.nombre = cliente_data.nombre
    db_cliente.cedula = cliente_data.cedula
    db_cliente.telefono = cliente_data.telefono
    
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@app.delete("/clientes/{cliente_id}")
def eliminar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    db_cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    db.delete(db_cliente)
    db.commit()
    return {"mensaje": "Cliente eliminado"}

@app.get("/clientes/{cliente_id}/pagos", response_model=ClienteConPagos)
def leer_pagos_de_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtiene los detalles de un cliente y todos sus pagos asociados."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    pagos = cliente.pagos or []
    total_bs = sum(float(p.monto or 0.0) for p in pagos)
    total_usd = sum(float(p.monto_usd or 0.0) for p in pagos)
    total_pagos = len(pagos)

    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "cedula": cliente.cedula,
        "telefono": cliente.telefono,
        "pagos": pagos,
        "total_bs": total_bs,
        "total_usd": total_usd,
        "total_pagos": total_pagos,
    }

@app.post("/IA/consultar/")
async def consultar_datos_ia(query: ChatQuery, db: Session = Depends(get_db)):
    """Permite hacer preguntas sobre los pagos en lenguaje natural."""
    # 1. Consultas rápidas para contexto de negocio
    total_clientes = db.query(models.Cliente).count()
    
    # Mejor cliente (más pagos realizados)
    mejor_cliente = db.query(
        models.Cliente.nombre, 
        func.count(models.Pago.id).label('total')
    ).join(models.Pago).group_by(models.Cliente.id).order_by(text('total DESC')).first()
    nombre_mejor = mejor_cliente.nombre if mejor_cliente else "N/A"

    # Recaudación mes actual
    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    recaudado_mes = db.query(func.sum(models.Pago.monto)).filter(models.Pago.fecha_registro >= inicio_mes).scalar() or 0.0
    
    # Últimos 5 pagos
    ultimos_pagos = db.query(models.Pago).order_by(desc(models.Pago.id)).limit(5).all()
    contexto_pagos = "\n".join([
        f"- Ref: {p.referencia}, Banco: {p.banco}, Monto: {p.monto} Bs, Cliente: {p.cliente.nombre if p.cliente else 'Particular'}" 
        for p in ultimos_pagos
    ])
    
    prompt = f"""
    Eres un asistente contable experto del Sistema de Conciliación.
    DATOS ACTUALES DE LA BASE DE DATOS:
    - Clientes totales: {total_clientes}
    - Mejor cliente (frecuencia): {nombre_mejor}
    - Total recaudado este mes: {recaudado_mes:,.2f} Bs.
    
    ÚLTIMOS 5 PAGOS REGISTRADOS:
    {contexto_pagos}

    INSTRUCCIONES:
    Responde de forma breve y profesional. Si te preguntan sobre ingresos de hoy, usa los últimos pagos como referencia.
    PREGUNTA DEL USUARIO:
    {query.pregunta}
    """
    
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.2
        )
        return {"respuesta": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en consulta IA: {e}")

@app.post("/convertir-a-usd/", response_model=ConversionResponse)
async def convertir_monto_a_usd(data: ConversionRequest, db: Session = Depends(get_db)):
    """Convierte un monto en bolívares a USD usando la tasa BCV con fallback robusto."""
    try:
        result = await convertir_payments(db, data.monto_bs)
    except TasaNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "monto_bs": float(result["monto_bs"]),
        "tasa_bcv": float(result["tasa_bcv"]),
        "fecha_consulta": result["fecha"],
        "monto_usd": float(result["monto_usd"]),
        "origen": result["origen"],
        "es_fallback": result["origen"] != "API",
    }

@app.get("/tasa-bcv/")
async def obtener_tasa_bcv_endpoint(db: Session = Depends(get_db)):
    tasa_info = await get_tasa_bcv(db)
    tasa = float(tasa_info["tasa"])
    origen = tasa_info["origen"]
    fecha = tasa_info["fecha"]
    es_fallback = origen != "API"
    return {"tasa_bcv": tasa, "fecha_consulta": fecha, "origen": origen, "es_fallback": es_fallback}

@app.get("/bancos/")
def listar_bancos():
    return {"bancos": bank_rules.get_available_banks()}

@app.post("/tasa-bcv/")
def set_tasa_bcv(data: TasaBCVUpdate, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    tasa_bcv = data.tasa_bcv
    if tasa_bcv <= 0:
        raise HTTPException(status_code=400, detail="La tasa debe ser mayor que cero")

    tasa_db = db.query(models.TasaCambio).filter(models.TasaCambio.proveedor == "BCV").first()
    if not tasa_db:
        tasa_db = models.TasaCambio(proveedor="BCV", monto_tasa=tasa_bcv)
        db.add(tasa_db)
    else:
        tasa_db.monto_tasa = tasa_bcv
        tasa_db.fecha_actualizacion = func.now()

    db.commit()
    return {"tasa_bcv": tasa_bcv, "mensaje": "Tasa BCV actualizada"}

@app.get("/ver-pagos/")
def leer_pagos(q: Optional[str] = None, banco: Optional[str] = None, page: int = 1, size: int = 10, limit: Optional[int] = None, offset: Optional[int] = None, db: Session = Depends(get_db)):
    # Compatibilidad: Si el frontend envía limit/offset (cache antiguo), calculamos la página
    if limit:
        size = limit
    if offset is not None:
        page = (offset // size) + 1

    # Lógica de paginación de SQL
    # Si page=1, skip=0. Si page=2, skip=10.
    skip = (page - 1) * size

    query = db.query(models.Pago)
    if q:
        query = query.filter(models.Pago.referencia.contains(q))
    if banco:
        termino = f"%{banco}%"
        query = query.filter(
            models.Pago.banco.ilike(termino)
        )

    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()

    # Evitar COUNT(*) caro en tablas muy grandes; si la tabla es pequeña o la solicitud lo pide, calcularlo
    total = None
    if os.getenv("FORCE_EXACT_COUNT", "false").lower() == "true":
        total = db.query(models.Pago).count()
    elif len(pagos) < size or page == 1:
        # Para la primera página (y pocos resultados) podemos usar un COUNT real sin mucho coste
        total = db.query(models.Pago).count()
    else:
        # Aprox. by using last row index o estimación de Postgres
        try:
            total = db.execute("SELECT reltuples::BIGINT AS estimate FROM pg_class WHERE oid = 'pagos'::regclass").scalar()
            if total is None or total <= 0:
                total = db.query(models.Pago).count()
        except Exception:
            total = db.query(models.Pago).count()

    return {
        "items": pagos,
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size if total is not None and total > 0 else 1
    }

@app.get("/buscar-pagos/")
def buscar_pagos(q: str, page: int = 1, size: int = 10, limit: Optional[int] = None, offset: Optional[int] = None, db: Session = Depends(get_db)):
    if limit:
        size = limit
    if offset is not None:
        page = (offset // size) + 1

    skip = (page - 1) * size
    query = db.query(models.Pago).filter(models.Pago.referencia.contains(q))

    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()

    total = None
    if os.getenv("FORCE_EXACT_COUNT", "false").lower() == "true":
        total = query.count()
    elif len(pagos) < size or page == 1:
        total = query.count()
    else:
        try:
            total = db.execute("SELECT reltuples::BIGINT AS estimate FROM pg_class WHERE oid = 'pagos'::regclass").scalar()
            if total is None or total <= 0:
                total = query.count()
        except Exception:
            total = query.count()

    return {
        "items": pagos,
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size if total is not None and total > 0 else 1
    }

@app.get("/pagos/", response_model=PagosResponse)
def listar_pagos(banco: Optional[str] = None, page: int = 1, size: int = 10, db: Session = Depends(get_db)):
    """Lista los pagos con opción de filtrar por banco emisor u origen."""
    query = db.query(models.Pago)
    if banco:
        termino = f"%{banco}%"
        query = query.filter(
            models.Pago.banco.ilike(termino)
        )

    skip = (page - 1) * size
    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()

    total = None
    if os.getenv("FORCE_EXACT_COUNT", "false").lower() == "true":
        total = query.count()
    elif len(pagos) < size or page == 1:
        total = query.count()
    else:
        try:
            total = db.execute("SELECT reltuples::BIGINT AS estimate FROM pg_class WHERE oid = 'pagos'::regclass").scalar()
            if total is None or total <= 0:
                total = query.count()
        except Exception:
            total = query.count()

    return {
        "items": pagos,
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size if total is not None and total > 0 else 1
    }


def _agregar_total_reporte(resultado: List[dict]) -> dict:
    total_bs = sum(item["total_bs"] for item in resultado)
    total_usd = sum(item["total_usd"] for item in resultado)
    total_pagos = sum(item["conteo"] for item in resultado)
    return {
        "total_bs": total_bs,
        "total_usd": total_usd,
        "total_pagos": total_pagos,
    }


def _query_reporte(db: Session, tipo_reporte: str, fecha_inicio: Optional[datetime], fecha_fin: Optional[datetime]) -> List[dict]:
    interval_map = {
        "diario": "day",
        "semanal": "week",
        "mensual": "month",
        "trimestral": "quarter",
        "anual": "year",
    }

    if tipo_reporte not in interval_map and tipo_reporte not in ["quincenal", "semestral"]:
        raise HTTPException(status_code=400, detail=f"Tipo de reporte desconocido: {tipo_reporte}")

    if tipo_reporte == "quincenal":
        periodo_expr = (
            func.date_trunc("month", models.Pago.fecha_registro)
            + (func.floor((func.extract("day", models.Pago.fecha_registro) - 1) / 15) * text("interval '15 days'"))
        )
    elif tipo_reporte == "semestral":
        periodo_expr = (
            func.date_trunc("year", models.Pago.fecha_registro)
            + (func.floor((func.extract("month", models.Pago.fecha_registro) - 1) / 6) * text("interval '6 months'"))
        )
    else:
        periodo_expr = func.date_trunc(interval_map[tipo_reporte], models.Pago.fecha_registro)

    query = db.query(
        periodo_expr.label("periodo"),
        func.sum(models.Pago.monto).label("total_bs"),
        func.sum(models.Pago.monto_usd).label("total_usd"),
        func.count(models.Pago.id).label("conteo"),
        func.min(models.Pago.fecha_registro).label("desde"),
        func.max(models.Pago.fecha_registro).label("hasta")
    )
    if fecha_inicio:
        query = query.filter(models.Pago.fecha_registro >= fecha_inicio)
    if fecha_fin:
        query = query.filter(models.Pago.fecha_registro <= fecha_fin)

    grouped = query.group_by(periodo_expr).order_by(periodo_expr).all()

    resultados = []
    for r in grouped:
        resultados.append({
            "periodo": r.periodo.isoformat() if hasattr(r.periodo, "isoformat") else str(r.periodo),
            "desde": r.desde,
            "hasta": r.hasta,
            "total_bs": float(r.total_bs or 0),
            "total_usd": float(r.total_usd or 0),
            "conteo": int(r.conteo or 0)
        })
    return resultados


def _query_pagos_detalle(db: Session, fecha_inicio: Optional[datetime], fecha_fin: Optional[datetime]) -> List[models.Pago]:
    """Obtiene la lista detallada de pagos para el reporte."""
    query = db.query(models.Pago)
    if fecha_inicio:
        query = query.filter(models.Pago.fecha_registro >= fecha_inicio)
    if fecha_fin:
        query = query.filter(models.Pago.fecha_registro <= fecha_fin)
    return query.order_by(models.Pago.fecha_registro.desc()).all()


def _crear_excel_reporte(resultados: List[dict], pagos_detalle: List[models.Pago], tipo_reporte: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    
    # Hoja 1: Resumen Agregado
    ws = wb.active
    ws.title = "Resumen"
    ws.append(["Reporte de Conciliación", tipo_reporte.title()])
    ws.append([])
    ws.append(["Periodo", "Desde", "Hasta", "Total Bs", "Total USD", "Conteo"])

    for item in resultados:
        ws.append([
            item["periodo"],
            item["desde"].strftime("%Y-%m-%d") if item["desde"] else "",
            item["hasta"].strftime("%Y-%m-%d") if item["hasta"] else "",
            item["total_bs"],
            item["total_usd"],
            item["conteo"],
        ])

    # Hoja 2: Detalle de Pagos (Solicitado)
    ws_det = wb.create_sheet(title="Detalle de Pagos")
    ws_det.append(["Referencia", "Banco Origen", "Fecha", "Monto (Bs)", "Tasa ($)", "Monto ($)"])
    for p in pagos_detalle:
        ws_det.append([
            p.referencia,
            p.banco,
            p.fecha_registro.strftime("%Y-%m-%d %H:%M") if p.fecha_registro else "N/A",
            p.monto,
            p.tasa_cambio,
            p.monto_usd
        ])

    for sheet in wb.worksheets:
        for columna in sheet.columns:
            max_length = 0
            for cell in columna:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            sheet.column_dimensions[columna[0].column_letter].width = min(max_length + 2, 40)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _crear_pdf_reporte(resultados: List[dict], pagos_detalle: List[models.Pago], tipo_reporte: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph(f"Reporte de Conciliación - {tipo_reporte.title()}", styles["Title"]))
    
    # Solución a error de formato de fecha cuando una es None
    range_parts = []
    if start_date: range_parts.append(f"Desde: {start_date.strftime('%Y-%m-%d')}")
    if end_date: range_parts.append(f"Hasta: {end_date.strftime('%Y-%m-%d')}")
    filtro_texto = " - ".join(range_parts) if range_parts else "Rango: completo"
    
    story.append(Paragraph(filtro_texto, styles["Normal"]))
    story.append(Spacer(1, 15))

    # --- Tabla de Resumen ---
    story.append(Paragraph("Resumen Agregado", styles["Heading3"]))
    data = [["Periodo", "Desde", "Hasta", "Total Bs", "Total USD", "Conteo"]]
    for item in resultados:
        data.append([
            item["periodo"],
            item["desde"].strftime("%Y-%m-%d") if item["desde"] else "",
            item["hasta"].strftime("%Y-%m-%d") if item["hasta"] else "",
            f"{item['total_bs']:.2f}",
            f"{item['total_usd']:.2f}",
            str(item["conteo"]),
        ])

    if not resultados:
        data.append(["No hay datos", "", "", "", "", ""])

    totales = _agregar_total_reporte(resultados)
    data.append(["Totales", "", "", f"{totales['total_bs']:.2f}", f"{totales['total_usd']:.2f}", str(totales['total_pagos'])])

    table = Table(data, colWidths=[100, 80, 80, 95, 95, 60])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # --- Tabla de Detalle (Nueva sección solicitada) ---
    story.append(Paragraph("Detalle Individual de Pagos", styles["Heading3"]))
    data_det = [["Referencia", "Banco", "Fecha", "Monto Bs", "Tasa ($)", "Monto USD"]]
    for p in pagos_detalle:
        data_det.append([
            p.referencia,
            (p.banco[:12] + '..') if p.banco and len(p.banco) > 12 else p.banco,
            p.fecha_registro.strftime("%Y-%m-%d") if p.fecha_registro else "N/A",
            f"{p.monto:.2f}",
            f"{p.tasa_cambio:.2f}",
            f"{p.monto_usd:.2f}"
        ])

    if not pagos_detalle:
        data_det.append(["Sin movimientos", "-", "-", "-", "-", "-"])

    table_det = Table(data_det, colWidths=[90, 100, 80, 90, 70, 90])
    table_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table_det)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _crear_nombre_archivo(tipo_reporte: str, formato: str) -> str:
    sufijo = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"reportes-{tipo_reporte}-{sufijo}.{formato}"


@app.get("/reportes/export/")
def exportar_reportes(tipo_reporte: str = "mensual", format: str = "xlsx", start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, db: Session = Depends(get_db)):
    formato = format.lower()
    if formato not in ["xlsx", "pdf"]:
        raise HTTPException(status_code=400, detail="Formato de exportación no válido. Usa pdf o xlsx.")

    resultados = _query_reporte(db, tipo_reporte.lower(), start_date, end_date)
    pagos_detalle = _query_pagos_detalle(db, start_date, end_date)

    if formato == "xlsx":
        contenido = _crear_excel_reporte(resultados, pagos_detalle, tipo_reporte, start_date, end_date)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        contenido = _crear_pdf_reporte(resultados, pagos_detalle, tipo_reporte, start_date, end_date)
        media_type = "application/pdf"

    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{_crear_nombre_archivo(tipo_reporte, formato)}\""}
    )


@app.get("/reportes/", response_model=ReporteResponse)
def obtener_reportes(tipo_reporte: str = "mensual", start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, db: Session = Depends(get_db)):
    """Genera un reporte agregado por período y devuelve totales con rangos."""
    resultados = _query_reporte(db, tipo_reporte.lower(), start_date, end_date)
    totales = _agregar_total_reporte(resultados)
    return {
        "tipo_reporte": tipo_reporte,
        "resultados": resultados,
        **totales,
    }

# --- 1. RUTA PARA SUBIR IMAGEN (Corrección para que funcione el botón) ---
@app.post("/subir-pago/")
async def subir_pago(
    file: UploadFile = File(...), 
    banco: str = Form(...),
    cliente_id: Optional[int] = Form(None),
    comentario: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    # --- MEJORA: Seguridad con API Key ---
    auth: bool = Depends(require_api_key)
):
    # --- MEJORA: Endpoint mucho más robusto ---
    filepath = None
    try:
        # 1. Validaciones y guardado seguro
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Solo se permiten archivos de imagen.")

        max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
        max_bytes = max_upload_mb * 1024 * 1024

        # Nombre de archivo sanitizado
        filename = f"{uuid.uuid4().hex}_{os.path.basename(file.filename)}"
        filepath = os.path.join("uploads", filename)

        # Guardado en streaming con límite de tamaño
        written_bytes = 0
        with open(filepath, "wb") as buffer:
            while chunk := await file.read(1024 * 1024): # Leemos en bloques de 1MB
                written_bytes += len(chunk)
                if written_bytes > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Archivo demasiado grande (máx {max_upload_mb}MB)")
                buffer.write(chunk)

        # 2. Calcular Hash para anti-duplicados
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        file_hash_str = sha256_hash.hexdigest()

        # --- MEJORA: Validación anti-duplicado por HASH más informativa ---
        existing_by_hash = db.query(models.Pago).filter(models.Pago.file_hash == file_hash_str).first()
        if existing_by_hash:
            return JSONResponse(
                content={
                    "mensaje": "Archivo duplicado detectado (hash). Ya existe un pago con este archivo.", 
                    "id_existente": existing_by_hash.id, 
                    "referencia": existing_by_hash.referencia
                },
                status_code=409
            )

        # 3. Procesar con OCR
        try:
            resultado = ocr_engine.procesar_imagen(filepath)
        except RuntimeError as e:
            logger.error("Error crítico OCR: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

        # 4. Validación anti-duplicado por lógica de negocio (se mantiene tu lógica)
        # Priorizamos los datos limpios devueltos por la IA (Groq)
        ref_ocr = str(resultado.get("referencia", "No detectada"))
        
        try:
            # Aseguramos que el monto sea float para cálculos y base de datos
            monto_ocr = float(resultado.get("monto") or 0.0)
        except (ValueError, TypeError):
            monto_ocr = 0.0

        if ref_ocr not in ["S/R", "No detectada"]:
            pago_existente = db.query(models.Pago).filter(
                models.Pago.referencia == ref_ocr,
                models.Pago.banco == banco,
                models.Pago.monto == monto_ocr
            ).first()
            if pago_existente:
                return JSONResponse(
                    content={"mensaje": f"Error: Ya existe un pago con la misma referencia ({ref_ocr}), banco ({banco}) and monto."}, 
                    status_code=409
                )

        # 5. Guardar en BD
        banco_destino = resultado.get("banco_destino") # Puede ser None

        # Obtener la tasa más reciente con la nueva ruta de intercambio
        tasa_info = await get_tasa_bcv(db)
        tasa_actual = float(tasa_info['tasa'])
        monto_usd_calc = round(monto_ocr / tasa_actual, 2) if tasa_actual > 0 else 0.0

        nuevo_pago = models.Pago(
            referencia=ref_ocr,
            banco=banco,
            banco_destino=banco_destino,
            monto=monto_ocr,
            ruta_imagen=filepath,
            file_hash=file_hash_str,
            cliente_id=cliente_id,
            tasa_cambio=tasa_actual,
            monto_usd=monto_usd_calc
        )
        
        try:
            db.add(nuevo_pago)
            db.commit()
            db.refresh(nuevo_pago)
        except sa_exc.IntegrityError: # --- MEJORA: Manejo de carrera (dos uploads idénticos a la vez)
            db.rollback()
            existing = db.query(models.Pago).filter(models.Pago.file_hash == file_hash_str).first()
            if existing:
                return JSONResponse(
                    content={
                        "mensaje": "Archivo duplicado detectado (hash). Ya existe un pago con este archivo.",
                        "id_existente": existing.id,
                        "referencia": existing.referencia,
                    },
                    status_code=409
                )
            # Si no es por el hash, relanzamos el error
            raise


        # 6. Auditoría (PagoHistory) - Se mantiene tu lógica
        origen_datos = resultado.get("source", "RULES_LEGACY") # Default si no viene
        
        detalles_audit = f"Creado vía /subir-pago/. Motor: {origen_datos}. Ref: {ref_ocr}. Banco: {nuevo_pago.banco}"
        if banco_destino:
             detalles_audit += f" -> Destino: {banco_destino}"

        registrar_auditoria(
            db, 
            pago_id=nuevo_pago.id, 
            accion="create_ia", 
            detalles=detalles_audit
        )
        
        return JSONResponse(content={"mensaje": "Procesado correctamente", "data": resultado}, status_code=200)

    except HTTPException:
        raise # Re-lanza las excepciones HTTP para que FastAPI las maneje
    except Exception as e:
        # --- MEJORA: Logging de errores detallado sin exponerlo al cliente ---
        tb = traceback.format_exc()
        logger.error("Fallo crítico en /subir-pago/\n%s", tb)
        try:
            with open('logs/subir_trace.log', 'a', encoding='utf-8') as fh:
                fh.write(f"--- {datetime.now()} ---\n{tb}\n")
        except Exception as log_e:
            logger.error("No se pudo escribir el log de trace: %s", log_e)
        raise HTTPException(status_code=500, detail="Error interno del servidor al procesar el archivo.")
    finally:
        if filepath and os.path.exists(filepath) and ('nuevo_pago' not in locals() or not getattr(locals().get('nuevo_pago'), 'id', None)):
            os.remove(filepath)

# --- 2. RUTA PARA REGISTRO MANUAL (Nueva) ---
@app.post("/pago-manual/")
async def crear_pago_manual(dato: PagoManual, db: Session = Depends(get_db)):
    try:
        # --- VALIDACIÓN ANTI-DUPLICADO MEJORADA ---
        pago_existente = db.query(models.Pago).filter(
            models.Pago.referencia == dato.referencia,
            models.Pago.banco == dato.banco,
            models.Pago.monto == dato.monto
        ).first()
        if pago_existente:
            raise HTTPException(status_code=409, detail=f"Error: Ya existe un pago con la misma referencia, banco y monto.")

        # Normalizar banco manual contra la lista canónica de bank_rules
        banco_normalizado = dato.banco.strip()
        if banco_normalizado not in bank_rules.get_available_banks():
            try:
                estrategia = bank_rules.get_bank_strategy(banco_normalizado)
                if estrategia and estrategia.name and estrategia.name != "Desconocido":
                    banco_normalizado = estrategia.name
            except Exception:
                pass

        # Obtener tasa para el registro manual (NCBC nueva función)
        tasa_info = await get_tasa_bcv(db)
        tasa_actual = float(tasa_info["tasa"])
        monto_usd_calc = round(dato.monto / tasa_actual, 2) if tasa_actual > 0 else 0.0

        nuevo_pago = models.Pago(
            referencia=dato.referencia,
            banco=banco_normalizado,
            monto=dato.monto, 
            ruta_imagen="", # Vacío porque es manual
            file_hash="MANUAL",
            cliente_id=dato.cliente_id,
            tasa_cambio=tasa_actual,
            monto_usd=monto_usd_calc
        )
        db.add(nuevo_pago)
        db.commit()
        db.refresh(nuevo_pago)

        registrar_auditoria(
            db, 
            pago_id=nuevo_pago.id, 
            accion="create_manual", 
            detalles="Registro manual por el usuario"
        )
        return {"mensaje": "Pago manual registrado"}
    except Exception as e:
        logger.error(f"Error manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 3. RUTA PARA RE-PROCESAR (Nueva) ---
@app.post("/reprocesar/{pago_id}")
def reprocesar_pago(pago_id: int, db: Session = Depends(get_db)):
    # 1. Buscar el pago
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    
    if not pago.ruta_imagen or not os.path.exists(pago.ruta_imagen):
        raise HTTPException(status_code=400, detail="Este pago no tiene imagen para reprocesar")

    try:
        # 2. Ejecutar OCR de nuevo
        resultado = ocr_engine.procesar_imagen(pago.ruta_imagen)
        
        # 3. Actualizar datos (No borramos para mantener el ID, solo actualizamos)
        banco_dest_nuevo = resultado.get("banco_destino", pago.banco_destino)
        ref_nueva = resultado.get("referencia", pago.referencia)
        monto_nuevo = float(resultado.get("monto") or pago.monto)

        pago.referencia = ref_nueva
        pago.banco_destino = banco_dest_nuevo
        pago.monto = monto_nuevo
        
        db.commit()

        # Mejoramos el detalle de la auditoría
        detalles_audit = f"Re-escaneo IA. Ref: {ref_nueva}, Banco: {pago.banco}, Monto: {monto_nuevo}"

        registrar_auditoria(
            db, 
            pago_id=pago.id, 
            accion="reprocess", 
            detalles=detalles_audit
        )
        return {"mensaje": "Pago reprocesado con éxito", "nuevos_datos": resultado}
    except Exception as e:
        logger.error(f"Error reprocesando: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- NUEVA RUTA PARA CAMBIAR ESTADO ---
@app.patch("/pago/{pago_id}/estado")
def cambiar_estado_pago(pago_id: int, update_data: EstadoUpdate, db: Session = Depends(get_db)):
    """Actualiza el estado de un pago y registra en la auditoría."""
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    estado_anterior = pago.estado
    nuevo_estado = update_data.estado.value
    
    if estado_anterior == nuevo_estado:
        return {"mensaje": "El estado ya es el solicitado, no se realizaron cambios."}

    pago.estado = nuevo_estado
    
    registrar_auditoria(
        db,
        pago_id=pago.id,
        accion="update_status",
        detalles=f"Estado cambiado de '{estado_anterior}' a '{nuevo_estado}'"
    )
    return {"mensaje": f"Estado del pago {pago_id} actualizado a '{nuevo_estado}'"}

@app.get("/pago/{pago_id}/historial")
def obtener_historial(pago_id: int, db: Session = Depends(get_db)):
    # Buscamos todos los registros de auditoría para ese pago
    historial = db.query(models.PagoHistory).filter(
        models.PagoHistory.pago_id == pago_id
    ).order_by(desc(models.PagoHistory.id)).all()
    return historial

@app.delete("/eliminar-pago-ref/{referencia}")
def eliminar_pago(referencia: str, confirm: bool = False, db: Session = Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.referencia == referencia).first()
    if not pago:
        # Intentamos buscar por ID si la referencia parece un ID (fallback)
        if referencia.isdigit():
             pago = db.query(models.Pago).filter(models.Pago.id == int(referencia)).first()
        
        if not pago:
            raise HTTPException(status_code=404, detail="Pago no encontrado")

    if confirm:
        # Borrar imagen física si existe
        if pago.ruta_imagen and os.path.exists(pago.ruta_imagen):
            try:
                os.remove(pago.ruta_imagen)
            except Exception as e:
                logger.warning(f"No se pudo eliminar el archivo físico {pago.ruta_imagen}: {e}")
        db.delete(pago)
        db.commit()
        return {"mensaje": "Eliminado correctamente"}
    
    return {"mensaje": "Se requiere confirmación (?confirm=true)"}