Sistema de Conciliación de Pagos con OCR y IA
=============================================

Este proyecto es una solución de backend y panel administrativo construida con FastAPI para automatizar la conciliación de pagos. Utiliza **RapidOCR** para la extracción de texto, **Groq (Llama 3)** para el análisis semántico con IA, y **SQLAlchemy** para la gestión de datos y auditoría.

## Características

-   **Carga de Pagos**: Sube imágenes de comprobantes de pago.
-   **OCR Automático**: Extrae automáticamente referencia, monto y banco de la imagen.
-   **Análisis con IA**: Utiliza un modelo de lenguaje para interpretar y estructurar los datos del OCR.
-   **Integridad Financiera**: Cálculos con precisión decimal (Decimal Type) para evitar errores de redondeo.
-   **Seguridad Anti-Fraude**: Sistema de hashing SHA256 para evitar duplicidad de comprobantes físicos.
-   **Resiliencia de Tasa**: Sistema de 4 niveles para obtención de tasa BCV (API, Scraping, DB, Env).
-   **Trazabilidad**: Auditoría completa de cada cambio en los estados de pago.

## Calidad del Código
El proyecto sigue principios **SOLID** y utiliza `Pydantic` para validación de datos en tiempo real, asegurando que solo información limpia llegue a la base de datos.
-   **Reglas bancarias ampliadas**: Soporte directo para más bancos venezolanos y detección reforzada con el módulo `bank_rules`.
-   **Filtro de banco dinámico**: La UI carga la lista canónica de bancos desde el backend para que los filtros y los pagos manuales sean consistentes.
-   **Exportación de reportes**: Descarga reportes agregados como PDF o Excel directamente desde la interfaz.
-   **Anti-Duplicados**: Evita el procesamiento de la misma imagen o del mismo pago (referencia + monto + banco).
-   **Registro manual normalizado**: El formulario manual ahora utiliza una lista de bancos validada y un backend que normaliza las entradas.
-   **Gestión de Clientes**: Directorio completo que permite buscar, registrar, editar y eliminar clientes, además de visualizar su historial de pagos individual.
-   **Calculadora BCV**: Herramienta de conversión de moneda integrada que utiliza la tasa oficial del Banco Central de Venezuela con sistema de contingencia (fallback).
-   **Auditoría**: Registra un historial de cambios para cada pago.
-   **Interfaz Web**: Panel de control interactivo construido con Vue.js y Bootstrap.

## Estructura del Proyecto

```
/
├── alembic/              # Directorio de migraciones de base de datos
├── static/               # Archivos del frontend (HTML, CSS, JS)
│   ├── app.js
│   └── index.html
├── uploads/              # Directorio donde se guardan las imágenes de los pagos
├── .env                  # Archivo de variables de entorno (NO subir a Git)
├── main.py               # Archivo principal de la aplicación FastAPI
├── models.py             # Modelos de la base de datos (SQLAlchemy)
├── database.py           # Configuración de la conexión a la base de datos
├── ocr_engine.py         # Orquestador del flujo OCR (RapidOCR + Groq AI)
├── ocr_utils.py          # Utilidades y carga del motor RapidOCR
├── bank_rules/           # Reglas deterministas por banco (paquete modular)
├── exchange.py           # Gestión de tasa BCV y conversiones
├── scripts/              # Utilidades y pruebas de desarrollo (no se empaqueta en el .exe)
├── setup_project.py      # Script de automatización de entorno y compilación
├── run.py                # Script de entrada para el servidor
├── OcrApp.spec           # Configuración de PyInstaller para empaquetado
├── requirements.txt      # Dependencias de producción
└── requirements-dev.txt  # Dependencias de desarrollo y empaquetado
```

## Configuración del Entorno

1.  **Clonar el repositorio**

