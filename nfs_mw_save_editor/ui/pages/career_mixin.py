"""Career page: current progression overview + career stage transplant.

Interaction contract (agreed 2026-07-07, see AGENT_CONTEXT.md):
- Transplant is immediate-with-confirm and writes to the in-memory buffer
  only, mirroring the app's "Apply (memory) -> Save + backup" model. The
  actual disk write stays with the standard Save + backup button.
- The transplant button is disabled while any staged edit is pending, so
  staged want-values can never race the transplanted have-values.
- After a transplant the staged state is reset and the whole UI refreshes
  through the same path used after opening a file.

The page hosts two animated views: the stage-change workflow above and a
read-only Blacklist dossier. Progress is parsed into one immutable summary per
save snapshot, then rendered as a hero, painted 15-node timeline, and selected
chapter inspector. Timeline browsing performs no writes.
"""

from __future__ import annotations

import struct
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBitmap,
    QColor,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core import (
    career_progress,
    career_transplant,
    milestone_names,
    race_display_names,
    rival_bios,
    rival_challenge,
)
from core.career_donor_library import (
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    CareerDonorEntry,
    default_user_career_donor_root,
    load_career_donor_library,
)
from ui.icon_map import game_icon_path, rival_asset_path
from ui.pages.constants import BLACKLIST_BOSS_NAMES
from ui.theme import resolve_theme_tokens
from ui.widgets import (
    AnimatedSegmentedControl,
    AnimatedStackedWidget,
    ThemeTransitionOverlay,
    ToastNotification,
)

_KEEPS_TEXT = "Keeps: money, alias, cars, installed parts, garage stats, Junkman inventory."
_CHANGES_TEXT = (
    "Changes: career stage, milestones, race progress, story SMS, shop unlocks."
)
_BOUNTY_CAVEAT_TEXT = (
    "Note: your cars keep their earned bounty; if the target stage implies "
    "more, the difference is added as sold-cars history."
)

_BOSS_GRID_COLUMNS = 5
_RAP_DOT_SIZE = 17
_CAREER_CROSSFADE_MS = 140
_RAP_BOSS_DOT_SIZE = 17
_RAP_TRAP_DOT_SIZE = 17

# EventID type digit -> packaged game icon (ground truth for the digits:
# the events' internal names in GLOBAL/gameplay.bin, see race_display_names).
_RACE_TYPE_ICONS = {
    1: "race_circuit",
    2: "race_sprint",
    3: "race_lap_knockout",
    4: "milestone_tollbooth",
    5: "trap",
    7: "race_drag",
}


def _norm_event_id(event_id: Optional[str]) -> str:
    if not event_id:
        return ""
    return event_id[:-2] if event_id.endswith(".r") else event_id


def _boss_series_rows(
    stage: int, boss_races: Sequence[career_progress.RaceRecord]
) -> list[_InspectorRow]:
    """Rival Challenge rows in the game's canon screen order.

    Series entries without a save slot (only 1.5.2, Razor's Warrent
    speedtrap) render synthetically; the guard on empty boss_races keeps
    ghost rows out of saves whose race table did not parse."""
    if not boss_races:
        return []
    series = rival_challenge.BOSS_SERIES.get(stage, ())
    tracked = {_norm_event_id(record.event_id): record for record in boss_races}
    rows = []
    used = set()
    for canon_id in series:
        record = tracked.get(_norm_event_id(canon_id))
        if record is not None:
            rows.append(_race_row(record, boss=True))
            used.add(_norm_event_id(canon_id))
        else:
            rows.append(_untracked_boss_row(canon_id, boss_races))
    for record in sorted(boss_races, key=_event_sort_key):
        if _norm_event_id(record.event_id) not in used:
            rows.append(_race_row(record, boss=True))
    return rows


def _untracked_boss_row(
    event_id: str, siblings: Sequence[career_progress.RaceRecord]
) -> _InspectorRow:
    if siblings and all(record.is_completed for record in siblings):
        state, detail = "done", "SERIES COMPLETE"
    elif any(
        record.flags & career_progress.RACE_FLAG_UNLOCKED_CAREER
        for record in siblings
    ):
        state, detail = "open", "AVAILABLE"
    else:
        state, detail = "locked", "LOCKED"
    title = race_display_names.display_name(event_id) or f"Event {event_id}"
    type_label = race_display_names.type_label(event_id) or "Event"
    return _InspectorRow(
        title=title,
        tag="",
        state=state,
        kind="boss",
        icon_path=game_icon_path(_race_type_icon(event_id)),
        detail=detail,
        fraction=None,
        tooltip=(
            f"{title} — rival race\n{type_label} · {event_id} · boss race\n"
            "The save keeps no record for this event — its state follows "
            "the rest of the rival series."
        ),
    )


def _race_type_icon(event_id: Optional[str]) -> str:
    if race_display_names.type_label(event_id) == "Pursuit":
        return "heat"
    if event_id:
        parts = event_id.split(".")
        if len(parts) >= 3:
            try:
                return _RACE_TYPE_ICONS.get(int(parts[1]), "race")
            except ValueError:
                pass
    return "race"


@dataclass(frozen=True)
class HeroPortraitLayout:
    """Per-rival normalized full-bust crop."""

    crop_x: float
    crop_y: float
    crop_width: float
    crop_height: float
    x_offset: float = 0.0


# Coordinates are normalized against each alpha-trimmed generated foreground.
# Every source crop includes the full head, chin, neck and shoulders, then the
# complete crop is fitted inside the Hero rather than enlarged beyond its clip.
HERO_PORTRAIT_LAYOUTS: Mapping[int, HeroPortraitLayout] = MappingProxyType({
    15: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    14: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, 0.00),
    13: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    12: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, -0.01),
    11: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    10: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    9: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    8: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    7: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    6: HeroPortraitLayout(0.00, 0.00, 1.00, 0.95, 0.00),
    5: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    4: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    3: HeroPortraitLayout(0.00, 0.00, 1.00, 0.98, 0.00),
    2: HeroPortraitLayout(0.00, 0.00, 1.00, 0.98, 0.00),
    1: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, 0.00),
})


class _CareerHero(QFrame):
    """Theme-built rival banner with graffiti and portrait art layers."""

    _COMPACT_HEIGHT = 320
    _WIDE_HEIGHT = 340
    _WIDE_BREAKPOINT = 1450
    _COMPACT_STAMP_WIDTH = 175.0
    _WIDE_STAMP_WIDTH = 210.0
    _art_cache: "OrderedDict[int, tuple[QPixmap, QPixmap]]" = OrderedDict()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerHero")
        self.setFixedHeight(self._COMPACT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._stage: Optional[int] = None
        self._graffiti = QPixmap()
        self._portrait = QPixmap()
        self._defeated_stamp = QPixmap()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._WIDE_HEIGHT if width >= self._WIDE_BREAKPOINT else self._COMPACT_HEIGHT

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1100, self.heightForWidth(max(1100, self.width())))

    def set_stage(self, stage: Optional[int]) -> None:
        if stage == self._stage:
            return
        self._stage = stage
        if stage is None:
            self._graffiti = QPixmap()
            self._portrait = QPixmap()
            self.update()
            return
        cached = self._art_cache.get(stage)
        if cached is not None:
            self._art_cache.move_to_end(stage)
            self._graffiti, self._portrait = cached
            self.update()
            return

        graffiti_path = rival_asset_path(stage, "graffiti")
        portrait_path = rival_asset_path(stage, "hero_portrait")
        graffiti = QPixmap(str(graffiti_path)) if graffiti_path is not None else QPixmap()
        portrait = QPixmap(str(portrait_path)) if portrait_path is not None else QPixmap()
        if portrait.isNull():
            portrait = self._fallback_portrait(stage)
        self._graffiti = graffiti
        self._portrait = portrait
        self._art_cache[stage] = (graffiti, portrait)
        while len(self._art_cache) > 3:
            self._art_cache.popitem(last=False)
        self.update()

    def set_defeated_stamp(self, stamp: QPixmap) -> None:
        self._defeated_stamp = QPixmap(stamp)
        self.update()

    @staticmethod
    def _fallback_portrait(stage: int) -> QPixmap:
        source = rival_asset_path(stage, "portrait")
        if source is None:
            return QPixmap()
        reader = QImageReader(str(source))
        reader.setScaledSize(QSize(1024, 1024))
        return QPixmap.fromImage(reader.read())

    def portraitSourceRect(self, stage: int) -> QRectF:  # noqa: N802
        """Normalized bust crop mapped onto the loaded foreground pixmap."""
        if self._portrait.isNull():
            return QRectF()
        layout = HERO_PORTRAIT_LAYOUTS[stage]
        return QRectF(
            self._portrait.width() * layout.crop_x,
            self._portrait.height() * layout.crop_y,
            self._portrait.width() * layout.crop_width,
            self._portrait.height() * layout.crop_height,
        )

    def portraitRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        """Bust target fully contained inside the Hero clip."""
        if self._portrait.isNull() or height <= 0:
            return QRectF()
        layout = HERO_PORTRAIT_LAYOUTS[stage]
        source = self.portraitSourceRect(stage)
        target_height = max(1.0, height - 14.0)
        target_width = target_height * source.width() / source.height()
        return QRectF(
            width - target_width - 7.0 + layout.x_offset * height,
            14.0,
            target_width,
            target_height,
        )

    def bustSafeRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        return self.portraitRect(stage, width, height)

    def defeatedStampRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        if self._defeated_stamp.isNull():
            return QRectF()
        portrait = self.portraitRect(stage, width, height)
        if portrait.isNull():
            return QRectF()
        stamp_width = (
            self._WIDE_STAMP_WIDTH
            if width >= self._WIDE_BREAKPOINT
            else self._COMPACT_STAMP_WIDTH
        )
        stamp_height = stamp_width * (
            self._defeated_stamp.height() / self._defeated_stamp.width()
        )
        return QRectF(
            portrait.center().x() - stamp_width * 0.55,
            portrait.top() + portrait.height() * 0.66,
            stamp_width,
            stamp_height,
        )

    def _paint_theme_background(self, painter: QPainter, tokens: Mapping[str, str]) -> None:
        width = self.width()
        height = self.height()
        base = QLinearGradient(0, 0, width, 0)
        base.setColorAt(0.0, QColor(tokens["BG_PANEL"]))
        base.setColorAt(0.48, QColor(tokens["BG_CARD"]))
        base.setColorAt(1.0, QColor(tokens["ACCENT_SOFT"]))
        painter.fillRect(self.rect(), base)

        glow_color = QColor(tokens["ACCENT_BRIGHT"])
        glow_color.setAlpha(74)
        clear_glow = QColor(glow_color)
        clear_glow.setAlpha(0)
        glow = QRadialGradient(width * 0.83, height * 0.38, width * 0.48)
        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(0.42, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 24))
        glow.setColorAt(1.0, clear_glow)
        painter.fillRect(self.rect(), glow)

        # Restrained dossier grid: enough structure to feel authored, never a
        # competing illustration behind the metrics and rival portrait.
        grid = QColor(tokens["BORDER"])
        grid.setAlpha(42)
        painter.setPen(QPen(grid, 1.0))
        start_x = int(width * 0.43)
        for x in range(start_x, width, 54):
            painter.drawLine(x, 0, x, height)
        for y in range(42, height, 42):
            painter.drawLine(start_x, y, width, y)

        band = QColor(tokens["ACCENT"])
        band.setAlpha(24)
        diagonal = QPainterPath(QPointF(width * 0.56, height))
        diagonal.lineTo(width * 0.72, 0)
        diagonal.lineTo(width * 0.78, 0)
        diagonal.lineTo(width * 0.62, height)
        diagonal.closeSubpath()
        painter.fillPath(diagonal, band)

        left_shade = QLinearGradient(0, 0, width * 0.72, 0)
        opaque = QColor(tokens["BG_PANEL"])
        soft = QColor(tokens["BG_PANEL"])
        clear = QColor(tokens["BG_PANEL"])
        soft.setAlpha(205)
        clear.setAlpha(0)
        left_shade.setColorAt(0.0, opaque)
        left_shade.setColorAt(0.52, soft)
        left_shade.setColorAt(1.0, clear)
        painter.fillRect(self.rect(), left_shade)

    def _graffiti_rect(self) -> QRectF:
        if self._stage is None or self._graffiti.isNull():
            return QRectF()
        portrait = self.portraitRect(self._stage, self.width(), self.height())
        max_width = min(self.width() * 0.36, 360.0)
        max_height = self.height() * 0.60
        scale = min(
            max_width / self._graffiti.width(),
            max_height / self._graffiti.height(),
        )
        target_width = self._graffiti.width() * scale
        target_height = self._graffiti.height() * scale
        # The signature bridges the empty middle and the portrait, but ends
        # underneath the subject so no isolated tail can survive at the edge.
        target_right = portrait.left() + portrait.width() * 0.20
        return QRectF(
            target_right - target_width,
            (self.height() - target_height) * 0.52,
            target_width,
            target_height,
        )

    def _paint_graffiti(self, painter: QPainter) -> None:
        target = self._graffiti_rect()
        if target.isNull():
            return
        painter.setOpacity(0.22)
        painter.drawPixmap(target, self._graffiti, QRectF(self._graffiti.rect()))
        painter.setOpacity(1.0)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(_event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 12.0, 12.0)
        painter.setClipPath(clip)
        self._paint_theme_background(painter, tokens)
        self._paint_graffiti(painter)

        if self._stage is not None and not self._portrait.isNull():
            painter.setOpacity(0.98)
            painter.drawPixmap(self.portraitRect(
                self._stage, self.width(), self.height()
            ), self._portrait, self.portraitSourceRect(self._stage))
            painter.setOpacity(1.0)
            if not self._defeated_stamp.isNull():
                painter.drawPixmap(
                    self.defeatedStampRect(self._stage, self.width(), self.height()),
                    self._defeated_stamp,
                    QRectF(self._defeated_stamp.rect()),
                )

        painter.setClipping(False)
        painter.setPen(QPen(QColor(tokens["BORDER"]), 1.0))
        painter.drawRoundedRect(rect, 12.0, 12.0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        desired_height = self.heightForWidth(event.size().width())
        if self.height() != desired_height:
            self.setFixedHeight(desired_height)
        super().resizeEvent(event)


class _ResponsiveProgressColumns(QWidget):
    """Places milestone/race dossiers side-by-side only when space permits."""

    _WIDE_BREAKPOINT = 1050

    def __init__(self, milestones: QWidget, races: QWidget) -> None:
        super().__init__()
        self.setObjectName("careerProgressColumns")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._milestones = milestones
        self._races = races
        self._wide: Optional[bool] = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self._reflow(False)

    def _reflow(self, wide: bool) -> None:
        if self._wide == wide:
            return
        self._wide = wide
        self._layout.removeWidget(self._milestones)
        self._layout.removeWidget(self._races)
        if wide:
            self._layout.addWidget(self._milestones, 0, 0)
            self._layout.addWidget(self._races, 0, 1)
            self._layout.setColumnStretch(0, 4)
            self._layout.setColumnStretch(1, 7)
        else:
            self._layout.addWidget(self._milestones, 0, 0)
            self._layout.addWidget(self._races, 1, 0)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 0)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._reflow(event.size().width() >= self._WIDE_BREAKPOINT)
        super().resizeEvent(event)


