from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Dict, List, Optional, Set

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.models import ResolvedMyCarsEntry, ResolvedPartsEntry
from core.savefile import SaveFile
from core.tuning_limits import PERF_PART_NAMES, get_model_tuning_limits
from ui.pages.constants import PARTS_TILE_MIN_WIDTH
from ui.rendering import ViewportLazyGridController, refresh_widget_style
from ui.widgets import WantSpinBox, build_perf_level_row

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TuningCardEntry:
    raw_entry: object
    display_name: str
    source_kind: str
    pink_slip: bool
    parts_slot: int
    block_abs_off: int
    career_slot: Optional[int]
    car_number: Optional[int]
    marker: Optional[bytes]
    confirmed_raw: Optional[bytes]
    junkman_mask: int


@dataclass(frozen=True)
class PartsCardVm:
    card_entry: TuningCardEntry
    changed: bool
    is_active: bool
    levels: Dict[str, int]
    mask: int
    statuses: List[str]
    limits: Optional[Dict[str, int]]


@dataclass
class PartsPerfRowHandle:
    num_label: QLabel
    segments: List[QFrame]
    spin: Optional[WantSpinBox]
    minus_button: Optional[QPushButton]
    plus_button: Optional[QPushButton]
    read_only_badge: Optional[QLabel] = None


@dataclass
class PartsCardHandle:
    card: QFrame
    slot_badge: QLabel
    source_badge: QLabel
    pink_slip_badge: QLabel
    active_badge: QLabel
    name_label: QLabel
    status_badges: Dict[str, QLabel]
    bulk_buttons: Dict[str, QPushButton]
    parts_badge: QLabel
    block_badge: QLabel
    career_badge: QLabel
    utility_label: QLabel
    perf_rows: Dict[str, PartsPerfRowHandle]
    junkman_buttons: Dict[str, QPushButton]
    diag_mask_label: Optional[QLabel] = None
    diag_marker_label: Optional[QLabel] = None
    diag_raw_label: Optional[QLabel] = None
    diag_raw_value: Optional[QLabel] = None
    diag_note_label: Optional[QLabel] = None


