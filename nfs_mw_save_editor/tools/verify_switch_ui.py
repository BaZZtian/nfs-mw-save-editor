"""Exercise the unchanged original Qt UI with a private native save copy.

Usage: python tools/verify_switch_ui.py /path/to/raw/save
The input is never modified; all writes occur in a temporary directory.
"""
from pathlib import Path
import hashlib
import os
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from ui.main_window import MainWindow
from ui.theme import available_theme_names
from ui.pages.junkman_mixin import ApplyConfirmDialog


def verify(input_path):
    original = Path(input_path).read_bytes()
    with tempfile.TemporaryDirectory(prefix="nfsmw-switch-ui-") as directory:
        root = Path(directory)
        os.environ["APPDATA"] = str(root / "appdata")
        save_path = root / "TEST_SAVE"
        save_path.write_bytes(original)
        app = QApplication.instance() or QApplication([])

        def dialog_failure(*args, **kwargs):
            raise AssertionError(f"Original UI opened an error dialog: {args[1:3]}")

        with patch.object(QMessageBox, "critical", side_effect=dialog_failure), patch.object(QMessageBox, "warning", side_effect=dialog_failure), patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), patch.object(ApplyConfirmDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            window = MainWindow()
            window.resize(1180, 780)
            window.on_open(str(save_path))
            app.processEvents()
            assert window.savefile is not None
            assert window.savefile.validate_integrity().actual_size == 62688
            assert window.have_money == window.savefile.get_money()
            assert len(available_theme_names()) == 30
            pages = tuple(window.nav_buttons)
            for name in pages:
                window.nav_buttons[name].click()
                app.processEvents()
            assert window.garage_detection_error is None
            assert window._career_summary_cache is not None
            window.nav_buttons["Profile"].click()
            window.money_edit.setText("345678")
            window.on_money_edit_finished()
            window.on_apply_changes()
            assert window.savefile.get_money() == 345678
            assert save_path.read_bytes() == original
            window.on_save()
            assert window.savefile.validate_integrity().md5_ok
            assert list(root.glob("TEST_SAVE.bak_*"))[0].read_bytes() == original
            window.savefile.set_money(1)
            assert window.savefile.get_money() == 1
            window.on_reload_from_disk()
            assert window.savefile.get_money() == 345678
            window.close()
            window.deleteLater()
            app.processEvents()
        assert Path(input_path).read_bytes() == original
        print("Original Qt UI: open, all pages, Apply (memory), Save + backup and Reload passed")
        print("Pages:", ", ".join(pages))
        print("Input unchanged; SHA-256:", hashlib.sha256(original).hexdigest())


if __name__ == "__main__":
    verify(sys.argv[1])
