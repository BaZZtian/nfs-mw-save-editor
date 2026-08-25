# Qt / PySide6 LGPL source and relinking information

This information applies to distributions of NFS MW Save Editor containing the
Qt, PySide6, and shiboken6 component versions listed below.

The application uses unmodified Qt 6.10.1 libraries dynamically through
unmodified PySide6 6.10.1 and shiboken6 6.10.1 wheels. They are distributed
under the GNU Lesser General Public License, version 3 (`LGPL-3.0.txt`, with
the incorporated GNU GPL version 3 text in `GPL-3.0.txt`). The application does
not contain Qt Virtual Keyboard.

## Direct network access to corresponding source

The exact source archives below are offered for direct download alongside the
application binaries under GNU GPL version 3, section 6(d), as incorporated by
the LGPL. They are hosted on the Qt Project's public download server, which
provides equivalent HTTP access at no charge. GNU GPL version 3 expressly
allows the corresponding source to be hosted on a different server operated by
a third party when clear directions are provided next to the object code.

The distributor remains responsible for keeping these directions and the exact
corresponding source available for as long as the application binaries are
offered. If an official URL becomes unavailable, the release directions must
be updated to another accessible copy of the same verified archive.

## Exact source archives

All hashes are SHA-256.

- Qt Base 6.10.1
  - https://download.qt.io/official_releases/qt/6.10/6.10.1/submodules/qtbase-everywhere-src-6.10.1.zip
  - `c43f471a808b07fc541528410e94ce89c6745bdc1d744492e19911d35fbf7d33`
- PySide6 and shiboken6 6.10.1
  - https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.1-src/pyside-setup-everywhere-src-6.10.1.zip
  - `835ef64b04f88ff04f0729d1ca730b700eb166578dba3740a0f1f21a64c957ed`

The Qt Base source archive contains the applicable third-party attribution
files and source for the components incorporated into the shipped Qt Core, GUI,
and Widgets libraries. The release package includes a consolidated copy at
`QT_THIRD_PARTY_LICENSES.txt`.

## Replacing or relinking the libraries

The `onedir` package keeps Qt and PySide6 libraries as separate files below
`_internal/PySide6`. A recipient may rebuild compatible versions from the
sources above and replace those files, preserving matching names and ABI.

The `onefile` package extracts the same separate libraries at run time. To use
replacement libraries there, rebuild the package with Python 3.13 and the
tracked PyInstaller specification at
`release/onefile/spec_onefile/NFS_MW_Junkman_Editor.spec`, substituting the
recipient-built PySide6/Qt installation. PyInstaller 6.18.0 was used for the
packaged application.

Permission is expressly granted to reverse engineer, unpack, repack, and modify
this application to the extent necessary to debug changes to, replace, or
relink the LGPL-covered Qt, PySide6, and shiboken6 components. The application
does not use code signing or an integrity check to prevent a modified build from
running.
