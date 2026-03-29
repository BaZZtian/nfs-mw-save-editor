from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCRIPT_PATH = Path(__file__).resolve()
APP_ROOT = SCRIPT_PATH.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.models import SnapshotLibraryEntry
from core.savefile import SaveFile


DEFAULT_SMOKE_CASES = (
    ("BMW M3 GTR", "my_cars"),
    ("Aston Martin DB9", "career"),
    ("BMW M3 Street Version", "my_cars"),
    ("Corvette C6.R", "career"),
)


@dataclass(frozen=True)
class PlannerSnapshot:
    target_mode: str
    status: str
    refusal_reason: Optional[str]
    target_parts_slot: Optional[int]
    target_sidecar_parts_slot: Optional[int]
    target_career_slot: Optional[int]
    warning_count: int


@dataclass(frozen=True)
class SavePlannerResult:
    save_label: str
    my_cars: PlannerSnapshot
    career: PlannerSnapshot


@dataclass(frozen=True)
class ValidationRow:
    json_path: Path
    bucket: str
    display_name: str
    naming_kind: str
    has_visual_sidecar: bool
    load_status: str
    load_error: Optional[str]
    save_results: tuple[SavePlannerResult, ...]


@dataclass(frozen=True)
class SmokeResult:
    display_name: str
    target_mode: str
    smoke_save_label: str
    status: str
    detail: str


def _snapshot_paths(root: Path) -> List[Path]:
    paths = {
        path.resolve()
        for pattern in (
            f"{SaveFile.SNAPSHOT_FILE_PREFIX}*.json",
            f"{SaveFile.LEGACY_SNAPSHOT_FILE_PREFIX}*.json",
        )
        for path in root.rglob(pattern)
    }
    return sorted(paths)


def _naming_kind(path: Path) -> str:
    if path.name.startswith(SaveFile.LEGACY_SNAPSHOT_FILE_PREFIX):
        return "legacy"
    if path.name.startswith(SaveFile.SNAPSHOT_FILE_PREFIX):
        return "new"
    return "unknown"


def _planner_snapshot(plan, target_mode: str) -> PlannerSnapshot:
    return PlannerSnapshot(
        target_mode=target_mode,
        status=("ok" if plan.refusal_reason is None else "blocked"),
        refusal_reason=plan.refusal_reason,
        target_parts_slot=plan.target_parts_slot,
        target_sidecar_parts_slot=plan.target_sidecar_parts_slot,
        target_career_slot=plan.target_career_slot,
        warning_count=len(plan.warnings),
    )


def _format_plan(plan: PlannerSnapshot) -> str:
    if plan.status != "ok":
        return f"BLOCKED: {plan.refusal_reason}"
    slot_text = f"parts {plan.target_parts_slot}"
    if plan.target_sidecar_parts_slot is not None:
        slot_text += f"/{plan.target_sidecar_parts_slot}"
    if plan.target_career_slot is not None:
        slot_text += f", career {plan.target_career_slot + 1}"
    if plan.warning_count:
        slot_text += f", warnings {plan.warning_count}"
    return f"OK: {slot_text}"


def validate_library(library_root: Path, save_paths: Iterable[Path]) -> List[ValidationRow]:
    saves = [(path.stem, SaveFile.load(path)) for path in save_paths]
    rows: List[ValidationRow] = []
    for json_path in _snapshot_paths(library_root):
        naming_kind = _naming_kind(json_path)
        try:
            entry = SaveFile.load_snapshot_library_entry(json_path, library_root=library_root)
        except Exception as exc:
            rows.append(
                ValidationRow(
                    json_path=json_path,
                    bucket="Unknown",
                    display_name=json_path.stem,
                    naming_kind=naming_kind,
                    has_visual_sidecar=False,
                    load_status="failed_to_parse",
                    load_error=str(exc),
                    save_results=tuple(),
                )
            )
            continue

        per_save: List[SavePlannerResult] = []
        for save_label, save in saves:
            my_plan = save.plan_snapshot_injection(entry, "my_cars")
            career_plan = save.plan_snapshot_injection(entry, "career")
            per_save.append(
                SavePlannerResult(
                    save_label=save_label,
                    my_cars=_planner_snapshot(my_plan, "my_cars"),
                    career=_planner_snapshot(career_plan, "career"),
                )
            )
        rows.append(
            ValidationRow(
                json_path=json_path,
                bucket=entry.library_bucket,
                display_name=entry.display_name,
                naming_kind=naming_kind,
                has_visual_sidecar=entry.has_visual_sidecar,
                load_status="loads_cleanly",
                load_error=None,
                save_results=tuple(per_save),
            )
        )
    return rows


def _find_entry_by_name(entries: Iterable[SnapshotLibraryEntry], display_name: str) -> SnapshotLibraryEntry:
    matches = [entry for entry in entries if entry.display_name == display_name]
    if not matches:
        raise ValueError(f"Snapshot '{display_name}' was not found in the library")
    if len(matches) > 1:
        raise ValueError(f"Snapshot '{display_name}' is ambiguous ({len(matches)} matches)")
    return matches[0]


