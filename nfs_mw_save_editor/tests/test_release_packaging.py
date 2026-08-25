from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent


def _spec_text(relative_path: str) -> str:
    return (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")


def test_both_specs_prune_unused_qt_payload_and_bundle_notices() -> None:
    spec_paths = (
        "release/spec/NFS_MW_Junkman_Editor.spec",
        "release/onefile/spec_onefile/NFS_MW_Junkman_Editor.spec",
    )
    for spec_path in spec_paths:
        text = _spec_text(spec_path)
        assert "'PySide6.QtVirtualKeyboard'" in text
        assert "'PySide6.QtPdf'" in text
        assert "'PySide6.QtQml'" in text
        assert "'PySide6.QtQuick'" in text
        assert "'PySide6.QtNetwork'" in text
        assert "'libcrypto-3.dll', 'libssl-3.dll'" in text
        assert "basename != 'qico.dll'" in text
        assert "'/translations/' in name" in text
        assert "a.binaries = _without_unused_qt_payload(a.binaries)" in text
        assert "a.datas = _without_unused_qt_payload(a.datas)" in text
        assert "'THIRD_PARTY_NOTICES.md'" in text
        assert "(str(APP_ROOT / 'licenses'), 'licenses')" in text
        assert "assets' / 'visual_parts_catalog.json" in text
        assert "release' / 'windows_version_info.txt" in text


def test_both_specs_enumerate_runtime_icons_instead_of_bundling_a_tree() -> None:
    spec_paths = (
        "release/spec/NFS_MW_Junkman_Editor.spec",
        "release/onefile/spec_onefile/NFS_MW_Junkman_Editor.spec",
    )
    for spec_path in spec_paths:
        text = _spec_text(spec_path)
        assert "def _runtime_icon_datas()" in text
        assert "*_runtime_icon_datas()," in text
        assert "(str(APP_ROOT / 'assets' / 'icons'), 'assets/icons')" not in text


def test_release_notice_and_required_license_files_are_present() -> None:
    required_files = (
        "THIRD_PARTY_NOTICES.md",
        "licenses/GPL-3.0.txt",
        "licenses/LGPL-3.0.txt",
        "licenses/PYTHON-3.13.txt",
        "licenses/NUMPY-2.5.1.txt",
        "licenses/PYINSTALLER-6.18.0.txt",
        "licenses/QT_LGPL_COMPLIANCE.md",
        "licenses/QT_THIRD_PARTY_LICENSES.txt",
        "release/windows_version_info.txt",
    )
    for relative_path in required_files:
        path = PACKAGE_ROOT / relative_path
        assert path.is_file(), relative_path
        assert path.stat().st_size > 0, relative_path

    notice = (PACKAGE_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Qt 6.10.1" in notice
    assert "PySide6 6.10.1" in notice
    assert "Python 3.13.14" in notice
    assert "NumPy 2.5.1" in notice
    assert "PyInstaller 6.18.0" in notice
    assert "Virtual Keyboard" in notice
    assert "QT_THIRD_PARTY_LICENSES.txt" in notice
    assert "v1.5.0" not in notice


def test_qt_compliance_notice_is_evergreen_and_actionable() -> None:
    notice = (PACKAGE_ROOT / "licenses/QT_LGPL_COMPLIANCE.md").read_text(encoding="utf-8")
    normalized_notice = " ".join(notice.split())
    assert "section 6(d)" in notice
    assert "different server operated by a third party" in normalized_notice
    assert "at least three years" not in notice
    assert "LGPL source request" not in notice
    assert "v1.5.0" not in notice
    assert "qtbase-everywhere-src-6.10.1.zip" in notice
    assert "qtdeclarative-everywhere-src-6.10.1.zip" not in notice
    assert "qtwebengine-everywhere-src-6.10.1.zip" not in notice
    assert "pyside-setup-everywhere-src-6.10.1.zip" in notice
    assert "c43f471a808b07fc541528410e94ce89c6745bdc1d744492e19911d35fbf7d33" in notice
    assert "835ef64b04f88ff04f0729d1ca730b700eb166578dba3740a0f1f21a64c957ed" in notice
    assert "release/onefile/spec_onefile/NFS_MW_Junkman_Editor.spec" in notice


def test_qt_third_party_notice_is_complete_and_regeneratable() -> None:
    notice = (PACKAGE_ROOT / "licenses/QT_THIRD_PARTY_LICENSES.txt").read_text(
        encoding="utf-8"
    )
    assert "Qt 6.10.1 third-party notices and license texts" in notice
    assert "COMPONENT ATTRIBUTIONS" in notice
    assert "FULL LICENSE TEXTS" in notice
    assert "D3D12 Memory Allocator" in notice
    assert "LibPNG" in notice
    assert "HarfBuzz-NG" in notice
    assert "PCRE2" in notice
    assert "X Server helper" in notice
    assert "X Consortium" in notice
    assert "Digital Equipment Corporation" in notice
    assert "OpenSSL" not in notice
    assert (PACKAGE_ROOT / "tools/build_qt_third_party_notices.py").is_file()


def test_windows_version_resource_identifies_v150() -> None:
    version_info = (PACKAGE_ROOT / "release/windows_version_info.txt").read_text(encoding="utf-8")
    assert "filevers=(1, 5, 0, 0)" in version_info
    assert "prodvers=(1, 5, 0, 0)" in version_info
    assert 'StringStruct("ProductName", "NFS MW Save Editor")' in version_info
    assert 'StringStruct("ProductVersion", "1.5.0")' in version_info
    assert 'StringStruct("OriginalFilename", "NFS_MW_Junkman_Editor.exe")' in version_info


def test_readme_links_the_release_notices() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    assert "nfs_mw_save_editor/THIRD_PARTY_NOTICES.md" in readme
