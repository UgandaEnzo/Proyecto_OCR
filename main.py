
from routers import clientes, pagos, reportes, gestion, ia
from utils import require_api_key, registrar_auditoria, _setup_logging

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import exc as sa_exc, inspect, text
base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
dotenv_path = base_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)
uploads_dir = base_dir / 'uploads'
static_dir = base_dir / 'static'
uploads_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)
from database import engine, get_db, Base
import models

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
                logger.warning(
                    "La columna 'tasa_momento' no existe en la tabla 'pagos'. "
                    "Ejecuta: alembic upgrade head"
                )
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
