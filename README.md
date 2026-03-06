Sistema de Conciliación de Pagos con OCR y IA
=============================================

Este proyecto es una aplicación web construida con FastAPI para gestionar, verificar y conciliar pagos recibidos a través de imágenes de comprobantes (captures). Utiliza Tesseract para el OCR, Groq para el análisis con IA, y SQLAlchemy para la persistencia de datos.

## Características

-   **Carga de Pagos**: Sube imágenes de comprobantes de pago.
-   **OCR Automático**: Extrae automáticamente referencia, monto y banco de la imagen.
-   **Análisis con IA**: Utiliza un modelo de lenguaje para interpretar y estructurar los datos del OCR.
-   **Anti-Duplicados**: Evita el procesamiento de la misma imagen o del mismo pago (referencia + monto + banco).
-   **Gestión de Clientes**: Asocia pagos a clientes recurrentes.
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
    ```

## Uso

1.  **Ejecutar el servidor de desarrollo:**
    ```bash
    uvicorn main:app --reload
    ```
    La aplicación estará disponible en `http://127.0.0.1:8000`.

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

## Endpoints de la API

La documentación interactiva de la API está disponible en `http://127.0.0.1:8000/docs`.

-   `POST /subir-pago/`: Sube una imagen para procesar un pago.
-   `POST /pago-manual/`: Registra un pago manualmente sin imagen.
-   `GET /ver-pagos/`: Lista los pagos con paginación.
-   `GET /buscar-pagos/`: Busca pagos por un término de búsqueda.
-   `PATCH /pago/{pago_id}/estado`: Cambia el estado de un pago (`verificado`, `falso`, etc.).
-   `POST /reprocesar/{pago_id}`: Vuelve a ejecutar el OCR en un pago existente.
-   `POST /clientes/`: Crea un nuevo cliente.
-   `GET /clientes/`: Lista todos los clientes.
