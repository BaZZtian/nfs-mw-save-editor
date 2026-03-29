from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.models import ResolvedMyCarsEntry, ResolvedPartsEntry
from core.savefile import SaveFile
from core.tuning_limits import PERF_PART_NAMES, get_model_tuning_limits
from ui.pages.constants import PARTS_TILE_MIN_WIDTH
from ui.widgets import WantSpinBox, build_perf_level_row


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
        self.parts_cards_scroll.setWidget(self.parts_cards)
        layout.addWidget(self.parts_cards_scroll, 1)

        self._parts_card_widgets: Dict[int, QFrame] = {}
        self._rebuild_parts_cards()
        return w

    def _detect_parts_card_columns(self) -> int:
        return self._detect_col_count("parts_cards_scroll", PARTS_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_parts_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols("parts_cards_scroll", "_parts_slot_columns", PARTS_TILE_MIN_WIDTH, ((1100, 2),), self._rebuild_parts_cards, force)

    def _format_parts_raw(self, raw: bytes) -> str:
        return raw.hex(" ").upper()

    def _make_stat_badge(self, text: str, object_name: str = "garageCardStatBadge") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _make_tuning_status_badge(self, text: str) -> QLabel:
        object_name = {
            "Stock": "tuningStatusStock",
            "Modified": "tuningStatusModified",
            "Maxed": "tuningStatusMaxed",
            "Junkman": "tuningStatusJunkman",
        }.get(text, "garageCardStatBadge")
        return self._make_stat_badge(text, object_name)

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

    def on_parts_level_changed(self, parts_slot: int, part_name: str, value: int) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        levels = dict(self._current_parts_levels().get(parts_slot, self._entry_parts_levels(entry)))
        levels[part_name] = int(value)
        self._set_parts_slot_levels(parts_slot, levels)
        self._update_action_states()
        self._refresh_parts_page()

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
        self._update_action_states()
        self._refresh_parts_page()

    def on_tuning_max_performance(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        limits = None if entry is None else self._parts_limits(entry)
        if limits is None:
            return
        self._set_parts_slot_levels(parts_slot, {name: int(limits.get(name, 0)) for name in PERF_PART_NAMES})
        self._update_action_states()
        self._refresh_parts_page()

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
        self._update_action_states()
        self._refresh_parts_page()

    def on_tuning_stock_build(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        self._set_parts_slot_levels(parts_slot, {name: 0 for name in PERF_PART_NAMES})
        self._set_parts_slot_mask(parts_slot, 0)
        self._update_action_states()
        self._refresh_parts_page()

    def on_tuning_clear_junkman(self, parts_slot: int) -> None:
        entry = self._entry_by_parts_slot(parts_slot)
        if entry is None or self._parts_limits(entry) is None:
            return
        self._set_parts_slot_mask(parts_slot, 0)
        self._update_action_states()
        self._refresh_parts_page()

    def _add_parts_perf_grid(self, parent: QVBoxLayout, entry) -> None:
        levels = self._current_parts_levels().get(entry.parts_slot, self._entry_parts_levels(entry))
        limits = self._parts_limits(entry)
        editable = limits is not None
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for idx, name in enumerate(PERF_PART_NAMES):
            level = int(levels.get(name, 0))
            max_level = max(level, int(limits.get(name, 0))) if editable else None
            row_w, row_layout = build_perf_level_row(name, level, max_level)
            if editable:
                btn_minus = QPushButton("\u2212")
                btn_minus.setObjectName("partsLevelBtn")
                btn_minus.setFixedSize(24, 24)
                spin = WantSpinBox()
                spin.setObjectName("partsLevelSpin")
                spin.setRange(0, max_level)
                spin.setValue(level)
                spin.setAlignment(Qt.AlignCenter)
                spin.setButtonSymbols(WantSpinBox.NoButtons)
                spin.valueChanged.connect(lambda val, slot=entry.parts_slot, part=name: self.on_parts_level_changed(slot, part, val))
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
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)

    def _add_parts_junkman_section(self, parent: QVBoxLayout, entry) -> None:
        levels = self._current_parts_levels().get(entry.parts_slot, self._entry_parts_levels(entry))
        mask = self._current_parts_masks().get(entry.parts_slot, self.have_parts_masks.get(entry.parts_slot, entry.junkman_mask))
        editable = self._parts_limits(entry) is not None
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        blocked: List[str] = []
        active_any = False
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
                    blocked.append(f"{cat}: {reason}")
                btn.clicked.connect(lambda checked, slot=entry.parts_slot, category=cat: self.on_parts_junkman_toggled(slot, category, checked))
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                row.addWidget(btn, 0, Qt.AlignLeft)
            elif enabled:
                row.addWidget(self._make_stat_badge(cat, "partsJunkmanActive"), 0, Qt.AlignLeft)
        if not active_any and not editable:
            row.addWidget(self._make_stat_badge("None", "partsJunkmanNone"), 0, Qt.AlignLeft)
        row.addStretch(1)
        parent.addLayout(row)
        if blocked:
            note = QLabel(" / ".join(blocked))
            note.setObjectName("partsCardNote")
            note.setWordWrap(True)
            parent.addWidget(note)

    def _rebuild_parts_cards(self) -> None:
        if not hasattr(self, "parts_cards_layout"):
            return
        self._clear_layout(self.parts_cards_layout)
        self._parts_card_widgets = {}
        columns = max(1, self._detect_parts_card_columns())
        self._parts_slot_columns = columns
        if not self.savefile:
            self.parts_cards_layout.addWidget(QLabel("Open a save to inspect and edit tuning builds."), 0, 0, 1, columns)
            return
        if self.parts_detection_error:
            label = QLabel(f"Tuning tools unavailable: {self.parts_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return
        visible_entries = self._tuning_card_entries()
        if not visible_entries:
            label = QLabel("No tuning entries match the current search or filter.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return
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
        for idx, card_entry in enumerate(visible_entries):
            entry = card_entry.raw_entry
            is_active = (
                projected_active_car_number is not None
                and card_entry.source_kind != "My Cars"
                and (
                    (card_entry.car_number is not None and int(card_entry.car_number) == int(projected_active_car_number))
                    or int(card_entry.parts_slot) in projected_active_parts_slots
                )
            )
            card = QFrame()
            card.setObjectName("partsCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(360)
            card.setProperty("changed", self._parts_card_changed(card_entry.parts_slot))
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
            header_row.addWidget(self._make_stat_badge(slot_text, "garageCardSlot"), 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(self._make_garage_source_badge(card_entry.source_kind), 0, Qt.AlignRight)
            if card_entry.pink_slip:
                header_row.addWidget(self._make_garage_source_badge("Pink Slip"), 0, Qt.AlignRight)
            if is_active:
                header_row.addWidget(self._make_active_car_badge(), 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            card_layout.addWidget(self._make_stat_badge(card_entry.display_name, "garageCardMeta"), 0, Qt.AlignLeft)

            statuses = self._parts_status_labels(entry)
            if statuses:
                status_row = QHBoxLayout()
                status_row.setSpacing(8)
                for text in statuses:
                    status_row.addWidget(self._make_tuning_status_badge(text), 0, Qt.AlignLeft)
                status_row.addStretch(1)
                card_layout.addLayout(status_row)

            limits = self._parts_limits(entry)
            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            for text, handler in [("Max Performance", self.on_tuning_max_performance), ("Max Junkman", self.on_tuning_max_junkman), ("Stock Build", self.on_tuning_stock_build), ("Clear Junkman", self.on_tuning_clear_junkman)]:
                btn = QPushButton(text)
                btn.setObjectName("partsBulkBtn")
                btn.setEnabled(limits is not None)
                btn.clicked.connect(lambda _, slot=card_entry.parts_slot, fn=handler: fn(slot))
                action_row.addWidget(btn)
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            meta_row.addWidget(self._make_stat_badge(f"Parts Slot {card_entry.parts_slot}"), 0, Qt.AlignLeft)
            meta_row.addWidget(self._make_stat_badge(f"Block 0x{card_entry.block_abs_off:05X}"), 0, Qt.AlignLeft)
            if card_entry.source_kind == "My Cars" and card_entry.career_slot is not None:
                meta_row.addWidget(self._make_stat_badge(f"Career Slot {card_entry.career_slot + 1}"), 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            if limits is None:
                note = QLabel("No confirmed tuning limits for this model yet. Safe mode keeps this card read-only.")
                note.setObjectName("partsCardNote")
                note.setWordWrap(True)
                card_layout.addWidget(note)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)
            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)
            self._add_parts_perf_grid(card_layout, entry)
            junkman_label = QLabel("Junkman")
            junkman_label.setObjectName("garageCardFieldLabel")
            junkman_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(junkman_label)
            self._add_parts_junkman_section(card_layout, entry)

            if self.show_parts_diagnostics:
                diag_sep = QFrame()
                diag_sep.setFrameShape(QFrame.HLine)
                diag_sep.setObjectName("garageCardSep")
                card_layout.addWidget(diag_sep)
                diag_label = QLabel("Diagnostics")
                diag_label.setObjectName("garageCardFieldLabel")
                diag_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(diag_label)
                card_layout.addWidget(self._make_stat_badge(f"Mask 0x{self._current_parts_masks().get(card_entry.parts_slot, card_entry.junkman_mask):02X}"), 0, Qt.AlignLeft)
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

            self.parts_cards_layout.addWidget(card, idx // columns, idx % columns)
            self._parts_card_widgets[card_entry.parts_slot] = card
        for col in range(columns):
            self.parts_cards_layout.setColumnStretch(col, 1)

    def _refresh_parts_page(self) -> None:
        loaded = self.savefile is not None
        if hasattr(self, "chk_show_parts_diagnostics"):
            self.chk_show_parts_diagnostics.blockSignals(True)
            self.chk_show_parts_diagnostics.setChecked(self.show_parts_diagnostics)
            self.chk_show_parts_diagnostics.setEnabled(loaded)
            self.chk_show_parts_diagnostics.blockSignals(False)
        if hasattr(self, "tuning_filter_buttons"):
            current = getattr(self, "tuning_filter", "All")
            for label, button in self.tuning_filter_buttons.items():
                button.setChecked(label == current)
        self._rebuild_parts_cards()

    def on_parts_search_changed(self) -> None:
        self._refresh_parts_page()

    def on_toggle_parts_diagnostics(self) -> None:
        self.show_parts_diagnostics = self.chk_show_parts_diagnostics.isChecked()
        self._refresh_parts_page()

    def _select_tuning_filter(self, source: str) -> None:
        self.tuning_filter = source
        self._refresh_parts_page()
