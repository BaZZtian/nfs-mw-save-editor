from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QSizePolicy, QWidget

from ui.main_window import MainWindow, _scrolled_card_gap
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


def test_footer_floats_over_the_stack_and_preserves_public_controls():
    window = _window()
    layout = window.centralWidget().layout()
    assert isinstance(layout, QGridLayout)

    # The footer left the grid.  It is parked on the bottom of the content
    # stack, which now spans its row, so lists scroll *under* the footer
    # instead of being sliced by an invisible viewport edge 19px above it.
    assert layout.indexOf(window.footer_chrome) == -1
    assert window.footer_chrome.parentWidget() is window.centralWidget()
    stack_index = layout.indexOf(window.stack)
    nav_index = layout.indexOf(window.nav_chrome)
    assert layout.getItemPosition(stack_index) == (1, 1, 2, 1)
    assert layout.getItemPosition(nav_index) == (0, 0, 3, 1)
    # No explicit minimumHeight: Qt replaces the computed layout minimum with an
    # explicit one instead of widening it, which used to let the grid squeeze the
    # footer row and clip the action buttons.  See the short-window test below.
    assert window.footer_chrome.minimumHeight() == 0
    assert window.footer_chrome.sizePolicy().verticalPolicy() == QSizePolicy.Fixed

    footer_rect = window.footer_chrome.geometry()
    stack_rect = window.stack.geometry()
    assert footer_rect.left() == stack_rect.left()
    assert footer_rect.width() == stack_rect.width()
    assert footer_rect.bottom() == stack_rect.bottom()
    assert footer_rect.top() > stack_rect.top()

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


def test_scrolled_page_runs_under_the_footer_and_stops_one_gap_short():
    """The tail contract: a list ends the same distance from the footer as its
    own items stand from each other, and nothing of it is unreachable.

    Before the footer floated, every scrolling page died against the viewport
    edge 19px above the footer - an edge with no pixels of its own, which read
    as an invisible visor shaving the cards.
    """

    window = _window()
    window.resize(1180, 700)
    window._select_page("Settings")
    QTest.qWait(40)
    APP.processEvents()

    area = window.page_settings
    content = area.widget()
    gap = _scrolled_card_gap(content.layout())
    assert gap > 0

    bar = area.verticalScrollBar()
    assert bar.maximum() > 0, "settings must overflow for this contract to mean anything"
    bar.setValue(bar.maximum())
    QTest.qWait(20)
    APP.processEvents()

    viewport = area.viewport()
    footer_top = window.footer_chrome.mapTo(window, QPoint(0, 0)).y()
    viewport_bottom = viewport.mapTo(window, QPoint(0, 0)).y() + viewport.height()
    assert viewport_bottom > footer_top, "the list must reach under the footer"

    last_bottom = max(
        child.mapTo(window, QPoint(0, 0)).y() + child.height()
        for child in content.findChildren(QWidget)
        if child.parentWidget() is content and child.isVisible()
    )
    assert footer_top - last_bottom == gap
    _close_window(window)


def test_short_window_never_clips_the_footer_actions():
    """The window's vertical floor must not eat the footer's own height.

    Regression: the footer carried a hardcoded ``setMinimumHeight(60)`` while its
    layout wanted 64, so at the floor the grid handed the action row 42px for
    46px buttons and their bottom edge (with the footer's border) was cut off.
    """

    window = _window()
    for height in (780, 700, 600, 400):
        window.resize(1180, height)
        QTest.qWait(20)
        APP.processEvents()
        footer = window.footer_chrome
        assert footer.height() == footer.sizeHint().height()
        assert window.footer_actions.height() >= window.footer_actions.sizeHint().height()
        for button in (window.btn_reset_want, window.btn_apply, window.btn_save_footer):
            assert button.geometry().bottom() <= window.footer_actions.rect().bottom()
            assert button.geometry().bottom() <= footer.rect().bottom()
    _close_window(window)


def test_footer_context_follows_page_and_actions_never_hide():
    window = _window(1180)
    window._footer_page_name = "Junkman"
    window._sync_footer_context_visibility(force=True)
    assert window.footer_context.isVisible()
    assert window.footer_junkman_context.isVisible()

    # Profile keeps its garage summary on the page, so it contributes no
    # footer context at all -- the strip collapses like on a plain page.
    window._select_page("Profile")
    APP.processEvents()
    assert not window.footer_context.isVisible()
    assert not window.footer_junkman_context.isVisible()

    # Career keeps its lifetime totals on the page, so it contributes no
    # footer context either -- Junkman is the only page that fills the slot.
    window._select_page("Career")
    APP.processEvents()
    assert not window.footer_context.isVisible()

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


