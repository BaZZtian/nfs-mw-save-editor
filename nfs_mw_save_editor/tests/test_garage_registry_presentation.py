from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import (
    CarNumberRegistryAudit,
    CareerSlotStatus,
    GarageAllocatorSnapshot,
    OwnedCarSlotStatus,
    PartsSlotStatus,
    ResolvedTransferCarEntry,
)
from core.savefile import SaveFile
from ui.pages.constants import RIVAL_CAR_MODELS
from ui.pages.garage_mixin import GarageMixin


def _owned_status(slot_index: int, *, reusable: bool) -> OwnedCarSlotStatus:
    return OwnedCarSlotStatus(
        slot_index=slot_index,
        abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET + slot_index * SaveFile.CAREER_VEHICLE_SIZE,
        occupied=not reusable,
        reusable=reusable,
        blocked_reason=None,
        status_kind="reusable" if reusable else "occupied",
        status_code="reusable" if reusable else "occupied",
        status_detail=None,
        car_number=SaveFile.EMPTY_CAR_NUMBER if reusable else slot_index + 1,
        location_bits=0,
        misc_bits=0,
        parts_slot=SaveFile.EMPTY_CAREER_SLOT,
        career_slot=SaveFile.EMPTY_CAREER_SLOT,
    )


def _parts_status(parts_slot: int, *, reusable: bool) -> PartsSlotStatus:
    return PartsSlotStatus(
        parts_slot=parts_slot,
        abs_off=SaveFile.PARTS_BLOCK_BASE_OFFSET
        + (parts_slot - SaveFile.PARTS_BLOCK_SLOT_BASE) * SaveFile.PARTS_BLOCK_SIZE,
        referenced_by_owned_car=not reusable,
        reusable=reusable,
        blocked_reason=None if reusable else "Referenced by owned-car record",
        status_kind="reusable" if reusable else "occupied",
        status_code="reusable_native_empty" if reusable else "occupied_owned_reference",
        status_detail=None,
        marker=SaveFile.EMPTY_PARTS_BLOCK_MARKER,
    )


def _pink_slip_entry(display_name: str = "Aston Martin DB9") -> ResolvedTransferCarEntry:
    return ResolvedTransferCarEntry(
        abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET,
        car_number=94,
        signature=b"\x11" * 8,
        display_name=display_name,
        source_kind="Pink Slip",
        location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
        misc_bits=0,
        parts_slot=45,
        career_slot=13,
        is_career=False,
        is_my_cars=False,
        is_pink_slip=True,
        has_pursuit_link=True,
        heat=None,
        heat_level=None,
        bounty=None,
        escaped=None,
        busted=None,
        pursuit_abs_off=None,
    )


class InjectionCapacityModelTests(unittest.TestCase):
    def test_capacity_is_min_of_owned_and_parts_pools(self) -> None:
        snapshot = GarageAllocatorSnapshot(
            owned_slots=tuple(_owned_status(index, reusable=index < 5) for index in range(8)),
            career_slots=(),
            parts_slots=tuple(_parts_status(31 + index, reusable=index < 2) for index in range(4)),
        )

        self.assertEqual(len(snapshot.reusable_owned_slots), 5)
        self.assertEqual(len(snapshot.reusable_parts_slots), 2)
        self.assertEqual(snapshot.injection_capacity, 2)

    def test_capacity_is_zero_when_parts_pool_is_exhausted(self) -> None:
        snapshot = GarageAllocatorSnapshot(
            owned_slots=tuple(_owned_status(index, reusable=True) for index in range(10)),
            career_slots=(),
            parts_slots=tuple(_parts_status(31 + index, reusable=False) for index in range(44)),
        )

        self.assertEqual(snapshot.injection_capacity, 0)

    def test_snapshot_from_savefile_carries_parts_pool(self) -> None:
        sf = object.__new__(SaveFile)
        sf.get_owned_car_slot_statuses = lambda **kwargs: [_owned_status(0, reusable=True)]
        sf.get_career_slot_statuses = lambda **kwargs: []
        captured: dict = {}

        def fake_parts(**kwargs):
            captured.update(kwargs)
            return [_parts_status(31, reusable=True), _parts_status(32, reusable=False)]

        sf.get_parts_slot_statuses = fake_parts

        snapshot = sf.get_garage_allocator_snapshot(reserved_parts_slots={40})

        self.assertEqual(captured["reserved_parts_slots"], {40})
        self.assertEqual(len(snapshot.parts_slots), 2)
        self.assertEqual(snapshot.injection_capacity, 1)


