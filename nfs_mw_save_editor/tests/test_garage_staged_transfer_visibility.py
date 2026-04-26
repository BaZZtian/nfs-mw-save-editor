from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import OwnedCarTransferPlan, ResolvedTransferCarEntry
from core.savefile import SaveFile
from ui.pages.garage_mixin import GarageMixin
from ui.staged_state import StagedEditState


def _entry(
    *,
    abs_off: int,
    car_number: int,
    source_kind: str,
    location_bits: int,
    career_slot: int,
) -> ResolvedTransferCarEntry:
    is_my_cars = source_kind == "My Cars"
    is_pink_slip = source_kind == "Pink Slip"
    is_career = source_kind in ("Career", "Pink Slip")
    has_pursuit_link = career_slot != SaveFile.EMPTY_CAREER_SLOT
    return ResolvedTransferCarEntry(
        abs_off=abs_off,
        car_number=car_number,
        signature=bytes([car_number & 0xFF]) * 8,
        display_name=f"Car {car_number}",
        source_kind=source_kind,
        location_bits=location_bits,
        misc_bits=0,
        parts_slot=car_number,
        career_slot=career_slot,
        is_career=is_career,
        is_my_cars=is_my_cars,
        is_pink_slip=is_pink_slip,
        has_pursuit_link=has_pursuit_link,
        heat=1.0 if has_pursuit_link else None,
        heat_level=1 if has_pursuit_link else None,
        bounty=1000 if has_pursuit_link else None,
        escaped=0 if has_pursuit_link else None,
        busted=0 if has_pursuit_link else None,
        pursuit_abs_off=(0x9000 + career_slot) if has_pursuit_link else None,
    )


class _DummySearch:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _DummySaveFile:
    def __init__(
        self,
        actual_entries: list[ResolvedTransferCarEntry],
        projected_entries: list[ResolvedTransferCarEntry],
        *,
        active_car_number: int | None = None,
    ) -> None:
        self._actual_entries = list(actual_entries)
        self._projected_entries = list(projected_entries)
        self._active_car_number = active_car_number

    def get_transfer_car_entries(self, **kwargs) -> list[ResolvedTransferCarEntry]:
        has_overrides = any(value is not None for value in kwargs.values())
        if has_overrides:
            return list(self._projected_entries)
        return list(self._actual_entries)

    def get_active_career_car_number(self) -> int | None:
        return self._active_car_number


class _GarageHarness(GarageMixin):
    def __init__(
        self,
        actual_entries: list[ResolvedTransferCarEntry],
        projected_entries: list[ResolvedTransferCarEntry],
    ) -> None:
        self.savefile = _DummySaveFile(actual_entries, projected_entries, active_car_number=actual_entries[0].car_number)
        self.garage_detection_error = None
        self.snapshot_library_error = None
        self.snapshot_library = []
        self.want_snapshot_injections = {}
        self.staged_state = StagedEditState()
        self.garage_transfer_entries = list(actual_entries)
        self.garage_slots = []
        self.garage_search = _DummySearch("")
        self.garage_filter = "All"
        self.have_owned_locations = {entry.abs_off: entry.location_bits for entry in actual_entries}
        self.have_owned_career_slots = {entry.abs_off: entry.career_slot for entry in actual_entries}
        self.staged_state.owned_locations.reset_to(
            {entry.abs_off: entry.location_bits for entry in projected_entries}
        )
        self.staged_state.owned_career_slots.reset_to(
            {entry.abs_off: entry.career_slot for entry in projected_entries}
        )
        self.have_slot_bounties = {}
        self.have_slot_heats = {}
        self._garage_visible_order = [entry.abs_off for entry in actual_entries]

    def _current_snapshot_injection_plans(self, extra=None):
        return {}, set(), set(), set()

    def _garage_transfer_plan_with_context(
        self,
        abs_off: int,
        target_mode: str,
        **kwargs,
    ) -> OwnedCarTransferPlan:
        current_entry = next(entry for entry in self._current_transfer_entries() if entry.abs_off == abs_off)
        if target_mode == "my_cars":
            target_location_bits = SaveFile.MY_CARS_FLAG
            target_career_slot = None
        else:
            target_location_bits = (
                SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG
                if current_entry.is_pink_slip
                else SaveFile.CAREER_FLAG
            )
            target_career_slot = 0 if current_entry.career_slot == SaveFile.EMPTY_CAREER_SLOT else current_entry.career_slot
        return OwnedCarTransferPlan(
            source_abs_off=current_entry.abs_off,
            source_display_name=current_entry.display_name,
            source_location_bits=current_entry.location_bits,
            source_misc_bits=current_entry.misc_bits,
            source_career_slot=current_entry.career_slot,
            source_parts_slot=current_entry.parts_slot,
            target_location_bits=target_location_bits,
            target_misc_bits=current_entry.misc_bits,
            target_career_slot=target_career_slot,
            cleared_source_career_slot=None,
            clears_pursuit_slot=False,
            target_owned_abs_off=current_entry.abs_off,
            requires_relocation=False,
            refusal_reason=None,
            warnings=(),
        )


class GarageStagedTransferVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actual_career = _entry(
            abs_off=0x6200,
            car_number=10,
            source_kind="Career",
            location_bits=SaveFile.CAREER_FLAG,
            career_slot=3,
        )
        self.actual_my_cars = _entry(
            abs_off=0x6300,
            car_number=20,
            source_kind="My Cars",
            location_bits=SaveFile.MY_CARS_FLAG,
            career_slot=SaveFile.EMPTY_CAREER_SLOT,
        )
        self.projected_my_cars = _entry(
            abs_off=self.actual_career.abs_off,
            car_number=self.actual_career.car_number,
            source_kind="My Cars",
            location_bits=SaveFile.MY_CARS_FLAG,
            career_slot=SaveFile.EMPTY_CAREER_SLOT,
        )
        self.projected_career = _entry(
            abs_off=self.actual_my_cars.abs_off,
            car_number=self.actual_my_cars.car_number,
            source_kind="Career",
            location_bits=SaveFile.CAREER_FLAG,
            career_slot=0,
        )
        self.harness = _GarageHarness(
            [self.actual_career, self.actual_my_cars],
            [self.projected_my_cars, self.projected_career],
        )

    def test_filters_keep_using_actual_save_state_until_apply(self) -> None:
        self.harness.garage_filter = "Career"
        career_ids = {entry.abs_off for entry in self.harness._garage_card_entries()}
        self.assertEqual(career_ids, {self.actual_career.abs_off})

        self.harness.garage_filter = "My Cars"
        my_cars_ids = {entry.abs_off for entry in self.harness._garage_card_entries()}
        self.assertEqual(my_cars_ids, {self.actual_my_cars.abs_off})

    def test_view_model_separates_actual_and_staged_transfer_state(self) -> None:
        view_models = {vm.slot.abs_off: vm for vm in self.harness._garage_card_view_models()}

        career_vm = view_models[self.actual_career.abs_off]
        self.assertFalse(career_vm.slot.is_my_cars)
        self.assertTrue(career_vm.projected_slot.is_my_cars)
        self.assertTrue(career_vm.changed)
        career_label, career_tooltip = self.harness._garage_utility_summary(career_vm)
        self.assertEqual(career_label, "Pending -> My Cars")
        self.assertIn("Apply", career_tooltip)

        my_cars_vm = view_models[self.actual_my_cars.abs_off]
        self.assertTrue(my_cars_vm.slot.is_my_cars)
        self.assertFalse(my_cars_vm.projected_slot.is_my_cars)
        self.assertTrue(my_cars_vm.changed)
        my_cars_label, my_cars_tooltip = self.harness._garage_utility_summary(my_cars_vm)
        self.assertEqual(my_cars_label, "Pending -> Career")
        self.assertIn("Career Slot 1", my_cars_tooltip)


if __name__ == "__main__":
    unittest.main()
