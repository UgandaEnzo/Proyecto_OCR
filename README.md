Proyecto Sistema OCR Pagos Móviles
=================================

Instrucciones rápidas

1. Crear entorno y activar:

```powershell
& .\.venv\Scripts\Activate.ps1
```

2. Ejecutar servidor en desarrollo:

```powershell
uvicorn main:app --reload
```

Migraciones y `file_hash`:

- Para producción se recomienda usar Alembic. Pasos rápidos:
  1. Inicializa Alembic en el proyecto: `alembic init alembic`.
  2. Configura `alembic.ini` y `env.py` para usar la URL de `database.SQLALCHEMY_DATABASE_URL`.
  3. Crea una migración para añadir la columna `file_hash`:
     - `alembic revision -m "add file_hash to pagos" --autogenerate`
  4. Aplica la migración: `alembic upgrade head`.
  5. Rellena los hashes para registros existentes: `python scripts/fill_file_hash.py`.

El script `scripts/fill_file_hash.py` calcula SHA256 para cada `ruta_imagen` existente y actualiza `file_hash` en la tabla `pagos`.
