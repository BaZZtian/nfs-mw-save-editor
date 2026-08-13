from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import (
    QAbstractAnimation,
    QEventLoop,
    QEvent,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QFont, QIcon, QMouseEvent, QPixmap
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
from ui.pages import career_mixin as career_module
from ui.pages.career_mixin import (
    _BlacklistTimeline,
    _CareerHero,
    _ProgressRowList,
    _race_row,
)
from ui.theme import apply_theme_palette, resolve_theme_tokens
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
    _ProgressRowList._pixmap_cache.clear()

    apply_theme_palette(_app(), "Cherry")
    cherry = _ProgressRowList._source_pixmap(path, 25).toImage()
    apply_theme_palette(_app(), "Kiwi")
    kiwi = _ProgressRowList._source_pixmap(path, 25).toImage()

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

    metrics = (
        window.career_races_metric,
        window.career_milestones_metric,
        window.career_bounty_metric,
    )
    for metric in metrics:
        icon = metric.findChild(QLabel, "careerHeroMetricIcon")
        assert icon is not None
        assert icon.pixmap() is not None and not icon.pixmap().isNull()
        assert metric.size() == QSize(204, 76)
        assert metric.findChild(QWidget, "careerHeroMetricProgress") is None

    captions = [
        metric.findChild(QLabel, "careerHeroMetricLabel").text()
        for metric in metrics
    ]
    assert captions == ["RACE WINS", "MILESTONES", "BOUNTY"]
    assert window.career_view_transplant_btn.text() == "CHANGE RIVAL"

    for button in (
        window.btn_open,
        window.btn_fix,
        window.btn_reset_want,
        window.btn_apply,
        window.btn_save_footer,
        window.nav_buttons["Tuning"],
        window.nav_buttons["Junkman"],
    ):
        assert not button.icon().isNull()
    assert nav_icon_path("Tuning").name == "nav_tuning.png"
    assert nav_icon_path("Junkman").name == "nav_junkman.png"
    assert game_icon_path("race").name == "race_events.png"
    assert game_icon_path("timeline_check").is_file()
    assert game_icon_path("timeline_arrow").is_file()

    window.close()
    app.processEvents()


def test_shell_action_button_centres_its_icon_and_label_as_one_block():
    """Icon + label sit centred, with the same margin left and right.

    The button is often wider than the two of them need - a 140px floor, or a
    width reserved for a caption this page does not show - and anchoring the
    block to the left dumped every spare pixel behind the text.
    """

    button = ShellActionButton("Save + backup")
    path = game_icon_path("action_save")
    assert path is not None
    button.setIcon(QIcon(str(path)))
    button.setIconSize(QSize(28, 28))

    for width in (button.sizeHint().width(), 220, 320):
        button.resize(width, button.sizeHint().height())
        icon_rect, text_rect = button._content_rects()
        text_end = text_rect.left() + button.fontMetrics().horizontalAdvance(button.text())

        assert button.height() >= 44
        assert text_rect.left() - icon_rect.right() == 8
        assert icon_rect.left() == pytest.approx(button.width() - text_end)
        assert icon_rect.left() >= 8


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


def test_segmented_control_indicator_follows_the_track_inset():
    app = _app()
    host = QWidget()
    layout = QHBoxLayout(host)
    control = AnimatedSegmentedControl(("PROGRESS", "CHANGE STAGE"))
    layout.addWidget(control)
    host.resize(420, 72)
    host.show()
    QTest.qWait(20)
    app.processEvents()

    track = QRectF(control.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    indicator = control.indicatorRect()
    assert abs(indicator.top() - track.top() - control._TRACK_INSET) <= 0.5
    assert abs(track.bottom() - indicator.bottom() - control._TRACK_INSET) <= 0.5
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
    stamp = QPixmap(180, 56)
    stamp.fill(Qt.GlobalColor.red)
    hero.set_defeated_stamp(stamp)
    hero.show()
    compact = _CareerHero._COMPACT_HEIGHT
    wide = _CareerHero._WIDE_HEIGHT
    for width, expected_height in ((790, compact), (1180, compact), (1640, wide)):
        hero.resize(width, expected_height)
        app.processEvents()
        assert hero.height() == expected_height
        expected_stamp_width = 210.0 if width >= 1450 else 175.0
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
            stamp_rect = hero.defeatedStampRect(stage, width, expected_height)
            assert stamp_rect.width() == expected_stamp_width
            assert QRectF(0, 0, width, expected_height).contains(stamp_rect)
            assert stamp_rect.intersects(safe)
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


def test_defeated_hero_uses_the_game_stamp_and_other_states_keep_text():
    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    window._on_career_timeline_selected(9)
    QTest.qWait(180)
    stamp = window.career_hero._defeated_stamp
    assert window.career_hero_status.property("stamp") is False
    assert window.career_hero_status.isHidden()
    assert window.career_hero_status.text() == ""
    assert not stamp.isNull()
    assert stamp.width() > window.career_hero._WIDE_STAMP_WIDTH
    assert stamp.height() > 56
    assert abs(stamp.width() / stamp.height() - 180 / 56) < 0.02
    assert window.career_hero_status.accessibleName() == "DEFEATED"
    assert window.career_hero.accessibleDescription() == "DEFEATED"
    stamp_rect = window.career_hero.defeatedStampRect(
        9, window.career_hero.width(), window.career_hero.height()
    )
    portrait_rect = window.career_hero.portraitRect(
        9, window.career_hero.width(), window.career_hero.height()
    )
    assert stamp_rect.intersects(portrait_rect)
    assert QRectF(window.career_hero.rect()).contains(stamp_rect)

    image = stamp.toImage()
    visible = [
        (x, image.pixelColor(x, y))
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    ]
    assert visible
    assert min(x for x, _color in visible) >= image.width() * 0.05
    assert max(x for x, _color in visible) <= image.width() * 0.95
    solid = [color for _x, color in visible if color.alpha() >= 250]
    assert solid
    assert max(color.red() for color in solid) == 147
    assert max(color.green() for color in solid) == 10
    assert max(color.blue() for color in solid) == 10
    ink_reds = {color.red() for _x, color in visible if color.alpha() >= 8}
    assert len(ink_reds) >= 50
    assert min(ink_reds) <= 80
    dark_backing = [
        color
        for _x, color in visible
        if color.alpha() >= 180
        and color.red() <= 24
        and color.green() <= 24
        and color.blue() <= 24
    ]
    assert len(dark_backing) >= 1000

    window._on_career_timeline_selected(8)
    QTest.qWait(180)
    assert window.career_hero_status.isHidden()
    assert window.career_hero_status.text() == ""
    assert window.career_hero._defeated_stamp.isNull()

    window._on_career_timeline_selected(7)
    QTest.qWait(180)
    assert not window.career_hero_status.isHidden()
    assert window.career_hero_status.property("stamp") is False
    assert window.career_hero_status.text() == "LOCKED"
    assert window.career_hero_status.pixmap().isNull()
    assert window.career_hero._defeated_stamp.isNull()
    window.close()
    app.processEvents()


def test_endgame_summary_selects_razor_and_defeats_entire_timeline():
    summary = career_progress.build_career_progress(bytes(_synthetic_career(1, endgame=True)))
    assert summary is not None
    assert summary.default_stage == 1
    assert all(summary.stage_state(stage) == "defeated" for stage in range(1, 16))


def test_timeline_selection_brackets_are_open_and_glide_to_the_new_stage():
    app = _app()
    summary = career_progress.build_career_progress(bytes(_synthetic_career(8)))
    assert summary is not None
    timeline = _BlacklistTimeline()
    timeline.resize(1180, 88)
    center = QPointF(40.0, 30.0)
    bracket_path = timeline._selection_bracket_path(center, 18.0, 5.5)
    subpaths = bracket_path.toSubpathPolygons()
    assert bracket_path.boundingRect() == QRectF(22.0, 12.0, 36.0, 36.0)
    assert len(subpaths) == 4
    assert all(len(polygon) == 3 for polygon in subpaths)
    assert all(not polygon.boundingRect().contains(center) for polygon in subpaths)
    timeline.set_progress(summary, 8)
    timeline.show()
    QTest.qWait(20)

    timeline.set_selected_stage(7)
    assert timeline._selection_animation.state().name == "Running"
    QTest.qWait(55)
    app.processEvents()
    assert 7.0 < timeline._selection_position < 8.0
    QTest.qWait(170)
    assert timeline._selection_position == 8.0
    timeline.close()
    app.processEvents()


def test_timeline_partial_line_tracks_real_gate_progress_and_edge_states():
    def summary(stage: int, fraction: float, *, endgame: bool = False):
        return SimpleNamespace(
            current_stage=stage,
            endgame=endgame,
            requirement_progress=lambda requested: (
                fraction if requested == stage else 0.0
            ),
            stage_state=lambda requested: (
                "defeated"
                if endgame or requested > stage
                else "boss_ready"
                if requested == stage and fraction >= 1.0
                else "current"
                if requested == stage
                else "locked"
            ),
        )

    timeline = _BlacklistTimeline()
    timeline.resize(1400, 88)
    timeline.set_progress(summary(5, 0.3), 5)
    nodes = timeline._nodes()
    points = dict(nodes)
    line = timeline._current_progress_line(nodes)
    assert line is not None
    start, end = line
    assert start == points[5]
    assert abs(
        (end.x() - start.x()) / (points[4].x() - start.x()) - 0.3
    ) < 1e-12

    timeline.set_selected_stage(12)
    selected_line = timeline._current_progress_line(timeline._nodes())
    assert selected_line is not None
    assert selected_line[0] == start
    assert selected_line[1] == end

    timeline.set_progress(summary(5, 1.0), 5)
    full_line = timeline._current_progress_line(timeline._nodes())
    assert full_line is not None and full_line[1] == dict(timeline._nodes())[4]
    assert timeline._state(4) == "locked"

    timeline.set_progress(summary(5, 0.0), 5)
    assert timeline._current_progress_line(timeline._nodes()) is None
    timeline.set_progress(summary(1, 0.8), 1)
    assert timeline._current_progress_line(timeline._nodes()) is None
    timeline.set_progress(summary(1, 1.0, endgame=True), 1)
    assert timeline._current_progress_line(timeline._nodes()) is None
    timeline.set_progress(None, None)
    assert timeline._current_progress_line(timeline._nodes()) is None


def test_progress_hero_and_cards_crossfade_without_covering_the_timeline():
    app = _app()
    window = MainWindow()
    window.resize(1665, 937)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    snapshot = QPixmap(320, 180)
    snapshot.fill(Qt.GlobalColor.black)
    window._career_crossfade_snapshot = lambda *_args: snapshot
    hero_geometry = window.career_hero.geometry()
    inspector_geometry = window.career_inspector_stack.geometry()
    previous_page = window.career_inspector_stack.currentIndex()

    window._on_career_timeline_selected(7)
    hero_overlay = window._career_hero_transition
    inspector_overlay = window._career_inspector_transition
    assert hero_overlay is not None
    assert inspector_overlay is not None
    assert hero_overlay.objectName() == "careerHeroTransitionOverlay"
    assert inspector_overlay.objectName() == "careerInspectorTransitionOverlay"
    assert hero_overlay.parentWidget() is window.career_hero
    assert inspector_overlay.parentWidget() is window.career_inspector_stack
    assert window.career_inspector_stack.currentIndex() != previous_page
    assert window.career_hero.geometry() == hero_geometry
    assert window.career_inspector_stack.geometry() == inspector_geometry
    for overlay in (hero_overlay, inspector_overlay):
        assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert overlay._fade.state() == QAbstractAnimation.Running

    deadline = time.monotonic() + 2.0
    while (
        window._career_hero_transition is not None
        or window._career_inspector_transition is not None
    ):
        QTest.qWait(10)
        if (
            window._career_hero_transition is None
            and window._career_inspector_transition is None
        ):
            break
        assert time.monotonic() < deadline

    assert window._career_hero_transition is None
    assert window._career_inspector_transition is None
    window.close()
    app.processEvents()


def test_progress_to_change_rival_crossfades_the_work_area():
    app = _app()
    window = MainWindow()
    window.resize(1665, 937)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    snapshot = QPixmap(320, 180)
    snapshot.fill(Qt.GlobalColor.black)
    window._career_crossfade_snapshot = lambda *_args: snapshot
    previous_geometry = window.career_view_stack.geometry()

    window.career_view_switch.setCurrentIndex(1)
    overlay = window._career_view_transition
    assert window.career_view_stack.currentIndex() == 0
    assert overlay is not None
    assert overlay.objectName() == "careerViewTransitionOverlay"
    assert overlay.parentWidget() is window.career_view_stack
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert window.career_view_stack.geometry() == previous_geometry
    QTest.qWait(45)
    assert 0.0 < overlay._opacity.opacity() < 1.0
    QTest.qWait(130)
    app.processEvents()
    assert window._career_view_transition is None
    window.close()
    app.processEvents()


def test_apply_rival_change_crossfades_the_refreshed_hero(tmp_path, monkeypatch):
    app = _app()
    window = MainWindow()
    window.resize(1665, 937)
    donor_path = tmp_path / "stage_07.bin"
    donor_path.write_bytes(b"test donor")
    data = _synthetic_career(8)
    plan = SimpleNamespace(
        refusal_reason=None,
        warnings=(),
        bounty_compensation=0,
        donor_bin=7,
        user_total_bounty=0,
        user_live_bounty=0,
        donor_total_bounty=0,
        normalized_sold_bounty=0,
    )

    def apply_transplant(_donor_data, _bounty_mode=career_transplant.BOUNTY_MODE_KEEP):
        data[career_transplant.CURRENT_BIN_OFFSET] = 7

    window.savefile = SimpleNamespace(
        data=data,
        plan_career_transplant=lambda _donor_data: plan,
        apply_career_transplant=apply_transplant,
    )
    window.career_donor_library = (
        SimpleNamespace(
            stage_bin=7,
            variant="chapter_start",
            is_loadable=True,
            save_path=donor_path,
            display_name="Stage 7",
        ),
    )
    window._reload_career_donor_library = lambda **_kwargs: None
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    snapshot = QPixmap(320, 180)
    snapshot.fill(Qt.GlobalColor.black)
    window._career_crossfade_snapshot = lambda *_args: snapshot
    window.refresh_state = window._refresh_career_page
    monkeypatch.setattr(
        career_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: career_module.QMessageBox.Yes,
    )
    monkeypatch.setattr(
        career_module.ToastNotification,
        "show_toast",
        lambda *_args, **_kwargs: None,
    )

    window._on_career_transplant_clicked()
    overlay = window._career_hero_transition
    assert career_transplant.read_current_bin(bytes(data)) == 7
    assert window.career_stage_value.text() == "#7"
    assert overlay is not None
    assert overlay.objectName() == "careerHeroTransitionOverlay"
    assert overlay.parentWidget() is window.career_hero
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    QTest.qWait(45)
    assert 0.0 < overlay._opacity.opacity() < 1.0
    QTest.qWait(130)
    app.processEvents()
    assert window._career_hero_transition is None
    window.close()
    app.processEvents()


def test_fullscreen_career_canvas_is_left_anchored_and_capped():
    app = _app()
    window = MainWindow()
    window.resize(1920, 1080)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    canvas = window.career_canvas
    assert canvas.width() <= 1800
    # Anchored to the nav side: no centering air on the left, leftover width
    # (beyond the ultra-wide cap) goes right.
    assert canvas.geometry().left() == 0
    parent_width = canvas.parentWidget().width()
    if parent_width <= 1800:
        assert canvas.width() == parent_width
    window.close()
    app.processEvents()


def test_career_switches_are_read_only_and_status_stays_with_boss_name():
    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    assert window._selected_career_stage() is None
    window.career_donor_library = tuple(
        SimpleNamespace(
            stage_bin=stage,
            variant=variant,
            is_loadable=True,
            save_path=Path("missing-test-donor"),
            display_name=f"Stage {stage}",
        )
        for variant in ("chapter_start", "boss_ready")
        for stage in (8, 15)
    )
    window._reload_career_donor_library = lambda **_kwargs: None
    data = _synthetic_career(8)
    window.savefile = SimpleNamespace(data=data)
    before = bytes(data)
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    assert window._selected_career_stage() == 8
    assert window.career_variant_ready.text() == "CHALLENGE RIVAL"
    window.career_stage_buttons[15].setChecked(True)
    assert window._selected_career_stage() == 15
    window.career_view_switch.setCurrentIndex(1)
    app.processEvents()
    assert window._selected_career_stage() == 8
    assert window.career_preview_status.minimumHeight() == 96
    assert window.career_preview_status.maximumHeight() == 96
    window.career_preview_status.setText("Short preview")
    window.career_review_panel.layout().activate()
    short_review_height = window.career_review_panel.sizeHint().height()
    window.career_preview_status.setText("Line one\nLine two\nLine three\nLine four")
    window.career_review_panel.layout().activate()
    assert window.career_review_panel.sizeHint().height() == short_review_height
    pair = window.career_transplant_pair
    pair._reflow(True)
    pair.resize(1300, pair.sizeHint().height())
    pair.layout().activate()
    assert pair._wide is True
    assert window.career_target_panel.height() == window.career_review_panel.height()
    pair._reflow(False)
    pair.resize(1000, pair.sizeHint().height())
    pair.layout().activate()
    assert pair._wide is False
    assert (
        window.career_review_panel.geometry().top()
        > window.career_target_panel.geometry().bottom()
    )
    window.career_variant_switch.setCurrentIndex(1)
    app.processEvents()
    assert window.career_stage_grid_host.graphicsEffect() is None
    window.career_variant_switch.setCurrentIndex(0)
    window.career_view_switch.setCurrentIndex(0)
    window.career_hero.resize(1000, 320)
    window.career_hero.layout().activate()
    app.processEvents()

    assert bytes(data) == before
    # The banner runs on one optical rhythm: the distance from the card's top
    # edge to the first ink, between every pair of blocks, and from the last
    # block to the bottom edge are all the same (within pixel rounding).
    hero = window.career_hero

    def _ink_band(widget, *, is_label: bool, sample=None) -> tuple[float, float]:
        top = widget.mapTo(hero, widget.rect().topLeft()).y()
        if not is_label:
            return float(top), float(top + widget.height())
        above, below = career_module._ink_insets(widget, widget.height(), sample=sample)
        return top + above, top + widget.height() - below

    bands = [
        _ink_band(window.career_hero_eyebrow, is_label=True),
        _ink_band(
            window.career_stage_value,
            is_label=True,
            sample=career_module._RANK_INK_SAMPLE,
        ),
        _ink_band(
            window.career_hero_tagline,
            is_label=True,
            sample=career_module._TAGLINE_INK_SAMPLE,
        ),
        _ink_band(window.career_races_metric, is_label=False),
        _ink_band(window.career_view_switch, is_label=False),
    ]
    edges = [0.0] + [band[1] for band in bands]
    starts = [band[0] for band in bands] + [float(hero.height())]
    rhythm = [start - edge for edge, start in zip(edges, starts)]
    assert len(rhythm) == 6
    assert max(rhythm) - min(rhythm) <= 1.0, rhythm
    assert min(rhythm) > 0
    assert window.career_view_switch.width() == 280
    assert window.career_view_switch.height() == 42
    assert window.career_view_rapsheet_btn.font().pixelSize() == 12
    assert window.career_view_rapsheet_btn.font().weight() == QFont.Weight.DemiBold
    assert window.career_hero_status.isHidden()
    assert not hasattr(window, "career_stage_sub")
    assert window.findChild(QLabel, "careerHeroSub") is None
    eyebrow = window.findChild(QLabel, "careerHeroEyebrow")
    assert eyebrow is not None
    assert eyebrow.text() == "BLACKLIST"
    assert window.career_stage_value.font().pixelSize() == 68
    assert window.career_boss_value.font().pixelSize() == 68
    assert window.career_hero_tagline.font().pixelSize() == 15
    assert window.career_hero_tagline.font().weight() == QFont.Weight.DemiBold
    assert not hasattr(window.career_stage_grid_host, "_refresh_transition_overlay")
    inspector = window.career_inspector_pages[window.career_inspector_stack.currentIndex()]
    assert not hasattr(inspector, "title")
    assert not hasattr(inspector, "copy")
    assert not hasattr(inspector, "lifetime")
    assert inspector.findChild(QLabel, "careerInspectorTitle") is None
    assert inspector.findChild(QLabel, "careerInspectorEyebrow") is None
    assert inspector.findChild(QLabel, "careerInspectorStatus") is None
    assert inspector.race_list._title == "RACE SCHEDULE"
    assert inspector.milestone_list._title == "MILESTONES"
    window.close()
    app.processEvents()


def test_change_rival_review_crossfades_without_geometry_or_input_changes():
    app = _app()
    window = MainWindow()
    window.resize(1665, 937)
    window.career_donor_library = tuple(
        SimpleNamespace(
            stage_bin=stage,
            variant="chapter_start",
            is_loadable=True,
            save_path=Path("missing-test-donor"),
            display_name=f"Stage {stage}",
        )
        for stage in (8, 15)
    )
    window._reload_career_donor_library = lambda **_kwargs: None
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    review_geometry = window.career_review_panel.geometry()
    snapshot = QPixmap(320, 180)
    snapshot.fill(Qt.GlobalColor.black)
    window._career_crossfade_snapshot = lambda *_args: snapshot
    window.career_stage_buttons[15].setChecked(True)
    overlay = window._career_review_transition
    assert overlay is not None
    assert overlay.objectName() == "careerReviewTransitionOverlay"
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert window.career_review_panel.geometry() == review_geometry
    QTest.qWait(45)
    assert 0.0 < overlay._opacity.opacity() < 1.0
    QTest.qWait(130)
    app.processEvents()
    assert window._career_review_transition is None
    assert window.career_review_panel.geometry() == review_geometry
    window.close()
    app.processEvents()


def test_career_totals_strip_lives_on_page_and_tracks_summary():
    from PySide6.QtWidgets import QFrame

    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    strip = window.findChild(QFrame, "careerTotalsPlate")
    assert strip is not None
    # The totals belong to Career, not to the shell chrome shared with every
    # other page's actions.
    assert window.page_career.isAncestorOf(strip)
    assert not window.footer_chrome.isAncestorOf(strip)
    assert window.findChild(QFrame, "careerLifetimeStrip") is None
    assert window.career_total_races_value.text() == "—"

    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    app.processEvents()
    summary = window._career_summary_cache
    assert summary is not None
    assert window.career_total_races_value.text() == (
        f"{summary.lifetime_race_wins} / {summary.lifetime_race_total}"
    )
    assert window.career_total_milestones_value.text() == (
        f"{summary.lifetime_milestone_wins} / {summary.lifetime_milestone_total}"
    )
    inspector = window.career_inspector_pages[0]
    assert strip.parentWidget() is not inspector
    window.close()
    app.processEvents()


def test_boss_gold_tokens_keep_gold_hue_on_every_theme():
    from PySide6.QtGui import QColor

    from ui.theme import available_theme_names

    for name in available_theme_names():
        tokens = resolve_theme_tokens(name)
        for key in (
            "BOSS_GOLD",
            "BOSS_GOLD_BRIGHT",
            "BOSS_GOLD_DIM",
            "BOSS_GOLD_BG",
            "BOSS_GOLD_BORDER",
        ):
            assert key in tokens, (name, key)
        hue = QColor(tokens["BOSS_GOLD"]).hue()
        assert 25 <= hue <= 70, (name, tokens["BOSS_GOLD"], hue)

    blueprint = resolve_theme_tokens("Blueprint")
    assert blueprint["BOSS_GOLD"] != blueprint["ACCENT"]
    assert blueprint["BOSS_GOLD"] != blueprint["GOLD"]


def test_rival_bios_are_canon_clean_and_wired_to_the_hero():
    from core import rival_bios

    assert sorted(rival_bios.RIVAL_BIOS) == list(range(1, 16))
    for rank, text in rival_bios.RIVAL_BIOS.items():
        assert text.strip() == text and text
        assert not any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in text), rank
        first = rival_bios.tagline(rank)
        assert first and text.startswith(first)
    assert rival_bios.tagline(5).startswith("Webster")
    assert "Toru" in rival_bios.bio(2)

    app = _app()
    window = MainWindow()
    window.resize(1180, 780)
    assert window.career_hero_tagline.isHidden()

    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    assert not window.career_hero_tagline.isHidden()
    assert window.career_hero_tagline.text() == rival_bios.tagline(8)
    assert window.career_hero_tagline.toolTip() == rival_bios.bio(8)

    window._on_career_timeline_selected(14)
    QTest.qWait(180)
    assert window.career_hero_tagline.text() == rival_bios.tagline(14)
    window.close()
    app.processEvents()


def test_hero_backdrop_has_no_coherent_stripes_and_is_cached():
    from PySide6.QtGui import QImage

    app = _app()
    _CareerHero._backdrop_cache.clear()
    hero = _CareerHero()
    hero.resize(1414, 300)

    def render() -> QImage:
        img = QImage(hero.size(), QImage.Format_RGB32)
        img.fill(0)
        hero.render(img)
        return img

    img = render()

    # The relevant artifact is vertical coherence, not noise: Qt's gradient dither
    # repeats per column and reads as stripes (~0.28 on this metric in the
    # steep mid zone), and a clean quantization leaves step edges. The
    # composed backdrop plus the blue-noise tile keeps the column-mean
    # profile flat; the residual grain is half-level and non-repeating.
    def stripe_coherence(x0: int, x1: int, y0: int = 30, y1: int = 270) -> float:
        half = 15
        cols = [0.0] * (x1 - x0)
        for y in range(y0, y1):
            for i, x in enumerate(range(x0, x1)):
                c = img.pixelColor(x, y)
                cols[i] += 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        cols = [v / (y1 - y0) for v in cols]
        prefix = [0.0]
        for value in cols:
            prefix.append(prefix[-1] + value)
        deviations = []
        for i in range(half, len(cols) - half):
            avg = (prefix[i + half + 1] - prefix[i - half]) / (2 * half + 1)
            deviations.append(abs(cols[i] - avg))
        return sum(deviations) / len(deviations)

    text_zone = stripe_coherence(40, int(1414 * 0.40))
    steep_zone = stripe_coherence(int(1414 * 0.45), int(1414 * 0.75))
    assert text_zone < 0.05, text_zone
    assert steep_zone < 0.15, steep_zone

    assert len(_CareerHero._backdrop_cache) == 1
    first = next(iter(_CareerHero._backdrop_cache.values()))
    render()
    assert next(iter(_CareerHero._backdrop_cache.values())) is first

    # Resize may paint a stretched cached reference before the delayed exact
    # render replaces it.
    hero.resize(1094, 300)
    render()
    assert not any(key[0] == 1094 for key in _CareerHero._backdrop_cache)
    QTest.qWait(250)
    app.processEvents()
    assert any(key[0] == 1094 for key in _CareerHero._backdrop_cache)


def test_hero_blocks_hold_one_position_across_all_rivals():
    # At application widths every canonical tagline is one line. A fixed ink
    # sample prevents glyph shapes from changing the vertical rhythm.
    app = _app()
    window = MainWindow()
    window.resize(1600, 900)
    window.savefile = SimpleNamespace(data=_synthetic_career(8))
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()
    window.career_hero.layout().activate()
    app.processEvents()

    summary = career_progress.build_career_progress(bytes(_synthetic_career(8)))
    hero = window.career_hero
    col = window.career_hero_copy
    positions = set()
    for stage in range(15, 0, -1):
        window._update_career_hero(summary, stage)
        # Re-run the rhythm math directly: offscreen, a text change alone is
        # not guaranteed to schedule the relayout a real window would get.
        col.setGeometry(col.geometry())
        positions.add((
            window.career_races_metric.mapTo(
                hero, window.career_races_metric.rect().topLeft()
            ).y(),
            window.career_view_switch.mapTo(
                hero, window.career_view_switch.rect().topLeft()
            ).y(),
            window.career_hero_tagline.mapTo(
                hero, window.career_hero_tagline.rect().topLeft()
            ).y(),
        ))
    assert len(positions) == 1, positions
    window.close()
    app.processEvents()


def test_longest_tagline_stays_one_line_and_holds_the_banner_still():
    """#2 Bull's sentence is the longest canon tagline (653px).

    Regression: with word wrap it took a second line as soon as the banner was
    narrower than that, and the plaques and the PROGRESS / CHANGE RIVAL switch
    below it dropped by a line.  It now elides on a word boundary instead, and
    the full sentence stays available via full_text() and the tooltip.
    """

    from core import rival_bios

    app = _app()
    window = MainWindow()
    window.resize(1400, 812)
    window.show()
    # A shown window repaints its header on resize, which reads savefile.path.
    window.savefile = SimpleNamespace(data=_synthetic_career(8), path="synthetic.sav")
    window._refresh_career_page()
    window._select_page("Career")
    app.processEvents()

    summary = career_progress.build_career_progress(bytes(_synthetic_career(8)))
    window._update_career_hero(summary, 2)
    app.processEvents()

    tagline = window.career_hero_tagline
    line_height = tagline.fontMetrics().height()
    hero = window.career_hero
    positions = set()
    painted = {}
    for width in (1400, 1182, 1050, 990):
        window.resize(width, 812)
        QTest.qWait(30)
        app.processEvents()
        assert tagline.height() <= line_height, width
        assert tagline.full_text() == rival_bios.tagline(2)
        painted[width] = tagline.text()
        positions.add((
            window.career_races_metric.mapTo(
                hero, window.career_races_metric.rect().topLeft()
            ).y(),
            window.career_view_switch.mapTo(
                hero, window.career_view_switch.rect().topLeft()
            ).y(),
        ))

    assert len(positions) == 1, positions
    assert painted[1400] == rival_bios.tagline(2)
    narrow = painted[990]
    assert narrow != rival_bios.tagline(2), "the narrow case must actually elide"
    assert narrow.endswith("…") and not narrow.endswith(" …")
    assert rival_bios.tagline(2).startswith(narrow[:-1])
    window.close()
    app.processEvents()


def _float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def test_race_rows_use_canon_track_names_types_and_boss_kind():
    done = career_progress.RaceRecord(
        index=0,
        race_hash=1,
        event_id="5.1.1",
        flags=career_progress.RACE_DONE_MASK,
        high_score=_float_bits(87.5),
        top_speed=142.4,
        average_speed=120.0,
    )
    row = _race_row(done, boss=False)
    assert row.state == "done"
    assert row.kind == "race"
    assert row.title == "Ironhorse"
    assert row.detail == "WON · 1:27.50"
    assert "best 1:27.50" in row.tooltip
    assert row.tag == ""
    assert row.icon_path is not None and row.icon_path.name == "circuit.png"
    assert "Circuit · 5.1.1" in row.tooltip

    trap_won = career_progress.RaceRecord(
        index=9,
        race_hash=9,
        event_id="5.5.1",
        flags=career_progress.RACE_DONE_MASK,
        high_score=_float_bits(1011.4),
        top_speed=0.0,
        average_speed=0.0,
    )
    row = _race_row(trap_won, boss=False)
    assert row.detail == "WON · SCORE 1,011"

    drag_won = career_progress.RaceRecord(
        index=10,
        race_hash=10,
        event_id="1.7.3",
        flags=career_progress.RACE_DONE_MASK,
        high_score=_float_bits(19.51),
        top_speed=0.0,
        average_speed=0.0,
    )
    row = _race_row(drag_won, boss=False)
    assert row.detail == "WON · 19.51"

    reversed_open = career_progress.RaceRecord(
        index=1,
        race_hash=2,
        event_id="5.5.2.r",
        flags=career_progress.RACE_FLAG_UNLOCKED_CAREER,
        high_score=0,
        top_speed=0.0,
        average_speed=0.0,
    )
    row = _race_row(reversed_open, boss=False)
    assert row.state == "open"
    assert row.title == "Green & Fairmont"
    assert row.tag == "REVERSED"
    assert row.detail == "AVAILABLE"
    assert row.icon_path is not None and row.icon_path.name == "speedtrap.png"

    # kUnlocked_Online alone (engine ScoreFlags 0x10) says nothing about
    # career availability and must not produce an AVAILABLE row.
    online_only = career_progress.RaceRecord(
        index=1,
        race_hash=2,
        event_id="5.5.2.r",
        flags=0x10,
        high_score=0,
        top_speed=0.0,
        average_speed=0.0,
    )
    assert _race_row(online_only, boss=False).state == "locked"

    boss_locked = career_progress.RaceRecord(
        index=2,
        race_hash=3,
        event_id="5.2.2",
        flags=0,
        high_score=0,
        top_speed=0.0,
        average_speed=0.0,
        is_boss_race=True,
    )
    boss_row = _race_row(boss_locked, boss=True)
    assert boss_row.state == "locked"
    assert boss_row.kind == "boss"
    assert boss_row.detail == "LOCKED"
    assert boss_row.title == "Beach & Chancellor"
    assert boss_row.icon_path is not None
    assert boss_row.icon_path.name == "sprint.png"
    assert "boss race" in boss_row.tooltip

    final_pursuit = career_progress.RaceRecord(
        index=3,
        race_hash=4,
        event_id="1.8.1",
        flags=0,
        high_score=0,
        top_speed=0.0,
        average_speed=0.0,
    )
    row = _race_row(final_pursuit, boss=True)
    assert row.title == "Final Pursuit"
    assert row.icon_path is not None and row.icon_path.name == "heat.png"
    assert "Pursuit · 1.8.1" in row.tooltip

    unnamed = career_progress.RaceRecord(
        index=4,
        race_hash=5,
        event_id="16.1.0",
        flags=0,
        high_score=0,
        top_speed=0.0,
        average_speed=0.0,
    )
    row = _race_row(unnamed, boss=False)
    assert row.title == "Event 16.1.0"

    row_list = _ProgressRowList("RACE SCHEDULE")
    row_list.set_items("subtitle", (_race_row(done, boss=False),), (boss_row,))
    assert row_list._boss_rows[0].kind == "boss"
    tall = row_list._content_height()
    row_list.set_items("subtitle", (), ())
    assert row_list._content_height() < tall


def test_rival_challenge_series_is_canon_ordered_with_synthetic_warrent():
    from core import rival_challenge
    from ui.pages.career_mixin import _boss_series_rows, _untracked_boss_row

    assert rival_challenge.BOSS_SERIES[1] == (
        "1.5.2", "1.7.3", "4.2.1", "1.1.2", "1.2.3", "1.8.1"
    )
    assert rival_challenge.ROUTE_REMAP == {"8.3.2": "13.3.1.r"}
    for stage in range(1, 16):
        assert rival_challenge.BOSS_SERIES[stage]
        assert rival_challenge.WORLD_ORDER[stage]

    def record(event_id, flags=career_progress.RACE_FLAG_UNLOCKED_CAREER):
        return career_progress.RaceRecord(
            index=0, race_hash=1, event_id=event_id, flags=flags,
            high_score=0, top_speed=0.0, average_speed=0.0, is_boss_race=True,
        )

    shuffled = [record(e) for e in ("1.2.3", "1.8.1", "1.1.2", "1.7.3", "4.2.1")]
    rows = _boss_series_rows(1, shuffled)
    assert [row.title for row in rows] == [
        "Warrent", "Terrace & Riverside", "Forest Green",
        "Clubhouse", "Clubhouse & Lennox", "Final Pursuit",
    ]
    assert [row.icon_path.name for row in rows if row.icon_path is not None] == [
        "speedtrap.png", "drag.png", "sprint.png",
        "circuit.png", "sprint.png", "heat.png",
    ]
    assert rows[0].detail == "AVAILABLE"
    assert "no record" in rows[0].tooltip
    assert _boss_series_rows(1, ()) == []

    def sibling(flags):
        return career_progress.RaceRecord(
            index=0, race_hash=1, event_id="1.1.2", flags=flags,
            high_score=0, top_speed=0.0, average_speed=0.0,
        )

    row = _untracked_boss_row("1.5.2", (sibling(career_progress.RACE_DONE_MASK),))
    assert row.title == "Warrent"
    assert row.state == "done"
    assert row.detail == "SERIES COMPLETE"
    row = _untracked_boss_row("1.5.2", (sibling(0x00),))
    assert row.state == "locked"


def test_remapped_slot_displays_the_driven_route():
    record = career_progress.RaceRecord(
        index=0, race_hash=1, event_id="8.3.2",
        flags=career_progress.RACE_FLAG_UNLOCKED_CAREER,
        high_score=0, top_speed=0.0, average_speed=0.0,
    )
    row = _race_row(record, boss=False)
    assert row.title == "Stadium"
    assert row.tag == "REVERSED"
    assert row.icon_path is not None and row.icon_path.name == "lap_knockout.png"
    assert "Lap Knockout · 8.3.2 · route 13.3.1.r" in row.tooltip


def test_race_display_names_cover_every_career_event():
    from core import race_display_names, race_names

    assert len(race_display_names.RACE_DISPLAY_NAMES) == 210
    known_unnamed = {"1.8.1", "16.1.0"}
    for event_id in race_names.RACE_EVENT_IDS.values():
        chapter = int(event_id.split(".", 1)[0])
        if not 1 <= chapter <= 16 or event_id in known_unnamed:
            continue
        assert race_display_names.display_name(event_id), event_id

    assert race_display_names.RACE_TYPE_LABELS[3] == "Lap Knockout"
    assert race_display_names.RACE_TYPE_LABELS[4] == "Tollbooth"
    assert race_display_names.RACE_TYPE_LABELS[5] == "Speedtrap"
    assert race_display_names.RACE_TYPE_LABELS[7] == "Drag"
    assert race_display_names.display_name("5.5.2") == "Fairmont & Clubhouse"
    assert race_display_names.display_name("5.5.2.r") == "Green & Fairmont"
    for icon_name in ("race_circuit", "race_sprint", "race_lap_knockout",
                      "milestone_tollbooth", "trap", "race_drag"):
        path = game_icon_path(icon_name)
        assert path is not None and path.is_file(), icon_name


def test_bonus_markers_are_re_dealt_per_opened_save():
    """The game rolls the bonus trio fresh every run, so the editor rolls it
    per opened save - but never while you are comparing rivals, or the pink
    slip would move under the cursor."""
    from core.blacklist_rewards import BONUS_MARKERS, reward_markers
    from ui.pages.career_mixin import _ChapterInspectorPage

    page = _ChapterInspectorPage()
    seen = set()
    for seed in range(12):
        page.set_reward_seed(seed)
        order = page.reward_offers(5)
        assert order == page.reward_offers(5)  # stable while the seed holds
        assert set(order[:3]) <= BONUS_MARKERS
        assert order[3:] == reward_markers(5)[3:]  # upgrades keep their order
        assert sorted(order) == sorted(reward_markers(5))
        seen.add(order)
    assert len(seen) > 1, "the deal never changed across rolls"
    page.deleteLater()


def test_a_rival_without_offers_survives_the_shuffle():
    from ui.pages.career_mixin import _ChapterInspectorPage

    page = _ChapterInspectorPage()
    page.set_reward_seed(7)
    assert page.reward_offers(1) == ()
    page.deleteLater()


def _chip_rows(count: int, *, boss: int = 0):
    from ui.pages.career_mixin import _InspectorRow

    def row(index: int, kind: str) -> _InspectorRow:
        return _InspectorRow(
            title=f"Event {index}",
            tag="",
            state="done",
            kind=kind,
            icon_path=game_icon_path("race_circuit"),
            detail="WON · 1:00.00",
            fraction=None,
            tooltip=f"Event {index} — completed",
        )

    return (
        tuple(row(i, "race") for i in range(count)),
        tuple(row(100 + i, "boss") for i in range(boss)),
    )


def _career_window_with_chips(app, rows, boss_rows, size=(1182, 812)):
    window = MainWindow()
    window.resize(*size)
    window.show()
    app.processEvents()
    window._select_page("Career")
    app.processEvents()
    page = window.career_inspector_pages[window.career_inspector_stack.currentIndex()]
    card = page.race_list
    card.set_items("8/5 wins · 8 events", rows, boss_rows)
    card.grab()  # chip rects are filled in while the card paints
    app.processEvents()
    return window, card


def _land_animation(overlay):
    """Run the overlay's animation to its end without waiting on the clock."""
    animation = overlay._animation
    animation.setCurrentTime(animation.duration())
    QApplication.instance().processEvents()


def test_clicking_a_chip_opens_the_dossier_it_stands_for():
    """The chip is a preview; the click is the only way to the results behind
    it, so the overlay must carry the same rows the card was given."""
    app = _app()
    rows, boss_rows = _chip_rows(8, boss=2)
    window, card = _career_window_with_chips(app, rows, boss_rows)

    chip_rect, chip_row = card._chip_rects[3]
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, chip_rect.center())
    app.processEvents()

    overlay = window.career_detail_overlay
    assert overlay.isVisible()
    assert overlay._animation.isRunning()
    assert overlay._animation.duration() == overlay._OPEN_MS
    # It grows from the chip that was clicked, not from the card.
    assert overlay._origin.size() == chip_rect.size()
    assert overlay.listing._rows == rows
    assert overlay.listing._boss_rows == boss_rows
    assert chip_row.title in {row.title for row in overlay.listing._rows}
    _land_animation(overlay)
    window.close()


