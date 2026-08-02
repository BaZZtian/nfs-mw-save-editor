from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

HashScheme = Optional[Literal["md5_saved_data", "md5_all_minus_tail"]]
SlotStatusKind = Literal["occupied", "reusable", "reserved", "blocked", "placeholder"]


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
    heat: float
    heat_level: Optional[int]
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

    @property
    def is_career(self) -> bool:
        return self.location_bits == 0x02 and self.career_slot != 0xFF

    @property
    def is_my_cars(self) -> bool:
        return self.location_bits == 0x04 and self.career_slot == 0xFF

    @property
    def is_pink_slip(self) -> bool:
        return self.location_bits == 0x42 and self.career_slot != 0xFF

    @property
    def has_pursuit_link(self) -> bool:
        return self.career_slot != 0xFF


@dataclass(frozen=True)
class ResolvedGarageEntry:
    career_slot: int
    car_number: Optional[int]
    signature: Optional[bytes]
    display_name: str
    source_kind: str
    occupied: bool
    heat: float
    heat_level: Optional[int]
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


@dataclass(frozen=True)
class ResolvedTransferCarEntry:
    abs_off: int
    car_number: int
    signature: bytes
    display_name: str
    source_kind: str
    location_bits: int
    misc_bits: int
    parts_slot: int
    career_slot: int
    is_career: bool
    is_my_cars: bool
    is_pink_slip: bool
    has_pursuit_link: bool
    heat: Optional[float]
    heat_level: Optional[int]
    bounty: Optional[int]
    escaped: Optional[int]
    busted: Optional[int]
    pursuit_abs_off: Optional[int]


@dataclass(frozen=True)
class OwnedCarSlotStatus:
    slot_index: int
    abs_off: int
    occupied: bool
    reusable: bool
    blocked_reason: Optional[str]
    status_kind: SlotStatusKind
    status_code: str
    status_detail: Optional[str]
    car_number: int
    location_bits: int
    misc_bits: int
    parts_slot: int
    career_slot: int


@dataclass(frozen=True)
class CareerSlotStatus:
    career_slot: int
    abs_off: int
    linked_car_count: int
    reusable: bool
    blocked_reason: Optional[str]
    status_kind: SlotStatusKind
    status_code: str
    status_detail: Optional[str]
    bounty: int
    escaped: int
    busted: int
    is_zero: bool


@dataclass(frozen=True)
class GarageAllocatorSnapshot:
    owned_slots: Tuple[OwnedCarSlotStatus, ...]
    career_slots: Tuple[CareerSlotStatus, ...]
    parts_slots: Tuple[PartsSlotStatus, ...] = ()

    @property
    def reusable_owned_slots(self) -> Tuple[OwnedCarSlotStatus, ...]:
        return tuple(slot for slot in self.owned_slots if slot.reusable)

    @property
    def reusable_parts_slots(self) -> Tuple[PartsSlotStatus, ...]:
        return tuple(slot for slot in self.parts_slots if slot.reusable)

    @property
    def injection_capacity(self) -> int:
        """How many new cars can be injected: each needs one free owned-car
        row and one free customization (parts) block, so the smaller pool
        is the real ceiling."""
        return min(len(self.reusable_owned_slots), len(self.reusable_parts_slots))

    @property
    def reusable_career_slots(self) -> Tuple[CareerSlotStatus, ...]:
        return tuple(slot for slot in self.career_slots if slot.reusable)

    @property
    def blocked_owned_slots(self) -> Tuple[OwnedCarSlotStatus, ...]:
        return tuple(slot for slot in self.owned_slots if not slot.occupied and not slot.reusable)

    @property
    def blocked_career_slots(self) -> Tuple[CareerSlotStatus, ...]:
        return tuple(slot for slot in self.career_slots if not slot.reusable and slot.linked_car_count != 1)

    @property
    def reserved_owned_slots(self) -> Tuple[OwnedCarSlotStatus, ...]:
        return tuple(slot for slot in self.owned_slots if slot.status_kind == "reserved")

    @property
    def reserved_career_slots(self) -> Tuple[CareerSlotStatus, ...]:
        return tuple(slot for slot in self.career_slots if slot.status_kind == "reserved")

    @property
    def hard_blocked_owned_slots(self) -> Tuple[OwnedCarSlotStatus, ...]:
        return tuple(slot for slot in self.owned_slots if slot.status_kind in {"blocked", "placeholder"})

    @property
    def hard_blocked_career_slots(self) -> Tuple[CareerSlotStatus, ...]:
        return tuple(slot for slot in self.career_slots if slot.status_kind in {"blocked", "placeholder"})

    @property
    def unavailable_owned_slots(self) -> Tuple[OwnedCarSlotStatus, ...]:
        return self.reserved_owned_slots + self.hard_blocked_owned_slots

    @property
    def unavailable_career_slots(self) -> Tuple[CareerSlotStatus, ...]:
        return self.reserved_career_slots + self.hard_blocked_career_slots


