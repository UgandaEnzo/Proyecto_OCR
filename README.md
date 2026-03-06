Proyecto Sistema OCR Pagos Móviles
=================================

Instrucciones rápidas

0. Instalar dependencias (recomendado):

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

1. Configurar variables de entorno (recomendado):

- Copia `.env.example` a `.env` y ajusta valores (por ejemplo credenciales de PostgreSQL).
- Este proyecto usa `python-dotenv` para cargar automáticamente `.env` al iniciar.

2. Activar entorno:

```powershell
& .\.venv\Scripts\Activate.ps1
```

3. Ejecutar servidor en desarrollo:

```powershell
uvicorn main:app --reload
```

4. Abrir el panel y la documentación:

- Panel (por defecto): `http://127.0.0.1:8000/`
- Swagger (API docs): `http://127.0.0.1:8000/api/docs`

Variables de entorno recomendadas

- Base de datos:
  - `DATABASE_URL` (recomendado) o `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `DB_NAME`
  - (Windows, opcional) `PGCLIENTENCODING` o `DB_CLIENT_ENCODING` si aparece `UnicodeDecodeError` al conectar
- OCR:
  - `TESSERACT_CMD` (ej: `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- API:
  - `API_KEY` (opcional, si se define se requiere header `x-api-key`)
- Uploads:
  - `MAX_UPLOAD_MB` (por defecto: 10)
- Logs:
  - `LOG_LEVEL` (por defecto: INFO)

Nota: no subas tu `.env` al repositorio (contiene secretos). Usa `.env.example` como plantilla.

Migraciones y `file_hash`:

- Para producción se recomienda usar Alembic. Pasos rápidos:
    1. Configura `alembic.ini` y `env.py` para usar la URL de `DATABASE_URL` o `database.SQLALCHEMY_DATABASE_URL`.
    2. Aplica migraciones: `alembic upgrade head`.
    3. Rellena los hashes para registros existentes: `python scripts/fill_file_hash.py`.
    4. (Opcional) Antes de activar índice único de `file_hash`, detecta duplicados: `python scripts/find_duplicate_hashes.py`.

El script `scripts/fill_file_hash.py` calcula SHA256 para cada `ruta_imagen` existente y actualiza `file_hash` en la tabla `pagos`.
