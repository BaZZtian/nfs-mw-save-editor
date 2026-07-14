import os
from pathlib import Path
import re
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from core.models import OwnedCarTransferPlan, PursuitRecord, ResolvedTransferCarEntry
from core.savefile import SaveFile
from ui.page_chrome import PageChromeMixin
from ui.pages.garage_mixin import GarageCardVm, GarageMixin
from ui.theme import build_page_stylesheet, resolve_theme_tokens


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _plan(slot: ResolvedTransferCarEntry, *, target_location_bits: int, target_career_slot: int | None) -> OwnedCarTransferPlan:
    return OwnedCarTransferPlan(
        source_abs_off=slot.abs_off,
        source_display_name=slot.display_name,
        source_location_bits=slot.location_bits,
        source_misc_bits=slot.misc_bits,
        source_career_slot=slot.career_slot,
        source_parts_slot=slot.parts_slot,
        target_location_bits=target_location_bits,
        target_misc_bits=slot.misc_bits,
        target_career_slot=target_career_slot,
        cleared_source_career_slot=None,
        clears_pursuit_slot=False,
        target_owned_abs_off=slot.abs_off,
        requires_relocation=False,
        refusal_reason=None,
        warnings=(),
    )


class _GarageHeatHarness(PageChromeMixin, GarageMixin):
    def __init__(self) -> None:
        self._profile_number_validator = QIntValidator(0, 999999999)
        self._garage_card_widgets_page = {}
        self._garage_card_handles = {}
        self.garage_card_edits = {}
        self.garage_card_current_labels = {}

    def _apply_garage_card_vm(self, handle, vm) -> None:
        return

    def _format_current_value(self, value) -> str:
        return str(value)

    def _set_profile_line_edit(self, edit, value, enabled) -> None:
        edit.setText("" if value is None else str(value))

    def on_garage_transfer_requested(self, abs_off: int, target_mode: str) -> None:
        return


class GarageHeatUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def test_heat_button_row_keeps_spacing_and_uses_transparent_container(self) -> None:
        harness = _GarageHeatHarness()
        slot = ResolvedTransferCarEntry(
            abs_off=0x6200,
            car_number=0x31,
            signature=b"\x01" * 8,
            display_name="BMW M3 GTR",
            source_kind="Career",
            location_bits=SaveFile.CAREER_FLAG,
            misc_bits=0,
            parts_slot=32,
            career_slot=1,
            is_career=True,
            is_my_cars=False,
            is_pink_slip=False,
            has_pursuit_link=True,
            heat=2.0,
            heat_level=2,
            bounty=37500,
            escaped=1,
            busted=0,
            pursuit_abs_off=0x9001,
        )
        vm = GarageCardVm(
            slot=slot,
            projected_slot=slot,
            changed=False,
            is_active=False,
            current_bounty=37500,
            have_bounty=37500,
            current_heat_level=2,
            have_heat_level=2,
            plan_my_cars=_plan(slot, target_location_bits=SaveFile.MY_CARS_FLAG, target_career_slot=None),
            plan_career=_plan(slot, target_location_bits=SaveFile.CAREER_FLAG, target_career_slot=slot.career_slot),
        )

        card = harness._build_garage_card(vm)
        heat_buttons = [btn for btn in card.findChildren(QPushButton) if btn.objectName() == "heatBtn"]

        self.assertEqual(len(heat_buttons), 5)
        heat_row = heat_buttons[0].parentWidget()
        self.assertIsNotNone(heat_row)
        self.assertEqual(heat_row.objectName(), "garageHeatRow")
        self.assertEqual(heat_row.layout().spacing(), 4)
        self.assertEqual([btn.property("segmentPos") for btn in heat_buttons], ["first", "middle", "middle", "middle", "last"])

        heat_icons = card.findChildren(QLabel, "garageHeatIcon")
        self.assertEqual(len(heat_icons), 1)

        stylesheet = build_page_stylesheet("Blueprint")
        self.assertIn(
            "QFrame#garageCard QWidget#garageHeatRow {\n    background: transparent;\n}",
            stylesheet,
        )
        self.assertIn(
            "QFrame#garageCard QLabel#garageHeatIcon {\n"
            "    background: transparent;\n"
            "    border: none;\n"
            "}",
            stylesheet,
        )
        match = re.search(
            r"QPushButton#heatBtn\s*\{(?P<body>.*?)\}",
            stylesheet,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("border-radius: 4px;", body)
        self.assertNotIn('[segmentPos="first"]', stylesheet)
        self.assertNotIn('[segmentPos="middle"]', stylesheet)
        self.assertNotIn('[segmentPos="last"]', stylesheet)

    def test_heat_button_checked_uses_text_on_accent_token(self) -> None:
        tokens = resolve_theme_tokens("Catppuccin")
        stylesheet = build_page_stylesheet("Catppuccin")
        self.assertIn(f"background: {tokens['HEAT_SEGMENT_FILL']};", stylesheet)
        match = re.search(
            r"QPushButton#heatBtn:checked\s*\{(?P<body>.*?)\}",
            stylesheet,
            re.DOTALL,
        )

        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn(f"background: {tokens['HEAT_SEGMENT_ACTIVE_BG']};", body)
        self.assertIn(f"color: {tokens['TEXT_ON_ACCENT']};", body)
        self.assertNotIn(f"background: {tokens['ACCENT']};", body)
        self.assertNotIn(f"color: {tokens['TEXT_NAV_ACTIVE']};", body)

    def test_story_heat_cap_disables_later_heat_buttons(self) -> None:
        harness = _GarageHeatHarness()
        slot = ResolvedTransferCarEntry(
            abs_off=0x6200,
            car_number=0x31,
            signature=b"\x01" * 8,
            display_name="BMW M3 GTR",
            source_kind="Career",
            location_bits=SaveFile.CAREER_FLAG,
            misc_bits=0,
            parts_slot=32,
            career_slot=1,
            is_career=True,
            is_my_cars=False,
            is_pink_slip=False,
            has_pursuit_link=True,
            heat=2.0,
            heat_level=2,
            bounty=37500,
            escaped=1,
            busted=0,
            pursuit_abs_off=0x9001,
        )
        vm = GarageCardVm(
            slot=slot,
            projected_slot=slot,
            changed=False,
            is_active=False,
            current_bounty=37500,
            have_bounty=37500,
            current_heat_level=2,
            have_heat_level=2,
            plan_my_cars=_plan(slot, target_location_bits=SaveFile.MY_CARS_FLAG, target_career_slot=None),
            plan_career=_plan(slot, target_location_bits=SaveFile.CAREER_FLAG, target_career_slot=slot.career_slot),
            max_heat_level=3,
        )

        card = harness._build_garage_card(vm)
        heat_buttons = [btn for btn in card.findChildren(QPushButton) if btn.objectName() == "heatBtn"]

        self.assertEqual([btn.isEnabled() for btn in heat_buttons], [True, True, True, False, False])
        self.assertEqual(heat_buttons[3].toolTip(), "Locked until later story progression. Current cap: x3")


class GarageHeatCapTests(unittest.TestCase):
    def _savefile_with_rank(self, rank: int) -> SaveFile:
        sf = SaveFile.__new__(SaveFile)
        sf.data = bytearray(0x5000)
        sf.data[SaveFile.PLAYER_RANK_OFFSET] = rank
        return sf

    def test_story_heat_cap_follows_blacklist_rank_thresholds(self) -> None:
        self.assertEqual(SaveFile.heat_cap_for_blacklist_rank(14), 2)
        self.assertEqual(SaveFile.heat_cap_for_blacklist_rank(12), 3)
        self.assertEqual(SaveFile.heat_cap_for_blacklist_rank(8), 4)
        self.assertEqual(SaveFile.heat_cap_for_blacklist_rank(4), 5)

    def test_set_slot_heat_rejects_levels_above_story_cap(self) -> None:
        sf = self._savefile_with_rank(13)
        pursuit = PursuitRecord(
            career_slot=1,
            heat=2.0,
            heat_level=2,
            bounty=0,
            escaped=0,
            busted=0,
            abs_off=0x4100,
        )
        sf.get_pursuit_records = lambda: [pursuit]

        with self.assertRaisesRegex(ValueError, "current cap is x2"):
            sf.set_slot_heat(1, 3.0)

        sf.set_slot_heat(1, 2.0)
        self.assertEqual(sf.get_story_heat_cap(), 2)


if __name__ == "__main__":
    unittest.main()
