from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core import career_progress, career_transplant
from ui.icon_map import game_icon_path, nav_icon_path, rival_asset_path
from ui.main_window import MainWindow
from ui.pages.career_mixin import _CareerHero, _ProgressMarkerStrip
from ui.theme import apply_theme_palette
from ui.widgets import AnimatedSegmentedControl, AnimatedStackedWidget, ShellActionButton

APP = QApplication.instance() or QApplication([])


def _app() -> QApplication:
    return APP


def _synthetic_career(stage: int = 15, *, endgame: bool = False) -> bytearray:
    data = bytearray(career_transplant.EXPECTED_SAVE_SIZE)
    data[
        career_transplant.GAME_MAGIC_OFFSET:
        career_transplant.GAME_MAGIC_OFFSET + len(career_transplant.GAME_MAGIC)
    ] = career_transplant.GAME_MAGIC
    struct.pack_into(
        "<IIII",
        data,
        career_progress.HEADER_TIMER_COUNT_OFFSET,
        1,
        1,
        1,
        0,
    )
    timers_base = career_transplant.GAME_SECTION_START + 0x2A0
    name_off = timers_base + career_progress.TIMER_NAME_REL
    data[name_off:name_off + len(career_progress.ANCHOR_TIMER_NAME) + 1] = (
        career_progress.ANCHOR_TIMER_NAME + b"\x00"
    )
    milestone_base = (
        timers_base
        + career_progress.TIMER_RECORD_SIZE
        + career_progress.TYPE_RECORD_SIZE
    )
    struct.pack_into("<IIBBHff", data, milestone_base, 1, 2, 1, 0, stage, 1.0, 0.0)
    data[career_transplant.CURRENT_BIN_OFFSET] = stage
    if endgame:
        struct.pack_into("<H", data, career_progress.SPECIAL_FLAGS_OFFSET, 0x1803)
    return data


def test_hero_art_layers_are_packaged_at_runtime_size():
    from PySide6.QtGui import QImageReader

    for stage in range(1, 16):
        graffiti = rival_asset_path(stage, "graffiti")
        portrait = rival_asset_path(stage, "hero_portrait")
        assert graffiti is not None and graffiti.is_file()
        assert portrait is not None and portrait.is_file()
        graffiti_size = QImageReader(str(graffiti)).size()
        assert graffiti_size.width() > 0
        assert graffiti_size.height() > 0
        portrait_size = QImageReader(str(portrait)).size()
        assert 0 < portrait_size.width() <= 1024
        assert 0 < portrait_size.height() <= 1024


def test_progress_marker_icons_keep_original_pixels_across_themes():
    path = game_icon_path("race_circuit")
    assert path is not None
    _ProgressMarkerStrip._pixmap_cache.clear()

    apply_theme_palette(_app(), "Cherry")
    cherry = _ProgressMarkerStrip._source_pixmap(path, 25).toImage()
    apply_theme_palette(_app(), "Kiwi")
    kiwi = _ProgressMarkerStrip._source_pixmap(path, 25).toImage()

    assert cherry == kiwi
    opaque_colors = {
        cherry.pixelColor(x, y).name()
        for y in range(cherry.height())
        for x in range(cherry.width())
        if cherry.pixelColor(x, y).alpha() == 255
    }
    assert "#ffffff" in opaque_colors


def test_game_icons_are_wired_to_hero_actions_and_tuning_nav():
    app = _app()
    window = MainWindow()
    app.processEvents()

    for metric in (
        window.career_races_metric,
        window.career_milestones_metric,
        window.career_bounty_metric,
    ):
        icon = metric.findChild(QLabel, "careerHeroMetricIcon")
        assert icon is not None
        assert icon.pixmap() is not None and not icon.pixmap().isNull()

    for button in (
        window.btn_save_header,
        window.btn_reset_want,
        window.btn_save_footer,
        window.nav_buttons["Tuning"],
        window.nav_buttons["Junkman"],
    ):
        assert not button.icon().isNull()

    assert window.btn_apply.icon().isNull()
    assert nav_icon_path("Tuning").name == "nav_tuning.png"
    assert nav_icon_path("Junkman").name == "nav_junkman.png"
    assert game_icon_path("race").name == "race_events.png"
    assert game_icon_path("timeline_check").is_file()
    assert game_icon_path("timeline_arrow").is_file()

    window.close()
    app.processEvents()


def test_shell_action_button_uses_equal_left_padding_and_icon_text_gap():
    button = ShellActionButton("Save + backup")
    path = game_icon_path("action_save")
    assert path is not None
    button.setIcon(QIcon(str(path)))
    button.setIconSize(QSize(28, 28))
    button.resize(button.sizeHint())
    icon_rect, text_rect = button._content_rects()

    assert button.height() >= 44
    assert icon_rect.left() == 8
    assert text_rect.left() - icon_rect.right() == 8
    assert button.width() - text_rect.right() == 8


