import os
import subprocess
import sys
import shutil

def run_command(args, description):
    """Ejecuta un comando y muestra el estado de la operación."""
    print(f"--- {description} ---")
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error en: {description}. Detalle: {e}")
        return False
    return True

def setup_and_build():
    """Configura un entorno virtual limpio e instala las dependencias necesarias."""
    if sys.version_info < (3, 10):
        print(f"Error: Se requiere Python 3.10 o superior. Detectado: {sys.version.split()[0]}")
        return

    project_dir = os.getcwd()
    build_venv_dir = os.environ.get('PROJECT_BUILD_VENV')
    if build_venv_dir:
        build_venv_dir = os.path.abspath(build_venv_dir)
    else:
        build_venv_dir = os.path.join(project_dir, ".venv_build")
    python_venv = os.path.join(build_venv_dir, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(build_venv_dir, "bin", "python")
    pyvenv_cfg = os.path.join(build_venv_dir, 'pyvenv.cfg')

    print("Limpiando instalaciones previas...")
    for folder in ['build', 'dist', build_venv_dir]:
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

    print("Creando entorno virtual de empaquetado...")
    if os.path.exists(build_venv_dir) and not os.path.exists(pyvenv_cfg):
        print("Entorno virtual anterior incompleto detectado; se recreará.")
        shutil.rmtree(build_venv_dir, ignore_errors=True)

    if not os.path.exists(python_venv):
        if not run_command([sys.executable, '-m', 'venv', build_venv_dir], "Creando entorno virtual"):
            return
    else:
        print("Entorno virtual de build ya existe.")

    print("Actualizando pip y herramientas base...")
    if not run_command([python_venv, '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'], "Instalando utilidades de Python"):
        return

    if os.path.exists("requirements.txt"):
        if not run_command([python_venv, '-m', 'pip', 'install', '-r', 'requirements.txt'], "Instalando dependencias de producción"):
            return
    else:
        print("No se encontró requirements.txt. Crea el archivo antes de continuar.")
        return

    if os.path.exists("requirements-dev.txt"):
        if not run_command([python_venv, '-m', 'pip', 'install', '-r', 'requirements-dev.txt'], "Instalando dependencias de desarrollo"):
            return

    print("Ejecutando PyInstaller...")
    if os.path.exists("OcrApp.spec"):
        if not run_command([python_venv, '-m', 'PyInstaller', '--clean', 'OcrApp.spec'], "Compilando desde OcrApp.spec"):
            return
    else:
        sep = ";" if os.name == 'nt' else ":"
        pyi_args = [
            python_venv,
            '-m',
            'PyInstaller',
            '--name',
            'OcrApp',
            '--onefile',
            '--clean',
            '--hidden-import',
            'rapidocr_onnxruntime',
            '--hidden-import',
            'PIL',
            '--hidden-import',
            'numpy',
            '--hidden-import',
            'openpyxl',
            '--hidden-import',
            'reportlab',
            '--add-data',
            f"static{sep}static",
            'run.py',
        ]
        if not run_command(pyi_args, "Compilando OcrApp.exe"):
            return

    exe_path = os.path.join(project_dir, "dist", "OcrApp.exe")
    if os.path.exists(exe_path):
        print(f"\nEjecutable creado: {exe_path}")
    else:
        print("\nEl ejecutable no se encontró. Revisa los logs para ver posibles errores.")

if __name__ == "__main__":
    setup_and_build()