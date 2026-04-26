# Proyecto: Sistema de Conciliación de Pagos con OCR + IA

## Resumen

Aplicación FastAPI para conciliación de pagos con detección OCR y soporte de visión IA. El proyecto combina RapidOCR para extracción de texto y Groq Vision para identificación de banco y datos relevantes en comprobantes.

## Componentes principales

- `main.py`: API principal con endpoints de pagos, reportes, clientes, IA, detección de banco y salud.
- `static/`: frontend Vue.js con interfaz de carga de imagen, vista previa y formulario editable.
- `database.py` / `models.py`: configuración de SQLAlchemy y modelos de datos.
- `ocr_engine.py` / `ocr_utils.py`: motor OCR y adaptador RapidOCR.
- `exchange.py`: lógica de tasa BCV con fallback.
- `setup_project.py`: script de build que crea `.venv_build`, instala dependencias y ejecuta PyInstaller.
- `OcrApp.spec`: configuración PyInstaller, incluyendo datos `static/` y dependencias ocultas.

## Estado actual

- El proyecto ya tiene documentación básica en `README.md`.
- Dependencias de producción están en `requirements.txt`.
- Dependencias de desarrollo actualizadas en `requirements-dev.txt`.
- Detección de banco usa ahora un endpoint `/detectar-banco-vision/` y compresión de imagen para reducir payload.
- `OcrApp.spec` corregido para calcular `root_dir` con `sys.argv[0]` en lugar de `__file__`.
- Se recomienda `GROQ_MODEL="llama-3.2-11b-vision-preview"` para detección visual con imágenes.

## Dependencias clave

- fastapi, uvicorn, python-multipart
- sqlalchemy, psycopg2-binary, pydantic
- rapidocr_onnxruntime, opencv-python-headless, Pillow
- reportlab, openpyxl
- groq, httpx, python-dotenv
- pyinstaller, pytest, alembic, build, twine

## Tareas completadas

- Corrección de layout y carga de imagen en UI.
- Envío de imagen comprimida y Base64 para detección de banco.
- Actualización de `requirements-dev.txt` con herramientas de empaquetado modernas.
- Solución de error de PyInstaller en `OcrApp.spec`.

## Recomendaciones inmediatas

1. Ejecutar de nuevo `py setup_project.py` tras la corrección de `OcrApp.spec`.
2. Probar el endpoint `/detectar-banco-vision/` con comprobante real.
3. Verificar exportes en PDF y XLSX de reportes.
4. Confirmar carga de `.env` junto al ejecutable.

## Observaciones

- El ejecutable no embebe `.env`; debe disponerse externamente en el despliegue.
- Groq Vision depende de una API key válida y modelo compatible.
- El sistema está preparado para soportar mejoras en detección de banco y reglas de validación.
