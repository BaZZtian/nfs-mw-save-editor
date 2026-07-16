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
HASH_CHALLENGE = 0xFE87E90B   # challenge-series slot "19.9.70"
HASH_ABSENT = 0xDEADBEEF      # not in the race table: resolution fails closed


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
    _write_race(data, 3, HASH_ABSENT, 0x04)
    _write_race(data, 4, HASH_CHALLENGE, 0x04)

    records = career_progress.parse_races(bytes(data))
    assert records is not None and len(records) == career_transplant.RACE_RECORD_COUNT

    done, available, prologue, unnamed, challenge = records[:5]
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

    assert challenge.event_id == "19.9.70"
    assert challenge.chapter == career_progress.CHALLENGE_CHAPTER
    assert not challenge.is_completed


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
    assert resolve_offering(HASH_CHALLENGE) is None  # challenge series: no offering


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


# ── immutable summary model ────────────────────────────────────


def test_blacklist_requirement_table_matches_pc_career_gates():
    expected = {
        15: (3, 3, 20_000), 14: (4, 3, 50_000),
        13: (4, 3, 100_000), 12: (4, 3, 180_000),
        11: (5, 3, 300_000), 10: (5, 4, 500_000),
        9: (5, 4, 790_000), 8: (5, 4, 1_180_000),
        7: (7, 4, 1_680_000), 6: (7, 4, 2_300_000),
        5: (7, 4, 3_050_000), 4: (7, 5, 4_050_000),
        3: (8, 5, 5_550_000), 2: (8, 5, 7_550_000),
        1: (9, 5, 10_000_000),
    }
    assert len(career_progress.BLACKLIST_REQUIREMENTS) == 15
    for stage, values in expected.items():
        requirement = career_progress.BLACKLIST_REQUIREMENTS[stage]
        assert (requirement.races, requirement.milestones, requirement.bounty) == values


def test_build_career_progress_groups_chapter_and_lifetime_state():
    milestone_rows = tuple(
        _pack_milestone(i, i + 1, career_progress.MILESTONE_STATE_AWARDED, 0, 15, 1.0, 1.0)
        for i in range(3)
    )
    data = _progress_buffer(milestones=milestone_rows)
    data[career_transplant.CURRENT_BIN_OFFSET] = 15
    struct.pack_into("<I", data, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 20_000)

    regular_hashes = [
        race_hash for race_hash, offering in RACE_OFFERING.items()
        if offering == (15, False)
    ][:3]
    boss_hash = next(
        race_hash for race_hash, offering in RACE_OFFERING.items()
        if offering == (15, True)
    )
    prologue_hash = next(
        race_hash for race_hash, event_id in RACE_EVENT_IDS.items()
        if event_id.startswith("16.") and race_hash not in RACE_OFFERING
    )
    for index, race_hash in enumerate(regular_hashes):
        _write_race(data, index, race_hash, 0x1E)
    _write_race(data, 3, boss_hash, 0x1E)
    _write_race(data, 4, prologue_hash, career_progress.RACE_FLAG_PROLOGUE_DONE)

    summary = career_progress.build_career_progress(bytes(data))
    assert summary is not None
    assert summary.current_stage == 15
    assert summary.default_stage == 15
    assert summary.total_bounty == 20_000
    assert summary.lifetime_race_wins == 5
    assert summary.lifetime_race_total == 5
    assert summary.lifetime_milestone_wins == 3
    assert summary.lifetime_milestone_total == 3
    assert len(summary.prologue_races) == 1

    sonny = summary.chapter(15)
    assert len(sonny.races) == 3
    assert len(sonny.boss_races) == 1
    assert sonny.race_wins == 3
    assert sonny.milestone_wins == 3
    assert summary.requirements_met(15)
    assert summary.stage_state(15) == "boss_ready"
    assert summary.stage_state(14) == "locked"


def test_requirement_progress_equally_weights_and_clamps_all_gate_parts():
    def build_summary(race_wins: int, milestone_wins: int, bounty: int):
        chapters = []
        for stage in range(15, 0, -1):
            requirement = career_progress.BLACKLIST_REQUIREMENTS[stage]
            races = tuple(
                career_progress.RaceRecord(
                    index=index,
                    race_hash=index,
                    event_id=None,
                    flags=career_transplant.RACE_DONE_MASK,
                    high_score=0,
                    top_speed=0.0,
                    average_speed=0.0,
                )
                for index in range(race_wins if stage == 15 else 0)
            )
            milestones = tuple(
                career_progress.MilestoneRecord(
                    index=index,
                    type_key=0,
                    challenge_key=0,
                    state=career_progress.MILESTONE_STATE_AWARDED,
                    flags=0,
                    bin_number=stage,
                    required_value=1.0,
                    recorded_value=1.0,
                )
                for index in range(milestone_wins if stage == 15 else 0)
            )
            chapters.append(career_progress.ChapterProgress(
                stage=stage,
                requirement=requirement,
                races=races,
                boss_races=(),
                milestones=milestones,
                speedtraps=(),
            ))
        return career_progress.CareerProgressSummary(
            current_stage=15,
            endgame=False,
            chapters=tuple(chapters),
            prologue_races=(),
            lifetime_race_wins=race_wins,
            lifetime_race_total=race_wins,
            lifetime_milestone_wins=milestone_wins,
            lifetime_milestone_total=milestone_wins,
            total_bounty=bounty,
        )

    assert build_summary(0, 0, 0).requirement_progress(15) == 0.0
    mixed = build_summary(1, 1, 10_000).requirement_progress(15)
    assert abs(mixed - ((1 / 3 + 1 / 3 + 1 / 2) / 3)) < 1e-12
    assert build_summary(3, 3, 20_000).requirement_progress(15) == 1.0
    assert build_summary(8, 9, 200_000).requirement_progress(15) == 1.0


def test_build_career_progress_marks_endgame_ladder_defeated():
    data = _progress_buffer(milestones=(_pack_milestone(1, 2, 1, 0, 1, 1.0, 0.0),))
    data[career_transplant.CURRENT_BIN_OFFSET] = 1
    struct.pack_into("<H", data, career_progress.SPECIAL_FLAGS_OFFSET, 0x1803)
    summary = career_progress.build_career_progress(bytes(data))
    assert summary is not None and summary.endgame
    assert summary.default_stage == 1
    assert all(summary.stage_state(stage) == "defeated" for stage in range(1, 16))


def test_build_career_progress_fails_closed_for_invalid_snapshot():
    assert career_progress.build_career_progress(b"\x00" * 100) is None


# ── generated name dictionary guards ───────────────────────────


def test_race_name_dictionary_shape():
    assert len(RACE_EVENT_IDS) == 248
    assert resolve_event_id(HASH_1_1_1) == "1.1.1"
    assert resolve_event_id(HASH_16_1_1_R) == "16.1.1.r"
    assert resolve_event_id(HASH_CHALLENGE) == "19.9.70"
    assert resolve_event_id(HASH_ABSENT) is None
    chapters = {int(e.split(".", 1)[0]) for e in RACE_EVENT_IDS.values()}
    assert chapters == set(range(1, 17)) | {19, 20, 21, 99}
