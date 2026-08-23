# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

APP_ROOT = Path(SPECPATH).resolve().parents[1]


a = Analysis(
    [str(APP_ROOT / 'main.py')],
    pathex=[],
    binaries=[],
    datas=[
        (str(APP_ROOT / 'token_catalog.json'), '.'),
        (str(APP_ROOT / 'assets' / 'icon.ico'), 'assets'),
        (str(APP_ROOT / 'assets' / 'icon.png'), 'assets'),
        (str(APP_ROOT / 'assets' / 'icons'), 'assets/icons'),
        (str(APP_ROOT / 'assets' / 'unique_cars'), 'assets/unique_cars'),
        (str(APP_ROOT / 'assets' / 'career_stages'), 'assets/career_stages'),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='NFS_MW_Junkman_Editor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(APP_ROOT / 'assets' / 'icon.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NFS_MW_Junkman_Editor',
)
