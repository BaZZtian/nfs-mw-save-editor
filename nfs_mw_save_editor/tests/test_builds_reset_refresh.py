from pathlib import Path
import sys
import unittest
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from ui.pages import junkman_mixin as junkman_module
from ui.pages.junkman_mixin import JunkmanMixin
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
        self.have_slot_flags = {0: 3}
        self.have_owned_locations = {0x6200: 0x02}
        self.have_owned_career_slots = {0x6200: 7}
        self.have_parts_levels = {31: {"engine": 2}}
        self.have_parts_masks = {31: 0x10}
        self.staged_state.snapshot_injections.stage("snap-a", "career")
        self.calls: list[tuple[str, str | None]] = []

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


if __name__ == "__main__":
    unittest.main()
