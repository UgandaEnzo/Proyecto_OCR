# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_all

rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all('rapidocr_onnxruntime')

# Cuando PyInstaller ejecuta este spec desde un ejecutable, `sys.argv[0]` es la ruta del spec.
# Esto evita errores de cálculo del directorio raíz al empaquetar en Windows.
spec_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else os.path.abspath(os.getcwd())
root_dir = os.path.abspath(os.path.dirname(spec_path))
pathex = [root_dir]
distpath = os.path.join(root_dir, 'dist')
workpath = os.path.join(root_dir, 'build')

hidden_imports = [
    'rapidocr_onnxruntime',
    'onnxruntime',
    'cv2',
    'PIL',
    'numpy',
    'openpyxl',
    'reportlab',
    'httpx',
    'bs4',
    'groq',
    'fastapi',
    'starlette',
    'pydantic',
    'uvicorn',
    'jinja2',
    'psycopg2',
    'sqlalchemy',
    'dotenv',
    'multipart',
] + rapidocr_hiddenimports

a = Analysis(
    [os.path.join(root_dir, 'run.py')],
    pathex=pathex,
    binaries=rapidocr_binaries,
    datas=[(os.path.join(root_dir, 'static'), 'static')] + rapidocr_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['requests'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OcrApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