def test_animated_segmented_control_rapid_switch_lands_on_last_choice():
    app = _app()
    host = QWidget()
    layout = QHBoxLayout(host)
    control = AnimatedSegmentedControl(("ONE", "TWO"))
    layout.addWidget(control)
    host.resize(360, 70)
    host.show()
    QTest.qWait(20)

    control.setCurrentIndex(1)
    control.setCurrentIndex(0)
    control.setCurrentIndex(1)
    QTest.qWait(220)
    app.processEvents()

    assert control.currentIndex() == 1
    assert abs(control._indicator_position - 1.0) < 0.001
    target = control.button(1).geometry()
    assert abs(control.indicatorRect().center().x() - target.center().x()) <= 1.0
    assert control.findChildren(QWidget, "animatedSegmentIndicator") == []
    host.close()
    app.processEvents()


def test_segmented_control_midframe_is_one_painted_surface():
    app = _app()
    host = QWidget()
    layout = QHBoxLayout(host)
    control = AnimatedSegmentedControl(("CHAPTER START", "BOSS FIGHT READY"))
    layout.addWidget(control)
    host.resize(760, 64)
    host.show()
    QTest.qWait(20)

    control.setCurrentIndex(1)
    QTest.qWait(55)
    app.processEvents()

    assert 0.0 < control._indicator_position < 1.0
    first = control.button(0).geometry()
    second = control.button(1).geometry()
    assert first.left() < control.indicatorRect().center().x() < second.right()
    assert all(button.graphicsEffect() is None for button in (control.button(0), control.button(1)))
    host.close()
    app.processEvents()


def test_segmented_control_track_shows_parent_surface():
    app = _app()
    apply_theme_palette(app, "Blueprint")
    host = QWidget()
    host.setObjectName("segmentTransparencyHost")
    host.setStyleSheet("#segmentTransparencyHost { background: #123456; }")
    layout = QHBoxLayout(host)
    control = AnimatedSegmentedControl(("PROGRESS", "CHANGE STAGE"))
    layout.addWidget(control)
    host.resize(420, 64)
    host.show()
    QTest.qWait(20)
    app.processEvents()

    image = host.grab().toImage()
    inactive = control.button(1).geometry()
    parent_surface = image.pixelColor(
        control.x() + inactive.left() + 8,
        control.y() + inactive.top() + 4,
    )
    assert parent_surface.name() == "#123456"
    host.close()
    app.processEvents()


def test_segment_hover_cannot_overpaint_parent_indicator_or_text():
    app = _app()
    host = QWidget()
    layout = QHBoxLayout(host)
    control = AnimatedSegmentedControl(("PROGRESS", "CHANGE STAGE"))
    layout.addWidget(control)
    host.resize(420, 64)
    host.show()
    QTest.qWait(20)

    active = control.button(0)
    QTest.mouseMove(active, active.rect().center())
    app.processEvents()
    image = control.grab().toImage()
    indicator = control.indicatorRect().toRect()
    accent = image.pixelColor(indicator.left() + 8, indicator.top() + 8)
    assert accent.alpha() == 255
    assert accent != image.pixelColor(control.button(1).geometry().center())
    assert active.__class__.__name__ == "_SegmentHitButton"

    control.setCurrentIndex(1)
    QTest.mouseMove(control.button(1), control.button(1).rect().center())
    QTest.qWait(55)
    assert 0.0 < control._indicator_position < 1.0
    assert control._animation.state().name == "Running"
    control.button(0).setFocus(Qt.TabFocusReason)
    app.processEvents()
    assert control.button(0).hasFocus()
    host.close()
    app.processEvents()


def test_stacked_transition_crossfades_live_pages_without_snapshot_overlay():
    app = _app()
    stack = AnimatedStackedWidget(duration_ms=180)
    first = QWidget()
    second = QWidget()
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(420, 180)
    stack.show()
    QTest.qWait(20)

    stack.setCurrentIndexAnimated(1)
    QTest.qWait(55)
    app.processEvents()

    assert stack.currentWidget() is second
    assert stack._transition_widgets == (first, second)
    assert stack.layout().stackingMode() == QStackedLayout.StackAll
    assert stack.findChildren(QLabel, "animatedStackOverlay") == []
    assert first.graphicsEffect() is not None
    assert second.graphicsEffect() is not None
    assert 0.0 < first.graphicsEffect().opacity() < 1.0
    assert 0.0 < second.graphicsEffect().opacity() < 1.0
    assert first.pos().x() == second.pos().x() == 0
    QTest.qWait(160)
    assert first.graphicsEffect() is None
    assert second.graphicsEffect() is None
    assert stack.layout().stackingMode() == QStackedLayout.StackOne
    stack.close()
    app.processEvents()


