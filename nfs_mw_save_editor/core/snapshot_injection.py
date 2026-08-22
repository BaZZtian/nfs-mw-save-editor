"""Snapshot injection planner and writer.

This module is intended to own the snapshot-entry -> save-file direction:
planning where a library entry can be injected and writing the selected
owned-car / parts / pursuit data through a passed save object. It must not
import SaveFile. The Protocols below document the exact SaveFile surface this
module uses, so instance-level monkeypatches in the characterization tests
continue to intercept allocator calls.
"""

from __future__ import annotations

import struct
from typing import Dict, List, Optional, Protocol, Set, Tuple

from core.models import (
    CareerSlotStatus,
    OwnedCarRecord,
    OwnedCarSlotStatus,
    PartsSlotStatus,
    SnapshotInjectionPlan,
    SnapshotLibraryEntry,
)


_NO_NATIVE_ROW_REFUSAL = "No empty owned-car row inside the native car registry"


class SnapshotInjectionFormat(Protocol):
    """Format constants required by snapshot injection helpers.

    SaveFile remains the authoritative source for these values. SaveFile class
    delegates can pass ``cls``; instance delegates can pass ``self``.
    """

    CAREER_FLAG: int
    PINK_SLIP_FLAG: int
    MY_CARS_FLAG: int
    EMPTY_CAREER_SLOT: int
    EMPTY_CAR_NUMBER: int
    CAREER_VEHICLE_SIZE: int
    CAREER_VEHICLE_SIGNATURE_SIZE: int
    CAREER_VEHICLE_SIGNATURE_OFFSET: int
    CAREER_VEHICLE_FLAGS_OFFSET: int
    CAREER_VEHICLE_FLAGS2_OFFSET: int
    CAREER_VEHICLE_PARTS_SLOT_OFFSET: int
    CAREER_VEHICLE_SLOT_OFFSET: int
    CAREER_VEHICLE_SENTINEL: bytes
    CAREER_VEHICLE_SLOT_COUNT: int
    CAR_NUMBER_SLOT_BASE: int
    PARTS_BLOCK_SIZE: int
    PARTS_MARKER_OFFSET: int
    EMPTY_PARTS_BLOCK_MARKER: bytes


class SnapshotInjectionSave(SnapshotInjectionFormat, Protocol):
    """SaveFile surface required to plan and perform snapshot injection."""

    data: bytearray

    def get_owned_car_slot_statuses(
        self,
        *,
        reserved_abs_offs: Optional[Set[int]] = None,
    ) -> List[OwnedCarSlotStatus]:
        """Return owned-car allocator statuses, honoring staged reservations."""
        ...

    def get_parts_slot_statuses(
        self,
        *,
        reserved_parts_slots: Optional[Set[int]] = None,
    ) -> List[PartsSlotStatus]:
        """Return parts-block allocator statuses, honoring staged reservations."""
        ...

    def get_career_slot_statuses(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
        cleared_slots: Optional[Set[int]] = None,
        reserved_slots: Optional[Set[int]] = None,
    ) -> List[CareerSlotStatus]:
        """Return career-slot allocator statuses, honoring staged reservations."""
        ...

    def count_career_like_owned_records(
        self,
        *,
        location_overrides: Optional[Dict[int, int]] = None,
        career_slot_overrides: Optional[Dict[int, int]] = None,
    ) -> int:
        """Count current/projected Career and Pink Slip owned records."""
        ...

    def career_pool_warning_text(self, career_like_count: int, *, projected: bool = False) -> Optional[str]:
        """Return the full-career-pool warning text, if the count requires one."""
        ...

    def _parts_block_abs_off(self, parts_slot: int) -> int:
        """Return the absolute offset for a parts block."""
        ...

    def clear_pursuit_slot(self, career_slot: int) -> None:
        """Canonicalize the linked pursuit slot before Career injection."""
        ...

    def get_active_career_record(self) -> Optional[OwnedCarRecord]:
        """Return the active Career/Pink Slip record, if it is valid."""
        ...

    def ensure_active_career_pointer_valid(self) -> int:
        """Repair the active Career pointer after injecting a Career car."""
        ...

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
        """Plan snapshot injection through SaveFile's public delegate."""
        ...