def test_escape_and_a_click_outside_close_the_dossier():
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    overlay = window.career_detail_overlay if hasattr(window, "career_detail_overlay") else None

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)

    # A click on the panel itself is not a click on the way out.
    QTest.mouseClick(
        overlay, Qt.LeftButton, Qt.NoModifier, overlay.scroll.geometry().center()
    )
    app.processEvents()
    assert overlay.isVisible()

    QTest.keyClick(overlay, Qt.Key_Escape)
    assert overlay._closing
    _land_animation(overlay)
    assert not overlay.isVisible()

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    _land_animation(overlay)
    # Not the rect's top-left: a null QPoint means "centre" to QTest, which
    # would land inside the panel and prove the opposite of the point.
    outside = QPoint(6, 6)
    assert not overlay.scroll.geometry().contains(outside)
    QTest.mouseClick(overlay, Qt.LeftButton, Qt.NoModifier, outside)
    assert overlay._closing
    _land_animation(overlay)
    assert not overlay.isVisible()
    window.close()


def test_a_long_chapter_scrolls_inside_the_panel_instead_of_overflowing():
    """Razor's chapter is the tall one; in a short window the dossier has to
    stay inside the page and hand the rest to its own scrollbar."""
    app = _app()
    rows, boss_rows = _chip_rows(24, boss=2)
    window, card = _career_window_with_chips(app, rows, boss_rows, size=(1182, 620))

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)

    assert overlay.rect().contains(overlay.scroll.geometry())
    assert overlay.listing.height() > overlay.scroll.height()
    assert overlay.scroll.verticalScrollBar().maximum() > 0
    window.close()


