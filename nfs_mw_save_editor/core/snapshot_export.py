"""Snapshot extraction and JSON export.

This module is intended to own the save-file -> snapshot-dict direction:
reading an existing owned build, summarizing its parts / visual sidecar state,
and producing the JSON payload consumed by core.snapshot_library. It must not
import SaveFile. The Protocol below documents the exact SaveFile surface the
implementation uses.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple

from core.cars import resolve_car_name
from core.models import (
    FullCarBuildSnapshot,
    OwnedCarRecord,
    OwnedCarTemplate,
    PartsRecord,
    VisualSidecarTemplate,
)


class SnapshotExportSave(Protocol):
    """SaveFile surface required to extract and export build snapshots."""

    data: bytearray
    path: Path
    SNAPSHOT_KIND: str
    EMPTY_CAR_NUMBER: int
    EMPTY_CAREER_SLOT: int
    MY_CARS_FLAG: int
    CAREER_VEHICLE_SIZE: int
    CAREER_VEHICLE_SIGNATURE_OFFSET: int
    CAREER_VEHICLE_SIGNATURE_SIZE: int
    CAREER_VEHICLE_FLAGS_OFFSET: int
    CAREER_VEHICLE_FLAGS2_OFFSET: int
    CAREER_VEHICLE_PARTS_SLOT_OFFSET: int
    CAREER_VEHICLE_SLOT_OFFSET: int
    PARTS_BLOCK_SIZE: int
    PARTS_MARKER_OFFSET: int
    PRIMARY_VISUAL_FIELDS: Tuple[Tuple[str, int, int], ...]
    VISUAL_TABLE_BASE_OFFSET: int
    VISUAL_TABLE_ENTRY_COUNT: int
    VISUAL_TABLE_ENTRY_STRIDE: int
    VISUAL_TABLE_LEGACY_VALUE_OFFSET: int
    VISUAL_TABLE_MODE_OFFSET: int
    VISUAL_TABLE_DEFAULT_VALUE: int

    def _parts_block_abs_off(self, parts_slot: int) -> int:
        """Return the absolute offset for a parts block."""
        ...

    def _parts_block_marker(self, parts_slot: int, allow_placeholder_marker: bool = False) -> bytes:
        """Validate and return the marker for a parts block."""
        ...

    def _read_u8(self, offset: int) -> int:
        """Read one unsigned byte from the save buffer."""
        ...

    def _bytes_to_hex(self, raw: bytes) -> str:
        """Format bytes using SaveFile's current snapshot JSON hex style."""
        ...

    def _owned_record_by_abs_off(
        self,
        abs_off: int,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        misc_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
    ) -> OwnedCarRecord:
        """Resolve an owned-car record at an absolute offset."""
        ...

    def _read_owned_record_raw(self, abs_off: int) -> bytes:
        """Read raw owned-record bytes with SaveFile's bounds/sentinel checks."""
        ...

    def get_parts_record(self, parts_slot: int) -> PartsRecord:
        """Read decoded parts information for a parts slot."""
        ...

    def derive_source_kind(self, flags: Optional[int]) -> str:
        """Map owned-record location bits to the displayed source kind."""
        ...

    def get_owned_car_records(self) -> List[OwnedCarRecord]:
        """Return currently detected non-empty owned-car records."""
        ...

    def extract_full_car_build_snapshot(self, abs_off: int) -> FullCarBuildSnapshot:
        """Extract one build snapshot through SaveFile's public delegate."""
        ...


