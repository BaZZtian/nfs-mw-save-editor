from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import CareerSlotStatus, OwnedCarRecord, OwnedCarTransferPlan, PursuitRecord
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


if __name__ == "__main__":
    unittest.main()
