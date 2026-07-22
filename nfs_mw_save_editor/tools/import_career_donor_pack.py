"""One-shot importer: full-career save pack -> career donor library.

Understands the pack layout used by NFS_Most_Wanted_Blacklist_Full_Career:
  "NN. Blacklist #K"                      -> stage K, variant chapter_start
  "NN. Final Race versus BOSS - ..."      -> stage 16 - NN, variant boss_ready
with the save at <folder>/NFS Most Wanted/<profile>/<profile> (the profile
directory name is auto-detected; MW stores the save file under the profile's
own name). The two endgame "16." folders are intentionally skipped in v1
(their donor semantics need a separate decision). Every accepted donor is
validated with the transplant planner's donor checks (size, game magic,
game-section MD5) before copying.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

SCRIPT_PATH = Path(__file__).resolve()
APP_ROOT = SCRIPT_PATH.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import hashlib
import json

from core import career_transplant
from core.career_donor_library import (
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    default_user_career_donor_root,
)

_BLACKLIST_RE = re.compile(r"^(\d{2})\. Blacklist #(\d+)")
_FINAL_RACE_RE = re.compile(r"^(\d{2})\. Final Race versus (.+?) - ")

_BOSS_NAMES = {
    15: "Sonny", 14: "Taz", 13: "Vic", 12: "Izzy", 11: "Big Lou",
    10: "Baron", 9: "Earl", 8: "Jewels", 7: "Kamikaze", 6: "Ming",
    5: "Webster", 4: "JV", 3: "Ronnie", 2: "Bull", 1: "Razor",
}


def _find_profile_save(folder: Path) -> Optional[Path]:
    """Locate <folder>/NFS Most Wanted/<profile>/<profile> without assuming
    a profile name: MW keeps the save file under the profile's own name."""
    base = folder / "NFS Most Wanted"
    if not base.is_dir():
        return None
    for profile_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        candidate = profile_dir / profile_dir.name
        if candidate.is_file():
            return candidate
    return None


def _classify(folder_name: str) -> Optional[Tuple[int, str]]:
    m = _BLACKLIST_RE.match(folder_name)
    if m:
        return int(m.group(2)), VARIANT_CHAPTER_START
    m = _FINAL_RACE_RE.match(folder_name)
    if m:
        return 16 - int(m.group(1)), VARIANT_BOSS_READY
    return None


def _donor_is_valid(data: bytes, stage: int) -> Optional[str]:
    if len(data) != career_transplant.EXPECTED_SAVE_SIZE:
        return "wrong file size"
    magic_off = career_transplant.GAME_MAGIC_OFFSET
    if data[magic_off:magic_off + len(career_transplant.GAME_MAGIC)] != career_transplant.GAME_MAGIC:
        return "game section magic missing"
    digest = hashlib.md5(
        data[career_transplant.GAME_SECTION_START:career_transplant.GAME_SECTION_END]
    ).digest()
    if digest != data[career_transplant.GAME_SECTION_MD5_OFFSET:career_transplant.GAME_SECTION_START]:
        return "game section MD5 invalid"
    if data[career_transplant.CURRENT_BIN_OFFSET] != stage:
        return f"CurrentBin {data[career_transplant.CURRENT_BIN_OFFSET]} does not match stage {stage}"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import a full-career save pack into the career donor library.",
    )
    parser.add_argument("pack_root", type=Path, help="Root folder of the full-career pack.")
    parser.add_argument(
        "--library",
        type=Path,
        default=default_user_career_donor_root(),
        help="Donor library directory (default: per-user career_ladder dir).",
    )
    args = parser.parse_args(argv)

    pack_root = args.pack_root.expanduser().resolve()
    library = args.library.expanduser().resolve()
    if not pack_root.is_dir():
        parser.error(f"pack root does not exist: {pack_root}")
    library.mkdir(parents=True, exist_ok=True)

    imported = 0
    skipped = []
    for folder in sorted(pack_root.iterdir()):
        if not folder.is_dir():
            continue
        classified = _classify(folder.name)
        if classified is None:
            skipped.append(f"{folder.name} (unrecognized name)")
            continue
        stage, variant = classified
        save_path = _find_profile_save(folder)
        if save_path is None:
            skipped.append(f"{folder.name} (no save file inside)")
            continue
        data = save_path.read_bytes()
        problem = _donor_is_valid(data, stage)
        if problem:
            skipped.append(f"{folder.name} ({problem})")
            continue

        boss = _BOSS_NAMES.get(stage, "?")
        base = f"stage{stage:02d}_{variant}"
        donor_name = f"{base}.sav"
        shutil.copyfile(save_path, library / donor_name)
        sidecar = {
            "save_file": donor_name,
            "stage_bin": stage,
            "variant": variant,
            "display_name": (
                f"Blacklist #{stage}: {boss}"
                if variant == VARIANT_CHAPTER_START
                else f"Boss fight ready #{stage}: {boss}"
            ),
            "source": folder.name,
        }
        (library / f"{base}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        imported += 1

    print(f"Imported {imported} donors into {library}")
    for line in skipped:
        print(f"  skipped: {line}")
    return 0 if imported else 1


if __name__ == "__main__":
    raise SystemExit(main())
