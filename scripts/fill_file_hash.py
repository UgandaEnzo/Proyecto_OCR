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
from database import SessionLocal
import models

BATCH = 100

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*64), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    db = SessionLocal()
    try:
        q = db.query(models.Pago).filter(models.Pago.file_hash == None).all()
        total = len(q)
        print(f"Registros sin file_hash: {total}")
        i = 0
        for p in q:
            i += 1
            if not p.ruta_imagen:
                continue
            if not os.path.exists(p.ruta_imagen):
                print(f"[{i}/{total}] Archivo no existe: {p.ruta_imagen}")
                continue
            try:
                h = sha256(p.ruta_imagen)
                p.file_hash = h
                db.add(p)
                if i % BATCH == 0:
                    db.commit()
                    print(f"Guardados {i}/{total}")
            except Exception as e:
                print(f"[{i}/{total}] Error hashing {p.ruta_imagen}: {e}")
                continue
        db.commit()
        print("Completado")
    finally:
        db.close()

if __name__ == '__main__':
    main()
