from __future__ import annotations

import struct
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core import career_progress, career_transplant
from core.race_chapters import RACE_OFFERING, resolve_offering
from core.race_names import RACE_EVENT_IDS, resolve_event_id


# Real hashes from the decoded race table (RE/race_table_decoded.txt).
HASH_1_1_1 = 0xF97E66FB       # career event "1.1.1"
HASH_16_1_1_R = 0x69360B36    # prologue event "16.1.1.r"
HASH_UNNAMED = 0xFE87E90B     # challenge-series slot, no EventID


def _pack_milestone(type_key, challenge_key, state, flags, bin_number, req, rec):
    return struct.pack("<IIBBHff", type_key, challenge_key, state, flags, bin_number, req, rec)


def _pack_speedtrap(bin_number, counter, trap_hash, required, best=0.0):
    best_bits = struct.unpack("<I", struct.pack("<f", best))[0] if best else 0
    return struct.pack(
        "<IIIff", best_bits, (bin_number << 16) | counter, trap_hash, 0.0, required
    )


def _progress_buffer(
    *,
    prefix: int = 0x2A0,
    num_timers: int = 2,
    num_types: int = 3,
    milestones: tuple[bytes, ...] = (),
    speedtraps: tuple[bytes, ...] = (),
    with_anchor: bool = True,
) -> bytearray:
    """Synthetic save with a floating game-section interior.

    ``prefix`` positions the timer array relative to the section start, so
    two different values simulate the per-save float the anchor must absorb.
    """

    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    struct.pack_into("<IIII", data, career_progress.HEADER_TIMER_COUNT_OFFSET,
                     num_timers, num_types, len(milestones), len(speedtraps))

    timers_base = career_transplant.GAME_SECTION_START + prefix
    if with_anchor:
        name_off = timers_base + career_progress.TIMER_NAME_REL
        data[name_off:name_off + len(career_progress.ANCHOR_TIMER_NAME) + 1] = (
            career_progress.ANCHOR_TIMER_NAME + b"\x00"
        )
    table_base = (
        timers_base
        + num_timers * career_progress.TIMER_RECORD_SIZE
        + num_types * career_progress.TYPE_RECORD_SIZE
    )
    for k, raw in enumerate(milestones):
        base = table_base + k * career_progress.MILESTONE_RECORD_SIZE
        data[base:base + career_progress.MILESTONE_RECORD_SIZE] = raw
    trap_base = table_base + len(milestones) * career_progress.MILESTONE_RECORD_SIZE
    for k, raw in enumerate(speedtraps):
        base = trap_base + k * career_progress.SPEEDTRAP_RECORD_SIZE
        data[base:base + career_progress.SPEEDTRAP_RECORD_SIZE] = raw
    return data


def _write_race(data: bytearray, index: int, race_hash: int, flags: int,
                high_score: int = 0, top_raw: int = 0, avg_raw: int = 0) -> None:
    base = career_transplant.RACE_TABLE_OFFSET + index * career_transplant.RACE_RECORD_SIZE
    struct.pack_into("<IIIHH", data, base, race_hash, flags, high_score, top_raw, avg_raw)


# ── milestones ─────────────────────────────────────────────────


def test_parse_milestones_decodes_records_via_anchor():
    ms = (
        _pack_milestone(0x11111111, 0x22222222, 1, 1, 4, 35.0, 0.0),
        _pack_milestone(0x33333333, 0x44444444, 4, 3, 13, 850000.0, 1675000.0),
    )
    records = career_progress.parse_milestones(bytes(_progress_buffer(milestones=ms)))
    assert records is not None and len(records) == 2
    active, awarded = records
    assert active.type_key == 0x11111111
    assert active.bin_number == 4
    assert active.required_value == 35.0
    assert not active.is_awarded
    assert awarded.state == career_progress.MILESTONE_STATE_AWARDED
    assert awarded.is_awarded
    assert awarded.recorded_value == 1675000.0


def test_parse_milestones_absorbs_floating_prefix():
    ms = (_pack_milestone(1, 2, 4, 0, 15, 1.0, 2.0),)
    for prefix in (0x2A0, 0x390, 0x4E0):
        records = career_progress.parse_milestones(
            bytes(_progress_buffer(prefix=prefix, milestones=ms))
        )
        assert records is not None and len(records) == 1, hex(prefix)
        assert records[0].bin_number == 15


