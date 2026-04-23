import os
import subprocess
import sys
import shutil

def run_command(args, description, cwd=None):
    """Ejecuta un comando y muestra el estado de la operación."""
    print(f"--- {description} ---")
    try:
        subprocess.run(args, check=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"Error en: {description}. Detalle: {e}")
        return False
    return True

def setup_and_build():
    """Configura un entorno virtual limpio e instala las dependencias necesarias."""
    if sys.version_info < (3, 10):
        print(f"Error: Se requiere Python 3.10 o superior. Detectado: {sys.version.split()[0]}")
        return

    project_dir = os.path.abspath(os.path.dirname(__file__))
    build_venv_dir = os.environ.get('PROJECT_BUILD_VENV', os.path.join(project_dir, ".venv_build"))
    build_venv_dir = os.path.abspath(build_venv_dir)
    python_venv = os.path.join(build_venv_dir, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(build_venv_dir, "bin", "python")
    pyvenv_cfg = os.path.join(build_venv_dir, 'pyvenv.cfg')
    requirements_txt = os.path.join(project_dir, 'requirements.txt')
    requirements_dev_txt = os.path.join(project_dir, 'requirements-dev.txt')
    spec_path = os.path.join(project_dir, 'OcrApp.spec')

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
    if not run_command([python_venv, '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'], "Instalando utilidades de Python", cwd=project_dir):
        return

    if os.path.exists(requirements_txt):
        if not run_command([python_venv, '-m', 'pip', 'install', '-r', requirements_txt], "Instalando dependencias de producción", cwd=project_dir):
            return
    else:
        print("No se encontró requirements.txt. Crea el archivo antes de continuar.")
        return

    if os.path.exists(requirements_dev_txt):
        if not run_command([python_venv, '-m', 'pip', 'install', '-r', requirements_dev_txt], "Instalando dependencias de desarrollo", cwd=project_dir):
            return
    else:
        print("Archivo requirements-dev.txt no encontrado. Se omiten dependencias de desarrollo.")

    print("Ejecutando PyInstaller...")
    if os.path.exists(spec_path):
        print(f"Usando spec: {spec_path}")
        if not run_command([python_venv, '-m', 'PyInstaller', '--clean', spec_path], "Compilando desde OcrApp.spec", cwd=project_dir):
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
            'onnxruntime',
            '--hidden-import',
            'PIL',
            '--hidden-import',
            'numpy',
            '--hidden-import',
            'openpyxl',
            '--hidden-import',
            'reportlab',
            '--hidden-import',
            'httpx',
            '--hidden-import',
            'dotenv',
            '--hidden-import',
            'groq',
            '--hidden-import',
            'fastapi',
            '--hidden-import',
            'sqlalchemy',
            '--hidden-import',
            'psycopg2',
            '--add-data',
            f"static{sep}static",
            'run.py',
        ]
        if not run_command(pyi_args, "Compilando OcrApp.exe", cwd=project_dir):
            return

    exe_path = os.path.join(project_dir, "dist", "OcrApp.exe")
    if os.path.exists(exe_path):
        print(f"\nEjecutable creado: {exe_path}")
    else:
        print("\nEl ejecutable no se encontró. Revisa los logs para ver posibles errores.")

if __name__ == "__main__":
    setup_and_build()