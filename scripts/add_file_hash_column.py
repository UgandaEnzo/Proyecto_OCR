from database import engine
from sqlalchemy import text
import traceback

sql = "ALTER TABLE pagos ADD COLUMN file_hash VARCHAR;"
try:
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print('Columna file_hash añadida (si no existía).')
except Exception:
    traceback.print_exc()
    print('No se pudo añadir la columna automáticamente; revisa manualmente.')
