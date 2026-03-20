from __future__ import annotations

import datetime
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from core.cars import resolve_car_name
from core.checksums import ea_crc32
from core.junkman import JunkmanInventory
from core.tuning_limits import get_model_tuning_limits

HashScheme = Optional[Literal["md5_saved_data", "md5_all_minus_tail"]]


@dataclass(frozen=True)
class SaveLayout:
    saved_data_offset: int = 0x34
    md5_len: int = 16
    file_size_offset: int = 0x04
    crc_block1_offset: int = 0x10
    crc_data_offset: int = 0x14
    crc_block2_offset: int = 0x18
    crc_block1_range: Tuple[int, int] = (0x1C, 0x24)
    crc_data_start: int = 0x24
    crc_block2_range: Tuple[int, int] = (0x00, 0x18)
    magic: bytes = b"MC02"
    header_len: int = 0x34


@dataclass
class IntegrityStatus:
    hash_scheme: HashScheme
    md5_ok: Optional[bool]
    crc_block1_ok: Optional[bool]
    crc_data_ok: Optional[bool]
    crc_block2_ok: Optional[bool]
    file_size_ok: bool
    stored_size: int
    actual_size: int
    stored_md5: bytes
    computed_md5: Optional[bytes]
    crc_details: Dict[str, Tuple[int, int]]


@dataclass(frozen=True)
class PursuitRecord:
    career_slot: int
    bounty: int
    escaped: int
    busted: int
    abs_off: int


@dataclass(frozen=True)
class CareerVehicleRecord:
    car_number: int
    signature: bytes
    flags: int
    flags2: int
    parts_slot: int
    career_slot: int
    abs_off: int


@dataclass(frozen=True)
class OwnedCarRecord:
    car_number: int
    signature: bytes
    location_bits: int
    misc_bits: int
    parts_slot: int
    career_slot: int
    abs_off: int


@dataclass(frozen=True)
class ResolvedGarageEntry:
    career_slot: int
    car_number: Optional[int]
    signature: Optional[bytes]
    display_name: str
    source_kind: str
    occupied: bool
    bounty: int
    escaped: int
    busted: int
    flags: Optional[int]
    flags2: Optional[int]
    parts_slot: Optional[int]
    match_count: int
    pursuit_abs_off: int
    car_abs_off: Optional[int]


@dataclass(frozen=True)
class PartsRecord:
    parts_slot: int
    block_abs_off: int
    confirmed_raw: bytes
    marker: bytes
    tires: int
    brakes: int
    suspension: int
    transmission: int
    engine: int
    turbo: int
    nos: int
    junkman_mask: int
    junkman_categories: Tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPartsEntry:
    career_slot: int
    display_name: str
    source_kind: str
    parts_slot: int
    block_abs_off: int
    marker: bytes
    confirmed_raw: bytes
    tires: int
    brakes: int
    suspension: int
    transmission: int
    engine: int
    turbo: int
    nos: int
    junkman_mask: int
    junkman_categories: Tuple[str, ...]
    flags: Optional[int]
    flags2: Optional[int]
    car_abs_off: Optional[int]


@dataclass(frozen=True)
class ResolvedMyCarsEntry:
    car_number: int
    signature: bytes
    resolved_model_name: str
    location_bits: int
    misc_bits: int
    parts_slot: int
    career_slot: int
    block_abs_off: int
    tires: int
    brakes: int
    suspension: int
    transmission: int
    engine: int
    turbo: int
    nos: int
    junkman_mask: int
    junkman_categories: Tuple[str, ...]
    car_abs_off: int


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
        if flags == cls.CAREER_FLAG:
            return "Career"
        if flags == (cls.CAREER_FLAG | cls.PINK_SLIP_FLAG):
            return "Pink Slip"
        return f"Unknown (0x{flags:02X})"

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
        abs_off = self.PARTS_BLOCK_BASE_OFFSET + (slot - self.PARTS_BLOCK_SLOT_BASE) * self.PARTS_BLOCK_SIZE
        end = abs_off + self.PARTS_BLOCK_SIZE
        if end > len(self.data):
            raise ValueError(f"Parts slot {slot} points outside the file")
        marker_off = abs_off + self.PARTS_MARKER_OFFSET
        marker = bytes(self.data[marker_off:marker_off + 4])
        expected_marker = bytes((slot & 0xFF, 0xCD, 0xCD, 0xCD))
        if marker != expected_marker:
            raise ValueError(
                f"Parts slot {slot} has unexpected marker {marker.hex(' ').upper()} at 0x{marker_off:05X}"
            )
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
        offset = self.PART_LEVEL_OFFSETS.get(str(part_name))
        if offset is None:
            raise ValueError(f"Unsupported part name: {part_name}")

        limits = get_model_tuning_limits(entry.display_name)
        if limits is None:
            raise ValueError(f"No confirmed tuning caps for {entry.display_name}")

        cap = int(limits.get(str(part_name), 0))
        wanted = max(0, min(int(level), cap))
        self._write_u32(entry.block_abs_off + offset, wanted)

    def set_junkman_mask(self, career_slot: int, mask: int) -> None:
        entry = self._parts_entry_for_career_slot(career_slot)
        wanted = int(mask)
        if not (0 <= wanted <= 0x7F):
            raise ValueError("junkman mask must be in range 0x00..0x7F")

        turbo_bit = next((bit for bit, name in self.JUNKMAN_MASK_BITS if name == "Turbo"), 0)
        nos_bit = next((bit for bit, name in self.JUNKMAN_MASK_BITS if name == "NOS"), 0)
        current = self.get_parts_record(entry.parts_slot)
        if turbo_bit and (wanted & turbo_bit) and current.turbo <= 0:
            raise ValueError("Junkman Turbo requires regular Turbo > 0")
        if nos_bit and (wanted & nos_bit) and current.nos <= 0:
            raise ValueError("Junkman NOS requires regular NOS > 0")

        self._write_u32(entry.block_abs_off + self.PARTS_JUNKMAN_MASK_OFFSET, wanted)

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
                # fallback to backing up current buffer if reading original failed
                self.write_backup()

        self.fix_integrity()
        dest = Path(out_path) if out_path is not None else self.path
        dest.write_bytes(bytes(self.data))
        return dest
