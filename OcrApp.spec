# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

rapidocr_datas, rapidocr_binaries, rapidocr_hiddenimports = collect_all('rapidocr_onnxruntime')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=rapidocr_binaries,
    datas=[('static', 'static')] + rapidocr_datas,
    hiddenimports=[
        'rapidocr_onnxruntime',
        'onnxruntime',
        'cv2',
        'PIL',
        'numpy',
        'openpyxl',
        'reportlab',
        'httpx',
        'bs4',
        'psycopg2',
        'sqlalchemy',
    ] + rapidocr_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
