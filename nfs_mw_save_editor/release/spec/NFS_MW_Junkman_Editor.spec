# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

APP_ROOT = Path(SPECPATH).resolve().parents[1]


QT_MODULE_EXCLUDES = [
    'PySide6.QtNetwork',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuickControls2',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtVirtualKeyboard',
]


def _without_unused_qt_payload(entries):
    """Keep only the Qt plugins and libraries used by this raster Widgets app."""
    filtered = []
    for entry in entries:
        name = str(entry[0]).replace('\\', '/').lower()
        basename = name.rsplit('/', 1)[-1]

        if basename in {'libcrypto-3.dll', 'libssl-3.dll', 'opengl32sw.dll'}:
            continue
        if basename in {
            'qt6network.dll',
            'qt6opengl.dll',
            'qt6pdf.dll',
            'qt6quick.dll',
            'qt6qml.dll',
            'qt6qmlmeta.dll',
            'qt6qmlmodels.dll',
            'qt6qmlworkerscript.dll',
            'qt6svg.dll',
            'qt6virtualkeyboard.dll',
        }:
            continue
        if basename in {
            'qdirect2d.dll',
            'qminimal.dll',
            'qtuiotouchplugin.dll',
            'qtvirtualkeyboardplugin.dll',
        }:
            continue
        if '/plugins/iconengines/' in name:
            continue
        if '/plugins/networkinformation/' in name or '/plugins/tls/' in name:
            continue
        if '/plugins/imageformats/' in name and basename != 'qico.dll':
            continue
        if '/translations/' in name:
            continue
        if basename in {
            'qtnetwork.pyd',
            'qtopengl.pyd',
            'qtpdf.pyd',
            'qtqml.pyd',
            'qtquick.pyd',
            'qtsvg.pyd',
        }:
            continue

        filtered.append(entry)
    return filtered


def _runtime_icon_datas():
    """Bundle each current runtime icon, never a directory tree wholesale."""
    icon_root = APP_ROOT / 'assets' / 'icons'
    destination_root = Path('assets/icons')
    return [
        (
            str(path),
            (destination_root / path.relative_to(icon_root).parent).as_posix(),
        )
        for path in sorted(icon_root.rglob('*'))
        if path.is_file()
    ]


a = Analysis(
    [str(APP_ROOT / 'main.py')],
    pathex=[],
    binaries=[],
    datas=[
        (str(APP_ROOT / 'token_catalog.json'), '.'),
        (str(APP_ROOT / 'assets' / 'icon.ico'), 'assets'),
        (str(APP_ROOT / 'assets' / 'icon.png'), 'assets'),
        (str(APP_ROOT / 'assets' / 'visual_parts_catalog.json'), 'assets'),
        *_runtime_icon_datas(),
        (str(APP_ROOT / 'assets' / 'unique_cars'), 'assets/unique_cars'),
        (str(APP_ROOT / 'assets' / 'career_stages'), 'assets/career_stages'),
        (str(APP_ROOT / 'THIRD_PARTY_NOTICES.md'), '.'),
        (str(APP_ROOT / 'licenses'), 'licenses'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_MODULE_EXCLUDES,
    noarchive=False,
    optimize=0,
)
a.binaries = _without_unused_qt_payload(a.binaries)
a.datas = _without_unused_qt_payload(a.datas)
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
    version=str(APP_ROOT / 'release' / 'windows_version_info.txt'),
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
