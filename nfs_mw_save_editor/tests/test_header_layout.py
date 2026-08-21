from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import available_theme_names, build_shell_stylesheet, resolve_theme_tokens
from ui.widgets import HeaderStateChip, ToastNotification


APP = QApplication.instance() or QApplication([])


def _close(widget) -> None:
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    APP.processEvents()


def _window() -> MainWindow:
    window = MainWindow()
    window.resize(1400, 780)
    window.show()
    QTest.qWait(20)
    APP.processEvents()
    return window


def _header_geometry(window: MainWindow) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(
        widget.geometry().getRect()
        for widget in (
            window.header_file_plate,
            window.lbl_unsaved,
            window.header_integrity_plate,
        )
    )


def _contrast_ratio(color_a: str, color_b: str) -> float:
    def relative_luminance(color: str) -> float:
        channels = []
        value = color.lstrip("#")
        for index in (0, 2, 4):
            channel = int(value[index:index + 2], 16) / 255.0
            channels.append(
                channel / 12.92
                if channel <= 0.03928
                else ((channel + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    luminance_a = relative_luminance(color_a)
    luminance_b = relative_luminance(color_b)
    return (max(luminance_a, luminance_b) + 0.05) / (
        min(luminance_a, luminance_b) + 0.05
    )


def test_header_info_slots_do_not_move_when_change_state_changes() -> None:
    window = _window()
    try:
        clean_geometry = _header_geometry(window)

        with mock.patch.object(window, "_has_pending_changes", return_value=True):
            window._update_action_states()
        APP.processEvents()
        assert window.lbl_unsaved.text() == "Unsaved changes"
        assert window.lbl_unsaved.stateKey() == "pending"
        assert _header_geometry(window) == clean_geometry

        window.savefile = SimpleNamespace(path=Path("C:/TESTSAVE"))
        with mock.patch.object(window, "_has_pending_changes", return_value=False), mock.patch.object(
            window, "_buffer_matches_disk", return_value=False
        ):
            window._update_action_states()
        APP.processEvents()
        assert window.lbl_unsaved.text() == "Applied, not saved"
        assert window.lbl_unsaved.stateKey() == "applied"
        assert _header_geometry(window) == clean_geometry

        with mock.patch.object(window, "_has_pending_changes", return_value=False), mock.patch.object(
            window, "_buffer_matches_disk", return_value=True
        ):
            window._update_action_states()
        APP.processEvents()
        assert window.lbl_unsaved.text() == "Saved"
        assert window.lbl_unsaved.stateKey() == "saved"
        assert _header_geometry(window) == clean_geometry
    finally:
        _close(window)


def test_header_uses_fixed_left_center_right_anchors_at_every_width() -> None:
    window = _window()
    try:
        positions = []
        for width in (1400, 1920, 1400):
            window.resize(width, 780)
            APP.processEvents()
            header = window.header_chrome
            path = window.header_file_plate
            actions = window.header_actions
            status = window.header_status_area

            assert path.geometry().center().x() == header.rect().center().x()
            assert actions.geometry().left() == header.rect().left()
            assert status.geometry().right() == header.rect().right()
            assert window.header_file_plate.isAncestorOf(window.lbl_unsaved)
            assert window.header_integrity_plate.geometry().right() == status.rect().right()
            positions.append(
                (
                    actions.width(),
                    path.width(),
                    status.width(),
                    status.geometry().right() - header.rect().right(),
                )
            )

        assert len(set(positions)) == 1
    finally:
        _close(window)


def test_saved_chip_survives_window_resize_without_a_state_refresh() -> None:
    window = _window()
    try:
        window.savefile = SimpleNamespace(path=Path("C:/TESTSAVE"))
        with mock.patch.object(window, "_has_pending_changes", return_value=False), mock.patch.object(
            window, "_buffer_matches_disk", return_value=True
        ):
            window._update_action_states()
        transition = window.lbl_unsaved._transition_group
        if transition is not None:
            transition.setCurrentTime(transition.duration())
        APP.processEvents()

        for width in (1920, 1400):
            window.resize(width, 780)
            APP.processEvents()
            visible = [label for label in window.lbl_unsaved._labels if label.isVisible()]
            assert window.lbl_unsaved.text() == "Saved"
            assert len(visible) == 1
            assert visible[0].text() == "Saved"
            assert visible[0].graphicsEffect().opacity() == 1.0
            assert not visible[0].graphicsEffect().isEnabled()
            assert window.lbl_unsaved.layout().currentIndex() == window.lbl_unsaved._current_index
    finally:
        _close(window)


def test_saved_chip_survives_resize_after_opening_save_on_junkman(tmp_path) -> None:
    """Regression: the first save opened on Junkman left a live opacity cache.

    Resizing could then move the chip while Qt reused an empty effect cache;
    changing pages happened to repaint it and made the symptom disappear.
    """

    save_path = tmp_path / "TESTSAVE"
    save_path.write_bytes(bytes(0xF86C))
    window = _window()
    try:
        assert window._current_stack_page_name() == "Junkman"
        with mock.patch.object(ToastNotification, "show_toast"):
            window.on_open(filepath=str(save_path))

        transition = window.lbl_unsaved._transition_group
        if transition is not None:
            transition.setCurrentTime(transition.duration())
        APP.processEvents()

        assert window.lbl_unsaved.text() == "Saved"
        for width in (1920, 1400):
            window.resize(width, 780)
            APP.processEvents()
            visible = [label for label in window.lbl_unsaved._labels if label.isVisible()]
            assert len(visible) == 1
            assert visible[0].text() == "Saved"
            assert visible[0].graphicsEffect().opacity() == 1.0
            assert not visible[0].graphicsEffect().isEnabled()
    finally:
        _close(window)


def test_header_integrity_plate_keeps_all_four_verdicts_visible() -> None:
    window = _window()
    try:
        window._update_header_integrity(
            SimpleNamespace(
                md5_ok=True,
                crc_block1_ok=False,
                crc_data_ok=None,
                crc_block2_ok=True,
            )
        )

        assert {
            key: (badge.text(), badge.property("verdict"))
            for key, badge in window.header_integrity_badges.items()
        } == {
            "md5": ("MD5 OK", "ok"),
            "crc1": ("CRC1 BAD", "bad"),
            "data": ("DATA ?", "unknown"),
            "crc2": ("CRC2 OK", "ok"),
        }
        assert window.header_integrity_plate.toolTip().splitlines() == [
            "MD5: OK",
            "CRC1: BAD",
            "CRC data: ?",
            "CRC2: OK",
        ]
    finally:
        _close(window)


def test_header_path_keeps_full_value_in_tooltip_when_elided() -> None:
    window = _window()
    try:
        full_path = Path("C:/a/very/long/folder/name/that/needs/eliding/TESTSAVE")
        window.savefile = SimpleNamespace(path=full_path)
        geometry = window.header_file_plate.geometry().getRect()
        window._update_header_path()

        assert window.lbl_file.toolTip() == str(full_path)
        assert window.lbl_file.text() != "File: (not opened)"
        assert window.header_file_plate.geometry().getRect() == geometry
    finally:
        _close(window)


def test_header_empty_path_keeps_readable_contrast_in_every_theme() -> None:
    for theme_name in available_theme_names():
        tokens = resolve_theme_tokens(theme_name)
        assert _contrast_ratio(tokens["HEADER_EMPTY_TEXT"], tokens["BG_GLASS"]) >= 4.5, theme_name

    tokens = resolve_theme_tokens("Solarized")
    stylesheet = build_shell_stylesheet("Solarized")
    file_path_rule = stylesheet.split("QLabel#filePath {", 1)[1].split("}", 1)[0]
    assert f"color: {tokens['HEADER_EMPTY_TEXT']};" in file_path_rule


def test_header_state_chip_crossfades_and_retargets_in_place() -> None:
    chip = HeaderStateChip()
    chip.show()
    APP.processEvents()
    try:
        width = chip.width()
        chip.setState("Unsaved changes", "pending")
        first = chip._transition_group
        assert first is not None
        assert first.duration() == chip._DURATION_MS
        assert first.state() == QAbstractAnimation.Running

        first.setCurrentTime(first.duration() // 2)
        chip.setState("Applied, not saved", "applied")
        second = chip._transition_group
        assert second is not None and second is not first
        assert chip.text() == "Applied, not saved"
        assert chip.width() == width

        second.setCurrentTime(second.duration())
        APP.processEvents()
        visible = [label for label in chip._labels if label.isVisible()]
        assert len(visible) == 1
        assert visible[0].text() == "Applied, not saved"
        assert visible[0].property("state") == "applied"
        assert visible[0].graphicsEffect().opacity() == 1.0
        assert not visible[0].graphicsEffect().isEnabled()
        assert chip.layout().currentIndex() == chip._current_index
    finally:
        _close(chip)


def test_header_state_chip_honours_disabled_widget_motion(monkeypatch) -> None:
    chip = HeaderStateChip()
    chip.show()
    APP.processEvents()
    try:
        monkeypatch.setattr(chip, "_motion_allowed", lambda: False)
        chip.setState("Unsaved changes", "pending")

        assert chip._transition_group is None
        visible = [label for label in chip._labels if label.isVisible()]
        assert len(visible) == 1
        assert visible[0].text() == "Unsaved changes"
        assert visible[0].graphicsEffect().opacity() == 1.0
        assert not visible[0].graphicsEffect().isEnabled()
    finally:
        _close(chip)