def snapshot_target_location_bits(
    save_format: SnapshotInjectionFormat,
    snapshot: SnapshotLibraryEntry,
    target_mode: str,
) -> int:
    """Return the owned-record location bits for the requested injection target."""

    target = str(target_mode)
    if target == "my_cars":
        return save_format.MY_CARS_FLAG
    if target != "career":
        raise ValueError(f"Unsupported injector target: {target}")

    template = snapshot.primary_owned_record_template
    source_flags = int(template.location_bits)
    source_kind = " ".join(
        str(template.source_kind or snapshot.source_kind or "").strip().lower().split()
    )
    if source_flags == (save_format.CAREER_FLAG | save_format.PINK_SLIP_FLAG) or source_kind == "pink slip":
        return save_format.CAREER_FLAG | save_format.PINK_SLIP_FLAG
    return save_format.CAREER_FLAG


def plan_snapshot_injection(
    save: SnapshotInjectionSave,
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
    """Plan snapshot injection without mutating the save buffer."""

    target = str(target_mode)
    warnings: List[str] = []
    refusal: Optional[str] = None
    target_location_bits: Optional[int] = None
    target_career_slot: Optional[int] = None
    target_owned_abs_off: Optional[int] = None
    target_parts_slot: Optional[int] = None
    target_car_number: Optional[int] = None
    target_sidecar_owned_abs_off: Optional[int] = None
    target_sidecar_parts_slot: Optional[int] = None

    if target not in ("my_cars", "career"):
        refusal = f"Unsupported injector target: {target}"
    else:
        target_location_bits = snapshot_target_location_bits(save, snapshot, target)
        if snapshot.has_visual_sidecar:
            if snapshot.optional_visual_sidecar is None:
                refusal = "Snapshot sidecar payload is missing"
            elif snapshot.optional_visual_sidecar.sidecar_parts_slot_offset != 1:
                refusal = "Only +1 sidecar snapshots are supported"

        if refusal is None:
            owned_candidates = save.get_owned_car_slot_statuses(reserved_abs_offs=reserved_owned_abs_offs)
            live_car_numbers = {
                int(slot.car_number)
                for slot in owned_candidates
                if int(slot.car_number) != save.EMPTY_CAR_NUMBER
            }
            number_collides = False
            if snapshot.has_visual_sidecar:
                pairs = _adjacent_owned_slot_pairs(save, owned_candidates)
                primary_owned, sidecar_owned, target_car_number, number_collides = _choose_owned_target(
                    save, pairs, live_car_numbers
                )
                if primary_owned is None or sidecar_owned is None:
                    if pairs:
                        refusal = _NO_NATIVE_ROW_REFUSAL
                    elif any(slot.reusable for slot in owned_candidates[:-1]):
                        refusal = "No adjacent empty owned-car slot for sidecar"
                    else:
                        refusal = "No validated empty owned-car slots available"
                else:
                    target_owned_abs_off = primary_owned.abs_off
                    target_sidecar_owned_abs_off = sidecar_owned.abs_off
            else:
                singles = [(slot, None) for slot in owned_candidates if slot.reusable]
                primary_owned, _unused, target_car_number, number_collides = _choose_owned_target(
                    save, singles, live_car_numbers
                )
                if primary_owned is None:
                    refusal = _NO_NATIVE_ROW_REFUSAL if singles else "No validated empty owned-car slots available"
                else:
                    target_owned_abs_off = primary_owned.abs_off
            if refusal is None and number_collides:
                # Every free row's native number is held by a hand-numbered
                # record. Writing anyway would duplicate a number, and the game
                # resolves duplicates to the first match - one of the two cars
                # becomes unreachable. No half-broken writes.
                refusal = (
                    f"Car number {target_car_number} belongs to owned-car row {primary_owned.slot_index} "
                    "but a live record already uses it - free that number or repair the save"
                )

        if refusal is None:
            parts_candidates = save.get_parts_slot_statuses(reserved_parts_slots=reserved_parts_slots)
            if snapshot.has_visual_sidecar:
                primary_parts, sidecar_parts, saw_primary_parts = _find_adjacent_parts_slot_pair(parts_candidates)
                if primary_parts is None or sidecar_parts is None:
                    refusal = (
                        "No adjacent empty parts slot for sidecar"
                        if saw_primary_parts else
                        "No validated empty parts slots available"
                    )
                else:
                    target_parts_slot = primary_parts.parts_slot
                    target_sidecar_parts_slot = sidecar_parts.parts_slot
            else:
                reusable_parts = [slot for slot in parts_candidates if slot.reusable]
                if not reusable_parts:
                    refusal = "No validated empty parts slots available"
                else:
                    target_parts_slot = reusable_parts[0].parts_slot

        if refusal is None and target == "career":
            career_candidates = save.get_career_slot_statuses(
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
            if refusal is None:
                projected_count = (
                    save.count_career_like_owned_records(
                        location_overrides=location_overrides,
                        career_slot_overrides=career_slot_overrides,
                    )
                    + len({int(slot) for slot in (reserved_career_slots or set())})
                    + 1
                )
                warning = save.career_pool_warning_text(projected_count, projected=True)
                if warning is not None:
                    warnings.append(warning)

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
        target_car_number=(target_car_number if refusal is None else None),
        target_sidecar_owned_abs_off=target_sidecar_owned_abs_off,
        target_sidecar_parts_slot=target_sidecar_parts_slot,
    )


def inject_snapshot(
    save: SnapshotInjectionSave,
    snapshot: SnapshotLibraryEntry,
    target_mode: str,
    *,
    desired_career_slot: Optional[int] = None,
) -> SnapshotInjectionPlan:
    """Apply a validated snapshot-injection plan to the save buffer."""

    plan = save.plan_snapshot_injection(snapshot, target_mode, desired_career_slot=desired_career_slot)
    if plan.refusal_reason:
        raise ValueError(plan.refusal_reason)
    if plan.target_owned_abs_off is None or plan.target_parts_slot is None:
        raise ValueError("Snapshot injector plan did not produce target owned/parts slots")
    if plan.target_car_number is None:
        raise ValueError("Snapshot injector plan did not produce a native car number")
    sidecar = snapshot.optional_visual_sidecar if snapshot.has_visual_sidecar else None
    if target_mode == "career":
        if plan.target_career_slot is None:
            raise ValueError("Career injection requires an allocated career slot")
        save.clear_pursuit_slot(plan.target_career_slot)
    _write_parts_block_for_slot_with_marker(
        save,
        plan.target_parts_slot,
        snapshot.normalized_primary_build_block,
        placeholder_marker=False,
    )
    if sidecar is not None:
        if plan.target_sidecar_owned_abs_off is None or plan.target_sidecar_parts_slot is None:
            raise ValueError("Sidecar snapshot plan did not produce adjacent sidecar slots")
        _write_parts_block_for_slot_with_marker(
            save,
            plan.target_sidecar_parts_slot,
            sidecar.normalized_sidecar_build_block,
            placeholder_marker=True,
        )
    _write_owned_car_record(
        save,
        plan.target_owned_abs_off,
        car_number=plan.target_car_number,
        signature=snapshot.primary_owned_record_template.signature,
        location_bits=plan.target_location_bits,
        misc_bits=plan.target_misc_bits,
        parts_slot=plan.target_parts_slot,
        career_slot=(plan.target_career_slot if plan.target_career_slot is not None else save.EMPTY_CAREER_SLOT),
    )
    if sidecar is not None:
        _write_owned_car_record(
            save,
            plan.target_sidecar_owned_abs_off,
            car_number=save.EMPTY_CAR_NUMBER,
            signature=sidecar.owned_record_signature_clone,
            location_bits=sidecar.owned_record_location_bits,
            misc_bits=sidecar.owned_record_misc_bits,
            parts_slot=plan.target_sidecar_parts_slot,
            career_slot=save.EMPTY_CAREER_SLOT,
        )
    if target_mode == "career" and save.get_active_career_record() is None:
        save.ensure_active_career_pointer_valid()
    return plan


def _write_owned_car_record(
    save: SnapshotInjectionSave,
    abs_off: int,
    *,
    car_number: int,
    signature: bytes,
    location_bits: int,
    misc_bits: int,
    parts_slot: int,
    career_slot: int,
) -> None:
    """Write one canonical owned-car record at an allocated owned slot."""

    if len(signature) != save.CAREER_VEHICLE_SIGNATURE_SIZE:
        raise ValueError(f"owned-car signature must be {save.CAREER_VEHICLE_SIGNATURE_SIZE} bytes")
    payload = bytearray(save.CAREER_VEHICLE_SIZE)
    struct.pack_into("<I", payload, 0x00, int(car_number) & 0xFFFFFFFF)
    payload[save.CAREER_VEHICLE_SIGNATURE_OFFSET:save.CAREER_VEHICLE_SIGNATURE_OFFSET + save.CAREER_VEHICLE_SIGNATURE_SIZE] = bytes(signature)
    struct.pack_into("<H", payload, save.CAREER_VEHICLE_FLAGS_OFFSET, int(location_bits) & 0xFFFF)
    struct.pack_into("<H", payload, save.CAREER_VEHICLE_FLAGS2_OFFSET, int(misc_bits) & 0xFFFF)
    payload[save.CAREER_VEHICLE_PARTS_SLOT_OFFSET] = int(parts_slot) & 0xFF
    payload[save.CAREER_VEHICLE_SLOT_OFFSET] = int(career_slot) & 0xFF
    payload[0x12:0x14] = save.CAREER_VEHICLE_SENTINEL
    save.data[abs_off:abs_off + save.CAREER_VEHICLE_SIZE] = payload


def native_car_number_for_slot(
    save_format: SnapshotInjectionFormat,
    slot_index: int,
) -> Optional[int]:
    """Return the car number the game would give a record in this registry row.

    The native allocator is positional: car_number = 81 + physical row, rows
    0..118 -> 81..199. Returns None for rows outside that native range, which
    the injector treats as "no legal number", never as a fallback counter.
    """

    slot = int(slot_index)
    if slot < 0 or slot >= int(save_format.CAREER_VEHICLE_SLOT_COUNT):
        return None
    return int(save_format.CAR_NUMBER_SLOT_BASE) + slot


def _choose_owned_target(
    save_format: SnapshotInjectionFormat,
    candidates: List[Tuple[OwnedCarSlotStatus, Optional[OwnedCarSlotStatus]]],
    live_car_numbers: Set[int],
) -> Tuple[Optional[OwnedCarSlotStatus], Optional[OwnedCarSlotStatus], Optional[int], bool]:
    """Pick the first candidate row whose native number is free.

    Returns ``(primary, sidecar, car_number, collides)``. Drifted saves may
    contain hand-numbered rows. If every legal number is occupied, the first
    candidate is returned with ``collides=True`` for a specific refusal.
    """

    fallback: Optional[Tuple[OwnedCarSlotStatus, Optional[OwnedCarSlotStatus], int, bool]] = None
    for primary, sidecar in candidates:
        car_number = native_car_number_for_slot(save_format, primary.slot_index)
        if car_number is None:
            continue
        if car_number not in live_car_numbers:
            return primary, sidecar, car_number, False
        if fallback is None:
            fallback = (primary, sidecar, car_number, True)
    if fallback is not None:
        return fallback
    return None, None, None, False



def _write_parts_block_for_slot_with_marker(
    save: SnapshotInjectionSave,
    parts_slot: int,
    normalized_block: bytes,
    *,
    placeholder_marker: bool,
) -> None:
    """Write a normalized parts block and restore the target slot marker."""

    slot = int(parts_slot)
    if len(normalized_block) != save.PARTS_BLOCK_SIZE:
        raise ValueError(f"normalized parts block must be exactly 0x{save.PARTS_BLOCK_SIZE:X} bytes")
    abs_off = save._parts_block_abs_off(slot)
    payload = bytearray(normalized_block)
    marker = save.EMPTY_PARTS_BLOCK_MARKER if placeholder_marker else bytes((slot & 0xFF, 0xCD, 0xCD, 0xCD))
    payload[save.PARTS_MARKER_OFFSET:save.PARTS_MARKER_OFFSET + 4] = marker
    save.data[abs_off:abs_off + save.PARTS_BLOCK_SIZE] = payload


def _adjacent_owned_slot_pairs(
    save_format: SnapshotInjectionFormat,
    statuses: List[OwnedCarSlotStatus],
) -> List[Tuple[OwnedCarSlotStatus, Optional[OwnedCarSlotStatus]]]:
    """Return every adjacent reusable owned-slot pair for sidecar snapshots."""

    pairs: List[Tuple[OwnedCarSlotStatus, Optional[OwnedCarSlotStatus]]] = []
    for idx, status in enumerate(statuses[:-1]):
        if not status.reusable:
            continue
        nxt = statuses[idx + 1]
        if nxt.reusable and nxt.abs_off == status.abs_off + save_format.CAREER_VEHICLE_SIZE:
            pairs.append((status, nxt))
    return pairs


def _find_adjacent_parts_slot_pair(
    statuses: List[PartsSlotStatus],
) -> Tuple[Optional[PartsSlotStatus], Optional[PartsSlotStatus], bool]:
    """Return the first adjacent reusable parts-slot pair for sidecar snapshots."""

    saw_primary = False
    for idx, status in enumerate(statuses[:-1]):
        if not status.reusable:
            continue
        saw_primary = True
        nxt = statuses[idx + 1]
        if nxt.reusable and nxt.parts_slot == status.parts_slot + 1:
            return status, nxt, saw_primary
    return None, None, saw_primary