2.  **Crear y activar un entorno virtual:**
    ```powershell
    python -m venv .venv
    & .\.venv\Scripts\Activate.ps1
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
    > Si tu editor muestra errores de importación, asegúrate de seleccionar el intérprete Python de tu entorno virtual `.venv`.
    > Nota: Se recomienda Python 3.10 o superior (compatible con 3.14+).
    > Para herramientas de desarrollo, migraciones y empaquetado opcional, instala también `requirements-dev.txt`.

4.  **Crear el archivo `.env`:**
    Crea un archivo llamado `.env` en la raíz del proyecto y añade las siguientes variables:
    ```env
    # URL de conexión a tu base de datos PostgreSQL.
    # Se recomienda usar DATABASE_URL para simplificar la configuración.
    DATABASE_URL="postgresql://user:password@host:port/database"

    # Si no usas DATABASE_URL, define las siguientes variables de conexión:
    # DB_USER="usuario"
    # DB_PASS="clave"
    # DB_HOST="localhost"
    # DB_PORT="5432"
    # DB_NAME="nombre_de_la_base"

    # Clave de API para el servicio de Groq
    GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # --- Variables de OCR y configuración ---

    # Modelo de Groq para análisis de pago móvil
    GROQ_MODEL="llama3-8b-8192"

    # URL opcional para el servicio de tasa BCV
    # TASA_BCV_API_URL="https://api.bcv.example/v1/tasa"
    # TASA_BCV_SKIP_TLS_VERIFY=false

    # Nivel de logs: DEBUG, INFO, WARNING, ERROR
    LOG_LEVEL=INFO

    # Tamaño máximo de subida en MB
    MAX_UPLOAD_MB=10

    # Si se define, las rutas protegidas exigirán el header: x-api-key
    # API_KEY="una-clave-secreta-muy-larga"
    ```

## Uso

1.  **Ejecutar el servidor de desarrollo:**
    ```bash
    uvicorn main:app --reload
    ```
    -   El panel de control estará en `http://127.0.0.1:8000`.
    -   La documentación de la API (Swagger) estará en `http://127.0.0.1:8000/api/docs`.

## Crear un Ejecutable (.exe)

Puedes empaquetar esta aplicación en un único archivo ejecutable para distribuirla y ejecutarla en otras máquinas Windows sin necesidad de instalar Python o un entorno virtual. Para esto, usaremos `PyInstaller`.

**Importante:** El ejecutable seguirá necesitando dos cosas en la máquina de destino:
1.  **Conexión a la base de datos PostgreSQL.** El `.env` junto al `.exe` debe apuntar a ella.
2.  **Motor ONNX.** El ejecutable utiliza `rapidocr_onnxruntime`, que es significativamente más ligero y rápido que PyTorch/EasyOCR.

**Pasos:**

1.  **Instalar PyInstaller en tu entorno virtual:**
    ```bash
    pip install pyinstaller
    ```

2.  **Instalar dependencias de desarrollo (opcional):**
    Si necesitas empaquetar el proyecto, ejecutar migraciones o ejecutar pruebas, instala también los extras de desarrollo:
    ```bash
    pip install -r requirements-dev.txt
    ```

3.  **Ejecutar PyInstaller:**
    Desde la terminal, en la raíz del proyecto, ejecuta el siguiente comando. Este le indica a PyInstaller que cree un solo archivo (`--onefile`), le dé un nombre (`--name`), y que incluya los archivos necesarios de `static`.

    ```bash
    # En Windows (usa ; como separador para --add-data)
    pyinstaller --name "OcrApp" --onefile --clean \
      --hidden-import rapidocr_onnxruntime \
      --hidden-import pillow \
      --hidden-import numpy \
      --hidden-import openpyxl \
      --hidden-import reportlab \
      --add-data "static;static" run.py
    ```

    > Nota: `scripts/` es solo para desarrollo y pruebas locales. No se agrega al ejecutable porque no se incluye como recurso ni se importa en tiempo de ejecución.

    > Recomendado: usa `OcrApp.spec` para incluir correctamente los recursos de RapidOCR en el ejecutable.

    > Nota: El archivo `.env` debe situarse en la misma carpeta que el `.exe` para que la aplicación cargue la configuración correctamente.

4.  **Encontrar el ejecutable:**
    Una vez que el proceso termine, encontrarás `OcrApp.exe` dentro de una nueva carpeta llamada `dist`. Puedes copiar este archivo a otra máquina, colocar un archivo `.env` configurado a su lado, y ejecutarlo. La carpeta `uploads/` se creará automáticamente al primer uso.

5.  **Migraciones de Base de Datos (Alembic):**
    Cuando realices cambios en los `models.py`, necesitarás generar y aplicar una migración.

    -   **Generar una nueva migración:**
        ```bash
        alembic revision --autogenerate -m "Descripción del cambio"
        ```
    -   **Aplicar las migraciones:**
        ```bash
        alembic upgrade head
        ```
    -   **Mantenimiento**: Las migraciones se manejan con `alembic` en la raíz del proyecto.
## Endpoints de la API

La documentación interactiva de la API está disponible en `http://127.0.0.1:8000/api/docs`.

