"""Profile / Rap Sheet page: stat strip, garage slot rows, money and integrity handlers."""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import ResolvedGarageEntry
from ui.pages.constants import *


class ProfileMixin:
    def _build_profile_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(12)

        self._profile_number_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9, ]*"), self,
        )

        # ── Stat strip (4 tiles) ────────────────────────────────
        stat_strip = QHBoxLayout()
        stat_strip.setSpacing(10)

        self.money_edit = QLineEdit()
        self.money_edit.setPlaceholderText("0")
        self.money_edit.setValidator(self._profile_number_validator)
        self.money_edit.setAlignment(Qt.AlignCenter)
        self.money_edit.setObjectName("statTileEdit")
        self.money_edit.editingFinished.connect(self.on_money_edit_finished)
        self.money_current_label = QLabel("Current: -")
        self.money_current_label.setObjectName("statTileSub")
        self.money_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Money", self.money_edit, self.money_current_label), 1,
        )

        self.total_bounty_label = QLabel("-")
        self.total_bounty_label.setObjectName("statTileValue")
        self.total_bounty_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.total_bounty_label.setAlignment(Qt.AlignCenter)
        self.total_bounty_current_label = QLabel("Current: -")
        self.total_bounty_current_label.setObjectName("statTileSub")
        self.total_bounty_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Total Bounty", self.total_bounty_label, self.total_bounty_current_label), 1,
        )

        self.escaped_total_label = QLabel("-")
        self.escaped_total_label.setObjectName("statTileValue")
        self.escaped_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.escaped_total_label.setAlignment(Qt.AlignCenter)
        self.escaped_total_current_label = QLabel("Current: -")
        self.escaped_total_current_label.setObjectName("statTileSub")
        self.escaped_total_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Escapes", self.escaped_total_label, self.escaped_total_current_label), 1,
        )

        self.busted_total_label = QLabel("-")
        self.busted_total_label.setObjectName("statTileValue")
        self.busted_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.busted_total_label.setAlignment(Qt.AlignCenter)
        self.busted_total_current_label = QLabel("Current: -")
        self.busted_total_current_label.setObjectName("statTileSub")
        self.busted_total_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Busts", self.busted_total_label, self.busted_total_current_label), 1,
        )

        layout.addLayout(stat_strip)
        hint = QLabel(
            "Money is edited here. Per-car bounty is managed on the Garage page. Technical build editing lives on Parts, with a player-facing build view on My Cars."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # ── Garage section header ───────────────────────────────
        garage_header = QHBoxLayout()
        garage_header.setSpacing(8)
        self.garage_section_title = QLabel("Garage")
        self.garage_section_title.setObjectName("sectionLabel")
        garage_header.addWidget(self.garage_section_title)
        garage_header.addStretch(1)
        layout.addLayout(garage_header)

        # ── Garage card grid (scrollable) ───────────────────────
        self.garage_rows = QWidget()
        self.garage_rows.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.garage_rows_layout = QGridLayout(self.garage_rows)
        self.garage_rows_layout.setContentsMargins(8, 8, 8, 8)
        self.garage_rows_layout.setHorizontalSpacing(12)
        self.garage_rows_layout.setVerticalSpacing(12)
        self.garage_rows_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.garage_rows_scroll = QScrollArea()
        self.garage_rows_scroll.setObjectName("cardScroll")
        self.garage_rows_scroll.setWidgetResizable(True)
        self.garage_rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.garage_rows_scroll.setWidget(self.garage_rows)
        layout.addWidget(self.garage_rows_scroll, 1)

        # ── Integrity (togglable) ──────────────────────────────
        self.integrity_section_label = self._section_label("Integrity")
        layout.addWidget(self.integrity_section_label)
        self.profile_info = QTextEdit()
        self.profile_info.setReadOnly(True)
        self.profile_info.setMinimumHeight(120)
        self.profile_info.setMaximumHeight(160)
        self.profile_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.profile_info)

        self.garage_slot_edits: Dict[int, QLineEdit] = {}
        self.garage_slot_current_labels: Dict[int, QLabel] = {}
        self._garage_card_widgets: Dict[int, QFrame] = {}
        self._rebuild_garage_slot_rows()
        self.garage_section_title.setVisible(False)
        self.garage_rows_scroll.setVisible(False)
        self._sync_integrity_visibility()
        return w

    def _visible_garage_slots(self) -> List[ResolvedGarageEntry]:
        if self.show_all_garage_slots:
            return list(self.garage_slots)
        return [slot for slot in self.garage_slots if slot.occupied]

    def _sync_integrity_visibility(self) -> None:
        visible = bool(self.show_integrity_panel)
        if hasattr(self, "integrity_section_label"):
            self.integrity_section_label.setVisible(visible)
        if hasattr(self, "profile_info"):
            self.profile_info.setVisible(visible)

    def _rebuild_garage_slot_rows(self) -> None:
        self._clear_layout(self.garage_rows_layout)
        self.garage_slot_edits = {}
        self.garage_slot_current_labels = {}
        self._garage_card_widgets = {}
        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect car bounty data.")
            label.setObjectName("mutedLabel")
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.garage_detection_error:
            label = QLabel(f"Garage bounty editor disabled: {self.garage_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_slots = self._visible_garage_slots()
        if not visible_slots:
            if self.garage_slots:
                msg = "No occupied garage slots. Enable 'Show empty valid garage slots' in Settings."
            else:
                msg = "No valid garage slots detected."
            label = QLabel(msg)
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, slot in enumerate(visible_slots):
            card = QFrame()
            card.setObjectName("garageCard")
            card.setProperty("changed", False)
            card.setProperty("occupied", slot.occupied)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(200)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # ── Header: slot number + car name ──────────────
            slot_label = QLabel(f"Slot {slot.career_slot + 1}")
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)

            name_label = QLabel(slot.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)

            card_layout.addWidget(slot_label, 0, Qt.AlignLeft)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # ── Separator ───────────────────────────────────
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # ── Bounty editor ───────────────────────────────
            bounty_label = QLabel("Bounty")
            bounty_label.setObjectName("garageCardFieldLabel")
            bounty_label.setAlignment(Qt.AlignCenter)

            edit = QLineEdit()
            edit.setPlaceholderText("0")
            edit.setValidator(self._profile_number_validator)
            edit.setAlignment(Qt.AlignCenter)
            edit.setObjectName("garageCardEdit")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            edit.editingFinished.connect(
                lambda idx=slot.career_slot: self.on_garage_slot_edit_finished(idx),
            )

            current = QLabel("Current: -")
            current.setObjectName("garageCardCurrent")
            current.setAlignment(Qt.AlignCenter)

            self.garage_slot_edits[slot.career_slot] = edit
            self.garage_slot_current_labels[slot.career_slot] = current
            self._garage_card_widgets[slot.career_slot] = card

            card_layout.addWidget(bounty_label)
            card_layout.addWidget(edit)
            card_layout.addWidget(current)

            # ── Stats row: escaped / busted ─────────────────
            stats_row = QHBoxLayout()
            stats_row.setSpacing(8)
            stats_row.setContentsMargins(0, 4, 0, 0)

            esc_lbl = QLabel(f"Escaped  {slot.escaped}")
            esc_lbl.setObjectName("garageCardStatBadge")
            esc_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            esc_lbl.setAlignment(Qt.AlignCenter)
            bust_lbl = QLabel(f"Busted  {slot.busted}")
            bust_lbl.setObjectName("garageCardStatBadge")
            bust_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bust_lbl.setAlignment(Qt.AlignCenter)
            stats_row.addWidget(esc_lbl, 0, Qt.AlignLeft)
            stats_row.addStretch(1)
            stats_row.addWidget(bust_lbl, 0, Qt.AlignRight)
            card_layout.addLayout(stats_row)

            row = idx // columns
            col = idx % columns
            self.garage_rows_layout.addWidget(card, row, col)

        for c in range(columns):
            self.garage_rows_layout.setColumnStretch(c, 1)

    def _set_profile_line_edit(self, edit: QLineEdit, value: int, enabled: bool) -> None:
        edit.blockSignals(True)
        edit.setText(self._format_u32(value) if enabled else "")
        edit.setEnabled(enabled)
        edit.blockSignals(False)

    def _refresh_garage_totals(self, loaded: bool) -> None:
        if not loaded:
            self.total_bounty_label.setText("-")
            self.total_bounty_current_label.setText("Current: -")
            self.escaped_total_label.setText("-")
            self.escaped_total_current_label.setText("Current: -")
            self.busted_total_label.setText("-")
            self.busted_total_current_label.setText("Current: -")
            return

        if self.garage_detection_error:
            self.total_bounty_label.setText("Unavailable")
            self.total_bounty_current_label.setText(self.garage_detection_error)
            self.escaped_total_label.setText("Unavailable")
            self.escaped_total_current_label.setText("Current: -")
            self.busted_total_label.setText("Unavailable")
            self.busted_total_current_label.setText("Current: -")
            return

        current_bounties = self._current_slot_bounties()
        cleared_slots = self._current_cleared_pursuit_slots()
        have_total = sum(self.have_slot_bounties.values())
        current_total = sum(current_bounties.values())
        escaped_total = sum(0 if slot.career_slot in cleared_slots else slot.escaped for slot in self.garage_slots)
        busted_total = sum(0 if slot.career_slot in cleared_slots else slot.busted for slot in self.garage_slots)

        self.total_bounty_label.setText(self._format_u32(current_total))
        self.total_bounty_current_label.setText(self._format_current_value(have_total))
        self.escaped_total_label.setText(self._format_u32(escaped_total))
        self.escaped_total_current_label.setText(self._format_current_value(escaped_total))
        self.busted_total_label.setText(self._format_u32(busted_total))
        self.busted_total_current_label.setText(self._format_current_value(busted_total))

    def _commit_profile_edit(self, edit: QLineEdit, fallback: int) -> Optional[int]:
        try:
            value = self._parse_u32_text(edit.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            self._set_profile_line_edit(edit, fallback, True)
            edit.setFocus()
            edit.selectAll()
            return None

        self._set_profile_line_edit(edit, value, True)
        return value

    def on_money_edit_finished(self) -> None:
        if self._profile_refreshing or not self.savefile:
            return
        fallback = self.want_money if self.want_money is not None else self.have_money
        value = self._commit_profile_edit(self.money_edit, fallback)
        if value is None:
            return
        self.want_money = value
        self._update_action_states()

    def on_toggle_show_all_garage_slots(self) -> None:
        self.show_all_garage_slots = self.chk_show_all_garage_slots.isChecked()
        self._refresh_profile_inputs()

    def on_toggle_show_integrity(self) -> None:
        self.show_integrity_panel = self.chk_show_integrity.isChecked()
        self._sync_integrity_visibility()

    def _refresh_profile_inputs(self) -> None:
        loaded = self.savefile is not None
        self.chk_show_integrity.blockSignals(True)
        self.chk_show_integrity.setChecked(self.show_integrity_panel)
        self.chk_show_integrity.blockSignals(False)
        self._sync_integrity_visibility()

        self._profile_refreshing = True
        try:
            money_value = self.want_money if self.want_money is not None else self.have_money
            self._set_profile_line_edit(self.money_edit, money_value, loaded)
            self.money_current_label.setText(
                self._format_current_value(self.have_money) if loaded else "Current: -"
            )
            self._refresh_garage_totals(loaded)
            self._refresh_garage_page()
        finally:
            self._profile_refreshing = False

    def _has_profile_pending_changes(self) -> bool:
        if self.savefile is None:
            return False
        current_money = self.want_money if self.want_money is not None else self.have_money
        if current_money != self.have_money:
            return True
        if self.garage_detection_error:
            return False
        for slot in self.garage_slots:
            if self._garage_card_changed(slot.career_slot):
                return True
        return False


