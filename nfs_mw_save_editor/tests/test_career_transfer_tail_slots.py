from pathlib import Path
import sys
import unittest
import struct


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import CareerSlotStatus, GarageAllocatorSnapshot, OwnedCarRecord, OwnedCarTransferPlan, PursuitRecord
from core.savefile import SaveFile


class CareerSlotTailAllocatorTests(unittest.TestCase):
    def test_blank_tail_slot_with_staged_link_is_not_reusable(self) -> None:
        sf = object.__new__(SaveFile)
        sf.data = bytearray(SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE * 18)
        sf.get_pursuit_records = lambda: []

        for slot in range(16):
            abs_off = SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE
            sf.data[abs_off:abs_off + SaveFile.GARAGE_SLOT_SIZE] = SaveFile._build_zero_pursuit_slot_payload(sf, slot)

        tail_off = SaveFile.GARAGE_BASE_OFFSET + 16 * SaveFile.GARAGE_SLOT_SIZE
        sf.data[tail_off:tail_off + SaveFile.GARAGE_SLOT_SIZE] = (
            b"\xFF" + (b"\xCD" * 23) + (b"\x00" * (SaveFile.GARAGE_SLOT_SIZE - 24))
        )

        sf.get_owned_car_records = lambda: [
            OwnedCarRecord(
                car_number=200,
                signature=b"\x01" * 8,
                location_bits=SaveFile.CAREER_FLAG,
                misc_bits=0,
                parts_slot=31,
                career_slot=16,
                abs_off=0x6219,
            )
        ]
        sf.get_pursuit_records = lambda: [
            PursuitRecord(
                career_slot=slot,
                heat=SaveFile.GARAGE_HEAT_BASELINE,
                heat_level=1,
                bounty=0,
                escaped=0,
                busted=0,
                abs_off=SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE,
            )
            for slot in range(16)
        ]

        statuses = sf.get_career_slot_statuses()
        tail_status = next(status for status in statuses if status.career_slot == 16)

        self.assertEqual(tail_status.linked_car_count, 1)
        self.assertFalse(tail_status.reusable)
        self.assertEqual(tail_status.blocked_reason, "Already targeted by a staged Career car")


class TransferOwnedCarPursuitInitTests(unittest.TestCase):
    def test_my_cars_to_career_initializes_target_pursuit_slot(self) -> None:
        sf = object.__new__(SaveFile)
        calls: list[tuple[str, int, int | None]] = []

        sf.get_active_career_car_number = lambda: 85
        sf.get_pursuit_records = lambda: []
        sf.plan_owned_car_transfer = lambda *args, **kwargs: OwnedCarTransferPlan(
            source_abs_off=0x6219,
            source_display_name="Test Car",
            source_location_bits=SaveFile.MY_CARS_FLAG,
            source_misc_bits=0,
            source_career_slot=SaveFile.EMPTY_CAREER_SLOT,
            source_parts_slot=31,
            target_location_bits=SaveFile.CAREER_FLAG,
            target_misc_bits=0,
            target_career_slot=16,
            cleared_source_career_slot=None,
            clears_pursuit_slot=False,
            target_owned_abs_off=0x6219,
            requires_relocation=False,
            refusal_reason=None,
        )
        sf.clear_pursuit_slot = lambda slot: calls.append(("clear_pursuit_slot", int(slot), None))
        sf.set_owned_car_location = (
            lambda abs_off, location_bits, misc_bits=None:
            calls.append(("set_owned_car_location", int(abs_off), int(location_bits)))
        )
        sf.clear_owned_car_career_slot = lambda abs_off: calls.append(("clear_owned_car_career_slot", int(abs_off), None))
        sf.set_owned_car_career_slot = (
            lambda abs_off, slot: calls.append(("set_owned_car_career_slot", int(abs_off), int(slot)))
        )
        sf._read_u32 = lambda abs_off: 0
        sf.choose_fallback_active_career_record = lambda: None
        sf.set_active_career_car_number = lambda car_number: calls.append(("set_active_career_car_number", int(car_number), None))

        plan = sf.transfer_owned_car(0x6219, "career", desired_career_slot=16)

        self.assertEqual(plan.target_career_slot, 16)
        self.assertIn(("clear_pursuit_slot", 16, None), calls)
        self.assertIn(("set_owned_car_location", 0x6219, SaveFile.CAREER_FLAG), calls)
        self.assertIn(("set_owned_car_career_slot", 0x6219, 16), calls)

    def test_my_cars_to_career_warns_when_filling_last_confirmed_career_slot(self) -> None:
        sf = object.__new__(SaveFile)
        source_abs_off = 0x7000
        source = OwnedCarRecord(
            car_number=300,
            signature=b"\xAA" * 8,
            location_bits=SaveFile.MY_CARS_FLAG,
            misc_bits=0,
            parts_slot=55,
            career_slot=SaveFile.EMPTY_CAREER_SLOT,
            abs_off=source_abs_off,
        )

        sf._owned_record_by_abs_off = lambda abs_off, **kwargs: source
        sf.get_pursuit_records = lambda: []
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
        ] + [source]
        sf.get_garage_allocator_snapshot = lambda **kwargs: GarageAllocatorSnapshot(
            owned_slots=(),
            career_slots=(
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
                ),
            ),
        )

        plan = sf.plan_owned_car_transfer(source_abs_off, "career")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_career_slot, 24)
        self.assertTrue(plan.warnings)
        self.assertIn("25/25", plan.warnings[0])


class PursuitSlotCanonicalizationTests(unittest.TestCase):
    def test_clear_pursuit_slot_restores_slot_byte_and_baseline_heat(self) -> None:
        sf = object.__new__(SaveFile)
        sf.data = bytearray(SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE * 2)

        for slot in range(2):
            abs_off = SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE
            payload = bytearray(SaveFile.GARAGE_SLOT_SIZE)
            payload[0] = slot & 0xFF
            payload[1] = 0xCD
            payload[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET] = SaveFile.GARAGE_MAX_BUSTED_BASE
            payload[0x0A:0x0C] = b"\xCD\xCD"
            SaveFile._write_pursuit_heat_into(payload, SaveFile.GARAGE_HEAT_BASELINE)
            sf.data[abs_off:abs_off + SaveFile.GARAGE_SLOT_SIZE] = payload

        dirty_off = SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE
        sf.data[dirty_off] = 0xFF
        struct.pack_into("<f", sf.data, dirty_off + SaveFile.GARAGE_HEAT_FLOAT_OFFSET, 3.5)

        sf.clear_pursuit_slot(1)

        repaired = bytes(sf.data[dirty_off:dirty_off + SaveFile.GARAGE_SLOT_SIZE])
        repaired_heat = struct.unpack_from("<f", repaired, SaveFile.GARAGE_HEAT_FLOAT_OFFSET)[0]

        self.assertEqual(repaired[0], 1)
        self.assertEqual(repaired[1], 0xCD)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET], SaveFile.GARAGE_MAX_BUSTED_BASE)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_TIMES_BUSTED_OFFSET], 0)
        self.assertEqual(repaired[0x0A:0x0C], b"\xCD\xCD")
        self.assertAlmostEqual(repaired_heat, SaveFile.GARAGE_HEAT_NATIVE_FRESH)


if __name__ == "__main__":
    unittest.main()
