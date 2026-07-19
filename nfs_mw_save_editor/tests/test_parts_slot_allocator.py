from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import (
    OwnedCarRecord,
    OwnedCarSlotStatus,
    OwnedCarTemplate,
    PartsSlotStatus,
    SnapshotLibraryEntry,
)
from core.savefile import SaveFile


TAIL_PARTS_SLOT = 74


def _savefile_with_native_empty_parts_region() -> SaveFile:
    sf = object.__new__(SaveFile)
    sf.data = bytearray(SaveFile.GARAGE_BASE_OFFSET)
    for slot in sf._parts_slot_numbers():
        abs_off = sf._parts_block_abs_off(slot)
        marker_off = abs_off + SaveFile.PARTS_MARKER_OFFSET
        sf.data[marker_off:marker_off + 4] = SaveFile.EMPTY_PARTS_BLOCK_MARKER
    sf.get_owned_car_records = lambda: []
    return sf


def _record_with_parts_slot(parts_slot: int) -> OwnedCarRecord:
    return OwnedCarRecord(
        car_number=99,
        signature=b"\x01" * 8,
        location_bits=SaveFile.MY_CARS_FLAG,
        misc_bits=0,
        parts_slot=parts_slot,
        career_slot=SaveFile.EMPTY_CAREER_SLOT,
        abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET,
    )


class PartsSlotStatusesTailSlotTests(unittest.TestCase):
    def test_parts_region_spans_slots_31_to_74(self) -> None:
        sf = _savefile_with_native_empty_parts_region()

        statuses = sf.get_parts_slot_statuses()

        self.assertEqual([status.parts_slot for status in statuses], list(range(31, 75)))

    def test_empty_tail_slot_74_is_reusable(self) -> None:
        sf = _savefile_with_native_empty_parts_region()

        statuses = sf.get_parts_slot_statuses()

        self.assertTrue(all(status.reusable for status in statuses))
        tail = statuses[-1]
        self.assertEqual(tail.parts_slot, TAIL_PARTS_SLOT)
        self.assertTrue(tail.reusable)
        self.assertIsNone(tail.blocked_reason)
        self.assertEqual(tail.status_code, "reusable_native_empty")

    def test_tail_slot_74_honors_staged_reservation(self) -> None:
        sf = _savefile_with_native_empty_parts_region()

        statuses = sf.get_parts_slot_statuses(reserved_parts_slots={TAIL_PARTS_SLOT})
        tail = statuses[-1]

        self.assertFalse(tail.reusable)
        self.assertEqual(tail.status_code, "reserved_by_staged_injector")

    def test_tail_slot_74_referenced_by_owned_car_is_occupied(self) -> None:
        sf = _savefile_with_native_empty_parts_region()
        sf.get_owned_car_records = lambda: [_record_with_parts_slot(TAIL_PARTS_SLOT)]

        statuses = sf.get_parts_slot_statuses()
        tail = statuses[-1]

        self.assertFalse(tail.reusable)
        self.assertEqual(tail.status_code, "occupied_owned_reference")


class PlannerTailSlotTests(unittest.TestCase):
    def _make_snapshot(self) -> SnapshotLibraryEntry:
        block = bytearray(index & 0xFF for index in range(SaveFile.PARTS_BLOCK_SIZE))
        block[SaveFile.PARTS_MARKER_OFFSET:SaveFile.PARTS_MARKER_OFFSET + 4] = b"\x00\x00\x00\x00"
        return SnapshotLibraryEntry(
            snapshot_id="tail-slot-test",
            json_path=Path("tail-slot-test.json"),
            library_bucket="Main",
            file_label="tail-slot-test",
            display_name="Tail Slot Car",
            source_file="fixture-save",
            source_kind="My Cars",
            primary_owned_record_template=OwnedCarTemplate(
                car_number=0,
                signature=b"\x22" * 8,
                location_bits=SaveFile.MY_CARS_FLAG,
                misc_bits=0,
                source_kind="My Cars",
            ),
            normalized_primary_build_block=bytes(block),
            performance_levels=(),
            primary_visual_fields=(),
            requires_unresolved_global_visual_state=False,
            has_visual_sidecar=False,
            optional_visual_sidecar=None,
        )

    def test_planner_selects_tail_slot_74_when_it_is_the_only_free_slot(self) -> None:
        sf = object.__new__(SaveFile)
        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            OwnedCarSlotStatus(
                slot_index=0,
                abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET,
                occupied=False,
                reusable=True,
                blocked_reason=None,
                status_kind="reusable",
                status_code="reusable",
                status_detail=None,
                car_number=SaveFile.EMPTY_CAR_NUMBER,
                location_bits=0,
                misc_bits=0,
                parts_slot=SaveFile.EMPTY_CAREER_SLOT,
                career_slot=SaveFile.EMPTY_CAREER_SLOT,
            )
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            PartsSlotStatus(
                parts_slot=slot,
                abs_off=SaveFile.PARTS_BLOCK_BASE_OFFSET
                + (slot - SaveFile.PARTS_BLOCK_SLOT_BASE) * SaveFile.PARTS_BLOCK_SIZE,
                referenced_by_owned_car=slot != TAIL_PARTS_SLOT,
                reusable=slot == TAIL_PARTS_SLOT,
                blocked_reason=None if slot == TAIL_PARTS_SLOT else "Referenced by owned-car record",
                status_kind="reusable" if slot == TAIL_PARTS_SLOT else "occupied",
                status_code="reusable_native_empty" if slot == TAIL_PARTS_SLOT else "occupied_owned_reference",
                status_detail=None if slot == TAIL_PARTS_SLOT else "Referenced by owned-car record",
                marker=SaveFile.EMPTY_PARTS_BLOCK_MARKER,
            )
            for slot in range(31, 75)
        ]

        plan = sf.plan_snapshot_injection(self._make_snapshot(), "my_cars")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_parts_slot, TAIL_PARTS_SLOT)


if __name__ == "__main__":
    unittest.main()
