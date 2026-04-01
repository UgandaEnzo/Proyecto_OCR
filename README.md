Sistema de Conciliación de Pagos con OCR y IA
=============================================

Este proyecto es una aplicación web construida con FastAPI para gestionar, verificar y conciliar pagos recibidos a través de imágenes de comprobantes (captures). Utiliza Tesseract para el OCR, Groq para el análisis con IA, y SQLAlchemy para la persistencia de datos.

## Características

-   **Carga de Pagos**: Sube imágenes de comprobantes de pago.
-   **OCR Automático**: Extrae automáticamente referencia, monto y banco de la imagen.
-   **Análisis con IA**: Utiliza un modelo de lenguaje para interpretar y estructurar los datos del OCR.
-   **Anti-Duplicados**: Evita el procesamiento de la misma imagen o del mismo pago (referencia + monto + banco).
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
├── ocr_engine.py         # Lógica de procesamiento de imágenes y OCR
├── skill_engine.py       # Lógica de interacción con la API de Groq
└── requirements.txt      # Dependencias de Python
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

4.  **Crear el archivo `.env`:**
    Crea un archivo llamado `.env` en la raíz del proyecto y añade las siguientes variables:
    ```env
    # URL de conexión a tu base de datos PostgreSQL
    DATABASE_URL="postgresql://user:password@host:port/database"

    # Clave de API para el servicio de Groq
    GROQ_API_KEY="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    # --- Variables Opcionales (con valores por defecto) ---
    
    # Ruta al ejecutable de Tesseract-OCR (si no está en el PATH del sistema).
    # Descomenta y ajusta la línea si es necesario.
    # En Windows, usa dobles barras invertidas.
    # TESSERACT_CMD="C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

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
2.  **Tesseract-OCR instalado.** Deberás instalarlo y asegurarte de que su ruta esté en el `PATH` del sistema o configurarla en la variable `TESSERACT_CMD` del archivo `.env`.

**Pasos:**

1.  **Instalar PyInstaller en tu entorno virtual:**
    ```bash
    pip install pyinstaller
    ```

2.  **Crear un script de entrada:**
    PyInstaller no puede ejecutar directamente el comando `uvicorn`. Crea un archivo llamado `run.py` en la raíz del proyecto con el siguiente contenido:

    ```python
    import uvicorn

    if __name__ == "__main__":
        from main import app
        uvicorn.run(app, host="0.0.0.0", port=8000)
    ```

3.  **Ejecutar PyInstaller:**
    Desde la terminal, en la raíz del proyecto, ejecuta el siguiente comando. Este le indica a PyInstaller que cree un solo archivo (`--onefile`), le dé un nombre (`--name`), y que incluya las carpetas y archivos necesarios (`--add-data`).

    ```bash
    # En Windows (usa ; como separador para --add-data)
    pyinstaller --name "OcrApp" --onefile --add-data "static;static" --add-data "skills;skills" --add-data ".env;." run.py
    ```

4.  **Encontrar el ejecutable:**
    Una vez que el proceso termine, encontrarás `OcrApp.exe` dentro de una nueva carpeta llamada `dist`. Puedes copiar este archivo a otra máquina, colocar un archivo `.env` configurado a su lado, y ejecutarlo. La carpeta `uploads/` se creará automáticamente al primer uso.

2.  **Migraciones de Base de Datos (Alembic):**
    Cuando realices cambios en los `models.py`, necesitarás generar y aplicar una migración.

    -   **Generar una nueva migración:**
        ```bash
        alembic revision --autogenerate -m "Descripción del cambio"
        ```
    -   **Aplicar las migraciones:**
        ```bash
        alembic upgrade head
        ```
    -   **Scripts de Mantenimiento**: En la carpeta `scripts/` encontrarás utilidades como `fill_file_hash.py` para poblar el hash de archivos en registros antiguos.

## Endpoints de la API

La documentación interactiva de la API está disponible en `http://127.0.0.1:8000/api/docs`.

-   `POST /subir-pago/`: Sube una imagen para procesar un pago.
-   `POST /pago-manual/`: Registra un pago manualmente sin imagen.
-   `GET /ver-pagos/`: Lista los pagos con paginación.
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
Si ves un error `❌ [SkillEngine] Error en la llamada a Groq: Error code: 401` en la consola:
1. Verifica que la variable `GROQ_API_KEY` en tu archivo `.env` sea correcta.
2. Asegúrate de que tu clave no tenga espacios adicionales.
3. El sistema entrará automáticamente en modo **Fallback** (Reglas Rígidas) si la IA falla, por lo que el OCR seguirá funcionando pero con menor precisión en formatos complejos.

---

## Actualización 2026-04-01: Módulo BCV robusto
Se ha implementado un flujo de tasa BCV con fallback: API + scraping + DB + env. Esta sección detalla los cambios recientes en el proyecto.

### Módulos clave
- main.py: API principal, endpoints de subir-pago, pago-manual, ver-pagos, tasa-bcv, convertir-a-usd, clientes, auditoría, anti-duplicados.
- exchange.py: gestión de tasa BCV y conversión Bs/USD con fallback y persistencia en TasaCambio.
- models.py: SQLAlchemy ORM para Cliente, Pago, PagoHistory, TasaCambio.
- ocr_engine.py: extracción OCR + fallback con IA (SkillEngine) o reglas con bank_rules.
- database.py: configuración SQLAlchemy y sesión.
- skill_engine.py: interacción con servicio Groq (IA).

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

