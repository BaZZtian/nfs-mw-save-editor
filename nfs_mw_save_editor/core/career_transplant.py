"""Career progression transplant with a strict progression/property boundary.

Only named progression spans come from the donor. Cash, alias, vehicles,
parts, garage records, Junkman inventory, and save-tail integrity remain user
property. The post-race span ends at 0x5739, immediately before the fixed
63-record Junkman belt, and excludes car-table and pending-parts artifacts.

The game-section MD5 at 0x34 travels with the copied section. File-tail
integrity is repaired only by the normal save path.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Protocol, Tuple

from core.garage_records import (
    EXPECTED_SAVE_SIZE,
    GARAGE_RECORD_BOUNTY_REL,
    GARAGE_RECORD_COUNT,
    GARAGE_RECORD_SIZE,
    GARAGE_RECORDS_OFFSET,
    SOLD_HISTORY_BOUNTY_OFFSET,
    is_empty_garage_record,
    is_live_garage_record,
)
from core.models import CareerTransplantPlan, OwnedCarRecord
from core.rap_sheet_totals import read_rap_sheet_totals
GAME_SECTION_MD5_OFFSET = 0x0034
GAME_SECTION_START = 0x0044
GAME_SECTION_END = 0x4034
GAME_MAGIC = b"Game"
GAME_MAGIC_OFFSET = GAME_SECTION_START

DONOR_STAGE_MIN_BIN = 1
DONOR_STAGE_MAX_BIN = 15
CURRENT_BIN_OFFSET = 0x4038

RACE_TABLE_OFFSET = 0x42C1
RACE_RECORD_SIZE = 0x10
RACE_RECORD_COUNT = 248
# Completion = both bits observed to be set together on finished events
# across the whole 32-save ladder (flags 0x10 -> 0x1E, 0x04 -> 0x0E).
RACE_DONE_MASK = 0x0A

U32_MAX = 0xFFFFFFFF

# Bounty handling on apply. The modes only diverge on rollback (user total
# above the donor target): keep preserves the earned total, normalize is the
# opt-in that sets SoldHistoryBounty so the rap-sheet total matches the
# target stage (floored at the live-car sum - cars are never touched).
BOUNTY_MODE_KEEP = "keep"
BOUNTY_MODE_NORMALIZE = "normalize"

REFUSAL_USER_SIZE_MISMATCH = "User save size is not 63596 bytes"
REFUSAL_DONOR_SIZE_MISMATCH = "Donor save size is not 63596 bytes"
REFUSAL_DONOR_GAME_MAGIC_MISSING = "Donor game section magic is missing"
REFUSAL_DONOR_GAME_MD5_INVALID = "Donor game section MD5 is invalid"
REFUSAL_USER_GAME_MAGIC_MISSING = "User game section magic is missing"

WARNING_DONOR_BIN_OUT_OF_RANGE = "Donor CurrentBin is outside Blacklist stage range 1..15"
WARNING_USER_ACTIVE_CAREER_POINTER_INVALID = "User active career pointer is invalid"

TransplantSpan = Tuple[int, int, str]

TRANSPLANT_SPANS: Tuple[TransplantSpan, ...] = (
    (0x0034, 0x4034, "game_section"),
    (0x4038, 0x4039, "current_bin"),
    # SMS sort order ends at 0x429D. The following CaseFileName[16] and
    # alignment bytes are user identity, not progression.
    (0x403D, 0x429D, "difficulty_flags_sms"),
    (0x42B9, 0x5241, "race_table"),
    (0x5241, 0x5739, "post_race_belt"),
    (0x5B41, 0x5B42, "tbd_5b41"),
    (0x5B62, 0x5B64, "tbd_5b62"),
)


class CareerTransplantSave(Protocol):
    """SaveFile surface required by career stage transplant."""

    data: bytearray

    def get_active_career_record(self) -> Optional[OwnedCarRecord]:
        """Return the active Career/Pink Slip car record, if it is valid."""
        ...

    def plan_career_transplant(self, donor_data: bytes) -> CareerTransplantPlan:
        """Plan a transplant through SaveFile's public delegate."""
        ...


def read_current_bin(data: bytes) -> Optional[int]:
    """Return the career stage byte, or None when the buffer is not a save."""

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    return int(data[CURRENT_BIN_OFFSET])


def count_completed_races(data: bytes) -> Optional[int]:
    """Count race-table records carrying the completion bits.

    Fixed offsets: the race table lives outside the floating-interior game
    section, so no anchor parsing is needed. Returns None when the buffer is
    not a save.
    """

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    done = 0
    for k in range(RACE_RECORD_COUNT):
        flags = int.from_bytes(
            data[RACE_TABLE_OFFSET + k * RACE_RECORD_SIZE + 4:
                 RACE_TABLE_OFFSET + k * RACE_RECORD_SIZE + 8],
            "little",
        )
        if (flags & RACE_DONE_MASK) == RACE_DONE_MASK:
            done += 1
    return done


