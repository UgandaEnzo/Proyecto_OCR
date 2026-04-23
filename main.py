
from routers import clientes, pagos, reportes, gestion, ia
from config import get_config_value

import os
import sys
import logging
from enum import Enum
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from logging.handlers import RotatingFileHandler
from sqlalchemy.orm import Session
from sqlalchemy import exc as sa_exc, inspect, text
base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
dotenv_path = base_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)
uploads_dir = base_dir / 'uploads'
static_dir = base_dir / 'static'
uploads_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)
from database import engine, get_db, Base, SQLALCHEMY_DATABASE_URL
import models

def _setup_logging() -> logging.Logger:
    """Configura un logger robusto que escribe en consola y en archivos rotativos."""
    os.makedirs('logs', exist_ok=True)
    logger = logging.getLogger('ocr_api')
    if logger.handlers:
        return logger
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s - %(message)s')
    file_handler = RotatingFileHandler(os.path.join('logs', 'app.log'), maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    return logger
logger = _setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el inicio y cierre de la aplicación de forma segura."""
    try:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        if 'pagos' in inspector.get_table_names():
            columnas_pagos = [col['name'] for col in inspector.get_columns('pagos')]
            if 'tasa_momento' not in columnas_pagos:
                with engine.begin() as conn:
                    conn.execute(text('ALTER TABLE pagos ADD COLUMN tasa_momento FLOAT'))
                logger.info("Se agregó la columna 'tasa_momento' en la tabla pagos.")
        logger.info('Sistema de Base de Datos inicializado: Tablas verificadas.')
        logger.info('🚀 [SISTEMA] Arquitectura OCR: RapidOCR (Motor Único)')
    except Exception as e:
        logger.error('❌ Error crítico al inicializar la base de datos: %s', e)
    yield
app = FastAPI(docs_url='/api/docs', redoc_url=None, openapi_url='/api/openapi.json', lifespan=lifespan)

@app.exception_handler(sa_exc.OperationalError)
def handle_db_operational_error(request, exc):
    logger.critical('Error de conexión con la base de datos: %s', exc)
    return JSONResponse(status_code=503, content={'detail': 'Base de datos no disponible. Revisa la configuración en tu .env.'})

@app.exception_handler(UnicodeDecodeError)
def handle_db_unicode_decode_error(request, exc):
    logger.critical('Error de codificación con la base de datos (común en Windows): %s', exc)
    return JSONResponse(status_code=503, content={'detail': 'Error de codificación con la BD. Revisa credenciales y considera definir PGCLIENTENCODING en .env.'})
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')
app.mount('/uploads', StaticFiles(directory=str(uploads_dir)), name='uploads')

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    favicon_path = str(static_dir / 'favicon.ico')
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    else:
        return Response(status_code=204)

@app.get('/healthz', include_in_schema=False)
def healthz():
    """Verifica que el servidor está en línea."""
    return {'status': 'ok'}

def require_api_key(x_api_key: Optional[str]=Header(None), db: Session = Depends(get_db)):
    configured_key = get_config_value(db, 'API_KEY')
    if configured_key and (not x_api_key or x_api_key != configured_key):
        raise HTTPException(status_code=401, detail='API key inválida o no proporcionada')
    return True

class EstadoPago(str, Enum):
    no_verificado = 'no_verificado'
    verificado = 'verificado'
    falso = 'falso'

def registrar_auditoria(db: Session, pago_id: int, accion: str, detalles: str):
    """Función para ahorrar trabajo: registra movimientos en el historial"""
    nuevo_historial = models.PagoHistory(pago_id=pago_id, accion=accion, detalles=detalles, usuario='sistema_ia')
    db.add(nuevo_historial)
    db.commit()

def _get_env_path() -> Path:
    return base_dir / '.env'



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

@app.get('/', include_in_schema=False)
async def root_redirect():
    """Redirige a la interfaz web estática."""
    return RedirectResponse(url='/static/index.html')

@app.get('/panel')
async def panel_redirect():
    """Endpoint visible en la documentación que abre la vista del panel web."""
    return RedirectResponse(url='/static/index.html')

app.include_router(clientes.router)
app.include_router(pagos.router)
app.include_router(reportes.router)
app.include_router(gestion.router)
app.include_router(ia.router)