-   `POST /subir-pago/`: Sube una imagen para procesar un pago.
-   `POST /pago-manual/`: Registra un pago manualmente sin imagen.
-   `GET /bancos/`: Devuelve la lista canónica de bancos soportados por el filtro y el formulario manual.
-   `GET /ver-pagos/`: Lista los pagos con paginación y admite filtro opcional por `banco` y `q`.
-   `GET /pagos/`: Lista los pagos filtrados por banco emisor u origen con paginación.
-   `GET /reportes/`: Genera reportes agregados por período (`diario`, `semanal`, `quincenal`, `mensual`, `trimestral`, `semestral`, `anual`) y acepta `start_date` / `end_date`.
-   `GET /reportes/export/`: Exporta el reporte como `pdf` o `xlsx` usando los mismos filtros de período y fechas.
-   `GET /buscar-pagos/`: Busca pagos por número de referencia con paginación.
-   `PATCH /pago/{pago_id}/estado`: Cambia el estado de un pago (`verificado`, `falso`, etc.).
-   `POST /reprocesar/{pago_id}`: Vuelve a ejecutar el OCR en un pago existente.
-   `GET /pago/{pago_id}/historial`: Obtiene la auditoría de cambios de un pago.
-   `DELETE /eliminar-pago-ref/{referencia}`: Elimina un pago por su referencia (requiere `confirm=true`).
-   `GET /clientes/`: Lista y busca clientes en el directorio.
-   `POST /clientes/`: Crea un nuevo cliente.
-   `PUT /clientes/{cliente_id}`: Actualiza la información de un cliente existente.
-   `DELETE /clientes/{cliente_id}`: Elimina a un cliente del sistema.
-   `GET /clientes/{cliente_id}/pagos`: Obtiene el historial de pagos de un cliente específico.
-   `POST /convertir-a-usd/`: Realiza la conversión de montos de Bs a USD usando la tasa oficial.

## Solución de Problemas

### Error 401 - Invalid API Key (Groq)
Si ves un error `⚠️ [IA] Error en limpieza con Groq` en la consola:
1. Verifica que la variable `GROQ_API_KEY` en tu archivo `.env` sea correcta.
2. Asegúrate de que tu clave no tenga espacios adicionales.
3. El sistema entrará automáticamente en modo **Fallback** (reglas rudas) si la IA falla, por lo que el OCR seguirá funcionando pero con menor precisión en formatos complejos.

---

## Actualización 2026-04-01: Módulo BCV robusto
Se ha implementado un flujo de tasa BCV con fallback: API + scraping + DB + env. Esta sección detalla los cambios recientes en el proyecto.

### Módulos clave
- main.py: API principal, endpoints de subir-pago, pago-manual, ver-pagos, tasa-bcv, convertir-a-usd, clientes, auditoría y anti-duplicados.
- exchange.py: gestión de tasa BCV y conversión Bs/USD con fallback y persistencia en TasaCambio.
- models.py: SQLAlchemy ORM para Cliente, Pago, PagoHistory y TasaCambio.
- ocr_engine.py: extracción OCR con RapidOCR y limpieza semántica con Groq.
- database.py: configuración SQLAlchemy y sesión.
- bank_rules/: reglas deterministas por banco y estrategia de detección.

### Endpoint de tasa BCV (nuevo / mejorado)
- GET /tasa-bcv/ => devuelve tasa_bcv, fecha_consulta, origen, es_fallback.
- POST /tasa-bcv/ => actualiza valor con x-api-key.
- POST /convertir-a-usd/ => convierte con tasa_bcv actual y devuelve monto_usd, origen, es_fallback.

### Nota sobre entorno y certificados
- TASA_BCV_API_URL en .env.
- Si hay problemas SSL, usar TASA_BCV_SKIP_TLS_VERIFY=true.

### Prueba de funcionamiento
1. uvicorn main:app --reload
2. GET /tasa-bcv/
3. POST /convertir-a-usd/ {"monto_bs":10000}
4. confirmar origen != DB si se obtiene tasa actual de API/scraping.

## Actualización 2026-04-04: Reglas bancarias y registro manual
Esta versión añade las siguientes mejoras:
- `bank_rules` ahora expone una lista canónica de bancos con soporte extendido para múltiples bancos venezolanos.
- El motor legacy de OCR usa `bank_rules` como fallback para identificar el banco cuando la IA no es concluyente.
- El formulario de pago manual muestra un selector de bancos cargado desde `GET /bancos/` y normaliza los bancos en el backend.
- El filtro de pagos por banco en la UI consume la misma lista canónica, reduciendo inconsistencias entre filtros y registros.
