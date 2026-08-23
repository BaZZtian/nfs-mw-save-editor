"""Career-stage donor discovery and compact bundled snapshot loading.

Legacy developer libraries contain a full 63596-byte donor save plus a JSON
sidecar. Public builds instead use ``career_stage_snapshot_v1`` JSON files.
Each compact snapshot stores only the seven progression spans consumed by the
transplant plus the donor's total bounty. At load time those fields are
materialized into a minimal internal donor buffer, so the existing transplant
planner and its fail-closed validation remain the single authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Tuple

from core import career_transplant
from core.garage_records import (
    GARAGE_EMPTY_HANDLE,
    GARAGE_RECORD_COUNT,
    GARAGE_RECORD_SIZE,
    GARAGE_RECORDS_OFFSET,
    SOLD_HISTORY_BOUNTY_OFFSET,
)
from core.rap_sheet_totals import read_rap_sheet_totals
from resources import resource_path


CAREER_DONOR_LIBRARY_DIRNAME = "career_ladder"
CAREER_DONOR_LIBRARY_APPDIR = "NFS_MW_Junkman_Editor"
DEFAULT_BUNDLED_CAREER_LIBRARY_DIR = ("assets", "career_stages")

VARIANT_CHAPTER_START = "chapter_start"
VARIANT_BOSS_READY = "boss_ready"
KNOWN_VARIANTS = (VARIANT_CHAPTER_START, VARIANT_BOSS_READY)

CAREER_STAGE_SNAPSHOT_KIND = "career_stage_snapshot_v1"
CAREER_STAGE_SNAPSHOT_SCHEMA = 1
U32_MAX = 0xFFFFFFFF


@dataclass(frozen=True)
class CareerDonorEntry:
    sidecar_path: Path
    save_path: Path
    stage_bin: int
    variant: str
    display_name: str
    problems: Tuple[str, ...] = field(default_factory=tuple)
    snapshot_data: bytes | None = None
    payload_sha256: str = ""

    @property
    def is_loadable(self) -> bool:
        return not self.problems

    def read_bytes(self) -> bytes:
        """Return a full internal donor buffer for the transplant planner."""

        if self.snapshot_data is not None:
            return self.snapshot_data
        return self.save_path.read_bytes()


def default_bundled_career_donor_root() -> Path:
    """Return the bundled compact career-stage snapshot root."""

    return resource_path(*DEFAULT_BUNDLED_CAREER_LIBRARY_DIR)


def default_user_career_donor_root() -> Path:
    """Return the legacy per-user full-save donor library root."""

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / CAREER_DONOR_LIBRARY_APPDIR / CAREER_DONOR_LIBRARY_DIRNAME
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / CAREER_DONOR_LIBRARY_APPDIR
        / CAREER_DONOR_LIBRARY_DIRNAME
    )


def _entry_sort_key(entry: CareerDonorEntry) -> tuple[int, int, str]:
    variant_rank = 0 if entry.variant == VARIANT_CHAPTER_START else 1
    return (-entry.stage_bin, variant_rank, entry.display_name)


def _canonical_snapshot_digest(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("payload_sha256", None)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_full_donor(data: bytes, stage_bin: int) -> None:
    if len(data) != career_transplant.EXPECTED_SAVE_SIZE:
        raise ValueError(
            f"donor save size is {len(data)}, expected "
            f"{career_transplant.EXPECTED_SAVE_SIZE}"
        )
    magic_start = career_transplant.GAME_MAGIC_OFFSET
    magic_end = magic_start + len(career_transplant.GAME_MAGIC)
    if data[magic_start:magic_end] != career_transplant.GAME_MAGIC:
        raise ValueError("donor game section magic is missing")
    expected_md5 = data[
        career_transplant.GAME_SECTION_MD5_OFFSET:
        career_transplant.GAME_SECTION_START
    ]
    actual_md5 = hashlib.md5(
        data[
            career_transplant.GAME_SECTION_START:
            career_transplant.GAME_SECTION_END
        ]
    ).digest()
    if actual_md5 != expected_md5:
        raise ValueError("donor game section MD5 is invalid")
    actual_stage = int(data[career_transplant.CURRENT_BIN_OFFSET])
    if actual_stage != stage_bin:
        raise ValueError(
            f"donor CurrentBin {actual_stage} does not match stage {stage_bin}"
        )


def build_career_stage_snapshot_payload(
    donor_data: bytes,
    *,
    stage_bin: int,
    variant: str,
    display_name: str,
    provenance: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build one deterministic compact snapshot payload from a full donor."""

    if variant not in KNOWN_VARIANTS:
        raise ValueError(f"unknown career snapshot variant: {variant!r}")
    if not (
        career_transplant.DONOR_STAGE_MIN_BIN
        <= stage_bin
        <= career_transplant.DONOR_STAGE_MAX_BIN
    ):
        raise ValueError(f"stage {stage_bin} is outside 1..15")
    _validate_full_donor(donor_data, stage_bin)
    try:
        totals = read_rap_sheet_totals(donor_data)
    except ValueError as exc:
        raise ValueError(f"donor garage records are unreadable: {exc}") from exc
    if totals is None:
        raise ValueError("donor rap-sheet totals are unavailable")
    if not (0 <= totals.total_bounty <= U32_MAX):
        raise ValueError("donor total bounty cannot be represented in a compact snapshot")

    payload: dict[str, Any] = {
        "kind": CAREER_STAGE_SNAPSHOT_KIND,
        "schema_version": CAREER_STAGE_SNAPSHOT_SCHEMA,
        "snapshot_id": f"stage{stage_bin:02d}_{variant}",
        "stage_bin": stage_bin,
        "variant": variant,
        "display_name": str(display_name),
        "donor_total_bounty": totals.total_bounty,
        "source_sha256": hashlib.sha256(donor_data).hexdigest(),
        "spans": [
            {
                "label": label,
                "start": start,
                "end": end,
                "normalized_hex": donor_data[start:end].hex(),
            }
            for start, end, label in career_transplant.TRANSPLANT_SPANS
        ],
    }
    if provenance:
        payload["provenance"] = {
            str(key): str(value) for key, value in sorted(provenance.items())
        }
    payload["payload_sha256"] = _canonical_snapshot_digest(payload)
    return payload


