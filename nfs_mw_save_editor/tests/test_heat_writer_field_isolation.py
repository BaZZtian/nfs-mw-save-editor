import math
from pathlib import Path
import struct
import sys
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.savefile import SaveFile


SENTINEL = 0xA5


def _savefile_with_pursuit_record(record: bytearray) -> SaveFile:
    assert len(record) == SaveFile.GARAGE_SLOT_SIZE
    sf = SaveFile.__new__(SaveFile)
    sf.data = bytearray(SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE * 2)
    sf.data[SaveFile.PLAYER_RANK_OFFSET] = 1
    sf.data[SaveFile.GARAGE_BASE_OFFSET:SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE] = record
    return sf


def _sentinel_record() -> bytearray:
    record = bytearray([SENTINEL] * SaveFile.GARAGE_SLOT_SIZE)
    record[0] = 0
    record[1:4] = SaveFile.GARAGE_SIGNATURE_A
    record[8:12] = SaveFile.GARAGE_SIGNATURE_B
    return record


class HeatWriterFieldIsolationTests(unittest.TestCase):
    def test_set_slot_heat_touches_only_the_heat_float(self) -> None:
        sf = _savefile_with_pursuit_record(_sentinel_record())
        before = bytes(sf.data)

        sf.set_slot_heat(0, 3.0)

        after = bytes(sf.data)
        heat_start = SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_HEAT_FLOAT_OFFSET
        changed = [off for off in range(len(before)) if before[off] != after[off]]
        self.assertTrue(all(heat_start <= off < heat_start + 4 for off in changed), changed)
        self.assertAlmostEqual(struct.unpack_from("<f", after, heat_start)[0], 3.0)

    def test_set_slot_heat_preserves_impound_and_infraction_counters(self) -> None:
        # MaxBusted/TimesBusted (+0x02/+0x03) double as the slot-detection
        # signature bytes, so only detectable values are exercised here.
        record = _sentinel_record()
        record[1:4] = b"\xCD\x05\x00"  # MaxBusted=5, TimesBusted=0
        record[SaveFile.GARAGE_IMPOUND_STATE_OFFSET] = 1
        record[SaveFile.GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET] = 4
        struct.pack_into("<H", record, SaveFile.GARAGE_IMPOUND_EVADE_COUNT_OFFSET, 7)
        struct.pack_into("<f", record, SaveFile.GARAGE_HEAT_FLOAT_OFFSET, 2.0)
        infraction_offsets = [
            block_off + counter * 2
            for block_off in (SaveFile.GARAGE_UNSERVED_INFRACTIONS_OFFSET, SaveFile.GARAGE_SERVED_INFRACTIONS_OFFSET)
            for counter in range(SaveFile.GARAGE_INFRACTION_COUNTER_COUNT)
        ]
        for index, rel_off in enumerate(infraction_offsets):
            struct.pack_into("<H", record, rel_off, 100 + index)
        sf = _savefile_with_pursuit_record(record)

        sf.set_slot_heat(0, 5.0)

        base = SaveFile.GARAGE_BASE_OFFSET
        self.assertEqual(sf.data[base + 0x02], 5)
        self.assertEqual(sf.data[base + SaveFile.GARAGE_IMPOUND_TIMES_BUSTED_OFFSET], 0)
        self.assertEqual(sf.data[base + SaveFile.GARAGE_IMPOUND_STATE_OFFSET], 1)
        self.assertEqual(sf.data[base + SaveFile.GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET], 4)
        self.assertEqual(struct.unpack_from("<H", sf.data, base + SaveFile.GARAGE_IMPOUND_EVADE_COUNT_OFFSET)[0], 7)
        for index, rel_off in enumerate(infraction_offsets):
            self.assertEqual(struct.unpack_from("<H", sf.data, base + rel_off)[0], 100 + index)
        record = sf.get_pursuit_records()[0]
        self.assertAlmostEqual(record.heat, 5.0)
        self.assertEqual(record.heat_level, 5)

    def test_non_finite_heat_reads_as_unknown_and_repairs_in_place(self) -> None:
        record = _sentinel_record()
        struct.pack_into("<f", record, SaveFile.GARAGE_HEAT_FLOAT_OFFSET, float("nan"))
        sf = _savefile_with_pursuit_record(record)
        before = bytes(sf.data)

        pursuit = sf.get_pursuit_records()[0]
        self.assertTrue(math.isnan(pursuit.heat))
        self.assertIsNone(pursuit.heat_level)
        self.assertIsNone(sf.get_slot_heat_level(0))

        sf.set_slot_heat(0, 2.0)

        after = bytes(sf.data)
        heat_start = SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_HEAT_FLOAT_OFFSET
        changed = [off for off in range(len(before)) if before[off] != after[off]]
        self.assertTrue(all(heat_start <= off < heat_start + 4 for off in changed), changed)
        self.assertEqual(sf.get_pursuit_records()[0].heat_level, 2)


if __name__ == "__main__":
    unittest.main()