def _live_car_bounties(data: bytes) -> Tuple[Tuple[int, int], ...]:
    """(slot_index, bounty) for every live garage record.

    Raises ValueError on a record that is neither empty nor canonically
    live; normalize must never scale a partial car list.
    """

    out = []
    for k in range(GARAGE_RECORD_COUNT):
        base = GARAGE_RECORDS_OFFSET + k * GARAGE_RECORD_SIZE
        raw = bytes(data[base:base + GARAGE_RECORD_SIZE])
        if is_empty_garage_record(raw):
            continue
        if not is_live_garage_record(raw, k):
            raise ValueError(
                f"Garage record {k} is neither empty nor canonically live"
            )
        out.append((k, int.from_bytes(
            raw[GARAGE_RECORD_BOUNTY_REL:GARAGE_RECORD_BOUNTY_REL + 4], "little"
        )))
    return tuple(out)


def _bounty_plan_numbers(
    user_data: bytes, donor_data: bytes
) -> Tuple[int, int, int, int, int, Tuple[Tuple[int, int, int], ...]]:
    """Rap-sheet bounty numbers for the plan preview and both apply modes.

    Returns ``(keep_compensation, user_total, user_live, donor_total,
    normalized_sold, normalized_car_bounties)``. Normalize always lands the
    total EXACTLY on the donor target: when the live-car sum exceeds it, every
    live bounty is scaled proportionally (floored) and the sold history
    carries the rounding remainder; otherwise cars stay untouched and sold
    history is the difference. All zeros/empty when either buffer is not a
    save. Raises ValueError, labeled with the offending side, when either
    garage table holds an unexplained record (fail closed: a partial
    aggregate would feed normalize under-counted numbers).
    """

    try:
        user_totals = read_rap_sheet_totals(user_data)
    except ValueError as exc:
        raise ValueError(f"User garage records are unreadable: {exc}") from exc
    try:
        donor_totals = read_rap_sheet_totals(donor_data)
    except ValueError as exc:
        raise ValueError(f"Donor garage records are unreadable: {exc}") from exc
    if user_totals is None or donor_totals is None:
        return (0, 0, 0, 0, 0, ())
    target = donor_totals.total_bounty
    live = user_totals.live_bounty
    scaled_cars: Tuple[Tuple[int, int, int], ...] = ()
    if live > target:
        scaled = tuple(
            (slot, bounty, bounty * target // live)
            for slot, bounty in _live_car_bounties(user_data)
        )
        scaled_cars = tuple(row for row in scaled if row[1] != row[2])
        normalized_sold = target - sum(new for _slot, _old, new in scaled)
    else:
        normalized_sold = target - live
    return (
        max(0, target - user_totals.total_bounty),
        user_totals.total_bounty,
        live,
        target,
        normalized_sold,
        scaled_cars,
    )


def plan_career_transplant(
    save: CareerTransplantSave,
    donor_data: bytes,
) -> CareerTransplantPlan:
    """Plan a career-stage transplant without mutating the user save.

    Refusal ladder, in order:
    1. user save size mismatch -> ``REFUSAL_USER_SIZE_MISMATCH``.
    2. donor save size mismatch -> ``REFUSAL_DONOR_SIZE_MISMATCH``.
    3. donor game-section magic missing -> ``REFUSAL_DONOR_GAME_MAGIC_MISSING``.
    4. donor game-section MD5 invalid -> ``REFUSAL_DONOR_GAME_MD5_INVALID``.
    5. user game-section magic missing -> ``REFUSAL_USER_GAME_MAGIC_MISSING``.
    6. unexplained garage record on either side -> dynamic reason naming the
       side and slot (the rap-sheet reader's fail-closed ValueError).

    Non-fatal warnings are evaluated only after the refusal ladder: donor
    CurrentBin outside ``DONOR_STAGE_MIN_BIN..DONOR_STAGE_MAX_BIN`` and user
    active career pointer invalid. The planner performs no writes.

    ``bounty_compensation`` reports how much apply will ADD to the user's
    SoldHistoryBounty so the rap-sheet total matches what the donor stage
    implies (0 when the user already has at least the donor's total). This is
    the only write outside TRANSPLANT_SPANS and it never lowers user bounty.
    """

    donor_bin = int(donor_data[CURRENT_BIN_OFFSET]) if len(donor_data) > CURRENT_BIN_OFFSET else 0
    spans_total_bytes = sum(end - start for start, end, _label in TRANSPLANT_SPANS)
    refusal_reason = None
    warnings = []

    if len(save.data) != EXPECTED_SAVE_SIZE:
        refusal_reason = REFUSAL_USER_SIZE_MISMATCH
    elif len(donor_data) != EXPECTED_SAVE_SIZE:
        refusal_reason = REFUSAL_DONOR_SIZE_MISMATCH
    elif bytes(donor_data[GAME_MAGIC_OFFSET:GAME_MAGIC_OFFSET + len(GAME_MAGIC)]) != GAME_MAGIC:
        refusal_reason = REFUSAL_DONOR_GAME_MAGIC_MISSING
    elif (
        hashlib.md5(donor_data[GAME_SECTION_START:GAME_SECTION_END]).digest()
        != bytes(donor_data[GAME_SECTION_MD5_OFFSET:GAME_SECTION_START])
    ):
        refusal_reason = REFUSAL_DONOR_GAME_MD5_INVALID
    elif bytes(save.data[GAME_MAGIC_OFFSET:GAME_MAGIC_OFFSET + len(GAME_MAGIC)]) != GAME_MAGIC:
        refusal_reason = REFUSAL_USER_GAME_MAGIC_MISSING

    if refusal_reason is None:
        if not (DONOR_STAGE_MIN_BIN <= donor_bin <= DONOR_STAGE_MAX_BIN):
            warnings.append(WARNING_DONOR_BIN_OUT_OF_RANGE)
        if save.get_active_career_record() is None:
            warnings.append(WARNING_USER_ACTIVE_CAREER_POINTER_INVALID)

    compensation, user_total, user_live, donor_total, normalized_sold, scaled_cars = (
        0, 0, 0, 0, 0, (),
    )
    if refusal_reason is None:
        try:
            compensation, user_total, user_live, donor_total, normalized_sold, scaled_cars = (
                _bounty_plan_numbers(bytes(save.data), donor_data)
            )
        except ValueError as exc:
            # Unexplained garage record on either side: refuse the whole
            # plan rather than hand normalize under-counted totals.
            refusal_reason = str(exc)
    return CareerTransplantPlan(
        refusal_reason=refusal_reason,
        warnings=tuple(warnings),
        donor_bin=donor_bin,
        spans_total_bytes=spans_total_bytes,
        bounty_compensation=compensation,
        user_total_bounty=user_total,
        user_live_bounty=user_live,
        donor_total_bounty=donor_total,
        normalized_sold_bounty=normalized_sold,
        normalized_car_bounties=scaled_cars,
    )


def apply_career_transplant(
    save: CareerTransplantSave,
    donor_data: bytes,
    bounty_mode: str = BOUNTY_MODE_KEEP,
) -> None:
    """Apply a planned career-stage transplant to the user save buffer.

    The implementation replans through ``save.plan_career_transplant`` so
    SaveFile delegates and instance monkeypatches keep the same self-call
    semantics as snapshot injection. It raises
    ``ValueError(plan.refusal_reason)`` when the plan refused, leaving the
    buffer byte-identical. Otherwise it copies ``TRANSPLANT_SPANS`` from donor
    to user in order, then settles SoldHistoryBounty per ``bounty_mode``:

    - ``keep`` (default): add ``plan.bounty_compensation`` (saturating at
      u32; no-op when 0) - the earned total is never lowered.
    - ``normalize``: land the rap-sheet total EXACTLY on the donor target -
      scale live car bounties per ``plan.normalized_car_bounties`` (only
      populated when the live sum exceeds the target) and SET
      SoldHistoryBounty to ``plan.normalized_sold_bounty``. This is the
      opt-in rollback path; it lowers bounty values, so callers must
      present every change (per-car included) before applying.

    No other mutation and no checksum recomputation.
    """

    if bounty_mode not in (BOUNTY_MODE_KEEP, BOUNTY_MODE_NORMALIZE):
        raise ValueError(f"Unknown bounty mode: {bounty_mode!r}")
    plan = save.plan_career_transplant(donor_data)
    if plan.refusal_reason:
        raise ValueError(plan.refusal_reason)
    for start, end, _label in TRANSPLANT_SPANS:
        save.data[start:end] = donor_data[start:end]
    if bounty_mode == BOUNTY_MODE_NORMALIZE:
        for slot, _old, new in plan.normalized_car_bounties:
            off = (GARAGE_RECORDS_OFFSET + slot * GARAGE_RECORD_SIZE
                   + GARAGE_RECORD_BOUNTY_REL)
            save.data[off:off + 4] = int(new).to_bytes(4, "little")
        sold = min(U32_MAX, int(plan.normalized_sold_bounty))
        save.data[SOLD_HISTORY_BOUNTY_OFFSET:SOLD_HISTORY_BOUNTY_OFFSET + 4] = sold.to_bytes(4, "little")
    elif plan.bounty_compensation > 0:
        sold = int.from_bytes(
            save.data[SOLD_HISTORY_BOUNTY_OFFSET:SOLD_HISTORY_BOUNTY_OFFSET + 4], "little"
        )
        sold = min(U32_MAX, sold + plan.bounty_compensation)
        save.data[SOLD_HISTORY_BOUNTY_OFFSET:SOLD_HISTORY_BOUNTY_OFFSET + 4] = sold.to_bytes(4, "little")