class ReusablePartsCardWidget(QFrame):
    def __init__(self, owner: "PartsMixin", *, diagnostics: bool):
        super().__init__()
        self._owner = owner
        self._diagnostics = bool(diagnostics)
        self._parts_slot: Optional[int] = None
        self._in_pool = False
        self._theme_name = owner._current_parts_theme_name()
        self.setObjectName("partsCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(360)
        self.setProperty("changed", False)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        slot_badge = owner._make_stat_badge("", "garageCardSlot")
        header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        source_badge = QLabel()
        source_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        source_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(source_badge, 0, Qt.AlignRight)
        pink_slip_badge = owner._make_garage_source_badge("Pink Slip")
        pink_slip_badge.setVisible(False)
        header_row.addWidget(pink_slip_badge, 0, Qt.AlignRight)
        active_badge = owner._make_active_car_badge()
        active_badge.setVisible(False)
        header_row.addWidget(active_badge, 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = owner._make_stat_badge("", "garageCardMeta")
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_badges: Dict[str, QLabel] = {}
        for text in ["Stock", "Modified", "Maxed", "Junkman", "Read-only"]:
            badge = owner._make_tuning_status_badge(text)
            badge.setVisible(False)
            status_badges[text] = badge
            status_row.addWidget(badge, 0, Qt.AlignLeft)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        bulk_buttons: Dict[str, QPushButton] = {}
        for text, handler in [
            ("Max Performance", owner.on_tuning_max_performance),
            ("Max Junkman", owner.on_tuning_max_junkman),
            ("Stock Build", owner.on_tuning_stock_build),
            ("Clear Junkman", owner.on_tuning_clear_junkman),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("partsBulkBtn")
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, fn=handler: self._on_bulk_action(fn))
            action_row.addWidget(btn)
            bulk_buttons[text] = btn
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        parts_badge = owner._make_stat_badge("")
        meta_row.addWidget(parts_badge, 0, Qt.AlignLeft)
        block_badge = owner._make_stat_badge("")
        meta_row.addWidget(block_badge, 0, Qt.AlignLeft)
        career_badge = owner._make_stat_badge("")
        career_badge.setVisible(False)
        meta_row.addWidget(career_badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)
        card_layout.addLayout(meta_row)

        utility_label = QLabel()
        utility_label.setObjectName("mutedLabel")
        utility_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card_layout.addWidget(utility_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("garageCardSep")
        card_layout.addWidget(sep)
        perf_label = QLabel("Performance")
        perf_label.setObjectName("garageCardFieldLabel")
        perf_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(perf_label)
        perf_rows = self._build_perf_grid(card_layout)
        junkman_label = QLabel("Junkman")
        junkman_label.setObjectName("garageCardFieldLabel")
        junkman_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(junkman_label)
        junkman_buttons = self._build_junkman_row(card_layout)

        diag_mask_label: Optional[QLabel] = None
        diag_marker_label: Optional[QLabel] = None
        diag_raw_label: Optional[QLabel] = None
        diag_raw_value: Optional[QLabel] = None
        diag_note_label: Optional[QLabel] = None
        if self._diagnostics:
            diag_sep = QFrame()
            diag_sep.setFrameShape(QFrame.HLine)
            diag_sep.setObjectName("garageCardSep")
            card_layout.addWidget(diag_sep)
            diag_label = QLabel("Diagnostics")
            diag_label.setObjectName("garageCardFieldLabel")
            diag_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(diag_label)
            diag_mask_label = owner._make_stat_badge("Mask 0x00")
            card_layout.addWidget(diag_mask_label, 0, Qt.AlignLeft)
            diag_marker_label = owner._make_stat_badge("")
            diag_marker_label.setVisible(False)
            card_layout.addWidget(diag_marker_label, 0, Qt.AlignLeft)
            diag_raw_label = QLabel("Confirmed Slice (+0x118..+0x137)")
            diag_raw_label.setObjectName("partsCardNote")
            diag_raw_label.setAlignment(Qt.AlignCenter)
            diag_raw_label.setVisible(False)
            card_layout.addWidget(diag_raw_label)
            diag_raw_value = QLabel()
            diag_raw_value.setObjectName("partsCardRaw")
            diag_raw_value.setAlignment(Qt.AlignCenter)
            diag_raw_value.setWordWrap(True)
            diag_raw_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            diag_raw_value.setVisible(False)
            card_layout.addWidget(diag_raw_value)
            diag_note_label = QLabel("This source type does not expose a confirmed raw diagnostic slice.")
            diag_note_label.setObjectName("partsCardNote")
            diag_note_label.setWordWrap(True)
            diag_note_label.setVisible(False)
            card_layout.addWidget(diag_note_label)

        self.handle = PartsCardHandle(
            card=self,
            slot_badge=slot_badge,
            source_badge=source_badge,
            pink_slip_badge=pink_slip_badge,
            active_badge=active_badge,
            name_label=name_label,
            status_badges=status_badges,
            bulk_buttons=bulk_buttons,
            parts_badge=parts_badge,
            block_badge=block_badge,
            career_badge=career_badge,
            utility_label=utility_label,
            perf_rows=perf_rows,
            junkman_buttons=junkman_buttons,
            diag_mask_label=diag_mask_label,
            diag_marker_label=diag_marker_label,
            diag_raw_label=diag_raw_label,
            diag_raw_value=diag_raw_value,
            diag_note_label=diag_note_label,
        )
        owner._reset_parts_card_handle(self.handle)

    def diagnostics_mode(self) -> bool:
        return self._diagnostics

    def current_parts_slot(self) -> Optional[int]:
        return self._parts_slot

    def is_pooled(self) -> bool:
        return self._in_pool

    def apply_vm(self, vm: PartsCardVm) -> None:
        self._in_pool = False
        self._parts_slot = vm.card_entry.parts_slot
        self._owner._apply_parts_card_vm(self.handle, vm)
        self._theme_name = self._owner._current_parts_theme_name()

    def ensure_theme(self, theme_name: str) -> None:
        if self._theme_name == theme_name:
            return
        self.repolish_for_theme(theme_name)

    def repolish_for_theme(self, theme_name: str) -> None:
        self._owner._refresh_parts_widget_tree(self)
        self._theme_name = theme_name

    def prepare_for_pool(self, theme_name: str) -> None:
        self._owner._reset_parts_card_handle(self.handle)
        self._parts_slot = None
        self._theme_name = theme_name
        self._in_pool = True
        self.hide()
        self.setParent(None)

    def _build_perf_grid(self, parent: QVBoxLayout) -> Dict[str, PartsPerfRowHandle]:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        handles: Dict[str, PartsPerfRowHandle] = {}
        for idx, name in enumerate(PERF_PART_NAMES):
            row_w = QWidget()
            row_w.setObjectName("partsLevelRow")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(name)
            lbl.setObjectName("partsLevelLabel")
            row_layout.addWidget(lbl)

            segments: List[QFrame] = []
            for _ in range(4):
                seg = QFrame()
                seg.setObjectName("partsLevelSeg")
                seg.setProperty("filled", "0")
                seg.setFixedSize(20, 8)
                row_layout.addWidget(seg)
                segments.append(seg)

            num_label = QLabel("0/?")
            num_label.setObjectName("partsLevelNum")
            row_layout.addWidget(num_label)

            read_only_badge = self._owner._make_stat_badge("Read-only")
            read_only_badge.setVisible(False)
            row_layout.addWidget(read_only_badge)

            btn_minus = QPushButton("-")
            btn_minus.setObjectName("partsLevelBtn")
            btn_minus.setFixedSize(24, 24)
            btn_minus.clicked.connect(lambda _, part=name: self._bump_perf_spin(part, -1))
            row_layout.addWidget(btn_minus)

            spin = WantSpinBox()
            spin.setObjectName("partsLevelSpin")
            spin.setRange(0, 4)
            spin.setValue(0)
            spin.setAlignment(Qt.AlignCenter)
            spin.setButtonSymbols(WantSpinBox.NoButtons)
            spin.valueChanged.connect(lambda val, part=name: self._on_perf_spin_changed(part, val))
            row_layout.addWidget(spin)

            btn_plus = QPushButton("+")
            btn_plus.setObjectName("partsLevelBtn")
            btn_plus.setFixedSize(24, 24)
            btn_plus.clicked.connect(lambda _, part=name: self._bump_perf_spin(part, 1))
            row_layout.addWidget(btn_plus)

            grid.addWidget(row_w, idx // 2, idx % 2)
            handles[name] = PartsPerfRowHandle(
                num_label=num_label,
                segments=segments,
                spin=spin,
                minus_button=btn_minus,
                plus_button=btn_plus,
                read_only_badge=read_only_badge,
            )
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)
        return handles

    def _build_junkman_row(self, parent: QVBoxLayout) -> Dict[str, QPushButton]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        buttons: Dict[str, QPushButton] = {}
        for _, cat in SaveFile.JUNKMAN_MASK_BITS:
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setChecked(False)
            btn.setEnabled(False)
            btn.setObjectName("partsJunkmanToggle")
            btn.setProperty("active", False)
            btn.clicked.connect(
                lambda checked, category=cat: self._on_junkman_toggled(category, checked),
            )
            refresh_widget_style(btn)
            row.addWidget(btn, 0, Qt.AlignLeft)
            buttons[cat] = btn
        row.addStretch(1)
        parent.addLayout(row)
        return buttons

    def _on_perf_spin_changed(self, part_name: str, value: int) -> None:
        if self._parts_slot is None:
            return
        self._owner.on_parts_level_changed(self._parts_slot, part_name, int(value))

    def _bump_perf_spin(self, part_name: str, delta: int) -> None:
        handle = self.handle.perf_rows.get(part_name)
        spin = None if handle is None else handle.spin
        if spin is None:
            return
        spin.setValue(max(spin.minimum(), min(spin.maximum(), spin.value() + int(delta))))

    def _on_junkman_toggled(self, category: str, checked: bool) -> None:
        if self._parts_slot is None:
            return
        self._owner.on_parts_junkman_toggled(self._parts_slot, category, checked)

    def _on_bulk_action(self, handler) -> None:
        if self._parts_slot is None:
            return
        handler(self._parts_slot)


class PartsMixin:
    def _build_parts_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)
        hint = QLabel("Tune Career and My Cars builds in one place. Changes stay staged until you Apply.")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.parts_search = QLineEdit()
        self.parts_search.setPlaceholderText("Search cars by model name...")
        self.parts_search.textChanged.connect(self.on_parts_search_changed)
        controls.addWidget(self.parts_search, 1)
        self.chk_show_parts_diagnostics = QCheckBox("Show tuning diagnostics")
        self.chk_show_parts_diagnostics.stateChanged.connect(self.on_toggle_parts_diagnostics)
        controls.addWidget(self.chk_show_parts_diagnostics, 0)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.tuning_filter_buttons: Dict[str, QPushButton] = {}
        self.tuning_filter_group = QButtonGroup(self)
        self.tuning_filter_group.setExclusive(True)
        for label in ["All", "Career", "My Cars"]:
            btn = QPushButton(label)
            btn.setObjectName("catButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, source=label: self._select_tuning_filter(source))
            self.tuning_filter_group.addButton(btn)
            self.tuning_filter_buttons[label] = btn
            filter_row.addWidget(btn)
        self.tuning_filter_buttons["All"].setChecked(True)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.parts_cards = QWidget()
        self.parts_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.parts_cards_layout = QGridLayout(self.parts_cards)
        self.parts_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.parts_cards_layout.setHorizontalSpacing(14)
        self.parts_cards_layout.setVerticalSpacing(14)
        self.parts_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.parts_cards_scroll = QScrollArea()
        self.parts_cards_scroll.setObjectName("cardScroll")
        self.parts_cards_scroll.setWidgetResizable(True)
        self.parts_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.parts_cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.parts_cards_scroll.setWidget(self.parts_cards)
        layout.addWidget(self.parts_cards_scroll, 1)

        self._parts_card_widgets: Dict[int, QFrame] = {}
        self._parts_card_handles: Dict[int, PartsCardHandle] = {}
        self._parts_visible_order: List[int] = []
        self._parts_live_vm_map: Dict[int, PartsCardVm] = {}
        self._parts_card_pool: Dict[bool, List[ReusablePartsCardWidget]] = {False: [], True: []}
        self._parts_pool_target = 8
        self._parts_pool_prewarm_requested = False
        self._parts_pool_prewarm_mode = False
        self._parts_pool_prewarm_timer = QTimer(self)
        self._parts_pool_prewarm_timer.setSingleShot(True)
        self._parts_pool_prewarm_timer.timeout.connect(self._on_parts_pool_prewarm_timeout)
        self._parts_render_controller = ViewportLazyGridController(
            self,
            name="Tuning",
            layout=self.parts_cards_layout,
            scroll_area=self.parts_cards_scroll,
            release_widget=self._release_parts_card_widget,
        )
        return w

    def _parts_page_visible(self) -> bool:
        return hasattr(self, "stack") and hasattr(self, "page_parts") and self.stack.currentWidget() is self.page_parts

    def _current_parts_theme_name(self) -> str:
        app = QApplication.instance()
        app_theme = app.property("themeName") if app is not None else None
        if isinstance(app_theme, str) and app_theme:
            return app_theme
        theme_name = getattr(self, "theme_name", "")
        return theme_name if isinstance(theme_name, str) else ""

    def _refresh_parts_widget_tree(self, widget: QWidget) -> None:
        refresh_widget_style(widget)
        for child in widget.findChildren(QWidget):
            refresh_widget_style(child)
            child.update()
        widget.update()

    def _parts_pool_bucket(self, diagnostics: bool) -> List[ReusablePartsCardWidget]:
        return self._parts_card_pool[bool(diagnostics)]

    def _create_parts_card_widget(self, *, diagnostics: bool) -> ReusablePartsCardWidget:
        card = ReusablePartsCardWidget(self, diagnostics=diagnostics)
        logger.debug("Tuning pool allocate: diagnostics=%s", diagnostics)
        return card

    def _acquire_parts_card_widget(self, *, diagnostics: bool) -> ReusablePartsCardWidget:
        bucket = self._parts_pool_bucket(diagnostics)
        if bucket:
            card = bucket.pop()
            logger.debug("Tuning pool acquire: hit (diagnostics=%s, %d remain)", diagnostics, len(bucket))
        else:
            card = self._create_parts_card_widget(diagnostics=diagnostics)
            logger.debug("Tuning pool acquire: miss (diagnostics=%s)", diagnostics)
        card.ensure_theme(self._current_parts_theme_name())
        return card

    def _release_parts_card_widget(self, widget: QWidget) -> None:
        if not isinstance(widget, ReusablePartsCardWidget):
            widget.deleteLater()
            return
        if widget.is_pooled():
            return
        parts_slot = widget.current_parts_slot()
        if parts_slot is not None:
            self._parts_card_widgets.pop(parts_slot, None)
            self._parts_card_handles.pop(parts_slot, None)
        theme_name = self._current_parts_theme_name()
        widget.prepare_for_pool(theme_name)
        bucket = self._parts_pool_bucket(widget.diagnostics_mode())
        bucket.append(widget)
        logger.debug(
            "Tuning pool release: slot=%s, diagnostics=%s, pooled=%d",
            parts_slot if parts_slot is not None else "n/a",
            widget.diagnostics_mode(),
            len(bucket),
        )

    def _parts_pool_reached_target(self, diagnostics: bool) -> bool:
        return len(self._parts_pool_bucket(diagnostics)) >= self._parts_pool_target

    def _is_any_heavy_renderer_active(self) -> bool:
        for attr in (
            "_garage_render_controller",
            "_parts_render_controller",
            "_snapshot_library_render_controller",
            "_snapshot_render_controller",
        ):
            controller = getattr(self, attr, None)
            if controller is not None and getattr(controller, "is_rendering", False):
                return True
        return False

    def _schedule_parts_pool_prewarm(self, *, delay_ms: int = 0) -> None:
        if not hasattr(self, "_parts_pool_prewarm_timer"):
            return
        if self.savefile is None or self.parts_detection_error or self._parts_page_visible():
            self._parts_pool_prewarm_requested = False
            self._parts_pool_prewarm_timer.stop()
            return
        diagnostics = bool(self.show_parts_diagnostics)
        if self._parts_pool_reached_target(diagnostics):
            self._parts_pool_prewarm_requested = False
            self._parts_pool_prewarm_timer.stop()
            return
        self._parts_pool_prewarm_requested = True
        self._parts_pool_prewarm_mode = diagnostics
        self._parts_pool_prewarm_timer.start(max(0, int(delay_ms)))

    def _on_parts_pool_prewarm_timeout(self) -> None:
        if not self._parts_pool_prewarm_requested:
            return
        diagnostics = bool(self._parts_pool_prewarm_mode)
        if self.savefile is None or self.parts_detection_error or self._parts_page_visible():
            self._parts_pool_prewarm_requested = False
            return
        if self._is_any_heavy_renderer_active():
            self._parts_pool_prewarm_timer.start(150)
            return
        if self._parts_pool_reached_target(diagnostics):
            self._parts_pool_prewarm_requested = False
            return
        card = self._create_parts_card_widget(diagnostics=diagnostics)
        card.prepare_for_pool(self._current_parts_theme_name())
        bucket = self._parts_pool_bucket(diagnostics)
        bucket.append(card)
        logger.debug(
            "Tuning pool prewarm: %d/%d ready (diagnostics=%s)",
            len(bucket),
            self._parts_pool_target,
            diagnostics,
        )
        if len(bucket) < self._parts_pool_target:
            self._parts_pool_prewarm_timer.start(0)
        else:
            self._parts_pool_prewarm_requested = False

    def _restyle_parts_pool(self) -> None:
        theme_name = self._current_parts_theme_name()
        restyled = 0
        for bucket in self._parts_card_pool.values():
            for card in bucket:
                card.repolish_for_theme(theme_name)
                restyled += 1
        if restyled:
            logger.debug("Tuning pool restyle: %d pooled card(s) for theme %s", restyled, theme_name)

    def _on_parts_theme_changed(self) -> None:
        self._restyle_parts_pool()

    def _detect_parts_card_columns(self) -> int:
        return self._detect_col_count("parts_cards_scroll", PARTS_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_parts_rows(self, force: bool = False) -> None:
        columns = max(1, self._detect_parts_card_columns())
        if not force and columns == getattr(self, "_parts_slot_columns", 0):
            return
        self._parts_slot_columns = columns
        if self._parts_cards_dirty or not self._parts_render_controller.has_rendered_content():
            if self._parts_page_visible():
                self._refresh_parts_page(reason="reflow")
            return
        self._parts_render_controller.reflow(columns)

    def _format_parts_raw(self, raw: bytes) -> str:
        return raw.hex(" ").upper()

    def _make_stat_badge(self, text: str, object_name: str = "garageCardStatBadge") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _make_tuning_status_badge(self, text: str) -> QLabel:
        object_name = self._tuning_status_object_name(text)
        return self._make_stat_badge(text, object_name)

    def _tuning_status_object_name(self, text: str) -> str:
        return {
            "Stock": "tuningStatusStock",
            "Modified": "tuningStatusModified",
            "Maxed": "tuningStatusMaxed",
            "Junkman": "tuningStatusJunkman",
            "Read-only": "tuningStatusReadOnly",
        }.get(text, "garageCardStatBadge")

    def _normalize_tuning_entry(self, entry: object) -> TuningCardEntry:
        if isinstance(entry, ResolvedPartsEntry):
            return TuningCardEntry(entry, entry.display_name, "Career", entry.source_kind == "Pink Slip", entry.parts_slot, entry.block_abs_off, entry.career_slot, None, entry.marker, entry.confirmed_raw, entry.junkman_mask)
        if isinstance(entry, ResolvedMyCarsEntry):
            slot = None if entry.career_slot == SaveFile.EMPTY_CAREER_SLOT else entry.career_slot
            return TuningCardEntry(entry, entry.resolved_model_name, "My Cars", False, entry.parts_slot, entry.block_abs_off, slot, entry.car_number, None, None, entry.junkman_mask)
        raise TypeError(f"Unsupported tuning entry type: {type(entry)!r}")

    def _tuning_card_entries(self) -> List[TuningCardEntry]:
        entries = [self._normalize_tuning_entry(e) for e in list(self.parts_entries) + list(self.my_cars_entries)]
        term = self.parts_search.text().strip().lower() if hasattr(self, "parts_search") else ""
        source = getattr(self, "tuning_filter", "All")
        if term:
            entries = [e for e in entries if term in e.display_name.lower()]
        if source != "All":
            entries = [e for e in entries if e.source_kind == source]
        return entries

    def _parts_level_dict_from_entry(self, entry: ResolvedPartsEntry) -> Dict[str, int]:
        return {"Tires": entry.tires, "Brakes": entry.brakes, "Suspension": entry.suspension, "Transmission": entry.transmission, "Engine": entry.engine, "Turbo": entry.turbo, "NOS": entry.nos}

    def _parts_level_dict_from_my_car(self, entry: ResolvedMyCarsEntry) -> Dict[str, int]:
        return {"Tires": entry.tires, "Brakes": entry.brakes, "Suspension": entry.suspension, "Transmission": entry.transmission, "Engine": entry.engine, "Turbo": entry.turbo, "NOS": entry.nos}

    def _entry_model_name(self, entry) -> str:
        return entry.display_name if hasattr(entry, "display_name") else entry.resolved_model_name

    def _entry_parts_levels(self, entry) -> Dict[str, int]:
        return self._parts_level_dict_from_entry(entry) if hasattr(entry, "display_name") else self._parts_level_dict_from_my_car(entry)

    def _entry_by_parts_slot(self, parts_slot: int):
        return next((e for e in (list(self.parts_entries) + list(self.my_cars_entries)) if e.parts_slot == parts_slot), None)

    def _current_parts_levels(self) -> Dict[int, Dict[str, int]]:
        want_map = self.want_parts_levels or {}
        dedup: Dict[int, object] = {}
        for entry in list(self.parts_entries) + list(self.my_cars_entries):
            dedup[entry.parts_slot] = entry
        return {entry.parts_slot: dict(want_map.get(entry.parts_slot, self.have_parts_levels.get(entry.parts_slot, self._entry_parts_levels(entry)))) for entry in dedup.values()}

    def _current_parts_masks(self) -> Dict[int, int]:
        want_map = self.want_parts_masks or {}
        dedup: Dict[int, object] = {}
        for entry in list(self.parts_entries) + list(self.my_cars_entries):
            dedup[entry.parts_slot] = entry
        return {entry.parts_slot: int(want_map.get(entry.parts_slot, self.have_parts_masks.get(entry.parts_slot, entry.junkman_mask))) for entry in dedup.values()}

    def _parts_limits(self, entry) -> Optional[Dict[str, int]]:
        return get_model_tuning_limits(self._entry_model_name(entry))

    def _parts_card_changed(self, parts_slot: int) -> bool:
        current_levels = self._current_parts_levels().get(parts_slot, {})
        have_levels = self.have_parts_levels.get(parts_slot, {})
        if any(int(current_levels.get(name, 0)) != int(have_levels.get(name, 0)) for name in PERF_PART_NAMES):
            return True
        return int(self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))) != int(self.have_parts_masks.get(parts_slot, 0))

    def _has_parts_pending_changes(self) -> bool:
        if self.savefile is None or self.parts_detection_error:
            return False
        all_slots = {e.parts_slot for e in self.parts_entries} | {e.parts_slot for e in self.my_cars_entries}
        return any(self._parts_card_changed(parts_slot) for parts_slot in all_slots)

    def _parts_junkman_reason(self, levels: Dict[str, int], category: str) -> Optional[str]:
        if category == "Turbo" and int(levels.get("Turbo", 0)) <= 0:
            return "Requires regular Turbo > 0"
        if category == "NOS" and int(levels.get("NOS", 0)) <= 0:
            return "Requires regular NOS > 0"
        return None

    def _ensure_parts_want_maps(self) -> None:
        if self.want_parts_levels is None:
            self.want_parts_levels = {slot: dict(levels) for slot, levels in self.have_parts_levels.items()}
        if self.want_parts_masks is None:
            self.want_parts_masks = dict(self.have_parts_masks)

    def _apply_junkman_prereqs(self, levels: Dict[str, int], mask: int) -> int:
        turbo_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "Turbo"), 0)
        nos_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "NOS"), 0)
        if turbo_bit and int(levels.get("Turbo", 0)) <= 0:
            mask &= ~turbo_bit
        if nos_bit and int(levels.get("NOS", 0)) <= 0:
            mask &= ~nos_bit
        return mask

    def _set_parts_slot_levels(self, parts_slot: int, levels: Dict[str, int]) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        limits = None if entry is None else self._parts_limits(entry)
        if entry is None or limits is None:
            return
        self._ensure_parts_want_maps()
        current = dict(self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry)))
        for name in PERF_PART_NAMES:
            current[name] = max(0, min(int(levels.get(name, current.get(name, 0))), int(limits.get(name, 0))))
        assert self.want_parts_levels is not None and self.want_parts_masks is not None
        self.want_parts_levels[parts_slot] = current
        self.want_parts_masks[parts_slot] = self._apply_junkman_prereqs(current, int(self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))))

    def _set_parts_slot_mask(self, parts_slot: int, mask: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None:
            return
        self._ensure_parts_want_maps()
        assert self.want_parts_masks is not None
        self.want_parts_masks[parts_slot] = self._apply_junkman_prereqs(self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry)), int(mask))

    def _parts_status_labels(self, entry) -> List[str]:
        levels = self._current_parts_levels().get(entry.parts_slot, self._entry_parts_levels(entry))
        mask = self._current_parts_masks().get(entry.parts_slot, self.have_parts_masks.get(entry.parts_slot, 0))
        labels: List[str] = []
        if all(int(levels.get(name, 0)) == 0 for name in PERF_PART_NAMES) and int(mask) == 0:
            labels.append("Stock")
        if any(int(levels.get(name, 0)) > 0 for name in PERF_PART_NAMES):
            labels.append("Modified")
        limits = self._parts_limits(entry)
        if limits is not None and all(int(levels.get(name, 0)) == int(limits.get(name, 0)) for name in PERF_PART_NAMES):
            labels.append("Maxed")
        if int(mask) != 0:
            labels.append("Junkman")
        return labels

    def _parts_empty_widget(self, _: int) -> QWidget:
        if not self.savefile:
            text = "Open a save to inspect and edit tuning builds."
        elif self.parts_detection_error:
            text = f"Tuning tools unavailable: {self.parts_detection_error}"
        else:
            text = "No tuning entries match the current search or filter."
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        return label

    def _parts_card_view_models(
        self,
        entries: Optional[List[TuningCardEntry]] = None,
    ) -> List[PartsCardVm]:
        if not self.savefile or self.parts_detection_error:
            return []
        target_entries = list(entries) if entries is not None else self._tuning_card_entries()
        current_levels = self._current_parts_levels()
        current_masks = self._current_parts_masks()
        projected_active_car_number = self.savefile.get_projected_active_career_car_number(
            location_overrides=self._current_owned_locations(),
            career_slot_overrides=self._current_owned_career_slots(),
        )
        projected_active_parts_slots: Set[int] = set()
        if projected_active_car_number is not None:
            projected_active_parts_slots = {
                int(entry.parts_slot)
                for entry in self._current_transfer_entries()
                if not entry.is_my_cars and int(entry.car_number) == int(projected_active_car_number)
            }

        view_models: List[PartsCardVm] = []
        for card_entry in target_entries:
            entry = card_entry.raw_entry
            limits = self._parts_limits(entry)
            view_models.append(
                PartsCardVm(
                    card_entry=card_entry,
                    changed=self._parts_card_changed(card_entry.parts_slot),
                    is_active=(
                        projected_active_car_number is not None
                        and card_entry.source_kind != "My Cars"
                        and (
                            (card_entry.car_number is not None and int(card_entry.car_number) == int(projected_active_car_number))
                            or int(card_entry.parts_slot) in projected_active_parts_slots
                        )
                    ),
                    levels=dict(current_levels.get(card_entry.parts_slot, self._entry_parts_levels(entry))),
                    mask=int(current_masks.get(card_entry.parts_slot, self.have_parts_masks.get(card_entry.parts_slot, 0))),
                    statuses=self._parts_status_labels(entry),
                    limits=None if limits is None else {name: int(value) for name, value in limits.items()},
                )
            )
        return view_models

    def on_parts_level_changed(self, parts_slot: int, part_name: str, value: int) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        levels = dict(self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry)))
        levels[part_name] = int(value)
        self._set_parts_slot_levels(parts_slot, levels)
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def on_parts_junkman_toggled(self, parts_slot: int, category: str, checked: bool) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == category), None)
        entry = self._entry_by_parts_slot(parts_slot)
        if bit is None or entry is None:
            return
        levels = self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry))
        if self._parts_junkman_reason(levels, category):
            return
        current = self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))
        self._set_parts_slot_mask(parts_slot, current | bit if checked else current & ~bit)
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def on_tuning_max_performance(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        limits = None if entry is None else self._parts_limits(entry)
        if limits is None:
            return
        self._set_parts_slot_levels(parts_slot, {name: int(limits.get(name, 0)) for name in PERF_PART_NAMES})
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def on_tuning_max_junkman(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        levels = self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry))
        mask = 0
        for bit, name in SaveFile.JUNKMAN_MASK_BITS:
            if self._parts_junkman_reason(levels, name) is None:
                mask |= bit
        self._set_parts_slot_mask(parts_slot, mask)
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def on_tuning_stock_build(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        self._set_parts_slot_levels(parts_slot, {name: 0 for name in PERF_PART_NAMES})
        self._set_parts_slot_mask(parts_slot, 0)
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def on_tuning_clear_junkman(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        self._set_parts_slot_mask(parts_slot, 0)
        self._parts_cards_dirty = True
        self._patch_parts_cards_in_place()
        self._update_action_states()

    def _capture_parts_perf_row_handle(
        self,
        row_w: QWidget,
        *,
        spin: Optional[WantSpinBox],
        minus_button: Optional[QPushButton],
        plus_button: Optional[QPushButton],
    ) -> PartsPerfRowHandle:
        num_label = next(
            (label for label in row_w.findChildren(QLabel) if label.objectName() == "partsLevelNum"),
            None,
        )
        if num_label is None:
            raise ValueError("partsLevelNum label missing from perf row")
        segments = [
            frame for frame in row_w.findChildren(QFrame)
            if frame.objectName() == "partsLevelSeg"
        ]
        return PartsPerfRowHandle(
            num_label=num_label,
            segments=segments,
            spin=spin,
            minus_button=minus_button,
            plus_button=plus_button,
        )

    def _update_parts_perf_row(
        self,
        handle: PartsPerfRowHandle,
        *,
        level: int,
        max_level: Optional[int],
    ) -> None:
        handle.num_label.setText(f"{level}/{max_level}" if max_level is not None else f"{level}/?")
        for idx, seg in enumerate(handle.segments, start=1):
            seg.setVisible(max_level is not None and idx <= int(max_level))
            seg.setProperty("filled", str(idx) if level >= idx else "0")
            refresh_widget_style(seg)
        editable = handle.spin is not None and handle.minus_button is not None and handle.plus_button is not None and max_level is not None
        if handle.read_only_badge is not None:
            handle.read_only_badge.setVisible(not editable)
        if handle.spin is not None:
            handle.spin.blockSignals(True)
            handle.spin.setRange(0, int(max_level) if max_level is not None else max(int(level), 0))
            handle.spin.setValue(int(level))
            handle.spin.blockSignals(False)
            handle.spin.setVisible(editable)
            handle.spin.setEnabled(editable)
        if handle.minus_button is not None:
            handle.minus_button.setVisible(editable)
            handle.minus_button.setEnabled(editable and int(level) > 0)
        if handle.plus_button is not None:
            handle.plus_button.setVisible(editable)
            handle.plus_button.setEnabled(editable and max_level is not None and int(level) < int(max_level))
        if editable:
            if handle.minus_button is not None:
                handle.minus_button.setEnabled(int(level) > 0)
            if handle.plus_button is not None:
                handle.plus_button.setEnabled(int(level) < int(max_level))

    def _reset_parts_card_handle(self, handle: PartsCardHandle) -> None:
        handle.card.setProperty("changed", False)
        handle.slot_badge.setText("")
        handle.source_badge.setText("")
        handle.source_badge.setToolTip("")
        handle.pink_slip_badge.setVisible(False)
        handle.active_badge.setVisible(False)
        handle.name_label.setText("")
        for badge in handle.status_badges.values():
            badge.setVisible(False)
            badge.setToolTip("")
        for button in handle.bulk_buttons.values():
            button.setEnabled(False)
        handle.parts_badge.setText("")
        handle.block_badge.setText("")
        handle.career_badge.setVisible(False)
        handle.career_badge.setText("")
        handle.utility_label.clear()
        handle.utility_label.setToolTip("")
        handle.utility_label.setVisible(False)
        for perf_handle in handle.perf_rows.values():
            self._update_parts_perf_row(perf_handle, level=0, max_level=None)
        for btn in handle.junkman_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            btn.setEnabled(False)
            btn.setToolTip("")
            btn.setProperty("active", False)
            refresh_widget_style(btn)
        if handle.diag_mask_label is not None:
            handle.diag_mask_label.setText("Mask 0x00")
        if handle.diag_marker_label is not None:
            handle.diag_marker_label.setText("")
            handle.diag_marker_label.setVisible(False)
        if handle.diag_raw_label is not None:
            handle.diag_raw_label.setVisible(False)
        if handle.diag_raw_value is not None:
            handle.diag_raw_value.clear()
            handle.diag_raw_value.setVisible(False)
        if handle.diag_note_label is not None:
            handle.diag_note_label.setText("This source type does not expose a confirmed raw diagnostic slice.")
            handle.diag_note_label.setVisible(False)
        refresh_widget_style(handle.card)

    def _parts_utility_summary(self, vm: PartsCardVm) -> tuple[str, str]:
        if vm.limits is None:
            return ("", "")
        blocked = [
            f"{cat}: {reason}"
            for _, cat in SaveFile.JUNKMAN_MASK_BITS
            for reason in [self._parts_junkman_reason(vm.levels, cat)]
            if reason
        ]
        if blocked:
            short = "1 toggle blocked" if len(blocked) == 1 else f"{len(blocked)} toggles blocked"
            return short, " / ".join(blocked)
        return "All toggles ready", "All Junkman toggles are currently available."

    def _apply_parts_card_vm(self, handle: PartsCardHandle, vm: PartsCardVm) -> None:
        card_entry = vm.card_entry
        if card_entry.source_kind == "Career" and card_entry.career_slot is not None:
            slot_text = f"Career Slot {card_entry.career_slot + 1}"
        elif card_entry.car_number is not None:
            slot_text = f"Car #{card_entry.car_number:02X}"
        else:
            slot_text = f"Parts Slot {card_entry.parts_slot}"
        handle.card.setProperty("changed", vm.changed)
        handle.slot_badge.setText(slot_text)
        self._apply_garage_source_badge(handle.source_badge, card_entry.source_kind)
        handle.pink_slip_badge.setVisible(card_entry.pink_slip)
        handle.active_badge.setVisible(vm.is_active)
        handle.name_label.setText(card_entry.display_name)

        visible_statuses = set(vm.statuses)
        read_only_tooltip = "No confirmed tuning limits for this model yet. Safe mode keeps this card read-only."
        if vm.limits is None:
            visible_statuses.add("Read-only")
        for text, badge in handle.status_badges.items():
            badge.setVisible(text in visible_statuses)
            badge.setToolTip(read_only_tooltip if text == "Read-only" and vm.limits is None else "")

        for button in handle.bulk_buttons.values():
            button.setEnabled(vm.limits is not None)

        handle.parts_badge.setText(f"Parts Slot {card_entry.parts_slot}")
        handle.block_badge.setText(f"Block 0x{card_entry.block_abs_off:05X}")
        handle.career_badge.setVisible(card_entry.source_kind == "My Cars" and card_entry.career_slot is not None)
        if card_entry.career_slot is not None:
            handle.career_badge.setText(f"Career Slot {card_entry.career_slot + 1}")

        utility_text, utility_tooltip = self._parts_utility_summary(vm)
        handle.utility_label.setText(utility_text)
        handle.utility_label.setToolTip(utility_tooltip)
        handle.utility_label.setVisible(bool(utility_text))

        limits = vm.limits or {}
        for name, perf_handle in handle.perf_rows.items():
            level = int(vm.levels.get(name, 0))
            max_level = None if vm.limits is None else max(level, int(limits.get(name, 0)))
            self._update_parts_perf_row(perf_handle, level=level, max_level=max_level)

        for bit, cat in SaveFile.JUNKMAN_MASK_BITS:
            btn = handle.junkman_buttons.get(cat)
            if btn is None:
                continue
            enabled = bool(vm.mask & bit)
            reason = self._parts_junkman_reason(vm.levels, cat)
            btn.blockSignals(True)
            btn.setChecked(enabled)
            btn.blockSignals(False)
            btn.setEnabled(reason is None)
            btn.setToolTip(reason or "")
            btn.setProperty("active", enabled)
            refresh_widget_style(btn)

        if handle.diag_mask_label is not None:
            handle.diag_mask_label.setText(f"Mask 0x{vm.mask:02X}")
        if handle.diag_marker_label is not None:
            handle.diag_marker_label.setVisible(vm.card_entry.marker is not None)
            if vm.card_entry.marker is not None:
                handle.diag_marker_label.setText(f"Marker {self._format_parts_raw(vm.card_entry.marker)}")
            else:
                handle.diag_marker_label.setText("")
        if handle.diag_raw_label is not None and handle.diag_raw_value is not None:
            has_raw = vm.card_entry.confirmed_raw is not None
            handle.diag_raw_label.setVisible(has_raw)
            handle.diag_raw_value.setVisible(has_raw)
            handle.diag_raw_value.setText(
                self._format_parts_raw(vm.card_entry.confirmed_raw) if has_raw else ""
            )
        if handle.diag_note_label is not None:
            handle.diag_note_label.setVisible(vm.card_entry.confirmed_raw is None)

        refresh_widget_style(handle.card)

    def _parts_visible_vm_map(self) -> Dict[int, PartsCardVm]:
        entries_by_slot: Dict[int, TuningCardEntry] = {}
        for entry in list(self.parts_entries) + list(self.my_cars_entries):
            normalized = self._normalize_tuning_entry(entry)
            entries_by_slot[normalized.parts_slot] = normalized
        frozen_entries = [
            entries_by_slot[key]
            for key in self._parts_visible_order
            if key in entries_by_slot
        ]
        return {
            vm.card_entry.parts_slot: vm
            for vm in self._parts_card_view_models(frozen_entries)
        }

    def _patch_parts_cards_in_place(self) -> None:
        if not self._parts_page_visible():
            self._mark_parts_cards_dirty()
            return
        started = perf_counter()
        vm_map = self._parts_visible_vm_map()
        self._parts_live_vm_map.update(vm_map)
        patched = 0
        for parts_slot, handle in list(self._parts_card_handles.items()):
            vm = vm_map.get(parts_slot)
            if vm is None:
                continue
            self._apply_parts_card_vm(handle, vm)
            patched += 1
        logger.debug("Tuning interactive patch: %d card(s) in %d ms", patched, int((perf_counter() - started) * 1000))

    def _add_parts_perf_grid(self, parent: QVBoxLayout, vm: PartsCardVm) -> Dict[str, PartsPerfRowHandle]:
        card_entry = vm.card_entry
        levels = vm.levels
        limits = vm.limits
        editable = limits is not None
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        handles: Dict[str, PartsPerfRowHandle] = {}
        for idx, name in enumerate(PERF_PART_NAMES):
            level = int(levels.get(name, 0))
            max_level = max(level, int(limits.get(name, 0))) if editable else None
            row_w, row_layout = build_perf_level_row(name, level, max_level)
            btn_minus: Optional[QPushButton] = None
            spin: Optional[WantSpinBox] = None
            btn_plus: Optional[QPushButton] = None
            if editable:
                btn_minus = QPushButton("-")
                btn_minus.setObjectName("partsLevelBtn")
                btn_minus.setFixedSize(24, 24)
                spin = WantSpinBox()
                spin.setObjectName("partsLevelSpin")
                spin.setRange(0, max_level)
                spin.setValue(level)
                spin.setAlignment(Qt.AlignCenter)
                spin.setButtonSymbols(WantSpinBox.NoButtons)
                spin.valueChanged.connect(
                    lambda val, slot=card_entry.parts_slot, part=name: self.on_parts_level_changed(slot, part, val)
                )
                btn_plus = QPushButton("+")
                btn_plus.setObjectName("partsLevelBtn")
                btn_plus.setFixedSize(24, 24)
                btn_minus.clicked.connect(lambda _, s=spin: s.setValue(max(s.minimum(), s.value() - 1)))
                btn_plus.clicked.connect(lambda _, s=spin: s.setValue(min(s.maximum(), s.value() + 1)))
                row_layout.addWidget(btn_minus)
                row_layout.addWidget(spin)
                row_layout.addWidget(btn_plus)
            else:
                row_layout.addWidget(self._make_stat_badge("Read-only"))
            grid.addWidget(row_w, idx // 2, idx % 2)
            handles[name] = self._capture_parts_perf_row_handle(
                row_w,
                spin=spin,
                minus_button=btn_minus,
                plus_button=btn_plus,
            )
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)
        return handles

    def _add_parts_junkman_section(self, parent: QVBoxLayout, vm: PartsCardVm) -> Dict[str, QPushButton]:
        card_entry = vm.card_entry
        levels = vm.levels
        mask = vm.mask
        editable = vm.limits is not None
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        active_any = False
        buttons: Dict[str, QPushButton] = {}
        for bit, cat in SaveFile.JUNKMAN_MASK_BITS:
            enabled = bool(mask & bit)
            active_any = active_any or enabled
            reason = self._parts_junkman_reason(levels, cat)
            if editable:
                btn = QPushButton(cat)
                btn.setCheckable(True)
                btn.setChecked(enabled)
                btn.setEnabled(reason is None)
                btn.setObjectName("partsJunkmanToggle")
                btn.setProperty("active", enabled)
                if reason:
                    btn.setToolTip(reason)
                btn.clicked.connect(
                    lambda checked, slot=card_entry.parts_slot, category=cat: self.on_parts_junkman_toggled(slot, category, checked)
                )
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                row.addWidget(btn, 0, Qt.AlignLeft)
                buttons[cat] = btn
            elif enabled:
                row.addWidget(self._make_stat_badge(cat, "partsJunkmanActive"), 0, Qt.AlignLeft)
        if not active_any and not editable:
            row.addWidget(self._make_stat_badge("None", "partsJunkmanNone"), 0, Qt.AlignLeft)
        row.addStretch(1)
        parent.addLayout(row)
        return buttons

    def _build_parts_card(self, vm: PartsCardVm) -> QWidget:
        card_entry = vm.card_entry
        card = QFrame()
        card.setObjectName("partsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumWidth(360)
        card.setProperty("changed", vm.changed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        if card_entry.source_kind == "Career" and card_entry.career_slot is not None:
            slot_text = f"Career Slot {card_entry.career_slot + 1}"
        elif card_entry.car_number is not None:
            slot_text = f"Car #{card_entry.car_number:02X}"
        else:
            slot_text = f"Parts Slot {card_entry.parts_slot}"
        slot_badge = self._make_stat_badge(slot_text, "garageCardSlot")
        header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        source_badge = QLabel()
        source_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        source_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(source_badge, 0, Qt.AlignRight)
        pink_slip_badge = self._make_garage_source_badge("Pink Slip")
        pink_slip_badge.setVisible(False)
        header_row.addWidget(pink_slip_badge, 0, Qt.AlignRight)
        active_badge = self._make_active_car_badge()
        active_badge.setVisible(False)
        header_row.addWidget(active_badge, 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = self._make_stat_badge(card_entry.display_name, "garageCardMeta")
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_badges: Dict[str, QLabel] = {}
        for text in ["Stock", "Modified", "Maxed", "Junkman", "Read-only"]:
            badge = self._make_tuning_status_badge(text)
            badge.setVisible(False)
            status_badges[text] = badge
            status_row.addWidget(badge, 0, Qt.AlignLeft)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        bulk_buttons: Dict[str, QPushButton] = {}
        for text, handler in [
            ("Max Performance", self.on_tuning_max_performance),
            ("Max Junkman", self.on_tuning_max_junkman),
            ("Stock Build", self.on_tuning_stock_build),
            ("Clear Junkman", self.on_tuning_clear_junkman),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("partsBulkBtn")
            btn.setEnabled(vm.limits is not None)
            btn.clicked.connect(lambda _, slot=card_entry.parts_slot, fn=handler: fn(slot))
            action_row.addWidget(btn)
            bulk_buttons[text] = btn
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        parts_badge = self._make_stat_badge(f"Parts Slot {card_entry.parts_slot}")
        meta_row.addWidget(parts_badge, 0, Qt.AlignLeft)
        block_badge = self._make_stat_badge(f"Block 0x{card_entry.block_abs_off:05X}")
        meta_row.addWidget(block_badge, 0, Qt.AlignLeft)
        career_badge = self._make_stat_badge("")
        career_badge.setVisible(False)
        meta_row.addWidget(career_badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)
        card_layout.addLayout(meta_row)

        utility_label = QLabel()
        utility_label.setObjectName("mutedLabel")
        utility_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card_layout.addWidget(utility_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("garageCardSep")
        card_layout.addWidget(sep)
        perf_label = QLabel("Performance")
        perf_label.setObjectName("garageCardFieldLabel")
        perf_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(perf_label)
        perf_rows = self._add_parts_perf_grid(card_layout, vm)
        junkman_label = QLabel("Junkman")
        junkman_label.setObjectName("garageCardFieldLabel")
        junkman_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(junkman_label)
        junkman_buttons = self._add_parts_junkman_section(card_layout, vm)

        diag_mask_label: Optional[QLabel] = None
        if self.show_parts_diagnostics:
            diag_sep = QFrame()
            diag_sep.setFrameShape(QFrame.HLine)
            diag_sep.setObjectName("garageCardSep")
            card_layout.addWidget(diag_sep)
            diag_label = QLabel("Diagnostics")
            diag_label.setObjectName("garageCardFieldLabel")
            diag_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(diag_label)
            diag_mask_label = self._make_stat_badge(f"Mask 0x{vm.mask:02X}")
            card_layout.addWidget(diag_mask_label, 0, Qt.AlignLeft)
            if card_entry.marker is not None:
                card_layout.addWidget(self._make_stat_badge(f"Marker {self._format_parts_raw(card_entry.marker)}"), 0, Qt.AlignLeft)
            if card_entry.confirmed_raw is not None:
                raw_label = QLabel("Confirmed Slice (+0x118..+0x137)")
                raw_label.setObjectName("partsCardNote")
                raw_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(raw_label)
                raw_value = QLabel(self._format_parts_raw(card_entry.confirmed_raw))
                raw_value.setObjectName("partsCardRaw")
                raw_value.setAlignment(Qt.AlignCenter)
                raw_value.setWordWrap(True)
                raw_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(raw_value)
            else:
                note = QLabel("This source type does not expose a confirmed raw diagnostic slice.")
                note.setObjectName("partsCardNote")
                note.setWordWrap(True)
                card_layout.addWidget(note)

        self._parts_card_widgets[card_entry.parts_slot] = card
        handle = PartsCardHandle(
            card=card,
            slot_badge=slot_badge,
            source_badge=source_badge,
            pink_slip_badge=pink_slip_badge,
            active_badge=active_badge,
            name_label=name_label,
            status_badges=status_badges,
            bulk_buttons=bulk_buttons,
            parts_badge=parts_badge,
            block_badge=block_badge,
            career_badge=career_badge,
            utility_label=utility_label,
            perf_rows=perf_rows,
            junkman_buttons=junkman_buttons,
            diag_mask_label=diag_mask_label,
        )
        self._parts_card_handles[card_entry.parts_slot] = handle
        self._apply_parts_card_vm(handle, vm)
        refresh_widget_style(card)
        return card

    def _build_parts_card_for_key(self, parts_slot: int) -> QWidget:
        vm = self._parts_live_vm_map.get(int(parts_slot))
        if vm is None:
            raise KeyError(f"Missing tuning VM for parts_slot={parts_slot}")
        card = self._acquire_parts_card_widget(diagnostics=self.show_parts_diagnostics)
        card.apply_vm(vm)
        self._parts_card_widgets[vm.card_entry.parts_slot] = card
        self._parts_card_handles[vm.card_entry.parts_slot] = card.handle
        return card

    def _rebuild_parts_cards(self, *, animate: bool = False, reset_scroll: bool = False) -> None:
        if hasattr(self, "_parts_pool_prewarm_timer"):
            self._parts_pool_prewarm_timer.stop()
            self._parts_pool_prewarm_requested = False
        self._parts_card_widgets = {}
        self._parts_card_handles = {}
        view_models = self._parts_card_view_models()
        self._parts_visible_order = [vm.card_entry.parts_slot for vm in view_models]
        self._parts_live_vm_map = {vm.card_entry.parts_slot: vm for vm in view_models}
        columns = max(1, self._detect_parts_card_columns())
        self._parts_slot_columns = columns
        self._parts_render_controller.schedule_render(
            self._parts_visible_order,
            build_widget=self._build_parts_card_for_key,
            columns=columns,
            empty_widget_factory=self._parts_empty_widget,
            animate=animate,
            reset_scroll=reset_scroll,
        )
        self._parts_cards_dirty = False

    def _refresh_parts_page(self, reason: str = "data_change") -> None:
        loaded = self.savefile is not None
        if hasattr(self, "_parts_pool_prewarm_timer") and self._parts_page_visible():
            self._parts_pool_prewarm_timer.stop()
            self._parts_pool_prewarm_requested = False
        if hasattr(self, "chk_show_parts_diagnostics"):
            self.chk_show_parts_diagnostics.blockSignals(True)
            self.chk_show_parts_diagnostics.setChecked(self.show_parts_diagnostics)
            self.chk_show_parts_diagnostics.setEnabled(loaded)
            self.chk_show_parts_diagnostics.blockSignals(False)
        if hasattr(self, "tuning_filter_buttons"):
            current = getattr(self, "tuning_filter", "All")
            for label, button in self.tuning_filter_buttons.items():
                button.setChecked(label == current)
        if not self._parts_page_visible():
            self._mark_parts_cards_dirty()
            return

        columns = max(1, self._detect_parts_card_columns())
        self._parts_slot_columns = columns
        if (
            reason in {"page_enter", "reflow"}
            and not self._parts_cards_dirty
            and self._parts_render_controller.has_rendered_content()
        ):
            self._parts_render_controller.reflow(columns)
            return

        self._rebuild_parts_cards(
            animate=reason in {"page_enter", "filter_change"},
            reset_scroll=reason in {"search_change", "filter_change"},
        )

    def on_parts_search_changed(self) -> None:
        self._mark_parts_cards_dirty()
        if hasattr(self, "_parts_search_timer"):
            self._parts_search_timer.start(150)

    def on_toggle_parts_diagnostics(self) -> None:
        self.show_parts_diagnostics = self.chk_show_parts_diagnostics.isChecked()
        self._mark_parts_cards_dirty()
        self._refresh_parts_page(reason="data_change")

    def _select_tuning_filter(self, source: str) -> None:
        self.tuning_filter = source
        self._mark_parts_cards_dirty()
        self._refresh_parts_page(reason="filter_change")
