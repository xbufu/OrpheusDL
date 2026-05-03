# -*- mode: python ; coding: utf-8 -*-
import os
import customtkinter

ROOT = os.path.abspath(os.path.dirname(SPEC))
CTK_PATH = os.path.dirname(customtkinter.__file__)

a = Analysis(
    [os.path.join(ROOT, 'gui.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # CustomTkinter themes and assets
        (CTK_PATH, 'customtkinter'),
        # Default config
        (os.path.join(ROOT, 'settings.json.example'), '.'),
        # OrpheusDL core (run as subprocess from GUI)
        (os.path.join(ROOT, 'orpheus.py'), '.'),
        (os.path.join(ROOT, 'orpheus'), 'orpheus'),
        (os.path.join(ROOT, 'utils'), 'utils'),
        # Modules (present at build time)
        (os.path.join(ROOT, 'modules'), 'modules'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._imagingtk',
        'PIL.Image',
        'PIL.ImageTk',
        'defusedxml',
        'mutagen',
        'requests',
        'tqdm',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OrpheusDL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(ROOT, 'icon.ico') if os.path.exists(os.path.join(ROOT, 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OrpheusDL',
)
