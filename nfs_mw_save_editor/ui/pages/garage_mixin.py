"""Garage page: transfer cards, allocator, pink-slip badges, garage handlers."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from time import perf_counter
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
from ui.rendering import ViewportLazyGridController, refresh_widget_style
from ui.widgets import ToastNotification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GarageCardVm:
    slot: ResolvedTransferCarEntry
    projected_slot: ResolvedTransferCarEntry
    changed: bool
    is_active: bool
    current_bounty: int
    have_bounty: int
    current_heat_level: Optional[int]
    have_heat_level: Optional[int]
    plan_my_cars: OwnedCarTransferPlan
    plan_career: OwnedCarTransferPlan
    max_heat_level: int = 5


@dataclass
class GarageCardHandle:
    card: QFrame
    slot_label: QLabel
    source_label: QLabel
    pink_slip_badge: QLabel
    active_badge: QLabel
    name_label: QLabel
    parts_badge: QLabel
    loc_badge: QLabel
    misc_badge: QLabel
    move_my_cars_btn: QPushButton
    move_career_btn: QPushButton
    utility_label: QLabel
    bounty_edit: Optional[QLineEdit]
    bounty_current_label: Optional[QLabel]
    heat_btns: Optional[List[QPushButton]]


class GarageMixin:
    def _career_empty_block_reason(self) -> str:
        return "Career garage cannot be empty; keep at least one Career car"

    def _is_career_like_state(self, location_bits: int, career_slot: int) -> bool:
        return (
            int(location_bits) in (SaveFile.CAREER_FLAG, SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
            and int(career_slot) != SaveFile.EMPTY_CAREER_SLOT
        )

    def _staged_career_vehicle_count(self) -> int:
        count = sum(
            1
            for entry in self._current_transfer_entries()
            if self._is_career_like_state(entry.location_bits, entry.career_slot)
        )
        plans, _, _, _ = self._current_snapshot_injection_plans()
        for snapshot_id, target_mode in self._ordered_snapshot_injection_items():
            plan = plans.get(snapshot_id)
            if plan is None or plan.refusal_reason:
                continue
            if str(target_mode) in ("career", "pink_slip") and plan.target_career_slot is not None:
                count += 1
        return count

    def _build_garage_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        hint = QLabel(
            "Move cars between Career and My Cars. "
            "Edit bounty and pursuit stats here."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls_frame, controls = self._make_page_controls_bar()
        self.garage_search = QLineEdit()
        self.garage_search.setPlaceholderText("Search cars by model name...")
        self.garage_search.textChanged.connect(self.on_garage_search_changed)
        filter_host = QWidget()
        filter_host.setObjectName("pageControlsSection")
        filter_row = QHBoxLayout(filter_host)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        self.garage_filter_buttons: Dict[str, QPushButton] = {}
        self.garage_filter_group = QButtonGroup(self)
        self.garage_filter_group.setExclusive(True)
        for label in ["All", "Career", "My Cars"]:
            btn = QPushButton(label)
            btn.setObjectName("filterButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, source=label: self._select_garage_filter(source))
            self.garage_filter_group.addButton(btn)
            self.garage_filter_buttons[label] = btn
            filter_row.addWidget(btn)
        self.garage_filter_buttons["All"].setChecked(True)
        controls.addWidget(filter_host, 0)
        controls.addWidget(self._make_centered_search_host(self.garage_search), 1)
        self.garage_alloc_frame = QWidget()
        self.garage_alloc_frame.setObjectName("pageControlsSection")
        alloc_row = QHBoxLayout(self.garage_alloc_frame)
        alloc_row.setContentsMargins(0, 0, 0, 0)
        alloc_row.setSpacing(8)
        self.garage_alloc_owned = self._make_stat_badge("Owned empty: -")
        self.garage_alloc_career = self._make_stat_badge("Career empty: -")
        self.garage_alloc_blocked = self._make_stat_badge("Unavailable: -")
        alloc_row.addWidget(self.garage_alloc_owned, 0, Qt.AlignLeft)
        alloc_row.addWidget(self.garage_alloc_career, 0, Qt.AlignLeft)
        alloc_row.addWidget(self.garage_alloc_blocked, 0, Qt.AlignLeft)
        controls.addWidget(self.garage_alloc_frame, 0, Qt.AlignRight)
        layout.addWidget(controls_frame)

        self.garage_warning_label = QLabel()
        self.garage_warning_label.setObjectName("contentCardNote")
        self.garage_warning_label.setWordWrap(True)
        self.garage_warning_label.setVisible(False)
        layout.addWidget(self.garage_warning_label)

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
        self.garage_cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.garage_cards_scroll.setWidget(self.garage_cards)
        layout.addWidget(self.garage_cards_scroll, 1)

        self.garage_diag_label = self._section_label("Allocator Diagnostics")
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
        self._garage_card_handles: Dict[int, GarageCardHandle] = {}
        self._garage_visible_order: List[int] = []
        self._garage_live_vm_map: Dict[int, GarageCardVm] = {}
        self._garage_render_controller = ViewportLazyGridController(
            self,
            name="Garage",
            layout=self.garage_cards_layout,
            scroll_area=self.garage_cards_scroll,
        )
        self._sync_garage_diagnostics_visibility()
        return w

    def _garage_page_visible(self) -> bool:
        return hasattr(self, "stack") and hasattr(self, "page_garage") and self.stack.currentWidget() is self.page_garage

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
            if not entry.has_pursuit_link:
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
                if plan.target_sidecar_owned_abs_off is not None:
                    reserved_owned.add(plan.target_sidecar_owned_abs_off)
                if plan.target_parts_slot is not None:
                    reserved_parts.add(plan.target_parts_slot)
                if plan.target_sidecar_parts_slot is not None:
                    reserved_parts.add(plan.target_sidecar_parts_slot)
                if plan.target_career_slot is not None:
                    reserved_career.add(plan.target_career_slot)
        return plans, reserved_owned, reserved_parts, reserved_career

    def _snapshot_injection_reallocation_messages(
        self,
        before_plans: Dict[str, SnapshotInjectionPlan],
        after_plans: Dict[str, SnapshotInjectionPlan],
    ) -> List[Tuple[str, bool]]:
        messages: List[Tuple[str, bool]] = []
        library_by_id = self._snapshot_library_by_id()
        for snapshot_id, target_mode in self._ordered_snapshot_injection_items():
            if str(target_mode) != "career":
                continue
            entry = library_by_id.get(snapshot_id)
            before = before_plans.get(snapshot_id)
            after = after_plans.get(snapshot_id)
            if entry is None or before is None or after is None:
                continue
            before_success = before.refusal_reason is None
            after_success = after.refusal_reason is None
            if before_success and after_success:
                if before.target_career_slot != after.target_career_slot and after.target_career_slot is not None:
                    messages.append((f"Build {entry.display_name} moved to slot {after.target_career_slot + 1}", False))
            elif before_success and not after_success:
                messages.append((f"Build {entry.display_name} blocked: no free slots", True))
        return messages

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

    def _garage_transfer_plan_with_context(
        self,
        abs_off: int,
        target_mode: str,
        *,
        current_locations: Dict[int, int],
        current_career_slots: Dict[int, int],
        cleared_slots: Set[int],
        reserved_career_slots: Set[int],
        staged_career_vehicle_count: int,
        desired_career_slot: Optional[int],
        allow_restore_to_nonvalidated_slot: bool,
    ) -> OwnedCarTransferPlan:
        if not self.savefile:
            raise ValueError("No save loaded")
        plan = self.savefile.plan_owned_car_transfer(
            abs_off,
            target_mode,
            location_overrides=current_locations,
            career_slot_overrides=current_career_slots,
            cleared_slots=cleared_slots,
            reserved_career_slots=reserved_career_slots,
            desired_career_slot=desired_career_slot,
            allow_restore_to_nonvalidated_slot=allow_restore_to_nonvalidated_slot,
        )
        if plan.refusal_reason is None and str(target_mode) == "my_cars":
            current_loc = int(current_locations.get(abs_off, plan.source_location_bits))
            current_slot = int(current_career_slots.get(abs_off, plan.source_career_slot))
            if self._is_career_like_state(current_loc, current_slot) and staged_career_vehicle_count <= 1:
                return replace(plan, refusal_reason=self._career_empty_block_reason())
        return plan

    def _garage_transfer_plan_for(
        self,
        abs_off: int,
        target_mode: str,
        desired_career_slot: Optional[int] = None,
        allow_restore_to_nonvalidated_slot: bool = False,
        reserved_career_slots_override: Optional[Set[int]] = None,
    ) -> OwnedCarTransferPlan:
        if reserved_career_slots_override is None:
            _, _, _, reserved_career = self._current_snapshot_injection_plans()
        else:
            reserved_career = set(reserved_career_slots_override)
        return self._garage_transfer_plan_with_context(
            abs_off,
            target_mode,
            current_locations=self._current_owned_locations(),
            current_career_slots=self._current_owned_career_slots(),
            cleared_slots=self._current_cleared_pursuit_slots(),
            reserved_career_slots=reserved_career,
            staged_career_vehicle_count=self._staged_career_vehicle_count(),
            desired_career_slot=desired_career_slot,
            allow_restore_to_nonvalidated_slot=allow_restore_to_nonvalidated_slot,
        )

    def _garage_card_entries(self) -> List[ResolvedTransferCarEntry]:
        entries = list(self.garage_transfer_entries)
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
                elif source == "Career":
                    if source_kind not in ("Career", "Pink Slip"):
                        continue
                elif source_kind != source:
                    continue
            filtered.append(slot)
        return filtered

    @staticmethod
    def _slot_status_display_text(slot) -> str:
        return str(slot.status_detail or slot.blocked_reason or slot.status_code)

    def _garage_allocator_diagnostic_sections_legacy(self) -> List[Tuple[str, List[str]]]:
        snapshot = self._current_allocator_snapshot()
        if snapshot is None:
            return []
        sections: List[Tuple[str, List[str]]] = []
        groups = [
            (
                "Career reserved",
                [
                    f"Career Slot {slot.career_slot + 1} — {self._slot_status_display_text(slot)}"
                    for slot in snapshot.reserved_career_slots
                ],
            ),
            (
                "Career blocked",
                [
                    f"Career Slot {slot.career_slot + 1} — {self._slot_status_display_text(slot)}"
                    for slot in snapshot.hard_blocked_career_slots
                ],
            ),
            (
                "Owned reserved",
                [
                    f"Owned Slot {slot.slot_index + 1} — {self._slot_status_display_text(slot)}"
                    for slot in snapshot.reserved_owned_slots
                ],
            ),
            (
                "Owned blocked",
                [
                    f"Owned Slot {slot.slot_index + 1} — {self._slot_status_display_text(slot)}"
                    for slot in snapshot.hard_blocked_owned_slots
                ],
            ),
        ]
        for title, lines in groups:
            if lines:
                sections.append((title, lines))
        return sections

    def _garage_allocator_diagnostic_sections(self) -> List[Tuple[str, List[str]]]:
        snapshot = self._current_allocator_snapshot()
        if snapshot is None:
            return []
        sections: List[Tuple[str, List[str]]] = []
        groups = [
            (
                "Career reserved",
                [
                    f"Career Slot {slot.career_slot + 1} - {self._slot_status_display_text(slot)}"
                    for slot in snapshot.reserved_career_slots
                ],
            ),
            (
                "Career blocked",
                [
                    f"Career Slot {slot.career_slot + 1} - {self._slot_status_display_text(slot)}"
                    for slot in snapshot.hard_blocked_career_slots
                ],
            ),
            (
                "Owned reserved",
                [
                    f"Owned Slot {slot.slot_index + 1} - {self._slot_status_display_text(slot)}"
                    for slot in snapshot.reserved_owned_slots
                ],
            ),
            (
                "Owned blocked",
                [
                    f"Owned Slot {slot.slot_index + 1} - {self._slot_status_display_text(slot)}"
                    for slot in snapshot.hard_blocked_owned_slots
                ],
            ),
        ]
        for title, lines in groups:
            if lines:
                sections.append((title, lines))
        return sections

    def _detect_garage_slot_columns(self) -> int:
        return self._detect_col_count("garage_cards_scroll", 300, ((1420, 3), (860, 2)))

    def _maybe_reflow_garage_rows(self, force: bool = False) -> None:
        columns = max(1, self._detect_garage_slot_columns())
        if not force and columns == getattr(self, "_garage_slot_columns", 0):
            return
        self._garage_slot_columns = columns
        if self._garage_cards_dirty or not self._garage_render_controller.has_rendered_content():
            if self._garage_page_visible():
                self._refresh_garage_page(reason="reflow")
            return
        self._garage_render_controller.reflow(columns)

    def _sync_garage_diagnostics_visibility(self) -> None:
        visible = bool(self.show_garage_allocator_diagnostics and self.savefile is not None)
        if hasattr(self, "garage_diag_label"):
            self.garage_diag_label.setVisible(visible)
        if hasattr(self, "garage_diag_text"):
            self.garage_diag_text.setVisible(visible)

    def _current_slot_heats(self) -> Dict[int, int]:
        want_map = self.want_slot_heats or {}
        return {
            slot.career_slot: want_map.get(slot.career_slot, self.have_slot_heats.get(slot.career_slot, 1))
            for slot in self.garage_slots
            if slot.occupied and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
        }

    def _pending_slot_heats(self) -> Dict[int, int]:
        if self.savefile is None or self.garage_detection_error:
            return {}
        current = self._current_slot_heats()
        pending: Dict[int, int] = {}
        for slot in self.garage_slots:
            if not slot.occupied or slot.career_slot == SaveFile.EMPTY_CAREER_SLOT:
                continue
            have = self.have_slot_heats.get(slot.career_slot, slot.heat_level)
            want = current.get(slot.career_slot, have)
            if want != have:
                pending[slot.career_slot] = want
        return pending

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
            badge = QLabel("Pink Slip")
            badge.setObjectName("pinkSlipBadgeText")
            badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            badge.setAlignment(Qt.AlignCenter)
            badge.setToolTip(source_kind)
            return badge

        label = QLabel()
        if source_kind == "Career":
            label.setObjectName("careerSourceBadge")
        elif source_kind == "My Cars":
            label.setObjectName("myCarsSourceBadge")
        else:
            label.setObjectName("contentCardStatBadge")
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        label.setToolTip(source_kind)
        label.setText(source_kind)
        return label

    def _make_active_car_badge(self) -> QLabel:
        badge = QLabel("Active")
        badge.setObjectName("activeCarBadge")
        badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        badge.setAlignment(Qt.AlignCenter)
        return badge

    def _garage_card_changed(self, slot_index: int) -> bool:
        have_bounty = self.have_slot_bounties.get(slot_index, 0)
        want_bounty = self._current_slot_bounties().get(slot_index, have_bounty)
        if want_bounty != have_bounty:
            return True
        have_heat = self.have_slot_heats.get(slot_index)
        if have_heat is not None:
            want_heat = self._current_slot_heats().get(slot_index, have_heat)
            if want_heat != have_heat:
                return True
        return False

    def _garage_transfer_changed(self, abs_off: int) -> bool:
        return (
            int(self._current_owned_locations().get(abs_off, self.have_owned_locations.get(abs_off, 0)))
            != int(self.have_owned_locations.get(abs_off, 0))
            or int(
                self._current_owned_career_slots().get(
                    abs_off,
                    self.have_owned_career_slots.get(abs_off, SaveFile.EMPTY_CAREER_SLOT),
                )
            ) != int(self.have_owned_career_slots.get(abs_off, SaveFile.EMPTY_CAREER_SLOT))
        )

    def _has_garage_transfer_pending_changes(self) -> bool:
        if self.savefile is None or self.garage_detection_error:
            return False
        return bool(self._current_cleared_pursuit_slots()) or any(
            self._garage_transfer_changed(entry.abs_off) for entry in self.garage_transfer_entries
        )

    def _has_garage_pursuit_pending_changes(self) -> bool:
        if self.savefile is None or self.garage_detection_error:
            return False
        return bool(self._pending_slot_heats())

    def _garage_empty_widget(self, _: int) -> QWidget:
        if not self.savefile:
            text = "Open a save to inspect real garage vehicles."
        elif self.garage_detection_error:
            text = f"Garage tools unavailable: {self.garage_detection_error}"
        else:
            text = "No cars match the current search or filter."
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        return label

    def _garage_card_view_models(
        self,
        entries: Optional[List[ResolvedTransferCarEntry]] = None,
    ) -> List[GarageCardVm]:
        if not self.savefile or self.garage_detection_error:
            return []
        target_entries = list(entries) if entries is not None else self._garage_card_entries()
        projected_entries_by_abs_off = {
            int(entry.abs_off): entry for entry in self._current_transfer_entries()
        }
        current_locations = self._current_owned_locations()
        current_career_slots = self._current_owned_career_slots()
        cleared_slots = self._current_cleared_pursuit_slots()
        _, _, _, reserved_career = self._current_snapshot_injection_plans()
        staged_career_vehicle_count = self._staged_career_vehicle_count()
        current_bounties = self._current_slot_bounties()
        current_heats = self._current_slot_heats()
        active_car_number = self.savefile.get_active_career_car_number()
        max_heat_level = (
            self.savefile.get_story_heat_cap()
            if hasattr(self.savefile, "get_story_heat_cap")
            else int(SaveFile.GARAGE_HEAT_MAX)
        )

        view_models: List[GarageCardVm] = []
        for slot in target_entries:
            projected_slot = projected_entries_by_abs_off.get(int(slot.abs_off), slot)
            career_slot = slot.career_slot
            view_models.append(
                GarageCardVm(
                    slot=slot,
                    projected_slot=projected_slot,
                    changed=self._garage_transfer_changed(slot.abs_off) or (
                        career_slot != SaveFile.EMPTY_CAREER_SLOT and self._garage_card_changed(career_slot)
                    ),
                    is_active=(
                        active_car_number is not None
                        and not slot.is_my_cars
                        and int(slot.car_number) == int(active_car_number)
                    ),
                    current_bounty=current_bounties.get(career_slot, int(slot.bounty or 0)),
                    have_bounty=self.have_slot_bounties.get(career_slot, int(slot.bounty or 0)),
                    current_heat_level=current_heats.get(career_slot) if slot.has_pursuit_link else None,
                    have_heat_level=self.have_slot_heats.get(career_slot) if slot.has_pursuit_link else None,
                    max_heat_level=max_heat_level,
                    plan_my_cars=self._garage_transfer_plan_with_context(
                        slot.abs_off,
                        "my_cars",
                        current_locations=current_locations,
                        current_career_slots=current_career_slots,
                        cleared_slots=cleared_slots,
                        reserved_career_slots=reserved_career,
                        staged_career_vehicle_count=staged_career_vehicle_count,
                        desired_career_slot=None,
                        allow_restore_to_nonvalidated_slot=False,
                    ),
                    plan_career=self._garage_transfer_plan_with_context(
                        slot.abs_off,
                        "career",
                        current_locations=current_locations,
                        current_career_slots=current_career_slots,
                        cleared_slots=cleared_slots,
                        reserved_career_slots=reserved_career,
                        staged_career_vehicle_count=staged_career_vehicle_count,
                        desired_career_slot=None,
                        allow_restore_to_nonvalidated_slot=False,
                    ),
                )
            )
        return view_models

    def _garage_visible_vm_map(self) -> Dict[int, GarageCardVm]:
        entry_by_abs_off = {
            int(entry.abs_off): entry for entry in self.garage_transfer_entries
        }
        frozen_entries = [
            entry_by_abs_off[key]
            for key in self._garage_visible_order
            if key in entry_by_abs_off
        ]
        return {vm.slot.abs_off: vm for vm in self._garage_card_view_models(frozen_entries)}

    def _garage_pending_transfer_summary(
        self,
        slot: ResolvedTransferCarEntry,
        projected_slot: ResolvedTransferCarEntry,
    ) -> Optional[Tuple[str, str]]:
        if not self._garage_transfer_changed(slot.abs_off):
            return None
        if projected_slot.is_my_cars or projected_slot.career_slot == SaveFile.EMPTY_CAREER_SLOT:
            return "Pending -> My Cars", "Will move to My Cars on Apply."
        slot_text = f"Career Slot {projected_slot.career_slot + 1}"
        if projected_slot.is_pink_slip:
            return "Pending -> Pink Slip", f"Will move to Pink Slip {slot_text} on Apply."
        return "Pending -> Career", f"Will move to {slot_text} on Apply."

    def _apply_garage_source_badge(self, label: QLabel, source_kind: str) -> None:
        if source_kind == "Career":
            label.setObjectName("careerSourceBadge")
        elif source_kind == "My Cars":
            label.setObjectName("myCarsSourceBadge")
        elif source_kind == "Pink Slip":
            label.setObjectName("pinkSlipBadgeText")
        else:
            label.setObjectName("contentCardStatBadge")
        label.setText(source_kind)
        label.setToolTip(source_kind)
        refresh_widget_style(label)

    def _garage_card_tooltip(self, slot: ResolvedTransferCarEntry) -> str:
        return (
            f"Parts Slot {slot.parts_slot} | Loc 0x{slot.location_bits:02X} | "
            f"Misc 0x{slot.misc_bits:02X}"
        )

    def _garage_action_tooltip(
        self,
        slot: ResolvedTransferCarEntry,
        target_mode: str,
        plan: OwnedCarTransferPlan,
    ) -> str:
        if plan.refusal_reason:
            return str(plan.refusal_reason)
        if target_mode == "my_cars":
            base = (
                "Move this car to My Cars and free its linked Career slot."
                if slot.has_pursuit_link
                else "Move this car to My Cars."
            )
        else:
            base = "Move this car into the next validated Career slot."
        if plan.warnings:
            return base + "\nWarning: " + "\n".join(plan.warnings)
        return base

    def _garage_utility_summary(self, vm: GarageCardVm) -> Tuple[str, str]:
        slot = vm.slot
        projected_slot = vm.projected_slot
        pending_transfer = self._garage_pending_transfer_summary(slot, projected_slot)
        if pending_transfer is not None:
            return pending_transfer
        visible_plan = vm.plan_career if projected_slot.is_my_cars else vm.plan_my_cars
        if visible_plan.refusal_reason:
            return "Blocked", str(visible_plan.refusal_reason)
        if visible_plan.warnings:
            return "Warning", "\n".join(visible_plan.warnings)
        if vm.plan_my_cars.clears_pursuit_slot and vm.plan_my_cars.cleared_source_career_slot is not None:
            detail = f"Moving to My Cars frees Career Slot {vm.plan_my_cars.cleared_source_career_slot + 1}."
            return f"Frees Slot {vm.plan_my_cars.cleared_source_career_slot + 1}", detail
        if (
            not projected_slot.is_my_cars
            and projected_slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            and not projected_slot.has_pursuit_link
        ):
            return "No pursuit link", "No pursuit record is linked to this car."
        return "Ready", "Action state is valid."

    def _apply_garage_card_vm(self, handle: GarageCardHandle, vm: GarageCardVm) -> None:
        slot = vm.slot
        projected_slot = vm.projected_slot
        slot_text = (
            f"Career Slot {slot.career_slot + 1}"
            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            else f"Car #{slot.car_number:02X}"
        )
        handle.card.setProperty("changed", vm.changed)
        handle.slot_label.setText(slot_text)
        if slot.is_pink_slip:
            self._apply_garage_source_badge(handle.source_label, "Career")
            self._apply_garage_source_badge(handle.pink_slip_badge, "Pink Slip")
            handle.pink_slip_badge.setVisible(True)
        else:
            self._apply_garage_source_badge(handle.source_label, slot.source_kind)
            handle.pink_slip_badge.setVisible(False)
        handle.active_badge.setVisible(vm.is_active)
        handle.name_label.setText(slot.display_name)
        handle.parts_badge.setText(f"Parts Slot {slot.parts_slot}")
        handle.loc_badge.setText(f"Loc 0x{slot.location_bits:02X}")
        handle.misc_badge.setText(f"Misc 0x{slot.misc_bits:02X}")
        handle.card.setToolTip(self._garage_card_tooltip(slot))

        handle.move_my_cars_btn.setVisible(not projected_slot.is_my_cars)
        handle.move_my_cars_btn.setEnabled(vm.plan_my_cars.refusal_reason is None)
        handle.move_my_cars_btn.setToolTip(self._garage_action_tooltip(projected_slot, "my_cars", vm.plan_my_cars))

        handle.move_career_btn.setVisible(projected_slot.is_my_cars)
        handle.move_career_btn.setEnabled(vm.plan_career.refusal_reason is None)
        handle.move_career_btn.setToolTip(self._garage_action_tooltip(projected_slot, "career", vm.plan_career))

        utility_text, utility_tooltip = self._garage_utility_summary(vm)
        handle.utility_label.setText(utility_text)
        handle.utility_label.setToolTip(utility_tooltip)

        if handle.bounty_edit is not None and handle.bounty_current_label is not None:
            edit_enabled = (
                not projected_slot.is_my_cars
                and projected_slot.has_pursuit_link
                and projected_slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            )
            handle.bounty_edit.setEnabled(edit_enabled)
            if edit_enabled:
                self._set_profile_line_edit(handle.bounty_edit, vm.current_bounty, True)
            handle.bounty_current_label.setText(self._format_current_value(vm.have_bounty))

        if handle.heat_btns is not None:
            btn_enabled = (
                not projected_slot.is_my_cars
                and projected_slot.has_pursuit_link
                and projected_slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            )
            lvl = vm.current_heat_level or 1
            for i, btn in enumerate(handle.heat_btns):
                heat_level = i + 1
                btn.setChecked(heat_level == lvl)
                btn.setEnabled(btn_enabled and heat_level <= vm.max_heat_level)
                if heat_level > vm.max_heat_level:
                    btn.setToolTip(f"Locked until later story progression. Current cap: x{vm.max_heat_level}")
                else:
                    btn.setToolTip("")

        refresh_widget_style(handle.card)

    def _build_garage_card(self, vm: GarageCardVm) -> QWidget:
        slot = vm.slot
        card, card_layout = self._make_card_frame(
            object_name="garageCard",
            changed=vm.changed,
            minimum_width=240,
            vertical_policy=QSizePolicy.Minimum,
            size_constraint=QVBoxLayout.SetMinimumSize,
        )
        card.setProperty("occupied", True)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        slot_text = (
            f"Career Slot {slot.career_slot + 1}"
            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            else f"Car #{slot.car_number:02X}"
        )
        slot_label = QLabel(slot_text)
        slot_label.setObjectName("contentCardSlot")
        slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        slot_label.setAlignment(Qt.AlignCenter)
        source_label = QLabel()
        source_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        source_label.setAlignment(Qt.AlignCenter)
        pink_slip_badge = self._make_garage_source_badge("Pink Slip")
        pink_slip_badge.setVisible(False)
        active_badge = self._make_active_car_badge()
        active_badge.setVisible(False)
        header_row.addWidget(slot_label, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        header_row.addWidget(source_label, 0, Qt.AlignRight)
        header_row.addWidget(pink_slip_badge, 0, Qt.AlignRight)
        header_row.addWidget(active_badge, 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = QLabel(slot.display_name)
        name_label.setObjectName("contentCardMeta")
        name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        parts_badge = QLabel()
        parts_badge.setObjectName("contentCardStatBadge")
        parts_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        parts_badge.setAlignment(Qt.AlignCenter)
        loc_badge = QLabel()
        loc_badge.setObjectName("contentCardStatBadge")
        loc_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        loc_badge.setAlignment(Qt.AlignCenter)
        misc_badge = QLabel()
        misc_badge.setObjectName("contentCardStatBadge")
        misc_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        misc_badge.setAlignment(Qt.AlignCenter)
        for badge in [parts_badge, loc_badge, misc_badge]:
            meta_row.addWidget(badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)
        card_layout.addLayout(meta_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        btn_my_cars = self._make_card_action_button("Move to My Cars")
        btn_my_cars.clicked.connect(
            lambda _, abs_off=slot.abs_off: self.on_garage_transfer_requested(abs_off, "my_cars")
        )
        action_row.addWidget(btn_my_cars)
        btn_career = self._make_card_action_button("Move to Career")
        btn_career.clicked.connect(
            lambda _, abs_off=slot.abs_off: self.on_garage_transfer_requested(abs_off, "career")
        )
        action_row.addWidget(btn_career)
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        utility_label = QLabel()
        utility_label.setObjectName("mutedLabel")
        utility_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card_layout.addWidget(utility_label)

        self._garage_card_widgets_page[slot.abs_off] = card

        bounty_edit: Optional[QLineEdit] = None
        bounty_current_label: Optional[QLabel] = None
        heat_buttons: Optional[List[QPushButton]] = None
        if not slot.is_my_cars and slot.has_pursuit_link:
            card_layout.addWidget(self._make_card_separator())

            # Heat level selector
            card_layout.addWidget(self._make_card_field_label("Heat"))

            heat_row = QWidget()
            heat_row.setObjectName("garageHeatRow")
            heat_row_layout = QHBoxLayout(heat_row)
            heat_row_layout.setContentsMargins(0, 0, 0, 0)
            heat_row_layout.setSpacing(4)

            heat_group = QButtonGroup(heat_row)
            heat_group.setExclusive(True)
            heat_buttons = []

            for lvl in range(1, 6):
                btn = QPushButton(f"x{lvl}")
                btn.setCheckable(True)
                btn.setObjectName("heatBtn")
                if lvl == 1:
                    btn.setProperty("segmentPos", "first")
                elif lvl == 5:
                    btn.setProperty("segmentPos", "last")
                else:
                    btn.setProperty("segmentPos", "middle")
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                    btn.clicked.connect(lambda _, s=slot.career_slot, l=lvl: self.on_garage_heat_changed(s, l))
                else:
                    btn.setEnabled(False)
                heat_group.addButton(btn)
                heat_row_layout.addWidget(btn)
                heat_buttons.append(btn)

            current_lvl = vm.current_heat_level or 1
            heat_buttons[current_lvl - 1].setChecked(True)
            for i, btn in enumerate(heat_buttons):
                heat_level = i + 1
                if heat_level > vm.max_heat_level:
                    btn.setEnabled(False)
                    btn.setToolTip(f"Locked until later story progression. Current cap: x{vm.max_heat_level}")
            card_layout.addWidget(heat_row)

            edit = QLineEdit()
            edit.setPlaceholderText("0")
            edit.setValidator(self._profile_number_validator)
            edit.setAlignment(Qt.AlignCenter)
            edit.setObjectName("garageCardEdit")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                edit.editingFinished.connect(lambda idx=slot.career_slot: self.on_garage_slot_edit_finished(idx))

            current = QLabel(self._format_current_value(vm.have_bounty))
            current.setObjectName("garageCardCurrent")
            current.setAlignment(Qt.AlignCenter)
            bounty_edit = edit
            bounty_current_label = current

            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT:
                self.garage_card_edits[slot.career_slot] = edit
                self.garage_card_current_labels[slot.career_slot] = current

            card_layout.addWidget(self._make_card_field_label("Bounty"))
            card_layout.addWidget(edit)
            card_layout.addWidget(current)
            self._set_profile_line_edit(edit, vm.current_bounty, True)

            stats_row = QHBoxLayout()
            stats_row.setSpacing(8)
            stats_row.setContentsMargins(0, 4, 0, 0)

            esc_lbl = QLabel(f"Escaped  {slot.escaped if slot.escaped is not None else '-'}")
            esc_lbl.setObjectName("contentCardStatBadge")
            esc_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            esc_lbl.setAlignment(Qt.AlignCenter)
            bust_lbl = QLabel(f"Busted  {slot.busted if slot.busted is not None else '-'}")
            bust_lbl.setObjectName("contentCardStatBadge")
            bust_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bust_lbl.setAlignment(Qt.AlignCenter)
            stats_row.addWidget(esc_lbl, 0, Qt.AlignLeft)
            stats_row.addStretch(1)
            stats_row.addWidget(bust_lbl, 0, Qt.AlignRight)
            card_layout.addLayout(stats_row)

        handle = GarageCardHandle(
            card=card,
            slot_label=slot_label,
            source_label=source_label,
            pink_slip_badge=pink_slip_badge,
            active_badge=active_badge,
            name_label=name_label,
            parts_badge=parts_badge,
            loc_badge=loc_badge,
            misc_badge=misc_badge,
            move_my_cars_btn=btn_my_cars,
            move_career_btn=btn_career,
            utility_label=utility_label,
            bounty_edit=bounty_edit,
            bounty_current_label=bounty_current_label,
            heat_btns=heat_buttons,
        )
        self._garage_card_handles[slot.abs_off] = handle
        self._apply_garage_card_vm(handle, vm)

        card.setMinimumHeight(card.sizeHint().height() + 4)
        refresh_widget_style(card)
        return card

    def _build_garage_card_for_key(self, abs_off: int) -> QWidget:
        vm = self._garage_live_vm_map.get(int(abs_off))
        if vm is None:
            raise KeyError(f"Missing garage VM for abs_off={abs_off}")
        return self._build_garage_card(vm)

    def _rebuild_garage_cards(self, *, animate: bool = False, reset_scroll: bool = False) -> None:
        self.garage_card_edits = {}
        self.garage_card_current_labels = {}
        self._garage_card_widgets_page = {}
        self._garage_card_handles = {}
        view_models = self._garage_card_view_models()
        self._garage_visible_order = [vm.slot.abs_off for vm in view_models]
        self._garage_live_vm_map = {vm.slot.abs_off: vm for vm in view_models}
        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns
        self._garage_render_controller.schedule_render(
            self._garage_visible_order,
            build_widget=self._build_garage_card_for_key,
            columns=columns,
            empty_widget_factory=self._garage_empty_widget,
            animate=animate,
            reset_scroll=reset_scroll,
        )
        self._garage_cards_dirty = False

    def _refresh_garage_diagnostics_text(self) -> None:
        if not hasattr(self, "garage_diag_text"):
            return
        if self.savefile is None:
            self.garage_diag_text.setText("")
            return
        sections = self._garage_allocator_diagnostic_sections()
        if not sections:
            self.garage_diag_text.setText("No allocator issues detected.")
            return
        blocks = [f"{title}\n" + "\n".join(lines) for title, lines in sections]
        self.garage_diag_text.setText("\n\n".join(blocks))

    def _sync_garage_summary_chrome(self, *, loaded: bool) -> None:
        snapshot = self._current_allocator_snapshot() if loaded else None
        if snapshot is None:
            self.garage_alloc_owned.setText("Owned empty: -")
            self.garage_alloc_career.setText("Career empty: -")
            self.garage_alloc_blocked.setText("Unavailable: -")
            self.garage_alloc_owned.setToolTip("")
            self.garage_alloc_career.setToolTip("")
            self.garage_alloc_blocked.setToolTip("")
            if hasattr(self, "garage_warning_label"):
                self.garage_warning_label.clear()
                self.garage_warning_label.setVisible(False)
        else:
            self.garage_alloc_owned.setText(f"Owned empty: {len(snapshot.reusable_owned_slots)}")
            self.garage_alloc_career.setText(f"Career empty: {len(snapshot.reusable_career_slots)}")
            unavailable_total = len(snapshot.unavailable_owned_slots) + len(snapshot.unavailable_career_slots)
            self.garage_alloc_blocked.setText(f"Unavailable: {unavailable_total}")
            tooltip = self._allocator_unavailable_tooltip(snapshot)
            self.garage_alloc_owned.setToolTip(tooltip)
            self.garage_alloc_career.setToolTip(tooltip)
            self.garage_alloc_blocked.setToolTip(tooltip)
            if hasattr(self, "garage_warning_label"):
                warning = SaveFile.career_pool_warning_text(self._staged_career_vehicle_count())
                if warning:
                    self.garage_warning_label.setText(warning)
                    self.garage_warning_label.setVisible(True)
                else:
                    self.garage_warning_label.clear()
                    self.garage_warning_label.setVisible(False)
        self._sync_garage_diagnostics_visibility()
        self._refresh_garage_diagnostics_text()

    def _patch_garage_cards_in_place(self) -> None:
        if not self._garage_page_visible():
            self._mark_garage_cards_dirty()
            return
        started = perf_counter()
        vm_map = self._garage_visible_vm_map()
        self._garage_live_vm_map.update(vm_map)
        patched = 0
        for abs_off, handle in list(self._garage_card_handles.items()):
            vm = vm_map.get(abs_off)
            if vm is None:
                continue
            self._apply_garage_card_vm(handle, vm)
            patched += 1
        self._garage_cards_dirty = True
        logger.debug("Garage interactive patch: %d card(s) in %d ms", patched, int((perf_counter() - started) * 1000))

    def _refresh_garage_page(self, reason: str = "data_change") -> None:
        loaded = self.savefile is not None
        if hasattr(self, "chk_show_garage_allocator_diagnostics"):
            self.chk_show_garage_allocator_diagnostics.blockSignals(True)
            self.chk_show_garage_allocator_diagnostics.setChecked(self.show_garage_allocator_diagnostics)
            self.chk_show_garage_allocator_diagnostics.setEnabled(loaded)
            self.chk_show_garage_allocator_diagnostics.blockSignals(False)

        if not self._garage_page_visible():
            self._mark_garage_cards_dirty()
            return

        self._sync_garage_summary_chrome(loaded=loaded)

        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns
        controller = self._garage_render_controller
        if (
            reason in {"page_enter", "reflow"}
            and not self._garage_cards_dirty
            and controller.has_rendered_content()
            and not controller.is_rendering
        ):
            if reason == "page_enter" and columns == controller.current_columns:
                controller.replay_visible_reveal()
            else:
                controller.reflow(columns)
            return

        if (
            reason == "reset_reveal"
            and controller.has_rendered_content()
            and not controller.is_rendering
            and columns == controller.current_columns
        ):
            self._patch_garage_cards_in_place()
            controller.replay_visible_reveal()
            return

        self._rebuild_garage_cards(
            animate=reason in {"page_enter", "filter_change", "reset_reveal", "save_load_visible"},
            reset_scroll=reason in {"search_change", "filter_change"},
        )

    def on_garage_search_changed(self) -> None:
        self._mark_garage_cards_dirty()
        if hasattr(self, "_garage_search_timer"):
            self._garage_search_timer.start(150)

    def _select_garage_filter(self, source: str) -> None:
        self.garage_filter = source
        for label, button in self.garage_filter_buttons.items():
            button.setChecked(label == source)
        self._mark_garage_cards_dirty()
        self._refresh_garage_page(reason="filter_change")

    def on_toggle_garage_allocator_diagnostics(self) -> None:
        self.show_garage_allocator_diagnostics = self.chk_show_garage_allocator_diagnostics.isChecked()
        self._sync_garage_diagnostics_visibility()
        if self._garage_page_visible():
            self._refresh_garage_diagnostics_text()

    def on_toggle_unlinked_pursuits(self) -> None:
        self.on_toggle_garage_allocator_diagnostics()

    def on_garage_transfer_requested(self, abs_off: int, target_mode: str) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        desired_slot = None
        effective_target = str(target_mode)
        allow_nonvalidated_restore = False
        restore_wins = False
        before_snapshot_plans: Dict[str, SnapshotInjectionPlan] = {}
        reserved_career_override: Optional[Set[int]] = None
        if effective_target == "career":
            have_loc = int(self.have_owned_locations.get(abs_off, 0))
            have_slot = int(self.have_owned_career_slots.get(abs_off, SaveFile.EMPTY_CAREER_SLOT))
            current_loc = int(self._current_owned_locations().get(abs_off, have_loc))
            current_slot = int(self._current_owned_career_slots().get(abs_off, have_slot))
            if (
                current_loc == SaveFile.MY_CARS_FLAG
                and current_slot == SaveFile.EMPTY_CAREER_SLOT
                and have_loc in (SaveFile.CAREER_FLAG, SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
                and have_slot != SaveFile.EMPTY_CAREER_SLOT
            ):
                desired_slot = have_slot
                effective_target = "pink_slip" if have_loc == (SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG) else "career"
                original_entry = next((item for item in self.garage_transfer_entries if item.abs_off == abs_off), None)
                allow_nonvalidated_restore = bool(original_entry is not None and not original_entry.has_pursuit_link)
                before_snapshot_plans, _, _, reserved_career = self._current_snapshot_injection_plans()
                reserved_career_override = set(reserved_career)
                reserved_career_override.discard(desired_slot)
                restore_wins = True
        try:
            plan = self._garage_transfer_plan_for(
                abs_off,
                effective_target,
                desired_career_slot=desired_slot,
                allow_restore_to_nonvalidated_slot=allow_nonvalidated_restore,
                reserved_career_slots_override=reserved_career_override,
            )
        except Exception as exc:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, UI_TITLE_BLOCKED, plan.refusal_reason)
            return
        if self.want_owned_locations is None:
            self.want_owned_locations = dict(self.have_owned_locations)
        if self.want_owned_career_slots is None:
            self.want_owned_career_slots = dict(self.have_owned_career_slots)
        self.want_owned_locations[abs_off] = plan.target_location_bits
        self.want_owned_career_slots[abs_off] = (
            SaveFile.EMPTY_CAREER_SLOT if plan.target_career_slot is None else int(plan.target_career_slot)
        )
        after_snapshot_plans: Dict[str, SnapshotInjectionPlan] = {}
        if restore_wins:
            after_snapshot_plans, _, _, _ = self._current_snapshot_injection_plans()
        self._garage_cards_dirty = True
        self._mark_parts_cards_dirty()
        self._mark_presets_cards_dirty(library=True, snapshot=False)
        self._sync_garage_summary_chrome(loaded=True)
        self._sync_presets_summary_chrome(loaded=True)
        self._patch_garage_cards_in_place()
        self._update_action_states()
        if restore_wins:
            for message, is_error in self._snapshot_injection_reallocation_messages(
                before_snapshot_plans,
                after_snapshot_plans,
            ):
                ToastNotification.show_toast(self, message, is_error=is_error)

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
        self._garage_cards_dirty = True
        self._sync_garage_summary_chrome(loaded=True)
        self._patch_garage_cards_in_place()
        self._update_action_states()

    def on_garage_heat_changed(self, slot_index: int, level: int) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        max_heat_level = self.savefile.get_story_heat_cap()
        if int(level) > max_heat_level:
            return
        if self.want_slot_heats is None:
            self.want_slot_heats = dict(self.have_slot_heats)
        self.want_slot_heats[slot_index] = level
        self._garage_cards_dirty = True
        self._patch_garage_cards_in_place()
        self._update_action_states()
