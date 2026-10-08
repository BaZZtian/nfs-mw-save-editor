"""Review regressions, including gameplay bytes not built by the codec.

These are serialization/safety tests, not evidence of in-game acceptance.
"""
import hashlib
import struct

import pytest

from core.savefile import SaveFile
from core.switch_format import _repair, _reverse, game_region
from test_switch_format import native_fixture


def minimal_game(to_pc=True, **counts):
    order = ">" if to_pc else "<"
    buf = bytearray(0x4000)
    buf[16:20] = b"emaG" if to_pc else b"Game"
    fields = (8, counts.get("persistent", 0), counts.get("timers", 0),
              counts.get("types", 0), counts.get("milestones", 0),
              counts.get("traps", 0), counts.get("gates", 0),
              counts.get("hiding_bits", 0), counts.get("bin_bytes", 4),
              counts.get("sms", 0))
    struct.pack_into(order + "10I", buf, 20, *fields)
    buf[:16] = hashlib.md5(buf[16:]).digest()
    return buf


@pytest.mark.parametrize("start,size", [(-1, 4), (0, -1), (7, 2), (9, 0)])
def test_reverse_rejects_out_of_bounds_without_mutation(start, size):
    buf = bytearray(range(8))
    before = bytes(buf)
    with pytest.raises(ValueError, match="range|bounds|span"):
        _reverse(buf, start, size)
    assert bytes(buf) == before


@pytest.mark.parametrize("to_pc", [True, False])
@pytest.mark.parametrize("field", ["persistent", "timers", "types", "milestones",
                                   "traps", "gates", "hiding_bits", "bin_bytes", "sms"])
def test_all_gameplay_counts_are_bounded(field, to_pc):
    raw = minimal_game(to_pc, **{field: 0xFFFFFFFF})
    with pytest.raises(ValueError):
        game_region(raw, to_pc)


@pytest.mark.parametrize("to_pc", [True, False])
def test_pending_sms_5000_is_rejected(to_pc):
    with pytest.raises(ValueError, match="SMS"):
        game_region(minimal_game(to_pc, sms=5000), to_pc)


