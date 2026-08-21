import os
from pathlib import Path
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
)

import ui.main_window as main_window_module
import ui.theme as theme_module
from ui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _ReentrantDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.stylesheet_calls = 0
        self._reentered = False

    def setStyleSheet(self, stylesheet: str) -> None:
        self.stylesheet_calls += 1
        if not self._reentered:
            self._reentered = True
            theme_module.apply_popup_theme(self, "Blueprint")
        super().setStyleSheet(stylesheet)


class _EventFilterHarness(MainWindow):
    def __init__(self) -> None:
        QMainWindow.__init__(self)
        self.theme_name = "Blueprint"


class PopupThemeReentrancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_apply_popup_theme_blocks_reentrant_setstylesheet(self) -> None:
        dialog = _ReentrantDialog()

        resolved_name = theme_module.apply_popup_theme(dialog, "Blueprint")

        self.assertEqual(resolved_name, "Blueprint")
        self.assertEqual(dialog.stylesheet_calls, 1)
        self.assertEqual(dialog.property("_scopedThemeName"), "Blueprint")
        self.assertFalse(bool(dialog.property(theme_module._SCOPED_POPUP_THEME_APPLYING_PROPERTY)))

    def test_event_filter_skips_guarded_popup_polish(self) -> None:
        window = _EventFilterHarness()
        dialog = QDialog(window)
        dialog.setProperty(theme_module._SCOPED_POPUP_THEME_APPLYING_PROPERTY, True)
        polish_event = QEvent(QEvent.Type.Polish)

        with mock.patch.object(main_window_module, "apply_popup_theme") as apply_mock:
            window.eventFilter(dialog, polish_event)

        apply_mock.assert_not_called()

    def test_event_filter_applies_popup_theme_on_show_only(self) -> None:
        window = _EventFilterHarness()
        dialog = QDialog(window)
        polish_event = QEvent(QEvent.Type.Polish)
        show_event = QEvent(QEvent.Type.Show)

        with mock.patch.object(main_window_module, "apply_popup_theme") as apply_mock:
            window.eventFilter(dialog, polish_event)
            apply_mock.assert_not_called()

            window.eventFilter(dialog, show_event)

        apply_mock.assert_called_once_with(dialog, "Blueprint")

    def test_popup_theme_marks_affirmative_choice_without_changing_safe_default(self) -> None:
        box = QMessageBox()
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)

        theme_module.apply_popup_theme(box, "Blueprint")

        yes = box.button(QMessageBox.Yes)
        no = box.button(QMessageBox.No)
        self.assertEqual(yes.property("popupAction"), "primary")
        self.assertEqual(no.property("popupAction"), "")
        self.assertTrue(no.isDefault())

    def test_popup_theme_marks_accept_and_destructive_roles(self) -> None:
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        theme_module.apply_popup_theme(dialog, "Blueprint")
        self.assertEqual(buttons.button(QDialogButtonBox.Ok).property("popupAction"), "primary")
        self.assertEqual(buttons.button(QDialogButtonBox.Cancel).property("popupAction"), "")

        box = QMessageBox()
        destructive = box.addButton("Discard", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        theme_module.apply_popup_theme(box, "Blueprint")
        self.assertEqual(destructive.property("popupAction"), "danger")

    def test_popup_theme_marks_only_default_custom_action(self) -> None:
        box = QMessageBox()
        recommended = box.addButton("Normalize to snapshot", QMessageBox.ActionRole)
        alternative = box.addButton("Keep earned bounty", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(recommended)

        theme_module.apply_popup_theme(box, "Blueprint")

        self.assertEqual(recommended.property("popupAction"), "primary")
        self.assertEqual(alternative.property("popupAction"), "")


if __name__ == "__main__":
    unittest.main()
