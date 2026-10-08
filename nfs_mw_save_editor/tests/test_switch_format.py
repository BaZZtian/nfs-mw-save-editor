"""Native byte-order, persistence and complete original-feature regression tests.

Set NFS_MW_SWITCH_TEST_SAVE to a private raw MC02 save for the real-save tests.
No personal save is distributed with the source or Windows package.
"""
import hashlib
import json
import os
import struct
from pathlib import Path

import pytest

from core.career_donor_library import load_career_donor_library
from core.career_progress import build_career_progress
from core.savefile import SaveFile
from core.switch_format import SwitchCodec, SwitchSaveFile, game_region, _repair

APP_ROOT = Path(__file__).resolve().parents[1]
DONORS = load_career_donor_library(APP_ROOT / "assets/career_stages")
BUILDS = SaveFile.load_snapshot_library(user_root=APP_ROOT / "missing-test-user-library")


def native_fixture():
    """Generated native fixture with one Cobalt, no private identity/progress."""
    buf = bytearray(0xF4E0)
    buf[:4] = b"MC02"
    struct.pack_into(">III", buf, 4, len(buf), 8, len(buf) - 0x24)
    struct.pack_into(">II", buf, 0x1C, 0x10D, len(buf) - 0x24)
    donor = next(e for e in DONORS if e.stage_bin == 15 and e.variant == "chapter_start")
    buf[0x34:0x4034] = game_region(donor.read_bytes()[0x34:0x4034], False)
    struct.pack_into(">I", buf, 0x4034, 81)
    buf[0x4038] = 15
    struct.pack_into(">I", buf, 0x4039, 17250)
    buf[0x5A31:0x5A38] = b"TESTER\0"
    for row in range(119):
        off = 0x6221 + row * 20
        struct.pack_into(">I", buf, off, 0xFFFFFFFF)
        buf[off + 16:off + 20] = b"\xFF\xFF\xAA\xAA"
    struct.pack_into(">IIII", buf, 0x6221, 81, 0x5A784095, 0x5A784095, 0x000F0002)
    buf[0x6231:0x6235] = b"\x1F\x00\xAA\xAA"
    for slot in range(31, 75):
        off = 0x9CD5 + (slot - 31) * 0x198
        buf[off:off + 0x116] = b"\xFF" * 0x116
        buf[off + 0x116:off + 0x118] = b"\xAA\xAA"
        buf[off + 0x194:off + 0x198] = b"\xFF\xAA\xAA\xAA"
    buf[0x9CD5 + 0x194] = 31
    for slot in range(25):
        off = 0xE2F5 + slot * 0x38
        buf[off] = 0xFF
        buf[off + 1] = 0xAA
        buf[off + 10:off + 12] = b"\xAA\xAA"
    buf[0xE2F5] = 0
    buf[0xE2F7] = 3
    struct.pack_into(">fIHH", buf, 0xE2F5 + 12, 1.0, 103950, 7, 0)
    struct.pack_into(">III", buf, 0x5739, 17, 0, 1)
    _repair(buf, ">")
    return bytes(buf)


@pytest.fixture
def native_save(tmp_path):
    path = tmp_path / "TESTER"
    path.write_bytes(native_fixture())
    return SaveFile.load(path)


def assert_integrity(save):
    result = save.validate_integrity()
    assert result.actual_size == 62688
    assert result.file_size_ok and result.md5_ok
    assert result.crc_block1_ok and result.crc_data_ok and result.crc_block2_ok
    native = bytes(save.data)
    assert native[0x44:0x48] == b"emaG"
    assert native[0x34:0x44] == hashlib.md5(native[0x44:0x4034]).digest()


def test_native_open_is_lossless(native_save):
    assert isinstance(native_save, SwitchSaveFile)
    assert bytes(native_save.data) == native_save.path.read_bytes()
    assert native_save.get_money() == 17250
    assert native_save.get_profile_alias() == "TESTER"
    assert native_save.get_junkman_counts() == {17: 1}
    assert native_save.get_active_career_car_number() == 81
    assert native_save.get_transfer_car_entries()[0].display_name == "Chevrolet Cobalt SS"
    native_save.save(make_backup=False)
    assert bytes(native_save.data) == native_fixture()
    assert_integrity(native_save)


def test_unknown_native_serialization_version_is_rejected(tmp_path):
    wire = bytearray(native_fixture())
    struct.pack_into(">I", wire, 0x1C, 0x10E)
    path = tmp_path / "UNKNOWN"
    path.write_bytes(wire)
    with pytest.raises(ValueError, match="serialization version"):
        SaveFile.load(path)
    assert path.read_bytes() == bytes(wire)