def _smoke_case_lookup(case_text: str) -> tuple[str, str]:
    display_name, _, target_mode = case_text.partition("|")
    target = (target_mode.strip() or "my_cars").lower()
    if target not in ("my_cars", "career"):
        raise ValueError(f"Unsupported smoke target '{target}' in case '{case_text}'")
    return display_name.strip(), target


def _verify_injected_record(
    reloaded: SaveFile,
    entry: SnapshotLibraryEntry,
    *,
    target_mode: str,
    target_parts_slot: int,
    target_career_slot: Optional[int],
) -> bool:
    expected_location = SaveFile.MY_CARS_FLAG if target_mode == "my_cars" else SaveFile.CAREER_FLAG
    for record in reloaded.get_owned_car_records():
        if record.signature != entry.primary_owned_record_template.signature:
            continue
        if int(record.location_bits) != int(expected_location):
            continue
        if int(record.parts_slot) != int(target_parts_slot):
            continue
        if target_mode == "my_cars" and int(record.career_slot) == SaveFile.EMPTY_CAREER_SLOT:
            return True
        if target_mode == "career" and target_career_slot is not None and int(record.career_slot) == int(target_career_slot):
            return True
    return False


def run_smoke_injects(
    entries: List[SnapshotLibraryEntry],
    smoke_save: Path,
    cases: Iterable[tuple[str, str]],
) -> List[SmokeResult]:
    results: List[SmokeResult] = []
    with tempfile.TemporaryDirectory(prefix="snapshot-library-smoke-") as tmp_dir_text:
        tmp_dir = Path(tmp_dir_text)
        for display_name, target_mode in cases:
            target_copy = tmp_dir / f"{display_name.replace('/', '_')}_{target_mode}.sav"
            shutil.copy2(smoke_save, target_copy)
            try:
                entry = _find_entry_by_name(entries, display_name)
                save = SaveFile.load(target_copy)
                plan = save.plan_snapshot_injection(entry, target_mode)
                if plan.refusal_reason is not None:
                    results.append(
                        SmokeResult(
                            display_name=display_name,
                            target_mode=target_mode,
                            smoke_save_label=smoke_save.stem,
                            status="blocked",
                            detail=plan.refusal_reason,
                        )
                    )
                    continue
                save.inject_snapshot(entry, target_mode, desired_career_slot=plan.target_career_slot)
                integrity = save.fix_integrity()
                save.save(target_copy, make_backup=False)
                reloaded = SaveFile.load(target_copy)
                reloaded_integrity = reloaded.validate_integrity()
                found = _verify_injected_record(
                    reloaded,
                    entry,
                    target_mode=target_mode,
                    target_parts_slot=int(plan.target_parts_slot),
                    target_career_slot=plan.target_career_slot,
                )
                active_ok = True
                if target_mode == "career":
                    active_ok = reloaded.get_active_career_record() is not None
                integrity_ok = (
                    bool(integrity.file_size_ok)
                    and bool(reloaded_integrity.file_size_ok)
                    and bool(reloaded_integrity.crc_block1_ok)
                    and bool(reloaded_integrity.crc_data_ok)
                    and bool(reloaded_integrity.crc_block2_ok)
                    and (reloaded_integrity.md5_ok is None or bool(reloaded_integrity.md5_ok))
                )
                if found and integrity_ok and active_ok:
                    detail = f"OK: parts {plan.target_parts_slot}"
                    if plan.target_career_slot is not None:
                        detail += f", career {plan.target_career_slot + 1}"
                    results.append(
                        SmokeResult(
                            display_name=display_name,
                            target_mode=target_mode,
                            smoke_save_label=smoke_save.stem,
                            status="ok",
                            detail=detail,
                        )
                    )
                else:
                    detail_bits = []
                    if not found:
                        detail_bits.append("reloaded record not found")
                    if not integrity_ok:
                        detail_bits.append("integrity failed after reload")
                    if not active_ok:
                        detail_bits.append("active career pointer unresolved")
                    results.append(
                        SmokeResult(
                            display_name=display_name,
                            target_mode=target_mode,
                            smoke_save_label=smoke_save.stem,
                            status="failed",
                            detail=", ".join(detail_bits) or "unknown smoke failure",
                        )
                    )
            except Exception as exc:
                results.append(
                    SmokeResult(
                        display_name=display_name,
                        target_mode=target_mode,
                        smoke_save_label=smoke_save.stem,
                        status="failed",
                        detail=str(exc),
                    )
                )
    return results


