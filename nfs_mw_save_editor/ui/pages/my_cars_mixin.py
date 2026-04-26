"""My Cars page: player-owned build cards, bulk performance/junkman actions."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from core.models import ResolvedMyCarsEntry
from core.savefile import SaveFile
from core.tuning_limits import PERF_PART_NAMES
from ui.pages.constants import *


class MyCarsMixin:
    def _build_my_cars_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        hint = QLabel(
            "Manage builds for your owned cars. Max Performance and Max Junkman shortcuts are available per car."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.my_cars_search = QLineEdit()
        self.my_cars_search.setPlaceholderText("Search My Cars by model name...")
        self.my_cars_search.textChanged.connect(self.on_my_cars_search_changed)
        controls.addWidget(self.my_cars_search, 1)
        layout.addLayout(controls)

        self.my_cars_cards = QWidget()
        self.my_cars_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.my_cars_cards_layout = QGridLayout(self.my_cars_cards)
        self.my_cars_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.my_cars_cards_layout.setHorizontalSpacing(14)
        self.my_cars_cards_layout.setVerticalSpacing(14)
        self.my_cars_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.my_cars_cards_scroll = QScrollArea()
        self.my_cars_cards_scroll.setObjectName("cardScroll")
        self.my_cars_cards_scroll.setWidgetResizable(True)
        self.my_cars_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.my_cars_cards_scroll.setWidget(self.my_cars_cards)
        layout.addWidget(self.my_cars_cards_scroll, 1)

        self._my_cars_card_widgets: Dict[int, QFrame] = {}
        self._rebuild_my_cars_cards()
        return w

    def _my_cars_card_entries(self) -> List[ResolvedMyCarsEntry]:
        entries = list(self.my_cars_entries)
        term = self.my_cars_search.text().strip().lower() if hasattr(self, "my_cars_search") else ""
        if term:
            entries = [e for e in entries if term in e.resolved_model_name.lower()]
        return entries

    def _detect_my_cars_card_columns(self) -> int:
        return self._detect_col_count("my_cars_cards_scroll", MY_CARS_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_my_cars_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols(
            "my_cars_cards_scroll", "_my_cars_slot_columns", MY_CARS_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_my_cars_cards, force,
        )

    def _rebuild_my_cars_cards(self) -> None:
        if not hasattr(self, "my_cars_cards_layout"):
            return
        self._clear_layout(self.my_cars_cards_layout)
        self._my_cars_card_widgets = {}
        columns = max(1, self._detect_my_cars_card_columns())
        self._my_cars_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect owned My Cars builds.")
            label.setObjectName("mutedLabel")
            self.my_cars_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.parts_detection_error:
            label = QLabel(f"My Cars unavailable: {self.parts_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.my_cars_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._my_cars_card_entries()
        if not visible_entries:
            label = QLabel("No My Cars entries match the current search/filter.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.my_cars_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, entry in enumerate(visible_entries):
            card, card_layout = self._make_card_frame(
                changed=self._parts_card_changed(entry.parts_slot),
                minimum_width=320,
            )

            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            car_label = QLabel(f"Car #{entry.car_number:02X}")
            car_label.setObjectName("contentCardSlot")
            car_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            car_label.setAlignment(Qt.AlignCenter)
            header_row.addWidget(car_label, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(self._make_garage_source_badge("My Cars"), 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            name_label = QLabel(entry.resolved_model_name)
            name_label.setObjectName("contentCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            badges = [f"Parts Slot {entry.parts_slot}"]
            if entry.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                badges.append(f"Career Slot {entry.career_slot + 1}")
            for text in badges:
                badge = QLabel(text)
                badge.setObjectName("contentCardStatBadge")
                badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                badge.setAlignment(Qt.AlignCenter)
                meta_row.addWidget(badge, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            limits = self._parts_limits(entry)
            btn_max_perf = self._make_card_action_button("Max Performance")
            btn_max_perf.setEnabled(limits is not None)
            btn_max_perf.clicked.connect(lambda _, slot=entry.parts_slot: self.on_my_cars_max_performance(slot))
            btn_max_junk = self._make_card_action_button("Max Junkman")
            btn_max_junk.setEnabled(limits is not None)
            btn_max_junk.clicked.connect(lambda _, slot=entry.parts_slot: self.on_my_cars_max_junkman(slot))
            action_row.addWidget(btn_max_perf)
            action_row.addWidget(btn_max_junk)
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            card_layout.addWidget(self._make_card_separator())

            card_layout.addWidget(self._make_card_field_label("Performance"))
            self._add_parts_perf_grid(card_layout, entry)

            card_layout.addWidget(self._make_card_field_label("Junkman"))
            self._add_parts_junkman_section(card_layout, entry)

            row = idx // columns
            col = idx % columns
            self.my_cars_cards_layout.addWidget(card, row, col)
            self._my_cars_card_widgets[entry.parts_slot] = card

        for col in range(columns):
            self.my_cars_cards_layout.setColumnStretch(col, 1)

    def _refresh_my_cars_page(self) -> None:
        self._rebuild_my_cars_cards()

    def on_my_cars_search_changed(self) -> None:
        self._refresh_my_cars_page()

    def on_my_cars_max_performance(self, parts_slot: int) -> None:
        entry = next((item for item in self.my_cars_entries if item.parts_slot == parts_slot), None)
        if entry is None:
            return
        limits = self._parts_limits(entry)
        if limits is None:
            return
        for name in PERF_PART_NAMES:
            self.on_parts_level_changed(parts_slot, name, int(limits.get(name, 0)))

    def on_my_cars_max_junkman(self, parts_slot: int) -> None:
        entry = next((item for item in self.my_cars_entries if item.parts_slot == parts_slot), None)
        if entry is None:
            return
        levels = self._current_parts_levels().get(parts_slot, self._parts_level_dict_from_my_car(entry))
        mask = 0
        for bit, name in SaveFile.JUNKMAN_MASK_BITS:
            if self._parts_junkman_reason(levels, name) is None:
                mask |= bit
        self.staged_state.parts_masks.set_item(parts_slot, mask, self.have_parts_masks)
        self._update_action_states()
        self._refresh_parts_page()
        self._refresh_my_cars_page()
