import sys
import os
from sqlalchemy import text

# Agregar el directorio raíz al path para poder importar database
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from database import engine

def aplicar_solucion_2():
    print("🔧 Iniciando actualización de esquema de Base de Datos (Solución 2)...")
    
    with engine.connect() as conn:
        # Iniciar transacción
        trans = conn.begin()
        try:
            # 1. Agregar columnas nuevas (si no existen)
            print("- Agregando columnas 'cedula' y 'telefono'...")
            conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cedula VARCHAR;"))
            conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefono VARCHAR;"))
            
            # 2. Eliminar columna vieja (si existe)
            print("- Eliminando columna obsoleta 'cedula_telefono'...")
            conn.execute(text("ALTER TABLE clientes DROP COLUMN IF EXISTS cedula_telefono;"))
            
            # 3. Agregar constraint unique
            print("- Aplicando restricción UNIQUE a 'cedula'...")
            try:
                conn.execute(text("ALTER TABLE clientes ADD CONSTRAINT uq_clientes_cedula UNIQUE (cedula);"))
            except Exception as e:
                print(f"  (Info: El constraint probablemente ya existe o hubo conflicto: {e})")
            
            trans.commit()
            print("✅ Base de datos actualizada exitosamente.")
            
        except Exception as e:
            trans.rollback()
            print(f"❌ Error crítico durante la migración: {e}")

if __name__ == "__main__":
    aplicar_solucion_2()