@pytest.mark.parametrize("to_pc", [True, False])
def test_sms_fits_but_leaves_no_footer(to_pc):
    # Bin count at 0x80; SMS starts at 0x88. This fills the section exactly.
    with pytest.raises(ValueError, match="footer"):
        game_region(minimal_game(to_pc, sms=(0x4000 - 0x88) // 4), to_pc)


@pytest.mark.parametrize("to_pc", [True, False])
def test_footer_exact_fit_is_accepted(to_pc):
    raw = minimal_game(to_pc, sms=(0x4000 - 0x88 - 32) // 4)
    converted = game_region(raw, to_pc)
    assert len(converted) == 0x4000
    assert game_region(converted, not to_pc) == raw


@pytest.mark.parametrize("to_pc", [True, False])
def test_arrays_within_individual_limits_still_cannot_overrun(to_pc):
    raw = minimal_game(to_pc, timers=64, types=128, milestones=256, traps=128,
                       gates=2000)
    with pytest.raises(ValueError, match="gates"):
        game_region(raw, to_pc)


@pytest.mark.parametrize("to_pc", [True, False])
def test_persistent_alignment_must_fit(to_pc):
    raw = minimal_game(to_pc, persistent=1)
    order = ">" if to_pc else "<"
    size = 0x4000 - 0x80 - 8
    struct.pack_into(order + "II", raw, 0x80, 0, size)
    struct.pack_into(order + "H", raw, 0x80 + 14, size - 8)
    # The record consumes the whole section, leaving no bin/footer.
    with pytest.raises(ValueError):
        game_region(raw, to_pc)


def test_gameplay_golden_arrays_do_not_use_codec_to_build_input():
    raw = minimal_game(timers=1, types=1, milestones=1, traps=1, gates=1,
                       hiding_bits=32, bin_bytes=12, sms=1)
    fields = [(128, 4), (136, 4)]  # timer
    fields += [(160 + rel, 4) for rel in (0, 4, 8, 12)]  # type
    fields += [(176 + rel, width) for rel, width in
               ((0, 4), (4, 4), (10, 2), (12, 4), (16, 4))]
    fields += [(200 + rel, width) for rel, width in
               ((0, 2), (2, 2), (4, 4), (8, 4), (12, 4), (16, 4))]
    fields += [(224, 4), (232, 4)]  # gate, hiding bitset
    struct.pack_into(">I", raw, 240, 1)  # one 8-byte bin record
    fields += [(244 + rel, 2) for rel in (0, 2, 4, 6)]
    fields += [(256, 4), (272, 4), (288, 4)]  # SMS and footer keys
    for pos, width in fields:
        raw[pos:pos + width] = bytes(range(1, width + 1))
    raw[:16] = hashlib.md5(raw[16:]).digest()
    expected = bytearray(raw)
    for pos, width in fields + [(pos, 4) for pos in range(16, 60, 4)] + [(240, 4)]:
        expected[pos:pos + width] = raw[pos:pos + width][::-1]
    expected[:16] = hashlib.md5(expected[16:]).digest()
    assert game_region(raw, True) == expected
    assert game_region(expected, False) == raw


def open_save(tmp_path, wire=None):
    path = tmp_path / "TESTER"
    path.write_bytes(wire if wire is not None else native_fixture())
    return SaveFile.load(path)


def test_held_buffer_preserves_setter_and_unknown_edits(tmp_path):
    save = open_save(tmp_path)
    buf = save.data
    save.set_money(222222)
    buf[0x5A55] = 0x51
    assert save.get_money() == 222222
    assert save.data is buf
    save.set_junkman_counts({2: 4})
    struct.pack_into(">I", buf, 0x4039, 333333)
    assert save.get_money() == 333333
    assert save.get_junkman_counts()[2] == 4
    save.save(make_backup=False)
    assert save.data is buf
    reopened = SaveFile.load(save.path)
    assert reopened.get_money() == 333333
    assert reopened.data[0x5A55] == 0x51
    assert reopened.get_junkman_counts()[2] == 4


def test_cached_setter_adopts_buffer_changes_at_call_time(tmp_path):
    save = open_save(tmp_path)
    buf = save.data
    setter = save.set_money
    save.set_money(222222)
    buf[0x5A55] = 0x51
    setter(333333)
    assert save.get_money() == 333333
    assert save.data[0x5A55] == 0x51
    assert save.data is buf


@pytest.mark.parametrize("kind,native,stride,pad", [
    ("owned", 0x6221, 20, 18),
    ("parts", 0x9CD5, 0x198, 0x116),
    ("pursuits", 0xE2F5, 0x38, 1),
])
def test_unedited_records_keep_nonstandard_padding(tmp_path, kind, native, stride, pad):
    wire = bytearray(native_fixture())
    pad_size = 1 if kind == "pursuits" else 2
    wire[native + stride + pad:native + stride + pad + pad_size] = b"\xCD" * pad_size
    # Reproduce the review's final pursuit-slot example, too.
    if kind == "pursuits":
        wire[0xE836] = 0xCD
    _repair(wire, ">")
    save = open_save(tmp_path, wire)
    before = bytes(save.data)
    if kind == "owned":
        save.set_owned_car_location(0x6219, 4)
    elif kind == "parts":
        save.set_part_level_for_parts_slot(31, "Engine", 1)
    else:
        save.set_slot_bounty(0, 123456)
    after = bytes(save.data)
    assert before[native:native + stride] != after[native:native + stride]
    table_end = native + stride * {"owned": 119, "parts": 44, "pursuits": 25}[kind]
    assert before[native + stride:table_end] == after[native + stride:table_end]
    save.save(make_backup=False)
    reopened = SaveFile.load(save.path)
    assert reopened.data[native + stride + pad] == 0xCD
    if kind == "pursuits":
        assert reopened.data[0xE836] == 0xCD
