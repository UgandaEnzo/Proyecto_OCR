import os
import shutil
import uuid
import json
import logging
import hashlib
from enum import Enum
from typing import Optional, List
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Header, Body
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime
from pydantic import BaseModel

# Carga las variables de entorno desde un archivo .env ANTES de importar módulos locales
load_dotenv()

# Importamos tus módulos
from database import engine, get_db
import models
import ocr_engine  # Tu motor de OCR

# Configuración de Logs (para ver errores en la consola negra)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear tablas si no existen
models.Base.metadata.create_all(bind=engine)
logger.info("Sistema de Base de Datos inicializado: Tablas verificadas/creadas.")

app = FastAPI()

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
def root_redirect():
    """Redirige a la interfaz web estática."""
    return RedirectResponse(url="/static/index.html")


@app.get("/panel")
def panel_redirect():
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
def leer_clientes(db: Session = Depends(get_db)):
    """Obtiene una lista de todos los clientes."""
    return db.query(models.Cliente).all()

@app.get("/clientes/{cliente_id}/pagos", response_model=ClienteConPagos)
def leer_pagos_de_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtiene los detalles de un cliente y todos sus pagos asociados."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    # Pydantic usa la relación `cliente.pagos` para poblar la respuesta
    return cliente

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
    total = db.query(models.Pago).count()
    
    return {
        "items": pagos,
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size # Cálculo rápido del total de páginas
    }

@app.get("/buscar-pagos/")
def buscar_pagos(q: str, page: int = 1, size: int = 10, limit: Optional[int] = None, offset: Optional[int] = None, db: Session = Depends(get_db)):
    if limit:
        size = limit
    if offset is not None:
        page = (offset // size) + 1

    skip = (page - 1) * size
    query = db.query(models.Pago).filter(models.Pago.referencia.contains(q))
    total = query.count()
    pagos = query.order_by(desc(models.Pago.id)).offset(skip).limit(size).all()
    return {
        "items": pagos, 
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size
    }

# --- 1. RUTA PARA SUBIR IMAGEN (Corrección para que funcione el botón) ---
@app.post("/subir-pago/")
async def subir_pago(
    file: UploadFile = File(...), 
    cliente_id: Optional[int] = Form(None),
    comentario: Optional[str] = Form(None),
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    try:
        # 1. Guardar archivo
        file_ext = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{file_ext}"
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Calcular Hash (SHA256 real)
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        file_hash_str = sha256_hash.hexdigest()

        # --- VALIDACIÓN ANTI-DUPLICADO POR HASH (IMAGEN EXACTA) ---
        # Si subes exactamente el mismo archivo, lo bloqueamos antes de gastar recursos en OCR
        if db.query(models.Pago).filter(models.Pago.file_hash == file_hash_str).first():
            if os.path.exists(filepath):
                os.remove(filepath)
            return JSONResponse(
                content={"mensaje": "Error: Esta imagen ya fue procesada anteriormente (Duplicado exacto)."}, 
                status_code=409
            )

        # 3. Procesar con OCR
        resultado = ocr_engine.procesar_imagen(filepath)
        
        # Extraemos los datos clave para la validación
        ref_ocr = resultado.get("referencia", "S/R")
        banco_origen = resultado.get("banco_origen") or resultado.get("banco", "Desconocido")
        monto_ocr = float(resultado.get("monto") or 0.0)

        # --- VALIDACIÓN ANTI-DUPLICADO ---
        if ref_ocr not in ["S/R", "No detectada"]:
            pago_existente = db.query(models.Pago).filter(
                models.Pago.referencia == ref_ocr,
                models.Pago.banco_origen == banco_origen,
                models.Pago.monto == monto_ocr
            ).first()
            if pago_existente:
                # Si es duplicado, borramos la imagen física que acabamos de subir
                if os.path.exists(filepath):
                    os.remove(filepath)
                return JSONResponse(
                    content={"mensaje": f"Error: Ya existe un pago con la misma referencia ({ref_ocr}), banco ({banco_origen}) y monto."}, 
                    status_code=409
                )

        # 4. Guardar en BD
        banco_destino = resultado.get("banco_destino") # Puede ser None

        nuevo_pago = models.Pago(
            referencia=ref_ocr,
            banco_origen=banco_origen,
            banco_destino=banco_destino,
            monto=monto_ocr,
            ruta_imagen=filepath,
            file_hash=file_hash_str,
            cliente_id=cliente_id
        )
        db.add(nuevo_pago)
        db.commit()
        db.refresh(nuevo_pago)

        # 5. Auditoría (PagoHistory)
        origen_datos = resultado.get("source", "RULES_LEGACY") # Default si no viene
        
        # Preparamos detalles enriquecidos
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

    except Exception as e:
        logger.error(f"Error subiendo pago: {e}")
        return JSONResponse(content={"detail": str(e)}, status_code=500)

# --- 2. RUTA PARA REGISTRO MANUAL (Nueva) ---
@app.post("/pago-manual/")
def crear_pago_manual(dato: PagoManual, db: Session = Depends(get_db)):
    try:
        # --- VALIDACIÓN ANTI-DUPLICADO MEJORADA ---
        pago_existente = db.query(models.Pago).filter(
            models.Pago.referencia == dato.referencia,
            models.Pago.banco_origen == dato.banco,
            models.Pago.monto == dato.monto
        ).first()
        if pago_existente:
            raise HTTPException(status_code=409, detail=f"Error: Ya existe un pago con la misma referencia, banco y monto.")

        nuevo_pago = models.Pago(
            referencia=dato.referencia,
            banco_origen=dato.banco, # Banco is required on manual
            monto=dato.monto, 
            ruta_imagen="", # Vacío porque es manual
            file_hash="MANUAL",
            cliente_id=dato.cliente_id
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