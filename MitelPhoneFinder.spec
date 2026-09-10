# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe: one windowed .exe, no Python needed on the target PC.

    python -m PyInstaller --noconfirm MitelPhoneFinder.spec
"""

block_cipher = None

analysis = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/appicon.ico', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtCharts',
        'PySide6.QtDataVisualization', 'PySide6.QtPdf', 'PySide6.QtSql',
        'PySide6.QtDesigner', 'PySide6.QtOpenGL', 'PySide6.QtTest',
        'tkinter', 'unittest', 'pydoc_data',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name='MitelPhoneFinder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon='assets/appicon.ico',
)
