
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import io
import schemas
from database import get_db
from utils import _query_reporte, _query_pagos_detalle, _crear_excel_reporte, _crear_pdf_reporte, _crear_nombre_archivo, _agregar_total_reporte
from config import get_config_value
import os

router = APIRouter(tags=['reportes'])

def _cargar_logo_bytes(logo_path: str) -> Optional[bytes]:
    if logo_path and os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            return f.read()
    return None

@router.get('/reportes/export/')
def exportar_reportes(tipo_reporte: str='mensual', format: str='xlsx', start_date: Optional[datetime]=None, end_date: Optional[datetime]=None, db: Session=Depends(get_db)):
    formato = format.lower()
    if formato not in ['xlsx', 'pdf']:
        raise HTTPException(status_code=400, detail='Formato de exportación no válido. Usa pdf o xlsx.')
    empresa_nombre = get_config_value(db, 'REPORTE_EMPRESA_NOMBRE', '')
    rif = get_config_value(db, 'REPORTE_RIF', '')
    contacto = get_config_value(db, 'REPORTE_CONTACTO', '')
    color_primario = get_config_value(db, 'REPORTE_COLOR_PRIMARY', '#1e3a8a')
    color_secundario = get_config_value(db, 'REPORTE_COLOR_SECONDARY', '#dbeafe')
    logo_path = get_config_value(db, 'REPORTE_LOGO_PATH', '')
    logo_bytes = _cargar_logo_bytes(logo_path) if logo_path else None
    resultados = _query_reporte(db, tipo_reporte.lower(), start_date, end_date)
    pagos_detalle = _query_pagos_detalle(db, start_date, end_date)
    if formato == 'xlsx':
        contenido = _crear_excel_reporte(resultados, pagos_detalle, tipo_reporte, start_date, end_date, empresa_nombre, color_primario, color_secundario, logo_bytes, rif, contacto)
        media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        contenido = _crear_pdf_reporte(resultados, pagos_detalle, tipo_reporte, start_date, end_date, empresa_nombre, color_primario, color_secundario, logo_bytes, rif, contacto)
        media_type = 'application/pdf'
    return StreamingResponse(io.BytesIO(contenido), media_type=media_type, headers={'Content-Disposition': f'attachment; filename="{_crear_nombre_archivo(tipo_reporte, formato)}"'})

@router.get('/reportes/', response_model=schemas.ReporteResponse)
def obtener_reportes(tipo_reporte: str='mensual', start_date: Optional[datetime]=None, end_date: Optional[datetime]=None, db: Session=Depends(get_db)):
    """Genera un reporte agregado por período y devuelve totales con rangos."""
    resultados = _query_reporte(db, tipo_reporte.lower(), start_date, end_date)
    totales = _agregar_total_reporte(resultados)
    return {'tipo_reporte': tipo_reporte, 'resultados': resultados, **totales}