def test_profile_markers_tuning_and_backup(native_save):
    original = native_save.path.read_bytes()
    native_save.set_money(987654321)
    native_save.set_profile_alias("SWITCH")
    native_save.set_junkman_counts({tid: 2 for tid in range(1, 22)})
    for name in native_save.PART_LEVEL_OFFSETS:
        native_save.set_part_level_for_parts_slot(31, name, 1)
    native_save.set_junkman_mask_for_parts_slot(31, 0x7F)
    assert bytes(native_save.data) != original
    assert native_save.path.read_bytes() == original  # memory-only edits
    native_save.save()
    assert list(native_save.path.parent.glob("TESTER.bak_*"))[0].read_bytes() == original
    wire = native_save.path.read_bytes()
    assert struct.unpack_from(">I", wire, 0x4039)[0] == 987654321
    assert struct.unpack_from(">III", wire, 0x5739) == (1, 0, 1)
    assert struct.unpack_from(">8I", wire, 0x9CD5 + 0x118) == (1,) * 7 + (0x7F,)
    reopened = SaveFile.load(native_save.path)
    assert reopened.get_money() == 987654321
    assert reopened.get_junkman_counts() == {tid: 2 for tid in range(1, 22)}
    assert_integrity(reopened)
    allowed = [(4, 8), (0x10, 0x1C), (0x4039, 0x403D), (0x5739, 0x5A2D),
               (0x5A31, 0x5A55), (0x9CD5, 0x9E6D), (len(wire) - 16, len(wire))]
    assert all(a == b or any(lo <= i < hi for lo, hi in allowed)
               for i, (a, b) in enumerate(zip(original, wire)))


def test_heat_bounty_fields_are_isolated(native_save):
    before = bytes(native_save.data)
    native_save.set_slot_heat(0, 2.0)
    native_save.set_slot_bounty(0, 1234567)
    after = bytes(native_save.data)
    assert struct.unpack_from(">fI", after, 0xE2F5 + 12) == (2.0, 1234567)
    assert all(a == b or 0xE301 <= i < 0xE309 for i, (a, b) in enumerate(zip(before, after)))
    assert native_save.get_rap_sheet_totals().total_bounty == 1234567


def test_native_mutable_buffer_contract(native_save):
    struct.pack_into(">I", native_save.data, 0x4039, 456789)
    assert native_save.get_money() == 456789
    native_save.data[0x5A55] = 0x51  # native field outside editor-owned regions
    native_save.set_junkman_counts({2: 1})
    native_save.save(make_backup=False)
    reloaded = SaveFile.load(native_save.path)
    assert reloaded.get_money() == 456789
    assert reloaded.data[0x5A55] == 0x51
    assert reloaded.get_junkman_counts() == {2: 1, 17: 1}
    assert_integrity(reloaded)


@pytest.mark.parametrize("entry", BUILDS, ids=lambda e: e.file_label)
@pytest.mark.parametrize("target", ("career", "my_cars"))
def test_every_bundled_build_native_save_reload(native_save, entry, target, tmp_path):
    plan = native_save.inject_snapshot(entry, target)
    assert plan.refusal_reason is None
    native_save.save(make_backup=False)
    reopened = SaveFile.load(native_save.path)
    assert_integrity(reopened)
    row = (plan.target_owned_abs_off - 0x6219) // 20
    off = 0x6221 + row * 20
    wire = bytes(reopened.data)
    assert struct.unpack_from(">I", wire, off)[0] == 81 + row
    signature = entry.primary_owned_record_template.signature
    assert wire[off + 4:off + 12] == signature[:4][::-1] + signature[4:][::-1]
    assert int.from_bytes(wire[off + 12:off + 16], "big") & 0xFFFF == plan.target_location_bits
    assert wire[off + 18:off + 20] == b"\xAA\xAA"
    build = reopened.extract_full_car_build_snapshot(plan.target_owned_abs_off)
    assert build.normalized_primary_build_block == entry.normalized_primary_build_block
    payload = reopened.snapshot_to_dict(build)
    exported = tmp_path / "car_build_snapshot_export.json"
    exported.write_text(json.dumps(payload), encoding="utf-8")
    restored = reopened.load_snapshot_library_entry(exported, library_root=tmp_path, library_bucket="User")
    assert restored.normalized_primary_build_block == entry.normalized_primary_build_block
    assert restored.primary_owned_record_template.signature == signature
    if entry.has_visual_sidecar:
        assert build.optional_visual_sidecar is not None
        assert build.optional_visual_sidecar.normalized_sidecar_build_block == entry.optional_visual_sidecar.normalized_sidecar_build_block


