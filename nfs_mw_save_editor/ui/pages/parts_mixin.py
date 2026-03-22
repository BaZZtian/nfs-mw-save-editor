"""Parts page: parts-block reader/editor, level controls, junkman toggles."""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import ResolvedMyCarsEntry, ResolvedPartsEntry
from core.savefile import SaveFile
from core.tuning_limits import PERF_PART_NAMES, get_model_tuning_limits, get_tuning_limit
from ui.pages.constants import *
from ui.widgets import WantSpinBox


class PartsMixin:
    def _build_parts_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        hint = QLabel(
            "Technical parts view/editor. Vehicle builds are resolved from parts_slot into the confirmed 0x198-byte "
            "per-car parts block. Regular performance levels and Junkman categories shown here are save-backed and staged until apply."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.parts_search = QLineEdit()
        self.parts_search.setPlaceholderText("Search parts by model name...")
        self.parts_search.textChanged.connect(self.on_parts_search_changed)
        controls.addWidget(self.parts_search, 1)
        self.chk_show_parts_diagnostics = QCheckBox("Show parts diagnostics")
        self.chk_show_parts_diagnostics.setChecked(False)
        self.chk_show_parts_diagnostics.stateChanged.connect(self.on_toggle_parts_diagnostics)
        controls.addWidget(self.chk_show_parts_diagnostics, 0)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.parts_filter_buttons: Dict[str, QPushButton] = {}
        self.parts_filter_group = QButtonGroup(self)
        self.parts_filter_group.setExclusive(True)
        for label in ["All", "Career", "Pink Slip", "Unknown"]:
            btn = QPushButton(label)
            btn.setObjectName("catButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, source=label: self._select_parts_filter(source))
            self.parts_filter_group.addButton(btn)
            self.parts_filter_buttons[label] = btn
            filter_row.addWidget(btn)
        self.parts_filter_buttons["All"].setChecked(True)
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

    def _parts_card_entries(self) -> List[ResolvedPartsEntry]:
        entries = list(self.parts_entries)
        term = self.parts_search.text().strip().lower() if hasattr(self, "parts_search") else ""
        source = self.parts_filter
        filtered: List[ResolvedPartsEntry] = []
        for entry in entries:
            if term and term not in entry.display_name.lower():
                continue
            if source != "All":
                if source == "Unknown":
                    if not entry.source_kind.startswith("Unknown"):
                        continue
                elif entry.source_kind != source:
                    continue
            filtered.append(entry)
        return filtered

    def _detect_parts_card_columns(self) -> int:
        return self._detect_col_count("parts_cards_scroll", PARTS_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_parts_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols(
            "parts_cards_scroll", "_parts_slot_columns", PARTS_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_parts_cards, force,
        )

    def _format_parts_raw(self, raw: bytes) -> str:
        return raw.hex(" ").upper()

    def _make_stat_badge(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("garageCardStatBadge")
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _parts_level_dict_from_entry(self, entry: ResolvedPartsEntry) -> Dict[str, int]:
        return {
            "Tires": entry.tires,
            "Brakes": entry.brakes,
            "Suspension": entry.suspension,
            "Transmission": entry.transmission,
            "Engine": entry.engine,
            "Turbo": entry.turbo,
            "NOS": entry.nos,
        }

    def _parts_level_dict_from_my_car(self, entry: ResolvedMyCarsEntry) -> Dict[str, int]:
        return {
            "Tires": entry.tires,
            "Brakes": entry.brakes,
            "Suspension": entry.suspension,
            "Transmission": entry.transmission,
            "Engine": entry.engine,
            "Turbo": entry.turbo,
            "NOS": entry.nos,
        }

    def _entry_model_name(self, entry) -> str:
        if hasattr(entry, "display_name"):
            return entry.display_name
        return entry.resolved_model_name

    def _entry_parts_levels(self, entry) -> Dict[str, int]:
        if hasattr(entry, "display_name"):
            return self._parts_level_dict_from_entry(entry)
        return self._parts_level_dict_from_my_car(entry)

    def _current_parts_levels(self) -> Dict[int, Dict[str, int]]:
        want_map = self.want_parts_levels or {}
        all_entries = list(self.parts_entries) + list(self.my_cars_entries)
        dedup: Dict[int, object] = {}
        for entry in all_entries:
            dedup[entry.parts_slot] = entry
        return {
            entry.parts_slot: dict(
                want_map.get(
                    entry.parts_slot,
                    self.have_parts_levels.get(
                        entry.parts_slot,
                        self._entry_parts_levels(entry),
                    ),
                )
            )
            for entry in dedup.values()
        }

    def _current_parts_masks(self) -> Dict[int, int]:
        want_map = self.want_parts_masks or {}
        all_entries = list(self.parts_entries) + list(self.my_cars_entries)
        dedup: Dict[int, object] = {}
        for entry in all_entries:
            dedup[entry.parts_slot] = entry
        return {
            entry.parts_slot: int(
                want_map.get(entry.parts_slot, self.have_parts_masks.get(entry.parts_slot, entry.junkman_mask))
            )
            for entry in dedup.values()
        }

    def _parts_limits(self, entry) -> Optional[Dict[str, int]]:
        return get_model_tuning_limits(self._entry_model_name(entry))

    def _parts_card_changed(self, parts_slot: int) -> bool:
        current_levels = self._current_parts_levels().get(parts_slot, {})
        have_levels = self.have_parts_levels.get(parts_slot, {})
        if any(int(current_levels.get(name, 0)) != int(have_levels.get(name, 0)) for name in PERF_PART_NAMES):
            return True
        current_mask = self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))
        return int(current_mask) != int(self.have_parts_masks.get(parts_slot, 0))

    def _has_parts_pending_changes(self) -> bool:
        if self.savefile is None or self.parts_detection_error:
            return False
        all_slots = {entry.parts_slot for entry in self.parts_entries} | {entry.parts_slot for entry in self.my_cars_entries}
        return any(self._parts_card_changed(parts_slot) for parts_slot in all_slots)

    def _parts_junkman_reason(self, levels: Dict[str, int], category: str) -> Optional[str]:
        if category == "Turbo" and int(levels.get("Turbo", 0)) <= 0:
            return "Requires regular Turbo > 0"
        if category == "NOS" and int(levels.get("NOS", 0)) <= 0:
            return "Requires regular NOS > 0"
        return None

    def on_parts_level_changed(self, parts_slot: int, part_name: str, value: int) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        entry = next((item for item in (list(self.parts_entries) + list(self.my_cars_entries)) if item.parts_slot == parts_slot), None)
        if entry is None:
            return
        limits = self._parts_limits(entry)
        if limits is None:
            return
        cap = int(limits.get(part_name, 0))
        wanted = max(0, min(int(value), cap))
        if self.want_parts_levels is None:
            self.want_parts_levels = {slot: dict(levels) for slot, levels in self.have_parts_levels.items()}
        if self.want_parts_masks is None:
            self.want_parts_masks = dict(self.have_parts_masks)
        self.want_parts_levels.setdefault(parts_slot, dict(self.have_parts_levels.get(parts_slot, {})))[part_name] = wanted

        current_levels = self._current_parts_levels().get(parts_slot, {})
        current_mask = self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))
        turbo_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "Turbo"), 0)
        nos_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "NOS"), 0)
        if turbo_bit and int(current_levels.get("Turbo", 0)) <= 0:
            current_mask &= ~turbo_bit
        if nos_bit and int(current_levels.get("NOS", 0)) <= 0:
            current_mask &= ~nos_bit
        self.want_parts_masks[parts_slot] = current_mask

        self._update_action_states()
        self._refresh_parts_page()
        self._refresh_my_cars_page()

    def on_parts_junkman_toggled(self, parts_slot: int, category: str, checked: bool) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == category), None)
        if bit is None:
            return
        levels = self._current_parts_levels().get(parts_slot, self.have_parts_levels.get(parts_slot, {}))
        if self._parts_junkman_reason(levels, category):
            return
        if self.want_parts_masks is None:
            self.want_parts_masks = dict(self.have_parts_masks)
        current = self._current_parts_masks().get(parts_slot, self.have_parts_masks.get(parts_slot, 0))
        self.want_parts_masks[parts_slot] = current | bit if checked else current & ~bit
        self._update_action_states()
        self._refresh_parts_page()
        self._refresh_my_cars_page()

    def _add_parts_perf_grid(self, parent: QVBoxLayout, entry) -> None:
        """Build a 2-column grid of staged level rows for performance parts."""
        current_levels = self._current_parts_levels().get(entry.parts_slot, self._entry_parts_levels(entry))
        limits = self._parts_limits(entry)
        editable = limits is not None
        perf_items = [(name, int(current_levels.get(name, 0))) for name in PERF_PART_NAMES]
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for idx, (name, level) in enumerate(perf_items):
            max_level = max(int(level), int((limits or {}).get(name, get_tuning_limit(self._entry_model_name(entry), name, default=4))))
            row_w = QWidget()
            row_w.setObjectName("partsLevelRow")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(name)
            lbl.setObjectName("partsLevelLabel")
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addWidget(lbl)

            for seg_idx in range(1, max_level + 1):
                seg = QFrame()
                seg.setObjectName("partsLevelSeg")
                if level >= seg_idx:
                    seg.setProperty("filled", str(seg_idx))
                else:
                    seg.setProperty("filled", "0")
                seg.setFixedSize(20, 8)
                row_layout.addWidget(seg)

            num = QLabel(f"{level}/{max_level}")
            num.setObjectName("partsLevelNum")
            num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(num)

            if editable:
                spin = WantSpinBox()
                spin.setObjectName("partsLevelSpin")
                spin.setRange(0, max_level)
                spin.setValue(level)
                spin.setAlignment(Qt.AlignCenter)
                spin.setButtonSymbols(WantSpinBox.PlusMinus)
                spin.valueChanged.connect(
                    lambda val, slot=entry.parts_slot, part=name: self.on_parts_level_changed(slot, part, val)
                )
                row_layout.addWidget(spin)
            else:
                row_layout.addWidget(self._make_stat_badge("Read-only"))

            gr = idx // 2
            gc = idx % 2
            grid.addWidget(row_w, gr, gc)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)

    def _add_parts_junkman_section(self, parent: QVBoxLayout, entry) -> None:
        current_levels = self._current_parts_levels().get(entry.parts_slot, self._entry_parts_levels(entry))
        current_mask = self._current_parts_masks().get(
            entry.parts_slot,
            self.have_parts_masks.get(entry.parts_slot, entry.junkman_mask),
        )
        editable = self._parts_limits(entry) is not None
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        blocked: List[str] = []
        active_any = False
        for bit, cat in SaveFile.JUNKMAN_MASK_BITS:
            enabled = bool(current_mask & bit)
            active_any = active_any or enabled
            reason = self._parts_junkman_reason(current_levels, cat)
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
                btn.clicked.connect(
                    lambda checked, slot=entry.parts_slot, category=cat: self.on_parts_junkman_toggled(slot, category, checked)
                )
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                row.addWidget(btn, 0, Qt.AlignLeft)
            elif enabled:
                pill = QLabel(cat)
                pill.setObjectName("partsJunkmanActive")
                pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                pill.setAlignment(Qt.AlignCenter)
                row.addWidget(pill, 0, Qt.AlignLeft)
        if not active_any and not editable:
            pill = QLabel("None")
            pill.setObjectName("partsJunkmanNone")
            pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            pill.setAlignment(Qt.AlignCenter)
            row.addWidget(pill, 0, Qt.AlignLeft)
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
            label = QLabel("Open a save to inspect resolved parts records.")
            label.setObjectName("mutedLabel")
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.parts_detection_error:
            label = QLabel(f"Parts viewer disabled: {self.parts_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._parts_card_entries()
        if not visible_entries:
            label = QLabel("No parts entries match the current search/filter.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, entry in enumerate(visible_entries):
            card = QFrame()
            card.setObjectName("partsCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(320)
            card.setProperty("changed", self._parts_card_changed(entry.parts_slot))

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # ── Header: slot + source badge ─────────────────
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_label = QLabel(f"Slot {entry.career_slot + 1}")
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)
            source_label = self._make_garage_source_badge(entry.source_kind)
            header_row.addWidget(slot_label, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_label, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # ── Car name ────────────────────────────────────
            name_label = QLabel(entry.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # ── Meta badges ─────────────────────────────────
            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            parts_label = QLabel(f"Parts Slot {entry.parts_slot}")
            parts_label.setObjectName("garageCardStatBadge")
            parts_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            parts_label.setAlignment(Qt.AlignCenter)
            meta_row.addWidget(parts_label, 0, Qt.AlignLeft)

            offset_label = QLabel(f"Block 0x{entry.block_abs_off:05X}")
            offset_label.setObjectName("garageCardStatBadge")
            offset_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            offset_label.setAlignment(Qt.AlignCenter)
            meta_row.addWidget(offset_label, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            limits = self._parts_limits(entry)
            if limits is None:
                ro_label = QLabel("Read-only: no confirmed tuning cap mapping for this model.")
                ro_label.setObjectName("partsCardNote")
                ro_label.setWordWrap(True)
                card_layout.addWidget(ro_label)

            # ── Separator ───────────────────────────────────
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # ── Performance (level bars) ────────────────────
            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)

            self._add_parts_perf_grid(card_layout, entry)

            # ── Junkman (accent pills) ──────────────────────
            junkman_label = QLabel("Junkman")
            junkman_label.setObjectName("garageCardFieldLabel")
            junkman_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(junkman_label)

            self._add_parts_junkman_section(card_layout, entry)

            # ── Diagnostics (toggle-gated) ──────────────────
            if self.show_parts_diagnostics:
                diag_sep = QFrame()
                diag_sep.setFrameShape(QFrame.HLine)
                diag_sep.setObjectName("garageCardSep")
                card_layout.addWidget(diag_sep)

                diag_label = QLabel("Diagnostics")
                diag_label.setObjectName("garageCardFieldLabel")
                diag_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(diag_label)

                marker_label = self._make_stat_badge(f"Marker {self._format_parts_raw(entry.marker)}")
                card_layout.addWidget(marker_label, 0, Qt.AlignLeft)

                mask_label = self._make_stat_badge(
                    f"Mask 0x{self._current_parts_masks().get(entry.parts_slot, entry.junkman_mask):02X}"
                )
                card_layout.addWidget(mask_label, 0, Qt.AlignLeft)

                raw_label = QLabel("Confirmed Slice (+0x118..+0x137)")
                raw_label.setObjectName("partsCardNote")
                raw_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(raw_label)

                raw_value = QLabel(self._format_parts_raw(entry.confirmed_raw))
                raw_value.setObjectName("partsCardRaw")
                raw_value.setAlignment(Qt.AlignCenter)
                raw_value.setWordWrap(True)
                raw_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(raw_value)

            row = idx // columns
            col = idx % columns
            self.parts_cards_layout.addWidget(card, row, col)
            self._parts_card_widgets[entry.parts_slot] = card

        for col in range(columns):
            self.parts_cards_layout.setColumnStretch(col, 1)

    def _refresh_parts_page(self) -> None:
        loaded = self.savefile is not None
        if hasattr(self, "chk_show_parts_diagnostics"):
            self.chk_show_parts_diagnostics.blockSignals(True)
            self.chk_show_parts_diagnostics.setChecked(self.show_parts_diagnostics)
            self.chk_show_parts_diagnostics.setEnabled(loaded)
            self.chk_show_parts_diagnostics.blockSignals(False)
        self._rebuild_parts_cards()

    def on_parts_search_changed(self) -> None:
        self._refresh_parts_page()

    def _select_parts_filter(self, source: str) -> None:
        self.parts_filter = source
        for label, button in self.parts_filter_buttons.items():
            button.setChecked(label == source)
        self._refresh_parts_page()

    def on_toggle_parts_diagnostics(self) -> None:
        self.show_parts_diagnostics = self.chk_show_parts_diagnostics.isChecked()
        self._refresh_parts_page()


