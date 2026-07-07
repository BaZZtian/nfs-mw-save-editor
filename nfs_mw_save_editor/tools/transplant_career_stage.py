from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


SCRIPT_PATH = Path(__file__).resolve()
APP_ROOT = SCRIPT_PATH.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.models import IntegrityStatus
from core.savefile import SaveFile


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _integrity_ok(integrity: IntegrityStatus) -> bool:
    return (
        bool(integrity.file_size_ok)
        and bool(integrity.crc_block1_ok)
        and bool(integrity.crc_data_ok)
        and bool(integrity.crc_block2_ok)
        # md5_ok is None means the hash scheme was not recognized; for a gate
        # that clears a file to be carried into the game, unknown must fail.
        and integrity.hash_scheme is not None
        and bool(integrity.md5_ok)
    )


def _print_plan(plan) -> None:
    print("Career stage transplant plan")
    print(f"  donor_bin: {plan.donor_bin}")
    print(f"  spans_total_bytes: {plan.spans_total_bytes}")
    if plan.refusal_reason:
        print(f"  refusal: {plan.refusal_reason}")
    else:
        print("  refusal: none")
    if plan.warnings:
        print("  warnings:")
        for warning in plan.warnings:
            print(f"    - {warning}")
    else:
        print("  warnings: none")


def _print_integrity(integrity: IntegrityStatus) -> None:
    print("Output integrity")
    print(f"  file_size_ok: {integrity.file_size_ok} ({integrity.actual_size})")
    print(f"  hash_scheme: {integrity.hash_scheme}")
    print(f"  md5_ok: {integrity.md5_ok}")
    print(f"  crc_block1_ok: {integrity.crc_block1_ok}")
    print(f"  crc_data_ok: {integrity.crc_data_ok}")
    print(f"  crc_block2_ok: {integrity.crc_block2_ok}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transplant career progression from a donor save into a copy of a user save.",
    )
    parser.add_argument("user_save", type=Path, help="User save to read without modifying.")
    parser.add_argument("donor_save", type=Path, help="Donor ladder save to read as raw bytes.")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Output save path. Must not already exist.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    user_path = _resolved(args.user_save)
    donor_path = _resolved(args.donor_save)
    output_path = _resolved(args.output)

    if output_path.exists():
        parser.error(f"OUTPUT already exists: {output_path}")
    if output_path == user_path:
        parser.error("OUTPUT must differ from USER_SAVE")
    if output_path == donor_path:
        parser.error("OUTPUT must differ from DONOR_SAVE")
    if not output_path.parent.exists():
        parser.error(f"OUTPUT parent directory does not exist: {output_path.parent}")

    save = SaveFile.load(user_path)
    donor_data = donor_path.read_bytes()
    plan = save.plan_career_transplant(donor_data)
    _print_plan(plan)

    if plan.refusal_reason:
        print("No output written.")
        return 2

    save.apply_career_transplant(donor_data)
    written = save.save(output_path, make_backup=False)
    print(f"Wrote output: {written}")

    reloaded = SaveFile.load(written)
    integrity = reloaded.validate_integrity()
    _print_integrity(integrity)
    if not _integrity_ok(integrity):
        print("Validation failed after reload.")
        return 1

    print("Validation passed after reload.")
    print("Reminder: output is a copy; back up before replacing the real profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
