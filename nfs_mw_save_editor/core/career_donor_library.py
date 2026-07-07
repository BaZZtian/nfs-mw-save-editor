"""Career donor library: discovery of transplant donor saves on disk.

A donor library is a flat directory of full 63596-byte donor saves, each
described by a JSON sidecar (same basename, ``.json`` extension):

    {
        "save_file": "08_chapter_start.sav",
        "stage_bin": 8,
        "variant": "chapter_start",          # or "boss_ready"
        "display_name": "Blacklist #8: Jewels"
    }

This module only does light discovery-time validation (sidecar shape, donor
file presence and size); deep donor validation (game-section magic and MD5)
stays in ``core.career_transplant.plan_career_transplant`` at use time, so a
stale library entry degrades into a planner refusal, never a crash.

Mirrors ``core.snapshot_library`` conventions: no SaveFile import, per-entry
problem strings instead of exceptions, and an APPDATA-based default user root.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from core.career_transplant import EXPECTED_SAVE_SIZE

CAREER_DONOR_LIBRARY_DIRNAME = "career_ladder"
CAREER_DONOR_LIBRARY_APPDIR = "NFS_MW_Junkman_Editor"

VARIANT_CHAPTER_START = "chapter_start"
VARIANT_BOSS_READY = "boss_ready"
KNOWN_VARIANTS = (VARIANT_CHAPTER_START, VARIANT_BOSS_READY)


@dataclass(frozen=True)
class CareerDonorEntry:
    sidecar_path: Path
    save_path: Path
    stage_bin: int
    variant: str
    display_name: str
    problems: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_loadable(self) -> bool:
        return not self.problems


def default_user_career_donor_root() -> Path:
    """Return the default per-user career donor library root."""

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / CAREER_DONOR_LIBRARY_APPDIR / CAREER_DONOR_LIBRARY_DIRNAME
    return Path.home() / "AppData" / "Roaming" / CAREER_DONOR_LIBRARY_APPDIR / CAREER_DONOR_LIBRARY_DIRNAME


def _entry_sort_key(entry: CareerDonorEntry) -> tuple[int, int, str]:
    variant_rank = 0 if entry.variant == VARIANT_CHAPTER_START else 1
    return (-entry.stage_bin, variant_rank, entry.display_name)


def _load_entry(sidecar_path: Path) -> CareerDonorEntry:
    problems = []
    stage_bin = 0
    variant = ""
    display_name = sidecar_path.stem
    save_path = sidecar_path.with_suffix("")

    try:
        raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return CareerDonorEntry(
            sidecar_path=sidecar_path,
            save_path=save_path,
            stage_bin=0,
            variant="",
            display_name=display_name,
            problems=(f"sidecar is not valid JSON: {exc}",),
        )

    if not isinstance(raw, dict):
        problems.append("sidecar root is not an object")
        raw = {}

    save_file = raw.get("save_file")
    if isinstance(save_file, str) and save_file:
        save_path = sidecar_path.parent / save_file
    else:
        problems.append("sidecar is missing 'save_file'")

    raw_bin = raw.get("stage_bin")
    if isinstance(raw_bin, int) and not isinstance(raw_bin, bool):
        stage_bin = raw_bin
    else:
        problems.append("sidecar 'stage_bin' is not an integer")

    raw_variant = raw.get("variant")
    if isinstance(raw_variant, str) and raw_variant in KNOWN_VARIANTS:
        variant = raw_variant
    else:
        problems.append(f"sidecar 'variant' must be one of {KNOWN_VARIANTS}")

    raw_name = raw.get("display_name")
    if isinstance(raw_name, str) and raw_name.strip():
        display_name = raw_name.strip()

    if not problems or save_path is not None:
        if not save_path.is_file():
            problems.append(f"donor save file not found: {save_path.name}")
        elif save_path.stat().st_size != EXPECTED_SAVE_SIZE:
            problems.append(
                f"donor save file size is {save_path.stat().st_size}, expected {EXPECTED_SAVE_SIZE}"
            )

    return CareerDonorEntry(
        sidecar_path=sidecar_path,
        save_path=save_path,
        stage_bin=stage_bin,
        variant=variant,
        display_name=display_name,
        problems=tuple(problems),
    )


def load_career_donor_library(root: Path) -> Tuple[CareerDonorEntry, ...]:
    """Scan ``root`` for donor sidecars; missing root yields an empty library."""

    root = Path(root)
    if not root.is_dir():
        return ()
    entries = [_load_entry(p) for p in sorted(root.glob("*.json"))]
    return tuple(sorted(entries, key=_entry_sort_key))
