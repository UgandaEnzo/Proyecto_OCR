# Proyecto: Sistema de Conciliación de Pagos con OCR + IA

## Resumen

Aplicación FastAPI para conciliación de pagos con detección OCR y soporte de visión IA. El proyecto combina RapidOCR para extracción de texto local y OpenRouter (Qwen) con dos modelos especializados para identificación de banco, purificación de texto OCR y chat asistente.

## Componentes principales

- `main.py`: API principal con endpoints de pagos, reportes, clientes, IA, detección de banco y salud.
- `static/`: frontend Vue.js con interfaz de carga de imagen, vista previa y formulario editable.
- `database.py` / `models.py`: configuración de SQLAlchemy y modelos de datos.
- `ocr_engine.py` / `ocr_utils.py`: motor OCR y adaptador RapidOCR.
- `ai_client.py`: cliente unificado OpenRouter para chat, purificación y visión.
- `exchange.py`: lógica de tasa BCV con fallback.
- `setup_project.py`: script de build que crea `.venv_build`, instala dependencias y ejecuta PyInstaller.
- `OcrApp.spec`: configuración PyInstaller, incluyendo datos `static/` y dependencias ocultas.

## Estado actual

- El proyecto ya tiene documentación básica en `README.md`.
- Dependencias de producción están en `requirements.txt`.
- Dependencias de desarrollo actualizadas en `requirements-dev.txt`.
- IA bajo OpenRouter con dos modelos gratuitos especializados:
  - **Visión**: `google/gemma-4-26b-a4b-it:free` (OCR nube + detección de bancos)
  - **Texto**: `nvidia/nemotron-3-super-120b-a12b:free` (purificación OCR + chat asistente)
- Se eliminó Groq y los modelos `qwen/qwen3.6-27b`, `openai/gpt-oss-120b`.
- Parseo local (`_parse_local_fallback`) como respaldo offline cuando OpenRouter no está disponible.
- Dependencia `groq` reemplazada por `openai`.

## Dependencias clave

- fastapi, uvicorn, python-multipart
- sqlalchemy, psycopg2-binary, pydantic
- rapidocr_onnxruntime, opencv-python-headless, Pillow
- reportlab, openpyxl
- openai (cliente HTTP para OpenRouter), httpx, python-dotenv
- pyinstaller, pytest, alembic, build, twine

## Tareas completadas

- Corrección de layout y carga de imagen en UI.
- Envío de imagen comprimida y Base64 para detección de banco.
- Actualización de `requirements-dev.txt` con herramientas de empaquetado modernas.
- Solución de error de PyInstaller en `OcrApp.spec`.
- Unificación de IA: eliminación de Groq, migración a OpenRouter con dos modelos (visión + texto).
- Parseo local offline como respaldo cuando no hay conexión a OpenRouter.
- **Corrección del guardado de clave API**: el frontend ya no fuerza `state='online'`; usa el estado real devuelto por el servidor y refresca el panel tras guardar.
- **Selector de modo OCR funcional**: `procesar_pago_ocr` respeta `MOTOR_OCR_ACTIVO` y decide entre:
  - **Local**: RapidOCR → limpieza IA (OpenRouter text) → fallback regex local.
  - **Nube**: OpenRouter Vision únicamente.
- **Inicialización dinámica de RapidOCR**: `get_engine()` evalúa el modo en cada llamada; permite cambiar entre local/nube sin reiniciar.
- **Migración completa de Groq a OpenRouter en el frontend** del panel de gestión.
- **Modelo de visión actualizado** a `google/gemma-4-26b-a4b-it:free` (Gemma 4 26B A4B, reemplaza a `qwen/qwen-2.5-vl-7b-instruct:free` que fue retirado de la capa gratuita).

## Recomendaciones inmediatas

1. Ejecutar `python setup_project.py` para reconstruir el `.exe` con las nuevas dependencias.
2. Probar el endpoint `/detectar-banco-vision/` con comprobante real (requiere clave OpenRouter válida).
3. Probar modo local: desactivar la clave API en el panel de gestión y verificar que el parseo local funciona.
4. Verificar exportes en PDF y XLSX de reportes.
5. Confirmar carga de `.env` junto al ejecutable.

## Observaciones

- El ejecutable no embebe `.env`; debe disponerse externamente en el despliegue.
- OpenRouter usa dos modelos gratuitos: `google/gemma-4-26b-a4b-it:free` (visión) y `nvidia/nemotron-3-super-120b-a12b:free` (texto).
- El sistema cae a RapidOCR + parseo local si OpenRouter no está disponible.
