from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.savefile import SaveFile
from tools.validate_snapshot_library import _verify_injected_record


class ValidateSnapshotLibraryTests(unittest.TestCase):
    def _entry(self, signature: bytes):
        return SimpleNamespace(
            primary_owned_record_template=SimpleNamespace(signature=signature),
        )

    def _reloaded(self, *, signature: bytes, location_bits: int):
        record = SimpleNamespace(
            signature=signature,
            location_bits=location_bits,
            parts_slot=32,
            career_slot=1,
        )
        return SimpleNamespace(get_owned_car_records=lambda: [record])

    def test_career_verification_accepts_planned_pink_slip_bits(self) -> None:
        signature = b"DB9-DB9!"

        found = _verify_injected_record(
            self._reloaded(
                signature=signature,
                location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
            ),
            self._entry(signature),
            target_mode="career",
            target_location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
            target_parts_slot=32,
            target_career_slot=1,
        )

        self.assertTrue(found)

    def test_career_verification_rejects_location_bits_different_from_plan(self) -> None:
        signature = b"DB9-DB9!"

        found = _verify_injected_record(
            self._reloaded(signature=signature, location_bits=SaveFile.CAREER_FLAG),
            self._entry(signature),
            target_mode="career",
            target_location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
            target_parts_slot=32,
            target_career_slot=1,
        )

        self.assertFalse(found)


if __name__ == "__main__":
    unittest.main()