def test_leaving_the_career_page_closes_the_dossier():
    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)
    assert overlay.isVisible()

    window._select_page("Profile")
    app.processEvents()
    _land_animation(overlay)
    assert not overlay.isVisible()
    window.close()


def test_an_empty_card_has_nothing_to_open():
    app = _app()
    window, card = _career_window_with_chips(app, (), ())

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card.rect().center())
    app.processEvents()
    assert getattr(window, "career_detail_overlay", None) is None
    window.close()


def test_a_pressed_chip_answers_the_click_before_the_panel_moves():
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip_rect = card._chip_rects[2][0]

    QTest.mousePress(card, Qt.LeftButton, Qt.NoModifier, chip_rect.center())
    assert card._pressed_chip == chip_rect
    QTest.mouseRelease(card, Qt.LeftButton, Qt.NoModifier, chip_rect.center())
    assert card._pressed_chip is None

    overlay = window.career_detail_overlay
    _land_animation(overlay)
    window.close()


def test_an_interrupted_opening_costs_only_the_distance_left():
    """Catching the panel a fifth of the way out and waiting the full close
    duration is the tell of an animation that ignores being interrupted."""
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay

    overlay._animation.stop()
    overlay._apply_progress(1.0)
    overlay.close_overlay()
    assert overlay._openness == 1.0
    assert overlay._animation.duration() == overlay._CLOSE_MS
    _land_animation(overlay)

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay._animation.stop()
    overlay._apply_progress(0.2)          # caught while it was still opening
    overlay.close_overlay()
    assert overlay._animation.duration() == max(
        overlay._MIN_MS, round(overlay._CLOSE_MS * overlay._openness)
    )
    assert overlay._animation.duration() < overlay._CLOSE_MS
    _land_animation(overlay)
    window.close()