def extract_full_car_build_snapshot(save: SnapshotExportSave, abs_off: int) -> FullCarBuildSnapshot:
    """Extract a full build snapshot from one owned-car record."""

    record = save._owned_record_by_abs_off(abs_off)
    parts = save.get_parts_record(record.parts_slot)
    primary_block = _read_parts_block_bytes(save, record.parts_slot)
    visual_table_entries = _visual_table_entries(save)
    visual_table_values = _visual_table_values(save, save.VISUAL_TABLE_LEGACY_VALUE_OFFSET)
    visual_table_mode_values = _visual_table_values(save, save.VISUAL_TABLE_MODE_OFFSET)
    effective_visual_entries = _effective_visual_table_entries(save, visual_table_entries)
    effective_visual_mode_values = _entry_probe_values(
        effective_visual_entries,
        save.VISUAL_TABLE_MODE_OFFSET,
    )
    mode_tail_value = (
        int(visual_table_entries[-1][save.VISUAL_TABLE_MODE_OFFSET])
        if visual_table_entries and _is_visual_table_tail_entry(save, visual_table_entries[-1])
        else None
    )
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
        source_kind=save.derive_source_kind(record.location_bits),
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
            source_kind=save.derive_source_kind(record.location_bits),
        ),
        primary_build_block_abs_off=parts.block_abs_off,
        primary_build_block=primary_block,
        normalized_primary_build_block=_normalize_parts_block(save, primary_block),
        performance_levels=performance_levels,
        primary_visual_fields=_primary_visual_summary(save, primary_block),
        optional_visual_sidecar=_detect_visual_sidecar(save, record),
        requires_unresolved_global_visual_state=any(
            value != save.VISUAL_TABLE_DEFAULT_VALUE for value in effective_visual_mode_values
        ),
        global_visual_table_entries=visual_table_entries,
        global_visual_table_values=visual_table_values,
        global_visual_table_uniform_value=_uniform_value(visual_table_values),
        global_visual_table_mode_offset=save.VISUAL_TABLE_MODE_OFFSET,
        global_visual_table_mode_values=visual_table_mode_values,
        global_visual_table_mode_uniform_value=_uniform_value(effective_visual_mode_values),
        global_visual_table_mode_tail_value=mode_tail_value,
    )


def get_full_car_build_snapshots(save: SnapshotExportSave) -> List[FullCarBuildSnapshot]:
    """Extract full build snapshots for every detected owned-car record."""

    snapshots = [
        save.extract_full_car_build_snapshot(record.abs_off)
        for record in save.get_owned_car_records()
    ]
    return sorted(snapshots, key=lambda item: item.car_number)


