
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
import os
import io
import csv
import models
import schemas
from database import get_db
from config import get_config_value, set_config_value
from utils import _get_sqlite_db_path, _get_database_type, uploads_dir, set_env_value

router = APIRouter(tags=['gestion'])

@router.get('/gestion/db/status')
def estado_db():
    db_type = _get_database_type()
    if db_type == 'sqlite':
        db_path = _get_sqlite_db_path()
        return {'database_type': 'sqlite', 'path': str(db_path) if db_path else None, 'exists': bool(db_path and db_path.exists()), 'message': 'SQLite local detectada. Importación de .db disponible.'}
    if db_type == 'postgresql':
        return {'database_type': 'postgresql', 'message': 'PostgreSQL detectada. No hay archivo SQLite local. Solo la importación de pagos CSV está disponible.', 'info': 'PostgreSQL'}
    return {'database_type': 'unsupported', 'message': 'Tipo de base de datos no soportado para gestión automática.', 'info': 'No disponible'}

@router.get('/gestion/db/export-pagos')
def exportar_pagos_csv(db: Session=Depends(get_db)):
    pagos = db.query(models.Pago).order_by(models.Pago.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'referencia', 'banco', 'banco_destino', 'monto', 'monto_usd', 'tasa_momento', 'tasa_cambio', 'fecha_registro', 'estado', 'cliente_id', 'cliente_nombre', 'cliente_cedula', 'ruta_imagen'])
    for pago in pagos:
        writer.writerow([pago.id, pago.referencia, pago.banco, pago.banco_destino or '', pago.monto, pago.monto_usd, pago.tasa_momento, pago.tasa_cambio, pago.fecha_registro.isoformat() if pago.fecha_registro else '', pago.estado, pago.cliente_id, pago.cliente.nombre if pago.cliente else '', pago.cliente.cedula if pago.cliente else '', pago.ruta_imagen or ''])
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=pagos_export.csv'})

@router.post('/gestion/db/import-pagos')
def importar_pagos_csv(file: UploadFile=File(...), db: Session=Depends(get_db)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail='El archivo debe ser CSV.')
    contenido = file.file.read().decode('utf-8', errors='replace')
    lector = csv.DictReader(io.StringIO(contenido))
    creados = 0
    actualizados = 0
    omitidos = 0
    for fila in lector:
        referencia = (fila.get('referencia') or fila.get('Referencia') or '').strip()
        banco = (fila.get('banco') or fila.get('Banco') or '').strip()
        monto_texto = (fila.get('monto') or fila.get('Monto') or '').strip()
        if not referencia or not banco or (not monto_texto):
            omitidos += 1
            continue
        try:
            monto = float(monto_texto.replace(',', '.'))
        except ValueError:
            omitidos += 1
            continue
        pago_existente = db.query(models.Pago).filter(models.Pago.referencia == referencia, models.Pago.banco == banco).first()
        if pago_existente:
            omitidos += 1
            continue
        cliente = None
        cedula = (fila.get('cliente_cedula') or fila.get('cedula') or fila.get('Cedula') or '').strip()
        nombre_cliente = (fila.get('cliente_nombre') or fila.get('cliente') or fila.get('Cliente') or '').strip()
        telefono = (fila.get('telefono') or fila.get('Telefono') or fila.get('telefono_cliente') or '').strip()
        if cedula:
            cliente = db.query(models.Cliente).filter(models.Cliente.cedula == cedula).first()
            if not cliente and nombre_cliente:
                cliente = models.Cliente(nombre=nombre_cliente, cedula=cedula, telefono=telefono or None)
                db.add(cliente)
                db.flush()
        fecha_registro = None
        fecha_texto = (fila.get('fecha_registro') or fila.get('fecha') or fila.get('Fecha') or '').strip()
        if fecha_texto:
            for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    fecha_registro = datetime.strptime(fecha_texto, fmt)
                    break
                except ValueError:
                    continue
        monto_usd_texto = (fila.get('monto_usd') or fila.get('Monto_USD') or fila.get('montoUsd') or '').strip()
        tasa_momento_texto = (fila.get('tasa_momento') or fila.get('Tasa_Momento') or '').strip()
        tasa_cambio_texto = (fila.get('tasa_cambio') or fila.get('Tasa_Cambio') or '').strip()
        estado = (fila.get('estado') or fila.get('Estado') or 'no_verificado').strip() or 'no_verificado'
        banco_destino = (fila.get('banco_destino') or fila.get('Banco_Destino') or '').strip() or None
        ruta_imagen = (fila.get('ruta_imagen') or fila.get('Ruta_Imagen') or '').strip() or None

        def parse_float(valor, fallback=None):
            if not valor:
                return fallback
            try:
                return float(valor.replace(',', '.'))
            except ValueError:
                return fallback
        pago = models.Pago(referencia=referencia, banco=banco, banco_destino=banco_destino, monto=monto, monto_usd=parse_float(monto_usd_texto, 0.0), tasa_momento=parse_float(tasa_momento_texto, 1.0), tasa_cambio=parse_float(tasa_cambio_texto, 1.0), fecha_registro=fecha_registro, ruta_imagen=ruta_imagen, estado=estado, cliente_id=cliente.id if cliente else None)
        db.add(pago)
        creados += 1
    db.commit()
    return {'mensaje': f'Pagos importados: {creados}, omitidos: {omitidos}.', 'creados': creados, 'omitidos': omitidos}

