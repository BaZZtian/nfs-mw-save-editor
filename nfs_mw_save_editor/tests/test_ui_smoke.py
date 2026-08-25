import os
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QAbstractAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QTextBrowser,
    QWidget,
)

from core.models import (
    FullCarBuildSnapshot,
    OwnedCarTemplate,
    OwnedCarTransferPlan,
    ResolvedTransferCarEntry,
    SnapshotInjectionPlan,
)
from core.savefile import SaveFile
from ui.main_window import MainWindow
from ui.pages.garage_mixin import GarageCardVm
from ui.pages.parts_mixin import PartsCardVm, ReusablePartsCardWidget, TuningCardEntry
from ui.pages.presets_mixin import SnapshotCardVm, SnapshotLibraryCardVm
from ui.theme import (
    available_theme_names,
    build_page_stylesheet,
    build_shell_stylesheet,
    load_ui_setting,
    resolve_theme_tokens,
)
from ui.widgets import AvailabilityButton


SMOKE_OBJECT_NAMES = (
    "appChromeRoot",
    "contentStack",
    "navChrome",
    "navBrandLogo",
    "navButton",
    "pageControlsRow",
    "pageControlsSection",
    "pageControlsSearchHost",
    "filterButton",
    "garageCard",
    "contentCard",
    "cardActionButton",
    "contentCardSlot",
    "contentCardMeta",
    "contentCardSep",
    "contentCardFieldLabel",
    "contentCardStatBadge",
    "contentCardNote",
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


def _tuning_card_vm() -> PartsCardVm:
    entry = TuningCardEntry(
        raw_entry=object(),
        display_name="BMW M3 GTR",
        source_kind="My Cars",
        pink_slip=False,
        parts_slot=32,
        block_abs_off=0xA32D,
        career_slot=1,
        car_number=0x31,
        marker=b"\x20\xCD\xCD\xCD",
        confirmed_raw=b"\x00" * 0x20,
        junkman_mask=0,
    )
    return PartsCardVm(
        card_entry=entry,
        changed=False,
        is_active=False,
        levels={},
        mask=0,
        statuses=["Stock"],
        limits=None,
    )


def _build_snapshot() -> FullCarBuildSnapshot:
    signature = b"\x01" * SaveFile.CAREER_VEHICLE_SIGNATURE_SIZE
    block = b"\x00" * SaveFile.PARTS_BLOCK_SIZE
    return FullCarBuildSnapshot(
        car_abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET,
        display_name="BMW M3 GTR",
        source_kind="Career",
        car_number=0x31,
        signature=signature,
        location_bits=SaveFile.CAREER_FLAG,
        misc_bits=0x0F,
        parts_slot=32,
        career_slot=1,
        primary_owned_record_template=OwnedCarTemplate(
            car_number=0x31,
            signature=signature,
            location_bits=SaveFile.CAREER_FLAG,
            misc_bits=0x0F,
            source_kind="Career",
        ),
        primary_build_block_abs_off=0xA32D,
        primary_build_block=block,
        normalized_primary_build_block=block,
        performance_levels=(),
        primary_visual_fields=(),
        optional_visual_sidecar=None,
    )


def _garage_my_cars_vm() -> GarageCardVm:
    vm = _garage_card_vm()
    slot = replace(
        vm.slot,
        source_kind="My Cars",
        location_bits=SaveFile.MY_CARS_FLAG,
        career_slot=SaveFile.EMPTY_CAREER_SLOT,
        is_career=False,
        is_my_cars=True,
        has_pursuit_link=False,
        pursuit_abs_off=None,
    )
    return replace(vm, slot=slot, projected_slot=slot)


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

    def test_about_uses_native_open_source_dialog_and_external_links(self) -> None:
        self.assertIsNotNone(self.window.btn_third_party_notices)
        self.assertEqual(self.window.btn_third_party_notices.text(), "Open-source software")

        dialog = self.window._build_open_source_dialog()
        self.assertEqual(dialog.objectName(), "openSourceDialog")
        labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("Qt / PySide6 / shiboken6 6.10.1", labels)
        self.assertIn("Python 3.13.14", labels)
        self.assertIn("NumPy 2.5.1", labels)
        self.assertIn("PyInstaller 6.18.0", labels)

        link_buttons = {
            button.text(): button
            for button in dialog.findChildren(QPushButton, "openSourceLink")
        }
        self.assertIn("Qt licensing", link_buttons)
        self.assertNotIn("Request source", link_buttons)
        self.assertIsNotNone(dialog.findChild(QPushButton, "viewLicenseTexts"))

        with patch("ui.pages.settings_mixin.QDesktopServices.openUrl", return_value=True) as open_url:
            link_buttons["Qt licensing"].click()

        opened_url = open_url.call_args.args[0]
        self.assertFalse(opened_url.isLocalFile())
        self.assertEqual(opened_url.host(), "doc.qt.io")
        dialog.close()

        license_dialog = self.window._build_license_text_dialog()
        selector = license_dialog.findChild(QComboBox, "licenseDocumentSelector")
        viewer = license_dialog.findChild(QTextBrowser, "licenseTextViewer")
        self.assertIsNotNone(selector)
        self.assertIsNotNone(viewer)
        self.assertIn("Third-party notices", viewer.toPlainText())

        qt_index = selector.findText("Qt third-party licenses")
        self.assertGreaterEqual(qt_index, 0)
        selector.setCurrentIndex(qt_index)
        QApplication.processEvents()
        self.assertIn("D3D12 Memory Allocator", viewer.toPlainText())
        self.assertIn("FULL LICENSE TEXTS", viewer.toPlainText())
        license_dialog.close()

    def test_page_stylesheet_uses_shared_content_card_selectors(self) -> None:
        stylesheet = build_page_stylesheet(self.window.theme_name)

        expected_selectors = (
            "QFrame#contentCard {",
            'QFrame#contentCard[changed="true"] {',
            "QPushButton#cardActionButton {",
            "QPushButton#cardActionButton:hover {",
            "QPushButton#cardActionButton:disabled {",
            "QLabel#contentCardSlot {",
            "QLabel#contentCardMeta {",
            "QLabel#contentCardFieldLabel {",
            "QFrame#contentCardSep {",
            "QLabel#contentCardRaw {",
            "QLabel#contentCardNote {",
            "QLabel#contentCardStatBadge {",
        )
        for selector in expected_selectors:
            self.assertIn(selector, stylesheet)
        self.assertIn('QPushButton#partsJunkmanToggle[blocked="true"] {', stylesheet)
        self.assertIn('QPushButton#cardActionButton[readyAction="true"] {', stylesheet)

        removed_selectors = (
            "#parts" + "Card",
            "#parts" + "BulkBtn",
            "#garage" + "CardSlot",
            "#garage" + "CardMeta",
            "#garage" + "CardFieldLabel",
            "#garage" + "CardSep",
            "#parts" + "CardRaw",
            "#parts" + "CardNote",
            "#garage" + "CardStatBadge",
        )
        for selector in removed_selectors:
            self.assertNotIn(selector, stylesheet)

    def test_nav_shell_is_carded_and_branded(self) -> None:
        stylesheet = build_shell_stylesheet(self.window.theme_name)
        tokens = resolve_theme_tokens(self.window.theme_name)
        self.assertIn("QFrame#navChrome {", stylesheet)
        self.assertIn("QLabel#navBrandLogo {", stylesheet)
        self.assertIn(f"background: {tokens['BG_CARD']};", stylesheet)
        self.assertIn(f"border: 1px solid {tokens['BORDER']};", stylesheet)
        self.assertEqual(self.window.nav_chrome.width(), 150)
        logo = self.window.findChild(QLabel, "navBrandLogo")
        self.assertIsNotNone(logo)
        self.assertEqual(logo.height(), 92)
        self.assertIsNotNone(logo.pixmap())
        self.assertFalse(logo.pixmap().isNull())
        self.assertIsNone(logo.graphicsEffect())

    def test_diagnostic_settings_are_independent_and_persist(self) -> None:
        self.assertFalse(self.window.show_technical_card_details)
        self.assertFalse(self.window.show_garage_allocator_diagnostics)
        self.assertFalse(self.window.show_tuning_raw_diagnostics)
        self.assertFalse(hasattr(self.window, "chk_show_parts_diagnostics"))

        tuning_page_toggles = [
            checkbox.text()
            for checkbox in self.window.page_parts.findChildren(QCheckBox)
        ]
        self.assertNotIn("Show parts diagnostics", tuning_page_toggles)

        self.window.chk_show_technical_card_details.setChecked(True)
        self.window.chk_show_garage_allocator_diagnostics.setChecked(True)
        self.window.chk_show_tuning_raw_diagnostics.setChecked(True)
        self.app.processEvents()

        self.assertTrue(load_ui_setting("show_technical_card_details"))
        self.assertTrue(load_ui_setting("show_garage_allocator_diagnostics"))
        self.assertTrue(load_ui_setting("show_tuning_raw_diagnostics"))

        self.window.close()
        self.window = MainWindow()
        self.assertTrue(self.window.show_technical_card_details)
        self.assertTrue(self.window.show_garage_allocator_diagnostics)
        self.assertTrue(self.window.show_tuning_raw_diagnostics)
        self.assertTrue(self.window.chk_show_technical_card_details.isChecked())
        self.assertTrue(self.window.chk_show_garage_allocator_diagnostics.isChecked())
        self.assertTrue(self.window.chk_show_tuning_raw_diagnostics.isChecked())

    def test_technical_card_details_toggle_garage_tuning_and_builds_metadata(self) -> None:
        garage_vm = _garage_card_vm()
        garage_handle = self.window._garage_card_handles[garage_vm.slot.abs_off]
        self.assertFalse(garage_handle.slot_label.isHidden())
        self.assertEqual(garage_handle.slot_label.text(), "Career Slot 2")
        self.assertTrue(garage_handle.parts_badge.isHidden())
        self.assertTrue(garage_handle.loc_badge.isHidden())
        self.assertTrue(garage_handle.misc_badge.isHidden())
        self.assertEqual(garage_handle.card.toolTip(), "")

        tuning_vm = _tuning_card_vm()
        tuning_card = ReusablePartsCardWidget(self.window, diagnostics=False)
        tuning_card.apply_vm(tuning_vm)
        tuning_handle = tuning_card.handle
        self.assertTrue(tuning_handle.slot_badge.isHidden())
        self.assertTrue(tuning_handle.parts_badge.isHidden())
        self.assertTrue(tuning_handle.block_badge.isHidden())
        self.assertTrue(tuning_handle.career_badge.isHidden())

        snapshot_vm = SnapshotCardVm(snapshot=_build_snapshot())
        snapshot_card = self.window._build_snapshot_card(snapshot_vm)
        snapshot_slot = next(
            label for label in snapshot_card.findChildren(QLabel)
            if label.text() == "Parts Slot 32"
        )
        self.assertTrue(snapshot_slot.isHidden())
        self.assertEqual(snapshot_card.toolTip(), "")

        self.window.show_technical_card_details = True
        self.window._apply_garage_card_vm(garage_handle, garage_vm)
        tuning_card.apply_vm(tuning_vm)
        detailed_snapshot_card = self.window._build_snapshot_card(snapshot_vm)
        detailed_snapshot_slot = next(
            label for label in detailed_snapshot_card.findChildren(QLabel)
            if label.text() == "Parts Slot 32"
        )

        self.assertFalse(garage_handle.parts_badge.isHidden())
        self.assertFalse(garage_handle.loc_badge.isHidden())
        self.assertFalse(garage_handle.misc_badge.isHidden())
        self.assertIn("Loc 0x02", garage_handle.card.toolTip())
        self.assertFalse(tuning_handle.slot_badge.isHidden())
        self.assertEqual(tuning_handle.slot_badge.text(), "Car #31")
        self.assertFalse(tuning_handle.parts_badge.isHidden())
        self.assertFalse(tuning_handle.block_badge.isHidden())
        self.assertFalse(tuning_handle.career_badge.isHidden())
        self.assertEqual(tuning_handle.career_badge.text(), "Career Slot 2")
        self.assertFalse(detailed_snapshot_slot.isHidden())
        self.assertIn("Block 0x0A32D", detailed_snapshot_card.toolTip())

    def test_hidden_identity_badge_collapses_into_the_name_row(self) -> None:
        garage_card = self.window._build_garage_card(_garage_my_cars_vm())
        garage_handle = self.window._garage_card_handles[0x6200]
        tuning_card = ReusablePartsCardWidget(self.window, diagnostics=False)
        tuning_card.apply_vm(_tuning_card_vm())
        snapshot_card = self.window._build_snapshot_card(SnapshotCardVm(snapshot=_build_snapshot()))

        cases = (
            (garage_card, garage_handle.slot_label, garage_handle.name_label),
            (tuning_card, tuning_card.handle.slot_badge, tuning_card.handle.name_label),
            (
                snapshot_card,
                next(label for label in snapshot_card.findChildren(QLabel) if label.text() == "Parts Slot 32"),
                next(label for label in snapshot_card.findChildren(QLabel) if label.text() == "BMW M3 GTR"),
            ),
        )
        for card, technical_badge, name_label in cases:
            header_layout = card.layout().itemAt(0).layout()
            identity_layout = header_layout.itemAt(0).layout()
            self.assertIs(identity_layout.itemAt(0).widget(), technical_badge)
            self.assertIs(identity_layout.itemAt(1).widget(), name_label)
            self.assertTrue(technical_badge.isHidden())

    def test_readiness_moves_into_actions_and_junkman_controls(self) -> None:
        garage_vm = _garage_card_vm()
        garage_handle = self.window._garage_card_handles[garage_vm.slot.abs_off]
        self.assertTrue(garage_handle.move_my_cars_btn.property("readyAction"))
        self.assertTrue(garage_handle.utility_label.isHidden())

        tuning_card = ReusablePartsCardWidget(self.window, diagnostics=False)
        tuning_card.apply_vm(_tuning_card_vm())
        tuning_handle = tuning_card.handle
        self.assertEqual(tuning_handle.junkman_label.text(), "Junkman · 2 locked")
        self.assertIn("Turbo: Requires regular Turbo", tuning_handle.junkman_label.toolTip())
        self.assertIn("NOS: Requires regular NOS", tuning_handle.junkman_label.toolTip())
        self.assertTrue(tuning_handle.junkman_buttons["Turbo"].property("blocked"))
        self.assertTrue(tuning_handle.junkman_buttons["NOS"].property("blocked"))
        self.assertIn("Requires regular Turbo", tuning_handle.junkman_buttons["Turbo"].toolTip())
        self.assertFalse(tuning_handle.junkman_buttons["Engine"].property("blocked"))
        self.assertTrue(tuning_handle.junkman_buttons["Engine"].isEnabled())

        ready_tuning_vm = replace(
            _tuning_card_vm(),
            levels={"Turbo": 1, "NOS": 1},
        )
        tuning_card.apply_vm(ready_tuning_vm)
        self.assertEqual(tuning_handle.junkman_label.text(), "Junkman")
        self.assertEqual(tuning_handle.junkman_label.toolTip(), "")

        entry = self.window.snapshot_library[0]
        plan_my = SnapshotInjectionPlan(
            snapshot_id=entry.snapshot_id,
            display_name=entry.display_name,
            target_mode="my_cars",
            target_location_bits=SaveFile.MY_CARS_FLAG,
            target_misc_bits=0x0F,
            target_owned_abs_off=0x6200,
            target_parts_slot=32,
            target_career_slot=None,
            refusal_reason=None,
            warnings=(),
        )
        plan_career = replace(
            plan_my,
            target_mode="career",
            target_location_bits=SaveFile.CAREER_FLAG,
            target_career_slot=1,
        )
        self.window.savefile = object()
        library_vm = SnapshotLibraryCardVm(
            entry=entry,
            staged_mode=None,
            plan_my=plan_my,
            plan_career=plan_career,
            staged_plan=None,
        )
        self.window._build_snapshot_library_card(library_vm)
        library_handle = self.window._snapshot_library_card_handles[entry.snapshot_id]
        self.assertTrue(library_handle.inject_my_btn.property("readyAction"))
        self.assertTrue(library_handle.inject_career_btn.property("readyAction"))
        self.assertEqual(
            library_handle.inject_my_btn.toolTip(),
            "Stage this build for My Cars.",
        )
        self.assertTrue(library_handle.utility_label.isHidden())

        blocked_career = replace(plan_career, refusal_reason="No reusable Career slot")
        self.window._apply_snapshot_library_card_vm(
            library_handle,
            replace(library_vm, plan_career=blocked_career),
        )
        self.assertFalse(library_handle.inject_career_btn.property("readyAction"))
        self.assertFalse(library_handle.inject_career_btn.isEnabled())
        self.assertEqual(
            library_handle.inject_career_btn.toolTip(),
            "No reusable Career slot",
        )
        self.assertEqual(library_handle.utility_label.text(), "Career blocked")
        self.assertFalse(library_handle.utility_label.isHidden())

    def test_junkman_unlock_feedback_is_short_interruptible_and_motion_safe(self) -> None:
        button = AvailabilityButton("Turbo")
        button.show()
        self.app.processEvents()
        try:
            button._motion_allowed = lambda: True
            button.setAvailability(False, "Requires regular Turbo > 0", animated=False)
            button.setAvailability(True)

            animation = button._unlock_animation
            self.assertIsNotNone(animation)
            self.assertEqual(animation.state(), QAbstractAnimation.Running)
            self.assertEqual(animation.duration(), 180)
            self.assertEqual(animation.easingCurve().type(), QEasingCurve.OutCubic)
            self.assertAlmostEqual(button._unlock_effect.opacity(), 0.58)

            animation.setCurrentTime(animation.duration() // 2)
            self.assertGreater(button._unlock_effect.opacity(), 0.58)
            self.assertLess(button._unlock_effect.opacity(), 1.0)

            button.setAvailability(False, "Requires regular Turbo > 0")
            self.assertIsNone(button._unlock_animation)
            self.assertIsNone(button.graphicsEffect())

            button.setAvailability(True)
            completed = button._unlock_animation
            self.assertIsNotNone(completed)
            completed.setCurrentTime(completed.duration())
            self.app.processEvents()
            self.assertIsNone(button._unlock_animation)
            self.assertIsNone(button.graphicsEffect())

            button.resetAvailabilityTracking()
            button._motion_allowed = lambda: False
            button.setAvailability(False, "Requires regular Turbo > 0", animated=False)
            button.setAvailability(True)
            self.assertIsNone(button._unlock_animation)
            self.assertIsNone(button.graphicsEffect())
            self.assertTrue(button.isEnabled())
        finally:
            button.close()


if __name__ == "__main__":
    unittest.main()