def snapshot_to_dict(save: SnapshotExportSave, snapshot: FullCarBuildSnapshot) -> Dict[str, object]:
    """Convert a full build snapshot to the persisted JSON payload shape."""

    sidecar = snapshot.optional_visual_sidecar
    return {
        "kind": save.SNAPSHOT_KIND,
        "source_file": str(save.path),
        "display_name": snapshot.display_name,
        "source_kind": snapshot.source_kind,
        "car_number": snapshot.car_number,
        "signature_hex": save._bytes_to_hex(snapshot.signature),
        "location_bits": snapshot.location_bits,
        "misc_bits": snapshot.misc_bits,
        "parts_slot": snapshot.parts_slot,
        "career_slot": snapshot.career_slot,
        "primary_owned_record_template": {
            "car_number": snapshot.primary_owned_record_template.car_number,
            "signature_hex": save._bytes_to_hex(snapshot.primary_owned_record_template.signature),
            "location_bits": snapshot.primary_owned_record_template.location_bits,
            "misc_bits": snapshot.primary_owned_record_template.misc_bits,
            "source_kind": snapshot.primary_owned_record_template.source_kind,
            "parts_slot_placeholder": True,
            "career_slot_placeholder": True,
        },
        "primary_build_block": {
            "abs_off": snapshot.primary_build_block_abs_off,
            "normalized_hex": save._bytes_to_hex(snapshot.normalized_primary_build_block),
            "marker_hex": save._bytes_to_hex(snapshot.primary_build_block[save.PARTS_MARKER_OFFSET:save.PARTS_MARKER_OFFSET + 4]),
            "performance_levels": {name: int(value) for name, value in snapshot.performance_levels},
            "primary_visual_fields": {name: value for name, value in snapshot.primary_visual_fields},
        },
        "optional_visual_sidecar": None if sidecar is None else {
            "owned_record_abs_off": sidecar.owned_record_abs_off,
            "owned_record_signature_clone_hex": save._bytes_to_hex(sidecar.owned_record_signature_clone),
            "owned_record_location_bits": sidecar.owned_record_location_bits,
            "owned_record_misc_bits": sidecar.owned_record_misc_bits,
            "sidecar_parts_slot_offset": sidecar.sidecar_parts_slot_offset,
            "sidecar_parts_slot": sidecar.sidecar_parts_slot,
            "sidecar_block_abs_off": sidecar.sidecar_block_abs_off,
            "normalized_sidecar_build_block_hex": save._bytes_to_hex(sidecar.normalized_sidecar_build_block),
            "sidecar_marker_hex": save._bytes_to_hex(
                sidecar.sidecar_build_block[save.PARTS_MARKER_OFFSET:save.PARTS_MARKER_OFFSET + 4]
            ),
        },
        "requires_unresolved_global_visual_state": snapshot.requires_unresolved_global_visual_state,
        "global_visual_table": {
            "base_offset": save.VISUAL_TABLE_BASE_OFFSET,
            "entry_count": len(snapshot.global_visual_table_entries),
            "stride": save.VISUAL_TABLE_ENTRY_STRIDE,
            "default_value": save.VISUAL_TABLE_DEFAULT_VALUE,
            "entries_hex": tuple(save._bytes_to_hex(entry) for entry in snapshot.global_visual_table_entries),
            "uniform_value": snapshot.global_visual_table_uniform_value,
            "unique_values": sorted(set(int(value) for value in snapshot.global_visual_table_values)),
            "values_hex": " ".join(f"{value:02X}" for value in snapshot.global_visual_table_values),
            "mode_offset": snapshot.global_visual_table_mode_offset,
            "mode_uniform_value": snapshot.global_visual_table_mode_uniform_value,
            "mode_tail_value": snapshot.global_visual_table_mode_tail_value,
            "mode_unique_values": sorted(set(int(value) for value in snapshot.global_visual_table_mode_values)),
            "mode_values_hex": " ".join(f"{value:02X}" for value in snapshot.global_visual_table_mode_values),
        },
    }


def _read_parts_block_bytes(
    save: SnapshotExportSave,
    parts_slot: int,
    allow_placeholder_marker: bool = False,
) -> bytes:
    """Read raw bytes for a validated parts block."""

    slot = int(parts_slot)
    abs_off = save._parts_block_abs_off(slot)
    save._parts_block_marker(slot, allow_placeholder_marker=allow_placeholder_marker)
    return bytes(save.data[abs_off:abs_off + save.PARTS_BLOCK_SIZE])


def _normalize_parts_block(save: SnapshotExportSave, raw_block: bytes) -> bytes:
    """Return a parts block with the slot marker zeroed for snapshot storage."""

    normalized = bytearray(raw_block)
    normalized[save.PARTS_MARKER_OFFSET:save.PARTS_MARKER_OFFSET + 4] = b"\x00\x00\x00\x00"
    return bytes(normalized)


def _visual_table_entries(save: SnapshotExportSave) -> Tuple[bytes, ...]:
    """Return raw visual table entries from the save buffer."""

    entries: List[bytes] = []
    start = save.VISUAL_TABLE_BASE_OFFSET
    for idx in range(save.VISUAL_TABLE_ENTRY_COUNT):
        off = start + idx * save.VISUAL_TABLE_ENTRY_STRIDE
        end = off + save.VISUAL_TABLE_ENTRY_STRIDE
        if end > len(save.data):
            break
        entries.append(bytes(save.data[off:end]))
    return tuple(entries)


def _visual_table_values(save: SnapshotExportSave, value_offset: Optional[int] = None) -> Tuple[int, ...]:
    """Return one byte value from each visual table entry."""

    if value_offset is None:
        value_offset = save.VISUAL_TABLE_LEGACY_VALUE_OFFSET
    values: List[int] = []
    start = save.VISUAL_TABLE_BASE_OFFSET
    for idx in range(save.VISUAL_TABLE_ENTRY_COUNT):
        off = start + idx * save.VISUAL_TABLE_ENTRY_STRIDE + int(value_offset)
        if off >= len(save.data):
            break
        values.append(save._read_u8(off))
    return tuple(values)


