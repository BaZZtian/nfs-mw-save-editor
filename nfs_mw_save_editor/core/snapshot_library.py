"""Snapshot library loading and JSON metadata helpers.

This module owns snapshot-library file naming, library root resolution,
snapshot JSON discovery, parsing, validation, and ordering. It deliberately
does not import SaveFile; SaveFile remains the authority for save-format
layout constants and delegates into this module with those constants supplied
as explicit configuration.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from core.models import OwnedCarTemplate, SnapshotLibraryEntry, SnapshotVisualSidecarEntry
from resources import resource_path


SNAPSHOT_FILE_PREFIX = "car_build_snapshot_"
LEGACY_SNAPSHOT_FILE_PREFIX = "boss_car_snapshot_"
SNAPSHOT_KIND = "car_build_snapshot_v2"
LEGACY_SNAPSHOT_KIND = "boss_car_build_snapshot_v2"
USER_SNAPSHOT_LIBRARY_DIRNAME = "user_builds"
USER_SNAPSHOT_LIBRARY_APPDIR = "NFS_MW_Junkman_Editor"
DEFAULT_SNAPSHOT_LIBRARY_DIR = ("assets", "unique_cars")
BLACKLIST_LIBRARY_ORDER = {
    "bmw m3 gtr": 0,
    "mercedes slr mclaren": 1,
    "aston martin db9": 2,
    "dodge viper srt10": 3,
    "corvette c6": 4,
    "lamborghini gallardo": 5,
    "mercedes clk 500": 6,
    "ford mustang gt": 7,
    "mitsubishi lancer evo viii": 8,
    "porsche cayman s": 9,
    "mitsubishi eclipse": 10,
    "mazda rx-8": 11,
    "toyota supra": 12,
    "lexus is300": 13,
    "vw golf gti": 14,
}


@dataclass(frozen=True)
class SnapshotLibraryFormat:
    """SaveFile-owned format constants needed to validate snapshot JSON."""

    parts_block_size: int
    career_vehicle_signature_size: int


def default_snapshot_library_root() -> Path:
    """Return the bundled snapshot-library root."""

    return resource_path(*DEFAULT_SNAPSHOT_LIBRARY_DIR)


def default_user_snapshot_library_root() -> Path:
    """Return the default per-user My Builds snapshot-library root."""

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / USER_SNAPSHOT_LIBRARY_APPDIR / USER_SNAPSHOT_LIBRARY_DIRNAME
    return Path.home() / "AppData" / "Roaming" / USER_SNAPSHOT_LIBRARY_APPDIR / USER_SNAPSHOT_LIBRARY_DIRNAME


def _hex_to_bytes(hex_text: str) -> bytes:
    return bytes.fromhex(str(hex_text).replace("\n", " ").strip())


def _normalize_snapshot_library_name(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _snapshot_library_sort_key(item: SnapshotLibraryEntry) -> tuple[int, int, str, str]:
    bucket_rank = {"Main": 0, "Bonus": 1, "User": 2}.get(item.library_bucket, 3)
    if item.library_bucket == "Main":
        normalized_name = _normalize_snapshot_library_name(item.display_name)
        blacklist_rank = BLACKLIST_LIBRARY_ORDER.get(normalized_name)
        if blacklist_rank is not None:
            return (bucket_rank, 0, f"{blacklist_rank:02d}", item.file_label.lower())
        return (bucket_rank, 1, item.display_name.lower(), item.file_label.lower())
    return (bucket_rank, 1, item.display_name.lower(), item.file_label.lower())


def load_snapshot_library_entry(
    path: str | Path,
    *,
    format_config: SnapshotLibraryFormat,
    library_root: str | Path | None = None,
    library_bucket: str | None = None,
) -> SnapshotLibraryEntry:
    """Load and validate one snapshot JSON file as a SnapshotLibraryEntry."""

    resolved_path = Path(path).resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if payload.get("kind") not in (SNAPSHOT_KIND, LEGACY_SNAPSHOT_KIND):
        raise ValueError(
            f"{resolved_path} is not a {SNAPSHOT_KIND} or {LEGACY_SNAPSHOT_KIND} file"
        )
    block = _hex_to_bytes(payload["primary_build_block"]["normalized_hex"])
    if len(block) != format_config.parts_block_size:
        raise ValueError(f"{resolved_path} has invalid normalized primary block size {len(block)}")
    template = payload["primary_owned_record_template"]
    signature = _hex_to_bytes(template["signature_hex"])
    if len(signature) != format_config.career_vehicle_signature_size:
        raise ValueError(f"{resolved_path} has invalid signature length {len(signature)}")
    library_base = Path(library_root).resolve() if library_root is not None else default_snapshot_library_root().resolve()
    if library_bucket is not None:
        bucket = str(library_bucket)
    else:
        relative_parent = resolved_path.parent.relative_to(library_base) if resolved_path.parent != library_base else Path(".")
        bucket = "Bonus" if "bonus_cars" in {part.lower() for part in relative_parent.parts} else "Main"
    performance = tuple(
        (str(name), int(value))
        for name, value in payload.get("primary_build_block", {}).get("performance_levels", {}).items()
    )
    visuals = tuple(
        (str(name), str(value))
        for name, value in payload.get("primary_build_block", {}).get("primary_visual_fields", {}).items()
    )
    provenance_payload = payload.get("provenance")
    provenance = (
        tuple((str(name), str(value)) for name, value in provenance_payload.items())
        if isinstance(provenance_payload, dict)
        else ()
    )
    sidecar_payload = payload.get("optional_visual_sidecar")
    sidecar_entry: SnapshotVisualSidecarEntry | None = None
    if sidecar_payload is not None:
        sidecar_block = _hex_to_bytes(sidecar_payload["normalized_sidecar_build_block_hex"])
        if len(sidecar_block) != format_config.parts_block_size:
            raise ValueError(f"{resolved_path} has invalid normalized sidecar block size {len(sidecar_block)}")
        sidecar_signature = _hex_to_bytes(sidecar_payload["owned_record_signature_clone_hex"])
        if len(sidecar_signature) != format_config.career_vehicle_signature_size:
            raise ValueError(f"{resolved_path} has invalid sidecar signature length {len(sidecar_signature)}")
        sidecar_marker = _hex_to_bytes(sidecar_payload["sidecar_marker_hex"])
        if len(sidecar_marker) != 4:
            raise ValueError(f"{resolved_path} has invalid sidecar marker length {len(sidecar_marker)}")
        sidecar_entry = SnapshotVisualSidecarEntry(
            owned_record_signature_clone=sidecar_signature,
            owned_record_location_bits=int(sidecar_payload["owned_record_location_bits"]),
            owned_record_misc_bits=int(sidecar_payload["owned_record_misc_bits"]),
            sidecar_parts_slot_offset=int(sidecar_payload["sidecar_parts_slot_offset"]),
            normalized_sidecar_build_block=sidecar_block,
            sidecar_marker=sidecar_marker,
        )
    return SnapshotLibraryEntry(
        snapshot_id=str(resolved_path).lower(),
        json_path=resolved_path,
        library_bucket=bucket,
        file_label=resolved_path.stem,
        display_name=str(payload.get("display_name") or resolved_path.stem),
        source_file=str(payload.get("source_file") or ""),
        source_kind=str(payload.get("source_kind") or "Unknown"),
        primary_owned_record_template=OwnedCarTemplate(
            car_number=int(template["car_number"]),
            signature=signature,
            location_bits=int(template["location_bits"]),
            misc_bits=int(template["misc_bits"]),
            source_kind=str(template.get("source_kind") or payload.get("source_kind") or "Unknown"),
        ),
        normalized_primary_build_block=block,
        performance_levels=performance,
        primary_visual_fields=visuals,
        has_visual_sidecar=sidecar_entry is not None,
        optional_visual_sidecar=sidecar_entry,
        provenance=provenance,
    )


def _snapshot_library_json_paths(root: Path) -> List[Path]:
    snapshot_paths = {
        path.resolve()
        for pattern in (
            f"{SNAPSHOT_FILE_PREFIX}*.json",
            f"{LEGACY_SNAPSHOT_FILE_PREFIX}*.json",
        )
        for path in root.rglob(pattern)
    }
    return sorted(snapshot_paths)


def load_snapshot_library(
    root: str | Path | None = None,
    *,
    format_config: SnapshotLibraryFormat,
    user_root: str | Path | None = None,
) -> List[SnapshotLibraryEntry]:
    """Load bundled and optional user snapshot-library entries in UI order."""

    library_root = Path(root) if root is not None else default_snapshot_library_root()
    user_library_root = Path(user_root) if user_root is not None else None
    entries: List[SnapshotLibraryEntry] = []

    if library_root.exists():
        for path in _snapshot_library_json_paths(library_root):
            entries.append(load_snapshot_library_entry(path, format_config=format_config, library_root=library_root))

    if user_library_root is not None and user_library_root.exists():
        for path in _snapshot_library_json_paths(user_library_root):
            entries.append(
                load_snapshot_library_entry(
                    path,
                    format_config=format_config,
                    library_root=user_library_root,
                    library_bucket="User",
                )
            )
    return sorted(entries, key=_snapshot_library_sort_key)
