from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGridLayout

from ui.main_window import MainWindow
from ui.pages import constants
from ui.theme import available_theme_names


APP = QApplication.instance() or QApplication([])


def _window(width: int = 1180) -> MainWindow:
    window = MainWindow()
    window.resize(width, 780)
    window.show()
    QTest.qWait(30)
    APP.processEvents()
    return window


def _close_window(window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    APP.processEvents()


def test_footer_is_a_layout_row_and_preserves_public_controls():
    window = _window()
    layout = window.centralWidget().layout()
    assert isinstance(layout, QGridLayout)

    footer_index = layout.indexOf(window.footer_chrome)
    nav_index = layout.indexOf(window.nav_chrome)
    assert layout.getItemPosition(footer_index) == (2, 1, 1, 1)
    assert layout.getItemPosition(nav_index) == (0, 0, 3, 1)
    assert window.footer_chrome.minimumHeight() == 60
    assert window.footer_chrome.geometry().top() > window.stack.geometry().bottom()

    for name in (
        "btn_save_footer",
        "btn_reset_want",
        "btn_apply",
        "lbl_free",
        "progress_bar",
    ):
        assert hasattr(window, name)

    assert window.footer_chrome in window._shell_theme_roots
    assert not hasattr(constants, "FOOTER_CLEARANCE")
    _close_window(window)


def test_footer_context_follows_page_and_actions_never_hide():
    window = _window(1180)
    window._footer_page_name = "Junkman"
    window._sync_footer_context_visibility(force=True)
    assert window.footer_context.isVisible()
    assert window.footer_junkman_context.isVisible()

    window._select_page("Profile")
    APP.processEvents()
    assert window.footer_context.isVisible()
    assert window.profile_footer_context.isVisible()
    assert not window.footer_junkman_context.isVisible()

    window._select_page("Career")
    APP.processEvents()
    assert window.footer_context.isVisible()
    assert window.career_footer_context.isVisible()
    assert not window.profile_footer_context.isVisible()

    window._select_page("Garage")
    APP.processEvents()
    assert not window.footer_context.isVisible()
    assert window.footer_actions.isVisible()
    assert all(
        button.isVisible()
        for button in (window.btn_reset_want, window.btn_apply, window.btn_save_footer)
    )

    window.resize(850, 780)
    QTest.qWait(20)
    assert window.footer_actions.isVisible()
    assert all(
        button.isVisible()
        for button in (window.btn_reset_want, window.btn_apply, window.btn_save_footer)
    )
    _close_window(window)


def test_profile_and_career_totals_live_in_footer_without_moving_local_metrics():
    window = _window(1180)
    assert set(window._footer_contexts) == {"Junkman", "Profile", "Career"}

    assert set(window.profile_summary_values) == {
        "career_cars",
        "pink_slips",
        "my_cars",
        "free_career_slots",
    }
    for value in window.profile_summary_values.values():
        assert window.profile_footer_context.isAncestorOf(value)
        assert window.footer_chrome.isAncestorOf(value)
        assert not window.page_profile.isAncestorOf(value)

    for value in (
        window.career_total_races_value,
        window.career_total_milestones_value,
        window.career_total_bounty_value,
        window.career_total_prologue_value,
    ):
        assert window.career_footer_context.isAncestorOf(value)
        assert window.footer_chrome.isAncestorOf(value)
        assert not window.page_career.isAncestorOf(value)

    for hero_value in (
        window.career_races_value,
        window.career_milestones_value,
        window.career_bounty_value,
    ):
        assert window.page_career.isAncestorOf(hero_value)
        assert not window.footer_chrome.isAncestorOf(hero_value)

    for local_value, page in (
        (window.garage_alloc_owned, window.page_garage),
        (window.garage_alloc_career, window.page_garage),
        (window.garage_alloc_blocked, window.page_garage),
        (window.parts_alloc_owned, window.page_parts),
        (window.parts_alloc_career, window.page_parts),
        (window.parts_alloc_blocked, window.page_parts),
        (window.presets_free_career_badge, window.page_presets),
    ):
        assert page.isAncestorOf(local_value)
        assert not window.footer_chrome.isAncestorOf(local_value)

    _close_window(window)


def test_moved_totals_refresh_without_page_parent_dependencies():
    window = _window(1180)
    window._refresh_profile_summary(False)
    assert {label.text() for label in window.profile_summary_values.values()} == {"-"}
    window._update_career_totals(None)
    assert window.career_total_races_value.text() == "—"

    window._select_page("Profile")
    APP.processEvents()
    assert window.profile_footer_context.isVisible()
    window._select_page("Career")
    APP.processEvents()
    assert window.career_footer_context.isVisible()

    _close_window(window)


def test_footer_context_width_hysteresis_is_40_pixels():
    window = _window(1180)
    window._footer_page_name = "Junkman"
    window._sync_footer_context_visibility(force=True)
    assert window._footer_context_expanded

    threshold = window._footer_context_required_width()
    shell_overhead = window.width() - window._footer_available_width()

    window.resize(threshold + shell_overhead - 1, 780)
    QTest.qWait(20)
    assert not window._footer_context_expanded

    window.resize(threshold + shell_overhead + 20, 780)
    QTest.qWait(20)
    assert not window._footer_context_expanded

    window.resize(threshold + shell_overhead + 41, 780)
    QTest.qWait(20)
    assert window._footer_context_expanded
    assert window.footer_context.isVisible()
    _close_window(window)


def test_footer_recalculates_threshold_for_each_page_context():
    window = _window(1920)
    thresholds = {}
    for page_name in ("Junkman", "Profile", "Career"):
        window._select_page(page_name)
        APP.processEvents()
        window._sync_footer_context_visibility(force=True)
        thresholds[page_name] = window._footer_context_required_width()
        assert window.footer_context.isVisible()

    assert len(set(thresholds.values())) > 1
    _close_window(window)


def test_visible_footer_context_does_not_raise_window_width_floor():
    window = _window(1920)
    for page_name in ("Junkman", "Profile", "Career"):
        window._select_page(page_name)
        window._sync_footer_context_visibility(force=True)
        QTest.qWait(20)
        context = window._footer_contexts[page_name]
        visible_floor = window.minimumWidth()
        assert window.footer_context.width() == context.sizeHint().width()

        window.footer_context.hide()
        window.footer_chrome.layout().invalidate()
        window.footer_chrome.updateGeometry()
        QTest.qWait(20)
        hidden_floor = window.minimumWidth()

        assert visible_floor <= hidden_floor
    _close_window(window)


def test_footer_width_sweep_keeps_actions_and_hides_context_when_needed():
    window = _window(850)
    window._footer_page_name = "Junkman"
    threshold = window._footer_context_required_width()

    for width in (850, 900, 940, 1180, 1440, 1920):
        window.resize(width, 780)
        QTest.qWait(20)
        available = window._footer_available_width()
        assert window.footer_actions.isVisible()
        assert all(
            button.isVisible()
            for button in (window.btn_reset_want, window.btn_apply, window.btn_save_footer)
        )
        if available < threshold:
            assert not window.footer_context.isVisible()
        elif available >= threshold + 40:
            assert window.footer_context.isVisible()

    _close_window(window)


def test_footer_uses_shell_theme_when_page_theme_is_lazy():
    window = _window()
    original = window.theme_name
    window._select_page("Profile")
    APP.processEvents()
    replacement = next(name for name in available_theme_names() if name != window.theme_name)
    window.on_theme_changed(replacement)
    APP.processEvents()

    assert window.footer_chrome.property("_scopedThemeName") == replacement
    assert "QFrame#footerChrome" in window.footer_chrome.styleSheet()
    assert "QLabel#footerMetricCaption" in window.footer_chrome.styleSheet()

    window._select_page("Settings")
    APP.processEvents()
    window.on_theme_changed(original)
    APP.processEvents()
    window._select_page("Career")
    APP.processEvents()

    assert window.career_footer_context.isVisible()
    assert window.footer_chrome.property("_scopedThemeName") == original
    assert "QFrame#footerChrome QLabel#careerTotalsCaption" in (
        window.footer_chrome.styleSheet()
    )
    _close_window(window)
