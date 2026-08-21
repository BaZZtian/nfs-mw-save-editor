"""Reload-from-disk affordance + the applied-but-unsaved badge.

Reset Want=Have stays staged-only by design; the Career footer slot turns
into "Reload from disk" because transplants apply immediately and staged
wants never exist there. The "Applied, not saved" badge closes the gap
where an applied buffer differed from disk with no indication at all.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox

import ui.main_window as main_window_module
from core.savefile import SaveFile
from ui.main_window import MainWindow


APP = QApplication.instance() or QApplication([])


def _close_window(window: MainWindow) -> None:
    window.close()


def _window_with_save(tmp_path: Path) -> tuple[MainWindow, Path]:
    save_path = tmp_path / "TESTSAVE"
    save_path.write_bytes(bytes(0xF86C))
    window = MainWindow()
    window.savefile = SaveFile.load(save_path)
    return window, save_path


def test_footer_reset_slot_switches_label_on_career() -> None:
    window = MainWindow()
    try:
        assert window.btn_reset_want.text() == "Reset Want=Have"
        window._set_footer_page("Career")
        assert window.btn_reset_want.text() == "Reload from disk"
        window._set_footer_page("Garage")
        assert window.btn_reset_want.text() == "Reset Want=Have"
    finally:
        _close_window(window)


def test_career_page_is_resolvable_for_the_footer_dispatcher() -> None:
    """Regression: the page-name resolver had no Career branch, so the
    footer dispatcher silently fell through to Reset Want=Have there."""

    window = MainWindow()
    try:
        window._select_page("Career")
        assert window._current_stack_page_name() == "Career"
    finally:
        _close_window(window)


def test_applied_dirty_badge_tracks_buffer_vs_disk(tmp_path) -> None:
    window, _save_path = _window_with_save(tmp_path)
    try:
        window._update_action_states()
        assert window.lbl_unsaved.text() == "Saved"

        window.savefile.data[0x4038] ^= 0xFF  # any applied edit
        window._update_action_states()
        assert window.lbl_unsaved.text() == "Applied, not saved"

        window.savefile.save(make_backup=False)
        window._update_action_states()
        assert window.lbl_unsaved.text() == "Saved"
    finally:
        _close_window(window)


def test_reload_from_disk_restores_disk_bytes(tmp_path) -> None:
    window, save_path = _window_with_save(tmp_path)
    try:
        disk_before = save_path.read_bytes()
        window.savefile.data[0x4038] ^= 0xFF
        assert bytes(window.savefile.data) != disk_before

        with mock.patch.object(
            main_window_module.QMessageBox, "question",
            return_value=QMessageBox.Yes,
        ), mock.patch.object(
            main_window_module.ToastNotification, "show_toast",
        ):
            window.on_reload_from_disk()

        assert bytes(window.savefile.data) == disk_before
        assert save_path.read_bytes() == disk_before
    finally:
        _close_window(window)


def test_reload_dialog_names_staged_edits_when_pending(tmp_path) -> None:
    """Regression (review 2026-08-14): on_open() after Reload resets staged
    wants from other pages too, but the dialog only admitted to
    applied-but-unsaved changes, causing silent data loss for staged edits."""

    window, _save_path = _window_with_save(tmp_path)
    try:
        window.savefile.data[0x4038] ^= 0xFF
        captured = {}

        def fake_question(parent, title, text, *args, **kwargs):
            captured["text"] = text
            return QMessageBox.No

        with mock.patch.object(
            main_window_module.QMessageBox, "question", side_effect=fake_question
        ):
            with mock.patch.object(window, "_has_pending_changes", return_value=True):
                window.on_reload_from_disk()
            assert "staged" in captured["text"]

            with mock.patch.object(window, "_has_pending_changes", return_value=False):
                window.on_reload_from_disk()
            assert "staged" not in captured["text"]
    finally:
        _close_window(window)


def test_reload_from_disk_declined_keeps_memory(tmp_path) -> None:
    window, save_path = _window_with_save(tmp_path)
    try:
        window.savefile.data[0x4038] ^= 0xFF
        changed = bytes(window.savefile.data)
        with mock.patch.object(
            main_window_module.QMessageBox, "question",
            return_value=QMessageBox.No,
        ):
            window.on_reload_from_disk()
        assert bytes(window.savefile.data) == changed
    finally:
        _close_window(window)
