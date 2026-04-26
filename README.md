Sistema de Conciliación de Pagos con OCR y IA
=============================================

Este proyecto es una solución de backend y panel administrativo construida con FastAPI para automatizar la conciliación de pagos. Utiliza **RapidOCR** para la extracción de texto, **Groq** para análisis semántico, y **SQLAlchemy** para la gestión de datos y auditoría.

## Características principales

-   **Carga de pagos por imagen**: administra recibos y comprobantes con extracción OCR.
-   **OCR + IA**: combinación de RapidOCR y Groq para detectar referencia, monto, banco y datos de pago.
-   **Detección híbrida de bancos**: detección visual con Groq Vision y validación por OCR para mayor precisión.
-   **Vista previa Base64 instantánea**: la imagen se renderiza en el navegador y se envía comprimida para evitar cargas excesivas.
-   **Exportes máximos**: reportes en `PDF` y `XLSX` con periodos `diario`, `semanal`, `quincenal`, `mensual`, `trimestral`, `semestral` y `anual`.
-   **Normalización de períodos**: el campo `Periodo` se formatea correctamente para evitar desbordes y errores de presentación.
-   **Conexión BCV robusta**: fallback en 4 niveles para obtener tasa de cambio (API, scraping, DB, env).
-   **Auditoría completa**: historial de cambios por pago, incluidos ediciones y re-procesos.
-   **Administración de clientes**: alta, edición, eliminación y historial de pagos por cliente.
-   **Prevención de duplicados**: hashing SHA256 y comparación por referencia/monto/banco.
-   **Interfaz web ligera**: frontend con Vue.js en `static/` y un panel de administración integrado.

## Estructura del proyecto

```
/
├── alembic/              # Migraciones de base de datos
├── bank_rules/           # Reglas para detección de bancos
├── static/               # Frontend (HTML, CSS, JS)
├── uploads/              # Imágenes subidas
├── .env                  # Variables de entorno (NO subir a Git)
├── database.py           # Configuración de SQLAlchemy
├── dist/                 # Ejecutable generado por PyInstaller
├── main.py               # Aplicación FastAPI principal
├── models.py             # Modelos de datos SQLAlchemy
├── ocr_engine.py         # Motor OCR + IA
├── ocr_utils.py          # Adaptadores de RapidOCR
├── exchange.py           # Lógica de tasa BCV y conversión
├── run.py                # Lanzador del servidor / ejecutable
├── setup_project.py      # Script para build y empaquetado
├── OcrApp.spec           # Configuración de PyInstaller
├── requirements.txt      # Dependencias de producción
└── requirements-dev.txt  # Dependencias de desarrollo y empaquetado
```

## Requisitos previos

- Python 3.10 o superior
- PostgreSQL para la base de datos
- Acceso a internet para consultas de tasa BCV y algunas llamadas de IA

## Configuración del entorno

1.  Clonar el repositorio.
2.  Crear y activar el entorno virtual:
    ```powershell
    python -m venv .venv
    & .\.venv\Scripts\Activate.ps1
    ```
3.  Instalar dependencias de producción:
    ```powershell
    pip install -r requirements.txt
    ```
4.  Instalar dependencias de desarrollo (opcional para pruebas y empaquetado):
    ```powershell
    pip install -r requirements-dev.txt
    ```

## Versiones recomendadas

Este proyecto se ha probado con las siguientes versiones aproximadas de dependencias:

- `fastapi` 0.118.x
- `uvicorn[standard]` 0.30.x
- `pydantic` 2.8.x
- `sqlalchemy` 2.0.x
- `openpyxl` 3.1.x
- `reportlab` 4.x
- `groq` 1.0.x
- `httpx` 0.24.x
- `python-dotenv` 1.x

## Archivo `.env`

Crea un archivo `.env` en la raíz del proyecto con al menos estas variables:

```env
DATABASE_URL="postgresql://user:password@host:port/database"
GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
GROQ_MODEL="llama-3.2-11b-vision-preview"
LOG_LEVEL=INFO
MAX_UPLOAD_MB=10
```

