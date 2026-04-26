import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtWidgets import QApplication, QWidget

from core.models import OwnedCarTransferPlan, ResolvedTransferCarEntry
from core.savefile import SaveFile
from ui.main_window import MainWindow
from ui.pages.garage_mixin import GarageCardVm
from ui.theme import available_theme_names


SMOKE_OBJECT_NAMES = (
    "appChromeRoot",
    "contentStack",
    "navButton",
    "pageControlsRow",
    "pageControlsSection",
    "pageControlsSearchHost",
    "filterButton",
    "garageCard",
    "partsCard",
    "partsBulkBtn",
    "garageHeatRow",
    "heatBtn",
    "partsLevelRow",
    "partsLevelSeg",
    "settingsGroup",
    "themePreviewRow",
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _plan(
    slot: ResolvedTransferCarEntry,
    *,
    target_location_bits: int,
    target_career_slot: int | None,
) -> OwnedCarTransferPlan:
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


def _garage_card_vm() -> GarageCardVm:
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
    return GarageCardVm(
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


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.resize(1182, 812)
        self.window.show()
        self._add_synthetic_garage_card()
        self._warm_smoke_pages()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _add_synthetic_garage_card(self) -> None:
        card = self.window._build_garage_card(_garage_card_vm())
        self.window.garage_cards_layout.addWidget(card, 0, 0)

    def _warm_smoke_pages(self) -> None:
        for page_name in ("Builds", "Tuning", "Settings"):
            self.window._select_page(page_name)
            self.app.processEvents()

    def _navigate(self, page_name: str) -> None:
        if page_name == "Parts":
            self.window._select_page("Tuning")
        elif page_name == "My Cars":
            # My Cars is currently a Tuning/Garage source filter, not a top-level nav page.
            self.window._select_page("Tuning")
            self.window._select_tuning_filter("My Cars")
        else:
            self.window._select_page(page_name)
        self.app.processEvents()

    def _switch_theme_once(self) -> None:
        names = available_theme_names()
        self.assertGreaterEqual(len(names), 2, "UI smoke needs at least two themes to test theme switching")
        current = self.window.theme_name
        next_theme = next((name for name in names if name != current), names[0])
        self.window.on_theme_changed(next_theme)
        self.app.processEvents()

    def _assert_smoke_objects_exist(self, page_name: str) -> None:
        for object_name in SMOKE_OBJECT_NAMES:
            matches = self.window.findChildren(QWidget, object_name)
            self.assertTrue(
                matches,
                f"Missing objectName '{object_name}' while on page '{page_name}'",
            )

    def test_main_window_navigation_and_theme_switch_keep_smoke_widgets(self) -> None:
        pages = ("Garage", "Parts", "Tuning", "Builds", "My Cars", "Profile", "Settings")

        for page_name in pages:
            self._navigate(page_name)
            self._assert_smoke_objects_exist(page_name)

        self._switch_theme_once()

        for page_name in pages:
            self._navigate(page_name)
            self._assert_smoke_objects_exist(f"{page_name} after theme switch")


if __name__ == "__main__":
    unittest.main()
