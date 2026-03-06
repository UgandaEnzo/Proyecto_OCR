"""
Script para poblar `file_hash` en registros existentes de la tabla `pagos`.
Usar desde el entorno virtual del proyecto:

    python scripts/fill_file_hash.py

Este script iterará los registros en la BD, calculará SHA256 de `ruta_imagen` si existe
y actualizará `file_hash` en la tabla. Requiere que `database.py` y `models.py` estén configurados.

Nota: en producción recomendamos hacer una migración con Alembic para añadir la columna y luego ejecutar este script.
"""

import hashlib
import os
import sys

# Añadir el directorio raíz del proyecto al path para poder importar 'database' y 'models'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

BATCH_SIZE = 100

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*64), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    db = SessionLocal()
    try:
        # Usamos un query que no carga todo en memoria de una vez
        query = db.query(models.Pago).filter(models.Pago.file_hash == None)
        total_to_process = query.count()
        print(f"Registros sin file_hash encontrados: {total_to_process}")

        if total_to_process == 0:
            print("No hay registros que necesiten actualización.")
            return

        processed_count = 0
        # Procesamos en lotes para ser eficientes con la memoria
        for pago in query.yield_per(BATCH_SIZE):
            if pago.ruta_imagen and os.path.exists(pago.ruta_imagen):
                try:
                    pago.file_hash = sha256(pago.ruta_imagen)
                    processed_count += 1
                    if processed_count % BATCH_SIZE == 0:
                        db.commit()
                        print(f"  ... {processed_count}/{total_to_process} registros procesados.")
                except Exception as e:
                    print(f"  [ERROR] No se pudo procesar el pago ID {pago.id} (imagen: {pago.ruta_imagen}): {e}")
        
        db.commit() # Guardar los registros restantes del último lote
        print(f"Completado. Se actualizaron {processed_count} de {total_to_process} registros.")
    finally:
        db.close()

if __name__ == '__main__':
    main()