"""Pre-flight audit of the car registry against the native numbering rule.

The game numbers a car by its physical registry row (car_number = 81 + row,
rows 0..118), reusing a sold row with that row's own number. Anything else in
a save was written by hand, so the audit classifies rows and reports drift,
duplicates and out-of-range numbers - it never repairs.
"""

from pathlib import Path
import struct
import sys
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.savefile import SaveFile


def _registry_savefile(rows: int = SaveFile.CAREER_VEHICLE_SLOT_COUNT) -> SaveFile:
    """A save whose registry is `rows` never-used rows."""

    sf = object.__new__(SaveFile)
    size = SaveFile.CAREER_VEHICLE_BASE_OFFSET + rows * SaveFile.CAREER_VEHICLE_SIZE
    sf.data = bytearray(size)
    for row in range(rows):
        abs_off = SaveFile.CAREER_VEHICLE_BASE_OFFSET + row * SaveFile.CAREER_VEHICLE_SIZE
        struct.pack_into("<I", sf.data, abs_off, SaveFile.EMPTY_CAR_NUMBER)
        sf.data[abs_off + 0x12:abs_off + 0x14] = SaveFile.CAREER_VEHICLE_SENTINEL
    return sf


def _fill_row(sf: SaveFile, row: int, *, car_number: int, signature: bytes = b"\x11" * 8) -> None:
    abs_off = SaveFile.CAREER_VEHICLE_BASE_OFFSET + row * SaveFile.CAREER_VEHICLE_SIZE
    struct.pack_into("<I", sf.data, abs_off, car_number)
    sf.data[
        abs_off + SaveFile.CAREER_VEHICLE_SIGNATURE_OFFSET:
        abs_off + SaveFile.CAREER_VEHICLE_SIGNATURE_OFFSET + SaveFile.CAREER_VEHICLE_SIGNATURE_SIZE
    ] = signature


class CarNumberRegistryAuditTests(unittest.TestCase):
    def test_native_save_is_clean(self) -> None:
        sf = _registry_savefile()
        for row in range(6):
            _fill_row(sf, row, car_number=SaveFile.CAR_NUMBER_SLOT_BASE + row)

        audit = sf.audit_car_number_registry()

        self.assertTrue(audit.is_native)
        self.assertTrue(audit.prefix_intact)
        self.assertEqual(audit.row_count, SaveFile.CAREER_VEHICLE_SLOT_COUNT)
        self.assertEqual(audit.live_rows, tuple(range(6)))
        self.assertEqual(audit.drifted_rows, ())

    def test_sold_row_is_a_tombstone_never_used_row_is_empty(self) -> None:
        sf = _registry_savefile()
        for row in range(3):
            _fill_row(sf, row, car_number=SaveFile.CAR_NUMBER_SLOT_BASE + row)
        # Native sale clears only the number and leaves the signature behind.
        sold_off = SaveFile.CAREER_VEHICLE_BASE_OFFSET + 1 * SaveFile.CAREER_VEHICLE_SIZE
        struct.pack_into("<I", sf.data, sold_off, SaveFile.EMPTY_CAR_NUMBER)

        audit = sf.audit_car_number_registry()

        self.assertEqual(audit.tombstone_rows, (1,))
        self.assertEqual(audit.live_rows, (0, 2))
        self.assertNotIn(1, audit.empty_rows)
        self.assertTrue(audit.is_native)

    def test_hand_numbered_row_is_reported_as_drift(self) -> None:
        sf = _registry_savefile()
        _fill_row(sf, 0, car_number=SaveFile.CAR_NUMBER_SLOT_BASE)
        _fill_row(sf, 1, car_number=150)  # parked out of the way by an editor

        audit = sf.audit_car_number_registry()

        self.assertEqual(audit.drifted_rows, ((1, 150),))
        self.assertFalse(audit.is_native)

    def test_duplicate_numbers_are_reported_once(self) -> None:
        sf = _registry_savefile()
        _fill_row(sf, 0, car_number=111)
        _fill_row(sf, 1, car_number=111)
        _fill_row(sf, 2, car_number=111)

        audit = sf.audit_car_number_registry()

        self.assertEqual(audit.duplicate_numbers, (111,))
        self.assertFalse(audit.is_native)

    def test_number_outside_the_native_range_is_reported(self) -> None:
        sf = _registry_savefile()
        _fill_row(sf, 0, car_number=1)  # representative non-native allocation

        audit = sf.audit_car_number_registry()

        self.assertEqual(audit.out_of_range_rows, ((0, 1),))
        self.assertFalse(audit.is_native)

    def test_short_registry_prefix_is_reported(self) -> None:
        sf = _registry_savefile(rows=40)

        audit = sf.audit_car_number_registry()

        self.assertEqual(audit.row_count, 40)
        self.assertFalse(audit.prefix_intact)
        self.assertFalse(audit.is_native)


if __name__ == "__main__":
    unittest.main()