@dataclass(frozen=True)
class PartsSlotStatus:
    parts_slot: int
    abs_off: int
    referenced_by_owned_car: bool
    reusable: bool
    blocked_reason: Optional[str]
    status_kind: SlotStatusKind
    status_code: str
    status_detail: Optional[str]
    marker: bytes


@dataclass(frozen=True)
class OwnedCarTransferPlan:
    source_abs_off: int
    source_display_name: str
    source_location_bits: int
    source_misc_bits: int
    source_career_slot: int
    source_parts_slot: int
    target_location_bits: int
    target_misc_bits: int
    target_career_slot: Optional[int]
    cleared_source_career_slot: Optional[int]
    clears_pursuit_slot: bool
    target_owned_abs_off: int
    requires_relocation: bool
    refusal_reason: Optional[str]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnedCarTemplate:
    car_number: int
    signature: bytes
    location_bits: int
    misc_bits: int
    source_kind: str


@dataclass(frozen=True)
class VisualSidecarTemplate:
    owned_record_abs_off: int
    owned_record_signature_clone: bytes
    owned_record_location_bits: int
    owned_record_misc_bits: int
    sidecar_parts_slot_offset: int
    sidecar_parts_slot: int
    sidecar_block_abs_off: int
    owned_record_raw: bytes
    sidecar_build_block: bytes
    normalized_sidecar_build_block: bytes


@dataclass(frozen=True)
class SnapshotVisualSidecarEntry:
    owned_record_signature_clone: bytes
    owned_record_location_bits: int
    owned_record_misc_bits: int
    sidecar_parts_slot_offset: int
    normalized_sidecar_build_block: bytes
    sidecar_marker: bytes


@dataclass(frozen=True)
class FullCarBuildSnapshot:
    car_abs_off: int
    display_name: str
    source_kind: str
    car_number: int
    signature: bytes
    location_bits: int
    misc_bits: int
    parts_slot: int
    career_slot: int
    primary_owned_record_template: OwnedCarTemplate
    primary_build_block_abs_off: int
    primary_build_block: bytes
    normalized_primary_build_block: bytes
    performance_levels: Tuple[Tuple[str, int], ...]
    primary_visual_fields: Tuple[Tuple[str, str], ...]
    optional_visual_sidecar: Optional[VisualSidecarTemplate]
    requires_unresolved_global_visual_state: bool
    global_visual_table_entries: Tuple[bytes, ...]
    global_visual_table_values: Tuple[int, ...]
    global_visual_table_uniform_value: Optional[int]
    global_visual_table_mode_offset: int
    global_visual_table_mode_values: Tuple[int, ...]
    global_visual_table_mode_uniform_value: Optional[int]
    global_visual_table_mode_tail_value: Optional[int]


@dataclass(frozen=True)
class SnapshotLibraryEntry:
    snapshot_id: str
    json_path: Path
    library_bucket: str
    file_label: str
    display_name: str
    source_file: str
    source_kind: str
    primary_owned_record_template: OwnedCarTemplate
    normalized_primary_build_block: bytes
    performance_levels: Tuple[Tuple[str, int], ...]
    primary_visual_fields: Tuple[Tuple[str, str], ...]
    requires_unresolved_global_visual_state: bool
    has_visual_sidecar: bool
    optional_visual_sidecar: Optional[SnapshotVisualSidecarEntry] = None
    global_visual_table_uniform_value: Optional[int] = None
    global_visual_table_mode_offset: int = 4
    global_visual_table_mode_uniform_value: Optional[int] = None
    global_visual_table_mode_tail_value: Optional[int] = None
    provenance: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SnapshotInjectionPlan:
    snapshot_id: str
    display_name: str
    target_mode: str
    target_location_bits: int
    target_misc_bits: int
    target_owned_abs_off: Optional[int]
    target_parts_slot: Optional[int]
    target_career_slot: Optional[int]
    refusal_reason: Optional[str]
    warnings: Tuple[str, ...]
    target_sidecar_owned_abs_off: Optional[int] = None
    target_sidecar_parts_slot: Optional[int] = None


@dataclass(frozen=True)
class CareerTransplantPlan:
    refusal_reason: Optional[str]
    warnings: Tuple[str, ...]
    donor_bin: int
    spans_total_bytes: int
    # Amount apply will add to SoldHistoryBounty so the rap-sheet total
    # matches the donor stage (0 = user already has enough).
    bounty_compensation: int = 0