> Nota: para detección visual se recomienda `GROQ_MODEL="llama-3.2-11b-vision-preview"`. Este proyecto usa Groq Vision para identificar banco, SUDEBAN, referencia y monto desde la imagen.
> Si trabajas solo con texto o deseas ahorrar tokens, puedes usar un modelo de texto compatible de Groq.
>
> Si no usas `DATABASE_URL`, puedes definir las variables separadas `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT` y `DB_NAME`.

## Ejecutar en desarrollo

```powershell
uvicorn main:app --reload
```

- Frontend disponible en `http://127.0.0.1:8000`
- Documentación Swagger en `http://127.0.0.1:8000/api/docs`
- OpenAPI JSON en `http://127.0.0.1:8000/api/openapi.json`

## Empaquetar como ejecutable (.exe)

El proyecto incluye un flujo de build completo con `setup_project.py` y `OcrApp.spec`.

1.  Instala las dependencias de desarrollo:
    ```powershell
    pip install -r requirements-dev.txt
    ```
2.  Ejecuta el build desde la raíz del proyecto:
    ```powershell
    python setup_project.py
    ```

El script crea un entorno virtual de empaquetado en `.venv_build`, instala las dependencias desde `requirements.txt` y `requirements-dev.txt`, y ejecuta PyInstaller con `OcrApp.spec`.

El artefacto resultante se genera en `dist\OcrApp.exe` o en la carpeta `dist` asociada a la salida de PyInstaller.

> Nota: el ejecutable **no incluye** el archivo `.env`. `run.py` busca `.env` en el directorio del ejecutable y en los padres inmediatos, así que coloca `.env` junto al `.exe` o en un directorio superior.

## Endpoints principales

- `GET /` → redirige a la interfaz web en `static/index.html`
- `GET /api/docs` → documentación Swagger
- `GET /reportes/` → devuelve reportes agregados por período
- `GET /reportes/export/` → exporta reportes en `pdf` o `xlsx`
- `POST /subir-pago/` → sube comprobante de pago por imagen
- `POST /detectar-banco-vision/` → detecta banco e intenta leer datos usando Groq Vision + OCR
- `POST /pago-manual/` → crea pago manual sin imagen
- `GET /clientes/` → lista clientes
- `POST /clientes/` → crea cliente
- `PUT /clientes/{cliente_id}` → actualiza cliente
- `GET /clientes/{cliente_id}/pagos` → historial de pagos por cliente
- `POST /convertir-a-usd/` → convierte Bs a USD usando tasa BCV actual

## Solución de problemas

### No se encuentra `.env`

El ejecutable carga `.env` desde el directorio del ejecutable o desde sus padres. Si no se encuentra, muestra una advertencia y deja de usar variables de entorno basadas en archivo.

### Error 401 con Groq

- Revisa `GROQ_API_KEY`.
- Asegúrate de que la clave no tenga espacios invisibles.
- El sistema puede reintentar con lógica de fallback si la IA no responde.

## Actualizaciones recientes

### 2026-04-14: Correcciones de reporte y exportación

- Se corrigió la exportación de `reportes` para todos los períodos (`diario`, `semanal`, `quincenal`, `mensual`, `trimestral`, `semestral`, `anual`).
- Se normalizó el campo `Periodo` en los reportes para que siempre muestre fechas legibles y evitar roturas de tabla en PDF/XLSX.
- Se mejoró la creación de archivos Excel con celdas de texto envuelto y tamaños máximos de columna.
- Se mejoró la generación de PDF con tablas y estilos estables para exportaciones largas.

### 2026-04-04: Reglas bancarias y registro manual

- El selector de bancos y el filtro de pagos usan la lista canónica de `bank_rules`.
- El backend normaliza el banco en pagos manuales.
- Se agregó un sistema de detección dual con texto y reglas visuales para mejorar la identificación de bancos.

### 2026-04-01: Módulo BCV robusto

- Flujo de tasa con fallback: API + scraping + DB + env.
- Nuevos endpoints para `tasa-bcv` y `convertir-a-usd`.
- Mejor resiliencia frente a fallos de red o cambios en la fuente de datos.
