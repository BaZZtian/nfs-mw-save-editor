"""Apply-level belt sentinel: token-clean apply must not touch the belt.

The core normalizer (JunkmanInventory.apply_counts) deliberately heals the
belt with clear-all-and-rewrite - that contract stays and is covered by
test_junkman_belt.py. These tests pin the orchestration rule on top of it:
on_apply_changes runs the normalizer ONLY when tokens were actually edited
(effective-value pending or a staged clear-unknown), so an unrelated apply
leaves all 63 raw slots byte-identical, ghost slots included.
"""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtWidgets import QDialog

from core.savefile import SaveFile
from ui.pages import junkman_mixin as junkman_module
from ui.pages.junkman_mixin import JunkmanMixin
from ui.main_window import MainWindow
from ui.staged_state import StagedEditState

BELT_ABS = 0x5739
BELT_END = 0x5A2D
SLOT_SIZE = 12


def _belt_slot(type_id: int, state: int) -> bytes:
    raw = bytearray(SLOT_SIZE)
    raw[0] = type_id
    raw[8] = state
    return bytes(raw)


def _make_savefile() -> SaveFile:
    """Synthetic save: 2x17 + 1x1 owned, one ghost {0,2}, one unknown ID 25."""

    data = bytearray(0xF86C)
    slots = [
        _belt_slot(17, 1),
        _belt_slot(1, 1),
        _belt_slot(0, 2),  # ghost from the ancient hand-written experiments
        _belt_slot(17, 1),
        _belt_slot(25, 1),  # unknown ID, preserved by contract
    ]
    for k, raw in enumerate(slots):
        data[BELT_ABS + k * SLOT_SIZE:BELT_ABS + (k + 1) * SLOT_SIZE] = raw
    return SaveFile(path=Path("synthetic"), data=data)


class _ApplyHarness(JunkmanMixin):
    def __init__(self, savefile: SaveFile) -> None:
        self.savefile = savefile
        self.have_counts = savefile.get_junkman_counts()
        self.have_money = savefile.get_money()
        self.have_profile_alias = "Player"
        self.staged_state = StagedEditState()
        self.clear_unknown_next = False
        self.preserve_unknown = True
        self.practical_cap10 = False
        self.tokens = [SimpleNamespace(id=i) for i in range(1, 22)]
        self.garage_detection_error = "test: garage path disabled"
        self.parts_detection_error = "test: parts path disabled"
        self.profile_alias_error = None

    def _build_apply_summary(self, want_full):
        return {"summary_lines": [], "detail_sections": []}

    def _staged_career_vehicle_count(self) -> int:
        return 1

    def _reset_want_edit_state(self) -> None:
        MainWindow._reset_want_edit_state(self)

    def refresh_state(self) -> None:
        pass


def _run_apply(harness: _ApplyHarness) -> None:
    dialog = mock.MagicMock()
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    with mock.patch.object(junkman_module, "ApplyConfirmDialog", return_value=dialog), \
            mock.patch.object(junkman_module.ToastNotification, "show_toast"), \
            mock.patch.object(junkman_module.QMessageBox, "critical",
                              side_effect=AssertionError("apply raised")):
        harness.on_apply_changes()


def _belt_bytes(savefile: SaveFile) -> bytes:
    return bytes(savefile.data[BELT_ABS:BELT_END])


class ApplyBeltSentinelTests(unittest.TestCase):
    def test_token_clean_apply_leaves_belt_byte_identical(self) -> None:
        savefile = _make_savefile()
        harness = _ApplyHarness(savefile)
        harness.staged_state.money.set(5000)
        before = _belt_bytes(savefile)

        _run_apply(harness)

        self.assertEqual(_belt_bytes(savefile), before)
        self.assertEqual(savefile.get_money(), 5000)

    def test_token_edit_still_heals_belt(self) -> None:
        savefile = _make_savefile()
        harness = _ApplyHarness(savefile)
        harness.staged_state.counts.set_item(2, 1, harness.have_counts)

        _run_apply(harness)

        slot_pairs = [
            (savefile.data[BELT_ABS + k * SLOT_SIZE],
             savefile.data[BELT_ABS + k * SLOT_SIZE + 8])
            for k in range(63)
        ]
        filled = [pair for pair in slot_pairs if pair != (0, 0)]
        # Canonical rewrite: sorted by ID, one slot per token, ghost healed,
        # unknown ID preserved.
        self.assertEqual(filled, [(1, 1), (2, 1), (17, 1), (17, 1), (25, 1)])

    def test_staged_clear_unknown_alone_triggers_rewrite(self) -> None:
        savefile = _make_savefile()
        harness = _ApplyHarness(savefile)
        harness.clear_unknown_next = True

        _run_apply(harness)

        counts = savefile.get_junkman_counts()
        self.assertNotIn(25, counts)
        self.assertEqual(counts, {1: 1, 17: 2})
        self.assertFalse(harness.clear_unknown_next)


if __name__ == "__main__":
    unittest.main()