def test_garage_round_trip_and_active_pointer(native_save):
    entry = BUILDS[0]
    new = native_save.inject_snapshot(entry, "career")
    old = native_save.get_owned_car_records()[0]
    native_save.transfer_owned_car(old.abs_off, "my_cars")
    assert native_save.get_active_career_car_number() == new.target_car_number
    assert struct.unpack_from(">I", native_save.data, 0x4034)[0] == new.target_car_number
    native_save.transfer_owned_car(old.abs_off, "career")
    native_save.save(make_backup=False)
    reopened = SaveFile.load(native_save.path)
    assert len(reopened.get_career_vehicle_records()) == 2
    assert reopened.get_active_career_record() is not None
    assert reopened.audit_car_number_registry().is_native
    assert_integrity(reopened)


@pytest.mark.parametrize("entry", DONORS, ids=lambda e: e.sidecar_path.stem)
@pytest.mark.parametrize("mode", ("keep", "normalize"))
def test_every_career_stage_native_save_reload(native_save, entry, mode):
    before = bytes(native_save.data)
    plan = native_save.plan_career_transplant(entry.read_bytes())
    assert plan.refusal_reason is None
    native_save.apply_career_transplant(entry.read_bytes(), mode)
    native_save.save(make_backup=False)
    reopened = SaveFile.load(native_save.path)
    wire = bytes(reopened.data)
    assert wire[0x4038] == entry.stage_bin
    summary = build_career_progress(wire)
    assert summary is not None and summary.current_stage == entry.stage_bin
    expected = build_career_progress(entry.read_bytes())
    assert summary.lifetime_race_wins == expected.lifetime_race_wins
    assert summary.lifetime_milestone_wins == expected.lifetime_milestone_wins
    if mode == "normalize":
        assert reopened.get_rap_sheet_totals().total_bounty == expected.total_bounty
    assert wire[0x4039:0x403D] == before[0x4039:0x403D]
    assert wire[0x5739:0x5A55] == before[0x5739:0x5A55]
    assert wire[0x6221:0xE2F5] == before[0x6221:0xE2F5]
    assert wire[0x5B41] == before[0x5B41]
    assert wire[0x5B62:0x5B64] == before[0x5B62:0x5B64]
    assert_integrity(reopened)


@pytest.mark.parametrize("entry", DONORS, ids=lambda e: e.sidecar_path.stem)
def test_career_serialization_preserves_packed_payloads(entry):
    raw = entry.read_bytes()[0x34:0x4034]
    native = game_region(raw, False)
    assert game_region(native, True) == raw
    assert struct.unpack_from(">I", native, 20)[0] == 8
    assert native[:16] == hashlib.md5(native[16:]).digest()


@pytest.mark.skipif(not os.getenv("NFS_MW_SWITCH_TEST_SAVE"), reason="private real-save fixture not supplied")
def test_real_native_save_and_complete_features(tmp_path):
    original = Path(os.environ["NFS_MW_SWITCH_TEST_SAVE"]).read_bytes()
    target = tmp_path / "PRIVATE"
    target.write_bytes(original)
    save = SaveFile.load(target)
    assert bytes(save.data) == original
    assert save.get_profile_alias() == original[0x5A31:0x5A55].split(b"\0", 1)[0].decode("ascii")
    assert save.get_money() == 17250
    assert save.get_junkman_counts() == {17: 3}
    assert [e.display_name for e in save.get_transfer_car_entries()] == ["Chevrolet Cobalt SS", "VW Golf GTI", "Toyota Supra"]
    assert save.get_active_career_car_number() == 81
    assert save.get_rap_sheet_totals().total_bounty == 103950
    assert_integrity(save)
    assert game_region(game_region(original[0x34:0x4034], True), False) == original[0x34:0x4034]
    save.set_money(999999)
    save.set_junkman_counts({tid: 3 for tid in range(1, 8)})
    save.set_slot_heat(0, 3)
    save.set_slot_bounty(0, 234567)
    for name in save.PART_LEVEL_OFFSETS:
        save.set_part_level_for_parts_slot(31, name, 1)
    save.set_junkman_mask_for_parts_slot(31, 0x7F)
    save.transfer_owned_car(save.get_owned_car_records()[2].abs_off, "my_cars")
    save.inject_snapshot(BUILDS[0], "career")
    save.apply_career_transplant(DONORS[-1].read_bytes())
    save.save()
    reopened = SaveFile.load(target)
    assert reopened.get_money() == 999999
    assert reopened.get_junkman_counts()[1] == 3
    assert reopened.get_parts_record(31).junkman_mask == 0x7F
    assert reopened.get_my_cars_records()
    assert reopened.get_active_career_record() is not None
    assert reopened.audit_car_number_registry().is_native
    assert_integrity(reopened)
    assert Path(os.environ["NFS_MW_SWITCH_TEST_SAVE"]).read_bytes() == original
