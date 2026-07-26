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
