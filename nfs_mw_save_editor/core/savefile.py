from __future__ import annotations

import datetime
import hashlib
import logging
import math
import struct
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from core import career_transplant, garage_records, rap_sheet_totals, snapshot_export, snapshot_injection, snapshot_library
from core.cars import resolve_car_name
from core.checksums import ea_crc32
from core.junkman import JunkmanInventory
from core.models import (
    CarNumberRegistryAudit,
    CareerSlotStatus,
    CareerTransplantPlan,
    CareerVehicleRecord,
    FullCarBuildSnapshot,
    GarageAllocatorSnapshot,
    HashScheme,
    IntegrityStatus,
    OwnedCarRecord,
    OwnedCarSlotStatus,
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
)
from core.tuning_limits import get_model_tuning_limits

logger = logging.getLogger(__name__)


class SaveFile:
    def __new__(cls, path=None, data=None, layout=None, hash_scheme=None):
        if cls is SaveFile and data is not None and len(data) == 0xF4E0 and data[:4] == b"MC02":
            from core.switch_format import SwitchSaveFile, is_switch_save
            if is_switch_save(data):
                return object.__new__(SwitchSaveFile)
            raise ValueError("Unrecognized 62688-byte MC02 save header")
        return object.__new__(cls)

    SNAPSHOT_FILE_PREFIX = snapshot_library.SNAPSHOT_FILE_PREFIX
    LEGACY_SNAPSHOT_FILE_PREFIX = snapshot_library.LEGACY_SNAPSHOT_FILE_PREFIX
    SNAPSHOT_KIND = snapshot_library.SNAPSHOT_KIND
    LEGACY_SNAPSHOT_KIND = snapshot_library.LEGACY_SNAPSHOT_KIND
    USER_SNAPSHOT_LIBRARY_DIRNAME = snapshot_library.USER_SNAPSHOT_LIBRARY_DIRNAME
    USER_SNAPSHOT_LIBRARY_APPDIR = snapshot_library.USER_SNAPSHOT_LIBRARY_APPDIR
    # Junkman inventory slot layout (dynamically detected)
    SAVED_DATA_START = JunkmanInventory.SAVED_DATA_START
    SLOT_STRIDE = JunkmanInventory.SLOT_STRIDE
    SLOT_TYPE_OFF = 0x00
    SLOT_COUNT_OFF = 0x08
    SLOT_SIZE = JunkmanInventory.SLOT_SIZE
    SLOT_MAX = 200  # upper bound for diff helpers
    PLAYER_RANK_OFFSET = 0x4038
    MONEY_OFFSET = 0x4039
    ACTIVE_CAREER_CAR_NUMBER_OFFSET = 0x4034
    PROFILE_ALIAS_OFFSET = 0x5A31
    PROFILE_ALIAS_BUFFER_SIZE = 0x24
    PROFILE_ALIAS_DEFAULT_LEN = 7
    PROFILE_ALIAS_MAX_LEN = 16
    GARAGE_BASE_OFFSET = garage_records.GARAGE_RECORDS_OFFSET
    GARAGE_SLOT_SIZE = garage_records.GARAGE_RECORD_SIZE
    GARAGE_SLOT_COUNT = garage_records.GARAGE_RECORD_COUNT
    GARAGE_EMPTY_HANDLE = garage_records.GARAGE_EMPTY_HANDLE
    # Garage slot = engine FECareerRecord. Persisted heat is ONLY the float at
    # +0x0C (native FECareerRecord::SetVehicleHeat writes a single float). The
    # bytes at +0x03..+0x07 belong to FEImpoundData and +0x18..+0x37 are the two
    # FEInfractionsData blocks; they correlate with heat in normal play but are
    # different fields and must never be written by the heat editor.
    GARAGE_IMPOUND_MAX_BUSTED_OFFSET = 0x02
    GARAGE_IMPOUND_TIMES_BUSTED_OFFSET = 0x03
    GARAGE_IMPOUND_STATE_OFFSET = 0x04
    GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET = 0x05
    GARAGE_IMPOUND_EVADE_COUNT_OFFSET = 0x06
    GARAGE_HEAT_FLOAT_OFFSET = 0x0C
    GARAGE_BOUNTY_OFFSET = 0x10
    GARAGE_ESCAPED_OFFSET = 0x14
    GARAGE_BUSTED_OFFSET = 0x16
    GARAGE_UNSERVED_INFRACTIONS_OFFSET = 0x18
    GARAGE_SERVED_INFRACTIONS_OFFSET = 0x28
    GARAGE_INFRACTION_COUNTER_COUNT = 8
    GARAGE_HEAT_BASELINE = 1.0
    GARAGE_HEAT_MIN = 1.0
    GARAGE_HEAT_MAX = 5.0
    # Native FECareerRecord::Default (0x56F750, build-specific) zeroes the
    # heat float; the in-game x1 display comes from runtime clamping. Editor
    # UI still clamps user input to GARAGE_HEAT_MIN..MAX.
    GARAGE_HEAT_NATIVE_FRESH = 0.0
    # Base impound-strike allowance; Add Impound Strike markers raise it to
    # at most 5. Gameplay data, never a detection criterion.
    GARAGE_MAX_BUSTED_BASE = 3
    CAREER_VEHICLE_BASE_OFFSET = 0x6219
    CAREER_VEHICLE_SIZE = 0x14
    CAREER_VEHICLE_SIGNATURE_OFFSET = 0x04
    CAREER_VEHICLE_SIGNATURE_SIZE = 0x08
    CAREER_VEHICLE_FLAGS_OFFSET = 0x0C
    CAREER_VEHICLE_FLAGS2_OFFSET = 0x0E
    CAREER_VEHICLE_PARTS_SLOT_OFFSET = 0x10
    CAREER_VEHICLE_SLOT_OFFSET = 0x11
    CAREER_VEHICLE_SENTINEL = b"\xCD\xCD"
    # Native car_number allocator [verified-by-bytes, 486 saves + 7 local
    # re-checks]: the registry at 0x6219 is a fixed 119-row prefix, and a
    # record's number is its PHYSICAL row, not a running counter -
    # car_number = 81 + slot index, so 81..199. Tombstoned rows are reused
    # with their own slot number (never max+1, never a shared counter).
    # 81 = CarTable[200] minus the 119 serialized rows [model-inference; the
    # literal is not in the decomp, allocator bodies are empty].
    CAREER_VEHICLE_SLOT_COUNT = 119
    CAR_NUMBER_SLOT_BASE = 81
    EMPTY_CAR_NUMBER = 0xFFFFFFFF
    EMPTY_CAREER_SLOT = 0xFF
    CAREER_FLAG = 0x02
    MY_CARS_FLAG = 0x04
    PINK_SLIP_FLAG = 0x40
    CONFIRMED_MAX_CAREER_LIKE_CARS = 25
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
    EMPTY_PARTS_BLOCK_HEAD_FILL = 0xFF
    EMPTY_PARTS_BLOCK_ZERO_TAIL_OFFSET = 0x190
    EMPTY_PARTS_BLOCK_MARKER = b"\xFF\xCD\xCD\xCD"
    VISUAL_SIDECAR_PARTS_BLOCKED_REASON = "Referenced by visual sidecar record"
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
        self.junkman = JunkmanInventory(self)

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

    def _read_f32(self, offset: int) -> float:
        return struct.unpack_from("<f", self.data, offset)[0]

    def _write_u16(self, offset: int, value: int) -> None:
        struct.pack_into("<H", self.data, offset, int(value) & 0xFFFF)

    def _write_u8(self, offset: int, value: int) -> None:
        self.data[offset] = int(value) & 0xFF

    def _write_u32(self, offset: int, value: int) -> None:
        struct.pack_into("<I", self.data, offset, int(value) & 0xFFFFFFFF)

    def _write_f32(self, offset: int, value: float) -> None:
        struct.pack_into("<f", self.data, offset, float(value))

    @staticmethod
    def _bytes_to_hex(raw: bytes) -> str:
        return bytes(raw).hex(" ").upper()

    @staticmethod
    def _require_u32(value: int) -> int:
        ivalue = int(value)
        if not (0 <= ivalue <= 0xFFFFFFFF):
            raise ValueError("value must be in range 0..4294967295")
        return ivalue

    @classmethod
    def _normalize_heat_value(cls, value: float | int) -> float:
        heat = float(value)
        if not math.isfinite(heat):
            raise ValueError("heat must be a finite number")
        if heat < cls.GARAGE_HEAT_MIN or heat > cls.GARAGE_HEAT_MAX:
            raise ValueError(f"heat must be between {cls.GARAGE_HEAT_MIN:.1f} and {cls.GARAGE_HEAT_MAX:.1f}")
        return heat

    @classmethod
    def heat_cap_for_blacklist_rank(cls, rank: int) -> int:
        current_rank = int(rank)
        if current_rank <= 4:
            return 5
        if current_rank <= 8:
            return 4
        if current_rank <= 12:
            return 3
        return 2

    def get_current_blacklist_rank(self) -> Optional[int]:
        if len(self.data) <= self.PLAYER_RANK_OFFSET:
            return None
        rank = self._read_u8(self.PLAYER_RANK_OFFSET)
        if rank <= 0:
            return None
        return int(rank)

    def get_story_heat_cap(self) -> int:
        rank = self.get_current_blacklist_rank()
        if rank is None:
            return int(self.GARAGE_HEAT_MAX)
        return self.heat_cap_for_blacklist_rank(rank)

    @classmethod
    def _heat_level_from_value(cls, heat: float | int) -> int:
        normalized = cls._normalize_heat_value(heat)
        level = int(math.floor(normalized))
        if level < int(cls.GARAGE_HEAT_MIN):
            return int(cls.GARAGE_HEAT_MIN)
        if level > int(cls.GARAGE_HEAT_MAX):
            return int(cls.GARAGE_HEAT_MAX)
        return level

    @classmethod
    def _write_pursuit_heat_into(cls, payload: bytearray, heat: float | int) -> None:
        struct.pack_into("<f", payload, cls.GARAGE_HEAT_FLOAT_OFFSET, cls._normalize_heat_value(heat))

    @classmethod
    def _init_empty_pursuit_counters_into(cls, payload: bytearray) -> None:
        # Explicit zero-record init for impound/infraction counters; MaxBusted
        # (+0x02) is gameplay data owned by the caller. EvadeCount is a
        # one-byte char; +0x07 is Pad1 and remains untouched.
        payload[cls.GARAGE_IMPOUND_TIMES_BUSTED_OFFSET] = 0
        payload[cls.GARAGE_IMPOUND_STATE_OFFSET] = 0
        payload[cls.GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET] = 0
        payload[cls.GARAGE_IMPOUND_EVADE_COUNT_OFFSET] = 0
        for block_off in (cls.GARAGE_UNSERVED_INFRACTIONS_OFFSET, cls.GARAGE_SERVED_INFRACTIONS_OFFSET):
            for counter in range(cls.GARAGE_INFRACTION_COUNTER_COUNT):
                struct.pack_into("<H", payload, block_off + counter * 2, 0)

    def _read_pursuit_heat_fields(self, abs_off: int) -> Tuple[float, Optional[int]]:
        raw_heat = self._read_f32(abs_off + self.GARAGE_HEAT_FLOAT_OFFSET)
        if math.isfinite(raw_heat):
            effective_heat = min(max(float(raw_heat), self.GARAGE_HEAT_MIN), self.GARAGE_HEAT_MAX)
            return float(raw_heat), int(self._heat_level_from_value(effective_heat))
        # Fail closed: an unreadable heat float is reported as unknown, never
        # reconstructed from the impound/infraction counters.
        return float(raw_heat), None

    def _write_pursuit_heat(self, abs_off: int, heat: float | int) -> None:
        self._write_f32(abs_off + self.GARAGE_HEAT_FLOAT_OFFSET, self._normalize_heat_value(heat))

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

    # --- economy / garage bounty ---

    def get_money(self) -> int:
        return self._read_u32(self.MONEY_OFFSET)

    def set_money(self, value: int) -> None:
        self._write_u32(self.MONEY_OFFSET, self._require_u32(value))

    def get_profile_alias_raw(self) -> bytes:
        start = self.PROFILE_ALIAS_OFFSET
        end = start + self.PROFILE_ALIAS_BUFFER_SIZE
        if end > len(self.data):
            raise ValueError("profile alias field points outside the file")
        return bytes(self.data[start:end])

    def get_profile_alias(self) -> str:
        raw = self.get_profile_alias_raw()
        name_bytes = raw.split(b"\x00", 1)[0]
        return name_bytes.decode("ascii")

    def set_profile_alias(self, value: str) -> None:
        alias = str(value)
        try:
            alias_bytes = alias.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("profile alias must contain ASCII characters only") from exc
        if len(alias_bytes) > self.PROFILE_ALIAS_MAX_LEN:
            raise ValueError(f"profile alias must be at most {self.PROFILE_ALIAS_MAX_LEN} ASCII characters")

        payload = alias_bytes + b"\x00"
        payload = payload.ljust(self.PROFILE_ALIAS_BUFFER_SIZE, b"\x00")
        start = self.PROFILE_ALIAS_OFFSET
        end = start + self.PROFILE_ALIAS_BUFFER_SIZE
        if end > len(self.data):
            raise ValueError("profile alias field points outside the file")
        self.data[start:end] = payload

    def get_active_career_car_number(self) -> int:
        return self._read_u8(self.ACTIVE_CAREER_CAR_NUMBER_OFFSET)

    def set_active_career_car_number(self, car_number: int) -> None:
        wanted = int(car_number)
        if wanted < 0 or wanted > 0xFF:
            raise ValueError("active career car_number must be in range 0..255")
        self._write_u8(self.ACTIVE_CAREER_CAR_NUMBER_OFFSET, wanted)

    def get_active_career_candidates(self) -> List[OwnedCarRecord]:
        candidates = [
            record
            for record in self.get_owned_car_records()
            if record.location_bits in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG)
            and record.career_slot != self.EMPTY_CAREER_SLOT
            and record.car_number != self.EMPTY_CAR_NUMBER
        ]
        return sorted(candidates, key=lambda record: (int(record.career_slot), int(record.car_number), int(record.abs_off)))

    def get_active_career_record(self) -> Optional[OwnedCarRecord]:
        active_car_number = self.get_active_career_car_number()
        return next(
            (record for record in self.get_active_career_candidates() if int(record.car_number) == int(active_car_number)),
            None,
        )

    def choose_fallback_active_career_record(self) -> Optional[OwnedCarRecord]:
        candidates = self.get_active_career_candidates()
        return candidates[0] if candidates else None

    def get_projected_active_career_car_number(
        self,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
    ) -> Optional[int]:
        current_active_car_number = int(self.get_active_career_car_number())
        current_location = location_overrides or {}
        current_career_slot = career_slot_overrides or {}
        candidates: List[Tuple[int, int, int]] = []
        for record in self.get_owned_car_records():
            location_bits = int(current_location.get(record.abs_off, record.location_bits))
            career_slot = int(current_career_slot.get(record.abs_off, record.career_slot))
            car_number = int(record.car_number)
            if location_bits not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG):
                continue
            if career_slot == self.EMPTY_CAREER_SLOT or car_number == self.EMPTY_CAR_NUMBER:
                continue
            candidates.append((career_slot, car_number, int(record.abs_off)))
        if not candidates:
            return None
        if any(car_number == current_active_car_number for _career_slot, car_number, _abs_off in candidates):
            return current_active_car_number
        candidates.sort()
        return int(candidates[0][1])

    def ensure_active_career_pointer_valid(self) -> int:
        active = self.get_active_career_record()
        if active is not None:
            return int(active.car_number)
        fallback = self.choose_fallback_active_career_record()
        if fallback is None:
            raise ValueError("Active career pointer has no surviving Career/Pink Slip target")
        self.set_active_career_car_number(int(fallback.car_number))
        return int(fallback.car_number)

    @classmethod
    def _is_empty_garage_slot(cls, raw: bytes) -> bool:
        return garage_records.is_empty_garage_record(raw)

    @classmethod
    def _is_live_garage_slot(cls, raw: bytes, career_slot: int) -> bool:
        return garage_records.is_live_garage_record(raw, career_slot)

    def _garage_slot_abs_off(self, career_slot: int) -> int:
        wanted = int(career_slot)
        if not (0 <= wanted < self.GARAGE_SLOT_COUNT):
            raise ValueError(f"career_slot must be in range 0..{self.GARAGE_SLOT_COUNT - 1}")
        abs_off = self.GARAGE_BASE_OFFSET + wanted * self.GARAGE_SLOT_SIZE
        if abs_off + self.GARAGE_SLOT_SIZE > len(self.data):
            raise ValueError(f"Career slot {wanted} points outside the file")
        return abs_off

    def _build_zero_pursuit_slot_payload(self, career_slot: int) -> bytes:
        # Native fresh FECareerRecord, mirroring the inlined Default body of
        # CreateNewCareerRecord: handle = slot, MaxBusted base, every counter
        # and the heat float zero. Native leaves the alignment bytes
        # +0x01/+0x0A..0B unchanged. Serialized records use CD there, and the
        # editor's live-record gate requires the same canonical padding.
        payload = bytearray(self.GARAGE_SLOT_SIZE)
        payload[0] = int(career_slot) & 0xFF
        payload[1] = 0xCD
        payload[self.GARAGE_IMPOUND_MAX_BUSTED_OFFSET] = self.GARAGE_MAX_BUSTED_BASE
        payload[0x0A:0x0C] = b"\xCD\xCD"
        struct.pack_into("<f", payload, self.GARAGE_HEAT_FLOAT_OFFSET, self.GARAGE_HEAT_NATIVE_FRESH)
        self._init_empty_pursuit_counters_into(payload)
        return bytes(payload)

    def _ensure_pursuit_slot_initialized(self, career_slot: int) -> int:
        wanted = int(career_slot)
        for slot in self.get_pursuit_records():
            if slot.career_slot == wanted:
                return slot.abs_off
        abs_off = self._garage_slot_abs_off(wanted)
        raw = bytes(self.data[abs_off:abs_off + self.GARAGE_SLOT_SIZE])
        if not self._is_empty_garage_slot(raw):
            raise ValueError(f"Pursuit slot {wanted} is neither live nor empty")
        self.data[abs_off:abs_off + self.GARAGE_SLOT_SIZE] = self._build_zero_pursuit_slot_payload(wanted)
        return abs_off

    def get_pursuit_records(self) -> List[PursuitRecord]:
        """Walk the fixed 25-slot CareerRecords array; return live records only.

        Occupancy is decided by the Handle byte alone (0xFF = empty, slot
        index = live); holes are legal and a zero-car garage is a valid [].
        Anything else is unexplained data and fails closed.
        """

        slots: List[PursuitRecord] = []
        for career_slot in range(self.GARAGE_SLOT_COUNT):
            base_off = self.GARAGE_BASE_OFFSET + career_slot * self.GARAGE_SLOT_SIZE
            if base_off + self.GARAGE_SLOT_SIZE > len(self.data):
                break
            raw = bytes(self.data[base_off:base_off + self.GARAGE_SLOT_SIZE])
            if self._is_empty_garage_slot(raw):
                continue
            if not self._is_live_garage_slot(raw, career_slot):
                if raw[0] != career_slot:
                    raise ValueError(
                        f"Garage record {career_slot} has unexpected handle 0x{raw[0]:02X}"
                    )
                raise ValueError(
                    f"Garage record {career_slot} fails the canonical pad-byte gate"
                )
            heat, heat_level = self._read_pursuit_heat_fields(base_off)
            slots.append(
                PursuitRecord(
                    career_slot=career_slot,
                    heat=heat,
                    heat_level=heat_level,
                    bounty=self._read_u32(base_off + self.GARAGE_BOUNTY_OFFSET),
                    escaped=self._read_u16(base_off + self.GARAGE_ESCAPED_OFFSET),
                    busted=self._read_u16(base_off + self.GARAGE_BUSTED_OFFSET),
                    abs_off=base_off,
                )
            )
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

    def audit_car_number_registry(self) -> CarNumberRegistryAudit:
        """Check the car registry against the native rule car_number = 81 + row.

        Pre-flight material for injection and the Compatibility page: rows that
        disagree with their position were numbered by hand, and a native
        purchase can later land on the same number. Read-only by design - a
        drifted save still loads in game, so repairing it is the user's call.
        """

        live: List[int] = []
        tombstones: List[int] = []
        empties: List[int] = []
        drifted: List[Tuple[int, int]] = []
        out_of_range: List[Tuple[int, int]] = []
        duplicates: List[int] = []
        seen: Set[int] = set()
        row = 0
        base_off = self.CAREER_VEHICLE_BASE_OFFSET
        highest_number = self.CAR_NUMBER_SLOT_BASE + self.CAREER_VEHICLE_SLOT_COUNT - 1

        while base_off + self.CAREER_VEHICLE_SIZE <= len(self.data):
            raw = bytes(self.data[base_off:base_off + self.CAREER_VEHICLE_SIZE])
            if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
                break
            car_number = self._read_u32(base_off)
            signature = raw[
                self.CAREER_VEHICLE_SIGNATURE_OFFSET:
                self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE
            ]
            if car_number == self.EMPTY_CAR_NUMBER:
                # A native sale only clears the number; the signature it leaves
                # behind is what tells a sold car from a never-used row.
                if signature == b"\x00" * self.CAREER_VEHICLE_SIGNATURE_SIZE:
                    empties.append(row)
                else:
                    tombstones.append(row)
            else:
                live.append(row)
                if car_number != self.CAR_NUMBER_SLOT_BASE + row:
                    drifted.append((row, car_number))
                if not (self.CAR_NUMBER_SLOT_BASE <= car_number <= highest_number):
                    out_of_range.append((row, car_number))
                if car_number in seen and car_number not in duplicates:
                    duplicates.append(car_number)
                seen.add(car_number)
            row += 1
            base_off += self.CAREER_VEHICLE_SIZE

        return CarNumberRegistryAudit(
            row_count=row,
            expected_row_count=self.CAREER_VEHICLE_SLOT_COUNT,
            live_rows=tuple(live),
            tombstone_rows=tuple(tombstones),
            empty_rows=tuple(empties),
            drifted_rows=tuple(drifted),
            out_of_range_rows=tuple(out_of_range),
            duplicate_numbers=tuple(duplicates),
        )

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

    @classmethod
    def is_career_like_location_bits(cls, location_bits: int) -> bool:
        return int(location_bits) in (cls.CAREER_FLAG, cls.CAREER_FLAG | cls.PINK_SLIP_FLAG)

    @classmethod
    def career_pool_warning_text(cls, career_like_count: int, *, projected: bool = False) -> Optional[str]:
        count = int(career_like_count)
        limit = int(cls.CONFIRMED_MAX_CAREER_LIKE_CARS)
        if count < limit:
            return None
        if projected:
            return (
                f"This will fill the Career garage to {count}/{limit}. "
                "The editor allows this, but winning another Blacklist Pink Slip in-game may cause a crash."
            )
        return (
            f"Career garage is full ({count}/{limit}). "
            "The editor allows this, but winning another Blacklist Pink Slip in-game may cause a crash."
        )

    def count_career_like_owned_records(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
    ) -> int:
        current_location = location_overrides or {}
        current_career_slot = career_slot_overrides or {}
        count = 0
        for record in self.get_owned_car_records():
            loc = current_location.get(record.abs_off, record.location_bits)
            slot = current_career_slot.get(record.abs_off, record.career_slot)
            if slot == self.EMPTY_CAREER_SLOT:
                continue
            if not self.is_career_like_location_bits(loc):
                continue
            count += 1
        return count

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
            occupied = car_number != self.EMPTY_CAR_NUMBER
            reusable = car_number == self.EMPTY_CAR_NUMBER
            blocked_reason = None
            status_kind = "occupied" if occupied else "reusable"
            status_code = "occupied" if occupied else "reusable"
            status_detail = None
            if reusable and base_off in reserved:
                reusable = False
                blocked_reason = "Reserved by staged injector"
                status_kind = "reserved"
                status_code = "reserved_by_staged_injector"
                status_detail = blocked_reason
            statuses.append(
                OwnedCarSlotStatus(
                    slot_index=slot_index,
                    abs_off=base_off,
                    occupied=occupied,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    status_kind=status_kind,
                    status_code=status_code,
                    status_detail=status_detail,
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

    def _is_native_empty_parts_block(self, raw_block: bytes) -> bool:
        return (
            len(raw_block) == self.PARTS_BLOCK_SIZE
            and raw_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4] == self.EMPTY_PARTS_BLOCK_MARKER
        )

    def _sidecar_placeholder_parts_slots(self) -> Set[int]:
        slots: Set[int] = set()
        records: List[Tuple[int, bytes, int, int, int]] = []
        base_off = self.CAREER_VEHICLE_BASE_OFFSET

        while base_off + self.CAREER_VEHICLE_SIZE <= len(self.data):
            raw = bytes(self.data[base_off:base_off + self.CAREER_VEHICLE_SIZE])
            if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
                break
            records.append(
                (
                    self._read_u32(base_off),
                    bytes(
                        self.data[
                            base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET:
                            base_off + self.CAREER_VEHICLE_SIGNATURE_OFFSET + self.CAREER_VEHICLE_SIGNATURE_SIZE
                        ]
                    ),
                    self._read_u16(base_off + self.CAREER_VEHICLE_FLAGS_OFFSET),
                    self._read_u8(base_off + self.CAREER_VEHICLE_PARTS_SLOT_OFFSET),
                    self._read_u8(base_off + self.CAREER_VEHICLE_SLOT_OFFSET),
                )
            )
            base_off += self.CAREER_VEHICLE_SIZE

        for idx in range(len(records) - 1):
            car_number, signature, location_bits, parts_slot, _career_slot = records[idx]
            next_car_number, next_signature, next_location_bits, next_parts_slot, next_career_slot = records[idx + 1]
            if car_number == self.EMPTY_CAR_NUMBER:
                continue
            if signature == (b"\x00" * self.CAREER_VEHICLE_SIGNATURE_SIZE):
                continue
            if location_bits != self.MY_CARS_FLAG:
                continue
            if next_car_number != self.EMPTY_CAR_NUMBER:
                continue
            if next_signature != signature:
                continue
            if next_location_bits != self.MY_CARS_FLAG or next_career_slot != self.EMPTY_CAREER_SLOT:
                continue
            if next_parts_slot != parts_slot + 1:
                continue
            if next_parts_slot not in self._parts_slot_numbers():
                continue
            parts_abs_off = self._parts_block_abs_off(next_parts_slot)
            raw_block = bytes(self.data[parts_abs_off:parts_abs_off + self.PARTS_BLOCK_SIZE])
            if self._is_native_empty_parts_block(raw_block):
                slots.add(next_parts_slot)
        return slots

    def get_parts_slot_statuses(
        self,
        *,
        reserved_parts_slots: Optional[Set[int]] = None,
    ) -> List[PartsSlotStatus]:
        reserved = {int(value) for value in (reserved_parts_slots or set())}
        referenced_slots = {record.parts_slot for record in self.get_owned_car_records()}
        sidecar_placeholder_slots = self._sidecar_placeholder_parts_slots()
        statuses: List[PartsSlotStatus] = []
        for slot in self._parts_slot_numbers():
            abs_off = self._parts_block_abs_off(slot)
            raw_block = bytes(self.data[abs_off:abs_off + self.PARTS_BLOCK_SIZE])
            marker = bytes(raw_block[self.PARTS_MARKER_OFFSET:self.PARTS_MARKER_OFFSET + 4])
            referenced = slot in referenced_slots
            reusable = False
            blocked_reason: Optional[str] = None
            status_kind = "blocked"
            status_code = "nonempty_block"
            status_detail: Optional[str] = None
            if referenced:
                blocked_reason = "Referenced by owned-car record"
                status_kind = "occupied"
                status_code = "occupied_owned_reference"
                status_detail = blocked_reason
            elif slot in sidecar_placeholder_slots:
                blocked_reason = self.VISUAL_SIDECAR_PARTS_BLOCKED_REASON
                status_kind = "placeholder"
                status_code = "placeholder_visual_sidecar"
                status_detail = blocked_reason
            elif slot in reserved:
                blocked_reason = "Reserved by staged injector"
                status_kind = "reserved"
                status_code = "reserved_by_staged_injector"
                status_detail = blocked_reason
            elif self._is_blank_parts_block(raw_block) or self._is_native_empty_parts_block(raw_block):
                reusable = True
                status_kind = "reusable"
                status_code = (
                    "reusable_blank" if self._is_blank_parts_block(raw_block) else "reusable_native_empty"
                )
                status_detail = None
            else:
                blocked_reason = "Non-empty parts block"
                status_kind = "blocked"
                status_code = "nonempty_block"
                status_detail = blocked_reason
            statuses.append(
                PartsSlotStatus(
                    parts_slot=slot,
                    abs_off=abs_off,
                    referenced_by_owned_car=referenced,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    status_kind=status_kind,
                    status_code=status_code,
                    status_detail=status_detail,
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
        pursuits_by_slot = {record.career_slot: record for record in self.get_pursuit_records()}
        for career_slot in range(self.GARAGE_SLOT_COUNT):
            try:
                abs_off = self._garage_slot_abs_off(career_slot)
            except ValueError:
                break
            linked = linked_counts.get(career_slot, 0)
            record = pursuits_by_slot.get(career_slot)
            blocked_reason = None
            status_detail: Optional[str] = None
            if record is None:
                # Empty slot (Handle 0xFF): any stale payload is invisible to
                # the game, so the slot is freely reusable when unlinked.
                reusable = linked == 0
                status_kind = "reusable" if reusable else "occupied"
                status_code = "reusable" if reusable else "occupied"
                if career_slot in reserved_career_slots and reusable:
                    reusable = False
                    blocked_reason = "Reserved by staged injector"
                    status_kind = "reserved"
                    status_code = "reserved_by_staged_injector"
                    status_detail = blocked_reason
                elif linked > 1:
                    blocked_reason = f"Ambiguous: {linked} cars target this career slot"
                    status_kind = "blocked"
                    status_code = "ambiguous_career_target"
                    status_detail = blocked_reason
                elif linked == 1:
                    blocked_reason = "Already targeted by a staged Career car"
                    status_kind = "reserved"
                    status_code = "reserved_by_staged_career_target"
                    status_detail = blocked_reason
                bounty = 0
                escaped = 0
                busted = 0
                is_zero = True
            else:
                if career_slot in staged_cleared_slots:
                    bounty = 0
                    escaped = 0
                    busted = 0
                else:
                    bounty = record.bounty
                    escaped = record.escaped
                    busted = record.busted
                is_zero = (bounty, escaped, busted) == (0, 0, 0)
                reusable = linked == 0 and is_zero
                status_kind = "occupied" if linked == 1 else ("reusable" if reusable else "blocked")
                status_code = "occupied" if linked == 1 else ("reusable" if reusable else "unlinked_pursuit")
                if career_slot in reserved_career_slots and reusable:
                    reusable = False
                    blocked_reason = "Reserved by staged injector"
                    status_kind = "reserved"
                    status_code = "reserved_by_staged_injector"
                    status_detail = blocked_reason
                elif linked == 0 and not is_zero:
                    blocked_reason = "Unlinked pursuit stats present"
                    status_kind = "blocked"
                    status_code = "unlinked_pursuit"
                    status_detail = blocked_reason
                elif linked > 1:
                    blocked_reason = f"Ambiguous: {linked} cars target this career slot"
                    status_kind = "blocked"
                    status_code = "ambiguous_career_target"
                    status_detail = blocked_reason
            statuses.append(
                CareerSlotStatus(
                    career_slot=career_slot,
                    abs_off=abs_off,
                    linked_car_count=linked,
                    reusable=reusable,
                    blocked_reason=blocked_reason,
                    status_kind=status_kind,
                    status_code=status_code,
                    status_detail=status_detail,
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
        reserved_parts_slots: Optional[Set[int]] = None,
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
            parts_slots=tuple(self.get_parts_slot_statuses(reserved_parts_slots=reserved_parts_slots)),
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
                    heat=self.GARAGE_HEAT_NATIVE_FRESH,
                    heat_level=self._heat_level_from_value(self.GARAGE_HEAT_MIN),
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
                    heat=(pursuit.heat if pursuit is not None else None),
                    heat_level=(pursuit.heat_level if pursuit is not None else None),
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
        abs_off = self._ensure_pursuit_slot_initialized(wanted)
        self.data[abs_off:abs_off + self.GARAGE_SLOT_SIZE] = self._build_zero_pursuit_slot_payload(wanted)

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
        allow_restore_to_nonvalidated_slot: bool = False,
    ) -> OwnedCarTransferPlan:
        source = self._owned_record_by_abs_off(
            abs_off,
            location_overrides=location_overrides,
            misc_overrides=misc_overrides,
            career_slot_overrides=career_slot_overrides,
        )
        pursuit_slots = {record.career_slot for record in self.get_pursuit_records()}
        source_has_pursuit_record = (
            source.career_slot != self.EMPTY_CAREER_SLOT and source.career_slot in pursuit_slots
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
        warnings: List[str] = []

        if target == "my_cars":
            if source.location_bits == self.MY_CARS_FLAG and source.career_slot == self.EMPTY_CAREER_SLOT:
                refusal = "Already in My Cars"
            elif source.location_bits not in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG, self.MY_CARS_FLAG):
                refusal = f"Unsupported source flags 0x{source.location_bits:02X}"
            else:
                target_location_bits = self.MY_CARS_FLAG
                target_career_slot = None
                if source_has_pursuit_record:
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
                            if allow_restore_to_nonvalidated_slot:
                                target_career_slot = int(desired_career_slot)
                            else:
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

        source_is_career_like = (
            self.is_career_like_location_bits(source.location_bits)
            and int(source.career_slot) != self.EMPTY_CAREER_SLOT
        )
        target_is_career_like = (
            target_location_bits is not None
            and self.is_career_like_location_bits(int(target_location_bits))
            and target_career_slot is not None
        )
        if refusal is None and target_is_career_like and not source_is_career_like:
            projected_count = (
                self.count_career_like_owned_records(
                    location_overrides=location_overrides,
                    career_slot_overrides=career_slot_overrides,
                )
                + len({int(slot) for slot in (reserved_career_slots or set())})
                + 1
            )
            warning = self.career_pool_warning_text(projected_count, projected=True)
            if warning is not None:
                warnings.append(warning)

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
            warnings=tuple(warnings),
        )

    def transfer_owned_car(
        self,
        abs_off: int,
        target_mode: str,
        *,
        desired_career_slot: Optional[int] = None,
        allow_restore_to_nonvalidated_slot: bool = False,
    ) -> OwnedCarTransferPlan:
        current_active_car_number = self.get_active_career_car_number()
        pursuit_slots = {record.career_slot for record in self.get_pursuit_records()}
        plan = self.plan_owned_car_transfer(
            abs_off,
            target_mode,
            desired_career_slot=desired_career_slot,
            allow_restore_to_nonvalidated_slot=allow_restore_to_nonvalidated_slot,
        )
        if plan.refusal_reason:
            raise ValueError(plan.refusal_reason)
        if plan.clears_pursuit_slot and plan.cleared_source_career_slot is not None:
            self.clear_pursuit_slot(plan.cleared_source_career_slot)
        target_is_career_like = (
            int(plan.target_location_bits) in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG)
            and plan.target_career_slot is not None
        )
        source_had_pursuit_link = (
            int(plan.source_location_bits) in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG)
            and int(plan.source_career_slot) != self.EMPTY_CAREER_SLOT
            and int(plan.source_career_slot) in pursuit_slots
        )
        if target_is_career_like and (
            not source_had_pursuit_link or int(plan.target_career_slot) != int(plan.source_career_slot)
        ):
            self.clear_pursuit_slot(int(plan.target_career_slot))
        self.set_owned_car_location(plan.source_abs_off, plan.target_location_bits, plan.target_misc_bits)
        if plan.target_career_slot is None:
            self.clear_owned_car_career_slot(plan.source_abs_off)
        else:
            self.set_owned_car_career_slot(plan.source_abs_off, plan.target_career_slot)
        source_was_active_career = (
            int(plan.source_location_bits) in (self.CAREER_FLAG, self.CAREER_FLAG | self.PINK_SLIP_FLAG)
            and int(plan.source_career_slot) != self.EMPTY_CAREER_SLOT
            and int(current_active_car_number) == int(self._read_u32(plan.source_abs_off))
        )
        if source_was_active_career and not target_is_career_like:
            fallback = self.choose_fallback_active_career_record()
            if fallback is not None:
                self.set_active_career_car_number(int(fallback.car_number))
        return plan

    @classmethod
    def _snapshot_library_format(cls) -> snapshot_library.SnapshotLibraryFormat:
        return snapshot_library.SnapshotLibraryFormat(
            parts_block_size=cls.PARTS_BLOCK_SIZE,
            career_vehicle_signature_size=cls.CAREER_VEHICLE_SIGNATURE_SIZE,
        )

    @classmethod
    def default_snapshot_library_root(cls) -> Path:
        return snapshot_library.default_snapshot_library_root()

    @classmethod
    def default_user_snapshot_library_root(cls) -> Path:
        return snapshot_library.default_user_snapshot_library_root()

    @classmethod
    def load_snapshot_library_entry(
        cls,
        path: str | Path,
        *,
        library_root: str | Path | None = None,
        library_bucket: str | None = None,
    ) -> SnapshotLibraryEntry:
        return snapshot_library.load_snapshot_library_entry(
            path,
            format_config=cls._snapshot_library_format(),
            library_root=library_root,
            library_bucket=library_bucket,
        )

    @classmethod
    def load_snapshot_library(
        cls,
        root: str | Path | None = None,
        *,
        user_root: str | Path | None = None,
    ) -> List[SnapshotLibraryEntry]:
        return snapshot_library.load_snapshot_library(
            root,
            format_config=cls._snapshot_library_format(),
            user_root=user_root,
        )

    def plan_career_transplant(self, donor_data: bytes) -> CareerTransplantPlan:
        return career_transplant.plan_career_transplant(self, donor_data)

    def apply_career_transplant(
        self,
        donor_data: bytes,
        bounty_mode: str = career_transplant.BOUNTY_MODE_KEEP,
    ) -> None:
        return career_transplant.apply_career_transplant(self, donor_data, bounty_mode)

    @classmethod
    def _snapshot_target_location_bits(
        cls,
        snapshot: SnapshotLibraryEntry,
        target_mode: str,
    ) -> int:
        return snapshot_injection.snapshot_target_location_bits(cls, snapshot, target_mode)

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
        return snapshot_injection.plan_snapshot_injection(
            self,
            snapshot,
            target_mode,
            location_overrides=location_overrides,
            career_slot_overrides=career_slot_overrides,
            cleared_slots=cleared_slots,
            reserved_owned_abs_offs=reserved_owned_abs_offs,
            reserved_parts_slots=reserved_parts_slots,
            reserved_career_slots=reserved_career_slots,
            desired_career_slot=desired_career_slot,
        )

    def inject_snapshot(
        self,
        snapshot: SnapshotLibraryEntry,
        target_mode: str,
        *,
        desired_career_slot: Optional[int] = None,
    ) -> SnapshotInjectionPlan:
        return snapshot_injection.inject_snapshot(
            self,
            snapshot,
            target_mode,
            desired_career_slot=desired_career_slot,
        )

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
                    heat=pursuit.heat,
                    heat_level=pursuit.heat_level,
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

    def _read_owned_record_raw(self, abs_off: int) -> bytes:
        if abs_off < 0 or abs_off + self.CAREER_VEHICLE_SIZE > len(self.data):
            raise ValueError(f"Owned-car record at 0x{abs_off:05X} is out of bounds")
        raw = bytes(self.data[abs_off:abs_off + self.CAREER_VEHICLE_SIZE])
        if raw[0x12:0x14] != self.CAREER_VEHICLE_SENTINEL:
            raise ValueError(f"Owned-car record at 0x{abs_off:05X} has no CD CD sentinel")
        return raw

    def extract_full_car_build_snapshot(self, abs_off: int) -> FullCarBuildSnapshot:
        return snapshot_export.extract_full_car_build_snapshot(self, abs_off)

    def get_full_car_build_snapshots(self) -> List[FullCarBuildSnapshot]:
        return snapshot_export.get_full_car_build_snapshots(self)

    def snapshot_to_dict(self, snapshot: FullCarBuildSnapshot) -> Dict[str, object]:
        return snapshot_export.snapshot_to_dict(self, snapshot)

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

    def get_slot_heat(self, slot_index: int) -> float:
        wanted = int(slot_index)
        for slot in self.get_pursuit_records():
            if slot.career_slot == wanted:
                return float(slot.heat)
        raise ValueError(f"Garage slot {wanted} was not detected")

    def get_slot_heat_level(self, slot_index: int) -> Optional[int]:
        wanted = int(slot_index)
        for slot in self.get_pursuit_records():
            if slot.career_slot == wanted:
                return None if slot.heat_level is None else int(slot.heat_level)
        raise ValueError(f"Garage slot {wanted} was not detected")

    def set_slot_heat(self, slot_index: int, value: float | int) -> None:
        wanted = int(slot_index)
        normalized = self._normalize_heat_value(value)
        level = self._heat_level_from_value(normalized)
        cap = self.get_story_heat_cap()
        if level > cap:
            rank = self.get_current_blacklist_rank()
            rank_text = f" for Blacklist #{rank}" if rank is not None else ""
            raise ValueError(f"Heat x{level} is locked by story progression{rank_text}; current cap is x{cap}")
        for slot in self.get_pursuit_records():
            if slot.career_slot == wanted:
                self._write_pursuit_heat(slot.abs_off, normalized)
                return
        raise ValueError(f"Garage slot {wanted} was not detected")

    def get_rap_sheet_totals(self) -> Optional[rap_sheet_totals.RapSheetTotals]:
        """Shared Rap Sheet aggregates (live garage + sold-car history).

        None means unavailable: not a save, or a garage record failed the
        fail-closed occupancy gate. Display surfaces show a gap; paths that
        must refuse loudly call read_rap_sheet_totals directly and let its
        ValueError carry the slot.
        """

        try:
            return rap_sheet_totals.read_rap_sheet_totals(bytes(self.data))
        except ValueError:
            return None

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
