from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import CareerSlotStatus, OwnedCarRecord, OwnedCarSlotStatus, PartsSlotStatus, OwnedCarTemplate, SnapshotLibraryEntry
from core.savefile import SaveFile


def _make_snapshot(*, source_kind: str, location_bits: int) -> SnapshotLibraryEntry:
    return SnapshotLibraryEntry(
        snapshot_id=f"test-{source_kind}-{location_bits}",
        json_path=Path("dummy.json"),
        library_bucket="Main",
        file_label="dummy.json",
        display_name="Dummy",
        source_file="dummy",
        source_kind=source_kind,
        primary_owned_record_template=OwnedCarTemplate(
            car_number=0,
            signature=b"\x00" * 8,
            location_bits=location_bits,
            misc_bits=0,
            source_kind=source_kind,
        ),
        normalized_primary_build_block=b"",
        performance_levels=(),
        primary_visual_fields=(),
        requires_unresolved_global_visual_state=False,
        has_visual_sidecar=False,
    )


class SnapshotInjectionLocationBitsTests(unittest.TestCase):
    def test_my_cars_target_uses_my_cars_flag(self) -> None:
        snapshot = _make_snapshot(source_kind="Pink Slip", location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
        self.assertEqual(
            SaveFile._snapshot_target_location_bits(snapshot, "my_cars"),
            SaveFile.MY_CARS_FLAG,
        )

    def test_career_target_preserves_pink_slip_flag(self) -> None:
        snapshot = _make_snapshot(source_kind="Pink Slip", location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
        self.assertEqual(
            SaveFile._snapshot_target_location_bits(snapshot, "career"),
            SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
        )

    def test_career_target_uses_plain_career_for_non_pink_slip_snapshots(self) -> None:
        snapshot = _make_snapshot(source_kind="Career", location_bits=SaveFile.CAREER_FLAG)
        self.assertEqual(
            SaveFile._snapshot_target_location_bits(snapshot, "career"),
            SaveFile.CAREER_FLAG,
        )

    def test_source_kind_fallback_preserves_pink_slip_when_template_bits_are_flattened(self) -> None:
        snapshot = _make_snapshot(source_kind="Pink Slip", location_bits=SaveFile.CAREER_FLAG)
        self.assertEqual(
            SaveFile._snapshot_target_location_bits(snapshot, "career"),
            SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
        )

    def test_career_injection_warns_when_filling_last_confirmed_career_slot(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(source_kind="Career", location_bits=SaveFile.CAREER_FLAG)

        sf.get_owned_car_records = lambda: [
            OwnedCarRecord(
                car_number=100 + slot,
                signature=bytes([slot & 0xFF]) * 8,
                location_bits=SaveFile.CAREER_FLAG,
                misc_bits=0,
                parts_slot=31 + slot,
                career_slot=slot,
                abs_off=0x6219 + slot * SaveFile.CAREER_VEHICLE_SIZE,
            )
            for slot in range(SaveFile.CONFIRMED_MAX_CAREER_LIKE_CARS - 1)
        ]
        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            OwnedCarSlotStatus(
                slot_index=24,
                abs_off=0x6500,
                occupied=False,
                reusable=True,
                blocked_reason=None,
                status_kind="reusable",
                status_code="empty",
                status_detail=None,
                car_number=SaveFile.EMPTY_CAR_NUMBER,
                location_bits=0,
                misc_bits=0,
                parts_slot=0xFF,
                career_slot=SaveFile.EMPTY_CAREER_SLOT,
            )
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            PartsSlotStatus(
                parts_slot=60,
                abs_off=0xA000,
                referenced_by_owned_car=False,
                reusable=True,
                blocked_reason=None,
                status_kind="reusable",
                status_code="empty",
                status_detail=None,
                marker=SaveFile.EMPTY_PARTS_BLOCK_MARKER,
            )
        ]
        sf.get_career_slot_statuses = lambda **kwargs: [
            CareerSlotStatus(
                career_slot=24,
                abs_off=SaveFile.GARAGE_BASE_OFFSET + 24 * SaveFile.GARAGE_SLOT_SIZE,
                linked_car_count=0,
                reusable=True,
                blocked_reason=None,
                status_kind="reusable",
                status_code="empty",
                status_detail=None,
                bounty=0,
                escaped=0,
                busted=0,
                is_zero=True,
            )
        ]

        plan = sf.plan_snapshot_injection(snapshot, "career")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_career_slot, 24)
        self.assertTrue(plan.warnings)
        self.assertIn("25/25", plan.warnings[0])


if __name__ == "__main__":
    unittest.main()