def test_parse_milestones_anchor_requires_nul_terminator():
    ms = (_pack_milestone(1, 2, 4, 0, 7, 1.0, 2.0),)
    data = _progress_buffer(prefix=0x390, milestones=ms)
    # Decoy substring without the char[20] NUL, earlier in the section.
    decoy = career_progress.ANCHOR_TIMER_NAME + b"X"
    data[career_transplant.GAME_SECTION_START + 0x40:
         career_transplant.GAME_SECTION_START + 0x40 + len(decoy)] = decoy
    records = career_progress.parse_milestones(bytes(data))
    assert records is not None and records[0].bin_number == 7


def test_parse_milestones_rejects_bad_buffers():
    ms = (_pack_milestone(1, 2, 4, 0, 7, 1.0, 2.0),)
    assert career_progress.parse_milestones(b"\x00" * 100) is None
    no_magic = _progress_buffer(milestones=ms)
    no_magic[career_transplant.GAME_MAGIC_OFFSET:
             career_transplant.GAME_MAGIC_OFFSET + 4] = b"\x00" * 4
    assert career_progress.parse_milestones(bytes(no_magic)) is None
    assert career_progress.parse_milestones(
        bytes(_progress_buffer(milestones=ms, with_anchor=False))
    ) is None


def test_parse_milestones_rejects_implausible_header_counts():
    ms = (_pack_milestone(1, 2, 4, 0, 7, 1.0, 2.0),)
    for field_off, bad in (
        (career_progress.HEADER_TIMER_COUNT_OFFSET, career_progress.MAX_TIMER_COUNT + 1),
        (career_progress.HEADER_TYPE_COUNT_OFFSET, career_progress.MAX_TYPE_COUNT + 1),
        (career_progress.HEADER_MILESTONE_COUNT_OFFSET, career_progress.MAX_MILESTONE_COUNT + 1),
        (career_progress.HEADER_TIMER_COUNT_OFFSET, 0),
    ):
        data = _progress_buffer(milestones=ms)
        struct.pack_into("<I", data, field_off, bad)
        assert career_progress.parse_milestones(bytes(data)) is None, (hex(field_off), bad)


def test_parse_milestones_rejects_table_past_section_end():
    # Anchor placed so late that the table would cross GAME_SECTION_END.
    prefix = (career_transplant.GAME_SECTION_END
              - career_transplant.GAME_SECTION_START - 0x40)
    ms = (_pack_milestone(1, 2, 4, 0, 7, 1.0, 2.0),) * 4
    data = _progress_buffer(prefix=prefix, milestones=())
    struct.pack_into("<I", data, career_progress.HEADER_MILESTONE_COUNT_OFFSET, len(ms))
    assert career_progress.parse_milestones(bytes(data)) is None


# ── races ──────────────────────────────────────────────────────


def test_parse_races_decodes_flags_names_and_speeds():
    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    _write_race(data, 0, HASH_1_1_1, 0x1E, high_score=1130524760,
                top_raw=int(37.2 * 256), avg_raw=int(23.8 * 256))
    _write_race(data, 1, HASH_1_1_1, 0x14)
    _write_race(data, 2, HASH_16_1_1_R, 0x02)
    _write_race(data, 3, HASH_UNNAMED, 0x04)

    records = career_progress.parse_races(bytes(data))
    assert records is not None and len(records) == career_transplant.RACE_RECORD_COUNT

    done, available, prologue, unnamed = records[:4]
    assert done.event_id == "1.1.1"
    assert done.chapter == 1
    assert done.is_completed
    assert done.high_score == 1130524760
    assert abs(done.top_speed - 37.2) < 0.01
    assert abs(done.average_speed - 23.8) < 0.01

    assert not available.is_completed

    assert prologue.event_id == "16.1.1.r"
    assert prologue.chapter == career_progress.PROLOGUE_CHAPTER
    assert prologue.is_reversed
    assert prologue.is_completed  # prologue completes at 0x02, not 0x1E

    assert unnamed.event_id is None
    assert unnamed.chapter is None
    assert not unnamed.is_completed