def test_stacked_transition_rapid_switch_lands_on_last_live_page():
    app = _app()
    stack = AnimatedStackedWidget(duration_ms=180)
    pages = [QWidget(), QWidget(), QWidget()]
    for page in pages:
        stack.addWidget(page)
    stack.resize(420, 180)
    stack.show()
    QTest.qWait(20)

    stack.setCurrentIndexAnimated(1)
    QTest.qWait(35)
    stack.setCurrentIndexAnimated(2)
    QTest.qWait(35)
    stack.setCurrentIndexAnimated(0)
    QTest.qWait(210)
    app.processEvents()

    assert stack.currentWidget() is pages[0]
    assert stack._transition_widgets is None
    assert stack.layout().stackingMode() == QStackedLayout.StackOne
    assert all(page.graphicsEffect() is None for page in pages)
    stack.close()
    app.processEvents()


def test_theme_refresh_snaps_live_animations_without_raster_overlay():
    app = _app()
    host = QWidget()
    layout = QVBoxLayout(host)
    control = AnimatedSegmentedControl(("PROGRESS", "CHANGE STAGE"))
    stack = AnimatedStackedWidget(duration_ms=180)
    stack.addWidget(QWidget())
    stack.addWidget(QWidget())
    layout.addWidget(control)
    layout.addWidget(stack)
    host.resize(520, 240)
    host.show()
    QTest.qWait(20)

    control.setCurrentIndex(1)
    stack.setCurrentIndexAnimated(1)
    QTest.qWait(35)
    apply_theme_palette(app, "Notion")
    app.processEvents()

    assert control._indicator_position == 1.0
    assert stack.currentWidget().pos().x() == 0
    assert stack.currentWidget().graphicsEffect() is None
    assert stack.findChildren(QLabel, "animatedStackOverlay") == []
    apply_theme_palette(app, "Blueprint")
    host.close()
    app.processEvents()


def test_all_hero_busts_stay_inside_compact_and_fullscreen_banners():
    app = _app()
    hero = _CareerHero()
    hero.show()
    for width, expected_height in ((790, 220), (1180, 220), (1640, 240)):
        hero.resize(width, expected_height)
        app.processEvents()
        assert hero.height() == expected_height
        for stage in range(1, 16):
            hero.set_stage(stage)
            safe = hero.bustSafeRect(stage, width, expected_height)
            assert safe.left() >= width * 0.52
            assert safe.right() <= width
            assert safe.top() >= 6
            assert safe.bottom() == expected_height
            source = hero.portraitSourceRect(stage)
            assert source.top() >= 0
            assert source.bottom() <= hero._portrait.height()
            assert source.height() >= hero._portrait.height() * 0.9
    hero.close()
    app.processEvents()


def test_timeline_selection_is_read_only_and_updates_selected_dossier():
    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    data = _synthetic_career(15)
    window.savefile = SimpleNamespace(data=data)
    before = bytes(data)

    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    assert window._career_selected_stage == 15
    assert window.career_timeline._state(15) == "current"

    window._on_career_timeline_selected(14)
    QTest.qWait(180)
    assert bytes(data) == before
    assert window._career_selected_stage == 14
    assert window.career_timeline._state(14) == "locked"
    assert window.career_boss_value.text() == "TAZ"
    assert window.career_hero_status.text() == "LOCKED"
    window.close()
    app.processEvents()


def test_endgame_summary_selects_razor_and_defeats_entire_timeline():
    summary = career_progress.build_career_progress(bytes(_synthetic_career(1, endgame=True)))
    assert summary is not None
    assert summary.default_stage == 1
    assert all(summary.stage_state(stage) == "defeated" for stage in range(1, 16))


def test_fullscreen_career_canvas_is_centered_and_capped():
    app = _app()
    window = MainWindow()
    window.resize(1920, 1080)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    assert window.career_canvas.width() <= 1640
    left = window.career_canvas.geometry().left()
    right = window.page_career.width() - window.career_canvas.geometry().right() - 1
    assert abs(left - right) <= 2
    window.close()
    app.processEvents()


def test_career_switches_are_read_only_and_status_stays_with_boss_name():
    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    data = _synthetic_career(8)
    window.savefile = SimpleNamespace(data=data)
    before = bytes(data)
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    window.career_view_switch.setCurrentIndex(1)
    window.career_variant_switch.setCurrentIndex(1)
    app.processEvents()
    assert window.career_stage_grid_host.graphicsEffect() is None
    window.career_variant_switch.setCurrentIndex(0)
    window.career_view_switch.setCurrentIndex(0)
    window.career_hero.resize(1000, 220)
    window.career_hero.layout().activate()
    app.processEvents()

    assert bytes(data) == before
    gap = window.career_hero_status.geometry().left() - window.career_boss_value.geometry().right()
    assert 0 <= gap <= 16
    assert window.career_hero_status.geometry().center().x() < window.career_hero.width() * 0.5
    assert not hasattr(window.career_stage_grid_host, "_refresh_transition_overlay")
    window.close()
    app.processEvents()
