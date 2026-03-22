from __future__ import annotations

import datetime
import hashlib
import json
import logging
import struct
from pathlib import Path
from typing import List, Optional, Set, Tuple

from core.cars import resolve_car_name
from core.checksums import ea_crc32
from core.junkman import JunkmanInventory
from core.models import (
    CareerSlotStatus,
    CareerVehicleRecord,
    FullCarBuildSnapshot,
    GarageAllocatorSnapshot,
    HashScheme,
    IntegrityStatus,
    OwnedCarRecord,
    OwnedCarSlotStatus,
    OwnedCarTemplate,
    OwnedCarTransferPlan,
    PartsRecord,
    PartsSlotStatus,
    PursuitRecord,
    ResolvedGarageEntry,
    ResolvedMyCarsEntry,
    ResolvedPartsEntry,
    ResolvedTransferCarEntry,
    SaveLayout,
    SnapshotInjectionPlan,
    SnapshotLibraryEntry,
    VisualSidecarTemplate,
)
from core.tuning_limits import get_model_tuning_limits

logger = logging.getLogger(__name__)


class SaveFile:
    # Junkman inventory slot layout (dynamically detected)
    SAVED_DATA_START = JunkmanInventory.SAVED_DATA_START
    SLOT_STRIDE = JunkmanInventory.SLOT_STRIDE
    SLOT_TYPE_OFF = 0x00
    SLOT_COUNT_OFF = 0x08
    SLOT_SIZE = JunkmanInventory.SLOT_SIZE
    SLOT_MAX = 200  # upper bound for diff helpers
    MONEY_OFFSET = 0x4039
    GARAGE_BASE_OFFSET = 0xE2ED
    GARAGE_SLOT_SIZE = 0x38
    GARAGE_BOUNTY_OFFSET = 0x10
    GARAGE_ESCAPED_OFFSET = 0x14
    GARAGE_BUSTED_OFFSET = 0x16
    GARAGE_SIGNATURE_A = b"\xCD\x03\x00"
    GARAGE_SIGNATURE_B = b"\x00\x00\xCD\xCD"
    CAREER_VEHICLE_BASE_OFFSET = 0x6219
    CAREER_VEHICLE_SIZE = 0x14
    CAREER_VEHICLE_SIGNATURE_OFFSET = 0x04
    CAREER_VEHICLE_SIGNATURE_SIZE = 0x08
    CAREER_VEHICLE_FLAGS_OFFSET = 0x0C
    CAREER_VEHICLE_FLAGS2_OFFSET = 0x0E
    CAREER_VEHICLE_PARTS_SLOT_OFFSET = 0x10
    CAREER_VEHICLE_SLOT_OFFSET = 0x11
    CAREER_VEHICLE_SENTINEL = b"\xCD\xCD"
    EMPTY_CAR_NUMBER = 0xFFFFFFFF
    EMPTY_CAREER_SLOT = 0xFF
    CAREER_FLAG = 0x02
    MY_CARS_FLAG = 0x04
    PINK_SLIP_FLAG = 0x40
    PARTS_BLOCK_BASE_OFFSET = 0x9CCD
    PARTS_BLOCK_SLOT_BASE = 31
    PARTS_BLOCK_SIZE = 0x198
    PARTS_MARKER_OFFSET = 0x194
    PARTS_LEVELS_BASE_OFFSET = 0x118
    PARTS_LEVEL_FIELD_SIZE = 0x04
    PARTS_TIRES_OFFSET = 0x118
    PARTS_BRAKES_OFFSET = 0x11C
    PARTS_SUSPENSION_OFFSET = 0x120
    PARTS_TRANSMISSION_OFFSET = 0x124
    PARTS_ENGINE_OFFSET = 0x128
    PARTS_TURBO_OFFSET = 0x12C
    PARTS_NOS_OFFSET = 0x130
    PARTS_JUNKMAN_MASK_OFFSET = 0x134
    PARTS_CONFIRMED_SLICE_END = 0x138
    VISUAL_TABLE_BASE_OFFSET = 0x5577
    VISUAL_TABLE_ENTRY_COUNT = 57
    VISUAL_TABLE_ENTRY_STRIDE = 0x08
    VISUAL_TABLE_DEFAULT_VALUE = 0x01
    EMPTY_PARTS_BLOCK_HEAD_FILL = 0xFF
    EMPTY_PARTS_BLOCK_ZERO_TAIL_OFFSET = 0x190
    EMPTY_PARTS_BLOCK_MARKER = b"\xFF\xCD\xCD\xCD"
    PRIMARY_VISUAL_FIELDS: Tuple[Tuple[str, int, int], ...] = (
        ("Body Kit", 0x02E, 1),
        ("Spoiler", 0x058, 2),
        ("Roof", 0x07C, 1),
        ("Hood", 0x07E, 1),
        ("Rims", 0x084, 2),
        ("Paint", 0x098, 1),
        ("Body Vinyl", 0x09A, 2),
        ("Advanced Ptr", 0x09C, 2),
        ("Windshield Decal", 0x0A6, 2),
        ("Rear Window Decal", 0x0B6, 2),
        ("Left Door Decal", 0x0D0, 2),
        ("Number Visual A", 0x0D2, 4),
        ("Right Door Decal", 0x0E0, 2),
        ("Number Visual B", 0x0E2, 4),
        ("Left Quarter Decal", 0x0E6, 2),
        ("Right Quarter Decal", 0x0F6, 2),
        ("Window Tint", 0x106, 1),
        ("Gauge A", 0x108, 1),
        ("Gauge B", 0x10A, 1),
        ("Gauge C", 0x10C, 1),
        ("Gauge D", 0x10E, 1),
    )
    JUNKMAN_MASK_BITS: Tuple[Tuple[int, str], ...] = (
        (0x01, "Tires"),
        (0x02, "Brakes"),
        (0x04, "Suspension"),
        (0x08, "Transmission"),
        (0x10, "Engine"),
        (0x20, "Turbo"),
        (0x40, "NOS"),
    )
    PART_LEVEL_OFFSETS: Dict[str, int] = {
        "Tires": PARTS_TIRES_OFFSET,
        "Brakes": PARTS_BRAKES_OFFSET,
        "Suspension": PARTS_SUSPENSION_OFFSET,
        "Transmission": PARTS_TRANSMISSION_OFFSET,
        "Engine": PARTS_ENGINE_OFFSET,
        "Turbo": PARTS_TURBO_OFFSET,
        "NOS": PARTS_NOS_OFFSET,
    }

    def __init__(self, path: Path, data: bytearray, layout: SaveLayout | None = None, hash_scheme: HashScheme = None):
        self.path = path
        self.data = data
        self.layout = layout or SaveLayout()
        self.hash_scheme = hash_scheme or self.detect_hash_scheme()
        self._junk_base_cache: Optional[int] = None
        self.junkman = JunkmanInventory(self)
        self._junk_base_cache = self.junkman.base_rel

    @staticmethod
    def load(path: str | Path) -> "SaveFile":
        p = Path(path)
        data = bytearray(p.read_bytes())
        sf = SaveFile(path=p, data=data)
        sf.hash_scheme = sf.detect_hash_scheme()
        return sf

    # --- basic helpers ---

    def _read_u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def _read_u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.data, offset)[0]

    def _read_u8(self, offset: int) -> int:
        return self.data[offset]

    def _write_u16(self, offset: int, value: int) -> None:
        struct.pack_into("<H", self.data, offset, int(value) & 0xFFFF)

    def _write_u32(self, offset: int, value: int) -> None:
        struct.pack_into("<I", self.data, offset, int(value) & 0xFFFFFFFF)

    @staticmethod
    def _bytes_to_hex(raw: bytes) -> str:
        return bytes(raw).hex(" ").upper()

    @staticmethod
    def _require_u32(value: int) -> int:
        ivalue = int(value)
        if not (0 <= ivalue <= 0xFFFFFFFF):
            raise ValueError("value must be in range 0..4294967295")
        return ivalue

    def saved_data_slice(self) -> Tuple[int, int]:
        start = self.layout.saved_data_offset
        if start != self.SAVED_DATA_START:
            # Enforce ground truth for PC v1.3
            start = self.SAVED_DATA_START
        end = len(self.data) - self.layout.md5_len
        if end <= start:
            raise ValueError("saved_data slice is invalid for this file")
        return start, end

    def saved_data_start(self) -> int:
        return self.saved_data_slice()[0]

    def saved_data(self) -> bytes:
        s, e = self.saved_data_slice()
        return bytes(self.data[s:e])

    def abs_to_rel(self, abs_off: int) -> int:
        return abs_off - self.saved_data_start()

    def tail_md5(self) -> bytes:
        return bytes(self.data[-self.layout.md5_len:])

    # --- hashing ---

    def md5_saved_data(self) -> bytes:
        return hashlib.md5(self.saved_data()).digest()

    def md5_all_minus_tail(self) -> bytes:
        if len(self.data) <= self.layout.md5_len:
            return b""
        return hashlib.md5(bytes(self.data[:-self.layout.md5_len])).digest()

    def detect_hash_scheme(self) -> HashScheme:
        if len(self.data) < self.layout.md5_len:
            return None
        tail = self.tail_md5()
        if self.md5_saved_data() == tail:
            return "md5_saved_data"
        if self.md5_all_minus_tail() == tail:
            return "md5_all_minus_tail"
        return None

    # --- CRCs ---

    def _bounded_slice(self, start: int, end: int) -> bytes:
        if start < 0:
            start = 0
        if end < 0:
            end = 0
        end = min(end, len(self.data))
        start = min(start, end)
        return bytes(self.data[start:end])

    def compute_crc_block1(self) -> int:
        a, b = self.layout.crc_block1_range
        return ea_crc32(self._bounded_slice(a, b))

    def compute_crc_data(self) -> int:
        return ea_crc32(self._bounded_slice(self.layout.crc_data_start, len(self.data)))

    def compute_crc_block2(self) -> int:
        a, b = self.layout.crc_block2_range
        return ea_crc32(self._bounded_slice(a, b))

    # --- scanning helpers ---

    def find_u32_in_saved_data(self, value: int, limit: Optional[int] = 5000) -> list[int]:
        needle = struct.pack("<I", int(value) & 0xFFFFFFFF)
        start, end = self.saved_data_slice()
        hay = self.data[start:end]
        res: list[int] = []
        i = 0
        while True:
            j = hay.find(needle, i)
            if j == -1:
                break
            res.append(start + j)
            i = j + 1
            if limit is not None and len(res) >= limit:
                break
        return res

    # --- economy / garage bounty ---

    def get_money(self) -> int:
        return self._read_u32(self.MONEY_OFFSET)

    def set_money(self, value: int) -> None:
        self._write_u32(self.MONEY_OFFSET, self._require_u32(value))

    @classmethod
    def _is_garage_slot(cls, raw: bytes) -> bool:
        return (
            len(raw) == cls.GARAGE_SLOT_SIZE
            and raw[1:4] == cls.GARAGE_SIGNATURE_A
            and raw[8:12] == cls.GARAGE_SIGNATURE_B
        )

    def get_pursuit_records(self) -> List[PursuitRecord]:
        slots: List[PursuitRecord] = []
        slot_index = 0
        base_off = self.GARAGE_BASE_OFFSET

        while base_off + self.GARAGE_SLOT_SIZE <= len(self.data):
            raw = bytes(self.data[base_off:base_off + self.GARAGE_SLOT_SIZE])
            if not self._is_garage_slot(raw):
                break
            slots.append(
                PursuitRecord(
                    career_slot=slot_index,
                    bounty=self._read_u32(base_off + self.GARAGE_BOUNTY_OFFSET),
                    escaped=self._read_u16(base_off + self.GARAGE_ESCAPED_OFFSET),
                    busted=self._read_u16(base_off + self.GARAGE_BUSTED_OFFSET),
                    abs_off=base_off,
                )
            )
            base_off += self.GARAGE_SLOT_SIZE
            slot_index += 1

        if not slots:
            raise ValueError("Failed to detect garage block")
        return slots

    def get_owned_car_records(self) -> List[OwnedCarRecord]:
        records: List[OwnedCarRecord] = []
        base_off = self.CAREER_VEHICLE_BASE_OFFSET

        while base_off + self.CAREER_VEHICLE_SIZE <= len(self.data):
            raw = bytes(self.data[base_off:base_off + self.CAREER_VEHICLE_SIZE])
            if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
                break

            car_number = self._read_u32(base_off)
            signature = bytes(
                self.data[
                    base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET:
                    base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE
                ]
            )
            career_slot = self._read_u8(base_off + self.CAREER_VEHICLE_SLOT_OFFSET)
            if (
                car_number != self.EMPTY_CAR_NUMBER
                and signature != (b"\x00" * self.CAREER_VEHICLE_SIGNATURE_SIZE)
            ):
                records.append(
                    OwnedCarRecord(
                        car_number=car_number,
                        signature=signature,
                        location_bits=self._read_u16(base_off + self.CAREER_VEHICLE_FLAGS_OFFSET),
                        misc_bits=self._read_u16(base_off + self.CAREER_VEHICLE_FLAGS2_OFFSET),
                        parts_slot=self._read_u8(base_off + self.CAREER_VEHICLE_PARTS_SLOT_OFFSET),
                        career_slot=career_slot,
                        abs_off=base_off,
                    )
                )

            base_off += self.CAREER_VEHICLE_SIZE

        return records

    def get_career_vehicle_records(self) -> List[CareerVehicleRecord]:
        return [
            CareerVehicleRecord(
                car_number=record.car_number,
                signature=record.signature,
                flags=record.location_bits,
                flags2=record.misc_bits,
                parts_slot=record.parts_slot,
                career_slot=record.career_slot,
                abs_off=record.abs_off,
            )
            for record in self.get_owned_car_records()
            if record.career_slot != self.EMPTY_CAREER_SLOT
        ]

    def get_my_cars_records(self) -> List[OwnedCarRecord]:
        return [
            record
            for record in self.get_owned_car_records()
            if record.location_bits == self.MY_CARS_FLAG
        ]

    @classmethod
    def derive_source_kind(cls, flags: Optional[int]) -> str:
        if flags is None:
            return "Unknown"
        if flags == cls.MY_CARS_FLAG:
            return "My Cars"
        if flags == cls.CAREER_FLAG:
            return "Career"
        if flags == (cls.CAREER_FLAG | cls.PINK_SLIP_FLAG):
            return "Pink Slip"
        return f"Unknown (0x{flags:02X})"

    def _owned_record_by_abs_off(
        self,
        abs_off: int,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        misc_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
    ) -> OwnedCarRecord:
        wanted = int(abs_off)
        for record in self.get_owned_car_records():
            if record.abs_off != wanted:
                continue
            return OwnedCarRecord(
                car_number=record.car_number,
                signature=record.signature,
                location_bits=(location_overrides or {}).get(record.abs_off, record.location_bits),
                misc_bits=(misc_overrides or {}).get(record.abs_off, record.misc_bits),
                parts_slot=record.parts_slot,
                career_slot=(career_slot_overrides or {}).get(record.abs_off, record.career_slot),
                abs_off=record.abs_off,
            )
        raise ValueError(f"Owned car record at 0x{wanted:05X} was not detected")

    def get_owned_car_slot_statuses(
        self,
        *,
        reserved_abs_offs: Optional[Set[int]] = None,
    ) -> List[OwnedCarSlotStatus]:
        reserved = {int(value) for value in (reserved_abs_offs or set())}
        statuses: List[OwnedCarSlotStatus] = []
        base_off = self.CAREER_VEHICLE_BASE_OFFSET
        slot_index = 0
        while base_off + self.CAREER_VEHICLE_SIZE <= len(self.data):
            raw = bytes(self.data[base_off:base_off + self.CAREER_VEHICLE_SIZE])
            if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
                break
            car_number = self._read_u32(base_off)
            signature = bytes(
                self.data[
                    base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET:
                    base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE
                ]
            )
            flags = self._read_u16(base_off + self.CAREER_VEHICLE_FLAGS_OFFSET)
            flags2 = self._read_u16(base_off + self.CAREER_VEHICLE_FLAGS2_OFFSET)
            parts_slot = self._read_u8(base_off + self.CAREER_VEHICLE_PARTS_SLOT_OFFSET)
            career_slot = self._read_u8(base_off + self.CAREER_VEHICLE_SLOT_OFFSET)
            occupied = car_number != self.EMPTY_CAR_NUMBER or signature != (b"\x00" * self.CAREER_VEHICLE_SIGNATURE_SIZE)
            reusable = (
                car_number == self.EMPTY_CAR_NUMBER
                and signature == (b"\x00" * self.CAREER_VEHICLE_SIGNATURE_SIZE)
                and career_slot == self.EMPTY_CAREER_SLOT
                and flags == 0
                and flags2 == 0
                and parts_slot == 0xFF
            )
            blocked_reason = None
            if not occupied and not reusable:
                blocked_reason = "Partially dirty empty owned-car slot"
            elif reusable and base_off in reserved:
                reusable = False
                blocked_reason = "Reserved by staged injector"
            statuses.append(
                OwnedCarSlotStatus(
                    slot_index=slot_index,
                    abs_off=base_off,
                    occupied=occupied,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    car_number=car_number,
                    location_bits=flags,
                    misc_bits=flags2,
                    parts_slot=parts_slot,
                    career_slot=career_slot,
                )
            )
            base_off += self.CAREER_VEHICLE_SIZE
            slot_index += 1
        return statuses

    def _parts_slot_numbers(self) -> range:
        count = (self.GARAGE_BASE_OFFSET - self.PARTS_BLOCK_BASE_OFFSET) // self.PARTS_BLOCK_SIZE
        return range(self.PARTS_BLOCK_SLOT_BASE, self.PARTS_BLOCK_SLOT_BASE + count)

    def _is_blank_parts_block(self, raw_block: bytes) -> bool:
        if len(raw_block) != self.PARTS_BLOCK_SIZE:
            return False
        return (
            raw_block[:self.PARTS_LEVELS_BASE_OFFSET - 2]
            == bytes([self.EMPTY_PARTS_BLOCK_HEAD_FILL]) * (self.PARTS_LEVELS_BASE_OFFSET - 2)
            and raw_block[self.PARTS_LEVELS_BASE_OFFSET - 2:self.PARTS_LEVELS_BASE_OFFSET] == self.CAREER_VEHICLE_SENTINEL
            and raw_block[self.PARTS_LEVELS_BASE_OFFSET:self.PARTS_CONFIRMED_SLICE_END]
            == b"\x00" * (self.PARTS_CONFIRMED_SLICE_END - self.PARTS_LEVELS_BASE_OFFSET)
            and raw_block[self.PARTS_CONFIRMED_SLICE_END:self.PARTS_MARKER_OFFSET]
            == b"\x00" * (self.PARTS_MARKER_OFFSET - self.PARTS_CONFIRMED_SLICE_END)
            and raw_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4] == self.EMPTY_PARTS_BLOCK_MARKER
        )

    def get_parts_slot_statuses(
        self,
        *,
        reserved_parts_slots: Optional[Set[int]] = None,
    ) -> List[PartsSlotStatus]:
        reserved = {int(value) for value in (reserved_parts_slots or set())}
        referenced_slots = {record.parts_slot for record in self.get_owned_car_records()}
        statuses: List[PartsSlotStatus] = []
        for slot in self._parts_slot_numbers():
            abs_off = self._parts_block_abs_off(slot)
            raw_block = bytes(self.data[abs_off:abs_off + self.PARTS_BLOCK_SIZE])
            marker = bytes(raw_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4])
            referenced = slot in referenced_slots
            reusable = False
            blocked_reason: Optional[str] = None
            if referenced:
                blocked_reason = "Referenced by owned-car record"
            elif slot in reserved:
                blocked_reason = "Reserved by staged injector"
            elif self._is_blank_parts_block(raw_block):
                reusable = True
            else:
                blocked_reason = "Non-empty parts block"
            statuses.append(
                PartsSlotStatus(
                    parts_slot=slot,
                    abs_off=abs_off,
                    referenced_by_owned_car=referenced,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    marker=marker,
                )
            )
        return statuses

    def get_career_slot_statuses(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
        reserved_slots: Optional[Set[int]] = None,
    ) -> List[CareerSlotStatus]:
        current_location = location_overrides or {}
        current_career_slot = career_slot_overrides or {}
        staged_cleared_slots = {int(slot) for slot in (cleared_slots or set())}
        reserved_career_slots = {int(slot) for slot in (reserved_slots or set())}
        linked_counts: Dict[int, int] = {}
        for record in self.get_owned_car_records():
            loc = current_location.get(record.abs_off, record.location_bits)
            slot = current_career_slot.get(record.abs_off, record.career_slot)
            if slot == self.EMPTY_CAREER_SLOT:
                continue
            if loc not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG):
                continue
            linked_counts[slot] = linked_counts.get(slot, 0) + 1

        statuses: List[CareerSlotStatus] = []
        for record in self.get_pursuit_records():
            linked = linked_counts.get(record.career_slot, 0)
            if record.career_slot in staged_cleared_slots:
                bounty = 0
                escaped = 0
                busted = 0
            else:
                bounty = record.bounty
                escaped = record.escaped
                busted = record.busted
            is_zero = (bounty, escaped, busted) == (0, 0, 0)
            reusable = linked == 0 and is_zero
            blocked_reason = None
            if record.career_slot in reserved_career_slots and reusable:
                reusable = False
                blocked_reason = "Reserved by staged injector"
            elif linked == 0 and not is_zero:
                blocked_reason = "Unlinked pursuit stats present"
            elif linked > 1:
                blocked_reason = f"Ambiguous: {linked} cars target this career slot"
            statuses.append(
                CareerSlotStatus(
                    career_slot=record.career_slot,
                    abs_off=record.abs_off,
                    linked_car_count=linked,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    bounty=bounty,
                    escaped=escaped,
                    busted=busted,
                    is_zero=is_zero,
                )
            )
        return statuses

    def get_garage_allocator_snapshot(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
        reserved_owned_abs_offs: Optional[Set[int]] = None,
        reserved_career_slots: Optional[Set[int]] = None,
    ) -> GarageAllocatorSnapshot:
        return GarageAllocatorSnapshot(
            owned_slots=tuple(self.get_owned_car_slot_statuses(reserved_abs_offs=reserved_owned_abs_offs)),
            career_slots=tuple(
                self.get_career_slot_statuses(
                    location_overrides=location_overrides,
                    career_slot_overrides=career_slot_overrides,
                    cleared_slots=cleared_slots,
                    reserved_slots=reserved_career_slots,
                )
            ),
        )

    def get_transfer_car_entries(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        misc_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
    ) -> List[ResolvedTransferCarEntry]:
        current_location = location_overrides or {}
        current_misc = misc_overrides or {}
        current_career_slot = career_slot_overrides or {}
        staged_cleared_slots = {int(slot) for slot in (cleared_slots or set())}
        pursuits = {record.career_slot: record for record in self.get_pursuit_records()}
        entries: List[ResolvedTransferCarEntry] = []
        for record in self.get_owned_car_records():
            location_bits = current_location.get(record.abs_off, record.location_bits)
            misc_bits = current_misc.get(record.abs_off, record.misc_bits)
            career_slot = current_career_slot.get(record.abs_off, record.career_slot)
            display_name = resolve_car_name(record.signature) or f"Sig {record.signature.hex().upper()}"
            pursuit = pursuits.get(career_slot) if career_slot != self.EMPTY_CAREER_SLOT else None
            if pursuit is not None and career_slot in staged_cleared_slots:
                pursuit = PursuitRecord(
                    career_slot=pursuit.career_slot,
                    bounty=0,
                    escaped=0,
                    busted=0,
                    abs_off=pursuit.abs_off,
                )
            is_career = location_bits == self.CAREER_FLAG and career_slot != self.EMPTY_CAREER_SLOT
            is_my_cars = location_bits == self.MY_CARS_FLAG and career_slot == self.EMPTY_CAREER_SLOT
            is_pink_slip = location_bits == (self.CAREER_FLAG | self.PINK_SLIP_FLAG) and career_slot != self.EMPTY_CAREER_SLOT
            entries.append(
                ResolvedTransferCarEntry(
                    abs_off=record.abs_off,
                    car_number=record.car_number,
                    signature=record.signature,
                    display_name=display_name,
                    source_kind=self.derive_source_kind(location_bits),
                    location_bits=location_bits,
                    misc_bits=misc_bits,
                    parts_slot=record.parts_slot,
                    career_slot=career_slot,
                    is_career=is_career,
                    is_my_cars=is_my_cars,
                    is_pink_slip=is_pink_slip,
                    has_pursuit_link=pursuit is not None,
                    bounty=(pursuit.bounty if pursuit is not None else None),
                    escaped=(pursuit.escaped if pursuit is not None else None),
                    busted=(pursuit.busted if pursuit is not None else None),
                    pursuit_abs_off=(pursuit.abs_off if pursuit is not None else None),
                )
            )
        return sorted(
            entries,
            key=lambda item: (
                0 if item.has_pursuit_link else 1,
                item.career_slot if item.career_slot != self.EMPTY_CAREER_SLOT else 999,
                item.display_name.lower(),
                item.car_number,
            ),
        )

    def set_owned_car_location(self, abs_off: int, location_bits: int, misc_bits: Optional[int] = None) -> None:
        record = self._owned_record_by_abs_off(abs_off)
        self._write_u16(record.abs_off + self.CAREER_VEHICLE_FLAGS_OFFSET, int(location_bits) & 0xFFFF)
        if misc_bits is None:
            misc_bits = record.misc_bits
        self._write_u16(record.abs_off + self.CAREER_VEHICLE_FLAGS2_OFFSET, int(misc_bits) & 0xFFFF)

    def set_owned_car_career_slot(self, abs_off: int, career_slot: int) -> None:
        record = self._owned_record_by_abs_off(abs_off)
        wanted = int(career_slot)
        if not (0 <= wanted <= 0xFF):
            raise ValueError("career_slot must be in range 0..255")
        self.data[record.abs_off + self.CAREER_VEHICLE_SLOT_OFFSET] = wanted & 0xFF

    def clear_owned_car_career_slot(self, abs_off: int) -> None:
        self.set_owned_car_career_slot(abs_off, self.EMPTY_CAREER_SLOT)

    def clear_pursuit_slot(self, career_slot: int) -> None:
        wanted = int(career_slot)
        for slot in self.get_pursuit_records():
            if slot.career_slot != wanted:
                continue
            self._write_u32(slot.abs_off + self.GARAGE_BOUNTY_OFFSET, 0)
            self._write_u16(slot.abs_off + self.GARAGE_ESCAPED_OFFSET, 0)
            self._write_u16(slot.abs_off + self.GARAGE_BUSTED_OFFSET, 0)
            return
        raise ValueError(f"Pursuit slot {wanted} was not detected")

    def plan_owned_car_transfer(
        self,
        abs_off: int,
        target_mode: str,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        misc_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
        reserved_career_slots: Optional[Set[int]] = None,
        desired_career_slot: Optional[int] = None,
    ) -> OwnedCarTransferPlan:
        source = self._owned_record_by_abs_off(
            abs_off,
            location_overrides=location_overrides,
            misc_overrides=misc_overrides,
            career_slot_overrides=career_slot_overrides,
        )
        display_name = resolve_car_name(source.signature) or f"Sig {source.signature.hex().upper()}"
        target = str(target_mode)
        target_misc = source.misc_bits
        target_owned_abs_off = source.abs_off
        target_career_slot: Optional[int] = None
        target_location_bits: Optional[int] = None
        cleared_source_career_slot: Optional[int] = None
        clears_pursuit_slot = False
        refusal: Optional[str] = None

        if target == "my_cars":
            if source.location_bits == self.MY_CARS_FLAG and source.career_slot == self.EMPTY_CAREER_SLOT:
                refusal = "Already in My Cars"
            elif source.location_bits not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG, self.MY_CARS_FLAG):
                refusal = f"Unsupported source flags 0x{source.location_bits:02X}"
            else:
                target_location_bits = self.MY_CARS_FLAG
                target_career_slot = None
                if source.career_slot != self.EMPTY_CAREER_SLOT:
                    cleared_source_career_slot = source.career_slot
                    clears_pursuit_slot = True
        elif target in ("career", "pink_slip"):
            if source.location_bits not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG, self.MY_CARS_FLAG):
                refusal = f"Unsupported source flags 0x{source.location_bits:02X}"
            elif target == "career" and source.location_bits == self.CAREER_FLAG and source.career_slot != self.EMPTY_CAREER_SLOT:
                refusal = "Already in Career"
            elif target == "pink_slip" and source.location_bits == (self.CAREER_FLAG | self.PINK_SLIP_FLAG) and source.career_slot != self.EMPTY_CAREER_SLOT:
                refusal = "Already marked Pink Slip"
            else:
                target_location_bits = self.CAREER_FLAG if target == "career" else (self.CAREER_FLAG | self.PINK_SLIP_FLAG)
                if source.location_bits == self.MY_CARS_FLAG or source.career_slot == self.EMPTY_CAREER_SLOT:
                    allocator = self.get_garage_allocator_snapshot(
                        location_overrides=location_overrides,
                        career_slot_overrides=career_slot_overrides,
                        cleared_slots=cleared_slots,
                        reserved_career_slots=reserved_career_slots,
                    )
                    reusable_slots = {slot.career_slot: slot for slot in allocator.reusable_career_slots}
                    if desired_career_slot is not None:
                        slot_status = reusable_slots.get(int(desired_career_slot))
                        if slot_status is None:
                            refusal = f"Career slot {int(desired_career_slot) + 1} is not a validated empty slot"
                        else:
                            target_career_slot = slot_status.career_slot
                    elif reusable_slots:
                        target_career_slot = sorted(reusable_slots)[0]
                    else:
                        refusal = "No validated empty career slots available"
                else:
                    target_career_slot = source.career_slot
        else:
            refusal = f"Unsupported transfer target: {target}"

        return OwnedCarTransferPlan(
            source_abs_off=source.abs_off,
            source_display_name=display_name,
            source_location_bits=source.location_bits,
            source_misc_bits=source.misc_bits,
            source_career_slot=source.career_slot,
            source_parts_slot=source.parts_slot,
            target_location_bits=(target_location_bits if target_location_bits is not None else source.location_bits),
            target_misc_bits=target_misc,
            target_career_slot=target_career_slot,
            cleared_source_career_slot=cleared_source_career_slot,
            clears_pursuit_slot=clears_pursuit_slot,
            target_owned_abs_off=target_owned_abs_off,
            requires_relocation=False,
            refusal_reason=refusal,
        )

    def transfer_owned_car(
        self,
        abs_off: int,
        target_mode: str,
        *,
        desired_career_slot: Optional[int] = None,
    ) -> OwnedCarTransferPlan:
        plan = self.plan_owned_car_transfer(abs_off, target_mode, desired_career_slot=desired_career_slot)
        if plan.refusal_reason:
            raise ValueError(plan.refusal_reason)
        if plan.clears_pursuit_slot and plan.cleared_source_career_slot is not None:
            self.clear_pursuit_slot(plan.cleared_source_career_slot)
        self.set_owned_car_location(plan.source_abs_off, plan.target_location_bits, plan.target_misc_bits)
        if plan.target_career_slot is None:
            self.clear_owned_car_career_slot(plan.source_abs_off)
        else:
            self.set_owned_car_career_slot(plan.source_abs_off, plan.target_career_slot)
        return plan

    _DEFAULT_SNAPSHOT_LIBRARY_DIR = Path.home() / "Desktop" / "unique_cars"

    @classmethod
    def default_snapshot_library_root(cls) -> Path:
        return cls._DEFAULT_SNAPSHOT_LIBRARY_DIR

    @staticmethod
    def _hex_to_bytes(hex_text: str) -> bytes:
        return bytes.fromhex(str(hex_text).replace("\n", " ").strip())

    @classmethod
    def load_snapshot_library(cls, root: str | Path | None = None) -> List[SnapshotLibraryEntry]:
        library_root = Path(root) if root is not None else cls.default_snapshot_library_root()
        if not library_root.exists():
            return []

        entries: List[SnapshotLibraryEntry] = []
        for path in sorted(library_root.rglob("boss_car_snapshot_*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("kind") != "boss_car_build_snapshot_v2":
                raise ValueError(f"{path} is not a boss_car_build_snapshot_v2 file")
            block = cls._hex_to_bytes(payload["primary_build_block"]["normalized_hex"])
            if len(block) != cls.PARTS_BLOCK_SIZE:
                raise ValueError(f"{path} has invalid normalized primary block size {len(block)}")
            template = payload["primary_owned_record_template"]
            signature = cls._hex_to_bytes(template["signature_hex"])
            if len(signature) != cls.CAREER_VEHICLE_SIGNATURE_SIZE:
                raise ValueError(f"{path} has invalid signature length {len(signature)}")
            relative_parent = path.parent.relative_to(library_root) if path.parent != library_root else Path(".")
            bucket = "Bonus" if "bonus_cars" in {part.lower() for part in relative_parent.parts} else "Main"
            performance = tuple(
                (str(name), int(value))
                for name, value in payload.get("primary_build_block", {}).get("performance_levels", {}).items()
            )
            visuals = tuple(
                (str(name), str(value))
                for name, value in payload.get("primary_build_block", {}).get("primary_visual_fields", {}).items()
            )
            entry = SnapshotLibraryEntry(
                snapshot_id=str(path.resolve()).lower(),
                json_path=path.resolve(),
                library_bucket=bucket,
                file_label=path.stem,
                display_name=str(payload.get("display_name") or path.stem),
                source_file=str(payload.get("source_file") or ""),
                source_kind=str(payload.get("source_kind") or "Unknown"),
                primary_owned_record_template=OwnedCarTemplate(
                    car_number=int(template["car_number"]),
                    signature=signature,
                    location_bits=int(template["location_bits"]),
                    misc_bits=int(template["misc_bits"]),
                    source_kind=str(template.get("source_kind") or payload.get("source_kind") or "Unknown"),
                ),
                normalized_primary_build_block=block,
                performance_levels=performance,
                primary_visual_fields=visuals,
                requires_unresolved_global_visual_state=bool(payload.get("requires_unresolved_global_visual_state")),
                has_visual_sidecar=payload.get("optional_visual_sidecar") is not None,
            )
            entries.append(entry)
        return sorted(entries, key=lambda item: (0 if item.library_bucket == "Main" else 1, item.display_name.lower(), item.file_label.lower()))

    def _write_owned_car_record(
        self,
        abs_off: int,
        *,
        car_number: int,
        signature: bytes,
        location_bits: int,
        misc_bits: int,
        parts_slot: int,
        career_slot: int,
    ) -> None:
        if len(signature) != self.CAREER_VEHICLE_SIGNATURE_SIZE:
            raise ValueError(f"owned-car signature must be {self.CAREER_VEHICLE_SIGNATURE_SIZE} bytes")
        payload = bytearray(self.CAREER_VEHICLE_SIZE)
        struct.pack_into("<I", payload, 0x00, int(car_number) & 0xFFFFFFFF)
        payload[self.CAREER_VEHICLE_SIGNATURE_OFFSET:self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE] = bytes(signature)
        struct.pack_into("<H", payload, self.CAREER_VEHICLE_FLAGS_OFFSET, int(location_bits) & 0xFFFF)
        struct.pack_into("<H", payload, self.CAREER_VEHICLE_FLAGS2_OFFSET, int(misc_bits) & 0xFFFF)
        payload[self.CAREER_VEHICLE_PARTS_SLOT_OFFSET] = int(parts_slot) & 0xFF
        payload[self.CAREER_VEHICLE_SLOT_OFFSET] = int(career_slot) & 0xFF
        payload[0x12:0x14] = self.CAREER_VEHICLE_SENTINEL
        self.data[abs_off:abs_off + self.CAREER_VEHICLE_SIZE] = payload

    def _allocate_injected_car_number(self) -> int:
        used = {
            int(record.car_number)
            for record in self.get_owned_car_records()
            if int(record.car_number) != self.EMPTY_CAR_NUMBER
        }
        if not used:
            return 1
        candidate = max(used) + 1
        while candidate in used:
            candidate += 1
        if candidate >= self.EMPTY_CAR_NUMBER:
            raise ValueError("No safe car_number values remain for snapshot injection")
        return candidate

    def _write_parts_block_for_slot(self, parts_slot: int, normalized_block: bytes) -> None:
        slot = int(parts_slot)
        if len(normalized_block) != self.PARTS_BLOCK_SIZE:
            raise ValueError(f"normalized parts block must be exactly 0x{self.PARTS_BLOCK_SIZE:X} bytes")
        abs_off = self._parts_block_abs_off(slot)
        payload = bytearray(normalized_block)
        payload[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4] = bytes((slot & 0xFF, 0xCD, 0xCD, 0xCD))
        self.data[abs_off:abs_off + self.PARTS_BLOCK_SIZE] = payload

    def plan_snapshot_injection(
        self,
        snapshot: SnapshotLibraryEntry,
        target_mode: str,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
        reserved_owned_abs_offs: Optional[Set[int]] = None,
        reserved_parts_slots: Optional[Set[int]] = None,
        reserved_career_slots: Optional[Set[int]] = None,
        desired_career_slot: Optional[int] = None,
    ) -> SnapshotInjectionPlan:
        target = str(target_mode)
        warnings: List[str] = []
        refusal: Optional[str] = None
        target_location_bits: Optional[int] = None
        target_career_slot: Optional[int] = None
        target_owned_abs_off: Optional[int] = None
        target_parts_slot: Optional[int] = None

        if snapshot.has_visual_sidecar:
            refusal = "Sidecar snapshots are not injectable yet"
        elif target not in ("my_cars", "career"):
            refusal = f"Unsupported injector target: {target}"
        else:
            target_location_bits = self.MY_CARS_FLAG if target == "my_cars" else self.CAREER_FLAG
            if snapshot.requires_unresolved_global_visual_state:
                warnings.append("Global visual table 0x5577 is not injected in v1.")

            owned_candidates = self.get_owned_car_slot_statuses(reserved_abs_offs=reserved_owned_abs_offs)
            reusable_owned = [slot for slot in owned_candidates if slot.reusable]
            if not reusable_owned:
                refusal = "No validated empty owned-car slots available"
            else:
                target_owned_abs_off = reusable_owned[0].abs_off

            if refusal is None:
                parts_candidates = self.get_parts_slot_statuses(reserved_parts_slots=reserved_parts_slots)
                reusable_parts = [slot for slot in parts_candidates if slot.reusable]
                if not reusable_parts:
                    refusal = "No validated empty parts slots available"
                else:
                    target_parts_slot = reusable_parts[0].parts_slot

            if refusal is None and target == "career":
                career_candidates = self.get_career_slot_statuses(
                    location_overrides=location_overrides,
                    career_slot_overrides=career_slot_overrides,
                    cleared_slots=cleared_slots,
                    reserved_slots=reserved_career_slots,
                )
                reusable_career = {slot.career_slot: slot for slot in career_candidates if slot.reusable}
                if desired_career_slot is not None:
                    wanted = int(desired_career_slot)
                    if wanted not in reusable_career:
                        refusal = f"Career slot {wanted + 1} is not a validated empty slot"
                    else:
                        target_career_slot = wanted
                elif reusable_career:
                    target_career_slot = sorted(reusable_career)[0]
                else:
                    refusal = "No validated empty career slots available"

        return SnapshotInjectionPlan(
            snapshot_id=snapshot.snapshot_id,
            display_name=snapshot.display_name,
            target_mode=target,
            target_location_bits=(target_location_bits if target_location_bits is not None else snapshot.primary_owned_record_template.location_bits),
            target_misc_bits=snapshot.primary_owned_record_template.misc_bits,
            target_owned_abs_off=target_owned_abs_off,
            target_parts_slot=target_parts_slot,
            target_career_slot=target_career_slot,
            refusal_reason=refusal,
            warnings=tuple(warnings),
        )

    def inject_snapshot(
        self,
        snapshot: SnapshotLibraryEntry,
        target_mode: str,
        *,
        desired_career_slot: Optional[int] = None,
    ) -> SnapshotInjectionPlan:
        plan = self.plan_snapshot_injection(snapshot, target_mode, desired_career_slot=desired_career_slot)
        if plan.refusal_reason:
            raise ValueError(plan.refusal_reason)
        if plan.target_owned_abs_off is None or plan.target_parts_slot is None:
            raise ValueError("Snapshot injector plan did not produce target owned/parts slots")
        if target_mode == "career":
            if plan.target_career_slot is None:
                raise ValueError("Career injection requires an allocated career slot")
            self.clear_pursuit_slot(plan.target_career_slot)
        self._write_parts_block_for_slot(plan.target_parts_slot, snapshot.normalized_primary_build_block)
        injected_car_number = self._allocate_injected_car_number()
        self._write_owned_car_record(
            plan.target_owned_abs_off,
            car_number=injected_car_number,
            signature=snapshot.primary_owned_record_template.signature,
            location_bits=plan.target_location_bits,
            misc_bits=plan.target_misc_bits,
            parts_slot=plan.target_parts_slot,
            career_slot=(plan.target_career_slot if plan.target_career_slot is not None else self.EMPTY_CAREER_SLOT),
        )
        return plan

    def get_garage_slots(self) -> List[ResolvedGarageEntry]:
        pursuits = self.get_pursuit_records()
        car_records_by_slot: Dict[int, List[CareerVehicleRecord]] = {}
        for record in self.get_career_vehicle_records():
            car_records_by_slot.setdefault(record.career_slot, []).append(record)

        resolved: List[ResolvedGarageEntry] = []
        for pursuit in pursuits:
            matches = car_records_by_slot.get(pursuit.career_slot, [])
            match = matches[0] if len(matches) == 1 else None
            occupied = bool(matches) or any((pursuit.bounty, pursuit.escaped, pursuit.busted))

            if match is not None:
                display_name = resolve_car_name(match.signature) or f"Sig {match.signature.hex().upper()}"
                car_number = match.car_number
                signature = match.signature
                flags = match.flags
                flags2 = match.flags2
                parts_slot = match.parts_slot
                car_abs_off = match.abs_off
            elif len(matches) > 1:
                display_name = f"Ambiguous vehicle ({len(matches)})"
                car_number = None
                signature = None
                flags = None
                flags2 = None
                parts_slot = None
                car_abs_off = None
                occupied = True
            else:
                display_name = "Empty" if not occupied else "Unlinked vehicle"
                car_number = None
                signature = None
                flags = None
                flags2 = None
                parts_slot = None
                car_abs_off = None

            resolved.append(
                ResolvedGarageEntry(
                    career_slot=pursuit.career_slot,
                    car_number=car_number,
                    signature=signature,
                    display_name=display_name,
                    source_kind=self.derive_source_kind(flags),
                    occupied=occupied,
                    bounty=pursuit.bounty,
                    escaped=pursuit.escaped,
                    busted=pursuit.busted,
                    flags=flags,
                    flags2=flags2,
                    parts_slot=parts_slot,
                    match_count=len(matches),
                    pursuit_abs_off=pursuit.abs_off,
                    car_abs_off=car_abs_off,
                )
            )

        return sorted(resolved, key=lambda item: item.career_slot)

    def get_parts_record(self, parts_slot: int) -> PartsRecord:
        slot = int(parts_slot)
        if slot < self.PARTS_BLOCK_SLOT_BASE:
            raise ValueError(f"parts_slot must be >= {self.PARTS_BLOCK_SLOT_BASE}")
        abs_off = self._parts_block_abs_off(slot)
        marker = self._parts_block_marker(slot)
        confirmed_raw = bytes(
            self.data[
                abs_off + self.PARTS_LEVELS_BASE_OFFSET:
                abs_off + self.PARTS_CONFIRMED_SLICE_END
            ]
        )
        junkman_mask = self._read_u32(abs_off + self.PARTS_JUNKMAN_MASK_OFFSET)
        return PartsRecord(
            parts_slot=slot,
            block_abs_off=abs_off,
            confirmed_raw=confirmed_raw,
            marker=marker,
            tires=self._read_u32(abs_off + self.PARTS_TIRES_OFFSET),
            brakes=self._read_u32(abs_off + self.PARTS_BRAKES_OFFSET),
            suspension=self._read_u32(abs_off + self.PARTS_SUSPENSION_OFFSET),
            transmission=self._read_u32(abs_off + self.PARTS_TRANSMISSION_OFFSET),
            engine=self._read_u32(abs_off + self.PARTS_ENGINE_OFFSET),
            turbo=self._read_u32(abs_off + self.PARTS_TURBO_OFFSET),
            nos=self._read_u32(abs_off + self.PARTS_NOS_OFFSET),
            junkman_mask=junkman_mask,
            junkman_categories=tuple(
                name for bit, name in self.JUNKMAN_MASK_BITS if junkman_mask & bit
            ),
        )

    def _parts_block_abs_off(self, parts_slot: int) -> int:
        slot = int(parts_slot)
        abs_off = self.PARTS_BLOCK_BASE_OFFSET + (slot - self.PARTS_BLOCK_SLOT_BASE) * self.PARTS_BLOCK_SIZE
        end = abs_off + self.PARTS_BLOCK_SIZE
        if end > len(self.data):
            raise ValueError(f"Parts slot {slot} points outside the file")
        return abs_off

    def _parts_block_marker(self, parts_slot: int, allow_placeholder_marker: bool = False) -> bytes:
        slot = int(parts_slot)
        abs_off = self._parts_block_abs_off(slot)
        marker_off = abs_off + self.PARTS_MARKER_OFFSET
        marker = bytes(self.data[marker_off:marker_off + 4])
        expected_marker = bytes((slot & 0xFF, 0xCD, 0xCD, 0xCD))
        placeholder_marker = bytes((0xFF, 0xCD, 0xCD, 0xCD))
        if marker != expected_marker and not (allow_placeholder_marker and marker == placeholder_marker):
            raise ValueError(
                f"Parts slot {slot} has unexpected marker {marker.hex(' ').upper()} at 0x{marker_off:05X}"
            )
        return marker

    def _read_parts_block_bytes(self, parts_slot: int, allow_placeholder_marker: bool = False) -> bytes:
        slot = int(parts_slot)
        abs_off = self._parts_block_abs_off(slot)
        self._parts_block_marker(slot, allow_placeholder_marker=allow_placeholder_marker)
        return bytes(self.data[abs_off:abs_off + self.PARTS_BLOCK_SIZE])

    def _normalize_parts_block(self, raw_block: bytes) -> bytes:
        normalized = bytearray(raw_block)
        normalized[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4] = b"\x00\x00\x00\x00"
        return bytes(normalized)

    def _visual_table_values(self) -> Tuple[int, ...]:
        values: List[int] = []
        start = self.VISUAL_TABLE_BASE_OFFSET
        for idx in range(self.VISUAL_TABLE_ENTRY_COUNT):
            off = start + idx * self.VISUAL_TABLE_ENTRY_STRIDE
            if off >= len(self.data):
                break
            values.append(self._read_u8(off))
        return tuple(values)

    @staticmethod
    def _uniform_value(values: Tuple[int, ...]) -> Optional[int]:
        if not values:
            return None
        first = values[0]
        return first if all(value == first for value in values) else None

    def _primary_visual_summary(self, raw_block: bytes) -> Tuple[Tuple[str, str], ...]:
        summary: List[Tuple[str, str]] = []
        for label, rel_off, size in self.PRIMARY_VISUAL_FIELDS:
            value = self._bytes_to_hex(raw_block[rel_off:rel_off + size])
            summary.append((label, value))
        return tuple(summary)

    def _read_owned_record_raw(self, abs_off: int) -> bytes:
        if abs_off < 0 or abs_off + self.CAREER_VEHICLE_SIZE > len(self.data):
            raise ValueError(f"Owned-car record at 0x{abs_off:05X} is out of bounds")
        raw = bytes(self.data[abs_off:abs_off + self.CAREER_VEHICLE_SIZE])
        if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
            raise ValueError(f"Owned-car record at 0x{abs_off:05X} has no CD CD sentinel")
        return raw

    def _detect_visual_sidecar(self, record: OwnedCarRecord) -> Optional[VisualSidecarTemplate]:
        next_off = record.abs_off + self.CAREER_VEHICLE_SIZE
        try:
            raw = self._read_owned_record_raw(next_off)
        except ValueError:
            return None
        car_number = struct.unpack_from("<I", raw, 0)[0]
        signature = raw[self.CAREER_VEHICLE_SIGNATURE_OFFSET:self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE]
        location_bits = struct.unpack_from("<H", raw, self.CAREER_VEHICLE_FLAGS_OFFSET)[0]
        misc_bits = struct.unpack_from("<H", raw, self.CAREER_VEHICLE_FLAGS2_OFFSET)[0]
        parts_slot = raw[self.CAREER_VEHICLE_PARTS_SLOT_OFFSET]
        career_slot = raw[self.CAREER_VEHICLE_SLOT_OFFSET]
        if car_number != self.EMPTY_CAR_NUMBER:
            return None
        if signature != record.signature:
            return None
        if location_bits != self.MY_CARS_FLAG or career_slot != self.EMPTY_CAREER_SLOT:
            return None
        if parts_slot != record.parts_slot + 1:
            return None
        raw_block = self._read_parts_block_bytes(parts_slot, allow_placeholder_marker=True)
        return VisualSidecarTemplate(
            owned_record_abs_off=next_off,
            owned_record_signature_clone=bytes(signature),
            owned_record_location_bits=location_bits,
            owned_record_misc_bits=misc_bits,
            sidecar_parts_slot_offset=1,
            sidecar_parts_slot=parts_slot,
            sidecar_block_abs_off=self._parts_block_abs_off(parts_slot),
            owned_record_raw=raw,
            sidecar_build_block=raw_block,
            normalized_sidecar_build_block=self._normalize_parts_block(raw_block),
        )

    def extract_full_car_build_snapshot(self, abs_off: int) -> FullCarBuildSnapshot:
        record = self._owned_record_by_abs_off(abs_off)
        parts = self.get_parts_record(record.parts_slot)
        primary_block = self._read_parts_block_bytes(record.parts_slot)
        visual_table_values = self._visual_table_values()
        performance_levels = tuple(
            (
                name,
                value,
            )
            for name, value in (
                ("Tires", parts.tires),
                ("Brakes", parts.brakes),
                ("Suspension", parts.suspension),
                ("Transmission", parts.transmission),
                ("Engine", parts.engine),
                ("Turbo", parts.turbo),
                ("NOS", parts.nos),
            )
        )
        return FullCarBuildSnapshot(
            car_abs_off=record.abs_off,
            display_name=resolve_car_name(record.signature) or f"Sig {record.signature.hex().upper()}",
            source_kind=self.derive_source_kind(record.location_bits),
            car_number=record.car_number,
            signature=record.signature,
            location_bits=record.location_bits,
            misc_bits=record.misc_bits,
            parts_slot=record.parts_slot,
            career_slot=record.career_slot,
            primary_owned_record_template=OwnedCarTemplate(
                car_number=record.car_number,
                signature=record.signature,
                location_bits=record.location_bits,
                misc_bits=record.misc_bits,
                source_kind=self.derive_source_kind(record.location_bits),
            ),
            primary_build_block_abs_off=parts.block_abs_off,
            primary_build_block=primary_block,
            normalized_primary_build_block=self._normalize_parts_block(primary_block),
            performance_levels=performance_levels,
            primary_visual_fields=self._primary_visual_summary(primary_block),
            optional_visual_sidecar=self._detect_visual_sidecar(record),
            requires_unresolved_global_visual_state=any(
                value != self.VISUAL_TABLE_DEFAULT_VALUE for value in visual_table_values
            ),
            global_visual_table_values=visual_table_values,
            global_visual_table_uniform_value=self._uniform_value(visual_table_values),
        )

    def get_full_car_build_snapshots(self) -> List[FullCarBuildSnapshot]:
        snapshots = [
            self.extract_full_car_build_snapshot(record.abs_off)
            for record in self.get_owned_car_records()
        ]
        return sorted(snapshots, key=lambda item: item.car_number)

    def snapshot_to_dict(self, snapshot: FullCarBuildSnapshot) -> Dict[str, object]:
        sidecar = snapshot.optional_visual_sidecar
        return {
            "kind": "boss_car_build_snapshot_v2",
            "source_file": str(self.path),
            "display_name": snapshot.display_name,
            "source_kind": snapshot.source_kind,
            "car_number": snapshot.car_number,
            "signature_hex": self._bytes_to_hex(snapshot.signature),
            "location_bits": snapshot.location_bits,
            "misc_bits": snapshot.misc_bits,
            "parts_slot": snapshot.parts_slot,
            "career_slot": snapshot.career_slot,
            "primary_owned_record_template": {
                "car_number": snapshot.primary_owned_record_template.car_number,
                "signature_hex": self._bytes_to_hex(snapshot.primary_owned_record_template.signature),
                "location_bits": snapshot.primary_owned_record_template.location_bits,
                "misc_bits": snapshot.primary_owned_record_template.misc_bits,
                "source_kind": snapshot.primary_owned_record_template.source_kind,
                "parts_slot_placeholder": True,
                "career_slot_placeholder": True,
            },
            "primary_build_block": {
                "abs_off": snapshot.primary_build_block_abs_off,
                "normalized_hex": self._bytes_to_hex(snapshot.normalized_primary_build_block),
                "marker_hex": self._bytes_to_hex(snapshot.primary_build_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4]),
                "performance_levels": {name: int(value) for name, value in snapshot.performance_levels},
                "primary_visual_fields": {name: value for name, value in snapshot.primary_visual_fields},
            },
            "optional_visual_sidecar": None if sidecar is None else {
                "owned_record_abs_off": sidecar.owned_record_abs_off,
                "owned_record_signature_clone_hex": self._bytes_to_hex(sidecar.owned_record_signature_clone),
                "owned_record_location_bits": sidecar.owned_record_location_bits,
                "owned_record_misc_bits": sidecar.owned_record_misc_bits,
                "sidecar_parts_slot_offset": sidecar.sidecar_parts_slot_offset,
                "sidecar_parts_slot": sidecar.sidecar_parts_slot,
                "sidecar_block_abs_off": sidecar.sidecar_block_abs_off,
                "normalized_sidecar_build_block_hex": self._bytes_to_hex(sidecar.normalized_sidecar_build_block),
                "sidecar_marker_hex": self._bytes_to_hex(
                    sidecar.sidecar_build_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4]
                ),
            },
            "requires_unresolved_global_visual_state": snapshot.requires_unresolved_global_visual_state,
            "global_visual_table": {
                "base_offset": self.VISUAL_TABLE_BASE_OFFSET,
                "entry_count": len(snapshot.global_visual_table_values),
                "stride": self.VISUAL_TABLE_ENTRY_STRIDE,
                "default_value": self.VISUAL_TABLE_DEFAULT_VALUE,
                "uniform_value": snapshot.global_visual_table_uniform_value,
                "unique_values": sorted(set(int(value) for value in snapshot.global_visual_table_values)),
                "values_hex": " ".join(f"{value:02X}" for value in snapshot.global_visual_table_values),
            },
        }

    def get_resolved_parts_entries(self) -> List[ResolvedPartsEntry]:
        entries: List[ResolvedPartsEntry] = []
        for slot in self.get_garage_slots():
            if slot.parts_slot is None or slot.car_abs_off is None:
                continue
            record = self.get_parts_record(slot.parts_slot)
            entries.append(
                ResolvedPartsEntry(
                    career_slot=slot.career_slot,
                    display_name=slot.display_name,
                    source_kind=slot.source_kind,
                    parts_slot=slot.parts_slot,
                    block_abs_off=record.block_abs_off,
                    marker=record.marker,
                    confirmed_raw=record.confirmed_raw,
                    tires=record.tires,
                    brakes=record.brakes,
                    suspension=record.suspension,
                    transmission=record.transmission,
                    engine=record.engine,
                    turbo=record.turbo,
                    nos=record.nos,
                    junkman_mask=record.junkman_mask,
                    junkman_categories=record.junkman_categories,
                    flags=slot.flags,
                    flags2=slot.flags2,
                    car_abs_off=slot.car_abs_off,
                )
            )
        return sorted(entries, key=lambda item: item.career_slot)

    def _parts_entry_for_career_slot(self, career_slot: int) -> ResolvedPartsEntry:
        wanted = int(career_slot)
        for entry in self.get_resolved_parts_entries():
            if entry.career_slot == wanted:
                return entry
        raise ValueError(f"Career slot {wanted} does not map to a resolved parts entry")

    def set_part_level(self, career_slot: int, part_name: str, level: int) -> None:
        entry = self._parts_entry_for_career_slot(career_slot)
        self.set_part_level_for_parts_slot(entry.parts_slot, part_name, level, model_name=entry.display_name)

    def set_part_level_for_parts_slot(
        self,
        parts_slot: int,
        part_name: str,
        level: int,
        model_name: Optional[str] = None,
    ) -> None:
        record = self.get_parts_record(parts_slot)
        offset = self.PART_LEVEL_OFFSETS.get(str(part_name))
        if offset is None:
            raise ValueError(f"Unsupported part name: {part_name}")

        wanted = int(level)
        if model_name is not None:
            limits = get_model_tuning_limits(model_name)
            if limits is None:
                raise ValueError(f"No confirmed tuning caps for {model_name}")
            cap = int(limits.get(str(part_name), 0))
            wanted = max(0, min(wanted, cap))
        elif wanted < 0:
            raise ValueError("part level must be >= 0")
        self._write_u32(record.block_abs_off + offset, wanted)

    def set_junkman_mask(self, career_slot: int, mask: int) -> None:
        entry = self._parts_entry_for_career_slot(career_slot)
        self.set_junkman_mask_for_parts_slot(entry.parts_slot, mask)

    def set_junkman_mask_for_parts_slot(self, parts_slot: int, mask: int) -> None:
        record = self.get_parts_record(parts_slot)
        wanted = int(mask)
        if not (0 <= wanted <= 0x7F):
            raise ValueError("junkman mask must be in range 0x00..0x7F")

        turbo_bit = next((bit for bit, name in self.JUNKMAN_MASK_BITS if name == "Turbo"), 0)
        nos_bit = next((bit for bit, name in self.JUNKMAN_MASK_BITS if name == "NOS"), 0)
        if turbo_bit and (wanted & turbo_bit) and record.turbo <= 0:
            raise ValueError("Junkman Turbo requires regular Turbo > 0")
        if nos_bit and (wanted & nos_bit) and record.nos <= 0:
            raise ValueError("Junkman NOS requires regular NOS > 0")

        self._write_u32(record.block_abs_off + self.PARTS_JUNKMAN_MASK_OFFSET, wanted)

    def set_junkman_enabled(self, career_slot: int, category: str, enabled: bool) -> None:
        entry = self._parts_entry_for_career_slot(career_slot)
        bit = next((bit for bit, name in self.JUNKMAN_MASK_BITS if name == str(category)), None)
        if bit is None:
            raise ValueError(f"Unsupported Junkman category: {category}")
        new_mask = entry.junkman_mask | bit if enabled else entry.junkman_mask & ~bit
        self.set_junkman_mask(career_slot, new_mask)

    def get_my_cars_parts_entries(self) -> List[ResolvedMyCarsEntry]:
        entries: List[ResolvedMyCarsEntry] = []
        for record in self.get_my_cars_records():
            parts = self.get_parts_record(record.parts_slot)
            entries.append(
                ResolvedMyCarsEntry(
                    car_number=record.car_number,
                    signature=record.signature,
                    resolved_model_name=resolve_car_name(record.signature) or f"Sig {record.signature.hex().upper()}",
                    location_bits=record.location_bits,
                    misc_bits=record.misc_bits,
                    parts_slot=record.parts_slot,
                    career_slot=record.career_slot,
                    block_abs_off=parts.block_abs_off,
                    tires=parts.tires,
                    brakes=parts.brakes,
                    suspension=parts.suspension,
                    transmission=parts.transmission,
                    engine=parts.engine,
                    turbo=parts.turbo,
                    nos=parts.nos,
                    junkman_mask=parts.junkman_mask,
                    junkman_categories=parts.junkman_categories,
                    car_abs_off=record.abs_off,
                )
            )
        return sorted(entries, key=lambda item: item.car_number)

    def set_slot_bounty(self, slot_index: int, value: int) -> None:
        wanted = int(slot_index)
        bounty = self._require_u32(value)
        for slot in self.get_pursuit_records():
            if slot.career_slot == wanted:
                self._write_u32(slot.abs_off + self.GARAGE_BOUNTY_OFFSET, bounty)
                return
        raise ValueError(f"Garage slot {wanted} was not detected")

    def set_slot_pink_slip(self, slot_index: int, enabled: bool) -> None:
        wanted = int(slot_index)
        matches = [record for record in self.get_career_vehicle_records() if record.career_slot == wanted]
        if len(matches) != 1:
            raise ValueError(f"Garage slot {wanted} does not map to a unique career vehicle")

        record = matches[0]
        if record.flags not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG):
            raise ValueError(f"Garage slot {wanted} has unsupported flags 0x{record.flags:02X}")

        new_flags = (record.flags | self.PINK_SLIP_FLAG) if enabled else (record.flags & ~self.PINK_SLIP_FLAG)
        self._write_u16(record.abs_off + self.CAREER_VEHICLE_FLAGS_OFFSET, new_flags)

    def get_total_bounty(self) -> int:
        return sum(slot.bounty for slot in self.get_garage_slots())

    def get_escape_bust_totals(self) -> Tuple[int, int]:
        slots = self.get_garage_slots()
        return (
            sum(slot.escaped for slot in slots),
            sum(slot.busted for slot in slots),
        )

    # --- integrity ---

    def validate_integrity(self) -> IntegrityStatus:
        scheme = self.hash_scheme or self.detect_hash_scheme()
        stored_md5 = self.tail_md5()
        computed_md5: Optional[bytes] = None
        md5_ok: Optional[bool] = None
        if scheme == "md5_saved_data":
            computed_md5 = self.md5_saved_data()
            md5_ok = stored_md5 == computed_md5
        elif scheme == "md5_all_minus_tail":
            computed_md5 = self.md5_all_minus_tail()
            md5_ok = stored_md5 == computed_md5

        stored_size = self._read_u32(self.layout.file_size_offset) if len(self.data) >= self.layout.file_size_offset + 4 else 0
        file_size_ok = stored_size == len(self.data)

        c1_stored = self._read_u32(self.layout.crc_block1_offset) if len(self.data) >= self.layout.crc_block1_offset + 4 else 0
        c_data_stored = self._read_u32(self.layout.crc_data_offset) if len(self.data) >= self.layout.crc_data_offset + 4 else 0
        c2_stored = self._read_u32(self.layout.crc_block2_offset) if len(self.data) >= self.layout.crc_block2_offset + 4 else 0

        c1_cmp = self.compute_crc_block1()
        cdata_cmp = self.compute_crc_data()
        c2_cmp = self.compute_crc_block2()

        return IntegrityStatus(
            hash_scheme=scheme,
            md5_ok=md5_ok,
            crc_block1_ok=(c1_stored == c1_cmp),
            crc_data_ok=(c_data_stored == cdata_cmp),
            crc_block2_ok=(c2_stored == c2_cmp),
            file_size_ok=file_size_ok,
            stored_size=stored_size,
            actual_size=len(self.data),
            stored_md5=stored_md5,
            computed_md5=computed_md5,
            crc_details={
                "block1": (c1_stored, c1_cmp),
                "data": (c_data_stored, cdata_cmp),
                "block2": (c2_stored, c2_cmp),
            },
        )

    def fix_integrity(self, force_scheme: HashScheme = None) -> IntegrityStatus:
        # keep header length field in sync
        self._write_u32(self.layout.file_size_offset, len(self.data))

        scheme = force_scheme or self.hash_scheme or self.detect_hash_scheme() or "md5_saved_data"
        if scheme == "md5_all_minus_tail":
            digest = self.md5_all_minus_tail()
        else:
            digest = self.md5_saved_data()
            scheme = "md5_saved_data"
        self.data[-self.layout.md5_len:] = digest
        self.hash_scheme = scheme

        # CRC order is important: block1/data first, then block2 which covers header CRCs
        c1 = self.compute_crc_block1()
        c_data = self.compute_crc_data()
        self._write_u32(self.layout.crc_block1_offset, c1)
        self._write_u32(self.layout.crc_data_offset, c_data)
        c2 = self.compute_crc_block2()
        self._write_u32(self.layout.crc_block2_offset, c2)

        return self.validate_integrity()

    # --- junkman inventory slots (saved_data-relative array) ---

    def read_slot(self, abs_off: int) -> Tuple[int, int, bytes]:
        raw = bytes(self.data[abs_off:abs_off + self.SLOT_SIZE])
        if len(raw) != self.SLOT_SIZE:
            raise IndexError("Slot read out of bounds")
        type_id = raw[self.SLOT_TYPE_OFF]
        count = raw[self.SLOT_COUNT_OFF]
        return type_id, count, raw

    @staticmethod
    def is_empty_slot(raw12: bytes) -> bool:
        return len(raw12) >= 9 and raw12[0] == 0 and raw12[8] == 0

    @staticmethod
    def is_clean_empty(raw12: bytes) -> bool:
        return len(raw12) == 12 and all(b == 0 for b in raw12)

    @staticmethod
    def is_clean_filled(raw12: bytes) -> bool:
        if len(raw12) != 12:
            return False
        type_id = raw12[0]
        if not (1 <= type_id <= 64):
            return False
        if raw12[8] != 1:
            return False
        return all(b == 0 for b in raw12[1:8]) and all(b == 0 for b in raw12[9:12])

    def write_token_into_slot(self, abs_off: int, type_id: int, count: int = 1) -> None:
        if not (0 <= type_id <= 0xFF) or not (0 <= count <= 0xFF):
            raise ValueError("type_id/count must be u8")
        payload = bytearray(self.SLOT_SIZE)
        payload[self.SLOT_TYPE_OFF] = type_id
        payload[self.SLOT_COUNT_OFF] = count
        self.data[abs_off:abs_off + self.SLOT_SIZE] = payload

    def clear_slot(self, abs_off: int) -> None:
        self.data[abs_off:abs_off + self.SLOT_SIZE] = b"\x00" * self.SLOT_SIZE

    def locate_junkman_base(self, max_slots: int = 80) -> Optional[int]:
        """Return detected junkman base (saved_data-relative)."""
        return self.junkman.base_rel

    def locate_junkman_base_from_diff(
        self, save_a: str | Path, save_b: str | Path, max_slots: int = 80
    ) -> Tuple[Optional[int], List[Tuple[int, bytes, bytes]], Tuple[int, int, int]]:
        """
        Deterministic locator from two saves:
        Finds offsets where block A matches [type,0..0,1,0,0,0] (type 1..64) and B has 12x00.
        Returns (base_rel, hit_details[(off, block_a, block_b)], (score_total, covered_hits, clean_filled)).
        """
        a = SaveFile.load(save_a)
        b = SaveFile.load(save_b)
        a_start, a_end = a.saved_data_slice()
        b_start, b_end = b.saved_data_slice()
        if (a_end - a_start) != (b_end - b_start):
            raise ValueError("Saved data size mismatch between A and B")
        sa = a.saved_data()
        sb = b.saved_data()
        hits: List[Tuple[int, bytes, bytes]] = []
        for off in range(0, len(sa) - self.SLOT_SIZE + 1):
            block_a = sa[off: off + self.SLOT_SIZE]
            block_b = sb[off: off + self.SLOT_SIZE]
            if not self.is_clean_filled(block_a):
                continue
            if not self.is_clean_empty(block_b):
                continue
            hits.append((off, block_a, block_b))
        if not hits:
            return None, [], (0, 0)

        def score_base(base_rel: int) -> Optional[Tuple[int, int, int, int]]:
            if base_rel < 0:
                return None
            clean_empty = 0
            clean_filled = 0
            filled = 0
            covered_hits = 0
            start = a_start
            end = a_end
            for idx in range(min(max_slots, self.SLOT_MAX)):
                abs_off = start + base_rel + idx * self.SLOT_STRIDE
                if abs_off + self.SLOT_SIZE > end:
                    break
                raw = sa[abs_off - start: abs_off - start + self.SLOT_SIZE]
                if self.is_clean_empty(raw):
                    clean_empty += 1
                elif self.is_clean_filled(raw):
                    clean_filled += 1
                    filled += 1
                else:
                    break
            for h, _, _ in hits:
                if h < base_rel:
                    continue
                if (h - base_rel) % self.SLOT_STRIDE == 0:
                    covered_hits += 1
            if filled == 0:
                return None
            if covered_hits == 0:
                return None
            score_total = clean_empty + clean_filled
            return (score_total, covered_hits, clean_filled, -base_rel)

        best: Optional[Tuple[int, int, int, int]] = None
        best_base: Optional[int] = None
        best_counts: Tuple[int, int, int] = (0, 0, 0)
        for h, _, _ in hits:
            for k in range(0, 201):
                cand = h - k * self.SLOT_STRIDE
                sc = score_base(cand)
                if sc is None:
                    continue
                if best is None or sc > best:
                    best = sc
                    best_base = cand
                    best_counts = (sc[0], sc[1], sc[2])  # total, covered_hits, clean_filled
        if best_base is None:
            return None, hits, (0, 0, 0)
        self._junk_base_cache = best_base
        return best_base, hits, best_counts

    def read_slots(self, max_slots: int = 20) -> List[Tuple[int, int, int, int, int, bytes]]:
        """
        Return (index, rel_offset, abs_offset, type_id, count, raw12) for slots within saved_data.
        """
        slots: List[Tuple[int, int, int, int, int, bytes]] = []
        start, _ = self.saved_data_slice()
        max_slots = min(max_slots, self.junkman.slot_count)
        for slot in self.junkman.read_slots()[:max_slots]:
            rel = slot.abs_off - start
            slots.append((slot.index, rel, slot.abs_off, slot.type_id, slot.count, slot.raw))
        return slots

    # Junkman convenience wrappers for UI
    def get_junkman_counts(self) -> Dict[int, int]:
        return self.junkman.get_counts()

    def set_junkman_count(self, type_id: int, count: int, clamp_max: int = 63) -> None:
        self.junkman.apply_counts({type_id: count}, clamp_max=clamp_max)

    def set_junkman_counts(self, mapping: Dict[int, int], clamp_max: int = 63) -> None:
        self.junkman.apply_counts(mapping, clamp_max=clamp_max)

    # --- persistence ---

    def backup_path(self) -> Path:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.path.with_suffix(self.path.suffix + f".bak_{ts}")

    def write_backup(self) -> Path:
        bp = self.backup_path()
        bp.write_bytes(bytes(self.data))
        return bp

    def save(self, out_path: str | Path | None = None, make_backup: bool = True) -> Path:
        if make_backup:
            try:
                original_bytes = self.path.read_bytes()
                self.backup_path().write_bytes(original_bytes)
            except Exception:
                logger.warning("Could not read original file for backup, using in-memory buffer", exc_info=True)
                self.write_backup()

        self.fix_integrity()
        dest = Path(out_path) if out_path is not None else self.path
        dest.write_bytes(bytes(self.data))
        return dest