def _stage_title(stage: int) -> str:
    boss = BLACKLIST_BOSS_NAMES.get(stage)
    return f"#{stage}: {boss}" if boss else f"#{stage}"


def _display_name_text(text: str) -> str:
    return text.replace(" — ", ": ")


def _fmt_num(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


def _fmt_compact(value: int) -> str:
    if value >= 1_000_000:
        number = value / 1_000_000
        return f"{number:.2f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        number = value / 1_000
        return f"{number:.1f}".rstrip("0").rstrip(".") + "K"
    return f"{value:,}"


def _milestone_display(type_key: int, value: float) -> str:
    info = milestone_names.type_label_and_unit(type_key)
    if info is None:
        return _fmt_num(value)
    _label, unit = info
    if unit == "money":
        return f"${int(round(value)):,}"
    if unit == "seconds":
        seconds = max(0, int(round(value)))
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{int(round(value)):,}"


def _milestone_icon(type_key: int) -> Optional[Path]:
    name = milestone_names.resolve_type_name(type_key)
    icon_names = {
        "bounty_in_pursuit": "milestone_pursuit_bounty",
        "cops_damaged": "cops_damaged",
        "cost_to_state_in_pursuit": "milestone_cost_to_state",
        "pursuit_evasion_time": "milestone_pursuit_mintime",
        "pursuit_length": "milestone_pursuit_duration",
        "roadblocks_dodged": "milestone_roadblocks",
        "tire_spikes_dodged": "milestone_spikestrips",
        "total_infractions": "milestone_infractions",
    }
    return game_icon_path(icon_names.get(name, "milestone"))


def _event_sort_key(record: career_progress.RaceRecord) -> Tuple[int, int, int]:
    parts = (record.event_id or "").split(".")
    try:
        return (int(parts[1]), int(parts[2]), 1 if record.is_reversed else 0)
    except (IndexError, ValueError):
        return (99, record.index, 0)


class _BlacklistTimeline(QWidget):
    """Single painted Blacklist ladder with read-only stage selection."""

    stageSelected = Signal(int)
    _glyph_cache: "OrderedDict[tuple[str, int], QPixmap]" = OrderedDict()
    _SELECTION_DURATION_MS = 190

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerTimeline")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(82)
        self._summary: Optional[career_progress.CareerProgressSummary] = None
        self._selected_stage: Optional[int] = None
        self._selection_position: Optional[float] = None
        self._selection_animation = QVariantAnimation(self)
        self._selection_animation.setDuration(self._SELECTION_DURATION_MS)
        self._selection_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._selection_animation.valueChanged.connect(self._set_selection_position)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1000, 88)

    def set_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        selected_stage: Optional[int],
    ) -> None:
        self._selection_animation.stop()
        self._summary = summary
        self._selected_stage = selected_stage
        self._selection_position = self._stage_position(selected_stage)
        self.update()

    def set_selected_stage(self, stage: int) -> None:
        if stage != self._selected_stage:
            start = self._selection_position
            if start is None:
                start = self._stage_position(self._selected_stage)
            end = self._stage_position(stage)
            self._selected_stage = stage
            self._selection_animation.stop()
            if self.isVisible() and start is not None and end is not None:
                self._selection_animation.setStartValue(start)
                self._selection_animation.setEndValue(end)
                self._selection_animation.start()
            else:
                self._selection_position = end
                self.update()

    @staticmethod
    def _stage_position(stage: Optional[int]) -> Optional[float]:
        if stage is None or not 1 <= stage <= 15:
            return None
        return float(15 - stage)

    def _set_selection_position(self, value) -> None:
        self._selection_position = float(value)
        self.update()

    @staticmethod
    def _selection_bracket_path(
        center: QPointF, radius: float, arm: float
    ) -> QPainterPath:
        left = center.x() - radius
        right = center.x() + radius
        top = center.y() - radius
        bottom = center.y() + radius
        path = QPainterPath()
        path.moveTo(left + arm, top)
        path.lineTo(left, top)
        path.lineTo(left, top + arm)
        path.moveTo(right - arm, top)
        path.lineTo(right, top)
        path.lineTo(right, top + arm)
        path.moveTo(left, bottom - arm)
        path.lineTo(left, bottom)
        path.lineTo(left + arm, bottom)
        path.moveTo(right, bottom - arm)
        path.lineTo(right, bottom)
        path.lineTo(right - arm, bottom)
        return path

    def _nodes(self) -> list[tuple[int, QPointF]]:
        left = 26.0
        right = max(left, self.width() - 26.0)
        span = max(1.0, right - left)
        return [
            (stage, QPointF(left + index * span / 14.0, 30.0))
            for index, stage in enumerate(range(15, 0, -1))
        ]

    def _state(self, stage: int) -> str:
        if self._summary is None:
            return "locked"
        return self._summary.stage_state(stage)

    def _current_progress_line(
        self, nodes: Sequence[tuple[int, QPointF]]
    ) -> Optional[tuple[QPointF, QPointF]]:
        summary = self._summary
        if summary is None or summary.endgame or summary.current_stage <= 1:
            return None
        fraction = summary.requirement_progress(summary.current_stage)
        if fraction <= 0.0:
            return None
        points = dict(nodes)
        start = points.get(summary.current_stage)
        target = points.get(summary.current_stage - 1)
        if start is None or target is None:
            return None
        end = QPointF(
            start.x() + (target.x() - start.x()) * fraction,
            start.y() + (target.y() - start.y()) * fraction,
        )
        return start, end

    @classmethod
    def _glyph(cls, icon_name: str, size: int) -> QPixmap:
        key = (icon_name, size)
        cached = cls._glyph_cache.get(key)
        if cached is not None:
            cls._glyph_cache.move_to_end(key)
            return cached
        path = game_icon_path(icon_name)
        source = QPixmap(str(path)) if path is not None else QPixmap()
        if source.isNull():
            return QPixmap()
        bounds = QRegion(QBitmap.fromImage(
            source.toImage().createAlphaMask()
        )).boundingRect()
        if not bounds.isEmpty():
            source = source.copy(bounds)
        source = source.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        cls._glyph_cache[key] = source
        while len(cls._glyph_cache) > 8:
            cls._glyph_cache.popitem(last=False)
        return source

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(_event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        nodes = self._nodes()
        if not nodes:
            return

        base_pen = QPen(QColor(tokens["BORDER"]), 2.0)
        painter.setPen(base_pen)
        painter.drawLine(nodes[0][1], nodes[-1][1])
        for (stage, point), (next_stage, next_point) in zip(nodes, nodes[1:]):
            if self._state(stage) == "defeated" and self._state(next_stage) in {
                "defeated", "current", "boss_ready"
            }:
                painter.setPen(QPen(QColor(tokens["ACCENT"]), 3.0))
                painter.drawLine(point, next_point)
        current_progress = self._current_progress_line(nodes)
        if current_progress is not None:
            progress_pen = QPen(QColor(tokens["ACCENT"]), 3.0)
            progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            painter.drawLine(*current_progress)

        wide = self.width() >= 1180
        node_radius = 12.5 if wide else 11.5
        selected_radius = node_radius + 5.5
        bracket_arm = 5.5 if wide else 5.0
        if self._selection_position is not None:
            position = max(0.0, min(14.0, self._selection_position))
            selection_x = nodes[0][1].x() + position * (
                nodes[-1][1].x() - nodes[0][1].x()
            ) / 14.0
            painter.setBrush(Qt.NoBrush)
            selection_pen = QPen(QColor(tokens["ACCENT_BRIGHT"]), 2.0)
            selection_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            selection_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(selection_pen)
            painter.drawPath(self._selection_bracket_path(
                QPointF(selection_x, 30.0), selected_radius, bracket_arm
            ))
        for stage, point in nodes:
            state = self._state(stage)
            selected = stage == self._selected_stage
            if state == "defeated":
                fill = QColor(tokens["ACCENT_BRIGHT"])
                border = QColor(tokens["ACCENT_BRIGHT"])
            elif state == "boss_ready":
                fill = QColor(tokens["ACCENT"])
                border = QColor(tokens["TEXT"])
            elif state == "current":
                fill = QColor(tokens["BG_PANEL"])
                border = QColor(tokens["ACCENT_BRIGHT"])
            else:
                fill = QColor(tokens["BG_DISABLED"])
                border = QColor(tokens["BORDER"])

            painter.setBrush(fill)
            painter.setPen(QPen(border, 2.0 if state in {"current", "boss_ready"} else 1.3))
            painter.drawEllipse(point, node_radius, node_radius)

            glyph_name = "timeline_check" if state == "defeated" else "timeline_arrow"
            if state == "defeated":
                glyph_size = 18 if wide else 17
            else:
                glyph_size = 10 if wide else 9
            glyph = self._glyph(glyph_name, glyph_size)
            if not glyph.isNull():
                painter.drawPixmap(
                    QRectF(
                        point.x() - glyph.width() / 2.0,
                        point.y() - glyph.height() / 2.0,
                        glyph.width(),
                        glyph.height(),
                    ),
                    glyph,
                    QRectF(glyph.rect()),
                )

            font = painter.font()
            font.setFamily("Bahnschrift SemiCondensed")
            font.setBold(selected or state in {"current", "boss_ready"})
            font.setPointSizeF(9.0 if wide else 8.5)
            painter.setFont(font)
            label_color = QColor(tokens["TEXT"])
            if not selected:
                label_color.setAlpha(175)
            painter.setPen(label_color)
            text_rect = QRectF(
                point.x() - 44,
                point.y() + node_radius + 4,
                88,
                32,
            )
            if wide:
                label = f"#{stage}\n{BLACKLIST_BOSS_NAMES.get(stage, '?').upper()}"
            else:
                label = f"#{stage}"
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

    def _stage_at(self, pos: QPoint) -> Optional[int]:
        nearest: tuple[float, Optional[int]] = (22.0, None)
        for stage, point in self._nodes():
            distance = abs(point.x() - pos.x())
            if distance < nearest[0] and abs(point.y() - pos.y()) <= 24:
                nearest = (distance, stage)
        return nearest[1]

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            stage = self._stage_at(event.position().toPoint())
            if stage is not None:
                self.stageSelected.emit(stage)
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        stage = self._stage_at(event.position().toPoint())
        if stage is None:
            self.setToolTip("")
        else:
            state = self._state(stage).replace("_", " ")
            self.setToolTip(f"{_stage_title(stage)} — {state}")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._selected_stage is not None and event.key() in (Qt.Key_Left, Qt.Key_Right):
            delta = 1 if event.key() == Qt.Key_Left else -1
            stage = min(15, max(1, self._selected_stage + delta))
            self.stageSelected.emit(stage)
            return
        super().keyPressEvent(event)


@dataclass(frozen=True)
class _InspectorRow:
    title: str
    tag: str
    state: str
    kind: str
    icon_path: Optional[Path]
    detail: str
    fraction: Optional[float]
    tooltip: str


class _ProgressRowList(QFrame):
    """Painted dossier list: one readable row per event with state and result."""

    _pixmap_cache: "OrderedDict[tuple[str, int], QPixmap]" = OrderedDict()
    _ROWS_TOP = 58
    _ROW_HEIGHT = 30
    _SECTION_GAP = 27
    _BOTTOM_PAD = 14

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("careerInspectorSection")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._title = title
        self._subtitle = ""
        self._rows: Tuple[_InspectorRow, ...] = ()
        self._boss_rows: Tuple[_InspectorRow, ...] = ()
        self._row_rects: list[tuple[QRect, _InspectorRow]] = []

    def _content_height(self) -> int:
        height = self._ROWS_TOP + len(self._rows) * self._ROW_HEIGHT
        if self._boss_rows:
            height += self._SECTION_GAP + len(self._boss_rows) * self._ROW_HEIGHT
        return height + self._BOTTOM_PAD

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(520, self._content_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(340, self._content_height())

    def set_items(
        self,
        subtitle: str,
        rows: Sequence[_InspectorRow],
        boss_rows: Sequence[_InspectorRow] = (),
    ) -> None:
        self._subtitle = subtitle
        self._rows = tuple(rows)
        self._boss_rows = tuple(boss_rows)
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    @classmethod
    def _source_pixmap(cls, path: Optional[Path], size: int) -> QPixmap:
        if path is None:
            return QPixmap()
        key = (str(path), size)
        cached = cls._pixmap_cache.get(key)
        if cached is not None:
            cls._pixmap_cache.move_to_end(key)
            return cached
        source = QPixmap(str(path))
        if source.isNull():
            return QPixmap()
        source = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        original = QPixmap(size, size)
        original.fill(Qt.transparent)
        painter = QPainter(original)
        x = (size - source.width()) // 2
        y = (size - source.height()) // 2
        painter.drawPixmap(x, y, source)
        painter.end()
        cls._pixmap_cache[key] = original
        while len(cls._pixmap_cache) > 128:
            cls._pixmap_cache.popitem(last=False)
        return original

    def _condensed_font(self, painter: QPainter, size: float, *, bold: bool) -> None:
        font = painter.font()
        font.setFamily("Bahnschrift SemiCondensed")
        font.setBold(bold)
        font.setPointSizeF(size)
        painter.setFont(font)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        self._condensed_font(painter, 11.0, bold=True)
        painter.setPen(QColor(tokens["TEXT"]))
        painter.drawText(QRectF(15, 11, self.width() - 30, 20), Qt.AlignLeft, self._title)
        self._condensed_font(painter, 9.5, bold=False)
        painter.setPen(QColor(tokens["MUTED"]))
        painter.drawText(QRectF(15, 32, self.width() - 30, 20), Qt.AlignLeft, self._subtitle)

        self._row_rects = []
        top = self._paint_rows(painter, tokens, self._rows, self._ROWS_TOP)
        if self._boss_rows:
            self._condensed_font(painter, 9.0, bold=True)
            painter.setPen(QColor(tokens["BOSS_GOLD"]))
            painter.drawText(
                QRectF(15, top + 5, self.width() - 30, 16), Qt.AlignLeft, "BOSS"
            )
            self._paint_rows(painter, tokens, self._boss_rows, top + self._SECTION_GAP)

    def _paint_rows(
        self,
        painter: QPainter,
        tokens: Mapping[str, str],
        rows: Sequence[_InspectorRow],
        top: int,
    ) -> int:
        width = self.width()
        for index, row in enumerate(rows):
            rect = QRect(10, top, width - 20, self._ROW_HEIGHT)
            self._row_rects.append((rect, row))
            boss = row.kind == "boss"
            if row.state == "done":
                box_fill = QColor(tokens["BOSS_GOLD" if boss else "ACCENT"])
                box_border = QColor(tokens["BOSS_GOLD_BRIGHT" if boss else "ACCENT_BRIGHT"])
                title_color = QColor(tokens["TEXT"])
                detail_color = QColor(tokens["BOSS_GOLD_BRIGHT" if boss else "ACCENT_BRIGHT"])
                icon_opacity = 1.0
            elif row.state == "open":
                box_fill = QColor(tokens["BG_INPUT"])
                box_border = QColor(tokens["BOSS_GOLD" if boss else "ACCENT"])
                title_color = QColor(tokens["TEXT"])
                detail_color = QColor(tokens["MUTED"])
                icon_opacity = 1.0
            else:
                box_fill = QColor(tokens["BG_INPUT"])
                box_border = QColor(tokens["BOSS_GOLD_DIM" if boss else "BORDER"])
                title_color = QColor(tokens["MUTED_DARK"])
                detail_color = QColor(tokens["MUTED_DARK"])
                icon_opacity = 0.38

            box = QRectF(rect.left() + 5, rect.top() + 4, 22, 22)
            painter.setBrush(box_fill)
            painter.setPen(QPen(box_border, 1.2))
            box_radius = 4.0 if boss else 6.0
            painter.drawRoundedRect(box, box_radius, box_radius)
            icon = self._source_pixmap(row.icon_path, 16)
            if not icon.isNull():
                painter.setOpacity(icon_opacity)
                painter.drawPixmap(int(box.left()) + 3, int(box.top()) + 3, icon)
                painter.setOpacity(1.0)

            self._condensed_font(painter, 10.0, bold=False)
            title_x = rect.left() + 37
            title_advance = painter.fontMetrics().horizontalAdvance(row.title)
            painter.setPen(title_color)
            painter.drawText(
                QRectF(title_x, rect.top(), rect.width() - 37, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                row.title,
            )

            if row.tag:
                self._condensed_font(painter, 7.5, bold=True)
                tag_width = painter.fontMetrics().horizontalAdvance(row.tag) + 10
                tag_rect = QRectF(
                    title_x + title_advance + 8, rect.center().y() - 7.5, tag_width, 15
                )
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(tokens["MUTED_DARK"]), 1.0))
                painter.drawRoundedRect(tag_rect, 4.0, 4.0)
                painter.setPen(QColor(tokens["MUTED"]))
                painter.drawText(tag_rect, Qt.AlignCenter, row.tag)

            self._condensed_font(painter, 9.0, bold=True)
            detail_width = painter.fontMetrics().horizontalAdvance(row.detail)
            painter.setPen(detail_color)
            painter.drawText(
                QRectF(rect.right() - 5 - detail_width, rect.top(), detail_width, rect.height()),
                Qt.AlignRight | Qt.AlignVCenter,
                row.detail,
            )

            if row.fraction is not None and row.state == "open" and rect.width() >= 330:
                bar = QRectF(
                    rect.right() - 5 - detail_width - 10 - 64,
                    rect.center().y() - 2.5,
                    64,
                    5,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(tokens["BG_INPUT"]))
                painter.drawRoundedRect(bar, 2.5, 2.5)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(tokens["BORDER"]), 1.0))
                painter.drawRoundedRect(bar.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)
                filled = max(0.0, min(1.0, row.fraction))
                if filled > 0.0:
                    fill_rect = QRectF(bar)
                    fill_rect.setWidth(max(5.0, bar.width() * filled))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(tokens["ACCENT_BRIGHT"]))
                    painter.drawRoundedRect(fill_rect, 2.5, 2.5)

            if index < len(rows) - 1:
                separator = QColor(tokens["BORDER"])
                separator.setAlpha(120)
                painter.setPen(QPen(separator, 1.0))
                painter.drawLine(
                    rect.left() + 2, rect.bottom(), rect.right() - 2, rect.bottom()
                )
            top += self._ROW_HEIGHT
        return top

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        position = event.position().toPoint()
        for rect, row in self._row_rects:
            if rect.contains(position):
                self.setToolTip(row.tooltip)
                return super().mouseMoveEvent(event)
        self.setToolTip("")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        QToolTip.hideText()
        super().leaveEvent(event)


