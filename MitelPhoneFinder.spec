# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe: one self-contained app per platform.

    python -m PyInstaller --noconfirm MitelPhoneFinder.spec

Windows produces dist/MitelPhoneFinder.exe with an embedded version resource.
macOS produces dist/MitelPhoneFinder (a command line binary) and
dist/Mitel Phone Finder.app. Neither needs Python on the target machine.
"""
import sys

IS_MAC = sys.platform == 'darwin'
VERSION = '1.1.0'

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
    version=None if IS_MAC else 'version_info.txt',
    icon='assets/appicon.icns' if IS_MAC else 'assets/appicon.ico',
)

if IS_MAC:
    app = BUNDLE(
        exe,
        name='Mitel Phone Finder.app',
        icon='assets/appicon.icns',
        bundle_identifier='io.github.dirazi83.mitelphonefinder',
        version=VERSION,
        info_plist={
            'CFBundleName': 'Mitel Phone Finder',
            'CFBundleDisplayName': 'Mitel 6900 IP Phone Finder',
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            'LSMinimumSystemVersion': '11.0',
            'LSApplicationCategoryType': 'public.app-category.utilities',
            'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'Copyright (c) 2026 dirazi83. MIT License.',
            # macOS 15 and later gate LAN access behind an explicit prompt.
            'NSLocalNetworkUsageDescription':
                'Mitel Phone Finder scans the local network to list Mitel IP phones.',
        },
    )
