from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core import career_donor_library, career_transplant, garage_records
from core.rap_sheet_totals import read_rap_sheet_totals


def _valid_donor_bytes(stage: int = 7) -> bytes:
    data = bytearray([0xBB] * career_transplant.EXPECTED_SAVE_SIZE)
    magic_off = career_transplant.GAME_MAGIC_OFFSET
    data[magic_off:magic_off + len(career_transplant.GAME_MAGIC)] = career_transplant.GAME_MAGIC
    data[career_transplant.CURRENT_BIN_OFFSET] = stage
    data[career_transplant.GAME_SECTION_MD5_OFFSET:career_transplant.GAME_SECTION_START] = hashlib.md5(
        data[career_transplant.GAME_SECTION_START:career_transplant.GAME_SECTION_END]
    ).digest()
    return bytes(data)


def _valid_snapshot_donor_bytes(stage: int = 7, *, bounty: int = 123_456) -> bytes:
    data = bytearray(_valid_donor_bytes(stage))
    for slot in range(garage_records.GARAGE_RECORD_COUNT):
        data[
            garage_records.GARAGE_RECORDS_OFFSET
            + slot * garage_records.GARAGE_RECORD_SIZE
        ] = garage_records.GARAGE_EMPTY_HANDLE
    data[
        garage_records.SOLD_HISTORY_BOUNTY_OFFSET:
        garage_records.SOLD_HISTORY_BOUNTY_OFFSET + 4
    ] = bounty.to_bytes(4, "little")
    return bytes(data)


def _write_donor(root: Path, base: str, stage: int, variant: str, *, save_bytes: bytes | None = None,
                 sidecar_overrides: dict | None = None) -> None:
    save_name = f"{base}.sav"
    if save_bytes is not None:
        (root / save_name).write_bytes(save_bytes)
    sidecar = {
        "save_file": save_name,
        "stage_bin": stage,
        "variant": variant,
        "display_name": f"Stage {stage} ({variant})",
    }
    if sidecar_overrides:
        sidecar.update(sidecar_overrides)
    (root / f"{base}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def test_load_returns_empty_for_missing_root(tmp_path: Path) -> None:
    """A nonexistent library root yields an empty tuple, not an error."""

    library = career_donor_library.load_career_donor_library(tmp_path / "nope")
    assert library == ()


def test_load_happy_path_and_sort_order(tmp_path: Path) -> None:
    """Entries sort by stage descending with chapter_start before boss_ready."""

    _write_donor(tmp_path, "a", 3, "boss_ready", save_bytes=_valid_donor_bytes(3))
    _write_donor(tmp_path, "b", 3, "chapter_start", save_bytes=_valid_donor_bytes(3))
    _write_donor(tmp_path, "c", 12, "chapter_start", save_bytes=_valid_donor_bytes(12))

    library = career_donor_library.load_career_donor_library(tmp_path)
    assert [(e.stage_bin, e.variant) for e in library] == [
        (12, "chapter_start"),
        (3, "chapter_start"),
        (3, "boss_ready"),
    ]
    assert all(e.is_loadable for e in library)


def test_missing_save_file_is_a_problem_not_an_error(tmp_path: Path) -> None:
    """A sidecar pointing at a missing donor file loads with problems set."""

    _write_donor(tmp_path, "gone", 5, "chapter_start")
    (entry,) = career_donor_library.load_career_donor_library(tmp_path)
    assert not entry.is_loadable
    assert any("not found" in p for p in entry.problems)


def test_wrong_size_save_file_is_a_problem(tmp_path: Path) -> None:
    """A donor file with the wrong size is flagged, not accepted."""

    _write_donor(tmp_path, "short", 5, "chapter_start", save_bytes=b"\x00" * 100)
    (entry,) = career_donor_library.load_career_donor_library(tmp_path)
    assert not entry.is_loadable
    assert any("size" in p for p in entry.problems)


def test_invalid_json_and_bad_fields_are_problems(tmp_path: Path) -> None:
    """Broken sidecars degrade into per-entry problems."""

    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write_donor(
        tmp_path, "badfields", 5, "chapter_start",
        save_bytes=_valid_donor_bytes(5),
        sidecar_overrides={"variant": "weird", "stage_bin": "five"},
    )
    library = career_donor_library.load_career_donor_library(tmp_path)
    assert len(library) == 2
    assert all(not e.is_loadable for e in library)
    problems = [p for e in library for p in e.problems]
    assert any("JSON" in p for p in problems)
    assert any("variant" in p for p in problems)
    assert any("stage_bin" in p for p in problems)


def test_compact_snapshot_roundtrip_preserves_only_progression_and_bounty(tmp_path: Path) -> None:
    """A compact payload materializes a planner-compatible internal donor."""

    donor = bytearray(_valid_snapshot_donor_bytes(7))
    donor[0x429D:0x42AD] = b"PRIVATE-CASE\x00\x00\x00\x00"
    payload = career_donor_library.build_career_stage_snapshot_payload(
        bytes(donor),
        stage_bin=7,
        variant=career_donor_library.VARIANT_CHAPTER_START,
        display_name="Blacklist #7: Kamikaze",
    )
    path = tmp_path / "stage07_chapter_start.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    (entry,) = career_donor_library.load_career_donor_library(tmp_path)
    assert entry.is_loadable
    materialized = entry.read_bytes()
    for start, end, _label in career_transplant.TRANSPLANT_SPANS:
        assert materialized[start:end] == donor[start:end]
    assert materialized[0x429D:0x42AD] != donor[0x429D:0x42AD]
    assert b"PRIVATE-CASE" not in materialized
    totals = read_rap_sheet_totals(materialized)
    assert totals is not None and totals.total_bounty == 123_456


def test_compact_snapshot_tamper_is_reported_without_loading(tmp_path: Path) -> None:
    payload = career_donor_library.build_career_stage_snapshot_payload(
        _valid_snapshot_donor_bytes(5),
        stage_bin=5,
        variant=career_donor_library.VARIANT_BOSS_READY,
        display_name="Boss fight ready #5: Webster",
    )
    payload["spans"][0]["normalized_hex"] = "00" + payload["spans"][0]["normalized_hex"][2:]
    (tmp_path / "tampered.json").write_text(json.dumps(payload), encoding="utf-8")

    (entry,) = career_donor_library.load_career_donor_library(tmp_path)
    assert not entry.is_loadable
    assert any("SHA-256" in problem for problem in entry.problems)


def test_bundled_career_snapshot_matrix_is_complete_and_loadable() -> None:
    entries = career_donor_library.load_career_donor_library(
        career_donor_library.default_bundled_career_donor_root()
    )
    assert len(entries) == 30
    assert all(entry.is_loadable for entry in entries)
    assert {(entry.stage_bin, entry.variant) for entry in entries} == {
        (stage, variant)
        for stage in range(1, 16)
        for variant in career_donor_library.KNOWN_VARIANTS
    }
    assert all(len(entry.read_bytes()) == career_transplant.EXPECTED_SAVE_SIZE for entry in entries)
    assert all(b"MW-2885-KSWD" not in entry.read_bytes() for entry in entries)