def test_parse_races_rejects_wrong_size():
    assert career_progress.parse_races(b"\x00" * 100) is None


# ── speedtraps ─────────────────────────────────────────────────


def test_parse_speedtraps_decodes_records():
    traps = (
        _pack_speedtrap(15, 3, 0xA3D3F573, 36.1),
        _pack_speedtrap(7, 5, 0x0896A321, 70.8, best=76.7),
    )
    ms = (_pack_milestone(1, 2, 4, 0, 7, 1.0, 2.0),)
    for prefix in (0x2A0, 0x4E0):
        records = career_progress.parse_speedtraps(
            bytes(_progress_buffer(prefix=prefix, milestones=ms, speedtraps=traps))
        )
        assert records is not None and len(records) == 2, hex(prefix)
        sonny, kamikaze = records
        assert sonny.bin_number == 15
        assert sonny.counter == 3
        assert not sonny.is_complete
        assert abs(sonny.required_speed - 36.1) < 0.01
        assert sonny.best_speed == 0.0
        assert kamikaze.bin_number == 7
        assert kamikaze.is_complete
        assert abs(kamikaze.best_speed - 76.7) < 0.01


def test_parse_speedtraps_rejects_table_past_section_end():
    prefix = (career_transplant.GAME_SECTION_END
              - career_transplant.GAME_SECTION_START - 0x80)
    data = _progress_buffer(prefix=prefix, milestones=(), speedtraps=())
    struct.pack_into("<II", data, career_progress.HEADER_MILESTONE_COUNT_OFFSET, 1, 4)
    assert career_progress.parse_speedtraps(bytes(data)) is None


# ── offering-chapter map guards ────────────────────────────────


def test_race_offering_map_matches_in_game_counts():
    # In-game per-chapter race counts (2026-07-07), #15..#1.
    in_game = [3, 6, 7, 7, 8, 8, 8, 7, 10, 11, 10, 11, 12, 12, 11]
    regular = {c: 0 for c in range(1, 16)}
    boss = {c: 0 for c in range(1, 16)}
    for chapter, is_boss in RACE_OFFERING.values():
        (boss if is_boss else regular)[chapter] += 1
    assert [regular[c] for c in range(15, 0, -1)] == in_game
    assert sum(boss.values()) == 37
    assert boss[1] == 5  # Razor showdown


def test_resolve_offering_known_cases():
    assert resolve_offering(HASH_16_1_1_R) == (7, False)  # prologue route, ch7
    assert resolve_offering(0xB352C935) == (1, True)      # 4.2.1, Razor showdown
    assert resolve_offering(HASH_UNNAMED) is None


def test_parse_races_carries_offering_data():
    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    _write_race(data, 0, HASH_16_1_1_R, 0x14)
    _write_race(data, 1, 0xB352C935, 0x14)
    records = career_progress.parse_races(bytes(data))
    assert records[0].offering_chapter == 7 and not records[0].is_boss_race
    assert records[1].offering_chapter == 1 and records[1].is_boss_race


# ── endgame flag ───────────────────────────────────────────────


def test_is_endgame_reads_special_flag_bit():
    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    struct.pack_into("<H", data, career_progress.SPECIAL_FLAGS_OFFSET, 0x0803)
    assert career_progress.is_endgame(bytes(data)) is False
    struct.pack_into("<H", data, career_progress.SPECIAL_FLAGS_OFFSET, 0x1803)
    assert career_progress.is_endgame(bytes(data)) is True
    struct.pack_into("<H", data, career_progress.SPECIAL_FLAGS_OFFSET, 0x1843)
    assert career_progress.is_endgame(bytes(data)) is True
    assert career_progress.is_endgame(b"\x00" * 100) is None


# ── generated name dictionary guards ───────────────────────────


def test_race_name_dictionary_shape():
    assert len(RACE_EVENT_IDS) == 209
    assert resolve_event_id(HASH_1_1_1) == "1.1.1"
    assert resolve_event_id(HASH_16_1_1_R) == "16.1.1.r"
    assert resolve_event_id(HASH_UNNAMED) is None
    chapters = {int(e.split(".", 1)[0]) for e in RACE_EVENT_IDS.values()}
    assert chapters == set(range(1, 17)) | {19, 20, 21, 99}