def test_footer_reset_slot_keeps_one_width_across_pages():
    """The reset slot swaps its caption per page and must not resize doing it.

    Regression: "Reload from disk" is 8px narrower than "Reset Want=Have", so the
    Career footer's first button was visibly smaller than every other page's.
    """

    window = _window()
    seen = {}
    for page_name in ("Junkman", "Career", "Garage"):
        window._select_page(page_name)
        APP.processEvents()
        QTest.qWait(20)
        seen[page_name] = (
            window.btn_reset_want.text(),
            window.btn_reset_want.width(),
            window.btn_apply.x(),
        )

    captions = {text for text, _, _ in seen.values()}
    geometry = {(width, apply_x) for _, width, apply_x in seen.values()}
    assert len(captions) == 2, "caption must actually change, or this proves nothing"
    assert len(geometry) == 1
    _close_window(window)


def test_footer_strip_regrows_when_its_numbers_arrive():
    """Numbers landing in an already-visible strip must not be painted clipped.

    Regression: the strip is capped at its own size hint, and only a window
    resize or a page switch recomputed that cap.  Opening a save while already
    standing on Career grew the totals from "—" to "100 / 173" against a cap
    frozen at the empty-state width, so the footer read "100 / 1", "MILESTON".
    """

    window = _window()
    window._select_page("Junkman")
    APP.processEvents()
    QTest.qWait(20)
    strip = window.footer_junkman_context
    empty_hint = strip.sizeHint().width()

    window.lbl_free.setText("Free slots: 34/63 - unlocked 63/63")
    APP.processEvents()
    QTest.qWait(20)

    assert strip.sizeHint().width() > empty_hint, "the numbers must widen the strip"
    assert window.footer_context.maximumWidth() >= strip.sizeHint().width()
    assert strip.width() >= strip.sizeHint().width()
    for label in strip.findChildren(QLabel):
        assert label.width() >= label.sizeHint().width(), label.text()
    _close_window(window)


def test_career_totals_live_on_the_page_without_moving_local_metrics():
    window = _window(1180)
    assert set(window._footer_contexts) == {"Junkman"}

    assert set(window.profile_summary_values) == {
        "career_cars",
        "pink_slips",
        "my_cars",
        "free_career_slots",
    }
    # The garage summary reads as tiles on the Profile page itself.
    for value in window.profile_summary_values.values():
        assert window.page_profile.isAncestorOf(value)
        assert not window.footer_chrome.isAncestorOf(value)

    for value in (
        window.career_total_races_value,
        window.career_total_milestones_value,
        window.career_total_bounty_value,
        window.career_total_prologue_value,
    ):
        assert window.career_totals_plate.isAncestorOf(value)
        assert window.page_career.isAncestorOf(value)
        assert not window.footer_chrome.isAncestorOf(value)

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
    assert not window.footer_context.isVisible()
    window._select_page("Career")
    APP.processEvents()
    assert not window.footer_context.isVisible()
    assert window.career_totals_plate.isVisible()

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
    """The fit threshold is per page, not a constant of the footer."""

    window = _window(1920)
    window._select_page("Junkman")
    APP.processEvents()
    window._sync_footer_context_visibility(force=True)
    with_context = window._footer_context_required_width()
    assert window.footer_context.isVisible()

    # Career contributes no context at all now, so its threshold is the bare
    # actions row and the strip stays collapsed.
    window._select_page("Career")
    APP.processEvents()
    window._sync_footer_context_visibility(force=True)
    without_context = window._footer_context_required_width()
    assert not window.footer_context.isVisible()

    assert without_context < with_context
    _close_window(window)


def test_visible_footer_context_does_not_raise_window_width_floor():
    window = _window(1920)
    for page_name in window._footer_contexts:
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

    assert window.career_totals_plate.isVisible()
    assert window.footer_chrome.property("_scopedThemeName") == original
    assert "QLabel#footerMetricCaption" in window.footer_chrome.styleSheet()
    _close_window(window)
