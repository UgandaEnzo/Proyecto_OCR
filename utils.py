import os
from pathlib import Path
from typing import Optional, List
import traceback
import sys
base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
uploads_dir = base_dir / 'uploads'
from datetime import datetime, timedelta
import io
import re
import json
import base64
from PIL import Image
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from fastapi import Header, HTTPException, Depends
import logging
from logging.handlers import RotatingFileHandler

import models
import bank_rules
from database import SQLALCHEMY_DATABASE_URL, get_db
from config import get_config_value

# Configuración del logger
def _setup_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("ocr_api")
    if logger.handlers:
        return logger
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    file_handler = RotatingFileHandler(os.path.join("logs", "app.log"), maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    return logger

logger = _setup_logging()

def require_api_key(x_api_key: Optional[str]=Header(None), db: Session = Depends(get_db)):
    configured_key = get_config_value(db, 'API_KEY')
    if configured_key and (not x_api_key or x_api_key != configured_key):
        raise HTTPException(status_code=401, detail='API key inválida o no proporcionada')
    return True

def registrar_auditoria(db: Session, pago_id: int, accion: str, detalles: str):
    nuevo_historial = models.PagoHistory(pago_id=pago_id, accion=accion, detalles=detalles, usuario='sistema_ia')
    db.add(nuevo_historial)
    db.commit()

def _get_database_type() -> str:
    url = SQLALCHEMY_DATABASE_URL.lower()
    if url.startswith('sqlite://'):
        return 'sqlite'
    if url.startswith('postgresql://') or url.startswith('postgres://'):
        return 'postgresql'
    return 'unsupported'

def _get_sqlite_db_path() -> Optional[Path]:
    if _get_database_type() != 'sqlite':
        return None
    if SQLALCHEMY_DATABASE_URL.startswith('sqlite:///'):
        sqlite_path = SQLALCHEMY_DATABASE_URL.replace('sqlite:///', '', 1)
        return Path(sqlite_path).resolve()
    if SQLALCHEMY_DATABASE_URL.startswith('sqlite://'):
        sqlite_path = SQLALCHEMY_DATABASE_URL.replace('sqlite://', '', 1)
        return Path(sqlite_path).resolve()
    return None
def _verificar_estado_groq(api_key: str) -> tuple[bool, str]:
    if not api_key:
        return (False, 'No se ha configurado la clave Groq.')
    try:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=3.0)
        client.chat.completions.create(messages=[{'role': 'user', 'content': 'Responde con pong'}], model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'), temperature=0.0, max_tokens=1, timeout=3.0)
        return (True, 'Clave Groq cargada y verificada.')
    except Exception as e:
        logger.warning('No se pudo verificar Groq API: %s', e)
        return (False, 'No se puede conectar a Groq. Comprueba tu conexión a internet y la clave de API.')

def _agregar_total_reporte(resultado: List[dict]) -> dict:
    total_bs = sum((item['total_bs'] for item in resultado))
    total_usd = sum((item['total_usd'] for item in resultado))
    total_pagos = sum((item['conteo'] for item in resultado))
    return {'total_bs': total_bs, 'total_usd': total_usd, 'total_pagos': total_pagos}

def _query_reporte(db: Session, tipo_reporte: str, fecha_inicio: Optional[datetime], fecha_fin: Optional[datetime]) -> List[dict]:
    interval_map = {'diario': 'day', 'semanal': 'week', 'mensual': 'month', 'trimestral': 'quarter', 'anual': 'year'}
    if tipo_reporte not in interval_map and tipo_reporte not in ['quincenal', 'semestral']:
        raise HTTPException(status_code=400, detail=f'Tipo de reporte desconocido: {tipo_reporte}')
    if tipo_reporte == 'quincenal':
        periodo_expr = func.date_trunc('month', models.Pago.fecha_registro) + func.floor((func.extract('day', models.Pago.fecha_registro) - 1) / 15) * text("interval '15 days'")
    elif tipo_reporte == 'semestral':
        periodo_expr = func.date_trunc('year', models.Pago.fecha_registro) + func.floor((func.extract('month', models.Pago.fecha_registro) - 1) / 6) * text("interval '6 months'")
    else:
        periodo_expr = func.date_trunc(interval_map[tipo_reporte], models.Pago.fecha_registro)
    query = db.query(periodo_expr.label('periodo'), func.sum(models.Pago.monto).label('total_bs'), func.sum(models.Pago.monto_usd).label('total_usd'), func.count(models.Pago.id).label('conteo'), func.min(models.Pago.fecha_registro).label('desde'), func.max(models.Pago.fecha_registro).label('hasta'))
    if fecha_inicio:
        query = query.filter(models.Pago.fecha_registro >= fecha_inicio)
    if fecha_fin:
        query = query.filter(models.Pago.fecha_registro <= fecha_fin)
    grouped = query.group_by(periodo_expr).order_by(periodo_expr).all()
    resultados = []
    for r in grouped:
        periodo_text = _simplificar_periodo(r.periodo)
        resultados.append({'periodo': periodo_text, 'desde': r.desde, 'hasta': r.hasta, 'total_bs': float(r.total_bs or 0), 'total_usd': float(r.total_usd or 0), 'conteo': int(r.conteo or 0)})
    return resultados

def _simplificar_periodo(periodo: Optional[object]) -> str:
    if periodo is None:
        return ''
    if isinstance(periodo, datetime):
        return periodo.strftime('%d-%m-%Y')
    if isinstance(periodo, str):
        periodo = periodo.strip()
        if not periodo:
            return ''
        try:
            if 'T' in periodo:
                fecha = datetime.fromisoformat(periodo)
                return fecha.strftime('%d-%m-%Y')
        except Exception:
            pass
        if 'T' in periodo:
            return periodo.split('T')[0]
        if ' ' in periodo and ':' in periodo:
            return periodo.split(' ')[0]
        return periodo
    return str(periodo)

def _limpiar_periodo_texto(periodo: Optional[object]) -> str:
    if periodo is None:
        return ''
    if isinstance(periodo, datetime):
        return periodo.strftime('%d-%m-%Y')
    if isinstance(periodo, str):
        texto = periodo.strip()
        if not texto:
            return ''
        match = re.search('(\\d{2})[-/](\\d{2})[-/](\\d{4})', texto)
        if match:
            return f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
        match = re.search('(\\d{4})-(\\d{2})-(\\d{2})', texto)
        if match:
            return f'{match.group(3)}-{match.group(2)}-{match.group(1)}'
        texto = texto.splitlines()[0].strip()
        return texto if len(texto) <= 32 else texto[:32] + '...'
    return str(periodo)

def _query_pagos_detalle(db: Session, fecha_inicio: Optional[datetime], fecha_fin: Optional[datetime]) -> List[models.Pago]:
    """Obtiene la lista detallada de pagos para el reporte."""
    query = db.query(models.Pago)
    if fecha_inicio:
        query = query.filter(models.Pago.fecha_registro >= fecha_inicio)
    if fecha_fin:
        query = query.filter(models.Pago.fecha_registro <= fecha_fin)
    return query.order_by(models.Pago.fecha_registro.desc()).all()

def parse_monto_string(valor) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    texto = re.sub('\\s+', '', texto)
    texto = texto.replace('Bs', '').replace('Bs.', '').replace('Bs,', '')
    texto = re.sub('[^0-9\\,\\.\\-]', '', texto)
    if texto.count(',') > 0 and texto.count('.') > 0:
        if texto.rfind(',') > texto.rfind('.'):
            texto = texto.replace('.', '')
            texto = texto.replace(',', '.')
        else:
            texto = texto.replace(',', '')
    else:
        texto = texto.replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0

def _extraer_codigo_sudeban(texto: Optional[str]) -> Optional[str]:
    if not texto:
        return None
    texto = str(texto)
    match = re.search('\\b(\\d{4})\\b', texto)
    if match:
        return match.group(1)
    return None

def _agrupar_totales_sudeban(pagos_detalle: List[models.Pago]) -> List[dict]:
    grupos = {}
    for pago in pagos_detalle:
        codigo = _extraer_codigo_sudeban(pago.banco) or _extraer_codigo_sudeban(pago.banco_destino)
        if codigo:
            banco_formal = bank_rules.get_bank_by_sudeban_code(codigo)
            etiqueta = f'{codigo} - {banco_formal}' if banco_formal != 'Desconocido' else f'{codigo} - Desconocido'
        else:
            etiqueta = 'Desconocido'
            codigo = 'N/A'
        clave = (codigo, etiqueta)
        if clave not in grupos:
            grupos[clave] = {'sudeban_code': codigo, 'banco_label': etiqueta, 'total_bs': 0.0, 'total_usd': 0.0, 'conteo': 0}
        grupos[clave]['total_bs'] += parse_monto_string(pago.monto)
        grupos[clave]['total_usd'] += parse_monto_string(pago.monto_usd)
        grupos[clave]['conteo'] += 1
    return [{'sudeban_code': codigo, 'banco_label': etiqueta, 'total_bs': valores['total_bs'], 'total_usd': valores['total_usd'], 'conteo': valores['conteo']} for (codigo, etiqueta), valores in sorted(grupos.items(), key=lambda item: item[0])]

def _crear_excel_reporte(resultados: List[dict], pagos_detalle: List[models.Pago], tipo_reporte: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumen'
    header_fill = PatternFill(start_color='1e3a8a', end_color='1e3a8a', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    right_align = Alignment(horizontal='right')
    ws.append(['Reporte de Conciliación', tipo_reporte.title()])
    ws.append(['Generado', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    ws.append(['Periodo', start_date.strftime('%Y-%m-%d') if start_date else 'Completo', end_date.strftime('%Y-%m-%d') if end_date else 'Completo'])
    ws.append([])
    sudeban_summary = _agrupar_totales_sudeban(pagos_detalle)
    ws.append(['Código SUDEBAN', 'Banco Origen', 'Total Bs', 'Total USD', 'Conteo'])
    for cell in ws[5]:
        cell.fill = header_fill
        cell.font = header_font
    for row in sudeban_summary:
        ws.append([row['sudeban_code'], row['banco_label'], row['total_bs'], row['total_usd'], row['conteo']])
    ws.append([])
    ws.append(['Resumen Agregado'])
    ws.append(['Periodo', 'Desde', 'Hasta', 'Total Bs', 'Total USD', 'Conteo'])
    for cell in ws[ws.max_row]:
        cell.fill = header_fill
        cell.font = header_font
    for item in resultados:
        periodo_text = _limpiar_periodo_texto(item['periodo'])
        ws.append([periodo_text, item['desde'].strftime('%Y-%m-%d') if item['desde'] else '', item['hasta'].strftime('%Y-%m-%d') if item['hasta'] else '', parse_monto_string(item.get('total_bs')), parse_monto_string(item.get('total_usd')), item.get('conteo', 0)])
        periodo_cell = ws[f'A{ws.max_row}']
        periodo_cell.alignment = Alignment(wrap_text=True, vertical='top')
    totales = _agregar_total_reporte(resultados)
    ws.append(['Totales', '', '', totales['total_bs'], totales['total_usd'], totales['total_pagos']])
    for sheet in wb.worksheets:
        for columna in sheet.columns:
            max_length = 0
            column_letter = columna[0].column_letter
            for cell in columna:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            sheet.column_dimensions[column_letter].width = min(max_length + 2, 30)
            if column_letter == 'A':
                for cell in columna:
                    if cell.value is not None and isinstance(cell.value, str) and (len(cell.value) > 30):
                        lines = (len(cell.value) - 1) // 30 + 1
                        current_height = sheet.row_dimensions[cell.row].height or 15
                        sheet.row_dimensions[cell.row].height = max(current_height, lines * 15)
        for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row):
            for cell in row:
                if cell.column_letter in ('C', 'D') and isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00 "Bs"'
                if cell.column_letter == 'E' and isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00'
    ws_det = wb.create_sheet(title='Detalle de Pagos')
    ws_det.append(['Referencia', 'Banco Origen', 'Fecha', 'Monto (Bs)', 'Tasa ($)', 'Monto ($)'])
    for cell in ws_det[1]:
        cell.fill = header_fill
        cell.font = header_font
    for p in pagos_detalle:
        ws_det.append([p.referencia, p.banco, p.fecha_registro.strftime('%Y-%m-%d %H:%M') if p.fecha_registro else 'N/A', parse_monto_string(p.monto), parse_monto_string(p.tasa_cambio), parse_monto_string(p.monto_usd)])
    for row in ws_det.iter_rows(min_row=2, max_row=ws_det.max_row):
        for cell in row:
            if cell.column_letter == 'D' and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00 "Bs"'
                cell.alignment = right_align
            if cell.column_letter in ('E', 'F') and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'
                cell.alignment = right_align
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

def _crear_pdf_reporte(resultados: List[dict], pagos_detalle: List[models.Pago], tipo_reporte: str, start_date: Optional[datetime], end_date: Optional[datetime]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    normal_style = styles['Normal']
    section_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], spaceAfter=10, spaceBefore=15)
    story = []
    story.append(Paragraph(f'Reporte de Conciliación Bancaria - {tipo_reporte.title()}', title_style))
    story.append(Paragraph(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    range_parts = []
    if start_date:
        range_parts.append(f"Desde: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        range_parts.append(f"Hasta: {end_date.strftime('%Y-%m-%d')}")
    filtro_texto = ' - '.join(range_parts) if range_parts else 'Rango: completo'
    story.append(Paragraph(filtro_texto, normal_style))
    story.append(Spacer(1, 15))
    sudeban_summary = _agrupar_totales_sudeban(pagos_detalle)
    story.append(Paragraph('Resumen por Código SUDEBAN', section_style))
    data_sudeban = [['Código SUDEBAN', 'Banco Origen', 'Total Bs', 'Total USD', 'Conteo']]
    for item in sudeban_summary:
        data_sudeban.append([item['sudeban_code'], item['banco_label'], f"{item['total_bs']:.2f}", f"{item['total_usd']:.2f}", str(item['conteo'])])
    if len(data_sudeban) == 1:
        data_sudeban.append(['No hay datos', '', '', '', ''])
    table_sudeban = Table(data_sudeban, colWidths=[90, 160, 90, 90, 60])
    style_sudeban = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('ALIGN', (2, 1), (3, -1), 'RIGHT'), ('ALIGN', (4, 1), (4, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))]
    for row_idx in range(1, len(data_sudeban)):
        if row_idx % 2 == 1:
            style_sudeban.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f3f4f6')))
    table_sudeban.setStyle(TableStyle(style_sudeban))
    story.append(table_sudeban)
    story.append(Spacer(1, 20))
    story.append(Paragraph('Resumen Agregado', section_style))
    periodo_style = ParagraphStyle('PeriodoCell', parent=normal_style, fontName='Helvetica', fontSize=8, leading=10, wordWrap='CJK')
    data = [['Periodo', 'Desde', 'Hasta', 'Total Bs', 'Total USD', 'Conteo']]
    for item in resultados:
        data.append([Paragraph(_limpiar_periodo_texto(item['periodo']), periodo_style), item['desde'].strftime('%Y-%m-%d') if item['desde'] else '', item['hasta'].strftime('%Y-%m-%d') if item['hasta'] else '', f"{parse_monto_string(item.get('total_bs')):.2f}", f"{parse_monto_string(item.get('total_usd')):.2f}", str(item.get('conteo', 0))])
    totales = _agregar_total_reporte(resultados)
    data.append(['Totales', '', '', f"{totales['total_bs']:.2f}", f"{totales['total_usd']:.2f}", str(totales['total_pagos'])])
    table = Table(data, colWidths=[120, 65, 65, 75, 75, 50])
    style = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('ALIGN', (3, 1), (4, -1), 'RIGHT'), ('ALIGN', (5, 1), (5, -1), 'RIGHT'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))]
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 1:
            style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f3f4f6')))
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph('Detalle Individual de Pagos', section_style))
    data_det = [['Referencia', 'Banco', 'Fecha', 'Monto Bs', 'Tasa ($)', 'Monto USD']]
    for p in pagos_detalle:
        data_det.append([p.referencia, p.banco or '-', p.fecha_registro.strftime('%Y-%m-%d') if p.fecha_registro else 'N/A', f'{parse_monto_string(p.monto):.2f}', f'{parse_monto_string(p.tasa_cambio):.2f}', f'{parse_monto_string(p.monto_usd):.2f}'])
    if len(data_det) == 1:
        data_det.append(['Sin movimientos', '-', '-', '-', '-', '-'])
    table_det = Table(data_det, colWidths=[80, 110, 70, 75, 55, 75])
    style_det = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('ALIGN', (3, 1), (3, -1), 'RIGHT'), ('ALIGN', (4, 1), (5, -1), 'RIGHT'), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1'))]
    for row_idx in range(1, len(data_det)):
        if row_idx % 2 == 1:
            style_det.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f3f4f6')))
    table_det.setStyle(TableStyle(style_det))
    story.append(table_det)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def _crear_nombre_archivo(tipo_reporte: str, formato: str) -> str:
    sufijo = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'reportes-{tipo_reporte}-{sufijo}.{formato}'

def _parse_groq_bank_response(texto: str) -> dict:
    if not texto:
        return {}
    texto = texto.strip()
    try:
        encontrado = re.search('\\{.*\\}', texto, re.S)
        if encontrado:
            return json.loads(encontrado.group(0))
    except Exception:
        pass
    parsed = {}
    match = re.search('"?banco_predicho"?\\s*[:=]\\s*"?([^"\\\'\\n]+)', texto, re.I)
    if match:
        parsed['banco_predicho'] = match.group(1).strip()
    match = re.search('"?sudeban_code"?\\s*[:=]\\s*"?([^"\\\'\\n]+)', texto, re.I)
    if match:
        parsed['sudeban_code'] = match.group(1).strip()
    if not parsed:
        parsed['banco_predicho'] = texto.splitlines()[0].strip()
    return parsed

def _comprimir_imagen_para_groq(image_bytes: bytes, max_side: int=720, quality: int=60) -> bytes:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert('RGB')
            max_dimension = max(img.width, img.height)
            if max_dimension > max_side:
                scale = max_side / max_dimension
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
            with io.BytesIO() as output:
                img.save(output, format='JPEG', quality=quality, optimize=True)
                return output.getvalue()
    except Exception as e:
        logger.debug('No se pudo comprimir la imagen para Groq, se usa el original: %s', e)
        return image_bytes

def _detectar_banco_con_groq(image_bytes: bytes) -> dict:
    api_key = os.getenv('GROQ_API_KEY', '').strip()
    if not api_key:
        return {}
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        image_bytes_for_groq = _comprimir_imagen_para_groq(image_bytes)
        image_b64 = base64.b64encode(image_bytes_for_groq).decode('utf-8')
        prompt_text = 'Eres un experto en reconocer bancos venezolanos a partir de comprobantes de pago. Devuelve un JSON válido con los campos banco_predicho y sudeban_code. Si no puedes identificar el banco, usa Desconocido. Responde únicamente con JSON válido, sin texto adicional.'
        response = client.chat.completions.create(messages=[{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image_b64}}, {'type': 'text', 'text': prompt_text}]}], model=os.getenv('GROQ_MODEL', 'llama-3.2-11b-vision-preview'), temperature=0.0, max_tokens=150)
        content = ''
        if getattr(response, 'choices', None):
            choice = response.choices[0]
            message = getattr(choice, 'message', None)
            if isinstance(message, dict):
                content = message.get('content', '')
            elif hasattr(message, 'content'):
                content = message.content or ''
            else:
                content = str(message or '')
        return _parse_groq_bank_response(content)
    except Exception as e:
        logger.warning('Groq Vision fallo: %s', e)
        return {}