def build_markdown_report(
    *,
    library_root: Path,
    save_paths: List[Path],
    rows: List[ValidationRow],
    smoke_results: List[SmokeResult],
) -> str:
    total = len(rows)
    clean = sum(1 for row in rows if row.load_status == "loads_cleanly")
    failed = sum(1 for row in rows if row.load_status == "failed_to_parse")
    legacy = sum(1 for row in rows if row.naming_kind == "legacy")
    new = sum(1 for row in rows if row.naming_kind == "new")
    sidecar = sum(1 for row in rows if row.has_visual_sidecar)
    boundary_hits = 0
    blocked = 0
    for row in rows:
        for save_result in row.save_results:
            for plan in (save_result.my_cars, save_result.career):
                if plan.status != "ok":
                    blocked += 1
                    if plan.refusal_reason == SaveFile.BOUNDARY_PARTS_SLOT_BLOCKED_REASON:
                        boundary_hits += 1
    lines: List[str] = []
    lines.append("# Snapshot Library Validation")
    lines.append("")
    lines.append(f"- Library root: `{library_root}`")
    lines.append(f"- Saves checked: {', '.join(path.stem for path in save_paths)}")
    lines.append(f"- Total snapshot files: {total}")
    lines.append(f"- Loads cleanly: {clean}")
    lines.append(f"- Failed to parse: {failed}")
    lines.append(f"- Legacy naming: {legacy}")
    lines.append(f"- New naming: {new}")
    lines.append(f"- Sidecar snapshots: {sidecar}")
    lines.append(f"- Blocked planner outcomes across all checked saves/modes: {blocked}")
    lines.append(f"- Boundary-slot-74 planner hits: {boundary_hits}")
    lines.append("")
    lines.append("## Per-save Summary")
    lines.append("")
    lines.append("| Save | My Cars OK | My Cars Blocked | Career OK | Career Blocked |")
    lines.append("|------|-----------:|----------------:|----------:|---------------:|")
    for save_path in save_paths:
        label = save_path.stem
        my_ok = my_blocked = career_ok = career_blocked = 0
        for row in rows:
            for save_result in row.save_results:
                if save_result.save_label != label:
                    continue
                if save_result.my_cars.status == "ok":
                    my_ok += 1
                else:
                    my_blocked += 1
                if save_result.career.status == "ok":
                    career_ok += 1
                else:
                    career_blocked += 1
        lines.append(f"| {label} | {my_ok} | {my_blocked} | {career_ok} | {career_blocked} |")
    lines.append("")
    lines.append("## Snapshot Matrix")
    lines.append("")
    header = ["Bucket", "Name", "File", "Naming", "Sidecar", "Load"]
    for save_path in save_paths:
        header.append(f"{save_path.stem} My")
        header.append(f"{save_path.stem} Career")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        cells = [
            row.bucket,
            row.display_name.replace("|", "/"),
            row.json_path.stem.replace("|", "/"),
            row.naming_kind,
            "Yes" if row.has_visual_sidecar else "No",
            ("OK" if row.load_status == "loads_cleanly" else f"FAIL: {row.load_error}"),
        ]
        if row.load_status == "loads_cleanly":
            indexed = {result.save_label: result for result in row.save_results}
            for save_path in save_paths:
                result = indexed[save_path.stem]
                cells.append(_format_plan(result.my_cars).replace("|", "/"))
                cells.append(_format_plan(result.career).replace("|", "/"))
        else:
            for _ in save_paths:
                cells.extend(["-", "-"])
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Save-backed Injector Smoke")
    lines.append("")
    if not smoke_results:
        lines.append("No smoke cases were run.")
    else:
        lines.append("| Snapshot | Target | Save | Status | Detail |")
        lines.append("|----------|--------|------|--------|--------|")
        for result in smoke_results:
            lines.append(
                f"| {result.display_name.replace('|', '/')} | {result.target_mode} | {result.smoke_save_label} | {result.status} | {result.detail.replace('|', '/')} |"
            )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report is loader/planner validation plus save-backed inject smoke only.")
    lines.append("- It does not claim full in-game visual certification for every snapshot.")
    lines.append(f"- The reserved boundary rule for parts slot `74` stayed active during validation.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate bundled snapshot library and run save-backed smoke checks.")
    parser.add_argument("--library-root", type=Path, default=SaveFile.default_snapshot_library_root(), help="Snapshot library root")
    parser.add_argument("--save", action="append", type=Path, required=True, help="Clean reference save to use for planner validation (repeatable)")
    parser.add_argument("--report-md", type=Path, help="Optional markdown report output path")
    parser.add_argument("--smoke-save", type=Path, help="Optional save path used for save-backed inject smoke")
    parser.add_argument("--smoke-case", action="append", default=[], help="Smoke case in the form 'Display Name|my_cars' or 'Display Name|career'")
    args = parser.parse_args()

    library_root = args.library_root.resolve()
    save_paths = [path.resolve() for path in args.save]
    rows = validate_library(library_root, save_paths)
    entries = SaveFile.load_snapshot_library(library_root)
    smoke_cases = [_smoke_case_lookup(text) for text in args.smoke_case]
    if args.smoke_save is not None and not smoke_cases:
        smoke_cases = list(DEFAULT_SMOKE_CASES)
    smoke_results = (
        run_smoke_injects(entries, args.smoke_save.resolve(), smoke_cases)
        if args.smoke_save is not None and smoke_cases
        else []
    )
    report = build_markdown_report(
        library_root=library_root,
        save_paths=save_paths,
        rows=rows,
        smoke_results=smoke_results,
    )
    if args.report_md is not None:
        args.report_md.resolve().write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