class InjectionCapacityBadgeTests(unittest.TestCase):
    def test_summary_text_and_tooltip_expose_both_pools(self) -> None:
        mixin = GarageMixin()
        snapshot = GarageAllocatorSnapshot(
            owned_slots=tuple(_owned_status(index, reusable=index < 7) for index in range(9)),
            career_slots=(),
            parts_slots=tuple(_parts_status(31 + index, reusable=index < 3) for index in range(44)),
        )

        text, tooltip = mixin._injection_capacity_summary(snapshot)

        self.assertEqual(text, "Injection capacity: 3")
        self.assertIn("Free customization blocks: 3 of 44", tooltip)
        self.assertIn("Free owned-car rows: 7", tooltip)


class CarNumberingDiagnosticsTests(unittest.TestCase):
    """Diagnostics stay quiet on native saves and name the rows on drifted ones."""

    def _mixin_with_audit(self, audit) -> GarageMixin:
        mixin = GarageMixin()
        sf = object.__new__(SaveFile)
        sf.audit_car_number_registry = lambda: audit
        mixin.savefile = sf
        return mixin

    def test_native_save_reports_nothing(self) -> None:
        audit = CarNumberRegistryAudit(
            row_count=SaveFile.CAREER_VEHICLE_SLOT_COUNT,
            expected_row_count=SaveFile.CAREER_VEHICLE_SLOT_COUNT,
            live_rows=(0, 1),
            tombstone_rows=(),
            empty_rows=tuple(range(2, SaveFile.CAREER_VEHICLE_SLOT_COUNT)),
            drifted_rows=(),
            out_of_range_rows=(),
            duplicate_numbers=(),
        )

        self.assertEqual(self._mixin_with_audit(audit)._car_numbering_diagnostic_lines(), [])

    def test_drift_and_duplicates_are_named(self) -> None:
        audit = CarNumberRegistryAudit(
            row_count=SaveFile.CAREER_VEHICLE_SLOT_COUNT,
            expected_row_count=SaveFile.CAREER_VEHICLE_SLOT_COUNT,
            live_rows=(0, 29),
            tombstone_rows=(3,),
            empty_rows=(4,),
            drifted_rows=((29, 150),),
            out_of_range_rows=(),
            duplicate_numbers=(111,),
        )

        lines = self._mixin_with_audit(audit)._car_numbering_diagnostic_lines()

        self.assertIn("2 live, 1 sold", lines[0])
        self.assertIn("Row 29 - car #150, the game would number it #110", lines[1])
        self.assertTrue(any("#111" in line for line in lines))


class PinkSlipProvenanceTests(unittest.TestCase):
    """Provenance keys off the car MODEL: every rival drives a unique one,
    so it survives repaints and vinyl swaps that killed the livery approach."""

    def test_tooltip_names_the_boss_by_model(self) -> None:
        tooltip = GarageMixin()._pink_slip_tooltip(_pink_slip_entry("Aston Martin DB9"))

        self.assertIn("Won from Blacklist #3 Ronnie", tooltip)
        self.assertIn("pink slip prize", tooltip)

    def test_all_fifteen_rival_models_are_mapped(self) -> None:
        self.assertEqual(len(RIVAL_CAR_MODELS), 15)
        self.assertEqual(sorted(number for number, _ in RIVAL_CAR_MODELS.values()), list(range(1, 16)))
        for display_name, (number, nickname) in RIVAL_CAR_MODELS.items():
            tooltip = GarageMixin()._pink_slip_tooltip(_pink_slip_entry(display_name))
            self.assertIn(f"Won from Blacklist #{number} {nickname}", tooltip)

    def test_tooltip_stays_generic_for_non_rival_models(self) -> None:
        tooltip = GarageMixin()._pink_slip_tooltip(_pink_slip_entry("Porsche 911 Turbo S"))

        self.assertIn("Won from a Blacklist rival", tooltip)
        self.assertNotIn("#", tooltip.split("\n")[0])

    def test_unresolved_signature_stays_generic(self) -> None:
        tooltip = GarageMixin()._pink_slip_tooltip(_pink_slip_entry("Sig AB12CD34AB12CD34"))

        self.assertIn("Won from a Blacklist rival", tooltip)


if __name__ == "__main__":
    unittest.main()
