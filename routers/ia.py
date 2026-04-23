
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from datetime import datetime, timedelta
import os
import tempfile
import base64
import models
import schemas
import ocr_engine
from database import get_db
from config import get_config_value, set_config_value
from utils import require_api_key, _verificar_estado_groq, _detectar_banco_con_groq

router = APIRouter(tags=['ia'])

@router.post('/IA/consultar/')
async def consultar_datos_ia(query: schemas.ChatQuery, db: Session=Depends(get_db)):
    """Permite hacer preguntas sobre los pagos en lenguaje natural."""
    total_clientes = db.query(models.Cliente).count()
    total_pagos = db.query(models.Pago).count()
    total_historial = db.query(models.PagoHistory).count()
    pagos_por_estado = db.query(models.Pago.estado, func.count(models.Pago.id).label('conteo'), func.sum(models.Pago.monto).label('total_monto')).group_by(models.Pago.estado).all()
    contexto_por_estado = '\n'.join([f'- {estado}: {conteo} pagos, total {total_monto or 0.0:,.2f} Bs' for estado, conteo, total_monto in pagos_por_estado]) or '- Sin registros de pago por estado.'
    mejor_cliente = db.query(models.Cliente.nombre, func.count(models.Pago.id).label('total')).join(models.Pago).group_by(models.Cliente.id).order_by(text('total DESC')).first()
    nombre_mejor = mejor_cliente.nombre if mejor_cliente else 'N/A'
    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    recaudado_mes = db.query(func.sum(models.Pago.monto)).filter(models.Pago.fecha_registro >= inicio_mes).scalar() or 0.0
    inicio_30_dias = datetime.now() - timedelta(days=30)
    recaudado_30_dias = db.query(func.sum(models.Pago.monto)).filter(models.Pago.fecha_registro >= inicio_30_dias).scalar() or 0.0
    inicio_60_dias = datetime.now() - timedelta(days=60)
    recaudado_60_dias = db.query(func.sum(models.Pago.monto)).filter(models.Pago.fecha_registro >= inicio_60_dias).scalar() or 0.0
    ultimos_pagos = db.query(models.Pago).order_by(desc(models.Pago.id)).limit(5).all()
    contexto_pagos = '\n'.join([f"- Ref: {p.referencia}, Banco: {p.banco}, Monto: {p.monto} Bs, Cliente: {(p.cliente.nombre if p.cliente else 'Particular')}" for p in ultimos_pagos]) or '- No hay pagos recientes registrados.'
    ultimas_acciones = db.query(models.PagoHistory).order_by(desc(models.PagoHistory.id)).limit(5).all()
    contexto_historial = '\n'.join([f"- Pago ID: {h.pago_id}, Acción: {h.accion}, Usuario: {h.usuario or 'desconocido'}, Detalles: {h.detalles}" for h in ultimas_acciones]) or '- No hay acciones de historial recientes.'
    ultima_tasa = db.query(models.TasaCambio).order_by(desc(models.TasaCambio.fecha_actualizacion)).first()
    tasa_bcv_texto = f'{ultima_tasa.monto_tasa:.4f} (actualizada {ultima_tasa.fecha_actualizacion})' if ultima_tasa else 'No disponible'
    total_usd_recaudado = db.query(func.sum(models.Pago.monto_usd)).scalar() or 0.0
    tasa_promedio_pagos = db.query(func.avg(models.Pago.tasa_momento)).scalar() or 0.0
    balance_total_bs = db.query(func.sum(models.Pago.monto)).scalar() or 0.0
    prompt = f'\n    Eres un asistente contable experto del Sistema de Conciliación.\n    TABLAS Y ESQUEMA DISPONIBLES EN LA BASE DE DATOS:\n    - clientes(id, nombre, cedula, telefono)\n    - pagos(id, referencia, banco, banco_destino, monto, monto_usd, tasa_momento, tasa_cambio, fecha_registro, ruta_imagen, file_hash, estado, cliente_id)\n    - pagos_history(id, pago_id, accion, detalles, usuario, fecha)\n    - tasas_cambio(id, proveedor, monto_tasa, fecha_actualizacion)\n    RELACIONES:\n    - pago.cliente_id -> cliente.id\n    - un pago puede no tener cliente asociado\n\n    CONTEXTO AGREGADO:\n    - Clientes totales: {total_clientes}\n    - Pagos totales: {total_pagos}\n    - Registros de auditoría: {total_historial}\n    - Pagos por estado:\n{contexto_por_estado}\n    - Total recaudado este mes: {recaudado_mes:,.2f} Bs.\n    - Total recaudado último 30 días: {recaudado_30_dias:,.2f} Bs.\n    - Total recaudado últimos 60 días: {recaudado_60_dias:,.2f} Bs.\n    - Total recaudado en USD (sumatoria de monto_usd): {total_usd_recaudado:,.2f} USD.\n    - Tasa promedio de los últimos pagos: {tasa_promedio_pagos:.4f}.\n    - Balance total en Bs: {balance_total_bs:,.2f} Bs.\n    - Última tasa BCV registrada: {tasa_bcv_texto}\n    - Mejor cliente (frecuencia): {nombre_mejor}\n\n    ÚLTIMOS 5 PAGOS REGISTRADOS:\n    {contexto_pagos}\n\n    ÚLTIMAS 5 ACCIONES DE HISTORIAL:\n    {contexto_historial}\n\n    INSTRUCCIONES:\n    - Usa SOLO los datos proporcionados en este prompt.\n    - No inventes valores, no supongas pagos, clientes ni datos adicionales.\n    - Si no tienes información suficiente para responder, di "No hay suficiente información en los datos".\n    - Responde de forma breve y profesional.\n\n    PREGUNTA DEL USUARIO:\n    {query.pregunta}\n    '
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        response = client.chat.completions.create(messages=[{'role': 'user', 'content': prompt}], model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'), temperature=0.2)
        return {'respuesta': response.choices[0].message.content}
    except Exception:
        return {'respuesta': 'No fue posible procesar la consulta IA en este momento. Comprueba la configuración de GROQ_API_KEY y vuelve a intentarlo.'}

@router.get('/gestion/ia/status')
def estado_groq_api(db: Session=Depends(get_db)):
    api_key = get_config_value(db, 'GROQ_API_KEY', '')
    online, message = _verificar_estado_groq(api_key)
    state = 'online' if online else 'invalid_key' if not api_key else 'offline'
    return {'state': state, 'api_key': api_key, 'message': message}

@router.post('/gestion/ia/key')
def guardar_groq_api_key(data: schemas.GestionApiKey, db: Session=Depends(get_db)):
    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail='La clave de Groq no puede estar vacía.')
    set_config_value(db, 'GROQ_API_KEY', api_key)
    os.environ['GROQ_API_KEY'] = api_key
    online, message = _verificar_estado_groq(api_key)
    state = 'online' if online else 'offline'
    return {'mensaje': 'Clave Groq guardada correctamente.', 'state': state, 'message': message}