def _is_visual_table_tail_entry(save: SnapshotExportSave, entry: bytes) -> bool:
    """Return whether the last visual table entry is the observed tail entry."""

    return (
        len(entry) == save.VISUAL_TABLE_ENTRY_STRIDE
        and entry[3] != 0xFF
        and entry[7] != 0xFF
    )


def _effective_visual_table_entries(
    save: SnapshotExportSave,
    entries: Tuple[bytes, ...],
) -> Tuple[bytes, ...]:
    """Return visual table entries excluding the special tail entry when present."""

    if entries and _is_visual_table_tail_entry(save, entries[-1]):
        return entries[:-1]
    return entries


def _entry_probe_values(entries: Tuple[bytes, ...], value_offset: int) -> Tuple[int, ...]:
    """Return probe values at one offset from a sequence of visual table entries."""

    return tuple(int(entry[int(value_offset)]) for entry in entries if len(entry) > int(value_offset))


def _uniform_value(values: Tuple[int, ...]) -> Optional[int]:
    """Return the shared value when all entries match, otherwise None."""

    if not values:
        return None
    first = values[0]
    return first if all(value == first for value in values) else None


def _primary_visual_summary(save: SnapshotExportSave, raw_block: bytes) -> Tuple[Tuple[str, str], ...]:
    """Summarize confirmed primary visual fields from a parts block."""

    summary: List[Tuple[str, str]] = []
    for label, rel_off, size in save.PRIMARY_VISUAL_FIELDS:
        value = save._bytes_to_hex(raw_block[rel_off:rel_off + size])
        summary.append((label, value))
    return tuple(summary)


def _detect_visual_sidecar(
    save: SnapshotExportSave,
    record: OwnedCarRecord,
) -> Optional[VisualSidecarTemplate]:
    """Detect the optional +1 visual sidecar owned record and parts block."""

    next_off = record.abs_off + save.CAREER_VEHICLE_SIZE
    try:
        raw = save._read_owned_record_raw(next_off)
    except ValueError:
        return None
    car_number = struct.unpack_from("<I", raw, 0)[0]
    signature = raw[save.CAREER_VEHICLE_SIGNATURE_OFFSET:save.CAREER_VEHICLE_SIGNATURE_OFFSET + save.CAREER_VEHICLE_SIGNATURE_SIZE]
    location_bits = struct.unpack_from("<H", raw, save.CAREER_VEHICLE_FLAGS_OFFSET)[0]
    misc_bits = struct.unpack_from("<H", raw, save.CAREER_VEHICLE_FLAGS2_OFFSET)[0]
    parts_slot = raw[save.CAREER_VEHICLE_PARTS_SLOT_OFFSET]
    career_slot = raw[save.CAREER_VEHICLE_SLOT_OFFSET]
    if car_number != save.EMPTY_CAR_NUMBER:
        return None
    if signature != record.signature:
        return None
    if location_bits != save.MY_CARS_FLAG or career_slot != save.EMPTY_CAREER_SLOT:
        return None
    if parts_slot != record.parts_slot + 1:
        return None
    raw_block = _read_parts_block_bytes(save, parts_slot, allow_placeholder_marker=True)
    return VisualSidecarTemplate(
        owned_record_abs_off=next_off,
        owned_record_signature_clone=bytes(signature),
        owned_record_location_bits=location_bits,
        owned_record_misc_bits=misc_bits,
        sidecar_parts_slot_offset=1,
        sidecar_parts_slot=parts_slot,
        sidecar_block_abs_off=save._parts_block_abs_off(parts_slot),
        owned_record_raw=raw,
        sidecar_build_block=raw_block,
        normalized_sidecar_build_block=_normalize_parts_block(save, raw_block),
    )
