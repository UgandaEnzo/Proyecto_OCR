# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all('rapidocr_onnxruntime')

pathex = [os.path.abspath('.')]

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
] + rapidocr_hiddenimports

a = Analysis(
    ['run.py'],
    pathex=pathex,
    binaries=rapidocr_binaries,
    datas=[('static', 'static')] + rapidocr_datas,
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