class _ResponsivePanelPair(QWidget):
    def __init__(
        self,
        first: QWidget,
        second: QWidget,
        *,
        breakpoint: int,
        fill: bool = False,
        equal_height_wide: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("careerResponsivePair")
        self._fill = fill
        self._equal_height_wide = equal_height_wide
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding if fill else QSizePolicy.Maximum,
        )
        self._first = first
        self._second = second
        self._breakpoint = breakpoint
        self._wide: Optional[bool] = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(12)
        self._layout.setVerticalSpacing(12)
        self._reflow(False)

    def _reflow(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        self._layout.removeWidget(self._first)
        self._layout.removeWidget(self._second)
        alignment = (
            Qt.Alignment()
            if self._fill or (wide and self._equal_height_wide)
            else Qt.AlignTop
        )
        if wide:
            self._layout.addWidget(self._first, 0, 0, alignment)
            self._layout.addWidget(self._second, 0, 1, alignment)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 1)
            self._layout.setRowStretch(0, 1 if self._fill else 0)
            self._layout.setRowStretch(1, 0)
        else:
            self._layout.addWidget(self._first, 0, 0, alignment)
            self._layout.addWidget(self._second, 1, 0, alignment)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 0)
            self._layout.setRowStretch(0, 1 if self._fill else 0)
            self._layout.setRowStretch(1, 1 if self._fill else 0)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._reflow(event.size().width() >= self._breakpoint)
        super().resizeEvent(event)


