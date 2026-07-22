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
        layout.setContentsMargins(0, 6, 0, FOOTER_CLEARANCE)
        layout.setSpacing(12)

        self._profile_number_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9, ]*"), self,
        )

        # ── Top strip: Alias + Money ───────────────────────────
        top_strip = QHBoxLayout()
        top_strip.setSpacing(10)

        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("Player alias")
        self.alias_edit.setAlignment(Qt.AlignCenter)
        self.alias_edit.setObjectName("statTileEdit")
        self.alias_edit.textChanged.connect(self._on_alias_text_changed)
        self.alias_current_label = QLabel("Current: -")
        self.alias_current_label.setObjectName("statTileSub")
        self.alias_current_label.setAlignment(Qt.AlignCenter)
        top_strip.addWidget(
            self._build_stat_tile("Alias", self.alias_edit, self.alias_current_label), 1,
        )

        self.money_edit = QLineEdit()
        self.money_edit.setPlaceholderText("0")
        self.money_edit.setValidator(self._profile_number_validator)
        self.money_edit.setAlignment(Qt.AlignCenter)
        self.money_edit.setObjectName("statTileEdit")
        self.money_edit.editingFinished.connect(self.on_money_edit_finished)
        self.money_current_label = QLabel("Current: -")
        self.money_current_label.setObjectName("statTileSub")
        self.money_current_label.setAlignment(Qt.AlignCenter)
        top_strip.addWidget(
            self._build_stat_tile("Money", self.money_edit, self.money_current_label), 1,
        )

        layout.addLayout(top_strip)

        # ── Bounty strip: Total Bounty, Escapes, Busts ─────────
        bounty_strip = QHBoxLayout()
        bounty_strip.setSpacing(10)

        self.total_bounty_label = QLabel("-")
        self.total_bounty_label.setObjectName("statTileValue")
        self.total_bounty_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.total_bounty_label.setAlignment(Qt.AlignCenter)
        self.total_bounty_current_label = QLabel("Current: -")
        self.total_bounty_current_label.setObjectName("statTileSub")
        self.total_bounty_current_label.setAlignment(Qt.AlignCenter)
        bounty_strip.addWidget(
            self._build_stat_tile("Total Bounty", self.total_bounty_label, self.total_bounty_current_label), 1,
        )

        self.escaped_total_label = QLabel("-")
        self.escaped_total_label.setObjectName("statTileValue")
        self.escaped_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.escaped_total_label.setAlignment(Qt.AlignCenter)
        self.escaped_total_current_label = QLabel("Current: -")
        self.escaped_total_current_label.setObjectName("statTileSub")
        self.escaped_total_current_label.setAlignment(Qt.AlignCenter)
        bounty_strip.addWidget(
            self._build_stat_tile("Escapes", self.escaped_total_label, self.escaped_total_current_label), 1,
        )

        self.busted_total_label = QLabel("-")
        self.busted_total_label.setObjectName("statTileValue")
        self.busted_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.busted_total_label.setAlignment(Qt.AlignCenter)
        self.busted_total_current_label = QLabel("Current: -")
        self.busted_total_current_label.setObjectName("statTileSub")
        self.busted_total_current_label.setAlignment(Qt.AlignCenter)
        bounty_strip.addWidget(
            self._build_stat_tile("Busts", self.busted_total_label, self.busted_total_current_label), 1,
        )

        layout.addLayout(bounty_strip)
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

    def _set_profile_text_edit(self, edit: QLineEdit, value: str, enabled: bool) -> None:
        edit.blockSignals(True)
        edit.setText(value if enabled else "")
        edit.setEnabled(enabled)
        edit.blockSignals(False)

    def _profile_alias_active_limit(self) -> int:
        return SaveFile.PROFILE_ALIAS_MAX_LEN if self.unlock_profile_alias_16 else SaveFile.PROFILE_ALIAS_DEFAULT_LEN

    def _profile_alias_should_lock(self, text: str) -> bool:
        return not self.unlock_profile_alias_16 and len(text) > SaveFile.PROFILE_ALIAS_DEFAULT_LEN

    def _evaluate_profile_alias_state(self, text: str) -> tuple[Optional[str], Optional[str]]:
        if not text.isascii():
            return ("ASCII characters only", None)

        if len(text) > SaveFile.PROFILE_ALIAS_MAX_LEN:
            if text == self.have_profile_alias and not self.unlock_profile_alias_16:
                return (
                    None,
                    f"Locked: current alias exceeds the safe {SaveFile.PROFILE_ALIAS_MAX_LEN}-character limit. Enable unlock to shorten it.",
                )
            return (
                f"Alias longer than {SaveFile.PROFILE_ALIAS_MAX_LEN} is unsafe. Shorten it before Apply.",
                None,
            )

        if not self.unlock_profile_alias_16 and len(text) > SaveFile.PROFILE_ALIAS_DEFAULT_LEN:
            if text != self.have_profile_alias:
                return (
                    f"Default mode allows up to {SaveFile.PROFILE_ALIAS_DEFAULT_LEN} characters. Enable unlock up to {SaveFile.PROFILE_ALIAS_MAX_LEN} in Settings.",
                    None,
                )
            return (
                None,
                f"Locked: enable unlock to edit aliases above {SaveFile.PROFILE_ALIAS_DEFAULT_LEN} characters.",
            )

        return (None, None)

    def _sync_profile_alias_edit_mode(self, text: str, loaded: bool) -> None:
        self.alias_edit.blockSignals(True)
        self.alias_edit.setEnabled(loaded)
        self.alias_edit.setReadOnly(bool(loaded and self._profile_alias_should_lock(text)))
        self.alias_edit.setMaxLength(max(self._profile_alias_active_limit(), len(text)))
        self.alias_edit.blockSignals(False)

    def _set_profile_alias_edit(self, value: str, enabled: bool) -> None:
        self.alias_edit.blockSignals(True)
        self.alias_edit.setEnabled(enabled)
        self.alias_edit.setReadOnly(bool(enabled and self._profile_alias_should_lock(value)))
        self.alias_edit.setMaxLength(max(self._profile_alias_active_limit(), len(value)))
        self.alias_edit.setText(value if enabled else "")
        self.alias_edit.blockSignals(False)

    def _sync_profile_alias_feedback(self, text: Optional[str] = None) -> None:
        loaded = self.savefile is not None
        alias_text = text if text is not None else (
            self.staged_state.profile_alias.current(self.have_profile_alias)
        )
        self._sync_profile_alias_edit_mode(alias_text, loaded)
        error, notice = self._evaluate_profile_alias_state(alias_text) if loaded else (None, None)
        self.profile_alias_error = error
        has_error = bool(error)
        if has_error:
            self.alias_current_label.setText(error)
        elif notice:
            self.alias_current_label.setText(notice)
        else:
            self.alias_current_label.setText(
                f"Current: {self.have_profile_alias}" if loaded else "Current: -"
            )
        alias_tip = error or notice or ""
        self.alias_current_label.setToolTip(alias_tip)
        self.alias_current_label.setProperty("status", "error" if has_error else "")
        self.alias_current_label.style().unpolish(self.alias_current_label)
        self.alias_current_label.style().polish(self.alias_current_label)
        self.alias_edit.setProperty("invalid", has_error)
        self.alias_edit.setToolTip(alias_tip)
        self.alias_edit.style().unpolish(self.alias_edit)
        self.alias_edit.style().polish(self.alias_edit)

    def _on_alias_text_changed(self, text: str) -> None:
        if self._profile_refreshing or not self.savefile:
            return
        self.staged_state.profile_alias.set(text)
        self._sync_profile_alias_feedback(text)
        self._update_action_states()

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
        fallback = self.staged_state.money.current(self.have_money)
        value = self._commit_profile_edit(self.money_edit, fallback)
        if value is None:
            return
        self.staged_state.money.set(value)
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
            money_value = self.staged_state.money.current(self.have_money)
            self._set_profile_line_edit(self.money_edit, money_value, loaded)
            self.money_current_label.setText(
                self._format_current_value(self.have_money) if loaded else "Current: -"
            )
            alias_value = self.staged_state.profile_alias.current(self.have_profile_alias)
            self._set_profile_alias_edit(alias_value, loaded)
            self._sync_profile_alias_feedback(alias_value)
            self._refresh_garage_totals(loaded)
            self._refresh_profile_summary(loaded)
            self._refresh_garage_page(reason="data_change")
        finally:
            self._profile_refreshing = False

    def _has_profile_pending_changes(self) -> bool:
        if self.savefile is None:
            return False
        if self.staged_state.money.has_pending(self.have_money):
            return True
        return self.staged_state.profile_alias.has_pending(self.have_profile_alias)
