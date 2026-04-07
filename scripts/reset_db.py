import sys
import os
import argparse
from sqlalchemy import text

# Agregar el directorio raíz al path para poder importar database y models
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import engine
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
    try:
        print("Iniciando REINICIO TOTAL de base de datos (DROP TABLES)...")
        
        # 1. Eliminar tablas completas para actualizar esquema (columnas nuevas)
        models.Base.metadata.drop_all(bind=engine)
        print("- Tablas eliminadas.")
        
        # 2. Crear tablas de nuevo con la estructura nueva de models.py
        models.Base.metadata.create_all(bind=engine)
        print("- Tablas creadas nuevamente con estructura actualizada.")
        
        # 3. Limpiar archivos físicos
        limpiar_uploads()
        
        print("Base de datos reiniciada exitosamente.")

    except Exception as e:
        print(f"Error al reiniciar la base de datos: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reinicia la base de datos y limpia archivos subidos.")
    parser.add_argument("--force", action="store_true", help="Omitir la confirmación interactiva.")
    args = parser.parse_args()

    if args.force:
        vaciar_base_datos()
    else:
        confirm = input("ADVERTENCIA: Esto borrará TODOS los datos y las IMÁGENES asociadas. ¿Estás seguro? (escribe 'si'): ")
        if confirm.lower() == 'si':
            vaciar_base_datos()
        else:
            print("Operación cancelada.")