def test_the_way_home_is_its_own_run_and_never_stands_still():
    """The close used to be the opening's curve replayed backwards, which by
    the book is an ease-in: the panel stood almost still for a quarter of the
    run and then bolted.  That pause was defended once and then named as the
    fault - the return "not smooth".  It is now a run out of rest of its own,
    like the opening, which is what a spring does in both directions.

    Locked as a shape, not as numbers: it must be moving at every quarter, and
    never be nearly home before it is half done.
    """
    app = _app()
    rows, boss_rows = _chip_rows(16, boss=2)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[0][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)

    opened = overlay.scroll.geometry()
    span = opened.height() - overlay._origin.height()
    overlay.close_overlay()
    overlay._animation.stop()

    covered = []
    for step in (0.25, 0.5, 0.75):
        overlay._apply_progress(step)
        covered.append((opened.height() - overlay.scroll.height()) / span)

    assert covered[0] > 0.05, f"it stands still at the start: {covered[0]:.1%}"
    assert covered[0] < 0.6, f"it bolts at the start: {covered[0]:.1%}"
    assert covered[1] < 0.95, f"nearly home at halfway: {covered[1]:.1%}"
    assert covered == sorted(covered), "the panel doubled back"
    assert covered[2] > covered[1], "the last quarter has nothing to show"

    overlay._apply_progress(1.0)
    assert overlay.scroll.geometry().size() == overlay._origin.size()
    window.close()


