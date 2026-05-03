# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import customtkinter

ROOT = os.path.abspath(os.path.dirname(SPEC))
CTK_PATH = os.path.dirname(customtkinter.__file__)

# Bundle ffmpeg/ffprobe binaries from bin/ if present
_bin_dir = os.path.join(ROOT, 'bin')
_ext = '.exe' if sys.platform == 'win32' else ''
_binaries = []
for _name in ('ffmpeg', 'ffprobe'):
    _path = os.path.join(_bin_dir, _name + _ext)
    if os.path.exists(_path):
        _binaries.append((_path, '.'))

a = Analysis(
    [os.path.join(ROOT, 'gui.py')],
    pathex=[ROOT],
    binaries=_binaries,
    datas=[
        (CTK_PATH, 'customtkinter'),
        (os.path.join(ROOT, 'settings.json.example'), '.'),
        (os.path.join(ROOT, 'orpheus.py'), '.'),
        (os.path.join(ROOT, 'orpheus'), 'orpheus'),
        (os.path.join(ROOT, 'utils'), 'utils'),
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
        'mutagen.flac',
        'mutagen.mp3',
        'mutagen.mp4',
        'mutagen.id3',
        'mutagen.oggvorbis',
        'mutagen.oggopus',
        'requests',
        'tqdm',
        'ffmpeg',
        'ffmpeg.nodes',
        'm3u8',
        'Cryptodome',
        'Cryptodome.Cipher',
        'Cryptodome.Cipher.AES',
        'google.protobuf',
    ],
    hookspath=[ROOT],
    runtime_hooks=[os.path.join(ROOT, 'hook-ffmpeg.py')],
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
