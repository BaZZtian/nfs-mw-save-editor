"""Garage page: transfer cards, allocator, pink-slip badges, garage handlers."""
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models import (
    GarageAllocatorSnapshot,
    OwnedCarTransferPlan,
    ResolvedTransferCarEntry,
    SnapshotInjectionPlan,
    SnapshotLibraryEntry,
)
from core.savefile import SaveFile
from resources import resource_path
from ui.pages.constants import *
from ui.widgets import ShimmerFrame


class GarageMixin:
    def _build_garage_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        hint = QLabel(
            "Transfer operator view. Move existing owned cars between Career, My Cars, and Pink Slip while "
            "tracking validated empty slots for future injection work."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.garage_search = QLineEdit()
        self.garage_search.setPlaceholderText("Search garage by model name...")
        self.garage_search.textChanged.connect(self.on_garage_search_changed)
        controls.addWidget(self.garage_search, 1)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.garage_filter_buttons: Dict[str, QPushButton] = {}
        self.garage_filter_group = QButtonGroup(self)
        self.garage_filter_group.setExclusive(True)
        for label in ["All", "Career", "My Cars", "Pink Slip", "Unknown"]:
            btn = QPushButton(label)
            btn.setObjectName("catButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, source=label: self._select_garage_filter(source))
            self.garage_filter_group.addButton(btn)
            self.garage_filter_buttons[label] = btn
            filter_row.addWidget(btn)
        self.garage_filter_buttons["All"].setChecked(True)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.garage_alloc_frame = QFrame()
        self.garage_alloc_frame.setObjectName("statTile")
        alloc_row = QHBoxLayout(self.garage_alloc_frame)
        alloc_row.setContentsMargins(12, 10, 12, 10)
        alloc_row.setSpacing(12)
        self.garage_alloc_owned = self._make_stat_badge("Owned empty: -")
        self.garage_alloc_career = self._make_stat_badge("Career empty: -")
        self.garage_alloc_blocked = self._make_stat_badge("Blocked: -")
        alloc_row.addWidget(self.garage_alloc_owned, 0, Qt.AlignLeft)
        alloc_row.addWidget(self.garage_alloc_career, 0, Qt.AlignLeft)
        alloc_row.addWidget(self.garage_alloc_blocked, 0, Qt.AlignLeft)
        alloc_row.addStretch(1)
        layout.addWidget(self.garage_alloc_frame)

        self.garage_cards = QWidget()
        self.garage_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.garage_cards_layout = QGridLayout(self.garage_cards)
        self.garage_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.garage_cards_layout.setHorizontalSpacing(14)
        self.garage_cards_layout.setVerticalSpacing(14)
        self.garage_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.garage_cards_scroll = QScrollArea()
        self.garage_cards_scroll.setObjectName("cardScroll")
        self.garage_cards_scroll.setWidgetResizable(True)
        self.garage_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.garage_cards_scroll.setWidget(self.garage_cards)
        layout.addWidget(self.garage_cards_scroll, 1)

        self.garage_diag_label = self._section_label("Unlinked Pursuit Diagnostics")
        layout.addWidget(self.garage_diag_label)
        self.garage_diag_text = QTextEdit()
        self.garage_diag_text.setReadOnly(True)
        self.garage_diag_text.setMinimumHeight(92)
        self.garage_diag_text.setMaximumHeight(140)
        self.garage_diag_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.garage_diag_text)

        self.garage_card_edits: Dict[int, QLineEdit] = {}
        self.garage_card_current_labels: Dict[int, QLabel] = {}
        self._garage_card_widgets_page: Dict[int, QFrame] = {}
        self._rebuild_garage_cards()
        self._sync_garage_diagnostics_visibility()
        return w

    def _current_owned_locations(self) -> Dict[int, int]:
        want_map = self.want_owned_locations or {}
        return {
            entry.abs_off: int(want_map.get(entry.abs_off, self.have_owned_locations.get(entry.abs_off, entry.location_bits)))
            for entry in self.garage_transfer_entries
        }

    def _current_owned_career_slots(self) -> Dict[int, int]:
        want_map = self.want_owned_career_slots or {}
        return {
            entry.abs_off: int(want_map.get(entry.abs_off, self.have_owned_career_slots.get(entry.abs_off, entry.career_slot)))
            for entry in self.garage_transfer_entries
        }

    def _current_cleared_pursuit_slots(self) -> set[int]:
        if self.savefile is None or self.garage_detection_error:
            return set()
        current_locations = self._current_owned_locations()
        current_career_slots = self._current_owned_career_slots()
        cleared: set[int] = set()
        for entry in self.garage_transfer_entries:
            have_loc = self.have_owned_locations.get(entry.abs_off, entry.location_bits)
            have_slot = self.have_owned_career_slots.get(entry.abs_off, entry.career_slot)
            want_loc = current_locations.get(entry.abs_off, have_loc)
            want_slot = current_career_slots.get(entry.abs_off, have_slot)
            if have_slot == SaveFile.EMPTY_CAREER_SLOT:
                continue
            if int(want_loc) == SaveFile.MY_CARS_FLAG or int(want_slot) == SaveFile.EMPTY_CAREER_SLOT:
                cleared.add(int(have_slot))
        return cleared

    def _current_transfer_entries(self) -> List[ResolvedTransferCarEntry]:
        if not self.savefile:
            return []
        return self.savefile.get_transfer_car_entries(
            location_overrides=self._current_owned_locations(),
            career_slot_overrides=self._current_owned_career_slots(),
            cleared_slots=self._current_cleared_pursuit_slots(),
        )

    def _snapshot_library_by_id(self) -> Dict[str, SnapshotLibraryEntry]:
        return {entry.snapshot_id: entry for entry in self.snapshot_library}

    def _ordered_snapshot_injection_items(
        self,
        extra: Optional[Tuple[str, str]] = None,
    ) -> List[Tuple[str, str]]:
        staged = dict(self.want_snapshot_injections)
        if extra is not None:
            staged[str(extra[0])] = str(extra[1])
        ordered: List[Tuple[str, str]] = []
        for entry in self.snapshot_library:
            target_mode = staged.get(entry.snapshot_id)
            if target_mode:
                ordered.append((entry.snapshot_id, target_mode))
        return ordered

    def _current_snapshot_injection_plans(
        self,
        extra: Optional[Tuple[str, str]] = None,
    ) -> Tuple[Dict[str, SnapshotInjectionPlan], Set[int], Set[int], Set[int]]:
        if not self.savefile or self.snapshot_library_error:
            return {}, set(), set(), set()
        library_by_id = self._snapshot_library_by_id()
        reserved_owned: Set[int] = set()
        reserved_parts: Set[int] = set()
        reserved_career: Set[int] = set()
        plans: Dict[str, SnapshotInjectionPlan] = {}
        for snapshot_id, target_mode in self._ordered_snapshot_injection_items(extra=extra):
            entry = library_by_id.get(snapshot_id)
            if entry is None:
                continue
            plan = self.savefile.plan_snapshot_injection(
                entry,
                target_mode,
                location_overrides=self._current_owned_locations(),
                career_slot_overrides=self._current_owned_career_slots(),
                cleared_slots=self._current_cleared_pursuit_slots(),
                reserved_owned_abs_offs=reserved_owned,
                reserved_parts_slots=reserved_parts,
                reserved_career_slots=reserved_career,
            )
            plans[snapshot_id] = plan
            if plan.refusal_reason is None:
                if plan.target_owned_abs_off is not None:
                    reserved_owned.add(plan.target_owned_abs_off)
                if plan.target_parts_slot is not None:
                    reserved_parts.add(plan.target_parts_slot)
                if plan.target_career_slot is not None:
                    reserved_career.add(plan.target_career_slot)
        return plans, reserved_owned, reserved_parts, reserved_career

    def _current_allocator_snapshot(self) -> Optional[GarageAllocatorSnapshot]:
        if not self.savefile:
            return None
        _, reserved_owned, _, reserved_career = self._current_snapshot_injection_plans()
        return self.savefile.get_garage_allocator_snapshot(
            location_overrides=self._current_owned_locations(),
            career_slot_overrides=self._current_owned_career_slots(),
            cleared_slots=self._current_cleared_pursuit_slots(),
            reserved_owned_abs_offs=reserved_owned,
            reserved_career_slots=reserved_career,
        )

    def _garage_transfer_plan_for(self, abs_off: int, target_mode: str) -> OwnedCarTransferPlan:
        if not self.savefile:
            raise ValueError("No save loaded")
        _, _, _, reserved_career = self._current_snapshot_injection_plans()
        return self.savefile.plan_owned_car_transfer(
            abs_off,
            target_mode,
            location_overrides=self._current_owned_locations(),
            career_slot_overrides=self._current_owned_career_slots(),
            cleared_slots=self._current_cleared_pursuit_slots(),
            reserved_career_slots=reserved_career,
        )

    def _garage_card_entries(self) -> List[ResolvedTransferCarEntry]:
        entries = list(self._current_transfer_entries())
        term = self.garage_search.text().strip().lower() if hasattr(self, "garage_search") else ""
        source = self.garage_filter
        filtered: List[ResolvedTransferCarEntry] = []
        for slot in entries:
            if term and term not in slot.display_name.lower():
                continue
            if source != "All":
                source_kind = slot.source_kind
                if source == "Unknown":
                    if not source_kind.startswith("Unknown"):
                        continue
                elif source_kind != source:
                    continue
            filtered.append(slot)
        return filtered

    def _garage_unlinked_entries(self):
        snapshot = self._current_allocator_snapshot()
        if snapshot is None:
            return []
        return [
            slot for slot in snapshot.career_slots
            if slot.blocked_reason == "Unlinked pursuit stats present"
        ]

    def _detect_garage_slot_columns(self) -> int:
        return self._detect_col_count("garage_cards_scroll", 300, ((1420, 3), (860, 2)))

    def _maybe_reflow_garage_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols(
            "garage_cards_scroll", "_garage_slot_columns", 300,
            ((1420, 3), (860, 2)), self._rebuild_garage_cards, force,
            post_fn=lambda: self._refresh_garage_page() if self.savefile is not None else None,
        )

    def _sync_garage_diagnostics_visibility(self) -> None:
        visible = bool(self.show_unlinked_pursuits and self.savefile is not None)
        if hasattr(self, "garage_diag_label"):
            self.garage_diag_label.setVisible(visible)
        if hasattr(self, "garage_diag_text"):
            self.garage_diag_text.setVisible(visible)

    def _current_slot_bounties(self) -> Dict[int, int]:
        want_map = self.want_slot_bounties or {}
        current = {
            slot.career_slot: want_map.get(slot.career_slot, self.have_slot_bounties.get(slot.career_slot, 0))
            for slot in self.garage_slots
        }
        for slot_index in self._current_cleared_pursuit_slots():
            current[slot_index] = 0
        return current

    def _current_slot_flags(self) -> Dict[int, int]:
        return {
            slot.career_slot: slot.location_bits
            for slot in self._current_transfer_entries()
            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
        }

    @staticmethod
    def _supports_pink_slip_toggle(flags: Optional[int]) -> bool:
        return flags in (SaveFile.CAREER_FLAG, SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)

    @staticmethod
    def _flags_to_source_kind(flags: Optional[int]) -> str:
        return SaveFile.derive_source_kind(flags)

    def _pink_slip_badge_icon(self, size: int = 14) -> QPixmap:
        if self._pink_slip_badge_pixmap is not None:
            return self._pink_slip_badge_pixmap
        icon_path = resource_path("assets", "icons", "pol", "pink_slip.png")
        pix = QPixmap(str(icon_path))
        if pix.isNull():
            self._pink_slip_badge_pixmap = QPixmap()
            return self._pink_slip_badge_pixmap
        self._pink_slip_badge_pixmap = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return self._pink_slip_badge_pixmap

    def _make_garage_source_badge(self, source_kind: str) -> QWidget:
        if source_kind == "Pink Slip":
            pix = self._pink_slip_badge_icon()
            if not pix.isNull():
                badge = ShimmerFrame()
                badge.setObjectName("pinkSlipBadge")
                badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                badge.setToolTip(source_kind)

                row = QHBoxLayout(badge)
                row.setContentsMargins(8, 5, 10, 5)
                row.setSpacing(6)

                icon_label = QLabel()
                icon_label.setObjectName("pinkSlipBadgeIcon")
                icon_label.setPixmap(pix)
                icon_label.setAlignment(Qt.AlignCenter)
                icon_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                row.addWidget(icon_label, 0, Qt.AlignVCenter)

                text_label = QLabel("Pink Slip")
                text_label.setObjectName("pinkSlipBadgeText")
                text_label.setAlignment(Qt.AlignCenter)
                text_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                row.addWidget(text_label, 0, Qt.AlignVCenter)
                return badge

        label = QLabel()
        label.setObjectName("garageCardStatBadge")
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        label.setToolTip(source_kind)

        label.setText(source_kind)
        return label

    def _garage_card_changed(self, slot_index: int) -> bool:
        have_bounty = self.have_slot_bounties.get(slot_index, 0)
        want_bounty = self._current_slot_bounties().get(slot_index, have_bounty)
        return want_bounty != have_bounty

    def _garage_transfer_changed(self, abs_off: int) -> bool:
        return (
            int(self._current_owned_locations().get(abs_off, self.have_owned_locations.get(abs_off, 0)))
            != int(self.have_owned_locations.get(abs_off, 0))
            or int(self._current_owned_career_slots().get(abs_off, self.have_owned_career_slots.get(abs_off, SaveFile.EMPTY_CAREER_SLOT)))
            != int(self.have_owned_career_slots.get(abs_off, SaveFile.EMPTY_CAREER_SLOT))
        )

    def _has_garage_transfer_pending_changes(self) -> bool:
        if self.savefile is None or self.garage_detection_error:
            return False
        return bool(self._current_cleared_pursuit_slots()) or any(
            self._garage_transfer_changed(entry.abs_off) for entry in self.garage_transfer_entries
        )

    def _rebuild_garage_cards(self) -> None:
        if not hasattr(self, "garage_cards_layout"):
            return
        self._clear_layout(self.garage_cards_layout)
        self.garage_card_edits = {}
        self.garage_card_current_labels = {}
        self._garage_card_widgets_page = {}
        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect real garage vehicles.")
            label.setObjectName("mutedLabel")
            self.garage_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.garage_detection_error:
            label = QLabel(f"Garage manager disabled: {self.garage_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_slots = self._garage_card_entries()
        if not visible_slots:
            label = QLabel("No garage cars match the current search/filter.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, slot in enumerate(visible_slots):
            changed = self._garage_transfer_changed(slot.abs_off) or (
                slot.career_slot != SaveFile.EMPTY_CAREER_SLOT and self._garage_card_changed(slot.career_slot)
            )
            card = QFrame()
            card.setObjectName("garageCard")
            card.setProperty("changed", changed)
            card.setProperty("occupied", True)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(240)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_text = f"Career Slot {slot.career_slot + 1}" if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT else f"Car #{slot.car_number:02X}"
            slot_label = QLabel(slot_text)
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)
            source_label = self._make_garage_source_badge(slot.source_kind)
            card.setProperty("pinkslip", slot.source_kind == "Pink Slip")
            header_row.addWidget(slot_label, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_label, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            name_label = QLabel(slot.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            for text in [
                f"Parts Slot {slot.parts_slot}",
                f"Loc 0x{slot.location_bits:02X}",
                f"Misc 0x{slot.misc_bits:02X}",
            ]:
                badge = QLabel(text)
                badge.setObjectName("garageCardStatBadge")
                badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                badge.setAlignment(Qt.AlignCenter)
                meta_row.addWidget(badge, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            plans = {
                "my_cars": self._garage_transfer_plan_for(slot.abs_off, "my_cars"),
                "career": self._garage_transfer_plan_for(slot.abs_off, "career"),
            }
            relevant_plans = []
            if not slot.is_my_cars:
                btn_my_cars = QPushButton("Move to My Cars")
                btn_my_cars.setObjectName("partsBulkBtn")
                btn_my_cars.setEnabled(plans["my_cars"].refusal_reason is None)
                btn_my_cars.setToolTip(
                    plans["my_cars"].refusal_reason
                    or "Clear the linked pursuit stats, free that career slot, and move this car into My Cars."
                )
                btn_my_cars.clicked.connect(lambda _, abs_off=slot.abs_off: self.on_garage_transfer_requested(abs_off, "my_cars"))
                action_row.addWidget(btn_my_cars)
                relevant_plans.append(plans["my_cars"])

            if slot.is_my_cars:
                btn_career = QPushButton("Move to Career")
                btn_career.setObjectName("partsBulkBtn")
                btn_career.setEnabled(plans["career"].refusal_reason is None)
                btn_career.setToolTip(plans["career"].refusal_reason or "Link this car to a validated empty career slot.")
                btn_career.clicked.connect(lambda _, abs_off=slot.abs_off: self.on_garage_transfer_requested(abs_off, "career"))
                action_row.addWidget(btn_career)
                relevant_plans.append(plans["career"])
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            if plans["my_cars"].clears_pursuit_slot and plans["my_cars"].cleared_source_career_slot is not None:
                release_note = QLabel(
                    f"Move to My Cars will free Career Slot {plans['my_cars'].cleared_source_career_slot + 1}."
                )
                release_note.setObjectName("mutedLabel")
                release_note.setWordWrap(True)
                card_layout.addWidget(release_note)

            if relevant_plans and all(plan.refusal_reason for plan in relevant_plans):
                blocker = QLabel(next(plan.refusal_reason for plan in relevant_plans if plan.refusal_reason))
                blocker.setObjectName("mutedLabel")
                blocker.setWordWrap(True)
                card_layout.addWidget(blocker)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            bounty_label = QLabel("Bounty")
            bounty_label.setObjectName("garageCardFieldLabel")
            bounty_label.setAlignment(Qt.AlignCenter)

            edit = QLineEdit()
            edit.setPlaceholderText("0")
            edit.setValidator(self._profile_number_validator)
            edit.setAlignment(Qt.AlignCenter)
            edit.setObjectName("garageCardEdit")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if slot.has_pursuit_link and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                edit.editingFinished.connect(lambda idx=slot.career_slot: self.on_garage_slot_edit_finished(idx))
            else:
                edit.setEnabled(False)

            current = QLabel("Current: -")
            current.setObjectName("garageCardCurrent")
            current.setAlignment(Qt.AlignCenter)

            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                self.garage_card_edits[slot.career_slot] = edit
                self.garage_card_current_labels[slot.career_slot] = current
            self._garage_card_widgets_page[slot.abs_off] = card

            card_layout.addWidget(bounty_label)
            card_layout.addWidget(edit)
            card_layout.addWidget(current)

            stats_row = QHBoxLayout()
            stats_row.setSpacing(8)
            stats_row.setContentsMargins(0, 4, 0, 0)

            esc_lbl = QLabel(f"Escaped  {slot.escaped if slot.escaped is not None else '-'}")
            esc_lbl.setObjectName("garageCardStatBadge")
            esc_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            esc_lbl.setAlignment(Qt.AlignCenter)
            bust_lbl = QLabel(f"Busted  {slot.busted if slot.busted is not None else '-'}")
            bust_lbl.setObjectName("garageCardStatBadge")
            bust_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bust_lbl.setAlignment(Qt.AlignCenter)
            stats_row.addWidget(esc_lbl, 0, Qt.AlignLeft)
            stats_row.addStretch(1)
            stats_row.addWidget(bust_lbl, 0, Qt.AlignRight)
            card_layout.addLayout(stats_row)

            row = idx // columns
            col = idx % columns
            self.garage_cards_layout.addWidget(card, row, col)

        for col in range(columns):
            self.garage_cards_layout.setColumnStretch(col, 1)

    def _refresh_garage_page(self) -> None:
        loaded = self.savefile is not None
        if hasattr(self, "chk_show_unlinked_pursuits"):
            self.chk_show_unlinked_pursuits.blockSignals(True)
            self.chk_show_unlinked_pursuits.setChecked(self.show_unlinked_pursuits)
            self.chk_show_unlinked_pursuits.setEnabled(loaded)
            self.chk_show_unlinked_pursuits.blockSignals(False)

        snapshot = self._current_allocator_snapshot() if loaded else None
        if snapshot is None:
            self.garage_alloc_owned.setText("Owned empty: -")
            self.garage_alloc_career.setText("Career empty: -")
            self.garage_alloc_blocked.setText("Blocked: -")
        else:
            self.garage_alloc_owned.setText(f"Owned empty: {len(snapshot.reusable_owned_slots)}")
            self.garage_alloc_career.setText(f"Career empty: {len(snapshot.reusable_career_slots)}")
            blocked_total = len(snapshot.blocked_owned_slots) + len(snapshot.blocked_career_slots)
            self.garage_alloc_blocked.setText(f"Blocked: {blocked_total}")

        self._sync_garage_diagnostics_visibility()
        self._rebuild_garage_cards()

        if not loaded:
            if hasattr(self, "garage_diag_text"):
                self.garage_diag_text.setText("")
            return

        current_bounties = self._current_slot_bounties()
        for slot in self._garage_card_entries():
            edit = self.garage_card_edits.get(slot.career_slot) if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT else None
            current_label = self.garage_card_current_labels.get(slot.career_slot) if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT else None
            if edit is not None:
                self._set_profile_line_edit(edit, current_bounties.get(slot.career_slot, int(slot.bounty or 0)), True)
            if current_label is not None:
                current_label.setText(
                    self._format_current_value(self.have_slot_bounties.get(slot.career_slot, int(slot.bounty or 0)))
                )
            card_w = self._garage_card_widgets_page.get(slot.abs_off)
            if card_w is not None:
                changed = self._garage_transfer_changed(slot.abs_off) or (
                    slot.career_slot != SaveFile.EMPTY_CAREER_SLOT and self._garage_card_changed(slot.career_slot)
                )
                card_w.setProperty("changed", changed)
                card_w.setProperty("pinkslip", slot.source_kind == "Pink Slip")
                card_w.style().unpolish(card_w)
                card_w.style().polish(card_w)

        if hasattr(self, "garage_diag_text"):
            entries = self._garage_unlinked_entries()
            if not entries:
                self.garage_diag_text.setText("No unlinked pursuit-only records detected.")
            else:
                lines = []
                for slot in entries:
                    lines.append(
                        f"Slot {slot.career_slot + 1}: bounty={slot.bounty}, escaped={slot.escaped}, busted={slot.busted}"
                    )
                self.garage_diag_text.setText("\n".join(lines))

    def on_garage_search_changed(self) -> None:
        self._refresh_garage_page()

    def _select_garage_filter(self, source: str) -> None:
        self.garage_filter = source
        for label, button in self.garage_filter_buttons.items():
            button.setChecked(label == source)
        self._refresh_garage_page()

    def on_toggle_unlinked_pursuits(self) -> None:
        self.show_unlinked_pursuits = self.chk_show_unlinked_pursuits.isChecked()
        self._sync_garage_diagnostics_visibility()

    def on_garage_transfer_requested(self, abs_off: int, target_mode: str) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        try:
            plan = self._garage_transfer_plan_for(abs_off, target_mode)
        except Exception as exc:
            QMessageBox.warning(self, "Transfer unavailable", str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, "Transfer blocked", plan.refusal_reason)
            return
        if self.want_owned_locations is None:
            self.want_owned_locations = dict(self.have_owned_locations)
        if self.want_owned_career_slots is None:
            self.want_owned_career_slots = dict(self.have_owned_career_slots)
        self.want_owned_locations[abs_off] = plan.target_location_bits
        self.want_owned_career_slots[abs_off] = (
            SaveFile.EMPTY_CAREER_SLOT if plan.target_career_slot is None else int(plan.target_career_slot)
        )
        self._update_action_states()
        self._refresh_garage_page()

    def on_garage_slot_edit_finished(self, slot_index: int) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        edit = self.garage_card_edits.get(slot_index)
        if edit is None:
            return
        current_want = self._current_slot_bounties()
        fallback = current_want.get(slot_index, self.have_slot_bounties.get(slot_index, 0))
        value = self._commit_profile_edit(edit, fallback)
        if value is None:
            return
        if self.want_slot_bounties is None:
            self.want_slot_bounties = dict(self.have_slot_bounties)
        self.want_slot_bounties[slot_index] = value
        self._refresh_garage_totals(True)
        self._refresh_garage_page()
        self._update_action_states()