def test_a_chip_answers_the_cursor_and_the_press_differently():
    app = _app()
    rows, boss_rows = _chip_rows(5, boss=1)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    first, second = card._chip_rects[0][0], card._chip_rects[1][0]

    def move_to(point):
        where = QPointF(point)
        app.sendEvent(card, QMouseEvent(QEvent.MouseMove, where, where,
                                        Qt.NoButton, Qt.NoButton, Qt.NoModifier))

    move_to(first.center())
    assert card._hovered_chip == first
    move_to(second.center())
    assert card._hovered_chip == second

    card.leaveEvent(QEvent(QEvent.Leave))
    assert card._hovered_chip is None
    window.close()


def test_hovering_a_locked_chip_does_not_dress_it_as_available():
    """The cursor may be acknowledged; availability may not be implied."""
    from ui.pages.career_mixin import _ChipPreviewCard, _InspectorRow

    def row(state: str) -> _InspectorRow:
        return _InspectorRow(title="x", tag="", state=state, kind="race",
                             icon_path=None, detail="", fraction=None, tooltip="")

    locked_token, locked_opacity = _ChipPreviewCard._hover_border(row("locked"), False, 0.38)
    assert "ACCENT" not in locked_token and "GOLD" not in locked_token
    assert 0.38 < locked_opacity < 1.0        # brighter, still plainly locked

    open_token, _ = _ChipPreviewCard._hover_border(row("open"), False, 1.0)
    boss_token, _ = _ChipPreviewCard._hover_border(row("done"), True, 1.0)
    assert open_token == "ACCENT_BRIGHT"
    assert boss_token == "BOSS_GOLD_BRIGHT"


