import sys
import os
import traceback

# Añadir la raíz del proyecto al path para permitir imports relativos cuando el script
# se ejecuta desde su propio directorio.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import engine

try:
    conn = engine.connect()
    print('CONEXION_OK')
    conn.close()
except Exception:
    traceback.print_exc()
