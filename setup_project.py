import os
import subprocess
import sys
import shutil

def run_command(command, description):
    """Ejecuta un comando de terminal y maneja errores."""
    print(f"--- {description} ---")
    try:
        # Usamos shell=True para compatibilidad con Windows
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error en: {description}. Detalle: {e}")
        # No salimos inmediatamente para intentar continuar con las otras librerías
        return False
    return True

def setup_and_build():
    """
    Configura el entorno y compila el proyecto.
    Optimizado para versiones experimentales de Python (3.14+).
    """
    # Verificación de versión mínima para asegurar compatibilidad
    if sys.version_info < (3, 9):
        print(f"❌ Error: Se requiere Python 3.9 o superior. Detectado: {sys.version.split()[0]}")
        print("Por favor, instala una versión más reciente de Python desde python.org")
        return

    project_dir = os.getcwd()
    venv_dir = os.path.join(project_dir, "venv_produccion")
    
    # Rutas de ejecutables
    python_venv = os.path.join(venv_dir, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(venv_dir, "bin", "python")
    pyinstaller_path = os.path.join(venv_dir, "Scripts", "pyinstaller.exe") if os.name == 'nt' else os.path.join(venv_dir, "bin", "pyinstaller")

    # 1. Limpieza profunda
    print("🧹 Limpiando rastros de instalaciones previas...")
    for folder in ['build', 'dist', venv_dir]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except Exception:
                pass

    # 2. Crear VENV con la versión de Python actual
    run_command(f'"{sys.executable}" -m venv venv_produccion', "Creando entorno virtual 3.14")

    # 3. Actualizar herramientas de empaquetado
    run_command(f'"{python_venv}" -m pip install --upgrade pip setuptools wheel', "Actualizando herramientas base")
    
    # 4. Instalación de dependencias
    # Nota: Eliminamos las versiones fijas para que PIP busque la mejor coincidencia para 3.14
    dependencies = [
        "fastapi", 
        "uvicorn[standard]", 
        "python-multipart",
        "rapidocr_onnxruntime", 
        "opencv-python-headless", 
        "Pillow", 
        "numpy", 
        "groq", 
        "python-dotenv",
        "openpyxl", 
        "reportlab",
        "pyinstaller",
        "sqlalchemy",
        "alembic",
        "httpx",
        "beautifulsoup4",
        "psycopg2-binary",
        "requests"
    ]
    
    print("📦 Instalando dependencias (Modo Inteligente para Python 3.14)...")
    # Intentamos instalar todo junto
    success = run_command(f'"{python_venv}" -m pip install {" ".join(dependencies)}', "Instalando paquete completo")

    if not success:
        print("⚠️ Algunos paquetes fallaron. Intentando instalación individual para omitir incompatibilidades...")
        for dep in dependencies:
            run_command(f'"{python_venv}" -m pip install {dep}', f"Instalando {dep}")

    # 5. Compilación del ejecutable
    print("🏗️ Iniciando empaquetado final...")
    if os.path.exists("OcrApp.spec"):
        run_command(f'"{pyinstaller_path}" --clean OcrApp.spec', "Compilando desde OcrApp.spec")
    else:
        # Comando basado en README.md si no existe el .spec
        sep = ";" if os.name == 'nt' else ":"
        pyi_cmd = (
            f'"{pyinstaller_path}" --name "OcrApp" --onefile --clean '
            f'--hidden-import rapidocr_onnxruntime --hidden-import pillow '
            f'--hidden-import numpy --hidden-import openpyxl --hidden-import reportlab '
            f'--add-data "static{sep}static" '
        )
        if os.path.exists("skills"):
            pyi_cmd += f'--add-data "skills{sep}skills" '
        
        pyi_cmd += "run.py"
        run_command(pyi_cmd, "Compilando OcrApp.exe (Generando nuevo ejecutable)")

    # 6. Resultado Final
    exe_path = os.path.join(project_dir, "dist", "OcrApp.exe")
    if os.path.exists(exe_path):
        print(f"\n✅ ¡MISIÓN CUMPLIDA!")
        print(f"🚀 Tu sistema de pagos móviles está listo para 2do grado.")
        print(f"📍 Ejecutable en: {exe_path}")
    else:
        print("\n⚠️ El proceso terminó, pero el .exe no está en /dist. Revisa los logs arriba.")

if __name__ == "__main__":
    setup_and_build()