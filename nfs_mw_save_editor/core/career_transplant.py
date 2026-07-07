"""Career progression transplant.

This module owns the future donor-save -> user-save career progression path.
It is deliberately scoped around the progression-vs-property split: donor bytes
come only from named progression spans, while user-owned property such as active
car identity, cash, alias, vehicles, parts, garage, Junkman inventory, and
save-tail integrity remains outside this module's copy map.

The span map comes from the 2026-07-07 reverse-engineering pass over the
32-save blacklist ladder and engine symbol/decompilation notes captured in
AGENT_CONTEXT.md. The "post_race_belt" span (uncharted bytes after the race
table plus the global visual table) was added after the first in-game test:
performance-shop tier unlocks did not follow the transplant without it.
Copying the visual table is harmless per the April 2026 injection fidelity
tests. The belt deliberately STOPS at 0x5739: the Junkman token inventory is
a fixed array of 63 12-byte slots at 0x5739..0x5A2D (empirically stable
across all saves) and is user property — the first cut of the belt leaked
donor tokens into it (caught during in-game validation). The former "tbd_57b1"/
"tbd_57b9" singles were that array's slot 10 (type/count bytes) and were
removed from the copy map for the same reason. Two invariants are fixed here for future tests and review:
the game-section MD5 at 0x34 travels with the copied game section verbatim, and
this module never recomputes checksums. The existing editor save path remains
responsible for the file-tail MD5 when the user writes the modified save.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Protocol, Tuple

from core.models import CareerTransplantPlan, OwnedCarRecord

EXPECTED_SAVE_SIZE = 0xF86C
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
    (0x403D, 0x42A9, "difficulty_flags_sms"),
    (0x42B9, 0x5241, "race_table"),
    (0x5241, 0x5739, "post_race_belt"),
    (0x5B41, 0x5B42, "tbd_5b41"),
    (0x5B62, 0x5B64, "tbd_5b62"),
    (0x5C71, 0x5C72, "tbd_5c71"),
    (0x5C73, 0x5C74, "tbd_5c73"),
    (0x793D, 0x795D, "tbd_793d_block"),
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

    Non-fatal warnings are evaluated only after the refusal ladder: donor
    CurrentBin outside ``DONOR_STAGE_MIN_BIN..DONOR_STAGE_MAX_BIN`` and user
    active career pointer invalid. The planner performs no writes.
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

    return CareerTransplantPlan(
        refusal_reason=refusal_reason,
        warnings=tuple(warnings),
        donor_bin=donor_bin,
        spans_total_bytes=spans_total_bytes,
    )


def apply_career_transplant(
    save: CareerTransplantSave,
    donor_data: bytes,
) -> None:
    """Apply a planned career-stage transplant to the user save buffer.

    The implementation replans through ``save.plan_career_transplant`` so
    SaveFile delegates and instance monkeypatches keep the same self-call
    semantics as snapshot injection. It raises
    ``ValueError(plan.refusal_reason)`` when the plan refused, leaving the
    buffer byte-identical. Otherwise it copies ``TRANSPLANT_SPANS`` from donor
    to user in order and performs no other mutation or checksum recomputation.
    """

    plan = save.plan_career_transplant(donor_data)
    if plan.refusal_reason:
        raise ValueError(plan.refusal_reason)
    for start, end, _label in TRANSPLANT_SPANS:
        save.data[start:end] = donor_data[start:end]
