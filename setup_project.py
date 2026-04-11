import os
import subprocess
import sys
import shutil

def run_command(command, description):
    """Ejecuta un comando de terminal y maneja errores."""
    print(f"--- {description} ---")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error en: {description}. Detalle: {e}")
        return False
    return True

def setup_and_build():
    """Configura un entorno virtual limpio e instala las dependencias necesarias."""
    if sys.version_info < (3, 10):
        print(f"❌ Error: Se requiere Python 3.10 o superior. Detectado: {sys.version.split()[0]}")
        return

    project_dir = os.getcwd()
    build_venv_dir = os.path.join(project_dir, ".venv_build")
    python_venv = os.path.join(build_venv_dir, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(build_venv_dir, "bin", "python")
    pyinstaller_path = os.path.join(build_venv_dir, "Scripts", "pyinstaller.exe") if os.name == 'nt' else os.path.join(build_venv_dir, "bin", "pyinstaller")

    print("🧹 Limpiando instalaciones previas...")
    for folder in ['build', 'dist', build_venv_dir]:
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

    print("⚙️ Creando entorno virtual de empaquetado...")
    if os.path.abspath(sys.prefix) == os.path.abspath(build_venv_dir):
        print("⚠️ Ya estás usando el entorno de build. No es necesario crear uno nuevo.")
    else:
        if not run_command(f'"{sys.executable}" -m venv "{build_venv_dir}"', "Creando entorno virtual"):
            return

    print("📦 Actualizando pip y herramientas base...")
    if not run_command(f'"{python_venv}" -m pip install --upgrade pip setuptools wheel', "Instalando utilidades de Python"):
        return

    if os.path.exists("requirements.txt"):
        if not run_command(f'"{python_venv}" -m pip install -r requirements.txt', "Instalando dependencias de producción"):
            return
    else:
        print("⚠️ No se encontró requirements.txt. Crea el archivo antes de continuar.")
        return

    if os.path.exists("requirements-dev.txt"):
        run_command(f'"{python_venv}" -m pip install -r requirements-dev.txt', "Instalando dependencias de desarrollo")

    print("🏗️ Ejecutando PyInstaller...")
    if os.path.exists("OcrApp.spec"):
        run_command(f'"{pyinstaller_path}" --clean OcrApp.spec', "Compilando desde OcrApp.spec")
    else:
        sep = ";" if os.name == 'nt' else ":"
        pyi_cmd = (
            f'"{pyinstaller_path}" --name "OcrApp" --onefile --clean '
            f'--hidden-import rapidocr_onnxruntime --hidden-import pillow '
            f'--hidden-import numpy --hidden-import openpyxl --hidden-import reportlab '
            f'--add-data "static{sep}static" run.py'
        )
        # scripts/ permanece en el repositorio para desarrollo; no se añade al .exe.
        run_command(pyi_cmd, "Compilando OcrApp.exe")

    exe_path = os.path.join(project_dir, "dist", "OcrApp.exe")
    if os.path.exists(exe_path):
        print(f"\n✅ Ejecutable creado: {exe_path}")
    else:
        print("\n⚠️ El ejecutable no se encontró. Revisa los logs para ver posibles errores.")

if __name__ == "__main__":
    setup_and_build()