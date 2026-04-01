import os
import shutil
import uuid
import logging
from logging.handlers import RotatingFileHandler
import hashlib
import traceback
import threading
from enum import Enum
from typing import Optional, List
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import requests

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Header, Body
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, exc as sa_exc
from datetime import datetime
from pydantic import BaseModel

from exchange import get_tasa_bcv, convertir_payments, TasaNoDisponibleError

# Carga las variables de entorno desde un archivo .env ANTES de importar módulos locales
load_dotenv()

# Importamos tus módulos (ahora database.py es más robusto)
from database import engine, get_db, Base
import models
import ocr_engine  # Tu motor de OCR

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
    cedula: Optional[str] = None
    telefono: Optional[str] = None

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

# Modelo de respuesta para el historial de un cliente
class ClienteConPagos(Cliente):
    pagos: List[PagoParaCliente] = []


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

def obtener_tasa_bcv_con_fallback(db: Session):
    """Wrapper legado para compatibilidad. Usa la función moderna de exchange."""
    import asyncio
    tasa_info = asyncio.get_event_loop().run_until_complete(get_tasa_bcv(db))
    return float(tasa_info["tasa"]), tasa_info["fecha"], tasa_info["origen"]

    # 1) Intentar tasa guardada en BD.
    tasa_db = db.query(models.TasaCambio).filter(models.TasaCambio.proveedor == "BCV").order_by(models.TasaCambio.fecha_actualizacion.desc()).first()
    if tasa_db and tasa_db.monto_tasa and tasa_db.monto_tasa > 0:
        es_fallback = True
        return tasa_db.monto_tasa, tasa_db.fecha_actualizacion or datetime.now(), es_fallback

    # 2) Intentar API externa.
    tasa_api_url = os.getenv("TASA_BCV_API_URL", "https://s3.amazonaws.com/dolartoday/data.json")
    if tasa_api_url:
        try:
            r = requests.get(tasa_api_url, timeout=8)
            r.raise_for_status()
            data = r.json()

            tasa_valor = None
            if isinstance(data, dict):
                if "USD" in data and isinstance(data["USD"], dict):
                    tasa_valor = float(data["USD"].get("dolartoday", {}).get("promedio", 0.0) or 0.0)
                elif "venta" in data and "compra" in data:
                    tasa_valor = float(data.get("venta", 0.0) or 0.0)
                elif "rates" in data and isinstance(data["rates"], dict):
                    v = float(data["rates"].get("VES", 0.0) or 0.0)
                    if v > 0:
                        tasa_valor = 1.0 / v

            if tasa_valor and tasa_valor > 0:
                tasa = tasa_valor
                tasa_db = db.query(models.TasaCambio).filter(models.TasaCambio.proveedor == "BCV").first()
                if not tasa_db:
                    tasa_db = models.TasaCambio(proveedor="BCV", monto_tasa=tasa)
                    db.add(tasa_db)
                else:
                    tasa_db.monto_tasa = tasa
                    tasa_db.fecha_actualizacion = func.now()
                db.commit()
                es_fallback = True
                return tasa, datetime.now(), es_fallback

        except Exception as e:
            logger.warning(f"No se pudo obtener la tasa desde API externa {tasa_api_url}: {e}")

    # 3) Fallback env var.
    tasa_env = float(os.getenv("DEFAULT_TASA_BCV", "1.0"))
    if tasa_env and tasa_env > 0:
        es_fallback = True
        return tasa_env, datetime.now(), es_fallback

    # 4) Fallback seguro.
    es_fallback = True
    return 1.0, datetime.now(), es_fallback

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
    if cliente.cedula:
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
    # Pydantic usa la relación `cliente.pagos` para poblar la respuesta
    return cliente

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
def leer_pagos(page: int = 1, size: int = 10, limit: Optional[int] = None, offset: Optional[int] = None, db: Session = Depends(get_db)):
    # Compatibilidad: Si el frontend envía limit/offset (cache antiguo), calculamos la página
    if limit:
        size = limit
    if offset is not None:
        page = (offset // size) + 1

    # Lógica de paginación de SQL
    # Si page=1, skip=0. Si page=2, skip=10.
    skip = (page - 1) * size

    pagos = db.query(models.Pago).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()

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

    pagos = query.order_by(desc(models.Pago.id)).offset(skip).limit(size).all()

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

# --- 1. RUTA PARA SUBIR IMAGEN (Corrección para que funcione el botón) ---
@app.post("/subir-pago/")
async def subir_pago(
    file: UploadFile = File(...), 
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
        except ocr_engine.pytesseract.TesseractNotFoundError:
            logger.error("Error crítico: Tesseract OCR no está instalado o configurado.")
            raise HTTPException(
                status_code=500, 
                detail="El servidor no tiene configurado el motor de lectura OCR (Tesseract).")
        
        # 4. Validación anti-duplicado por lógica de negocio (se mantiene tu lógica)
        ref_ocr = resultado.get("referencia", "S/R")
        banco_origen = resultado.get("banco_origen") or resultado.get("banco", "Desconocido")
        monto_ocr = float(resultado.get("monto") or 0.0)

        if ref_ocr not in ["S/R", "No detectada"]:
            pago_existente = db.query(models.Pago).filter(
                models.Pago.referencia == ref_ocr,
                models.Pago.banco_origen == banco_origen,
                models.Pago.monto == monto_ocr
            ).first()
            if pago_existente:
                return JSONResponse(
                    content={"mensaje": f"Error: Ya existe un pago con la misma referencia ({ref_ocr}), banco ({banco_origen}) y monto."}, 
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
            banco_origen=banco_origen,
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
        
        detalles_audit = f"Creado vía /subir-pago/. Motor: {origen_datos}. Ref: {ref_ocr}"
        if banco_destino:
             detalles_audit += f". Origen: {banco_origen} -> Destino: {banco_destino}"

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
        if filepath and os.path.exists(filepath) and 'nuevo_pago' not in locals():
            os.remove(filepath)

# --- 2. RUTA PARA REGISTRO MANUAL (Nueva) ---
@app.post("/pago-manual/")
async def crear_pago_manual(dato: PagoManual, db: Session = Depends(get_db)):
    try:
        # --- VALIDACIÓN ANTI-DUPLICADO MEJORADA ---
        pago_existente = db.query(models.Pago).filter(
            models.Pago.referencia == dato.referencia,
            models.Pago.banco_origen == dato.banco,
            models.Pago.monto == dato.monto
        ).first()
        if pago_existente:
            raise HTTPException(status_code=409, detail=f"Error: Ya existe un pago con la misma referencia, banco y monto.")

        # Obtener tasa para el registro manual (NCBC nueva función)
        tasa_info = await get_tasa_bcv(db)
        tasa_actual = float(tasa_info["tasa"])
        monto_usd_calc = round(dato.monto / tasa_actual, 2) if tasa_actual > 0 else 0.0

        nuevo_pago = models.Pago(
            referencia=dato.referencia,
            banco_origen=dato.banco, # Banco is required on manual
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
        # BUGFIX: Usar el mismo patrón que en /subir-pago para obtener el banco
        banco_nuevo = resultado.get("banco_origen") or resultado.get("banco", pago.banco_origen)
        banco_dest_nuevo = resultado.get("banco_destino", pago.banco_destino)
        ref_nueva = resultado.get("referencia", pago.referencia)
        monto_nuevo = float(resultado.get("monto") or pago.monto)

        pago.referencia = ref_nueva
        pago.banco_origen = banco_nuevo
        pago.banco_destino = banco_dest_nuevo
        pago.monto = monto_nuevo
        
        db.commit()

        # Mejoramos el detalle de la auditoría
        detalles_audit = f"Re-escaneo IA. Ref: {ref_nueva}, Banco: {banco_nuevo}, Monto: {monto_nuevo}"

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