def _materialize_snapshot_donor(
    span_values: tuple[tuple[int, int, str, bytes], ...],
    donor_total_bounty: int,
) -> bytes:
    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    for slot in range(GARAGE_RECORD_COUNT):
        data[GARAGE_RECORDS_OFFSET + slot * GARAGE_RECORD_SIZE] = GARAGE_EMPTY_HANDLE
    data[
        SOLD_HISTORY_BOUNTY_OFFSET:SOLD_HISTORY_BOUNTY_OFFSET + 4
    ] = int(donor_total_bounty).to_bytes(4, "little")
    for start, end, _label, value in span_values:
        data[start:end] = value
    return bytes(data)


def _load_snapshot_entry(sidecar_path: Path, raw: dict[str, Any]) -> CareerDonorEntry:
    problems: list[str] = []
    stage_bin = 0
    variant = ""
    display_name = sidecar_path.stem
    payload_sha256 = str(raw.get("payload_sha256") or "")

    if raw.get("schema_version") != CAREER_STAGE_SNAPSHOT_SCHEMA:
        problems.append(
            f"snapshot schema must be {CAREER_STAGE_SNAPSHOT_SCHEMA}"
        )
    raw_stage = raw.get("stage_bin")
    if isinstance(raw_stage, int) and not isinstance(raw_stage, bool):
        stage_bin = raw_stage
        if not (
            career_transplant.DONOR_STAGE_MIN_BIN
            <= stage_bin
            <= career_transplant.DONOR_STAGE_MAX_BIN
        ):
            problems.append("snapshot stage_bin must be in 1..15")
    else:
        problems.append("snapshot stage_bin is not an integer")
    raw_variant = raw.get("variant")
    if isinstance(raw_variant, str) and raw_variant in KNOWN_VARIANTS:
        variant = raw_variant
    else:
        problems.append(f"snapshot variant must be one of {KNOWN_VARIANTS}")
    raw_name = raw.get("display_name")
    if isinstance(raw_name, str) and raw_name.strip():
        display_name = raw_name.strip()
    else:
        problems.append("snapshot display_name is missing")
    raw_bounty = raw.get("donor_total_bounty")
    donor_total_bounty = 0
    if (
        isinstance(raw_bounty, int)
        and not isinstance(raw_bounty, bool)
        and 0 <= raw_bounty <= U32_MAX
    ):
        donor_total_bounty = raw_bounty
    else:
        problems.append("snapshot donor_total_bounty must be a u32 integer")

    expected_digest = _canonical_snapshot_digest(raw)
    if len(payload_sha256) != 64 or payload_sha256.lower() != expected_digest:
        problems.append("snapshot payload SHA-256 is invalid")

    span_values: list[tuple[int, int, str, bytes]] = []
    raw_spans = raw.get("spans")
    expected_spans = career_transplant.TRANSPLANT_SPANS
    if not isinstance(raw_spans, list) or len(raw_spans) != len(expected_spans):
        problems.append(
            f"snapshot must contain exactly {len(expected_spans)} transplant spans"
        )
    else:
        for index, ((start, end, label), span) in enumerate(
            zip(expected_spans, raw_spans)
        ):
            if not isinstance(span, dict):
                problems.append(f"snapshot span {index} is not an object")
                continue
            if (
                span.get("label") != label
                or span.get("start") != start
                or span.get("end") != end
            ):
                problems.append(f"snapshot span {index} does not match {label}")
                continue
            try:
                value = bytes.fromhex(str(span.get("normalized_hex") or ""))
            except ValueError:
                problems.append(f"snapshot span {label} is not valid hex")
                continue
            if len(value) != end - start:
                problems.append(
                    f"snapshot span {label} has size {len(value)}, expected {end - start}"
                )
                continue
            span_values.append((start, end, label, value))

    snapshot_data: bytes | None = None
    if not problems:
        snapshot_data = _materialize_snapshot_donor(
            tuple(span_values), donor_total_bounty
        )
        try:
            _validate_full_donor(snapshot_data, stage_bin)
            totals = read_rap_sheet_totals(snapshot_data)
            if totals is None or totals.total_bounty != donor_total_bounty:
                raise ValueError("materialized donor bounty does not match metadata")
        except ValueError as exc:
            problems.append(str(exc))
            snapshot_data = None

    return CareerDonorEntry(
        sidecar_path=sidecar_path,
        save_path=sidecar_path,
        stage_bin=stage_bin,
        variant=variant,
        display_name=display_name,
        problems=tuple(problems),
        snapshot_data=snapshot_data,
        payload_sha256=payload_sha256.lower(),
    )


def _load_entry(sidecar_path: Path) -> CareerDonorEntry:
    problems: list[str] = []
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
        return CareerDonorEntry(
            sidecar_path=sidecar_path,
            save_path=save_path,
            stage_bin=0,
            variant="",
            display_name=display_name,
            problems=("sidecar root is not an object",),
        )
    if raw.get("kind") == CAREER_STAGE_SNAPSHOT_KIND:
        return _load_snapshot_entry(sidecar_path, raw)

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

    if not save_path.is_file():
        problems.append(f"donor save file not found: {save_path.name}")
    elif save_path.stat().st_size != career_transplant.EXPECTED_SAVE_SIZE:
        problems.append(
            f"donor save file size is {save_path.stat().st_size}, "
            f"expected {career_transplant.EXPECTED_SAVE_SIZE}"
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
    """Scan a bundled snapshot or legacy donor root.

    Missing roots yield an empty tuple. Invalid entries carry problem strings
    and never raise into the UI.
    """

    root = Path(root)
    if not root.is_dir():
        return ()
    entries = [_load_entry(path) for path in sorted(root.glob("*.json"))]
    return tuple(sorted(entries, key=_entry_sort_key))
