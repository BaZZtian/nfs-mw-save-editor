from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import OwnedCarTemplate, SnapshotLibraryEntry
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


if __name__ == "__main__":
    unittest.main()
