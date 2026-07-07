"""Read-only career progress parsing: milestone table + race table.

Complements core/career_transplant.py (which copies these regions opaquely)
with structured views for the UI. Two different addressing rules apply and
they are the reason this module exists:

- The race table (GRaceSaveInfo[248] at 0x42C1) lies OUTSIDE the game section
  and does not float: fixed offsets are correct.
- The milestone table (GMilestone[]) lives INSIDE the self-checksummed game
  section whose persistent-activity prefix is variable-size, so its offset
  floats per save (observed bases 0x3D4..0x524). Fixed-offset reads there are
  WRONG; the table is located by anchoring on the SavedTimerInfo name ASCII
  ("cellusage" = timer[0].name at +0xC) and walking timer/type counts taken
  from the SavedGameplayDataHeader, never hardcoded.

This module performs no writes and no checksum work.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

from core.career_transplant import (
    EXPECTED_SAVE_SIZE,
    GAME_MAGIC,
    GAME_MAGIC_OFFSET,
    GAME_SECTION_END,
    GAME_SECTION_START,
    RACE_DONE_MASK,
    RACE_RECORD_COUNT,
    RACE_RECORD_SIZE,
    RACE_TABLE_OFFSET,
)
from core.race_chapters import resolve_offering
from core.race_names import resolve_event_id

# SavedGameplayDataHeader counts (u32 each, from 0x4C): mNumPersistent,
# mNumSavedTimers, mNumMilestoneTypes, mNumMilestoneRecords,
# mNumSpeedTrapRecords, ...
HEADER_TIMER_COUNT_OFFSET = 0x50
HEADER_TYPE_COUNT_OFFSET = 0x54
HEADER_MILESTONE_COUNT_OFFSET = 0x58
HEADER_SPEEDTRAP_COUNT_OFFSET = 0x5C

TIMER_RECORD_SIZE = 0x20
TIMER_NAME_REL = 0x0C
TYPE_RECORD_SIZE = 0x10
MILESTONE_RECORD_SIZE = 0x14
ANCHOR_TIMER_NAME = b"cellusage"

# Sanity ceilings for header counts: a corrupt header must fail parsing, not
# send the walk beyond the section (observed values are 8 / 30 / 55).
MAX_TIMER_COUNT = 64
MAX_TYPE_COUNT = 128
MAX_MILESTONE_COUNT = 256
MAX_SPEEDTRAP_COUNT = 128

SPEEDTRAP_RECORD_SIZE = 0x14
# Ladder-verified (reverse-engineering analysis, 2026-07-07): the packed low word is a
# monotonic 0..5 progress counter shared by all of a bin's speedtrap records;
# 5 = the bin's speedtrap milestones are complete. The game displays "n/5".
SPEEDTRAP_COMPLETE_COUNT = 5

# GMilestone.State observed across the 32-save ladder: 1 = active (recorded
# still zero), 4 = awarded (recorded values populated). Other values exist in
# principle; only 4 is treated as awarded.
MILESTONE_STATE_AWARDED = 4

# Race-table flag semantics from ladder transitions: base 0x04/0x10/0x14,
# completion sets 0x02|0x08 (career events end 0x1E, prologue events 0x02 —
# hence the completion test uses only bit 0x02 for chapter 16).
RACE_FLAG_PROLOGUE_DONE = 0x02

PROLOGUE_CHAPTER = 16
CHALLENGE_CHAPTER = 19
SPECIAL_CHAPTERS = (20, 21, 99)

# CareerSettings special flags (u16 at 0x4040, in the serialized block after
# the game section). Empirical across the 32-save ladder: 0x0803 all career,
# bit 0x1000 set once the Razor race is won (Final Pursuit save), 0x0040
# added on the 100% GAME OVER save. CurrentBin stays 1 through the endgame,
# so this bit is the only save-side "Razor defeated" signal.
SPECIAL_FLAGS_OFFSET = 0x4040
FLAG_ENDGAME = 0x1000

_UDECFIX16_UNIT = 256.0


@dataclass(frozen=True)
class MilestoneRecord:
    index: int
    type_key: int
    challenge_key: int
    state: int
    flags: int
    bin_number: int
    required_value: float
    recorded_value: float

    @property
    def is_awarded(self) -> bool:
        return self.state == MILESTONE_STATE_AWARDED


@dataclass(frozen=True)
class SpeedtrapRecord:
    index: int
    bin_number: int
    counter: int
    trap_hash: int
    required_speed: float
    best_speed: float

    @property
    def is_complete(self) -> bool:
        return self.counter >= SPEEDTRAP_COMPLETE_COUNT


@dataclass(frozen=True)
class RaceRecord:
    index: int
    race_hash: int
    event_id: Optional[str]
    flags: int
    high_score: int
    top_speed: float
    average_speed: float
    # Ladder-derived offering data (core/race_chapters.py); None/False for
    # slots outside the career schedule (prologue-static, challenge, cut).
    offering_chapter: Optional[int] = None
    is_boss_race: bool = False

    @property
    def chapter(self) -> Optional[int]:
        """Route-family chapter from the EventID prefix (NOT where it is
        offered — use offering_chapter for play-order grouping)."""
        if not self.event_id:
            return None
        return int(self.event_id.split(".", 1)[0])

    @property
    def is_reversed(self) -> bool:
        return bool(self.event_id) and self.event_id.endswith(".r")

    @property
    def is_completed(self) -> bool:
        if self.chapter == PROLOGUE_CHAPTER:
            return bool(self.flags & RACE_FLAG_PROLOGUE_DONE)
        return (self.flags & RACE_DONE_MASK) == RACE_DONE_MASK


def _read_u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def is_endgame(data: bytes) -> Optional[bool]:
    """True once the Razor race is won; None when the buffer is not a save."""

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    flags = int.from_bytes(data[SPECIAL_FLAGS_OFFSET:SPECIAL_FLAGS_OFFSET + 2], "little")
    return bool(flags & FLAG_ENDGAME)


def _locate_tables(data: bytes) -> Optional[Tuple[int, int, int, int]]:
    """(milestone_base, n_milestones, speedtrap_base, n_traps) or None.

    Anchors on timer[0].name inside the floating game-section interior and
    walks header counts; refuses on any implausibility.
    """

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    if bytes(data[GAME_MAGIC_OFFSET:GAME_MAGIC_OFFSET + len(GAME_MAGIC)]) != GAME_MAGIC:
        return None

    num_timers = _read_u32(data, HEADER_TIMER_COUNT_OFFSET)
    num_types = _read_u32(data, HEADER_TYPE_COUNT_OFFSET)
    num_milestones = _read_u32(data, HEADER_MILESTONE_COUNT_OFFSET)
    num_traps = _read_u32(data, HEADER_SPEEDTRAP_COUNT_OFFSET)
    if not (0 < num_timers <= MAX_TIMER_COUNT):
        return None
    if not (0 < num_types <= MAX_TYPE_COUNT):
        return None
    if not (0 < num_milestones <= MAX_MILESTONE_COUNT):
        return None
    if not (0 <= num_traps <= MAX_SPEEDTRAP_COUNT):
        return None

    # timer[0].name — require the terminating NUL of the char[20] field so a
    # stray substring inside the persistent pool cannot masquerade as anchor.
    anchor = bytes(data).find(
        ANCHOR_TIMER_NAME + b"\x00", GAME_SECTION_START, GAME_SECTION_END
    )
    if anchor < 0:
        return None
    timers_base = anchor - TIMER_NAME_REL
    if timers_base < GAME_SECTION_START:
        return None

    milestone_base = (
        timers_base
        + num_timers * TIMER_RECORD_SIZE
        + num_types * TYPE_RECORD_SIZE
    )
    trap_base = milestone_base + num_milestones * MILESTONE_RECORD_SIZE
    if trap_base + num_traps * SPEEDTRAP_RECORD_SIZE > GAME_SECTION_END:
        return None
    return milestone_base, num_milestones, trap_base, num_traps


def parse_milestones(data: bytes) -> Optional[Tuple[MilestoneRecord, ...]]:
    """Parse GMilestone records via the cellusage anchor.

    Returns None when the buffer is not a save, the game-section magic is
    missing, the anchor cannot be found, header counts are implausible, or
    the located tables would leave the game section.
    """

    layout = _locate_tables(data)
    if layout is None:
        return None
    table_base, num_milestones, _trap_base, _num_traps = layout

    records = []
    for k in range(num_milestones):
        base = table_base + k * MILESTONE_RECORD_SIZE
        type_key, challenge_key, state, flags, bin_number, required, recorded = (
            struct.unpack_from("<IIBBHff", data, base)
        )
        records.append(
            MilestoneRecord(
                index=k,
                type_key=type_key,
                challenge_key=challenge_key,
                state=state,
                flags=flags,
                bin_number=bin_number,
                required_value=required,
                recorded_value=recorded,
            )
        )
    return tuple(records)


def parse_speedtraps(data: bytes) -> Optional[Tuple[SpeedtrapRecord, ...]]:
    """Parse the speedtrap milestone table (same anchor walk as milestones)."""

    layout = _locate_tables(data)
    if layout is None:
        return None
    _milestone_base, _num_milestones, trap_base, num_traps = layout

    records = []
    for k in range(num_traps):
        base = trap_base + k * SPEEDTRAP_RECORD_SIZE
        best_bits, packed, trap_hash = struct.unpack_from("<III", data, base)
        required = struct.unpack_from("<f", data, base + 0x10)[0]
        best = struct.unpack("<f", best_bits.to_bytes(4, "little"))[0]
        records.append(
            SpeedtrapRecord(
                index=k,
                bin_number=packed >> 16,
                counter=packed & 0xFFFF,
                trap_hash=trap_hash,
                required_speed=required,
                best_speed=best,
            )
        )
    return tuple(records)


def parse_races(data: bytes) -> Optional[Tuple[RaceRecord, ...]]:
    """Parse the fixed-offset race table; None when the buffer is not a save."""

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    records = []
    for k in range(RACE_RECORD_COUNT):
        base = RACE_TABLE_OFFSET + k * RACE_RECORD_SIZE
        race_hash, flags, high_score, top_speed_raw, avg_speed_raw = (
            struct.unpack_from("<IIIHH", data, base)
        )
        offering = resolve_offering(race_hash)
        records.append(
            RaceRecord(
                index=k,
                race_hash=race_hash,
                event_id=resolve_event_id(race_hash),
                flags=flags,
                high_score=high_score,
                top_speed=top_speed_raw / _UDECFIX16_UNIT,
                average_speed=avg_speed_raw / _UDECFIX16_UNIT,
                offering_chapter=offering[0] if offering else None,
                is_boss_race=bool(offering[1]) if offering else False,
            )
        )
    return tuple(records)
