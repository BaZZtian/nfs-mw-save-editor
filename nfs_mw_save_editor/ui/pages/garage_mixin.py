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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GarageCardVm:
    slot: ResolvedTransferCarEntry
    changed: bool
    is_active: bool
    current_bounty: int
    have_bounty: int
    plan_my_cars: OwnedCarTransferPlan
    plan_career: OwnedCarTransferPlan


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

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.garage_search = QLineEdit()
        self.garage_search.setPlaceholderText("Search cars by model name...")
        self.garage_search.textChanged.connect(self.on_garage_search_changed)
        controls.addWidget(self.garage_search, 1)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.garage_filter_buttons: Dict[str, QPushButton] = {}
        self.garage_filter_group = QButtonGroup(self)
        self.garage_filter_group.setExclusive(True)
        for label in ["All", "Career", "My Cars"]:
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
        self.garage_cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.garage_cards_scroll.setWidget(self.garage_cards)
        layout.addWidget(self.garage_cards_scroll, 1)

        self.garage_diag_label = self._section_label("Pursuit Diagnostics")
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
    ) -> OwnedCarTransferPlan:
        _, _, _, reserved_career = self._current_snapshot_injection_plans()
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
                elif source == "Career":
                    if source_kind not in ("Career", "Pink Slip"):
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
            label.setObjectName("garageCardStatBadge")
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
        return want_bounty != have_bounty

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
        current_locations = self._current_owned_locations()
        current_career_slots = self._current_owned_career_slots()
        cleared_slots = self._current_cleared_pursuit_slots()
        _, _, _, reserved_career = self._current_snapshot_injection_plans()
        staged_career_vehicle_count = self._staged_career_vehicle_count()
        current_bounties = self._current_slot_bounties()
        projected_active_car_number = self.savefile.get_projected_active_career_car_number(
            location_overrides=current_locations,
            career_slot_overrides=current_career_slots,
        )

        view_models: List[GarageCardVm] = []
        for slot in target_entries:
            career_slot = slot.career_slot
            view_models.append(
                GarageCardVm(
                    slot=slot,
                    changed=self._garage_transfer_changed(slot.abs_off) or (
                        career_slot != SaveFile.EMPTY_CAREER_SLOT and self._garage_card_changed(career_slot)
                    ),
                    is_active=(
                        projected_active_car_number is not None
                        and not slot.is_my_cars
                        and int(slot.car_number) == int(projected_active_car_number)
                    ),
                    current_bounty=current_bounties.get(career_slot, int(slot.bounty or 0)),
                    have_bounty=self.have_slot_bounties.get(career_slot, int(slot.bounty or 0)),
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
            int(entry.abs_off): entry for entry in self._current_transfer_entries()
        }
        frozen_entries = [
            entry_by_abs_off[key]
            for key in self._garage_visible_order
            if key in entry_by_abs_off
        ]
        return {vm.slot.abs_off: vm for vm in self._garage_card_view_models(frozen_entries)}

    def _apply_garage_source_badge(self, label: QLabel, source_kind: str) -> None:
        if source_kind == "Career":
            label.setObjectName("careerSourceBadge")
        elif source_kind == "My Cars":
            label.setObjectName("myCarsSourceBadge")
        elif source_kind == "Pink Slip":
            label.setObjectName("pinkSlipBadgeText")
        else:
            label.setObjectName("garageCardStatBadge")
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
            return (
                "Move this car to My Cars and free its linked Career slot."
                if slot.has_pursuit_link
                else "Move this car to My Cars."
            )
        return "Move this car into the next validated Career slot."

    def _garage_utility_summary(self, vm: GarageCardVm) -> Tuple[str, str]:
        slot = vm.slot
        visible_plan = vm.plan_career if slot.is_my_cars else vm.plan_my_cars
        if visible_plan.refusal_reason:
            return "Blocked", str(visible_plan.refusal_reason)
        if vm.plan_my_cars.clears_pursuit_slot and vm.plan_my_cars.cleared_source_career_slot is not None:
            detail = f"Moving to My Cars frees Career Slot {vm.plan_my_cars.cleared_source_career_slot + 1}."
            return f"Frees Slot {vm.plan_my_cars.cleared_source_career_slot + 1}", detail
        if (
            not slot.is_my_cars
            and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            and not slot.has_pursuit_link
        ):
            return "No pursuit link", "No pursuit record is linked to this car."
        return "Ready", "Action state is valid."

    def _apply_garage_card_vm(self, handle: GarageCardHandle, vm: GarageCardVm) -> None:
        slot = vm.slot
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

        handle.move_my_cars_btn.setVisible(not slot.is_my_cars)
        handle.move_my_cars_btn.setEnabled(vm.plan_my_cars.refusal_reason is None)
        handle.move_my_cars_btn.setToolTip(self._garage_action_tooltip(slot, "my_cars", vm.plan_my_cars))

        handle.move_career_btn.setVisible(slot.is_my_cars)
        handle.move_career_btn.setEnabled(vm.plan_career.refusal_reason is None)
        handle.move_career_btn.setToolTip(self._garage_action_tooltip(slot, "career", vm.plan_career))

        utility_text, utility_tooltip = self._garage_utility_summary(vm)
        handle.utility_label.setText(utility_text)
        handle.utility_label.setToolTip(utility_tooltip)

        if handle.bounty_edit is not None and handle.bounty_current_label is not None:
            edit_enabled = (
                not slot.is_my_cars
                and slot.has_pursuit_link
                and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            )
            handle.bounty_edit.setEnabled(edit_enabled)
            if edit_enabled:
                self._set_profile_line_edit(handle.bounty_edit, vm.current_bounty, True)
            handle.bounty_current_label.setText(self._format_current_value(vm.have_bounty))

        refresh_widget_style(handle.card)

    def _build_garage_card(self, vm: GarageCardVm) -> QWidget:
        slot = vm.slot
        card = QFrame()
        card.setObjectName("garageCard")
        card.setProperty("changed", vm.changed)
        card.setProperty("occupied", True)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        card.setMinimumWidth(240)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)
        card_layout.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        slot_text = (
            f"Career Slot {slot.career_slot + 1}"
            if slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
            else f"Car #{slot.car_number:02X}"
        )
        slot_label = QLabel(slot_text)
        slot_label.setObjectName("garageCardSlot")
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
        name_label.setObjectName("garageCardMeta")
        name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        parts_badge = QLabel()
        parts_badge.setObjectName("garageCardStatBadge")
        parts_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        parts_badge.setAlignment(Qt.AlignCenter)
        loc_badge = QLabel()
        loc_badge.setObjectName("garageCardStatBadge")
        loc_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        loc_badge.setAlignment(Qt.AlignCenter)
        misc_badge = QLabel()
        misc_badge.setObjectName("garageCardStatBadge")
        misc_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        misc_badge.setAlignment(Qt.AlignCenter)
        for badge in [parts_badge, loc_badge, misc_badge]:
            meta_row.addWidget(badge, 0, Qt.AlignLeft)
        meta_row.addStretch(1)
        card_layout.addLayout(meta_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        btn_my_cars = QPushButton("Move to My Cars")
        btn_my_cars.setObjectName("partsBulkBtn")
        btn_my_cars.clicked.connect(
            lambda _, abs_off=slot.abs_off: self.on_garage_transfer_requested(abs_off, "my_cars")
        )
        action_row.addWidget(btn_my_cars)
        btn_career = QPushButton("Move to Career")
        btn_career.setObjectName("partsBulkBtn")
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
        if not slot.is_my_cars and slot.has_pursuit_link:
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

            card_layout.addWidget(bounty_label)
            card_layout.addWidget(edit)
            card_layout.addWidget(current)
            self._set_profile_line_edit(edit, vm.current_bounty, True)

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
        entries = self._garage_unlinked_entries()
        if not entries:
            self.garage_diag_text.setText("No unlinked pursuit records detected.")
            return
        self.garage_diag_text.setText(
            "\n".join(
                f"Career Slot {slot.career_slot + 1}: bounty={slot.bounty}, escaped={slot.escaped}, busted={slot.busted}"
                for slot in entries
            )
        )

    def _sync_garage_summary_chrome(self, *, loaded: bool) -> None:
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
        if hasattr(self, "chk_show_unlinked_pursuits"):
            self.chk_show_unlinked_pursuits.blockSignals(True)
            self.chk_show_unlinked_pursuits.setChecked(self.show_unlinked_pursuits)
            self.chk_show_unlinked_pursuits.setEnabled(loaded)
            self.chk_show_unlinked_pursuits.blockSignals(False)

        if not self._garage_page_visible():
            self._mark_garage_cards_dirty()
            return

        self._sync_garage_summary_chrome(loaded=loaded)

        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns
        if (
            reason in {"page_enter", "reflow"}
            and not self._garage_cards_dirty
            and self._garage_render_controller.has_rendered_content()
            and not self._garage_render_controller.is_rendering
        ):
            if reason == "page_enter" and columns == self._garage_render_controller.current_columns:
                self._garage_render_controller.replay_visible_reveal()
            else:
                self._garage_render_controller.reflow(columns)
            return

        self._rebuild_garage_cards(
            animate=reason in {"page_enter", "filter_change"},
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

    def on_toggle_unlinked_pursuits(self) -> None:
        self.show_unlinked_pursuits = self.chk_show_unlinked_pursuits.isChecked()
        self._sync_garage_diagnostics_visibility()
        if self._garage_page_visible():
            self._refresh_garage_diagnostics_text()

    def on_garage_transfer_requested(self, abs_off: int, target_mode: str) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        desired_slot = None
        effective_target = str(target_mode)
        allow_nonvalidated_restore = False
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
        try:
            plan = self._garage_transfer_plan_for(
                abs_off,
                effective_target,
                desired_career_slot=desired_slot,
                allow_restore_to_nonvalidated_slot=allow_nonvalidated_restore,
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
        self._garage_cards_dirty = True
        self._mark_parts_cards_dirty()
        self._mark_presets_cards_dirty(library=True, snapshot=False)
        self._sync_garage_summary_chrome(loaded=True)
        self._patch_garage_cards_in_place()
        self._update_action_states()

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
