from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
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
        assert metric.size() == QSize(204, 72)
        assert metric.findChild(QWidget, "careerHeroMetricProgress") is None

    captions = [
        metric.findChild(QLabel, "careerHeroMetricLabel").text()
        for metric in metrics
    ]
    assert captions == ["RACE WINS", "MILESTONES", "BOUNTY"]
    assert window.career_view_transplant_btn.text() == "CHANGE RIVAL"

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
    for width, expected_height in ((790, 320), (1180, 320), (1640, 340)):
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
    QTest.qWait(45)
    assert 0.0 < hero_overlay._opacity.opacity() < 1.0
    assert 0.0 < inspector_overlay._opacity.opacity() < 1.0
    QTest.qWait(130)
    app.processEvents()
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
    )

    def apply_transplant(_donor_data):
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
    metric_gap = (
        window.career_view_switch.geometry().top()
        - window.career_races_metric.geometry().bottom()
        - 1
    )
    copy_gap = (
        window.career_races_metric.geometry().top()
        - window.career_hero_tagline.geometry().bottom()
        - 1
    )
    assert metric_gap >= 16
    assert abs(copy_gap - metric_gap) <= 1
    assert window.career_view_switch.width() == 268
    assert window.career_view_switch.height() == 42
    assert window.career_view_rapsheet_btn.font().pixelSize() == 11
    assert window.career_hero_status.isHidden()
    assert not hasattr(window, "career_stage_sub")
    assert window.findChild(QLabel, "careerHeroSub") is None
    eyebrow = window.findChild(QLabel, "careerHeroEyebrow")
    assert eyebrow is not None
    assert eyebrow.text() == "BLACKLIST"
    headline_gap = window.career_stage_value.geometry().top() - eyebrow.geometry().bottom() - 1
    assert 0 <= headline_gap <= 8
    assert window.career_stage_value.font().pixelSize() == 54
    assert window.career_boss_value.font().pixelSize() == 48
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
    strip = window.findChild(QFrame, "careerTotalsStrip")
    assert strip is not None
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
    # career availability — the pre-2026-07-16 UI mistook it for AVAILABLE.
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
