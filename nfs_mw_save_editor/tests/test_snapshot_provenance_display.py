from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.savefile import SaveFile
from ui.pages.presets_mixin import PresetsMixin, SnapshotLibraryCardVm
from tests.test_snapshot_library_injection import (
    _make_snapshot,
    _snapshot_json_payload,
    _write_raw_snapshot_json,
)


GENERATED_PROVENANCE = {
    "method": "pending-band harvest, VLT preset cross-check (EXACT on non-kit-derived slots)",
    "donor_save": "fresh-career start save (clean profile)",
    "pending_parts_slot": 24,
    "preset": "CE_GTRSTREET",
    "perf_rule": "pending package verbatim",
}


class SnapshotProvenanceLoadingTests(unittest.TestCase):
    def _load_entry_with_payload(self, payload: dict):
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Provenance.json"
            _write_raw_snapshot_json(path, payload)
            return SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

    def test_provenance_parsed_in_json_order_with_values_as_text(self) -> None:
        payload = _snapshot_json_payload(display_name="Provenance Car")
        payload["provenance"] = GENERATED_PROVENANCE

        entry = self._load_entry_with_payload(payload)

        self.assertEqual(
            entry.provenance,
            (
                ("method", "pending-band harvest, VLT preset cross-check (EXACT on non-kit-derived slots)"),
                ("donor_save", "fresh-career start save (clean profile)"),
                ("pending_parts_slot", "24"),
                ("preset", "CE_GTRSTREET"),
                ("perf_rule", "pending package verbatim"),
            ),
        )

    def test_missing_or_malformed_provenance_loads_as_empty(self) -> None:
        entry = self._load_entry_with_payload(_snapshot_json_payload(display_name="No Provenance"))
        self.assertEqual(entry.provenance, ())

        malformed = _snapshot_json_payload(display_name="Bad Provenance")
        malformed["provenance"] = "not a mapping"
        entry = self._load_entry_with_payload(malformed)
        self.assertEqual(entry.provenance, ())


class _TooltipHarness(PresetsMixin):
    def __init__(self) -> None:
        self.savefile = None
        self.snapshot_library_error = None


class SnapshotProvenanceTooltipTests(unittest.TestCase):
    def test_generated_provenance_lines_hide_internal_fields(self) -> None:
        entry = replace(
            _make_snapshot(),
            provenance=tuple((name, str(value)) for name, value in GENERATED_PROVENANCE.items()),
        )

        lines = PresetsMixin._snapshot_provenance_lines(entry)

        self.assertEqual(
            lines,
            [
                "Provenance: pending-band harvest, VLT preset cross-check (EXACT on non-kit-derived slots)",
                "Donor save: fresh-career start save (clean profile)",
                "VLT preset: CE_GTRSTREET",
            ],
        )

    def test_story_provenance_lines_keep_note(self) -> None:
        entry = replace(_make_snapshot(), provenance=(
            ("method", "save harvest (materialized story/challenge car, no VLT preset)"),
            ("note", "Story car; harvested build kept byte-identical"),
        ))

        self.assertEqual(
            PresetsMixin._snapshot_provenance_lines(entry),
            [
                "Provenance: save harvest (materialized story/challenge car, no VLT preset)",
                "Note: Story car; harvested build kept byte-identical",
            ],
        )

    def test_entry_without_provenance_adds_no_lines(self) -> None:
        self.assertEqual(PresetsMixin._snapshot_provenance_lines(_make_snapshot()), [])

    def test_card_tooltip_places_provenance_after_identity_lines(self) -> None:
        entry = replace(_make_snapshot(), provenance=(("method", "save harvest"),))
        vm = SnapshotLibraryCardVm(
            entry=entry, staged_mode=None, plan_my=None, plan_career=None, staged_plan=None
        )

        tooltip = _TooltipHarness()._snapshot_library_card_tooltip(vm)

        lines = tooltip.split("\n")
        self.assertTrue(lines[0].startswith("File: "))
        self.assertTrue(lines[1].startswith("Snapshot ID: "))
        self.assertEqual(lines[2], "Provenance: save harvest")
        self.assertIn("State: Open a save to stage", lines)


if __name__ == "__main__":
    unittest.main()