class _ChapterInspectorPage(QFrame):
    """Selected chapter dossier lists backed by one CareerProgressSummary.

    Identity and gate progress live on the Hero (which follows the selected
    stage), so this page deliberately has no header of its own."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerInspector")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.race_list = _ProgressRowList("RACE SCHEDULE")
        self.milestone_list = _ProgressRowList("MILESTONES")
        self._body = _ResponsivePanelPair(
            self.race_list, self.milestone_list, breakpoint=1150, fill=True
        )
        root.addWidget(self._body)

    def set_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        stage: Optional[int],
    ) -> None:
        if summary is None or stage is None:
            self.race_list.set_items("No race table loaded", ())
            self.milestone_list.set_items("No milestone table loaded", ())
            return

        chapter = summary.chapter(stage)
        requirement = chapter.requirement

        world_rank = {
            _norm_event_id(event_id): position
            for position, event_id in enumerate(
                rival_challenge.WORLD_ORDER.get(stage, ())
            )
        }
        race_rows = [
            _race_row(record, boss=False)
            for record in sorted(
                chapter.races,
                key=lambda r: (
                    world_rank.get(_norm_event_id(r.event_id), 99),
                    _event_sort_key(r),
                ),
            )
        ]
        boss_rows = _boss_series_rows(stage, chapter.boss_races)
        self.race_list.set_items(
            f"{chapter.race_wins}/{requirement.races} wins  ·  "
            f"{len(chapter.races)} events  ·  {len(boss_rows)} boss",
            race_rows,
            boss_rows,
        )

        milestone_rows = []
        for index, record in enumerate(chapter.milestones, 1):
            type_info = milestone_names.type_label_and_unit(record.type_key)
            title = type_info[0] if type_info is not None else f"Milestone {index}"
            required = _milestone_display(record.type_key, record.required_value)
            recorded = _milestone_display(record.type_key, record.recorded_value)
            if record.is_awarded:
                state = "done"
                detail = f"AWARDED · {recorded}"
                fraction: Optional[float] = None
            else:
                state = "open"
                detail = f"{recorded} / {required}"
                fraction = (
                    record.recorded_value / record.required_value
                    if record.required_value > 0
                    else None
                )
            status = "awarded" if record.is_awarded else f"state {record.state}"
            milestone_rows.append(_InspectorRow(
                title=title,
                tag="",
                state=state,
                kind="milestone",
                icon_path=_milestone_icon(record.type_key),
                detail=detail,
                fraction=fraction,
                tooltip=(
                    f"{title} — {status}\n"
                    f"Required {required} · recorded {recorded}"
                ),
            ))
        traps_in_route_order = sorted(
            chapter.speedtraps,
            key=lambda trap: milestone_names.speedtrap_ordinal(trap.trap_hash) or 99,
        )
        for index, trap in enumerate(traps_in_route_order, 1):
            ordinal = milestone_names.speedtrap_ordinal(trap.trap_hash) or index
            required_mph = trap.required_speed * 2.2369362920544
            best_mph = trap.best_speed * 2.2369362920544
            best = f"{best_mph:.1f} mph" if trap.best_speed > 0 else "—"
            # The 0..5 counter is chapter-wide (shared by every trap record of
            # the bin), so it never appears on individual rows — only the
            # trap's own speeds do; the shared counter stays in the tooltip.
            if trap.is_complete:
                state = "done"
                detail = f"DONE · BEST {best_mph:.0f} MPH" if trap.best_speed > 0 else "DONE"
                fraction: Optional[float] = None
            else:
                state = "open"
                if trap.best_speed > 0:
                    detail = f"BEST {best_mph:.0f} / {required_mph:.0f} MPH"
                    fraction = best_mph / required_mph if required_mph > 0 else None
                else:
                    detail = f"REQ {required_mph:.0f} MPH"
                    fraction = None
            milestone_rows.append(_InspectorRow(
                title=f"Speedtrap {ordinal}",
                tag="",
                state=state,
                kind="trap",
                icon_path=game_icon_path("trap"),
                detail=detail,
                fraction=fraction,
                tooltip=(
                    f"Speedtrap {ordinal} — required {required_mph:.1f} mph\n"
                    f"Chapter counter {trap.counter}/{career_progress.SPEEDTRAP_COMPLETE_COUNT}"
                    f" · best {best}"
                ),
            ))
        self.milestone_list.set_items(
            f"{chapter.milestone_wins}/{requirement.milestones} wins  ·  "
            f"{chapter.milestone_total} available",
            milestone_rows,
        )


def _fmt_race_time(seconds: float) -> str:
    if seconds < 60.0:
        return f"{seconds:.2f}"
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:05.2f}"


def _race_best_result(record: career_progress.RaceRecord, type_label: str) -> Optional[str]:
    """Human reading of the race-table high_score field.

    The u32 stores IEEE-754 float bits: the best TIME in seconds for every
    mode except speedtrap races, which accumulate a speed score (the HUD's
    running total). Out-of-range values fall back to the raw int."""
    if record.high_score == 0:
        return None
    value = struct.unpack("<f", struct.pack("<I", record.high_score))[0]
    if not 1.0 <= value < 100_000.0:
        return f"{record.high_score:,}"
    if type_label == "Speedtrap":
        return f"SCORE {value:,.0f}"
    return _fmt_race_time(value)


def _race_row(record: career_progress.RaceRecord, *, boss: bool) -> _InspectorRow:
    event = record.event_id or f"slot {record.index}"
    fallback = f"Event {event[:-2] if event.endswith('.r') else event}"
    # A few save slots track a route with a different EventID (slot 8.3.2
    # drives 13.3.1.r); name, type and icon follow the DRIVEN route.
    route_id = rival_challenge.ROUTE_REMAP.get(record.event_id or "", record.event_id)
    title = race_display_names.display_name(route_id) or fallback
    type_label = race_display_names.type_label(route_id) or "Event"
    kind_line = f"{type_label} · {record.event_id}" + (" · boss race" if boss else "")
    if route_id != record.event_id:
        kind_line += f" · route {route_id}"
    if record.is_completed:
        state = "done"
        best = _race_best_result(record, type_label)
        detail = f"WON · {best}" if best else "WON"
        tooltip_detail = (
            f"completed{f' · best {best}' if best else ''}\n"
            f"top {record.top_speed:.1f} · avg {record.average_speed:.1f}"
        )
    elif record.flags & career_progress.RACE_FLAG_UNLOCKED_CAREER:
        state = "open"
        detail = "AVAILABLE"
        tooltip_detail = "available"
    else:
        state = "locked"
        detail = "LOCKED"
        tooltip_detail = "locked"
    reversed_route = record.is_reversed or bool(route_id and route_id.endswith(".r"))
    return _InspectorRow(
        title=title,
        tag="REVERSED" if reversed_route else "",
        state=state,
        kind="boss" if boss else "race",
        icon_path=game_icon_path(_race_type_icon(route_id)),
        detail=detail,
        fraction=None,
        tooltip=f"{title} — {tooltip_detail}\n{kind_line}",
    )


class CareerMixin:
    def _build_career_page(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(0)
        self.career_canvas = QWidget()
        self.career_canvas.setObjectName("careerCanvas")
        self.career_canvas.setMaximumWidth(1640)
        self.career_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self.career_canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        outer.addStretch(1)
        outer.addWidget(self.career_canvas, 100)
        outer.addStretch(1)

        self.career_donor_root = default_user_career_donor_root()
        self.career_donor_library: tuple[CareerDonorEntry, ...] = ()
        self._career_donor_signature: Optional[tuple] = None
        self._career_snapshot_cache: Optional[bytes] = None
        self._career_summary_cache: Optional[career_progress.CareerProgressSummary] = None
        self._career_selected_stage: Optional[int] = None
        self._career_defeated_stamp: Optional[QPixmap] = None

        # ── Current target hero + compact progression summary ──
        self.career_hero = _CareerHero()
        self._career_hero_transition: Optional[ThemeTransitionOverlay] = None
        hero_layout = QHBoxLayout(self.career_hero)
        hero_layout.setContentsMargins(28, 18, 20, 16)
        hero_layout.setSpacing(14)

        hero_copy = QVBoxLayout()
        hero_copy.setContentsMargins(0, 34, 0, 0)
        hero_copy.setSpacing(3)
        eyebrow = QLabel("BLACKLIST")
        eyebrow.setObjectName("careerHeroEyebrow")
        eyebrow.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        hero_copy.addWidget(eyebrow)

        headline = QHBoxLayout()
        headline.setSpacing(10)
        self.career_stage_value = QLabel("-")
        self.career_stage_value.setObjectName("careerHeroRank")
        self.career_stage_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        headline.addWidget(self.career_stage_value)
        self.career_boss_value = QLabel("NO SAVE LOADED")
        self.career_boss_value.setObjectName("careerHeroBoss")
        self.career_boss_value.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        headline.addWidget(self.career_boss_value)
        self.career_hero_status = QLabel("NO DATA")
        self.career_hero_status.setObjectName("careerHeroStatus")
        self.career_hero_status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        headline.addWidget(self.career_hero_status, 0, Qt.AlignVCenter)
        headline.addStretch(1)
        hero_copy.addLayout(headline)
        self.career_hero_tagline = QLabel("")
        self.career_hero_tagline.setObjectName("careerHeroTagline")
        self.career_hero_tagline.setWordWrap(True)
        self.career_hero_tagline.setMaximumWidth(640)
        self.career_hero_tagline.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.career_hero_tagline.setVisible(False)
        hero_copy.addWidget(self.career_hero_tagline)
        hero_copy.addStretch(1)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.career_races_value = QLabel("-")
        self.career_races_metric = self._build_career_hero_metric(
            "RACE WINS", self.career_races_value, "race"
        )
        metrics.addWidget(self.career_races_metric)
        self.career_milestones_value = QLabel("-")
        self.career_milestones_metric = self._build_career_hero_metric(
            "MILESTONES", self.career_milestones_value, "milestone"
        )
        metrics.addWidget(self.career_milestones_metric)
        self.career_bounty_value = QLabel("-")
        self.career_bounty_metric = self._build_career_hero_metric(
            "BOUNTY", self.career_bounty_value, "bounty"
        )
        metrics.addWidget(self.career_bounty_metric)
        metrics.addStretch(1)
        hero_copy.addLayout(metrics)
        hero_copy.addSpacing(12)

        # ── View switch: safe progress overview | stage change ──
        self.career_view_switch = AnimatedSegmentedControl(
            ("PROGRESS", "CHANGE RIVAL"),
            button_object_name="careerViewTab",
            fixed_height=44,
        )
        self.career_view_rapsheet_btn = self.career_view_switch.button(0)
        self.career_view_transplant_btn = self.career_view_switch.button(1)
        hero_switch_row = QHBoxLayout()
        hero_switch_row.addWidget(self.career_view_switch)
        hero_switch_row.addStretch(1)
        hero_copy.addLayout(hero_switch_row)

        hero_layout.addLayout(hero_copy, 3)
        hero_layout.addStretch(2)
        layout.addWidget(self.career_hero)

        self.career_view_stack = AnimatedStackedWidget(duration_ms=180)
        self._career_view_transition: Optional[ThemeTransitionOverlay] = None
        self.career_view_stack.addWidget(self._build_career_transplant_view())
        self.career_view_stack.addWidget(self._build_career_progress_view())
        self.career_view_stack.setCurrentIndex(1)
        self.career_view_switch.currentChanged.connect(self._on_career_view_changed)
        layout.addWidget(self.career_view_stack, 1)

        self._reload_career_donor_library(force=True)
        self._rebuild_career_stage_list()
        self._refresh_career_preview()
        self._refresh_career_progress(None, animate=False)
        return w

    def _build_career_hero_metric(
        self, caption: str, value: QLabel, icon_name: str
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("careerHeroMetric")
        frame.setProperty("met", False)
        frame.setFixedSize(188, 72)
        metric_layout = QHBoxLayout(frame)
        metric_layout.setContentsMargins(12, 9, 14, 9)
        metric_layout.setSpacing(10)

        icon_path = game_icon_path(icon_name)
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon = QLabel()
                icon.setObjectName("careerHeroMetricIcon")
                icon.setFixedSize(32, 32)
                icon.setAlignment(Qt.AlignCenter)
                icon.setPixmap(self._tight_icon(
                    icon_path, QSize(30, 30)
                ).pixmap(30, 30))
                metric_layout.addWidget(icon, 0, Qt.AlignVCenter)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(0)
        value.setObjectName("careerHeroMetricValue")
        value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label = QLabel(caption)
        label.setObjectName("careerHeroMetricLabel")
        copy.addWidget(value)
        copy.addWidget(label)
        metric_layout.addLayout(copy)
        return frame

    def _build_career_transplant_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("careerTransplantView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(0)

        target_card, target_layout = self._make_card_frame(
            object_name="careerTargetPanel",
            vertical_policy=QSizePolicy.Preferred,
        )
        self.career_target_panel = target_card
        target_layout.setContentsMargins(18, 16, 18, 16)
        target_layout.setSpacing(9)
        step = QLabel("STEP 01")
        step.setObjectName("careerStepLabel")
        target_layout.addWidget(step)
        title = QLabel("Pick the target chapter")
        title.setObjectName("careerPanelTitle")
        target_layout.addWidget(title)
        intro = QLabel(
            "Choose where the Blacklist story should resume. Only stages backed by "
            "a validated donor snapshot can be selected."
        )
        intro.setObjectName("careerPanelCopy")
        intro.setWordWrap(True)
        target_layout.addWidget(intro)

        self.career_variant_switch = AnimatedSegmentedControl(
            ("CHAPTER START", "CHALLENGE RIVAL"),
            button_object_name="careerVariantButton",
        )
        self.career_variant_start = self.career_variant_switch.button(0)
        self.career_variant_ready = self.career_variant_switch.button(1)
        self.career_variant_switch.currentChanged.connect(self._on_career_variant_changed)
        target_layout.addWidget(self.career_variant_switch)

        self.career_stage_grid_host = QWidget()
        self.career_stage_grid_host.setObjectName("careerStageGrid")
        stage_grid = QGridLayout(self.career_stage_grid_host)
        stage_grid.setContentsMargins(0, 2, 0, 2)
        stage_grid.setHorizontalSpacing(6)
        stage_grid.setVerticalSpacing(6)
        self.career_stage_buttons: Dict[int, QPushButton] = {}
        self.career_stage_group = QButtonGroup(view)
        self.career_stage_group.setExclusive(True)
        for pos, stage in enumerate(range(15, 0, -1)):
            button = QPushButton(f"#{stage}  {BLACKLIST_BOSS_NAMES.get(stage, '?').upper()}")
            button.setObjectName("careerStageButton")
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("stage", stage)
            button.toggled.connect(
                lambda checked, s=stage: self._on_career_stage_toggled(s, checked)
            )
            self.career_stage_group.addButton(button)
            self.career_stage_buttons[stage] = button
            stage_grid.addWidget(button, pos // 3, pos % 3)
        for column in range(3):
            stage_grid.setColumnStretch(column, 1)
        target_layout.addWidget(self.career_stage_grid_host, 1)

        self.career_library_status = QLabel("")
        self.career_library_status.setObjectName("careerLibraryStatus")
        target_layout.addWidget(self.career_library_status)

        review_card, review_layout = self._make_card_frame(
            object_name="careerReviewPanel",
            vertical_policy=QSizePolicy.Preferred,
        )
        review_layout.setContentsMargins(18, 16, 18, 16)
        review_layout.setSpacing(9)
        self.career_review_panel = review_card
        self._career_review_transition: Optional[ThemeTransitionOverlay] = None
        step = QLabel("STEP 02")
        step.setObjectName("careerStepLabel")
        review_layout.addWidget(step)
        title = QLabel("Review the transfer")
        title.setObjectName("careerPanelTitle")
        review_layout.addWidget(title)

        route = QFrame()
        route.setObjectName("careerRoute")
        route_layout = QHBoxLayout(route)
        route_layout.setContentsMargins(12, 10, 12, 10)
        route_layout.setSpacing(8)
        self.career_route_from = QLabel("OPEN A SAVE")
        self.career_route_from.setObjectName("careerRouteStage")
        self.career_route_from.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(self.career_route_from, 1)
        arrow = QLabel("→")
        arrow.setObjectName("careerRouteArrow")
        arrow.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(arrow)
        self.career_route_to = QLabel("SELECT TARGET")
        self.career_route_to.setObjectName("careerRouteStage")
        self.career_route_to.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(self.career_route_to, 1)
        review_layout.addWidget(route)

        self.career_preview_status = QLabel("")
        self.career_preview_status.setObjectName("careerPreviewStatus")
        self.career_preview_status.setWordWrap(True)
        # Normal previews vary between one and four lines (same-stage warning,
        # bounty compensation, donor warnings). Keep the full four-line slot so
        # changing targets cannot alter sizeHint and nudge the whole workflow.
        self.career_preview_status.setFixedHeight(96)
        self.career_preview_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        review_layout.addWidget(self.career_preview_status)

        impact_row = QHBoxLayout()
        impact_row.setSpacing(8)
        changes, changes_layout = self._build_career_impact_box("CHANGES", "changes")
        self.career_preview_changes = QLabel(
            "Career stage\nRace & milestone progress\nStory SMS & shop unlocks"
        )
        self.career_preview_changes.setObjectName("careerImpactItems")
        self.career_preview_changes.setWordWrap(True)
        changes_layout.addWidget(self.career_preview_changes)
        impact_row.addWidget(changes, 1)
        keeps, keeps_layout = self._build_career_impact_box("STAYS YOURS", "keeps")
        self.career_preview_keeps = QLabel(
            "Money & profile alias\nCars, parts & garage stats\nJunkman inventory"
        )
        self.career_preview_keeps.setObjectName("careerImpactItems")
        self.career_preview_keeps.setWordWrap(True)
        keeps_layout.addWidget(self.career_preview_keeps)
        impact_row.addWidget(keeps, 1)
        review_layout.addLayout(impact_row)

        self.career_preview_caveat = QLabel(_BOUNTY_CAVEAT_TEXT)
        self.career_preview_caveat.setObjectName("careerSafetyNote")
        self.career_preview_caveat.setWordWrap(True)
        review_layout.addWidget(self.career_preview_caveat)
        review_layout.addStretch(1)

        self.btn_career_transplant = self._make_card_action_button(
            "APPLY STAGE TO MEMORY", object_name="careerTransplantButton"
        )
        self.btn_career_transplant.setMinimumHeight(42)
        self.btn_career_transplant.setCursor(Qt.PointingHandCursor)
        self.btn_career_transplant.clicked.connect(self._on_career_transplant_clicked)
        review_layout.addWidget(self.btn_career_transplant)
        disk_note = QLabel("Disk stays untouched until you choose Save + backup.")
        disk_note.setObjectName("careerDiskNote")
        disk_note.setAlignment(Qt.AlignCenter)
        review_layout.addWidget(disk_note)

        self.career_transplant_pair = _ResponsivePanelPair(
            target_card,
            review_card,
            breakpoint=1200,
            equal_height_wide=True,
        )
        layout.addWidget(self.career_transplant_pair, 0, Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setObjectName("cardScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(view)
        return scroll

    def _build_career_impact_box(
        self, title: str, impact: str
    ) -> tuple[QFrame, QVBoxLayout]:
        box = QFrame()
        box.setObjectName("careerImpactBox")
        box.setProperty("impact", impact)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(11, 9, 11, 9)
        box_layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("careerImpactTitle")
        box_layout.addWidget(heading)
        return box, box_layout

    # ── Rap Sheet view (read-only dossier) ─────────────────────

    def _build_career_progress_view(self) -> QWidget:
        host = QWidget()
        host.setObjectName("careerProgressView")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 6, 0)
        host_layout.setSpacing(10)
        host_layout.setAlignment(Qt.AlignTop)

        self.career_timeline = _BlacklistTimeline()
        self.career_timeline.stageSelected.connect(self._on_career_timeline_selected)
        host_layout.addWidget(self.career_timeline)

        self.career_inspector_stack = AnimatedStackedWidget(
            duration_ms=_BlacklistTimeline._SELECTION_DURATION_MS
        )
        self._career_inspector_transition: Optional[ThemeTransitionOverlay] = None
        self.career_inspector_stack.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.career_inspector_pages = (_ChapterInspectorPage(), _ChapterInspectorPage())
        for page in self.career_inspector_pages:
            self.career_inspector_stack.addWidget(page)
        self.career_inspector_stack.setCurrentIndex(0)
        host_layout.addWidget(self.career_inspector_stack, 1)
        host_layout.addWidget(self._build_career_totals_strip())

        scroll = QScrollArea()
        scroll.setObjectName("cardScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(host)
        return scroll

    def _build_career_totals_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("careerTotalsStrip")
        strip.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(strip)
        row.setContentsMargins(24, 11, 24, 11)
        row.setSpacing(12)
        self.career_total_races_value = QLabel("—")
        self.career_total_milestones_value = QLabel("—")
        self.career_total_bounty_value = QLabel("—")
        self.career_total_prologue_value = QLabel("—")
        cells = (
            ("race", "RACES", self.career_total_races_value),
            ("milestone", "MILESTONES", self.career_total_milestones_value),
            ("bounty", "BOUNTY", self.career_total_bounty_value),
            ("rival_race", "PROLOGUE", self.career_total_prologue_value),
        )
        row.addStretch(1)
        for position, (icon_name, caption, value) in enumerate(cells):
            if position:
                row.addStretch(2)
            cell = QHBoxLayout()
            cell.setSpacing(10)
            icon_path = game_icon_path(icon_name)
            if icon_path is not None:
                icon = QLabel()
                icon.setObjectName("careerTotalsIcon")
                icon.setFixedSize(26, 26)
                icon.setAlignment(Qt.AlignCenter)
                icon.setPixmap(self._tight_icon(
                    icon_path, QSize(24, 24)
                ).pixmap(24, 24))
                cell.addWidget(icon, 0, Qt.AlignVCenter)
            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(0)
            caption_label = QLabel(caption)
            caption_label.setObjectName("careerTotalsCaption")
            value.setObjectName("careerTotalsValue")
            copy.addWidget(caption_label)
            copy.addWidget(value)
            cell.addLayout(copy)
            row.addLayout(cell)
        row.addStretch(1)
        return strip

    def _on_career_view_changed(self, index: int) -> None:
        view_snapshot = self._career_crossfade_snapshot(
            self.career_view_stack, "_career_view_transition"
        )
        target = 1 if index == 0 else 0
        summary = self._career_summary_cache
        if summary is not None:
            hero_stage = (
                self._career_selected_stage if index == 0 else summary.current_stage
            )
            self._update_career_hero(summary, hero_stage)
        if index == 1:
            self._rebuild_career_stage_list(
                preferred_stage=summary.current_stage if summary is not None else None
            )
            self._refresh_career_preview()
        self.career_view_stack.setCurrentIndex(target)
        self.career_view_stack.updateGeometry()
        self._start_career_crossfade(
            self.career_view_stack,
            view_snapshot,
            "_career_view_transition",
            "careerViewTransitionOverlay",
        )

    def _on_career_timeline_selected(self, stage: int) -> None:
        summary = self._career_summary_cache
        if summary is None or stage == self._career_selected_stage:
            return
        hero_snapshot = self._career_crossfade_snapshot(
            self.career_hero, "_career_hero_transition"
        )
        inspector_snapshot = self._career_crossfade_snapshot(
            self.career_inspector_stack, "_career_inspector_transition"
        )
        self._career_selected_stage = stage
        self.career_timeline.set_selected_stage(stage)
        self._update_career_hero(summary, stage)
        target_index = 1 - self.career_inspector_stack.currentIndex()
        self.career_inspector_pages[target_index].set_progress(summary, stage)
        self.career_inspector_pages[target_index].updateGeometry()
        self.career_inspector_stack.setCurrentIndex(target_index)
        self.career_inspector_stack.updateGeometry()
        self._start_career_crossfade(
            self.career_hero,
            hero_snapshot,
            "_career_hero_transition",
            "careerHeroTransitionOverlay",
        )
        self._start_career_crossfade(
            self.career_inspector_stack,
            inspector_snapshot,
            "_career_inspector_transition",
            "careerInspectorTransitionOverlay",
        )

    def _refresh_career_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        *,
        animate: bool,
    ) -> None:
        if summary is not None and self._career_selected_stage is None:
            self._career_selected_stage = summary.default_stage
        stage = self._career_selected_stage if summary is not None else None
        self.career_timeline.set_progress(summary, stage)
        current = self.career_inspector_stack.currentIndex()
        self.career_inspector_pages[current].set_progress(summary, stage)
        self.career_inspector_pages[current].updateGeometry()
        self.career_inspector_stack.updateGeometry()
        self._update_career_totals(summary)
        self._update_career_hero(summary, stage)

    def _update_career_totals(
        self, summary: Optional[career_progress.CareerProgressSummary]
    ) -> None:
        if summary is None:
            for label in (
                self.career_total_races_value,
                self.career_total_milestones_value,
                self.career_total_bounty_value,
                self.career_total_prologue_value,
            ):
                label.setText("—")
            return
        self.career_total_races_value.setText(
            f"{summary.lifetime_race_wins} / {summary.lifetime_race_total}"
        )
        self.career_total_milestones_value.setText(
            f"{summary.lifetime_milestone_wins} / {summary.lifetime_milestone_total}"
        )
        self.career_total_bounty_value.setText(_fmt_compact(summary.total_bounty))
        prologue_done = sum(record.is_completed for record in summary.prologue_races)
        self.career_total_prologue_value.setText(
            f"{prologue_done} / {len(summary.prologue_races)}"
        )

    def _update_career_hero(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        stage: Optional[int],
    ) -> None:
        if summary is None or stage is None:
            self.career_hero.set_stage(None)
            self.career_stage_value.setText("-")
            self.career_boss_value.setText("NO SAVE LOADED")
            self.career_hero_tagline.setVisible(False)
            self.career_hero_tagline.clear()
            self.career_hero_tagline.setToolTip("")
            self._set_career_hero_status("NO DATA", "locked")
            for frame, label in (
                (self.career_races_metric, self.career_races_value),
                (self.career_milestones_metric, self.career_milestones_value),
                (self.career_bounty_metric, self.career_bounty_value),
            ):
                self._set_career_metric(frame, label, "-", False)
            self._polish_career_hero_status()
            return

        chapter = summary.chapter(stage)
        requirement = chapter.requirement
        state = summary.stage_state(stage)
        status_text = {
            "defeated": "DEFEATED",
            "current": "CURRENT TARGET",
            "boss_ready": "BOSS READY",
            "locked": "LOCKED",
        }[state]
        if summary.endgame and stage == 1:
            status_text = "BLACKLIST CLEARED"
        boss = BLACKLIST_BOSS_NAMES.get(stage, "Unknown")
        self.career_hero.set_stage(stage)
        self.career_stage_value.setText(f"#{stage}")
        self.career_boss_value.setText(boss.upper())
        tagline = rival_bios.tagline(stage)
        if tagline:
            self.career_hero_tagline.setText(tagline)
            self.career_hero_tagline.setToolTip(rival_bios.bio(stage) or "")
            self.career_hero_tagline.setVisible(True)
        else:
            self.career_hero_tagline.setVisible(False)
            self.career_hero_tagline.clear()
            self.career_hero_tagline.setToolTip("")
        self._set_career_hero_status(status_text, state)
        self._set_career_metric(
            self.career_races_metric,
            self.career_races_value,
            f"{chapter.race_wins} / {requirement.races}",
            chapter.race_wins >= requirement.races,
        )
        self._set_career_metric(
            self.career_milestones_metric,
            self.career_milestones_value,
            f"{chapter.milestone_wins} / {requirement.milestones}",
            chapter.milestone_wins >= requirement.milestones,
        )
        self._set_career_metric(
            self.career_bounty_metric,
            self.career_bounty_value,
            f"{_fmt_compact(summary.total_bounty)} / {_fmt_compact(requirement.bounty)}",
            summary.total_bounty >= requirement.bounty,
        )
        self._polish_career_hero_status()

    @staticmethod
    def _set_career_metric(frame: QFrame, label: QLabel, text: str, met: bool) -> None:
        label.setText(text)
        if frame.property("met") != met:
            frame.setProperty("met", met)
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def _polish_career_hero_status(self) -> None:
        self.career_hero_status.style().unpolish(self.career_hero_status)
        self.career_hero_status.style().polish(self.career_hero_status)

    def _set_career_hero_status(self, text: str, state: str) -> None:
        label = self.career_hero_status
        label.clear()
        label.setProperty("state", state)
        label.setAccessibleName(text)
        label.setToolTip(text if state == "defeated" else "")
        stamp = self._defeated_stamp_pixmap() if state == "defeated" else QPixmap()
        self.career_hero.set_defeated_stamp(stamp)
        show_portrait_stamp = state == "defeated" and not stamp.isNull()
        self.career_hero.setAccessibleDescription(
            "DEFEATED" if state == "defeated" else ""
        )
        label.setProperty("stamp", False)
        label.setHidden(state == "current" or show_portrait_stamp)

        if state == "current" or show_portrait_stamp:
            label.setMinimumSize(0, 0)
            label.setMaximumSize(QSize(16777215, 16777215))
            label.updateGeometry()
            return

        label.setMinimumSize(0, 0)
        label.setMaximumSize(QSize(16777215, 16777215))
        label.setText(text)
        label.updateGeometry()

    def _defeated_stamp_pixmap(self) -> QPixmap:
        if self._career_defeated_stamp is not None:
            return self._career_defeated_stamp

        path = game_icon_path("status_defeated")
        if path is None:
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        # Keep the game texture at native resolution through tinting and rotation.
        # The previous 146x36 intermediate was later enlarged to 175/210 px in the
        # Hero, so its already-antialiased edges became visibly soft.  These
        # reference dimensions now define composition only; all raster work stays
        # at the source texture's substantially larger native scale.
        source_texture = QPixmap(str(path))
        if source_texture.isNull():
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        reference_source = QSize(146, 36)
        render_scale = source_texture.height() / reference_source.height()
        source = QPixmap(
            round(reference_source.width() * render_scale),
            source_texture.height(),
        )
        source.fill(Qt.transparent)
        source_painter = QPainter(source)
        source_painter.drawPixmap(
            (source.width() - source_texture.width()) // 2,
            0,
            source_texture,
        )
        source_painter.end()
        if source.isNull():
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        def tinted_layer(color: str) -> QPixmap:
            layer = QPixmap(source.size())
            layer.fill(Qt.transparent)
            layer_painter = QPainter(layer)
            layer_painter.drawPixmap(0, 0, source)
            layer_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            layer_painter.fillRect(layer.rect(), QColor(color))
            layer_painter.end()
            return layer

        # The game stamp is not a flat red mask: weak ink reads almost black while
        # dense lettering and frame edges carry the brighter crimson.  Layering the
        # same worn mask in two tones recreates that range on our uniform navy Hero
        # instead of making every variation look like blue background transparency.
        dark_ink = tinted_layer("#430506")
        bright_ink = tinted_layer("#930A0A")
        inked = QPixmap(source.size())
        inked.fill(Qt.transparent)
        painter = QPainter(inked)
        backing = QPainterPath()
        backing.moveTo(3.0, 5.0)
        backing.lineTo(141.0, 1.0)
        backing.lineTo(145.0, 27.0)
        backing.lineTo(139.0, 33.0)
        backing.lineTo(7.0, 35.0)
        backing.lineTo(1.0, 30.0)
        backing.closeSubpath()
        painter.save()
        painter.scale(render_scale, render_scale)
        painter.fillPath(backing, QColor(7, 8, 9, 234))
        painter.restore()
        painter.drawPixmap(0, 0, dark_ink)
        painter.drawPixmap(0, 0, bright_ink)
        painter.end()

        rotated = inked.transformed(
            QTransform().rotate(-4.0), Qt.SmoothTransformation
        )
        canvas = QPixmap(round(180 * render_scale), round(56 * render_scale))
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(
            (canvas.width() - rotated.width()) // 2,
            (canvas.height() - rotated.height()) // 2,
            rotated,
        )
        painter.end()
        self._career_defeated_stamp = canvas
        return canvas

    def _build_career_rap_sheet_view(self) -> QWidget:
        host = QWidget()
        self.rap_sheet_layout = QVBoxLayout(host)
        self.rap_sheet_layout.setContentsMargins(0, 0, 6, 0)
        self.rap_sheet_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setObjectName("cardScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(host)
        return scroll

    def _refresh_rap_sheet(self) -> None:
        while self.rap_sheet_layout.count():
            item = self.rap_sheet_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        savefile = getattr(self, "savefile", None)
        if savefile is None:
            card, card_layout = self._make_card_frame()
            note = QLabel("Open a save to assemble the rap sheet.")
            note.setObjectName("contentCardNote")
            note.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(note)
            self.rap_sheet_layout.addWidget(card)
            self.rap_sheet_layout.addStretch(1)
            return

        data = bytes(savefile.data)
        current_bin = career_transplant.read_current_bin(data)
        milestones = career_progress.parse_milestones(data)
        speedtraps = career_progress.parse_speedtraps(data)
        races = career_progress.parse_races(data)

        endgame = bool(career_progress.is_endgame(data))
        self.rap_sheet_layout.addWidget(self._build_rap_board_card(current_bin, endgame))

        progress_columns = _ResponsiveProgressColumns(
            self._build_rap_milestones_card(milestones, speedtraps),
            self._build_rap_races_card(races),
        )
        self.rap_sheet_layout.addWidget(progress_columns)
        self.rap_sheet_layout.addStretch(1)

    def _rap_count_chip(self, done: int, total: int) -> QLabel:
        chip = QLabel(f"{done} / {total}")
        chip.setObjectName("rapRowCount")
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        chip.setAlignment(Qt.AlignCenter)
        if total > 0 and done >= total:
            chip.setProperty("status", "full")
        return chip

    def _rap_card(self, title: str, done: int, total: int) -> tuple[QFrame, QVBoxLayout]:
        card, card_layout = self._make_card_frame(vertical_policy=QSizePolicy.Minimum)
        head = QHBoxLayout()
        head.setSpacing(8)
        heading = self._make_card_field_label(title, "careerSectionTitle")
        heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        head.addWidget(heading)
        head.addStretch(1)
        head.addWidget(self._rap_count_chip(done, total))
        card_layout.addLayout(head)
        card_layout.addWidget(self._make_card_separator())
        return card, card_layout

    def _rap_dot(
        self,
        state: str,
        tooltip: str,
        *,
        kind: Optional[str] = None,
        boss: bool = False,
    ) -> QFrame:
        if boss:
            shape = "square"
            icon_name = "boss_race"
        elif kind == "trap":
            shape = "triangle"
            icon_name = "trap"
        elif kind == "milestone":
            shape = "triangle"
            icon_name = "milestone"
        elif kind == "race":
            shape = "circle"
            icon_name = "race"
        else:
            shape = "circle"
            icon_name = None
        dot = _RapMarker(shape, game_icon_path(icon_name) if icon_name else None)
        dot.setProperty("state", state)
        if kind:
            dot.setProperty("kind", kind)
        if boss:
            dot.setProperty("boss", True)
        size = (
            _RAP_BOSS_DOT_SIZE
            if boss
            else (_RAP_TRAP_DOT_SIZE if kind == "trap" else _RAP_DOT_SIZE)
        )
        dot.setFixedSize(size, size)
        dot.setToolTip(tooltip)
        return dot

    def _rap_dot_row(
        self, label_text: str, dots: Sequence[QFrame], done: int, total: int
    ) -> QWidget:
        row = QWidget()
        row.setObjectName("rapDotRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("rapRowLabel")
        label.setFixedWidth(92)
        row_layout.addWidget(label)
        for dot in dots:
            row_layout.addWidget(dot)
        row_layout.addStretch(1)
        row_layout.addWidget(self._rap_count_chip(done, total))
        return row

    def _build_rap_board_card(self, current_bin: Optional[int], endgame: bool) -> QFrame:
        stages = list(range(15, 0, -1))
        # CurrentBin stays 1 after Razor falls; the endgame flag is the only
        # signal that #1 is DOWN rather than NEXT UP.
        in_career = (
            not endgame and current_bin is not None and 1 <= current_bin <= 15
        )
        defeated = sum(
            1 for s in stages
            if (in_career and s > current_bin) or not in_career
        )
        card, card_layout = self._rap_card("BLACKLIST LADDER", defeated, len(stages))

        grid_host = QWidget()
        grid_host.setObjectName("rapBoardGrid")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for pos, stage in enumerate(stages):
            if not in_career:
                state, tag = "defeated", "DOWN"
            elif stage > current_bin:
                state, tag = "defeated", "DOWN"
            elif stage == current_bin:
                state, tag = "current", "NEXT UP"
            else:
                state, tag = "locked", ""
            cell = self._build_rap_boss_cell(stage, state, tag)
            grid.addWidget(cell, pos // _BOSS_GRID_COLUMNS, pos % _BOSS_GRID_COLUMNS)
        for col in range(_BOSS_GRID_COLUMNS):
            grid.setColumnStretch(col, 1)
        card_layout.addWidget(grid_host)
        return card

    def _build_rap_boss_cell(self, stage: int, state: str, tag: str) -> QFrame:
        cell = QFrame()
        cell.setObjectName("rapBossCell")
        cell.setProperty("state", state)
        cell.setMinimumHeight(54)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(9, 6, 9, 7)
        cell_layout.setSpacing(1)

        top = QHBoxLayout()
        top.setSpacing(4)
        num = QLabel(f"#{stage}")
        num.setObjectName("rapBossNum")
        top.addWidget(num)
        top.addStretch(1)
        if tag:
            tag_label = QLabel(tag)
            tag_label.setObjectName("rapBossTag")
            top.addWidget(tag_label)
        cell_layout.addLayout(top)

        name = QLabel(BLACKLIST_BOSS_NAMES.get(stage, "?").upper())
        name.setObjectName("rapBossName")
        if state == "defeated":
            font = name.font()
            font.setStrikeOut(True)
            name.setFont(font)
        cell_layout.addWidget(name)

        tooltips = {
            "defeated": "taken down",
            "current": "current target",
            "locked": "not yet reached",
        }
        cell.setToolTip(f"{_stage_title(stage)} — {tooltips.get(state, state)}")
        return cell

    def _build_rap_milestones_card(
        self,
        milestones: Optional[Tuple[career_progress.MilestoneRecord, ...]],
        speedtraps: Optional[Tuple[career_progress.SpeedtrapRecord, ...]],
    ) -> QFrame:
        if milestones is None:
            card, card_layout = self._make_card_frame()
            note = QLabel("Milestone table could not be located in this save.")
            note.setObjectName("contentCardNote")
            note.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(note)
            return card

        traps = tuple(speedtraps or ())
        awarded_total = (
            sum(1 for m in milestones if m.is_awarded)
            + sum(1 for t in traps if t.is_complete)
        )
        card, card_layout = self._rap_card(
            "MILESTONES", awarded_total, len(milestones) + len(traps)
        )

        by_bin: Dict[int, List[career_progress.MilestoneRecord]] = {}
        for record in milestones:
            by_bin.setdefault(record.bin_number, []).append(record)
        traps_by_bin: Dict[int, List[career_progress.SpeedtrapRecord]] = {}
        for trap in traps:
            traps_by_bin.setdefault(trap.bin_number, []).append(trap)

        all_bins = set(by_bin) | set(traps_by_bin)
        known = [b for b in sorted(all_bins, reverse=True) if b in BLACKLIST_BOSS_NAMES]
        other = [b for b in sorted(all_bins, reverse=True) if b not in BLACKLIST_BOSS_NAMES]
        for bin_number in known + other:
            group = by_bin.get(bin_number, [])
            trap_group = traps_by_bin.get(bin_number, [])
            boss = BLACKLIST_BOSS_NAMES.get(bin_number)
            label = f"#{bin_number} · {boss}" if boss else f"Bin {bin_number}"
            dots = []
            for record in group:
                if record.is_awarded:
                    status = "awarded"
                elif record.state == 1:
                    status = "active"
                else:
                    status = f"state {record.state}"
                dots.append(self._rap_dot(
                    "done" if record.is_awarded else "open",
                    (
                        f"Milestone {record.index + 1} — {status}\n"
                        f"required {_fmt_num(record.required_value)}"
                        f" · recorded {_fmt_num(record.recorded_value)}"
                    ),
                    kind="milestone",
                ))
            for trap in trap_group:
                best = (
                    f"best {trap.best_speed:.1f} mph"
                    if trap.best_speed > 0 else "best —"
                )
                dots.append(self._rap_dot(
                    "done" if trap.is_complete else "open",
                    (
                        f"Speedtrap milestone — required {trap.required_speed:.1f} mph\n"
                        f"progress {trap.counter}/{career_progress.SPEEDTRAP_COMPLETE_COUNT}"
                        f" · {best}"
                    ),
                    kind="trap",
                ))
            done = (
                sum(1 for r in group if r.is_awarded)
                + sum(1 for t in trap_group if t.is_complete)
            )
            card_layout.addWidget(
                self._rap_dot_row(label, dots, done, len(group) + len(trap_group))
            )

        note = QLabel(
            "Milestone icons include speedtraps; speedtrap tooltips show their "
            "per-chapter n/5 progress."
        )
        note.setObjectName("rapFootnote")
        note.setWordWrap(True)
        card_layout.addWidget(note)
        return card

    def _build_rap_races_card(
        self, races: Optional[Tuple[career_progress.RaceRecord, ...]]
    ) -> QFrame:
        if races is None:
            card, card_layout = self._make_card_frame()
            note = QLabel("Race table could not be read from this save.")
            note.setObjectName("contentCardNote")
            note.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(note)
            return card

        # Grouped by the ladder-derived OFFERING chapter (matches the in-game
        # per-chapter race counts), not by the EventID route prefix.
        regular_by: Dict[int, List[career_progress.RaceRecord]] = {}
        boss_by: Dict[int, List[career_progress.RaceRecord]] = {}
        prologue: List[career_progress.RaceRecord] = []
        for record in races:
            if record.offering_chapter is not None:
                target = boss_by if record.is_boss_race else regular_by
                target.setdefault(record.offering_chapter, []).append(record)
            elif record.chapter == career_progress.PROLOGUE_CHAPTER:
                prologue.append(record)

        career_events = (
            prologue
            + [r for g in regular_by.values() for r in g]
            + [r for g in boss_by.values() for r in g]
        )
        done_total = sum(1 for r in career_events if r.is_completed)
        card, card_layout = self._rap_card("RACE TABLE", done_total, len(career_events))

        if prologue:
            group = sorted(prologue, key=_event_sort_key)
            dots = [self._rap_race_dot(record) for record in group]
            done = sum(1 for r in group if r.is_completed)
            card_layout.addWidget(self._rap_dot_row("Prologue", dots, done, len(group)))

        for chapter in range(15, 0, -1):
            group = sorted(regular_by.get(chapter, []), key=_event_sort_key)
            boss_group = sorted(boss_by.get(chapter, []), key=_event_sort_key)
            if not group and not boss_group:
                continue
            boss = BLACKLIST_BOSS_NAMES.get(chapter)
            label = f"#{chapter} · {boss}" if boss else f"#{chapter}"
            dots = [self._rap_race_dot(record) for record in group]
            dots.extend(self._rap_race_dot(r, boss_race=True) for r in boss_group)
            # Chip mirrors the in-game per-chapter race counter, which
            # excludes boss races.
            done = sum(1 for r in group if r.is_completed)
            card_layout.addWidget(self._rap_dot_row(label, dots, done, len(group)))

        named_special = sum(
            1 for r in races
            if r.offering_chapter is None
            and r.chapter in (career_progress.CHALLENGE_CHAPTER,) + tuple(
                career_progress.SPECIAL_CHAPTERS
            )
        )
        unnamed = sum(1 for r in races if r.event_id is None)
        footnote = QLabel(
            "Key icons at the end of a row are boss races — the game's "
            "per-chapter race counter (and the row chip) excludes them. "
            f"+ {named_special} challenge/special events and {unnamed} unnamed "
            "slots carry no career progression state."
        )
        footnote.setObjectName("rapFootnote")
        footnote.setWordWrap(True)
        card_layout.addWidget(footnote)
        return card

    def _rap_race_dot(
        self, record: career_progress.RaceRecord, *, boss_race: bool = False
    ) -> QFrame:
        suffix = " (reversed)" if record.is_reversed else ""
        route_id = rival_challenge.ROUTE_REMAP.get(
            record.event_id or "", record.event_id
        )
        name = race_display_names.display_name(route_id)
        type_label = race_display_names.type_label(route_id) or "Event"
        prefix = "Boss race — " if boss_race else ""
        title = f"{prefix}{name or f'Event {record.event_id}'}{suffix}"
        kind_line = f"\n{type_label} · {record.event_id}"
        if record.is_completed:
            state = "done"
            best = _race_best_result(record, type_label)
            tooltip = (
                f"{title} — completed{f' · best {best}' if best else ''}\n"
                f"top {record.top_speed:.1f} · avg {record.average_speed:.1f}"
                f"{kind_line}"
            )
        elif record.flags & career_progress.RACE_FLAG_UNLOCKED_CAREER:
            state = "open"
            tooltip = f"{title} — available{kind_line}"
        else:
            state = "locked"
            tooltip = f"{title} — locked{kind_line}"
        return self._rap_dot(state, tooltip, kind="race", boss=boss_race)

    # ── Library / list state ───────────────────────────────────

    def _career_donor_directory_signature(self) -> tuple:
        root = Path(self.career_donor_root)
        if not root.is_dir():
            return ()
        entries = []
        try:
            for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file():
                    continue
                stat = path.stat()
                entries.append((path.name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            return ()
        return tuple(entries)

    def _reload_career_donor_library(self, *, force: bool = False) -> None:
        signature = self._career_donor_directory_signature()
        if not force and signature == self._career_donor_signature:
            return
        try:
            self.career_donor_library = load_career_donor_library(self.career_donor_root)
        except Exception:
            self.career_donor_library = ()
        self._career_donor_signature = signature

    def _career_selected_variant(self) -> str:
        if self.career_variant_switch.currentIndex() == 1:
            return VARIANT_BOSS_READY
        return VARIANT_CHAPTER_START

    def _career_donors_for_variant(self, variant: str) -> Dict[int, CareerDonorEntry]:
        donors: Dict[int, CareerDonorEntry] = {}
        for entry in self.career_donor_library:
            if entry.is_loadable and entry.variant == variant and entry.stage_bin not in donors:
                donors[entry.stage_bin] = entry
        return donors

    def _rebuild_career_stage_list(
        self, *, preferred_stage: Optional[int] = None
    ) -> None:
        selected_stage = (
            preferred_stage
            if preferred_stage is not None
            else self._selected_career_stage()
        )
        donors = self._career_donors_for_variant(self._career_selected_variant())
        if selected_stage not in donors:
            current = (
                career_transplant.read_current_bin(bytes(self.savefile.data))
                if self.savefile is not None else None
            )
            selected_stage = (
                current
                if current in donors
                else (max(donors) if donors and self.savefile is not None else None)
            )
        for stage, button in self.career_stage_buttons.items():
            button.blockSignals(True)
            available = stage in donors
            button.setEnabled(available)
            button.setChecked(available and stage == selected_stage)
            button.setToolTip(
                "" if available else "No donor save for this stage in the library"
            )
            button.blockSignals(False)
        variant_label = (
            "boss-ready" if self._career_selected_variant() == VARIANT_BOSS_READY
            else "chapter-start"
        )
        self.career_library_status.setText(
            f"{len(donors)} / 15 {variant_label} donor snapshots ready"
        )

    def _selected_career_stage(self) -> Optional[int]:
        for stage, button in self.career_stage_buttons.items():
            if button.isChecked() and button.isEnabled():
                return stage
        return None

    def _selected_career_donor(self) -> Optional[CareerDonorEntry]:
        stage = self._selected_career_stage()
        if stage is None:
            return None
        return self._career_donors_for_variant(self._career_selected_variant()).get(stage)

    def _on_career_stage_toggled(self, _stage: int, checked: bool) -> None:
        if checked:
            snapshot = self._career_crossfade_snapshot(
                self.career_review_panel, "_career_review_transition"
            )
            self._refresh_career_preview()
            self._start_career_crossfade(
                self.career_review_panel,
                snapshot,
                "_career_review_transition",
                "careerReviewTransitionOverlay",
            )

    def _clear_career_crossfade(self, transition_attribute: str) -> None:
        overlay = getattr(self, transition_attribute, None)
        setattr(self, transition_attribute, None)
        if overlay is not None:
            overlay.finish_immediately()

    def _career_crossfade_snapshot(
        self, widget: QWidget, transition_attribute: str
    ) -> QPixmap:
        self._clear_career_crossfade(transition_attribute)
        if not widget.isVisible() or widget.size().isEmpty():
            return QPixmap()
        return widget.grab()

    def _start_career_crossfade(
        self,
        widget: QWidget,
        snapshot: QPixmap,
        transition_attribute: str,
        object_name: str,
    ) -> None:
        if snapshot.isNull() or snapshot.size().isEmpty():
            return
        overlay = ThemeTransitionOverlay(
            widget,
            snapshot,
            duration_ms=_CAREER_CROSSFADE_MS,
        )
        overlay.setObjectName(object_name)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.destroyed.connect(
            lambda _obj=None, overlay=overlay, attr=transition_attribute: (
                setattr(self, attr, None)
                if getattr(self, attr, None) is overlay
                else None
            )
        )
        setattr(self, transition_attribute, overlay)
        overlay.start()

    # ── Refresh / preview ──────────────────────────────────────

    def _refresh_career_page(self) -> None:
        data = bytes(self.savefile.data) if self.savefile is not None else b""
        current_bin = career_transplant.read_current_bin(data)
        if current_bin is None:
            self.career_hero.set_stage(None)
            self.career_stage_value.setText("-")
            self.career_boss_value.setText("NO SAVE LOADED")
            self.career_rivals_value.setText("-")
            self.career_races_value.setText("-")
            self.career_milestones_value.setText("-")
        else:
            endgame = bool(career_progress.is_endgame(data))
            self.career_hero.set_stage(current_bin)
            self.career_stage_value.setText(f"#{current_bin}")
            if endgame:
                self.career_boss_value.setText("BLACKLIST CLEARED")
                self.career_rivals_value.setText("15 / 15")
            else:
                boss = BLACKLIST_BOSS_NAMES.get(current_bin, "Unknown")
                self.career_boss_value.setText(boss.upper())
                defeated = max(0, 15 - current_bin)
                self.career_rivals_value.setText(f"{defeated} / 15")
            races = career_progress.parse_races(data)
            if races is None:
                self.career_races_value.setText("-")
            else:
                # Same career-event scope as the rap sheet card (offering map
                # + prologue), so the tile and the card can never disagree.
                career_events = [
                    r for r in races
                    if r.offering_chapter is not None
                    or r.chapter == career_progress.PROLOGUE_CHAPTER
                ]
                done = sum(1 for r in career_events if r.is_completed)
                self.career_races_value.setText(f"{done} / {len(career_events)}")
            milestones = career_progress.parse_milestones(data)
            traps = career_progress.parse_speedtraps(data) or ()
            if milestones is None:
                self.career_milestones_value.setText("-")
            else:
                awarded = (
                    sum(1 for m in milestones if m.is_awarded)
                    + sum(1 for t in traps if t.is_complete)
                )
                total = len(milestones) + len(traps)
                self.career_milestones_value.setText(f"{awarded} / {total}")
        self._reload_career_donor_library()
        self._rebuild_career_stage_list()
        for stage, button in self.career_stage_buttons.items():
            is_current = current_bin is not None and stage == current_bin
            if button.property("current") != is_current:
                button.setProperty("current", is_current)
                button.style().unpolish(button)
                button.style().polish(button)
        self._refresh_career_preview()
        self._refresh_rap_sheet()

    def _on_career_variant_changed(self, checked: bool = False) -> None:
        if not checked:
            return
        self._rebuild_career_stage_list()
        self._refresh_career_preview()

    def _refresh_career_page(self) -> None:
        data = bytes(self.savefile.data) if self.savefile is not None else b""
        previous = self._career_summary_cache
        snapshot_changed = data != self._career_snapshot_cache
        if snapshot_changed:
            self._career_snapshot_cache = data
            self._career_summary_cache = career_progress.build_career_progress(data)
        summary = self._career_summary_cache
        if summary is None:
            self._career_selected_stage = None
        elif (
            self._career_selected_stage is None
            or previous is None
            or previous.current_stage != summary.current_stage
            or previous.endgame != summary.endgame
        ):
            self._career_selected_stage = summary.default_stage

        self._refresh_career_progress(summary, animate=False)
        self._reload_career_donor_library()
        current_bin = summary.current_stage if summary is not None else None
        self._rebuild_career_stage_list(
            preferred_stage=current_bin if snapshot_changed else None
        )
        for stage, button in self.career_stage_buttons.items():
            is_current = current_bin is not None and stage == current_bin
            if button.property("current") != is_current:
                button.setProperty("current", is_current)
                button.style().unpolish(button)
                button.style().polish(button)
        self._refresh_career_preview()

    def _on_career_variant_changed(self, _index: int) -> None:
        self._rebuild_career_stage_list()
        self._refresh_career_preview()

    def _career_block_reason(self) -> Optional[str]:
        if self.savefile is None:
            return "Open a save first."
        if self._has_pending_changes():
            return "Apply or Reset pending edits first."
        if self._selected_career_donor() is None:
            return "Pick a target stage with an available donor."
        return None

    def _refresh_career_preview(self) -> None:
        lines: List[str] = []
        donor = self._selected_career_donor()
        block_reason = self._career_block_reason()
        current = (
            career_transplant.read_current_bin(bytes(self.savefile.data))
            if self.savefile is not None else None
        )
        self.career_route_from.setText(
            _stage_title(current).replace(":", "").upper()
            if current is not None else "OPEN A SAVE"
        )
        self.career_route_to.setText(
            _stage_title(donor.stage_bin).replace(":", "").upper()
            if donor is not None else "SELECT TARGET"
        )
        state = "idle"
        can_apply = block_reason is None

        if donor is not None and self.savefile is not None:
            try:
                donor_data = Path(donor.save_path).read_bytes()
                plan = self.savefile.plan_career_transplant(donor_data)
            except Exception as exc:
                lines.append(f"Donor could not be read: {exc}")
                state = "blocked"
                can_apply = False
            else:
                if plan.refusal_reason:
                    lines.append(f"Refused: {plan.refusal_reason}")
                    state = "blocked"
                    can_apply = False
                else:
                    lines.append(
                        f"{_display_name_text(donor.display_name)} is ready. "
                        "The profile will change in memory only."
                    )
                    state = "ready"
                    if current == plan.donor_bin:
                        lines.append("Same stage: this resets the chapter's progress.")
                        state = "warning"
                    if plan.bounty_compensation > 0:
                        lines.append(
                            f"Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history."
                        )
                    if plan.warnings:
                        state = "warning"
                        lines.extend(f"Warning: {w}" for w in plan.warnings)
        if block_reason:
            if self.savefile is None:
                lines.append("Open a save before building a stage-change plan.")
            elif donor is None:
                lines.append("Choose a target stage to assemble the transplant plan.")
            else:
                lines.append(block_reason)
            state = "blocked" if self.savefile is None or self._has_pending_changes() else "idle"

        self.career_preview_status.setText("\n".join(lines))
        self.career_preview_status.setProperty("state", state)
        self.career_preview_status.style().unpolish(self.career_preview_status)
        self.career_preview_status.style().polish(self.career_preview_status)
        self.btn_career_transplant.setEnabled(can_apply)

    # ── Apply ──────────────────────────────────────────────────

    def _on_career_transplant_clicked(self) -> None:
        donor = self._selected_career_donor()
        if donor is None or self.savefile is None:
            return
        try:
            donor_data = Path(donor.save_path).read_bytes()
            plan = self.savefile.plan_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Stage change failed", str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, "Stage change blocked", plan.refusal_reason)
            self._refresh_career_preview()
            return

        current = career_transplant.read_current_bin(bytes(self.savefile.data))
        warning_lines = "".join(f"\n- {w}" for w in plan.warnings)
        if plan.bounty_compensation > 0:
            warning_lines += (
                f"\n- Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history"
            )
        answer = QMessageBox.question(
            self,
            "Confirm career stage change",
            (
                f"Change career progression in memory?\n\n"
                f"{_stage_title(current)}  ->  {_stage_title(plan.donor_bin)}\n"
                f"Target snapshot: {_display_name_text(donor.display_name)}\n\n"
                f"{_CHANGES_TEXT}\n{_KEEPS_TEXT}\n\n"
                f"This edits memory only; use Save + backup to write the file."
                f"{warning_lines}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        hero_snapshot = self._career_crossfade_snapshot(
            self.career_hero, "_career_hero_transition"
        )
        try:
            self.savefile.apply_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Stage change failed", str(exc))
            return

        self._reset_want_edit_state()
        self.refresh_state()
        self._start_career_crossfade(
            self.career_hero,
            hero_snapshot,
            "_career_hero_transition",
            "careerHeroTransitionOverlay",
        )
        ToastNotification.show_toast(
            self, "Career stage changed in memory. Save + backup to write"
        )
