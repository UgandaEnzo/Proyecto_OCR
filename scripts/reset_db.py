import sys
import os
from sqlalchemy import text

# Agregar el directorio raíz al path para poder importar database y models
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import SessionLocal
import models

def limpiar_uploads():
    """Elimina todos los archivos de la carpeta uploads/ en la raíz del proyecto."""
    uploads_path = os.path.join(parent_dir, "uploads")
    
    if not os.path.exists(uploads_path):
        print("Carpeta 'uploads' no encontrada. No se eliminaron archivos.")
        return

    print(f"Limpiando carpeta de imágenes: {uploads_path}")
    deleted = 0
    try:
        for filename in os.listdir(uploads_path):
            file_path = os.path.join(uploads_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    deleted += 1
            except Exception as e:
                print(f"Error al eliminar {filename}: {e}")
        print(f"- Eliminados {deleted} archivos de imagen.")
    except Exception as e:
        print(f"Error al leer carpeta uploads: {e}")

def vaciar_base_datos():
    db = SessionLocal()
    try:
        print("Iniciando limpieza de base de datos...")
        
        # 1. Eliminar historial primero (porque depende de pagos)
        num_hist = db.query(models.PagoHistory).delete()
        print(f"- Eliminados {num_hist} registros de historial.")

        # 2. Eliminar pagos
        num_pagos = db.query(models.Pago).delete()
        print(f"- Eliminados {num_pagos} registros de pagos.")

        # 3. Confirmar cambios
        db.commit()
        
        # Opcional: Intentar reiniciar los contadores de ID (Secuencias en PostgreSQL)
        try:
            db.execute(text("ALTER SEQUENCE pagos_id_seq RESTART WITH 1"))
            db.execute(text("ALTER SEQUENCE pago_history_id_seq RESTART WITH 1"))
            db.commit()
            print("- Secuencias de ID reiniciadas a 1.")
        except Exception:
            print("- Nota: No se reiniciaron las secuencias (puede que los nombres difieran o no sea PostgreSQL).")

        print("Base de datos vaciada exitosamente.")
        
        # 4. Limpiar archivos físicos
        limpiar_uploads()

    except Exception as e:
        print(f"Error al vaciar la base de datos: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    confirm = input("ADVERTENCIA: Esto borrará TODOS los datos y las IMÁGENES asociadas. ¿Estás seguro? (escribe 'si'): ")
    if confirm.lower() == 'si':
        vaciar_base_datos()
    else:
        print("Operación cancelada.")