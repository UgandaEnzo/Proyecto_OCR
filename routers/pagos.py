
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime
import os
import uuid
import hashlib
import models
import schemas
import bank_rules
import ocr_engine
from database import get_db
import traceback
from sqlalchemy import exc as sa_exc
from utils import uploads_dir, require_api_key, registrar_auditoria, logger
from exchange import get_tasa_bcv
from exchange import convertir_payments, TasaNoDisponibleError

router = APIRouter(tags=['pagos'])

@router.post('/convertir-a-usd/', response_model=schemas.ConversionResponse)
async def convertir_monto_a_usd(data: schemas.ConversionRequest, db: Session=Depends(get_db)):
    """Convierte un monto en bolívares a USD usando la tasa BCV con fallback robusto."""
    try:
        result = await convertir_payments(db, data.monto_bs)
    except TasaNoDisponibleError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {'monto_bs': float(result['monto_bs']), 'tasa_bcv': float(result['tasa_bcv']), 'fecha_consulta': result['fecha'], 'monto_usd': float(result['monto_usd']), 'origen': result['origen'], 'es_fallback': result['origen'] != 'API'}

@router.get('/tasa-bcv/')
async def obtener_tasa_bcv_endpoint(db: Session=Depends(get_db)):
    tasa_info = await get_tasa_bcv(db)
    tasa = float(tasa_info['tasa'])
    origen = tasa_info['origen']
    fecha = tasa_info['fecha']
    es_fallback = origen != 'API'
    return {'tasa_bcv': tasa, 'fecha_consulta': fecha, 'origen': origen, 'es_fallback': es_fallback}

@router.get('/bancos/')
def listar_bancos():
    return {'bancos': bank_rules.get_available_banks()}

@router.post('/tasa-bcv/')
def set_tasa_bcv(data: schemas.TasaBCVUpdate, db: Session=Depends(get_db), x_api_key: Optional[str]=Header(None)):
    require_api_key(x_api_key)
    tasa_bcv = data.tasa_bcv
    if tasa_bcv <= 0:
        raise HTTPException(status_code=400, detail='La tasa debe ser mayor que cero')
    tasa_db = db.query(models.TasaCambio).filter(models.TasaCambio.proveedor == 'BCV').first()
    if not tasa_db:
        tasa_db = models.TasaCambio(proveedor='BCV', monto_tasa=tasa_bcv)
        db.add(tasa_db)
    else:
        tasa_db.monto_tasa = tasa_bcv
        tasa_db.fecha_actualizacion = func.now()
    db.commit()
    return {'tasa_bcv': tasa_bcv, 'mensaje': 'Tasa BCV actualizada'}

