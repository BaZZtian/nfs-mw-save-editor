"""Profile / Rap Sheet page: stat strip, summary metrics, money and integrity handlers."""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.savefile import SaveFile
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
            "Money is edited here. This page shows save totals and a compact garage summary."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # ── Compact garage summary ──────────────────────────────
        summary_strip = QHBoxLayout()
        summary_strip.setSpacing(10)
        self.profile_summary_values: Dict[str, QLabel] = {}
        summary_defs = [
            ("Career Cars", "career_cars"),
            ("Pink Slips", "pink_slips"),
            ("My Cars", "my_cars"),
            ("Free Career Slots", "free_career_slots"),
        ]
        for title, key in summary_defs:
            value = QLabel("-")
            value.setObjectName("statTileValue")
            value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            value.setAlignment(Qt.AlignCenter)
            sub = QLabel("Current save")
            sub.setObjectName("statTileSub")
            sub.setAlignment(Qt.AlignCenter)
            self.profile_summary_values[key] = value
            summary_strip.addWidget(self._build_stat_tile(title, value, sub), 1)
        layout.addLayout(summary_strip)

        # ── Integrity (togglable) ──────────────────────────────
        self.integrity_section_label = self._section_label("Integrity")
        layout.addWidget(self.integrity_section_label)
        self.profile_info = QTextEdit()
        self.profile_info.setReadOnly(True)
        self.profile_info.setMinimumHeight(120)
        self.profile_info.setMaximumHeight(160)
        self.profile_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.profile_info)

        self._sync_integrity_visibility()
        return w

    def _sync_integrity_visibility(self) -> None:
        visible = bool(self.show_integrity_panel)
        if hasattr(self, "integrity_section_label"):
            self.integrity_section_label.setVisible(visible)
        if hasattr(self, "profile_info"):
            self.profile_info.setVisible(visible)

    def _set_profile_line_edit(self, edit: QLineEdit, value: int, enabled: bool) -> None:
        edit.blockSignals(True)
        edit.setText(self._format_u32(value) if enabled else "")
        edit.setEnabled(enabled)
        edit.blockSignals(False)

    def _refresh_profile_summary(self, loaded: bool) -> None:
        if not hasattr(self, "profile_summary_values"):
            return
        if not loaded:
            for label in self.profile_summary_values.values():
                label.setText("-")
            return
        if self.garage_detection_error:
            for label in self.profile_summary_values.values():
                label.setText("N/A")
            return

        entries = self._current_transfer_entries()
        snapshot = self._current_allocator_snapshot()

        career_cars = sum(
            1
            for entry in entries
            if entry.career_slot != SaveFile.EMPTY_CAREER_SLOT and not entry.is_my_cars
        )
        pink_slips = sum(
            1
            for entry in entries
            if entry.career_slot != SaveFile.EMPTY_CAREER_SLOT and entry.source_kind == "Pink Slip"
        )
        my_cars = sum(1 for entry in entries if entry.is_my_cars)
        free_career_slots = len(snapshot.reusable_career_slots) if snapshot is not None else 0

        self.profile_summary_values["career_cars"].setText(self._format_u32(career_cars))
        self.profile_summary_values["pink_slips"].setText(self._format_u32(pink_slips))
        self.profile_summary_values["my_cars"].setText(self._format_u32(my_cars))
        self.profile_summary_values["free_career_slots"].setText(self._format_u32(free_career_slots))

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
            self._refresh_profile_summary(loaded)
            self._refresh_garage_page()
        finally:
            self._profile_refreshing = False

    def _has_profile_pending_changes(self) -> bool:
        if self.savefile is None:
            return False
        current_money = self.want_money if self.want_money is not None else self.have_money
        return current_money != self.have_money


