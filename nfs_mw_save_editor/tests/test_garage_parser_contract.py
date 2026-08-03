"""Handle-based garage parser contract (native FEPlayerCarDB.CareerRecords[25]).

Occupancy is decided by the Handle byte alone: 0xFF = empty (stale payload
legal and invisible), slot index = live (plus the canonical pad-byte gate as
the editor's extra fail-closed policy). Holes are legal, a zero-car garage is
a valid empty result, and MaxBusted/TimesBusted are gameplay data, never
detection criteria.
"""

from pathlib import Path
import struct
import sys
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.savefile import SaveFile


def _empty_garage_savefile() -> SaveFile:
    sf = object.__new__(SaveFile)
    sf.data = bytearray(SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE * SaveFile.GARAGE_SLOT_COUNT)
    for slot in range(SaveFile.GARAGE_SLOT_COUNT):
        abs_off = SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE
        sf.data[abs_off:abs_off + SaveFile.GARAGE_SLOT_SIZE] = (
            b"\xFF" + b"\xCD" * (SaveFile.GARAGE_SLOT_SIZE - 1)
        )
    return sf


def _live_payload(career_slot: int, *, bounty: int = 0) -> bytearray:
    payload = bytearray(SaveFile.GARAGE_SLOT_SIZE)
    payload[0] = career_slot
    payload[1] = 0xCD
    payload[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET] = SaveFile.GARAGE_MAX_BUSTED_BASE
    payload[0x0A:0x0C] = b"\xCD\xCD"
    struct.pack_into("<f", payload, SaveFile.GARAGE_HEAT_FLOAT_OFFSET, SaveFile.GARAGE_HEAT_BASELINE)
    struct.pack_into("<I", payload, SaveFile.GARAGE_BOUNTY_OFFSET, bounty)
    return payload


def _write_slot(sf: SaveFile, career_slot: int, payload: bytes) -> None:
    abs_off = SaveFile.GARAGE_BASE_OFFSET + career_slot * SaveFile.GARAGE_SLOT_SIZE
    sf.data[abs_off:abs_off + SaveFile.GARAGE_SLOT_SIZE] = payload


class GarageParserContractTests(unittest.TestCase):
    def test_zero_car_garage_is_a_valid_empty_result(self) -> None:
        sf = _empty_garage_savefile()
        self.assertEqual(sf.get_pursuit_records(), [])

    def test_stale_payload_under_empty_handle_never_becomes_a_phantom_record(self) -> None:
        sf = _empty_garage_savefile()
        stale = _live_payload(3, bounty=123_456)
        stale[0] = SaveFile.GARAGE_EMPTY_HANDLE
        _write_slot(sf, 3, stale)

        self.assertEqual(sf.get_pursuit_records(), [])

    def test_holes_between_live_records_are_legal(self) -> None:
        sf = _empty_garage_savefile()
        _write_slot(sf, 0, _live_payload(0, bounty=10))
        _write_slot(sf, 2, _live_payload(2, bounty=30))
        _write_slot(sf, 24, _live_payload(24, bounty=240))

        records = sf.get_pursuit_records()
        self.assertEqual([record.career_slot for record in records], [0, 2, 24])
        self.assertEqual([record.bounty for record in records], [10, 30, 240])
        self.assertEqual(
            [record.abs_off for record in records],
            [SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE for slot in (0, 2, 24)],
        )

    def test_times_busted_is_not_a_detection_criterion(self) -> None:
        sf = _empty_garage_savefile()
        payload = _live_payload(0)
        payload[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET] = 5
        payload[SaveFile.GARAGE_IMPOUND_TIMES_BUSTED_OFFSET] = 3
        payload[SaveFile.GARAGE_IMPOUND_STATE_OFFSET] = 2
        _write_slot(sf, 0, payload)

        records = sf.get_pursuit_records()
        self.assertEqual([record.career_slot for record in records], [0])

    def test_unexpected_handle_fails_closed(self) -> None:
        sf = _empty_garage_savefile()
        payload = _live_payload(0)
        payload[0] = 0x05
        _write_slot(sf, 0, payload)

        with self.assertRaises(ValueError):
            sf.get_pursuit_records()

    def test_live_handle_failing_pad_gate_fails_closed(self) -> None:
        sf = _empty_garage_savefile()
        payload = _live_payload(0)
        payload[1] = 0x00
        _write_slot(sf, 0, payload)

        with self.assertRaises(ValueError):
            sf.get_pursuit_records()

    def test_statuses_treat_stale_empty_slot_as_reusable(self) -> None:
        sf = _empty_garage_savefile()
        sf.get_owned_car_records = lambda: []
        stale = _live_payload(7, bounty=999_999)
        stale[0] = SaveFile.GARAGE_EMPTY_HANDLE
        _write_slot(sf, 7, stale)

        statuses = sf.get_career_slot_statuses()
        self.assertEqual(len(statuses), SaveFile.GARAGE_SLOT_COUNT)
        stale_status = next(status for status in statuses if status.career_slot == 7)
        self.assertTrue(stale_status.reusable)
        self.assertEqual(stale_status.bounty, 0)
        self.assertTrue(all(status.reusable for status in statuses))

    def test_ensure_initialized_overwrites_stale_empty_slot_canonically(self) -> None:
        sf = _empty_garage_savefile()
        stale = _live_payload(4, bounty=555)
        stale[0] = SaveFile.GARAGE_EMPTY_HANDLE
        _write_slot(sf, 4, stale)

        abs_off = sf._ensure_pursuit_slot_initialized(4)

        raw = bytes(sf.data[abs_off:abs_off + SaveFile.GARAGE_SLOT_SIZE])
        expected = _live_payload(4)
        struct.pack_into("<f", expected, SaveFile.GARAGE_HEAT_FLOAT_OFFSET, SaveFile.GARAGE_HEAT_NATIVE_FRESH)
        self.assertEqual(raw[0], 4)
        self.assertEqual(raw, bytes(expected))
        self.assertEqual([record.career_slot for record in sf.get_pursuit_records()], [4])


if __name__ == "__main__":
    unittest.main()
