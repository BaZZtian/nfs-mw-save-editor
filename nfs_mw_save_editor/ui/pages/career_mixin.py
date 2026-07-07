"""Career page: current progression overview + career stage transplant.

Interaction contract (agreed 2026-07-07, see AGENT_CONTEXT.md):
- Transplant is immediate-with-confirm and writes to the in-memory buffer
  only, mirroring the app's "Apply (memory) -> Save + backup" model. The
  actual disk write stays with the standard Save + backup button.
- The transplant button is disabled while any staged edit is pending, so
  staged want-values can never race the transplanted have-values.
- After a transplant the staged state is reset and the whole UI refreshes
  through the same path used after opening a file.

The page hosts two views behind a segmented switch: the transplant view
(above contract) and the read-only "Rap Sheet" progress dossier (blacklist
board, milestone table, race table). The rap sheet performs no writes; it is
rebuilt from the in-memory buffer on every refresh, milestones parsed via the
cellusage anchor (core/career_progress.py), never via fixed offsets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import career_progress, career_transplant
from core.career_donor_library import (
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    CareerDonorEntry,
    default_user_career_donor_root,
    load_career_donor_library,
)
from ui.icon_map import game_icon_path
from ui.pages.constants import BLACKLIST_BOSS_NAMES
from ui.theme import resolve_theme_tokens
from ui.widgets import ToastNotification

_STAGE_ROLE = Qt.UserRole
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
_RAP_BOSS_DOT_SIZE = 17
_RAP_TRAP_DOT_SIZE = 17


def _stage_title(stage: int) -> str:
    boss = BLACKLIST_BOSS_NAMES.get(stage)
    return f"#{stage}: {boss}" if boss else f"#{stage}"


def _display_name_text(text: str) -> str:
    return text.replace(" — ", ": ")


def _fmt_num(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


def _event_sort_key(record: career_progress.RaceRecord) -> Tuple[int, int, int]:
    parts = (record.event_id or "").split(".")
    try:
        return (int(parts[1]), int(parts[2]), 1 if record.is_reversed else 0)
    except (IndexError, ValueError):
        return (99, record.index, 0)


class _RapMarker(QFrame):
    """Theme-aware progress marker for the Rap Sheet dot matrices."""

    _source_cache: Dict[str, QImage] = {}
    _tint_cache: Dict[Tuple[str, int], QImage] = {}

    def __init__(self, shape: str, icon_path: Optional[Path] = None) -> None:
        super().__init__()
        self._shape = shape
        self._icon_path = str(icon_path) if icon_path is not None else None
        self.setObjectName("rapDot")
        self.setAttribute(Qt.WA_TranslucentBackground)

    @classmethod
    def _source_image(cls, path: str) -> QImage:
        image = cls._source_cache.get(path)
        if image is None:
            image = QImage(path).convertToFormat(QImage.Format_ARGB32)
            cls._source_cache[path] = image
        return image

    @classmethod
    def _tinted_image(cls, path: str, color: QColor) -> QImage:
        key = (path, int(color.rgba()))
        cached = cls._tint_cache.get(key)
        if cached is not None:
            return cached

        source = cls._source_image(path)
        tinted = QImage(source.size(), QImage.Format_ARGB32)
        tinted.fill(Qt.transparent)
        for y in range(source.height()):
            for x in range(source.width()):
                pixel = source.pixelColor(x, y)
                alpha = pixel.alpha()
                if alpha <= 0:
                    continue
                luminance = (
                    0.2126 * pixel.red()
                    + 0.7152 * pixel.green()
                    + 0.0722 * pixel.blue()
                )
                out = QColor(8, 8, 8) if luminance < 45 else QColor(color)
                out.setAlpha(alpha)
                tinted.setPixelColor(x, y, out)

        cls._tint_cache[key] = tinted
        return tinted

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        tokens = resolve_theme_tokens()
        state = self.property("state")
        if state == "done":
            fill = QColor(tokens["ACCENT_BRIGHT"])
            border = QColor(tokens["ACCENT_BRIGHT"])
        elif state == "open":
            fill = QColor(tokens["ACCENT_SOFT"])
            border = QColor(tokens["ACCENT"])
        else:
            fill = QColor(tokens["BG_DISABLED"])
            border = QColor(tokens["BORDER"])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._icon_path and not self._source_image(self._icon_path).isNull():
            icon = self._tinted_image(self._icon_path, border if state == "locked" else fill)
            target = QRectF(self.rect()).adjusted(0.3, 0.3, -0.3, -0.3)
            painter.drawImage(target, icon)
            return

        painter.setBrush(fill)
        pen = QPen(border)
        pen.setWidthF(1.4 if self._shape != "square" else 1.6)
        painter.setPen(pen)

        rect = QRectF(self.rect()).adjusted(1.4, 1.4, -1.4, -1.4)
        if self._shape == "triangle":
            path = QPainterPath()
            path.moveTo(QPointF(rect.center().x(), rect.top()))
            path.lineTo(QPointF(rect.right(), rect.bottom()))
            path.lineTo(QPointF(rect.left(), rect.bottom()))
            path.closeSubpath()
            painter.drawPath(path)
        elif self._shape == "square":
            painter.drawRoundedRect(rect, 2.0, 2.0)
        else:
            painter.drawEllipse(rect)


class CareerMixin:
    def _build_career_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(12)

        self.career_donor_root = default_user_career_donor_root()
        self.career_donor_library: tuple[CareerDonorEntry, ...] = ()

        # ── Read-only progression strip ────────────────────────
        strip = QHBoxLayout()
        strip.setSpacing(10)

        self.career_stage_value = QLabel("-")
        self.career_stage_value.setObjectName("statTileValue")
        self.career_stage_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.career_stage_value.setAlignment(Qt.AlignCenter)
        self.career_stage_sub = QLabel("Current blacklist stage")
        self.career_stage_sub.setObjectName("statTileSub")
        self.career_stage_sub.setAlignment(Qt.AlignCenter)
        strip.addWidget(self._build_stat_tile("Stage", self.career_stage_value, self.career_stage_sub), 1)

        self.career_races_value = QLabel("-")
        self.career_races_value.setObjectName("statTileValue")
        self.career_races_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.career_races_value.setAlignment(Qt.AlignCenter)
        self.career_races_sub = QLabel("Completed career events, prologue included")
        self.career_races_sub.setObjectName("statTileSub")
        self.career_races_sub.setAlignment(Qt.AlignCenter)
        strip.addWidget(self._build_stat_tile("Races done", self.career_races_value, self.career_races_sub), 1)

        self.career_milestones_value = QLabel("-")
        self.career_milestones_value.setObjectName("statTileValue")
        self.career_milestones_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.career_milestones_value.setAlignment(Qt.AlignCenter)
        self.career_milestones_sub = QLabel("Milestones awarded")
        self.career_milestones_sub.setObjectName("statTileSub")
        self.career_milestones_sub.setAlignment(Qt.AlignCenter)
        strip.addWidget(self._build_stat_tile("Milestones", self.career_milestones_value, self.career_milestones_sub), 1)

        layout.addLayout(strip)

        # ── View switch: Transplant | Rap Sheet ────────────────
        switch_row = QHBoxLayout()
        switch_row.setSpacing(8)
        self.career_view_transplant_btn = self._make_card_action_button(
            "TRANSPLANT", object_name="careerViewTab"
        )
        self.career_view_rapsheet_btn = self._make_card_action_button(
            "RAP SHEET", object_name="careerViewTab"
        )
        for btn in (self.career_view_transplant_btn, self.career_view_rapsheet_btn):
            btn.setCheckable(True)
        self.career_view_transplant_btn.setChecked(True)
        group = QButtonGroup(w)
        group.setExclusive(True)
        group.addButton(self.career_view_transplant_btn)
        group.addButton(self.career_view_rapsheet_btn)
        switch_row.addStretch(1)
        switch_row.addWidget(self.career_view_transplant_btn)
        switch_row.addWidget(self.career_view_rapsheet_btn)
        switch_row.addStretch(1)
        layout.addLayout(switch_row)

        self.career_view_stack = QStackedWidget()
        self.career_view_stack.addWidget(self._build_career_transplant_view())
        self.career_view_stack.addWidget(self._build_career_rap_sheet_view())
        self.career_view_rapsheet_btn.toggled.connect(
            lambda checked: self.career_view_stack.setCurrentIndex(1 if checked else 0)
        )
        layout.addWidget(self.career_view_stack, 1)

        self._reload_career_donor_library()
        self._rebuild_career_stage_list()
        self._refresh_career_preview()
        self._refresh_rap_sheet()
        return w

    def _build_career_transplant_view(self) -> QWidget:
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        card, card_layout = self._make_card_frame(vertical_policy=QSizePolicy.Expanding)

        title = self._make_card_field_label("Career stage transplant")
        card_layout.addWidget(title)

        intro = QLabel(
            "Move your profile to another blacklist stage by transplanting the "
            "career progression from a known-good donor save. Your property is untouched."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(intro)

        variant_row = QHBoxLayout()
        variant_row.setSpacing(12)
        self.career_variant_start = QRadioButton("Chapter start")
        self.career_variant_ready = QRadioButton("Boss fight ready")
        self.career_variant_start.setObjectName("careerVariantRadio")
        self.career_variant_ready.setObjectName("careerVariantRadio")
        self.career_variant_start.setChecked(True)
        self.career_variant_start.toggled.connect(self._on_career_variant_changed)
        variant_row.addStretch(1)
        variant_row.addWidget(self.career_variant_start)
        variant_row.addWidget(self.career_variant_ready)
        variant_row.addStretch(1)
        card_layout.addLayout(variant_row)

        self.career_stage_list = QListWidget()
        self.career_stage_list.setObjectName("careerStageList")
        self.career_stage_list.setUniformItemSizes(True)
        self.career_stage_list.currentItemChanged.connect(
            lambda *_: self._refresh_career_preview()
        )
        card_layout.addWidget(self.career_stage_list, 1)

        card_layout.addWidget(self._make_card_separator())

        self.career_preview_status = QLabel("")
        self.career_preview_status.setObjectName("contentCardMeta")
        self.career_preview_status.setWordWrap(True)
        self.career_preview_status.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_status)

        self.career_preview_changes = QLabel(_CHANGES_TEXT)
        self.career_preview_changes.setObjectName("contentCardNote")
        self.career_preview_changes.setWordWrap(True)
        self.career_preview_changes.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_changes)

        self.career_preview_keeps = QLabel(_KEEPS_TEXT)
        self.career_preview_keeps.setObjectName("contentCardNote")
        self.career_preview_keeps.setWordWrap(True)
        self.career_preview_keeps.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_keeps)

        self.career_preview_caveat = QLabel(_BOUNTY_CAVEAT_TEXT)
        self.career_preview_caveat.setObjectName("contentCardNote")
        self.career_preview_caveat.setWordWrap(True)
        self.career_preview_caveat.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_caveat)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.btn_career_transplant = self._make_card_action_button("Transplant (memory)")
        self.btn_career_transplant.clicked.connect(self._on_career_transplant_clicked)
        action_row.addWidget(self.btn_career_transplant)
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        layout.addWidget(card, 1)
        return view

    # ── Rap Sheet view (read-only dossier) ─────────────────────

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
        self.rap_sheet_layout.addWidget(self._build_rap_milestones_card(milestones, speedtraps))
        self.rap_sheet_layout.addWidget(self._build_rap_races_card(races))
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
        card, card_layout = self._make_card_frame()
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self._make_card_field_label(title))
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
        elif kind in ("milestone", "trap"):
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
        label.setMinimumWidth(110)
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
        card, card_layout = self._rap_card("BLACKLIST", defeated, len(stages))

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
        prefix = "Boss race — route " if boss_race else "Event "
        title = f"{prefix}{record.event_id}{suffix}"
        if record.is_completed:
            state = "done"
            tooltip = (
                f"{title} — completed\n"
                f"high score {record.high_score:,}\n"
                f"top {record.top_speed:.1f} · avg {record.average_speed:.1f}"
            )
        elif record.flags & 0x10:
            state = "open"
            tooltip = f"{title} — available"
        else:
            state = "locked"
            tooltip = f"{title} — locked"
        return self._rap_dot(state, tooltip, kind="race", boss=boss_race)

    # ── Library / list state ───────────────────────────────────

    def _reload_career_donor_library(self) -> None:
        try:
            self.career_donor_library = load_career_donor_library(self.career_donor_root)
        except Exception:
            self.career_donor_library = ()

    def _career_selected_variant(self) -> str:
        if self.career_variant_ready.isChecked():
            return VARIANT_BOSS_READY
        return VARIANT_CHAPTER_START

    def _career_donors_for_variant(self, variant: str) -> Dict[int, CareerDonorEntry]:
        donors: Dict[int, CareerDonorEntry] = {}
        for entry in self.career_donor_library:
            if entry.is_loadable and entry.variant == variant and entry.stage_bin not in donors:
                donors[entry.stage_bin] = entry
        return donors

    def _rebuild_career_stage_list(self) -> None:
        selected_stage = None
        current = self.career_stage_list.currentItem()
        if current is not None:
            selected_stage = current.data(_STAGE_ROLE)

        donors = self._career_donors_for_variant(self._career_selected_variant())
        self.career_stage_list.blockSignals(True)
        self.career_stage_list.clear()
        for stage in range(15, 0, -1):
            item = QListWidgetItem(_stage_title(stage))
            item.setData(_STAGE_ROLE, stage)
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(0, 36))
            if stage not in donors:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
                item.setToolTip("No donor save for this stage in the library")
            self.career_stage_list.addItem(item)
            if stage == selected_stage and stage in donors:
                self.career_stage_list.setCurrentItem(item)
        self.career_stage_list.blockSignals(False)

    def _selected_career_donor(self) -> Optional[CareerDonorEntry]:
        item = self.career_stage_list.currentItem()
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return None
        stage = item.data(_STAGE_ROLE)
        return self._career_donors_for_variant(self._career_selected_variant()).get(stage)

    # ── Refresh / preview ──────────────────────────────────────

    def _refresh_career_page(self) -> None:
        data = bytes(self.savefile.data) if self.savefile is not None else b""
        current_bin = career_transplant.read_current_bin(data)
        if current_bin is None:
            self.career_stage_value.setText("-")
            self.career_races_value.setText("-")
            self.career_milestones_value.setText("-")
        else:
            if career_progress.is_endgame(data):
                self.career_stage_value.setText("Blacklist cleared")
                self.career_stage_sub.setText("Razor is down — career complete")
            else:
                self.career_stage_value.setText(_stage_title(current_bin))
                self.career_stage_sub.setText("Current blacklist stage")
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
        self._refresh_career_preview()
        self._refresh_rap_sheet()

    def _on_career_variant_changed(self, _checked: bool = False) -> None:
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

        if donor is not None and self.savefile is not None:
            try:
                donor_data = Path(donor.save_path).read_bytes()
                plan = self.savefile.plan_career_transplant(donor_data)
            except Exception as exc:
                lines.append(f"Donor could not be read: {exc}")
            else:
                if plan.refusal_reason:
                    lines.append(f"Refused: {plan.refusal_reason}")
                else:
                    current = career_transplant.read_current_bin(bytes(self.savefile.data))
                    lines.append(
                        f"Ready: {_stage_title(current)} -> {_stage_title(plan.donor_bin)}"
                        f" ({_display_name_text(donor.display_name)})"
                    )
                    if current == plan.donor_bin:
                        lines.append("Same stage: this resets the chapter's progress.")
                    if plan.bounty_compensation > 0:
                        lines.append(
                            f"Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history."
                        )
                    lines.extend(f"Warning: {w}" for w in plan.warnings)
        if block_reason:
            lines.append(block_reason)

        self.career_preview_status.setText("\n".join(lines))
        self.btn_career_transplant.setEnabled(block_reason is None)

    # ── Apply ──────────────────────────────────────────────────

    def _on_career_transplant_clicked(self) -> None:
        donor = self._selected_career_donor()
        if donor is None or self.savefile is None:
            return
        try:
            donor_data = Path(donor.save_path).read_bytes()
            plan = self.savefile.plan_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Transplant failed", str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, "Transplant refused", plan.refusal_reason)
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
            "Career stage transplant",
            (
                f"Transplant career progression?\n\n"
                f"{_stage_title(current)}  ->  {_stage_title(plan.donor_bin)}\n"
                f"Donor: {_display_name_text(donor.display_name)}\n\n"
                f"{_CHANGES_TEXT}\n{_KEEPS_TEXT}\n\n"
                f"This edits memory only; use Save + backup to write the file."
                f"{warning_lines}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.savefile.apply_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Transplant failed", str(exc))
            return

        self._reset_want_edit_state()
        self.refresh_state()
        ToastNotification.show_toast(
            self, "Career stage transplanted (memory). Save + backup to write"
        )