@router.post('/gestion/db/clear-test-data')
def limpiar_datos_prueba(data: schemas.ConfirmBody, db: Session=Depends(get_db)):
    if not data.confirm:
        raise HTTPException(status_code=400, detail='Se requiere confirmación para borrar datos de prueba.')
    pagos = db.query(models.Pago).filter(or_(models.Pago.estado == 'no_verificado', models.Pago.referencia.ilike('%test%'))).all()
    deleted = len(pagos)
    for pago in pagos:
        db.delete(pago)
    db.commit()
    return {'mensaje': f'{deleted} pagos de prueba eliminados correctamente.'}

@router.get('/gestion/db/credentials')
def obtener_credenciales(db: Session=Depends(get_db)):
    return {'admin_user': get_config_value(db, 'ADMIN_USER', ''), 'admin_pass': get_config_value(db, 'ADMIN_PASS', '')}

@router.post('/gestion/db/credentials')
def guardar_credenciales(data: schemas.GestionCredentials, db: Session=Depends(get_db)):
    set_config_value(db, 'ADMIN_USER', data.admin_user.strip())
    set_config_value(db, 'ADMIN_PASS', data.admin_pass.strip())
    os.environ['ADMIN_USER'] = data.admin_user.strip()
    os.environ['ADMIN_PASS'] = data.admin_pass.strip()
    set_env_value('ADMIN_USER', data.admin_user.strip())
    set_env_value('ADMIN_PASS', data.admin_pass.strip())
    return {'mensaje': 'Credenciales guardadas correctamente.'}

@router.get('/gestion/ocr/mode')
def obtener_modo_ocr(db: Session=Depends(get_db)):
    modo = get_config_value(db, 'MOTOR_OCR_ACTIVO', 'rapidocr').lower()
    return {'modo': 'local' if modo == 'rapidocr' else 'nube', 'modo_raw': modo}

@router.post('/gestion/ocr/mode')
def actualizar_modo_ocr(data: schemas.GestionOcrMode, db: Session=Depends(get_db)):
    modo = data.modo.strip().lower()
    if modo not in ['local', 'nube']:
        raise HTTPException(status_code=400, detail='El modo OCR debe ser "local" o "nube".')
    modo_raw = 'rapidocr' if modo == 'local' else 'openrouter_vision'
    set_config_value(db, 'MOTOR_OCR_ACTIVO', modo_raw)
    os.environ['MOTOR_OCR_ACTIVO'] = modo_raw
    set_env_value('MOTOR_OCR_ACTIVO', modo_raw)
    return {'mensaje': f'Modo OCR cambiado a {modo} correctamente.', 'modo': modo}

@router.get('/gestion/reporte/config')
def obtener_config_reporte(db: Session = Depends(get_db)):
    return {
        'nombre_empresa': get_config_value(db, 'REPORTE_EMPRESA_NOMBRE', ''),
        'rif': get_config_value(db, 'REPORTE_RIF', ''),
        'contacto': get_config_value(db, 'REPORTE_CONTACTO', ''),
        'color_primario': get_config_value(db, 'REPORTE_COLOR_PRIMARY', '#1e3a8a'),
        'color_secundario': get_config_value(db, 'REPORTE_COLOR_SECONDARY', '#dbeafe'),
    }

@router.post('/gestion/reporte/config')
def guardar_config_reporte(data: schemas.ReporteConfigSchema, db: Session = Depends(get_db)):
    set_config_value(db, 'REPORTE_EMPRESA_NOMBRE', data.nombre_empresa.strip())
    set_config_value(db, 'REPORTE_RIF', data.rif.strip())
    set_config_value(db, 'REPORTE_CONTACTO', data.contacto.strip())
    set_config_value(db, 'REPORTE_COLOR_PRIMARY', data.color_primario.strip())
    set_config_value(db, 'REPORTE_COLOR_SECONDARY', data.color_secundario.strip())
    return {'mensaje': 'Configuración de reportes guardada.'}

@router.post('/gestion/reporte/logo')
async def subir_logo_reporte(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail='Solo se permiten archivos de imagen.')
    logos_dir = uploads_dir / 'logos'
    logos_dir.mkdir(parents=True, exist_ok=True)
    for old in logos_dir.iterdir():
        old.unlink()
    ext = os.path.splitext(file.filename)[1] or '.png'
    logo_path = str(logos_dir / f'logo_reporte{ext}')
    with open(logo_path, 'wb') as f:
        while chunk := (await file.read(1024 * 1024)):
            f.write(chunk)
    set_config_value(db, 'REPORTE_LOGO_PATH', logo_path)
    return {'mensaje': 'Logo subido correctamente.', 'logo_url': f'/uploads/logos/{os.path.basename(logo_path)}'}

@router.get('/gestion/reporte/logo')
def obtener_logo_reporte(db: Session = Depends(get_db)):
    path = get_config_value(db, 'REPORTE_LOGO_PATH', '')
    if path and os.path.exists(path):
        return {'logo_url': f'/uploads/logos/{os.path.basename(path)}'}
    return {'logo_url': None}

