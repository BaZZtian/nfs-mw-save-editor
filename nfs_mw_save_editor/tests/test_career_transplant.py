from __future__ import annotations

import hashlib

import pytest

from core import career_transplant, garage_records
from core.rap_sheet_totals import read_rap_sheet_totals
from core.savefile import SaveFile


KEEP_USER_HOLES = (
    (0x0000, 0x0034, "file_header"),
    (0x4034, 0x4038, "current_car"),
    (0x4039, 0x403D, "current_cash"),
    (0x42A9, 0x42B9, "case_file_name"),
    (0x5739, 0x5B41, "junkman_inventory_and_alias_region"),
    (0x5B42, 0x5B62, "gap_after_tbd_5b41"),
    # 0x5B64.. includes the FE car table (0x5BC5), user property, and pending
    # parts blocks, including fields affected by the Showcase bug.
    (0x5B64, career_transplant.EXPECTED_SAVE_SIZE, "fe_table_property_and_tail_region"),
)


class _FakeSave:
    def __init__(self, data: bytearray, *, active_record: object | None = object()) -> None:
        self.data = data
        self._active_record = active_record

    def get_active_career_record(self) -> object | None:
        return self._active_record

    def plan_career_transplant(self, donor_data: bytes) -> object:
        return career_transplant.plan_career_transplant(self, donor_data)


def _zero_bounty_fields(data: bytearray) -> None:
    """Zero garage bounties + sold history so fixtures imply no compensation."""

    for k in range(garage_records.GARAGE_RECORD_COUNT):
        off = (garage_records.GARAGE_RECORDS_OFFSET
               + k * garage_records.GARAGE_RECORD_SIZE
               + garage_records.GARAGE_RECORD_BOUNTY_REL)
        data[off:off + 4] = b"\x00" * 4
    data[career_transplant.SOLD_HISTORY_BOUNTY_OFFSET:
         career_transplant.SOLD_HISTORY_BOUNTY_OFFSET + 4] = b"\x00" * 4


