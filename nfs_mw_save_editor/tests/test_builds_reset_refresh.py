from pathlib import Path
import sys
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from ui.pages import junkman_mixin as junkman_module
from ui.pages.junkman_mixin import JunkmanMixin
from ui.main_window import MainWindow
from ui.staged_state import StagedEditState


class _ResetWantHarness(JunkmanMixin):
    def __init__(self) -> None:
        self.have_counts = {1: 2}
        self.have_money = 100
        self.have_profile_alias = "Player"
        self.staged_state = StagedEditState()
        self.staged_state.counts.set_item(1, 5, self.have_counts)
        self.staged_state.money.set(999)
        self.staged_state.profile_alias.set("Staged")
        self.profile_alias_error = "bad"
        self.garage_detection_error = None
        self.parts_detection_error = None
        self.have_slot_bounties = {0: 111}
        self.have_slot_heats = {0: 2}
        self.have_owned_locations = {0x6200: 0x02}
        self.have_owned_career_slots = {0x6200: 7}
        self.have_parts_levels = {31: {"engine": 2}}
        self.have_parts_masks = {31: 0x10}
        self.staged_state.snapshot_injections.stage("snap-a", "career")
        self.clear_unknown_next = False
        self.calls: list[tuple[str, str | None]] = []

    def _has_pending_changes(self) -> bool:
        return MainWindow._has_pending_changes(self)

    def _has_profile_pending_changes(self) -> bool:
        return False

    def _has_parts_pending_changes(self) -> bool:
        return False

    def _has_garage_transfer_pending_changes(self) -> bool:
        return False

    def _has_garage_pursuit_pending_changes(self) -> bool:
        return False

    def _mark_all_heavy_pages_dirty(self) -> None:
        self.calls.append(("mark_all_heavy_pages_dirty", None))

    def _refresh_profile_inputs(self) -> None:
        self.calls.append(("refresh_profile_inputs", None))

    def _current_stack_page_name(self) -> str:
        return "Builds"

    def _refresh_garage_page(self, reason: str = "data_change") -> None:
        self.calls.append(("refresh_garage_page", reason))

    def _refresh_parts_page(self, reason: str = "data_change") -> None:
        self.calls.append(("refresh_parts_page", reason))

    def _refresh_presets_page(self, reason: str = "data_change") -> None:
        self.calls.append(("refresh_presets_page", reason))

    def refresh_cards(self) -> None:
        self.calls.append(("refresh_cards", None))


class BuildsResetRefreshTests(unittest.TestCase):
    def test_reset_want_refreshes_builds_page_with_reset_reveal(self) -> None:
        harness = _ResetWantHarness()

        with mock.patch.object(junkman_module.ToastNotification, "show_toast"):
            harness.on_reset_want()

        self.assertIn(("refresh_presets_page", "reset_reveal"), harness.calls)
        self.assertNotIn(("refresh_garage_page", "reset_reveal"), harness.calls)
        self.assertNotIn(("refresh_parts_page", "reset_reveal"), harness.calls)
        self.assertFalse(harness.staged_state.snapshot_injections.has_pending())

    def test_reset_want_clears_clear_unknown_pending_flag(self) -> None:
        harness = _ResetWantHarness()
        harness.staged_state.counts.reset_to(harness.have_counts)
        harness.staged_state.money.reset_to(harness.have_money)
        harness.staged_state.profile_alias.reset_to(harness.have_profile_alias)
        harness.staged_state.slot_bounties.reset_to(harness.have_slot_bounties)
        harness.staged_state.slot_heats.reset_to(harness.have_slot_heats)
        harness.staged_state.owned_locations.reset_to(harness.have_owned_locations)
        harness.staged_state.owned_career_slots.reset_to(harness.have_owned_career_slots)
        harness.staged_state.parts_levels.reset_to(harness.have_parts_levels)
        harness.staged_state.parts_masks.reset_to(harness.have_parts_masks)
        harness.staged_state.snapshot_injections.clear_all()
        harness.clear_unknown_next = True

        self.assertTrue(harness._has_pending_changes())

        with mock.patch.object(junkman_module.ToastNotification, "show_toast"):
            harness.on_reset_want()

        self.assertFalse(harness.clear_unknown_next)
        self.assertFalse(harness._has_pending_changes())

    def test_reset_want_edit_state_clears_clear_unknown_flag(self) -> None:
        # Open-file path: _reset_want_edit_state must not leak the staged
        # clear-unknown action into the next save file.
        harness = _ResetWantHarness()
        harness.clear_unknown_next = True

        MainWindow._reset_want_edit_state(harness)

        self.assertFalse(harness.clear_unknown_next)


if __name__ == "__main__":
    unittest.main()