def _hover_chip(app, card, point) -> None:
    where = QPointF(point)
    app.sendEvent(card, QMouseEvent(QEvent.MouseMove, where, where,
                                    Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def test_a_chip_rises_over_time_rather_than_snapping():
    """Two pixels are still a movement, and a movement has a middle."""
    app = _app()
    rows, boss_rows = _chip_rows(5, boss=1)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[0][0]

    _hover_chip(app, card, chip.center())
    run = card._hover_run
    assert run.state() == QAbstractAnimation.Running
    assert card._hover_level.get(chip, 0.0) == 0.0     # nothing has moved yet
    assert run.duration() <= 200, "a hover is met too often to run this long"

    run.setCurrentTime(run.duration() // 2)
    midway = card._hover_level[chip]
    assert 0.0 < midway < 1.0, "the chip jumped instead of travelling"
    assert midway > 0.5, "an ease-in start would leave the cursor unanswered"

    run.setCurrentTime(run.duration())
    assert card._hover_level[chip] == 1.0
    window.close()


def test_leaving_a_chip_is_quicker_than_arriving_at_it():
    """Feedback that outlives the cursor reads as lag."""
    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[0][0]

    _hover_chip(app, card, chip.center())
    arriving = card._hover_run.duration()
    card._hover_run.setCurrentTime(arriving)

    card.leaveEvent(QEvent(QEvent.Leave))
    leaving = card._hover_run.duration()
    assert 0 < leaving < arriving
    card._hover_run.setCurrentTime(leaving)
    assert card._hover_level.get(chip, 0.0) == 0.0
    window.close()


def test_a_cursor_crossing_the_row_never_drops_a_chip_first():
    """The chip being left carries on from where it stands, and the two share
    one clock: a crossing is a single movement, not one chip finishing before
    the next may start."""
    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    first, second = card._chip_rects[0][0], card._chip_rects[1][0]

    _hover_chip(app, card, first.center())
    card._hover_run.setCurrentTime(card._hover_run.duration() // 4)
    caught = card._hover_level[first]
    assert 0.0 < caught < 1.0

    _hover_chip(app, card, second.center())
    assert card._hover_level[first] == pytest.approx(caught), "it jumped first"

    card._hover_run.setCurrentTime(card._hover_run.duration())
    assert card._hover_level.get(first, 0.0) == 0.0
    assert card._hover_level[second] == 1.0
    window.close()


def test_a_chip_caught_on_its_way_up_comes_back_sooner_than_a_risen_one():
    """Runs are priced by the distance LEFT, so a hover barely begun is not
    made to play out a full exit before the chip is back down."""
    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[0][0]
    run = card._hover_run

    _hover_chip(app, card, chip.center())
    run.setCurrentTime(run.duration())              # all the way up
    card.leaveEvent(QEvent(QEvent.Leave))
    risen = run.duration()
    run.setCurrentTime(risen)                       # and all the way back

    _hover_chip(app, card, chip.center())
    run.setCurrentTime(run.duration() // 3)         # caught on the way up
    card.leaveEvent(QEvent(QEvent.Leave))
    assert card._HOVER_MIN_MS <= run.duration() < risen
    window.close()


def test_the_lift_does_not_rebuild_the_glyph_on_every_frame():
    """The pixmap is cached by size, so the size has to come from the chip and
    not from the shape that is moving - otherwise two pixels of travel cost a
    re-tint of every glyph sixty times a second."""
    from ui.pages.career_mixin import _ChipPreviewCard

    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[0][0]
    card.grab()
    cached = len(_ChipPreviewCard._pixmap_cache)

    _hover_chip(app, card, chip.center())
    run = card._hover_run
    for step in range(1, 6):
        run.setCurrentTime(run.duration() * step // 5)
        card.grab()
    assert len(_ChipPreviewCard._pixmap_cache) == cached
    window.close()



def _press(app, card, point, release=False):
    where = QPointF(point)
    kind = QEvent.MouseButtonRelease if release else QEvent.MouseButtonPress
    app.sendEvent(card, QMouseEvent(kind, where, where, Qt.LeftButton,
                                    Qt.LeftButton, Qt.NoModifier))


def test_a_press_that_misses_the_chips_is_answered_by_the_card():
    """Missing a chip still opens the dossier, so the press cannot go
    unanswered - the card's own edge lights while the button is down."""
    app = _app()
    rows, boss_rows = _chip_rows(5, boss=1)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    header = QPoint(card.width() // 2, 6)      # above the chips, inside the card
    assert card._chip_at(header) is None
    resting = card.grab().toImage()

    _press(app, card, header)
    assert card._card_mark == card._EDGE_HELD, "a press must be answered at once"
    assert card.grab().toImage() != resting, "the press was never drawn"

    opened = []
    card.activated.connect(opened.append)
    _press(app, card, header, release=True)
    assert opened == [card.rect()], "the panel must grow from the whole card"
    # NOT cut at the handover: the panel grows out of this very outline, and a
    # quick click would otherwise be a blink.
    assert card._card_mark == card._EDGE_HELD
    assert card.grab().toImage() != resting

    card.release_card_mark()
    run = card._mark_run
    assert 0 < run.duration() <= card._MARK_OUT_MS
    run.setCurrentTime(run.duration() // 2)
    assert 0.0 < card._card_mark < 1.0, "the edge was cut instead of fading"
    run.setCurrentTime(run.duration())
    assert card._card_mark == 0.0
    assert card.grab().toImage() == resting
    window.close()


def test_the_card_holds_its_edge_until_the_dossier_is_home():
    """The outline hands the panel over on the way out as on the way in: it is
    released only once the panel has closed back into it."""
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, QPoint(card.width() // 2, 6))
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)
    assert card._card_mark == card._EDGE_HELD, "the outline let go while its dossier stood open"

    window.close_career_detail()
    _land_animation(overlay)
    assert card._mark_run.state() == QAbstractAnimation.Running
    card._mark_run.setCurrentTime(card._mark_run.duration())
    assert card._card_mark == 0.0
    window.close()


def test_a_press_that_wanders_onto_a_chip_has_nothing_to_hand_over():
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[2][0]

    _press(app, card, QPoint(card.width() // 2, 6))
    assert card._card_mark == card._EDGE_HELD
    opened = []
    card.activated.connect(opened.append)
    _press(app, card, chip.center(), release=True)

    assert opened == [chip], "the panel must grow from the chip let go over"
    assert card._mark_run.state() == QAbstractAnimation.Running
    card._mark_run.setCurrentTime(card._mark_run.duration())
    assert card._card_mark == 0.0
    window.close()


def test_a_card_with_nothing_behind_it_does_not_promise_a_click():
    app = _app()
    rows, boss_rows = _chip_rows(5)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    assert card.cursor().shape() == Qt.PointingHandCursor

    card.set_items("No race table loaded", ())
    assert card.cursor().shape() == Qt.ArrowCursor
    _press(app, card, QPoint(card.width() // 2, 6))
    assert not card._pressed_card, "an empty card answered a press it cannot serve"
    window.close()


def test_the_cards_edge_does_not_blink_as_the_cursor_meets_a_chip():
    """The edge answers the CARD, so it must not go out over a chip - it would
    blink all the way along the row."""
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip = card._chip_rects[2][0]
    run = card._mark_run

    _hover_chip(app, card, QPoint(card.width() // 2, 6))   # on the card, off the chips
    assert run.state() == QAbstractAnimation.Running
    run.setCurrentTime(run.duration())
    assert card._card_mark == pytest.approx(card._EDGE_HOVER)

    _hover_chip(app, card, chip.center())                  # and onto a chip
    assert card._card_mark == pytest.approx(card._EDGE_HOVER), "the edge blinked"
    assert run.state() != QAbstractAnimation.Running

    card.leaveEvent(QEvent(QEvent.Leave))
    assert run.state() == QAbstractAnimation.Running
    run.setCurrentTime(run.duration())
    assert card._card_mark == 0.0
    window.close()


def _career_window_with_offers(app, stage=9, size=(1182, 812)):
    from core.blacklist_rewards import CARDS_TAKEN

    window = MainWindow()
    window.resize(*size)
    window.show()
    app.processEvents()
    window._select_page("Career")
    app.processEvents()
    page = window.career_inspector_pages[window.career_inspector_stack.currentIndex()]
    card = page.reward_list
    offers = page.reward_offers(stage)
    card.set_offers(f"take {CARDS_TAKEN} of {len(offers)}", offers)
    card.grab()      # cells are filled in while the card paints
    app.processEvents()
    return window, card, offers


def test_the_rewards_card_opens_what_it_can_only_hint_at():
    """The card can show six tokens and nothing more; the sentence under each
    one is the whole reason to open the panel."""
    app = _app()
    window, card, offers = _career_window_with_offers(app)
    cell = card._cells[2][0]

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, cell.center())
    app.processEvents()
    overlay = window.career_detail_overlay
    _land_animation(overlay)

    rows = overlay.listing._rows
    assert len(rows) == len(offers)
    assert overlay.listing._title == "REWARDS"
    assert all(row.note for row in rows), "an offer with nothing said about it"
    assert all(row.state == "open" for row in rows), "offers are not claims"
    # Taller than a plain row apiece: the sentence needs its own line.
    assert overlay.listing._content_height() > len(rows) * 30
    window.close()


def test_the_panel_grows_from_the_token_that_was_pressed():
    """From the diamond, not from the column of air it stands in: the cell is
    three times wider than the token, and a panel unfolding out of it reads as
    a bar snapping open - and carried the token's glyph at the cell's scale,
    half again too big at the first frame."""
    app = _app()
    window, card, _offers = _career_window_with_offers(app)
    opened = []
    card.activated.connect(opened.append)

    cell = card._cells[4][0]
    token = card._token_rect(cell)
    assert token.width() == token.height() < cell.width()
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, cell.center())
    assert opened == [token]

    face = card.face_for(token)
    assert face is not None and face.icon_px == card._icon_size()

    # Between the tokens there is only the card, so the card is the origin.
    card.activated.disconnect()
    caught = []
    card.activated.connect(caught.append)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, QPoint(card.width() // 2, 6))
    assert caught == [card.rect()]
    window.close()


def test_a_rewards_card_with_no_offers_promises_nothing():
    app = _app()
    window, card, _offers = _career_window_with_offers(app)
    assert card.cursor().shape() == Qt.PointingHandCursor

    card.set_offers("", (), "No career data loaded")
    assert card.cursor().shape() == Qt.ArrowCursor
    opened = []
    card.activated.connect(opened.append)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, QPoint(card.width() // 2, 20))
    assert opened == []
    assert card._card_mark == 0.0
    window.close()


def _average_colour(image, rect):
    total = [0, 0, 0]
    step = max(1, rect.width() // 12)
    seen = 0
    for x in range(rect.left() + 4, rect.right() - 4, step):
        for y in range(rect.top() + 4, rect.bottom() - 4, step):
            pixel = image.pixelColor(x, y)
            total[0] += pixel.red()
            total[1] += pixel.green()
            total[2] += pixel.blue()
            seen += 1
    return [channel / max(1, seen) for channel in total]


def test_the_panel_starts_as_the_chip_it_grew_from():
    """Nothing appears from nothing.  At the first frame the panel is not an
    empty sheet standing where a chip was - it IS the chip: its fill, its
    border, its glyph, which it then lets go of as it grows."""
    app = _app()
    rows, boss_rows = _chip_rows(8, boss=2)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    chip_rect, chip_row = card._chip_rects[3]

    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, chip_rect.center())
    app.processEvents()
    overlay = window.career_detail_overlay
    face = overlay._face
    assert face is not None, "the panel was given nothing to start as"
    assert (face.fill, face.border) == card._chip_colours(chip_row)[:2]
    assert face.icon_path == chip_row.icon_path

    overlay._apply_progress(0.0)
    assert overlay._face_weight() == 1.0
    worn = _average_colour(overlay.grab().toImage(), overlay.scroll.geometry())

    overlay._apply_progress(1.0)
    assert overlay._face_weight() == 0.0
    landed = overlay.grab().toImage()
    own = _average_colour(landed, overlay.scroll.geometry())
    chip = _average_colour(card.grab().toImage(), chip_rect)

    def distance(a, b):
        return sum(abs(x - y) for x, y in zip(a, b))

    assert distance(worn, chip) < distance(worn, own), (
        f"the first frame looks like the panel, not the chip: {worn} {chip} {own}"
    )
    window.close()


def test_a_press_on_the_card_itself_lends_no_face():
    """The card and the panel are the same surface already; there is nothing
    to borrow, and pretending otherwise would tint the panel for no reason."""
    app = _app()
    rows, boss_rows = _chip_rows(6)
    window, card = _career_window_with_chips(app, rows, boss_rows)

    assert card.face_for(card.rect()) is None
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, QPoint(card.width() // 2, 6))
    app.processEvents()
    overlay = window.career_detail_overlay
    assert overlay._face is None
    overlay._apply_progress(0.0)
    assert overlay._face_weight() == 0.0
    window.close()


def test_the_glyph_dissolves_across_the_list_rather_than_fighting_it():
    """The two overlap on purpose - letting the glyph go before the list
    starts leaves a stretch with nothing in the panel at all.  What must hold
    is that it is a dissolve: by the time the list is half lit the glyph is a
    whisper, and it is gone before the panel is.
    """
    from ui.pages.career_mixin import _DetailOverlay

    starts, ends = _DetailOverlay._CONTENT_IN
    half_lit = starts + (ends - starts) / 2
    hold, out = _DetailOverlay._GLYPH_HOLD, _DetailOverlay._GLYPH_OUT
    glyph_then = max(0.0, 1.0 - (half_lit - hold) / (out - hold))

    assert hold >= starts, "the glyph starts leaving before it was ever fully seen"
    assert glyph_then <= 0.35, f"still {glyph_then:.2f} of glyph over a half-lit list"
    assert out < 1.0, "the glyph outlives the opening"

    still_worn = max(0.0, 1.0 - starts / _DetailOverlay._FACE_OUT)
    assert still_worn <= 0.15, f"the panel is still wearing the chip: {still_worn:.2f}"


def test_a_token_answers_for_its_own_square_only():
    """The cells tile the whole row, so testing them made a token turn while
    the cursor was plainly beside it - and swallowed presses meant for the
    card underneath."""
    app = _app()
    window, card, _offers = _career_window_with_offers(app)
    cell = card._cells[1][0]
    token = card._token_rect(cell)
    beside = QPoint((cell.left() + token.left()) // 2, cell.center().y())
    assert cell.contains(beside) and not token.contains(beside)

    assert card._cell_at(token.center()) == 1
    assert card._cell_at(beside) is None

    opened = []
    card.activated.connect(opened.append)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, beside)
    assert opened == [card.rect()], "a press beside a token opened the token"
    window.close()


def test_the_list_arrives_with_a_hair_of_scale_and_lands_crisp():
    """A plain fade reads as a layer switched on.  The last few per cent of
    scale under it read as the thing settling into place - but it must land at
    exactly 1, or the text stays softened by a transform that never ended."""
    app = _app()
    rows, boss_rows = _chip_rows(10, boss=2)
    window, card = _career_window_with_chips(app, rows, boss_rows)
    QTest.mouseClick(card, Qt.LeftButton, Qt.NoModifier, card._chip_rects[2][0].center())
    app.processEvents()
    overlay = window.career_detail_overlay
    overlay._animation.stop()

    seen = []
    for step in (0.45, 0.6, 0.75, 0.9, 1.0):
        overlay._apply_progress(step)
        seen.append((overlay._fade.opacity(), overlay._fade._scale))

    opacities = [shown for shown, _scale in seen]
    scales = [scale for _shown, scale in seen]
    assert opacities == sorted(opacities) and scales == sorted(scales)
    assert scales[0] == pytest.approx(overlay._CONTENT_RISE, abs=0.01)
    assert scales[-1] == 1.0, "the list is left standing under a transform"
    assert 0.9 < overlay._CONTENT_RISE < 1.0, "further down and the text grows"
    window.close()
