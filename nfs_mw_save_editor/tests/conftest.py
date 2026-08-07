"""Shared fixtures for the test suite.

UI tests build the real MainWindow, which reads AND persists per-user state
under %APPDATA%/NFS_MW_Junkman_Editor: the token catalog (rewritten by
catalog normalization on every launch), the My Builds snapshot library, and
the ui-settings file (theme/unlock toggles). A 2026-07-12 suite run silently
migrated the user's live token catalog that way.

Redirecting APPDATA per test keeps everything hermetic: every path helper
that resolves per-user state (ui.main_window._appdata_dir,
ui.theme._appdata_dir, core.snapshot_library.default_user_snapshot_library_root)
reads the environment at call time, so no test can touch real user data.
"""
import os
from pathlib import Path

import pytest

# Test modules that need a Qt environment: they import PySide6 (directly or
# through ui.*), and several build a QApplication at import time — so a
# marker filter alone cannot exclude them; they must be skipped at
# collection. Keep this list current when adding Qt-dependent test modules;
# `pytest -m "not qt"` runs the core + api contract suite without importing
# Qt at all.
QT_TEST_FILES = {
    "test_apply_belt_sentinel.py",
    "test_builds_reset_refresh.py",
    "test_card_grid_fit.py",
    "test_career_ui.py",
    "test_footer_layout.py",
    "test_garage_heat_ui.py",
    "test_garage_registry_presentation.py",
    "test_garage_staged_transfer_visibility.py",
    "test_popup_theme_reentrancy.py",
    "test_reload_from_disk.py",
    "test_rendering.py",
    "test_snapshot_provenance_display.py",
    "test_token_card_flip.py",
    "test_token_catalog.py",
    "test_ui_smoke.py",
}


def pytest_ignore_collect(collection_path, config):
    markexpr = getattr(config.option, "markexpr", "") or ""
    if "not qt" in markexpr and collection_path.name in QT_TEST_FILES:
        return True
    return None


def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(str(item.fspath)).name in QT_TEST_FILES:
            item.add_marker(pytest.mark.qt)


# The offscreen platform brings no fonts of its own. With no font directory
# QFontDatabase comes up empty and every text metric collapses, so any test
# that compares laid-out widths measures a layout that cannot happen in the
# app - the footer fit/hysteresis tests failed exactly that way. This has to
# run before the first QApplication, which test modules build at import time,
# so it lives at module scope rather than in a fixture.
if not os.environ.get("QT_QPA_FONTDIR"):
    _system_fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if _system_fonts.is_dir():
        os.environ["QT_QPA_FONTDIR"] = str(_system_fonts)


@pytest.fixture(autouse=True)
def hermetic_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    return appdata