@router.get('/ver-pagos/')
def leer_pagos(q: Optional[str]=None, banco: Optional[str]=None, page: int=1, size: int=10, limit: Optional[int]=None, offset: Optional[int]=None, db: Session=Depends(get_db)):
    if limit:
        size = limit
    if offset is not None:
        page = offset // size + 1
    skip = (page - 1) * size
    query = db.query(models.Pago)
    if q:
        query = query.filter(models.Pago.referencia.contains(q))
    if banco:
        termino = f'%{banco}%'
        query = query.filter(models.Pago.banco.ilike(termino))
    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()
    total = None
    if os.getenv('FORCE_EXACT_COUNT', 'false').lower() == 'true':
        total = db.query(models.Pago).count()
    elif len(pagos) < size or page == 1:
        total = db.query(models.Pago).count()
    else:
        try:
            total = db.execute("SELECT reltuples::BIGINT AS estimate FROM pg_class WHERE oid = 'pagos'::regclass").scalar()
            if total is None or total <= 0:
                total = db.query(models.Pago).count()
        except Exception:
            total = db.query(models.Pago).count()
    return {'items': pagos, 'total': total, 'page': page, 'pages': (total + size - 1) // size if total is not None and total > 0 else 1}

@router.get('/buscar-pagos/')
def buscar_pagos(q: str, page: int=1, size: int=10, limit: Optional[int]=None, offset: Optional[int]=None, db: Session=Depends(get_db)):
    if limit:
        size = limit
    if offset is not None:
        page = offset // size + 1
    skip = (page - 1) * size
    query = db.query(models.Pago).filter(models.Pago.referencia.contains(q))
    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()
    total = None
    if os.getenv('FORCE_EXACT_COUNT', 'false').lower() == 'true':
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
    return {'items': pagos, 'total': total, 'page': page, 'pages': (total + size - 1) // size if total is not None and total > 0 else 1}

@router.get('/pagos/', response_model=schemas.PagosResponse)
def listar_pagos(q: Optional[str]=None, banco: Optional[str]=None, page: int=1, size: int=10, db: Session=Depends(get_db)):
    """Lista los pagos con opción de filtrar por referencia y banco emisor u origen."""
    query = db.query(models.Pago)
    if q:
        termino_q = f'%{q}%'
        query = query.filter(models.Pago.referencia.ilike(termino_q))
    if banco:
        termino = f'%{banco}%'
        query = query.filter(models.Pago.banco.ilike(termino))
    if page < 1:
        page = 1
    skip = (page - 1) * size
    pagos = query.options(joinedload(models.Pago.cliente)).order_by(desc(models.Pago.id)).offset(skip).limit(size).all()
    total = None
    if os.getenv('FORCE_EXACT_COUNT', 'false').lower() == 'true':
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
    return {'items': pagos, 'total': total, 'page': page, 'pages': (total + size - 1) // size if total is not None and total > 0 else 1}

@router.post('/subir-pago/')
async def subir_pago(file: Optional[UploadFile]=File(None), banco: str=Form(...), cliente_id: Optional[str]=Form(None), comentario: Optional[str]=Form(None), db: Session=Depends(get_db), auth: bool=Depends(require_api_key)):
    filepath = None
    try:
        if cliente_id == '':
            cliente_id = None
        elif cliente_id is not None:
            try:
                cliente_id = int(cliente_id)
            except ValueError:
                raise HTTPException(status_code=422, detail='cliente_id debe ser un entero válido o vacío.')
        if file is None:
            raise HTTPException(status_code=400, detail='Seleccione un archivo de imagen.')
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail='Solo se permiten archivos de imagen.')
        max_upload_mb = int(os.getenv('MAX_UPLOAD_MB', '10'))
        max_bytes = max_upload_mb * 1024 * 1024
        filename = None
        filename = f'{uuid.uuid4().hex}_{os.path.basename(file.filename)}'
        filepath = str(uploads_dir / filename)
        written_bytes = 0
        with open(filepath, 'wb') as buffer:
            while (chunk := (await file.read(1024 * 1024))):
                written_bytes += len(chunk)
                if written_bytes > max_bytes:
                    raise HTTPException(status_code=413, detail=f'Archivo demasiado grande (máx {max_upload_mb}MB)')
                buffer.write(chunk)
        sha256_hash = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        file_hash_str = sha256_hash.hexdigest()
        existing_by_hash = db.query(models.Pago).filter(models.Pago.file_hash == file_hash_str).first()
        if existing_by_hash:
            return JSONResponse(content={'mensaje': 'Archivo duplicado detectado (hash). Ya existe un pago con este archivo.', 'id_existente': existing_by_hash.id, 'referencia': existing_by_hash.referencia}, status_code=409)
        try:
            resultado = ocr_engine.procesar_imagen(filepath)
        except RuntimeError as e:
            logger.error('Error crítico OCR: %s', e)
            raise HTTPException(status_code=500, detail=str(e))
        ref_ocr = str(resultado.get('referencia', 'No detectada'))
        try:
            monto_ocr = float(resultado.get('monto') or 0.0)
        except (ValueError, TypeError):
            monto_ocr = 0.0
        if ref_ocr not in ['S/R', 'No detectada']:
            pago_existente = db.query(models.Pago).filter(models.Pago.referencia == ref_ocr, models.Pago.banco == banco, models.Pago.monto == monto_ocr).first()
            if pago_existente:
                return JSONResponse(content={'mensaje': f'Error: Ya existe un pago con la misma referencia ({ref_ocr}), banco ({banco}) and monto.'}, status_code=409)
        banco_destino = resultado.get('banco_destino')
        tasa_info = await get_tasa_bcv(db)
        tasa_actual = float(tasa_info['tasa'])
        monto_usd_calc = round(monto_ocr / tasa_actual, 2) if tasa_actual > 0 else 0.0
        nuevo_pago = models.Pago(referencia=ref_ocr, banco=banco, banco_destino=banco_destino, monto=monto_ocr, ruta_imagen=filepath, file_hash=file_hash_str, cliente_id=cliente_id, tasa_momento=tasa_actual, tasa_cambio=tasa_actual, monto_usd=monto_usd_calc)
        try:
            db.add(nuevo_pago)
            db.commit()
            db.refresh(nuevo_pago)
        except sa_exc.IntegrityError:
            db.rollback()
            existing = db.query(models.Pago).filter(models.Pago.file_hash == file_hash_str).first()
            if existing:
                return JSONResponse(content={'mensaje': 'Archivo duplicado detectado (hash). Ya existe un pago con este archivo.', 'id_existente': existing.id, 'referencia': existing.referencia}, status_code=409)
            raise
        origen_datos = resultado.get('source', 'RULES_LEGACY')
        detalles_audit = f'Creado vía /subir-pago/. Motor: {origen_datos}. Ref: {ref_ocr}. Banco: {nuevo_pago.banco}'
        if banco_destino:
            detalles_audit += f' -> Destino: {banco_destino}'
        registrar_auditoria(db, pago_id=nuevo_pago.id, accion='create_ia', detalles=detalles_audit)
        return JSONResponse(content={'mensaje': 'Procesado correctamente', 'data': resultado}, status_code=200)
    except HTTPException:
        raise
    except Exception:
        tb = traceback.format_exc()
        logger.error('Fallo crítico en /subir-pago/\n%s', tb)
        try:
            with open('logs/subir_trace.log', 'a', encoding='utf-8') as fh:
                fh.write(f'--- {datetime.now()} ---\n{tb}\n')
        except Exception as log_e:
            logger.error('No se pudo escribir el log de trace: %s', log_e)
        raise HTTPException(status_code=500, detail='Error interno del servidor al procesar el archivo.')
    finally:
        if filepath and os.path.exists(filepath) and ('nuevo_pago' not in locals() or not getattr(locals().get('nuevo_pago'), 'id', None)):
            os.remove(filepath)

@router.post('/pago-manual/')
async def crear_pago_manual(dato: schemas.PagoManual, db: Session=Depends(get_db)):
    try:
        if not dato.banco.strip():
            raise HTTPException(status_code=400, detail='El banco es obligatorio y debe ser un valor válido.')
        if not dato.referencia.strip():
            raise HTTPException(status_code=400, detail='La referencia es obligatoria y no puede estar vacía.')
        if dato.monto <= 0:
            raise HTTPException(status_code=400, detail='El monto debe ser un número mayor a cero.')
        pago_existente = db.query(models.Pago).filter(models.Pago.referencia == dato.referencia, models.Pago.banco == dato.banco, models.Pago.monto == dato.monto).first()
        if pago_existente:
            raise HTTPException(status_code=409, detail='Error: Ya existe un pago con la misma referencia, banco y monto.')
        banco_normalizado = dato.banco.strip()
        if banco_normalizado not in bank_rules.get_available_banks():
            try:
                estrategia = bank_rules.get_bank_strategy(banco_normalizado)
                if estrategia and estrategia.name and (estrategia.name != 'Desconocido'):
                    banco_normalizado = estrategia.name
            except Exception:
                pass
        tasa_info = await get_tasa_bcv(db)
        tasa_actual = float(tasa_info['tasa'])
        monto_usd_calc = round(dato.monto / tasa_actual, 2) if tasa_actual > 0 else 0.0
        nuevo_pago = models.Pago(referencia=dato.referencia, banco=banco_normalizado, monto=dato.monto, ruta_imagen='', file_hash=None, cliente_id=dato.cliente_id, tasa_momento=tasa_actual, tasa_cambio=tasa_actual, monto_usd=monto_usd_calc)
        db.add(nuevo_pago)
        db.commit()
        db.refresh(nuevo_pago)
        registrar_auditoria(db, pago_id=nuevo_pago.id, accion='create_manual', detalles='Registro manual por el usuario')
        return {'mensaje': 'Pago manual registrado'}
    except Exception as e:
        logger.error(f'Error manual: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@router.patch('/pagos/{pago_id}', response_model=schemas.PagoResponse)
async def actualizar_pago_manual(pago_id: int, datos: schemas.PagoManual, db: Session=Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail='Pago no encontrado')
    if pago.ruta_imagen:
        raise HTTPException(status_code=400, detail='Solo se pueden editar pagos manuales sin imagen.')
    if not datos.banco or not datos.referencia or datos.monto is None:
        raise HTTPException(status_code=400, detail='Banco, referencia y monto son obligatorios. Asegúrate de completar todos los campos y que el monto sea mayor a cero.')
    pago.banco = datos.banco.strip()
    pago.referencia = datos.referencia.strip()
    pago.monto = datos.monto
    pago.cliente_id = datos.cliente_id
    tasa_info = await get_tasa_bcv(db)
    nueva_tasa = float(tasa_info['tasa'])
    pago.tasa_momento = nueva_tasa
    pago.tasa_cambio = nueva_tasa
    pago.monto_usd = round(datos.monto / nueva_tasa, 2) if nueva_tasa > 0 else 0.0
    db.commit()
    db.refresh(pago)
    registrar_auditoria(db, pago_id=pago.id, accion='update_manual', detalles=f'Pago manual editado: ref {pago.referencia}, monto {pago.monto}, banco {pago.banco}')
    return pago

@router.post('/reprocesar/{pago_id}')
def reprocesar_pago(pago_id: int, db: Session=Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail='Pago no encontrado')
    if not pago.ruta_imagen or not os.path.exists(pago.ruta_imagen):
        raise HTTPException(status_code=400, detail='Este pago no tiene imagen para reprocesar')
    try:
        resultado = ocr_engine.procesar_imagen(pago.ruta_imagen)
        banco_dest_nuevo = resultado.get('banco_destino', pago.banco_destino)
        ref_nueva = resultado.get('referencia', pago.referencia)
        monto_nuevo = float(resultado.get('monto') or pago.monto)
        pago.referencia = ref_nueva
        pago.banco_destino = banco_dest_nuevo
        pago.monto = monto_nuevo
        db.commit()
        detalles_audit = f'Re-escaneo IA. Ref: {ref_nueva}, Banco: {pago.banco}, Monto: {monto_nuevo}'
        registrar_auditoria(db, pago_id=pago.id, accion='reprocess', detalles=detalles_audit)
        return {'mensaje': 'Pago reprocesado con éxito', 'nuevos_datos': resultado}
    except Exception as e:
        logger.error(f'Error reprocesando: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@router.patch('/pago/{pago_id}/estado')
def cambiar_estado_pago(pago_id: int, update_data: schemas.EstadoUpdate, db: Session=Depends(get_db)):
    """Actualiza el estado de un pago y registra en la auditoría."""
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail='Pago no encontrado')
    estado_anterior = pago.estado
    nuevo_estado = update_data.estado.value
    if estado_anterior == nuevo_estado:
        return {'mensaje': 'El estado ya es el solicitado, no se realizaron cambios.'}
    pago.estado = nuevo_estado
    registrar_auditoria(db, pago_id=pago.id, accion='update_status', detalles=f"Estado cambiado de '{estado_anterior}' a '{nuevo_estado}'")
    return {'mensaje': f"Estado del pago {pago_id} actualizado a '{nuevo_estado}'"}

@router.get('/pago/{pago_id}/historial')
def obtener_historial(pago_id: int, db: Session=Depends(get_db)):
    historial = db.query(models.PagoHistory).filter(models.PagoHistory.pago_id == pago_id).order_by(desc(models.PagoHistory.id)).all()
    return historial

@router.get('/pagos/{pago_id}/imagen')
def obtener_imagen_pago(pago_id: int, db: Session=Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail='Pago no encontrado')
    if not pago.ruta_imagen:
        raise HTTPException(status_code=404, detail='Este pago no tiene imagen asociada')
    filename = os.path.basename(pago.ruta_imagen)
    if not filename:
        raise HTTPException(status_code=404, detail='Ruta de imagen inválida')
    return {'imagen_url': f'/uploads/{filename}'}

@router.post('/pagos/{pago_id}/reprocesar')
def reprocesar_pago_alias(pago_id: int, db: Session=Depends(get_db)):
    return reprocesar_pago(pago_id, db)

@router.post('/pagos/{pago_id}/estado')
def cambiar_estado_pago_alias(pago_id: int, update_data: schemas.EstadoUpdate, db: Session=Depends(get_db)):
    return cambiar_estado_pago(pago_id, update_data, db)

@router.delete('/pagos/{pago_id}/')
def eliminar_pago_por_id(pago_id: int, db: Session=Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail='Pago no encontrado')
    if pago.ruta_imagen and os.path.exists(pago.ruta_imagen):
        try:
            os.remove(pago.ruta_imagen)
        except Exception as e:
            logger.warning(f'No se pudo eliminar el archivo físico {pago.ruta_imagen}: {e}')
    db.delete(pago)
    db.commit()
    return {'mensaje': 'Eliminado correctamente'}

@router.delete('/eliminar-pago-ref/{referencia}')
def eliminar_pago(referencia: str, confirm: bool=False, db: Session=Depends(get_db)):
    pago = db.query(models.Pago).filter(models.Pago.referencia == referencia).first()
    if not pago:
        if referencia.isdigit():
            pago = db.query(models.Pago).filter(models.Pago.id == int(referencia)).first()
        if not pago:
            raise HTTPException(status_code=404, detail='Pago no encontrado')
    if confirm:
        if pago.ruta_imagen and os.path.exists(pago.ruta_imagen):
            try:
                os.remove(pago.ruta_imagen)
            except Exception as e:
                logger.warning(f'No se pudo eliminar el archivo físico {pago.ruta_imagen}: {e}')
        db.delete(pago)
        db.commit()
        return {'mensaje': 'Eliminado correctamente'}
    return {'mensaje': 'Se requiere confirmación (?confirm=true)'}