def _valid_user_buffer(fill: int = 0xAA) -> bytearray:
    data = bytearray([fill] * career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    _zero_bounty_fields(data)
    return data


def _valid_donor_buffer(fill: int = 0xBB, *, donor_bin: int = 7) -> bytes:
    data = bytearray([fill] * career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    data[career_transplant.CURRENT_BIN_OFFSET] = int(donor_bin) & 0xFF
    _zero_bounty_fields(data)
    data[
        career_transplant.GAME_SECTION_MD5_OFFSET:
        career_transplant.GAME_SECTION_START
    ] = hashlib.md5(
        data[career_transplant.GAME_SECTION_START:career_transplant.GAME_SECTION_END]
    ).digest()
    return bytes(data)


def _assert_bytes_match_ranges(actual: bytes | bytearray, expected: bytes | bytearray, ranges) -> None:
    for start, end, label in ranges:
        assert actual[start:end] == expected[start:end], label


def _assert_refusal_and_apply_untouched(save: _FakeSave, donor_data: bytes, expected: str) -> None:
    before = bytes(save.data)
    plan = career_transplant.plan_career_transplant(save, donor_data)
    assert plan.refusal_reason == expected
    assert bytes(save.data) == before
    with pytest.raises(ValueError) as exc:
        career_transplant.apply_career_transplant(save, donor_data)
    assert str(exc.value) == expected
    assert bytes(save.data) == before


def test_transplant_span_table_is_sorted_bounded_and_avoids_keep_user_holes() -> None:
    """Assert transplant spans and keep-user holes tile the file exactly."""

    spans = career_transplant.TRANSPLANT_SPANS
    for start, end, label in spans:
        assert 0 <= start < end <= career_transplant.EXPECTED_SAVE_SIZE, label
    assert list(spans) == sorted(spans, key=lambda item: item[0])
    for previous, current in zip(spans, spans[1:]):
        assert previous[1] <= current[0]

    tiled = sorted(
        [(start, end, f"copy:{label}") for start, end, label in spans]
        + [(start, end, f"keep:{label}") for start, end, label in KEEP_USER_HOLES],
        key=lambda item: item[0],
    )
    assert tiled[0][0] == 0
    assert tiled[-1][1] == career_transplant.EXPECTED_SAVE_SIZE
    cursor = 0
    for start, end, label in tiled:
        assert start == cursor, label
        assert start < end, label
        cursor = end
    assert cursor == career_transplant.EXPECTED_SAVE_SIZE


def test_plan_career_transplant_never_mutates_user_buffer() -> None:
    """Assert planning reads validation state but does not alter user bytes."""

    user = _valid_user_buffer()
    donor = _valid_donor_buffer()
    save = _FakeSave(user)
    before = bytes(save.data)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.refusal_reason is None
    assert bytes(save.data) == before


def test_apply_happy_path_copies_all_spans_and_preserves_holes_and_tail() -> None:
    """Assert apply copies every donor span while every keep-user hole remains unchanged."""

    user = _valid_user_buffer()
    donor = _valid_donor_buffer()
    save = _FakeSave(user)
    before = bytes(save.data)
    career_transplant.apply_career_transplant(save, donor)
    _assert_bytes_match_ranges(save.data, donor, career_transplant.TRANSPLANT_SPANS)
    _assert_bytes_match_ranges(save.data, before, KEEP_USER_HOLES)


def test_plan_refuses_user_size_mismatch_with_exact_message() -> None:
    """Assert the first refusal rung returns 'User save size is not 63596 bytes'."""

    save = _FakeSave(_valid_user_buffer()[:-1])
    donor = _valid_donor_buffer()
    _assert_refusal_and_apply_untouched(
        save,
        donor,
        career_transplant.REFUSAL_USER_SIZE_MISMATCH,
    )


def test_plan_refuses_donor_size_mismatch_with_exact_message() -> None:
    """Assert the second refusal rung returns 'Donor save size is not 63596 bytes'."""

    save = _FakeSave(_valid_user_buffer())
    donor = _valid_donor_buffer()[:-1]
    _assert_refusal_and_apply_untouched(
        save,
        donor,
        career_transplant.REFUSAL_DONOR_SIZE_MISMATCH,
    )


def test_plan_refuses_missing_donor_game_magic_with_exact_message() -> None:
    """Assert the third refusal rung returns 'Donor game section magic is missing'."""

    save = _FakeSave(_valid_user_buffer())
    donor = bytearray(_valid_donor_buffer())
    donor[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = b"Nope"
    _assert_refusal_and_apply_untouched(
        save,
        bytes(donor),
        career_transplant.REFUSAL_DONOR_GAME_MAGIC_MISSING,
    )


def test_plan_refuses_invalid_donor_game_section_md5_with_exact_message() -> None:
    """Assert the fourth refusal rung returns 'Donor game section MD5 is invalid'."""

    save = _FakeSave(_valid_user_buffer())
    donor = bytearray(_valid_donor_buffer())
    donor[career_transplant.GAME_SECTION_MD5_OFFSET] ^= 0xFF
    _assert_refusal_and_apply_untouched(
        save,
        bytes(donor),
        career_transplant.REFUSAL_DONOR_GAME_MD5_INVALID,
    )


def test_plan_refuses_missing_user_game_magic_with_exact_message() -> None:
    """Assert the fifth refusal rung returns 'User game section magic is missing'."""

    user = _valid_user_buffer()
    user[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = b"Nope"
    save = _FakeSave(user)
    donor = _valid_donor_buffer()
    _assert_refusal_and_apply_untouched(
        save,
        donor,
        career_transplant.REFUSAL_USER_GAME_MAGIC_MISSING,
    )


def test_plan_warns_when_donor_bin_is_zero() -> None:
    """Assert donor CurrentBin 0 is non-fatal and emits the out-of-range warning."""

    save = _FakeSave(_valid_user_buffer())
    donor = _valid_donor_buffer(donor_bin=0)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.refusal_reason is None
    assert plan.donor_bin == 0
    assert plan.warnings == (career_transplant.WARNING_DONOR_BIN_OUT_OF_RANGE,)


def test_plan_warns_when_active_career_record_is_missing() -> None:
    """Assert missing active career pointer is non-fatal and emits the pointer warning."""

    save = _FakeSave(_valid_user_buffer(), active_record=None)
    donor = _valid_donor_buffer()
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.refusal_reason is None
    assert plan.warnings == (career_transplant.WARNING_USER_ACTIVE_CAREER_POINTER_INVALID,)


def test_apply_carries_donor_game_section_md5_verbatim_so_user_section_validates() -> None:
    """Assert copied game-section bytes include the donor MD5 and validate after apply."""

    save = _FakeSave(_valid_user_buffer())
    donor = _valid_donor_buffer()
    career_transplant.apply_career_transplant(save, donor)
    assert (
        bytes(save.data[career_transplant.GAME_SECTION_MD5_OFFSET:career_transplant.GAME_SECTION_START])
        == donor[career_transplant.GAME_SECTION_MD5_OFFSET:career_transplant.GAME_SECTION_START]
    )
    assert (
        hashlib.md5(save.data[career_transplant.GAME_SECTION_START:career_transplant.GAME_SECTION_END]).digest()
        == bytes(save.data[career_transplant.GAME_SECTION_MD5_OFFSET:career_transplant.GAME_SECTION_START])
    )


def test_apply_refused_plan_raises_and_leaves_buffer_untouched() -> None:
    """Assert apply raises ValueError for a refused plan and does not mutate the save buffer."""

    save = _FakeSave(_valid_user_buffer())
    donor = _valid_donor_buffer()[:-1]
    _assert_refusal_and_apply_untouched(
        save,
        donor,
        career_transplant.REFUSAL_DONOR_SIZE_MISMATCH,
    )


def test_savefile_delegates_plan_and_apply_career_transplant() -> None:
    """Assert real SaveFile delegates route through the career transplant module."""

    sf = object.__new__(SaveFile)
    sf.data = _valid_user_buffer()
    sf.get_active_career_record = lambda: object()
    donor = _valid_donor_buffer()

    plan = sf.plan_career_transplant(donor)
    assert plan.refusal_reason is None
    before = bytes(sf.data)
    sf.apply_career_transplant(donor)
    _assert_bytes_match_ranges(sf.data, donor, career_transplant.TRANSPLANT_SPANS)
    _assert_bytes_match_ranges(sf.data, before, KEEP_USER_HOLES)


def test_read_current_bin_and_race_count_helpers() -> None:
    """Assert progression read helpers decode bin and completed-race count."""

    data = bytearray(_valid_donor_buffer(donor_bin=9))
    base = career_transplant.RACE_TABLE_OFFSET
    for k in range(career_transplant.RACE_RECORD_COUNT):
        off = base + k * career_transplant.RACE_RECORD_SIZE + 4
        data[off:off + 4] = (0).to_bytes(4, "little")
    for k in (0, 3, 17):
        off = base + k * career_transplant.RACE_RECORD_SIZE + 4
        data[off:off + 4] = (0x1E).to_bytes(4, "little")

    assert career_transplant.read_current_bin(bytes(data)) == 9
    assert career_transplant.count_completed_races(bytes(data)) == 3
    assert career_transplant.read_current_bin(b"short") is None
    assert career_transplant.count_completed_races(b"short") is None


def test_apply_preserves_junkman_token_array() -> None:
    """Assert the Junkman slot array (63 x 12 bytes at 0x5739) never takes donor bytes.

    The post_race_belt span must stop at 0x5739 to preserve user tokens.
    """

    user = _valid_user_buffer()
    donor = _valid_donor_buffer()
    save = _FakeSave(user)
    before = bytes(save.data)
    career_transplant.apply_career_transplant(save, donor)
    assert bytes(save.data[0x5739:0x5A2D]) == before[0x5739:0x5A2D]


def _set_u32(data: bytearray, off: int, value: int) -> None:
    data[off:off + 4] = value.to_bytes(4, "little")


def _fill_garage_record(data: bytearray, index: int, bounty: int) -> None:
    """Write a live (Handle == index) garage record with the given bounty."""

    base = garage_records.GARAGE_RECORDS_OFFSET + index * garage_records.GARAGE_RECORD_SIZE
    data[base:base + garage_records.GARAGE_RECORD_SIZE] = b"\x00" * garage_records.GARAGE_RECORD_SIZE
    data[base] = index
    data[base + 1] = 0xCD
    data[base + 0x0A:base + 0x0C] = b"\xCD\xCD"
    _set_u32(data, base + garage_records.GARAGE_RECORD_BOUNTY_REL, bounty)


def test_bounty_compensation_computed_and_applied() -> None:
    """Assert apply tops up SoldHistoryBounty by exactly the donor-vs-user deficit."""

    user = _valid_user_buffer()
    _fill_garage_record(user, 0, 100_000)
    _set_u32(user, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 50_000)

    donor = bytearray(_valid_donor_buffer())
    _fill_garage_record(donor, 0, 400_000)
    _set_u32(donor, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 250_000)
    donor = bytes(donor)

    save = _FakeSave(user)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.bounty_compensation == 500_000  # 650k donor total - 150k user total

    career_transplant.apply_career_transplant(save, donor)
    sold = int.from_bytes(
        save.data[career_transplant.SOLD_HISTORY_BOUNTY_OFFSET:
                  career_transplant.SOLD_HISTORY_BOUNTY_OFFSET + 4], "little")
    assert sold == 50_000 + 500_000
    assert read_rap_sheet_totals(bytes(save.data)).total_bounty == 650_000


def _sold_value(save: _FakeSave) -> int:
    return int.from_bytes(
        save.data[career_transplant.SOLD_HISTORY_BOUNTY_OFFSET:
                  career_transplant.SOLD_HISTORY_BOUNTY_OFFSET + 4], "little")


def test_normalize_mode_lowers_sold_history_on_rollback() -> None:
    """Assert normalize sets sold history so the total matches the target."""

    user = _valid_user_buffer()
    _fill_garage_record(user, 0, 100_000)
    _set_u32(user, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 900_000)

    donor = bytearray(_valid_donor_buffer())
    _fill_garage_record(donor, 0, 200_000)
    _set_u32(donor, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 100_000)
    donor = bytes(donor)

    save = _FakeSave(user)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.bounty_compensation == 0
    assert plan.user_total_bounty == 1_000_000
    assert plan.user_live_bounty == 100_000
    assert plan.donor_total_bounty == 300_000
    assert plan.normalized_sold_bounty == 200_000
    # Live sum is below the target, so cars stay untouched.
    assert plan.normalized_car_bounties == ()

    career_transplant.apply_career_transplant(
        save, donor, career_transplant.BOUNTY_MODE_NORMALIZE)
    assert _sold_value(save) == 200_000
    assert read_rap_sheet_totals(bytes(save.data)).total_bounty == 300_000


def _record_without_bounty(data: bytearray, slot: int) -> bytes:
    base = garage_records.GARAGE_RECORDS_OFFSET + slot * garage_records.GARAGE_RECORD_SIZE
    raw = bytearray(data[base:base + garage_records.GARAGE_RECORD_SIZE])
    raw[garage_records.GARAGE_RECORD_BOUNTY_REL:
        garage_records.GARAGE_RECORD_BOUNTY_REL + 4] = b"\x00" * 4
    return bytes(raw)


def test_normalize_mode_scales_live_cars_to_exact_target() -> None:
    """Assert rich live cars are scaled proportionally and the total lands exactly."""

    user = _valid_user_buffer()
    _fill_garage_record(user, 0, 300_000)
    _fill_garage_record(user, 1, 200_000)
    _set_u32(user, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 100_000)

    donor = bytearray(_valid_donor_buffer())
    _fill_garage_record(donor, 0, 250_000)
    donor = bytes(donor)

    save = _FakeSave(user)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.user_live_bounty == 500_000
    assert plan.donor_total_bounty == 250_000
    assert plan.normalized_car_bounties == ((0, 300_000, 150_000), (1, 200_000, 100_000))
    assert plan.normalized_sold_bounty == 0

    before_rest = [_record_without_bounty(save.data, k) for k in (0, 1)]
    career_transplant.apply_career_transplant(
        save, donor, career_transplant.BOUNTY_MODE_NORMALIZE)
    totals = read_rap_sheet_totals(bytes(save.data))
    assert (totals.live_bounty, totals.sold_bounty) == (250_000, 0)
    assert totals.total_bounty == 250_000
    # Only the bounty field of each record changed.
    assert [_record_without_bounty(save.data, k) for k in (0, 1)] == before_rest


def test_normalize_rounding_remainder_lands_in_sold_history() -> None:
    """Assert floored car scaling still hits the exact target via sold history."""

    user = _valid_user_buffer()
    _fill_garage_record(user, 0, 3)
    _fill_garage_record(user, 1, 2)

    donor = bytearray(_valid_donor_buffer())
    _fill_garage_record(donor, 0, 4)
    donor = bytes(donor)

    save = _FakeSave(user)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.normalized_car_bounties == ((0, 3, 2), (1, 2, 1))
    assert plan.normalized_sold_bounty == 1

    career_transplant.apply_career_transplant(
        save, donor, career_transplant.BOUNTY_MODE_NORMALIZE)
    assert read_rap_sheet_totals(bytes(save.data)).total_bounty == 4


def test_bounty_modes_agree_when_moving_forward() -> None:
    """Assert keep and normalize write the same bytes on a forward jump."""

    def _fixture() -> tuple[_FakeSave, bytes]:
        user = _valid_user_buffer()
        _fill_garage_record(user, 0, 100_000)
        _set_u32(user, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 50_000)
        donor = bytearray(_valid_donor_buffer())
        _fill_garage_record(donor, 0, 400_000)
        _set_u32(donor, career_transplant.SOLD_HISTORY_BOUNTY_OFFSET, 250_000)
        return _FakeSave(user), bytes(donor)

    save_keep, donor = _fixture()
    career_transplant.apply_career_transplant(
        save_keep, donor, career_transplant.BOUNTY_MODE_KEEP)
    save_norm, _ = _fixture()
    career_transplant.apply_career_transplant(
        save_norm, donor, career_transplant.BOUNTY_MODE_NORMALIZE)

    assert bytes(save_keep.data) == bytes(save_norm.data)
    assert _sold_value(save_keep) == 550_000


def test_unknown_bounty_mode_refuses_before_writing() -> None:
    """Assert a bad mode raises and leaves the buffer byte-identical."""

    user = _valid_user_buffer()
    donor = _valid_donor_buffer()
    save = _FakeSave(user)
    before = bytes(save.data)
    with pytest.raises(ValueError, match="Unknown bounty mode"):
        career_transplant.apply_career_transplant(save, donor, "undo")
    assert bytes(save.data) == before


def test_bounty_compensation_is_zero_when_user_is_richer() -> None:
    """Assert a richer user gets no compensation and sold history stays untouched."""

    user = _valid_user_buffer()
    _fill_garage_record(user, 0, 9_000_000)
    donor = _valid_donor_buffer()

    save = _FakeSave(user)
    plan = career_transplant.plan_career_transplant(save, donor)
    assert plan.bounty_compensation == 0
    before_sold = bytes(save.data[career_transplant.SOLD_HISTORY_BOUNTY_OFFSET:
                                  career_transplant.SOLD_HISTORY_BOUNTY_OFFSET + 4])
    career_transplant.apply_career_transplant(save, donor)
    after_sold = bytes(save.data[career_transplant.SOLD_HISTORY_BOUNTY_OFFSET:
                                 career_transplant.SOLD_HISTORY_BOUNTY_OFFSET + 4])
    assert after_sold == before_sold
