"""Generate bundled compact Career snapshots from a validated donor library.

The source library remains local and contains full saves. Generated JSON files
contain only the progression spans used by Change Rival plus the donor's total
bounty. No full save or profile/case-file identity is copied into assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


SCRIPT_PATH = Path(__file__).resolve()
APP_ROOT = SCRIPT_PATH.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core import career_transplant
from core.career_donor_library import (
    KNOWN_VARIANTS,
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    build_career_stage_snapshot_payload,
    default_bundled_career_donor_root,
    default_user_career_donor_root,
    load_career_donor_library,
)


_BOSS_NAMES = {
    15: "Sonny",
    14: "Taz",
    13: "Vic",
    12: "Izzy",
    11: "Big Lou",
    10: "Baron",
    9: "Earl",
    8: "Jewels",
    7: "Kamikaze",
    6: "Ming",
    5: "Webster",
    4: "JV",
    3: "Ronnie",
    2: "Bull",
    1: "Razor",
}

_CASE_FILE_NAME_START = 0x429D
_CASE_FILE_NAME_END = 0x42AD


def _display_name(stage: int, variant: str) -> str:
    boss = _BOSS_NAMES[stage]
    if variant == VARIANT_BOSS_READY:
        return f"Boss fight ready #{stage}: {boss}"
    return f"Blacklist #{stage}: {boss}"


def _privacy_check(donor_data: bytes, payload: dict) -> None:
    """Refuse a payload that leaks the donor's CaseFileName."""

    case_name = donor_data[_CASE_FILE_NAME_START:_CASE_FILE_NAME_END].split(b"\x00", 1)[0]
    if len(case_name) < 4:
        return
    extracted = b"".join(
        bytes.fromhex(span["normalized_hex"]) for span in payload["spans"]
    )
    if case_name in extracted:
        raise ValueError(
            f"snapshot payload leaks donor CaseFileName {case_name!r}"
        )


def _render_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate compact bundled Career snapshots from local full-save donors."
    )
    parser.add_argument(
        "--source-library",
        type=Path,
        default=default_user_career_donor_root(),
        help="Legacy full-save donor library root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_bundled_career_donor_root(),
        help="Bundled compact snapshot output directory.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify deterministic output without writing files.",
    )
    args = parser.parse_args(argv)

    source_root = args.source_library.expanduser().resolve()
    output_root = args.output.expanduser().resolve()
    if not source_root.is_dir():
        parser.error(f"source library does not exist: {source_root}")

    entries = load_career_donor_library(source_root)
    invalid = [entry for entry in entries if not entry.is_loadable]
    if invalid:
        for entry in invalid:
            print(f"invalid {entry.sidecar_path.name}: {'; '.join(entry.problems)}")
        return 1

    by_key = {}
    for entry in entries:
        key = (entry.stage_bin, entry.variant)
        if key in by_key:
            print(f"duplicate donor for stage {entry.stage_bin} / {entry.variant}")
            return 1
        by_key[key] = entry
    expected_keys = {
        (stage, variant)
        for stage in range(
            career_transplant.DONOR_STAGE_MIN_BIN,
            career_transplant.DONOR_STAGE_MAX_BIN + 1,
        )
        for variant in KNOWN_VARIANTS
    }
    if set(by_key) != expected_keys:
        missing = sorted(expected_keys - set(by_key))
        extra = sorted(set(by_key) - expected_keys)
        print(f"donor matrix mismatch; missing={missing}, extra={extra}")
        return 1

    rendered: dict[str, str] = {}
    for stage, variant in sorted(expected_keys, key=lambda item: (-item[0], item[1])):
        entry = by_key[(stage, variant)]
        donor_data = entry.read_bytes()
        sidecar = json.loads(entry.sidecar_path.read_text(encoding="utf-8"))
        provenance = {
            "source_package": "NFS Most Wanted Blacklist Full Career",
            "source_stage": str(sidecar.get("source") or entry.sidecar_path.stem),
        }
        payload = build_career_stage_snapshot_payload(
            donor_data,
            stage_bin=stage,
            variant=variant,
            display_name=_display_name(stage, variant),
            provenance=provenance,
        )
        _privacy_check(donor_data, payload)
        rendered[f"stage{stage:02d}_{variant}.json"] = _render_payload(payload)

    if args.check:
        failed = False
        for name, expected in rendered.items():
            path = output_root / name
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                print(f"out of date: {path}")
                failed = True
        unexpected = (
            sorted(path.name for path in output_root.glob("*.json") if path.name not in rendered)
            if output_root.is_dir()
            else []
        )
        for name in unexpected:
            print(f"unexpected generated file: {output_root / name}")
            failed = True
        if failed:
            return 1
        print(f"Verified {len(rendered)} deterministic Career snapshots in {output_root}")
        return 0

    output_root.mkdir(parents=True, exist_ok=True)
    unexpected = sorted(
        path for path in output_root.glob("*.json") if path.name not in rendered
    )
    if unexpected:
        print("refusing to overwrite a directory with unexpected JSON files:")
        for path in unexpected:
            print(f"  {path}")
        return 1
    for name, content in rendered.items():
        (output_root / name).write_text(content, encoding="utf-8")
    print(f"Generated {len(rendered)} compact Career snapshots in {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