@router.post('/detectar-banco/')
async def detectar_banco(file: UploadFile=File(...), auth: bool=Depends(require_api_key)):
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail='Solo se permiten archivos de imagen.')
    temp_file = tempfile.NamedTemporaryFile(suffix=os.path.splitext(file.filename)[1] or '.jpg', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    try:
        with open(temp_path, 'wb') as buffer:
            while (chunk := (await file.read(1024 * 1024))):
                buffer.write(chunk)
        resultado = ocr_engine.procesar_imagen(temp_path)
        if not resultado:
            raise HTTPException(status_code=500, detail='No se pudo procesar la imagen para detección de banco.')
        return {'banco_predicho': resultado.get('banco_predicho'), 'banco_ia': resultado.get('banco_ia'), 'sudeban_code': resultado.get('sudeban_code'), 'referencia': resultado.get('referencia'), 'monto': resultado.get('monto'), 'cedula': resultado.get('cedula'), 'texto_completo': resultado.get('texto_completo')}
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

@router.post('/detectar-banco-vision/')
async def detectar_banco_vision(data: schemas.VisionBankDetectionRequest, auth: bool=Depends(require_api_key)):
    image_base64 = data.image_base64.strip()
    if not image_base64:
        raise HTTPException(status_code=400, detail='Se requiere image_base64.')
    try:
        image_data = base64.b64decode(image_base64.split(',', 1)[-1])
    except Exception:
        raise HTTPException(status_code=400, detail='Base64 inválido para la imagen.')
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    try:
        with open(temp_path, 'wb') as buffer:
            buffer.write(image_data)
        resultado = ocr_engine.procesar_imagen(temp_path) or {}
        groq_info = _detectar_banco_con_groq(image_data)
        banco_predicho = groq_info.get('banco_predicho') or resultado.get('banco_predicho') or resultado.get('banco_ia')
        sudeban_code = groq_info.get('sudeban_code') or resultado.get('sudeban_code')
        return {'banco_predicho': banco_predicho, 'banco_ia': resultado.get('banco_ia'), 'sudeban_code': sudeban_code, 'referencia': resultado.get('referencia'), 'monto': resultado.get('monto'), 'cedula': resultado.get('cedula'), 'texto_completo': resultado.get('texto_completo')}
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

