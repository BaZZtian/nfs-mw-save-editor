from __future__ import annotations

import hashlib

import pytest

from core import career_transplant
from core.savefile import SaveFile


KEEP_USER_HOLES = (
    (0x0000, 0x0034, "file_header"),
    (0x4034, 0x4038, "current_car"),
    (0x4039, 0x403D, "current_cash"),
    (0x42A9, 0x42B9, "case_file_name"),
    (0x5241, 0x57B1, "post_race_gap_including_visual_table"),
    (0x57B2, 0x57B9, "gap_after_tbd_57b1"),
    (0x57BA, 0x5B41, "gap_after_tbd_57b9"),
    (0x5B42, 0x5B62, "gap_after_tbd_5b41"),
    (0x5B64, 0x5C71, "gap_after_tbd_5b62"),
    (0x5C72, 0x5C73, "gap_after_tbd_5c71"),
    (0x5C74, 0x793D, "gap_after_tbd_5c73"),
    (0x795D, career_transplant.EXPECTED_SAVE_SIZE, "property_and_tail_region"),
)


class _FakeSave:
    def __init__(self, data: bytearray, *, active_record: object | None = object()) -> None:
        self.data = data
        self._active_record = active_record

    def get_active_career_record(self) -> object | None:
        return self._active_record

    def plan_career_transplant(self, donor_data: bytes) -> object:
        return career_transplant.plan_career_transplant(self, donor_data)


def _valid_user_buffer(fill: int = 0xAA) -> bytearray:
    data = bytearray([fill] * career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    return data


def _valid_donor_buffer(fill: int = 0xBB, *, donor_bin: int = 7) -> bytes:
    data = bytearray([fill] * career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    data[career_transplant.CURRENT_BIN_OFFSET] = int(donor_bin) & 0xFF
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
