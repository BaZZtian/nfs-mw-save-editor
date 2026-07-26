"""Builds page: library injection, user snapshot saves, save snapshot export."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Dict, List

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.savefile import SaveFile
from core.cars import resolve_car_name
from core.models import FullCarBuildSnapshot, SnapshotInjectionPlan, SnapshotLibraryEntry
from core.tuning_limits import get_model_tuning_limits
from ui.pages.constants import *
from ui.rendering import ViewportLazyGridController, refresh_widget_style
from ui.widgets import ToastNotification, build_perf_value_host

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotLibraryCardVm:
    entry: SnapshotLibraryEntry
    staged_mode: str | None
    plan_my: SnapshotInjectionPlan | None
    plan_career: SnapshotInjectionPlan | None
    staged_plan: SnapshotInjectionPlan | None


@dataclass(frozen=True)
class SnapshotCardVm:
    snapshot: FullCarBuildSnapshot


@dataclass
class SnapshotLibraryCardHandle:
    card: QFrame
    bucket_badge: QLabel
    source_badge: QLabel
    name_label: QLabel
    inject_my_btn: QPushButton
    inject_career_btn: QPushButton
    unstage_btn: QPushButton
    utility_label: QLabel


class PresetsMixin:
    # -- Page builder --------------------------------------------

    def _preset_bucket_ui_label(self, bucket: str) -> str:
        if str(bucket) == "Main":
            return "Blacklist"
        if str(bucket) == "User":
            return "My Builds"
        return str(bucket)

    def _build_presets_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 6, 0, 8)
        layout.setSpacing(10)

        hint = QLabel("Apply library builds to your save or save current builds for reuse.")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls_frame, controls = self._make_page_controls_bar()
        filter_host = QWidget()
        filter_host.setObjectName("pageControlsSection")
        filter_row = QHBoxLayout(filter_host)
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)

        self.snapshot_library_filter_group = QButtonGroup(self)
        self.snapshot_library_filter_group.setExclusive(True)
        self.snapshot_library_filter_buttons: Dict[str, QPushButton] = {}
        for filter_value in ["Main", "Bonus", "User"]:
            btn = QPushButton(self._preset_bucket_ui_label(filter_value))
            btn.setCheckable(True)
            btn.setObjectName("filterButton")
            btn.clicked.connect(lambda _, v=filter_value: self.on_snapshot_library_filter_changed(v))
            self.snapshot_library_filter_group.addButton(btn)
            self.snapshot_library_filter_buttons[filter_value] = btn
            filter_row.addWidget(btn)
        self.snapshot_library_filter_buttons["Main"].setChecked(True)

        self.snapshot_save_filter_group = QButtonGroup(self)
        self.snapshot_save_filter_group.setExclusive(True)
        self.snapshot_save_filter_buttons: Dict[str, QPushButton] = {}
        for filter_value in ["All", "Career", "My Cars"]:
            btn = QPushButton(filter_value)
            btn.setCheckable(True)
            btn.setObjectName("filterButton")
            btn.clicked.connect(lambda _, v=filter_value: self._select_snapshot_save_filter(v))
            self.snapshot_save_filter_group.addButton(btn)
            self.snapshot_save_filter_buttons[filter_value] = btn
            filter_row.addWidget(btn)
            btn.setVisible(False)
        self.snapshot_save_filter_buttons["All"].setChecked(True)

        controls.addWidget(filter_host, 0)

        self.presets_search = QLineEdit()
        self.presets_search.setPlaceholderText("Search build library...")
        self.presets_search.textChanged.connect(self._on_presets_search_changed)
        controls.addWidget(self._make_centered_search_host(self.presets_search), 1)

        right_host = QWidget()
        right_host.setObjectName("pageControlsSection")
        right_row = QHBoxLayout(right_host)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(8)
        self.presets_free_career_badge = self._make_stat_badge("Free Career Slots: -")
        self.presets_free_career_badge.setToolTip(
            "Validated reusable Career slots currently available for Add to Career. Reserved and unavailable slots are not counted here."
        )
        right_row.addWidget(self.presets_free_career_badge, 0, Qt.AlignRight)

        self.presets_view_group = QButtonGroup(self)
        self.presets_view_group.setExclusive(True)
        self.presets_view_buttons: Dict[str, QPushButton] = {}
        for name in ["Library", "My Save"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("filterButton")
            btn.clicked.connect(lambda _, v=name: self._on_presets_view_changed(v))
            self.presets_view_group.addButton(btn)
            self.presets_view_buttons[name] = btn
            right_row.addWidget(btn)
        self.presets_view_buttons["Library"].setChecked(True)
        controls.addWidget(right_host, 0, Qt.AlignRight)
        layout.addWidget(controls_frame)

        # -- QStackedWidget: Library / My Save -----------------
        self.presets_stack = QStackedWidget()

        # Page 0: Library cards
        self.snapshot_library_cards = QWidget()
        self.snapshot_library_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.snapshot_library_cards_layout = QGridLayout(self.snapshot_library_cards)
        self.snapshot_library_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.snapshot_library_cards_layout.setHorizontalSpacing(14)
        self.snapshot_library_cards_layout.setVerticalSpacing(14)
        self.snapshot_library_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.snapshot_library_scroll = QScrollArea()
        self.snapshot_library_scroll.setObjectName("cardScroll")
        self.snapshot_library_scroll.setWidgetResizable(True)
        self.snapshot_library_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.snapshot_library_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.snapshot_library_scroll.setWidget(self.snapshot_library_cards)
        self.presets_stack.addWidget(self.snapshot_library_scroll)

        # Page 1: My Save snapshot cards
        self.snapshot_cards = QWidget()
        self.snapshot_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.snapshot_cards_layout = QGridLayout(self.snapshot_cards)
        self.snapshot_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.snapshot_cards_layout.setHorizontalSpacing(14)
        self.snapshot_cards_layout.setVerticalSpacing(14)
        self.snapshot_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.snapshot_cards_scroll = QScrollArea()
        self.snapshot_cards_scroll.setObjectName("cardScroll")
        self.snapshot_cards_scroll.setWidgetResizable(True)
        self.snapshot_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.snapshot_cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.snapshot_cards_scroll.setWidget(self.snapshot_cards)
        self.presets_stack.addWidget(self.snapshot_cards_scroll)

        layout.addWidget(self.presets_stack, 1)

        self._snapshot_card_widgets: Dict[int, QFrame] = {}
        self._snapshot_library_card_widgets: Dict[str, QFrame] = {}
        self._snapshot_library_card_handles: Dict[str, SnapshotLibraryCardHandle] = {}
        self._snapshot_library_visible_order: List[str] = []
        self._snapshot_library_live_vm_map: Dict[str, SnapshotLibraryCardVm] = {}
        self._snapshot_library_render_controller = ViewportLazyGridController(
            self,
            name="PresetsLibrary",
            layout=self.snapshot_library_cards_layout,
            scroll_area=self.snapshot_library_scroll,
            split_initial_visible_batch=True,
        )
        self._snapshot_render_controller = ViewportLazyGridController(
            self,
            name="PresetsMySave",
            layout=self.snapshot_cards_layout,
            scroll_area=self.snapshot_cards_scroll,
            split_initial_visible_batch=True,
        )
        return w

    def _presets_page_visible(self) -> bool:
        return hasattr(self, "stack") and hasattr(self, "page_presets") and self.stack.currentWidget() is self.page_presets

    # -- View toggle / search ------------------------------------

    def _on_presets_view_changed(self, view: str) -> None:
        self.presets_view = view
        is_library = view == "Library"
        for btn in self.snapshot_library_filter_buttons.values():
            btn.setVisible(is_library)
        for btn in self.snapshot_save_filter_buttons.values():
            btn.setVisible(not is_library)
        if hasattr(self, "presets_free_career_badge"):
            self.presets_free_career_badge.setVisible(is_library)
        self.presets_stack.setCurrentIndex(0 if is_library else 1)
        self.presets_search.setPlaceholderText(
            "Search build library..." if is_library else "Search builds in this save...",
        )
        self._refresh_presets_page(reason="page_enter")

    def _on_presets_search_changed(self) -> None:
        self._mark_presets_cards_dirty()
        if hasattr(self, "_presets_search_timer"):
            self._presets_search_timer.start(150)

    def on_snapshot_library_filter_changed(self, value: str) -> None:
        self.snapshot_library_filter = str(value)
        for label, button in self.snapshot_library_filter_buttons.items():
            button.setChecked(label == self.snapshot_library_filter)
        self._mark_presets_cards_dirty(library=True, snapshot=False)
        self._refresh_presets_page(reason="filter_change")

    def _select_snapshot_save_filter(self, value: str) -> None:
        self.snapshot_save_filter = str(value)
        for label, button in self.snapshot_save_filter_buttons.items():
            button.setChecked(label == self.snapshot_save_filter)
        self._mark_presets_cards_dirty(library=False, snapshot=True)
        self._refresh_presets_page(reason="filter_change")

    # -- Shared perf grid (read-only) ----------------------------

    def _presets_model_name(self, signature: bytes, display_name: str) -> str:
        """Model name for tuning-limit lookups.

        Library display names may carry qualifiers ("Corvette C6 R (red)");
        the signature is the immutable model key, so resolve through it and
        fall back to the display name only when the signature is unknown.
        """
        return resolve_car_name(signature) or str(display_name)

    def _add_presets_perf_grid(self, parent: QVBoxLayout, performance_levels, model_name: str = "") -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        limits = get_model_tuning_limits(model_name)
        for idx, (name, level) in enumerate(performance_levels):
            max_level = max(level, int(limits.get(name, 0))) if limits is not None else None
            row_w = self._build_presets_perf_row(name, level, max_level)
            grid.addWidget(row_w, idx // 2, idx % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)

    def _build_presets_perf_visual_host(self, level: int, max_level: int | None) -> QWidget:
        return build_perf_value_host(level, max_level)

    def _build_presets_perf_row(self, name: str, level: int, max_level: int | None) -> QWidget:
        row_w = QWidget()
        row_w.setObjectName("partsLevelRow")
        row_layout = QHBoxLayout(row_w)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        lbl = QLabel(name)
        lbl.setObjectName("partsLevelLabel")
        row_layout.addWidget(lbl)

        current_host = self._build_presets_perf_visual_host(int(level), max_level)
        reference_max_level = max_level if max_level is not None else 4
        reference_host = self._build_presets_perf_visual_host(int(level), reference_max_level)
        host_width = max(current_host.minimumSizeHint().width(), reference_host.minimumSizeHint().width())
        host_height = max(current_host.minimumSizeHint().height(), reference_host.minimumSizeHint().height())
        current_host.setFixedSize(host_width, host_height)
        row_layout.addWidget(current_host)
        return row_w

    # -- Library card columns / reflow ---------------------------

    def _detect_library_card_columns(self) -> int:
        return self._detect_col_count("snapshot_library_scroll", LIBRARY_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_library_rows(self, force: bool = False) -> None:
        columns = max(1, self._detect_library_card_columns())
        if not force and columns == getattr(self, "_library_slot_columns", 0):
            return
        self._library_slot_columns = columns
        if self.presets_view != "Library":
            return
        if self._snapshot_library_cards_dirty or not self._snapshot_library_render_controller.has_rendered_content():
            if self._presets_page_visible():
                self._refresh_presets_page(reason="reflow")
            return
        self._snapshot_library_render_controller.reflow(columns)

    # -- Library entries filter ----------------------------------

    def _snapshot_library_entries(self) -> List[SnapshotLibraryEntry]:
        query = ""
        if hasattr(self, "presets_search"):
            query = self.presets_search.text().strip().lower()
        entries = [entry for entry in self.snapshot_library if entry.library_bucket == self.snapshot_library_filter]
        if query:
            entries = [
                entry for entry in entries
                if query in entry.display_name.lower() or query in entry.file_label.lower()
            ]
        return entries

    def _snapshot_library_empty_widget(self, _: int) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        if self.snapshot_library_error:
            text = f"Build library unavailable: {self.snapshot_library_error}"
        elif self.snapshot_library_filter == "User":
            text = (
                "My Builds is empty. Save a build from My Save to start your personal snapshot library."
                if not self.presets_search.text().strip()
                else "No personal builds match the current search."
            )
            label = QLabel(text)
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            layout.addWidget(label)
            open_btn = QPushButton("Open folder")
            open_btn.setObjectName("cardActionButton")
            open_btn.clicked.connect(self.on_open_user_builds_folder)
            layout.addWidget(open_btn, 0, Qt.AlignLeft)
            layout.addStretch(1)
            return container
        elif not self.snapshot_library:
            text = f"No snapshot files found in {self.snapshot_library_root}."
        else:
            text = "No build-library entries match the current search."
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        layout.addWidget(label)
        return container

    def _snapshot_library_card_view_models(
        self,
        entries: List[SnapshotLibraryEntry] | None = None,
    ) -> List[SnapshotLibraryCardVm]:
        visible_entries = list(entries) if entries is not None else self._snapshot_library_entries()
        plans, reserved_owned, reserved_parts, reserved_career = self._current_snapshot_injection_plans()
        current_locations = self._current_owned_locations()
        current_career_slots = self._current_owned_career_slots()
        cleared_slots = self._current_cleared_pursuit_slots()
        view_models: List[SnapshotLibraryCardVm] = []
        for entry in visible_entries:
            plan_my = None
            plan_career = None
            if self.savefile is not None and not self.snapshot_library_error:
                plan_my = self.savefile.plan_snapshot_injection(
                    entry,
                    "my_cars",
                    location_overrides=current_locations,
                    career_slot_overrides=current_career_slots,
                    cleared_slots=cleared_slots,
                    reserved_owned_abs_offs=set(reserved_owned),
                    reserved_parts_slots=set(reserved_parts),
                    reserved_career_slots=set(reserved_career),
                )
                plan_career = self.savefile.plan_snapshot_injection(
                    entry,
                    "career",
                    location_overrides=current_locations,
                    career_slot_overrides=current_career_slots,
                    cleared_slots=cleared_slots,
                    reserved_owned_abs_offs=set(reserved_owned),
                    reserved_parts_slots=set(reserved_parts),
                    reserved_career_slots=set(reserved_career),
                )
            view_models.append(
                SnapshotLibraryCardVm(
                    entry=entry,
                    staged_mode=self.staged_state.snapshot_injections.mode_for(entry.snapshot_id),
                    plan_my=plan_my,
                    plan_career=plan_career,
                    staged_plan=plans.get(entry.snapshot_id),
                )
            )
        return view_models

    def _snapshot_library_visible_vm_map(self) -> Dict[str, SnapshotLibraryCardVm]:
        entries_by_id = {entry.snapshot_id: entry for entry in self.snapshot_library}
        frozen_entries = [
            entries_by_id[key]
            for key in self._snapshot_library_visible_order
            if key in entries_by_id
        ]
        return {
            vm.entry.snapshot_id: vm
            for vm in self._snapshot_library_card_view_models(frozen_entries)
        }

    def _snapshot_library_utility_summary(self, vm: SnapshotLibraryCardVm) -> tuple[str, str]:
        tooltip_parts: List[str] = []
        blocked_parts: List[str] = []
        warning_parts: List[str] = []
        if not self.savefile:
            return "Open a save to stage", "Open a save to stage an injection."
        if vm.staged_mode is not None:
            tooltip_parts.append(
                "Staged target: "
                + ("My Cars" if vm.staged_mode == "my_cars" else "Career")
            )
            if vm.staged_plan is not None and vm.staged_plan.refusal_reason is None:
                target_bits: List[str] = []
                if vm.staged_plan.target_parts_slot is not None:
                    target_bits.append(f"Parts Slot {vm.staged_plan.target_parts_slot}")
                if vm.staged_plan.target_career_slot is not None:
                    target_bits.append(f"Career Slot {vm.staged_plan.target_career_slot + 1}")
                if target_bits:
                    tooltip_parts.append("Resolved to " + " | ".join(target_bits))
            if vm.staged_plan is not None and vm.staged_plan.refusal_reason:
                tooltip_parts.append(f"Staged result blocked: {vm.staged_plan.refusal_reason}")
                return "Staged blocked", "\n".join(tooltip_parts)
            if vm.staged_plan is not None and vm.staged_plan.warnings:
                warning_parts.extend(f"Warning: {warning}" for warning in vm.staged_plan.warnings)
                tooltip_parts.extend(warning_parts)
                return "Staged warning", "\n".join(tooltip_parts)
            return (
                "Staged to My Cars" if vm.staged_mode == "my_cars" else "Staged to Career",
                "\n".join(tooltip_parts) or "Injection is staged.",
            )
        if vm.plan_my is not None and vm.plan_my.refusal_reason:
            blocked_parts.append(f"My Cars blocked: {vm.plan_my.refusal_reason}")
        if vm.plan_career is not None and vm.plan_career.refusal_reason:
            blocked_parts.append(f"Career blocked: {vm.plan_career.refusal_reason}")
        if vm.plan_my is not None and vm.plan_my.warnings:
            warning_parts.extend(f"My Cars warning: {warning}" for warning in vm.plan_my.warnings)
        if vm.plan_career is not None and vm.plan_career.warnings:
            warning_parts.extend(f"Career warning: {warning}" for warning in vm.plan_career.warnings)
        if blocked_parts:
            tooltip_parts.extend(blocked_parts)
            tooltip_parts.extend(warning_parts)
            if len(blocked_parts) == 2:
                return "All targets blocked", "\n".join(tooltip_parts)
            return (
                "My Cars blocked" if blocked_parts[0].startswith("My Cars") else "Career blocked",
                "\n".join(tooltip_parts),
            )
        if warning_parts:
            return "Ready with warning", "\n".join(warning_parts)
        return "Ready to stage", "Both injection targets are currently available."

    @staticmethod
    def _snapshot_provenance_lines(entry: SnapshotLibraryEntry) -> List[str]:
        labels = {
            "method": "Provenance",
            "donor_save": "Donor save",
            "preset": "VLT preset",
            "note": "Note",
        }
        hidden = {"pending_parts_slot", "perf_rule"}
        return [
            f"{labels.get(name, name)}: {value}"
            for name, value in entry.provenance
            if name not in hidden
        ]

    def _snapshot_library_card_tooltip(self, vm: SnapshotLibraryCardVm) -> str:
        entry = vm.entry
        tooltip_parts = [
            f"File: {entry.file_label}",
            f"Snapshot ID: {entry.snapshot_id[:60]}...",
        ]
        tooltip_parts.extend(self._snapshot_provenance_lines(entry))
        if entry.has_visual_sidecar:
            tooltip_parts.append("Has visual sidecar")
        if entry.requires_unresolved_global_visual_state:
            if entry.global_visual_table_mode_uniform_value is not None:
                tooltip_parts.append(
                    f"Requires 0x5577+{entry.global_visual_table_mode_offset:X} mode 0x{entry.global_visual_table_mode_uniform_value:02X} "
                    "(not injected in v1)"
                )
            else:
                tooltip_parts.append(
                    f"Requires 0x5577+{entry.global_visual_table_mode_offset:X} visual mode state (not injected in v1)"
                )
        utility_text, utility_tooltip = self._snapshot_library_utility_summary(vm)
        tooltip_parts.append(f"State: {utility_text}")
        if utility_tooltip:
            tooltip_parts.append(utility_tooltip)
        return "\n".join(tooltip_parts)

    def _apply_snapshot_library_card_vm(self, handle: SnapshotLibraryCardHandle, vm: SnapshotLibraryCardVm) -> None:
        entry = vm.entry
        handle.card.setProperty("changed", vm.staged_mode is not None)
        handle.bucket_badge.setText(self._preset_bucket_ui_label(entry.library_bucket))
        self._apply_garage_source_badge(handle.source_badge, entry.source_kind)
        handle.name_label.setText(entry.display_name)

        handle.inject_my_btn.setText("Add to My Cars")
        handle.inject_my_btn.setEnabled(
            self.savefile is not None
            and vm.plan_my is not None
            and vm.plan_my.refusal_reason is None
        )
        handle.inject_career_btn.setText("Add to Career")
        handle.inject_career_btn.setEnabled(
            self.savefile is not None
            and vm.plan_career is not None
            and vm.plan_career.refusal_reason is None
        )
        if vm.staged_mode == "my_cars":
            handle.inject_my_btn.setText("Staged: My Cars")
            handle.inject_my_btn.setEnabled(False)
        elif vm.staged_mode == "career":
            handle.inject_career_btn.setText("Staged: Career")
            handle.inject_career_btn.setEnabled(False)
        handle.unstage_btn.setVisible(vm.staged_mode is not None)
        handle.unstage_btn.setEnabled(vm.staged_mode is not None)

        utility_text, utility_tooltip = self._snapshot_library_utility_summary(vm)
        handle.utility_label.setText(utility_text)
        handle.utility_label.setToolTip(utility_tooltip)
        handle.card.setToolTip(self._snapshot_library_card_tooltip(vm))
        refresh_widget_style(handle.card)

    def _patch_snapshot_library_cards_in_place(self) -> None:
        if not (self._presets_page_visible() and getattr(self, "presets_view", "Library") == "Library"):
            self._mark_presets_cards_dirty(library=True, snapshot=False)
            return
        started = perf_counter()
        vm_map = self._snapshot_library_visible_vm_map()
        self._snapshot_library_live_vm_map.update(vm_map)
        patched = 0
        for snapshot_id, handle in list(self._snapshot_library_card_handles.items()):
            vm = vm_map.get(snapshot_id)
            if vm is None:
                continue
            self._apply_snapshot_library_card_vm(handle, vm)
            patched += 1
        logger.debug(
            "Presets Library interactive patch: %d card(s) in %d ms",
            patched,
            int((perf_counter() - started) * 1000),
        )

    def _restore_snapshot_library_scroll(self, value: int) -> None:
        if not hasattr(self, "snapshot_library_scroll"):
            return
        scrollbar = self.snapshot_library_scroll.verticalScrollBar()
        if scrollbar is None:
            return
        target = max(int(scrollbar.minimum()), min(int(value), int(scrollbar.maximum())))
        scrollbar.setValue(target)

    def _patch_snapshot_library_cards_preserving_scroll(self) -> None:
        scrollbar = None
        restore_value = 0
        if hasattr(self, "snapshot_library_scroll"):
            scrollbar = self.snapshot_library_scroll.verticalScrollBar()
            if scrollbar is not None:
                restore_value = int(scrollbar.value())
        self._patch_snapshot_library_cards_in_place()
        self._restore_snapshot_library_scroll(restore_value)
        QTimer.singleShot(
            0,
            lambda value=restore_value: self._restore_snapshot_library_scroll(value),
        )

    # -- Library cards -------------------------------------------

    def _rebuild_snapshot_library_cards(self) -> None:
        if not hasattr(self, "snapshot_library_cards_layout"):
            return
        self._clear_layout(self.snapshot_library_cards_layout)
        self._snapshot_library_card_widgets = {}
        columns = max(1, self._detect_library_card_columns())
        self._library_slot_columns = columns

        if self.snapshot_library_error:
            label = QLabel(f"Build library unavailable: {self.snapshot_library_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.snapshot_library_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._snapshot_library_entries()
        if not visible_entries:
            label = QLabel(
                f"No snapshot files found in {self.snapshot_library_root}."
                if not self.snapshot_library
                else "No build-library entries match the current search."
            )
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.snapshot_library_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        plans, _, _, _ = self._current_snapshot_injection_plans()
        for idx, entry in enumerate(visible_entries):
            staged_mode = self.staged_state.snapshot_injections.mode_for(entry.snapshot_id)
            plan_my = None
            plan_career = None
            if self.savefile and not self.snapshot_library_error:
                plan_my = self._current_snapshot_injection_plans(
                    extra_snapshot_id=entry.snapshot_id,
                    extra_target_mode="my_cars",
                )[0].get(entry.snapshot_id)
                plan_career = self._current_snapshot_injection_plans(
                    extra_snapshot_id=entry.snapshot_id,
                    extra_target_mode="career",
                )[0].get(entry.snapshot_id)
            staged_plan = plans.get(entry.snapshot_id)

            card, card_layout = self._make_card_frame(minimum_width=360)

            # Header: bucket badge + source badge
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            bucket_badge = QLabel(self._preset_bucket_ui_label(entry.library_bucket))
            bucket_badge.setObjectName("contentCardSlot")
            bucket_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bucket_badge.setAlignment(Qt.AlignCenter)
            source_badge = self._make_garage_source_badge(entry.source_kind)
            header_row.addWidget(bucket_badge, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_badge, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # Car name
            name_label = QLabel(entry.display_name)
            name_label.setObjectName("contentCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # Capability / warning badges
            if entry.has_visual_sidecar:
                warn_badge = QLabel("Needs adjacent sidecar slots")
                warn_badge.setObjectName("contentCardNote")
                warn_badge.setWordWrap(True)
                card_layout.addWidget(warn_badge)
            if entry.requires_unresolved_global_visual_state:
                mode_text = (
                    f"Uses extra 0x5577+{entry.global_visual_table_mode_offset:X} visual state not replayed in this preview"
                    if entry.global_visual_table_mode_uniform_value is not None
                    else "Uses extra 0x5577 visual state not replayed in this preview"
                )
                warn_badge = QLabel(mode_text)
                warn_badge.setObjectName("contentCardNote")
                warn_badge.setWordWrap(True)
                card_layout.addWidget(warn_badge)

            # Separator
            card_layout.addWidget(self._make_card_separator())

            # Performance bars (read-only, proper caps)
            card_layout.addWidget(self._make_card_field_label("Performance"))
            self._add_presets_perf_grid(card_layout, entry.performance_levels, self._presets_model_name(entry.primary_owned_record_template.signature, entry.display_name))

            # Action row
            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            inject_my = self._make_card_action_button("Add to My Cars")
            inject_my.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "my_cars"))
            inject_career = self._make_card_action_button("Add to Career")
            inject_career.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "career"))

            inject_my.setEnabled(self.savefile is not None and plan_my is not None and plan_my.refusal_reason is None)
            inject_career.setEnabled(self.savefile is not None and plan_career is not None and plan_career.refusal_reason is None)

            if staged_mode == "my_cars":
                inject_my.setText("Staged: My Cars")
                inject_my.setEnabled(False)
            elif staged_mode == "career":
                inject_career.setText("Staged: Career")
                inject_career.setEnabled(False)

            action_row.addWidget(inject_my)
            action_row.addWidget(inject_career)

            if staged_mode is not None:
                unstage_btn = self._make_card_action_button("Unstage")
                unstage_btn.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_clear_snapshot_injection(sid))
                action_row.addWidget(unstage_btn)

            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            # Refusal line — visible reason when injection is blocked
            refusal_texts: List[str] = []
            if not self.savefile:
                refusal_texts.append("Open a save to stage an injection")
            else:
                if plan_my is not None and plan_my.refusal_reason and staged_mode != "my_cars":
                    refusal_texts.append(f"My Cars blocked: {plan_my.refusal_reason}")
                if plan_career is not None and plan_career.refusal_reason and staged_mode != "career":
                    refusal_texts.append(f"Career blocked: {plan_career.refusal_reason}")
                if staged_plan is not None and staged_plan.refusal_reason:
                    refusal_texts.append(f"Staged result blocked: {staged_plan.refusal_reason}")
            if refusal_texts:
                refusal_label = QLabel(" | ".join(refusal_texts))
                refusal_label.setObjectName("mutedLabel")
                refusal_label.setWordWrap(True)
                card_layout.addWidget(refusal_label)

            # Tooltip — technical details for power users
            tooltip_parts = [
                f"File: {entry.file_label}",
                f"Snapshot ID: {entry.snapshot_id[:60]}...",
            ]
            if entry.has_visual_sidecar:
                tooltip_parts.append("Has visual sidecar")
            if entry.requires_unresolved_global_visual_state:
                if entry.global_visual_table_mode_uniform_value is not None:
                    tooltip_parts.append(
                        f"Requires 0x5577+{entry.global_visual_table_mode_offset:X} mode 0x{entry.global_visual_table_mode_uniform_value:02X} "
                        "(not injected in v1)"
                    )
                else:
                    tooltip_parts.append(
                        f"Requires 0x5577+{entry.global_visual_table_mode_offset:X} visual mode state (not injected in v1)"
                    )
            card.setToolTip("\n".join(tooltip_parts))

            row = idx // columns
            col = idx % columns
            self.snapshot_library_cards_layout.addWidget(card, row, col)
            self._snapshot_library_card_widgets[entry.snapshot_id] = card

        for col in range(columns):
            self.snapshot_library_cards_layout.setColumnStretch(col, 1)

    # -- Snapshot card columns / reflow --------------------------

    def _detect_snapshot_card_columns(self) -> int:
        return self._detect_col_count("snapshot_cards_scroll", SNAPSHOT_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_snapshot_rows(self, force: bool = False) -> None:
        columns = max(1, self._detect_snapshot_card_columns())
        if not force and columns == getattr(self, "_snapshot_slot_columns", 0):
            return
        self._snapshot_slot_columns = columns
        if self.presets_view != "My Save":
            return
        if self._snapshot_cards_dirty or not self._snapshot_render_controller.has_rendered_content():
            if self._presets_page_visible():
                self._refresh_presets_page(reason="reflow")
            return
        self._snapshot_render_controller.reflow(columns)

    # -- Snapshot entries filter ---------------------------------

    def _snapshot_card_entries(self) -> List[FullCarBuildSnapshot]:
        query = ""
        if hasattr(self, "presets_search"):
            query = self.presets_search.text().strip().lower()
        entries = list(self.build_snapshots)
        current_filter = getattr(self, "snapshot_save_filter", "All")
        if current_filter == "Career":
            entries = [
                entry for entry in entries
                if entry.career_slot != SaveFile.EMPTY_CAREER_SLOT
                and entry.location_bits in (
                    SaveFile.CAREER_FLAG,
                    SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
                )
            ]
        elif current_filter == "My Cars":
            entries = [
                entry for entry in entries
                if entry.career_slot == SaveFile.EMPTY_CAREER_SLOT
                and entry.location_bits == SaveFile.MY_CARS_FLAG
            ]
        if query:
            entries = [entry for entry in entries if query in entry.display_name.lower()]
        return entries

    # -- Snapshot cards (My Save view) ---------------------------

    def _rebuild_snapshot_cards(self) -> None:
        if not hasattr(self, "snapshot_cards_layout"):
            return
        self._clear_layout(self.snapshot_cards_layout)
        self._snapshot_card_widgets = {}
        columns = max(1, self._detect_snapshot_card_columns())
        self._snapshot_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect build snapshots from this save.")
            label.setObjectName("mutedLabel")
            self.snapshot_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.snapshot_detection_error:
            label = QLabel(f"Build snapshot tools unavailable: {self.snapshot_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.snapshot_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._snapshot_card_entries()
        if not visible_entries:
            label = QLabel("No build snapshots match the current search.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.snapshot_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, snapshot in enumerate(visible_entries):
            card, card_layout = self._make_card_frame(minimum_width=360)

            # Header: parts slot badge + source badge
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_badge = QLabel(f"Parts Slot {snapshot.parts_slot}")
            slot_badge.setObjectName("contentCardSlot")
            slot_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_badge.setAlignment(Qt.AlignCenter)
            source_badge = self._make_garage_source_badge(snapshot.source_kind)
            header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_badge, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # Car name
            name_label = QLabel(snapshot.display_name)
            name_label.setObjectName("contentCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            mode_label = QLabel(
                f"0x5577+{snapshot.global_visual_table_mode_offset:X} visual mode: "
                + (
                    f"0x{snapshot.global_visual_table_mode_uniform_value:02X}"
                    if snapshot.global_visual_table_mode_uniform_value is not None
                    else "mixed"
                )
            )
            mode_label.setObjectName("contentCardNote")
            mode_label.setWordWrap(True)
            card_layout.addWidget(mode_label)

            # Separator
            card_layout.addWidget(self._make_card_separator())

            # Performance bars (read-only)
            card_layout.addWidget(self._make_card_field_label("Performance"))
            self._add_presets_perf_grid(card_layout, snapshot.performance_levels, self._presets_model_name(snapshot.signature, snapshot.display_name))

            # Export button
            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            export_btn = self._make_card_action_button("Export Snapshot")
            export_btn.clicked.connect(lambda _, off=snapshot.car_abs_off: self.on_export_build_snapshot(off))
            action_row.addWidget(export_btn, 0, Qt.AlignLeft)
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            # Tooltip — technical details for power users
            tooltip_parts = [
                f"Car #{snapshot.car_number:02X}",
                f"Loc 0x{snapshot.location_bits:02X} | Misc 0x{snapshot.misc_bits:02X}",
                f"Block 0x{snapshot.primary_build_block_abs_off:05X}",
            ]
            if snapshot.optional_visual_sidecar:
                sc = snapshot.optional_visual_sidecar
                tooltip_parts.append(f"Sidecar: slot {sc.sidecar_parts_slot}, block 0x{sc.sidecar_block_abs_off:05X}")
            if snapshot.global_visual_table_values:
                if snapshot.global_visual_table_mode_uniform_value is not None:
                    tooltip_parts.append(
                        f"0x5577+{snapshot.global_visual_table_mode_offset:X} Mode: "
                        f"0x{snapshot.global_visual_table_mode_uniform_value:02X}"
                    )
                else:
                    tooltip_parts.append(f"0x5577+{snapshot.global_visual_table_mode_offset:X} Mode: mixed")
                if snapshot.global_visual_table_mode_tail_value is not None:
                    tooltip_parts.append(
                        f"0x5577+{snapshot.global_visual_table_mode_offset:X} Tail: "
                        f"0x{snapshot.global_visual_table_mode_tail_value:02X}"
                    )
                if snapshot.global_visual_table_uniform_value is not None:
                    tooltip_parts.append(f"0x5577+0 Legacy: 0x{snapshot.global_visual_table_uniform_value:02X}")
                else:
                    tooltip_parts.append("0x5577+0 Legacy: mixed values")
            card.setToolTip("\n".join(tooltip_parts))

            row = idx // columns
            col = idx % columns
            self.snapshot_cards_layout.addWidget(card, row, col)
            self._snapshot_card_widgets[snapshot.car_abs_off] = card

        for col in range(columns):
            self.snapshot_cards_layout.setColumnStretch(col, 1)

    # -- Helpers -------------------------------------------------

    def _snapshot_filename_slug(self, text: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip("_") or "snapshot"

    def _ensure_user_snapshot_library_dir(self) -> Path:
        root = Path(self.user_snapshot_library_root)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _next_user_snapshot_path(self, snapshot: FullCarBuildSnapshot) -> Path:
        root = self._ensure_user_snapshot_library_dir()
        stem = f"{self.savefile.SNAPSHOT_FILE_PREFIX}{self._snapshot_filename_slug(snapshot.display_name)}"
        candidate = root / f"{stem}.json"
        suffix = 2
        while candidate.exists():
            candidate = root / f"{stem}-{suffix}.json"
            suffix += 1
        return candidate

    def _reload_snapshot_library(self) -> None:
        self.snapshot_library = SaveFile.load_snapshot_library(
            self.snapshot_library_root,
            user_root=self.user_snapshot_library_root,
        )
        self.snapshot_library_error = None

    def on_open_user_builds_folder(self) -> None:
        target = self._ensure_user_snapshot_library_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def on_save_build_to_user_library(self, abs_off: int) -> None:
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        snapshot = next((item for item in self.build_snapshots if item.car_abs_off == abs_off), None)
        if snapshot is None:
            QMessageBox.warning(self, UI_TITLE_SNAPSHOT_UNAVAILABLE, "Could not resolve the requested build snapshot.")
            return
        try:
            target_path = self._next_user_snapshot_path(snapshot)
            payload = self.savefile.snapshot_to_dict(snapshot)
            target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._reload_snapshot_library()
        except Exception as exc:
            QMessageBox.warning(self, "Save to My Builds failed", str(exc))
            return
        self._mark_presets_cards_dirty(library=True, snapshot=False)
        if self._presets_page_visible():
            self._refresh_presets_page(reason="data_change")
        ToastNotification.show_toast(self, "Saved to My Builds")

    def on_export_build_snapshot(self, abs_off: int) -> None:
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        snapshot = next((item for item in self.build_snapshots if item.car_abs_off == abs_off), None)
        if snapshot is None:
            QMessageBox.warning(self, UI_TITLE_SNAPSHOT_UNAVAILABLE, "Could not resolve the requested build snapshot.")
            return
        default_name = (
            f"{self.savefile.SNAPSHOT_FILE_PREFIX}"
            f"{self._snapshot_filename_slug(snapshot.display_name)}.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export build snapshot",
            str(Path.home() / default_name),
            "JSON (*.json)",
        )
        if not path:
            return
        payload = self.savefile.snapshot_to_dict(snapshot)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ToastNotification.show_toast(self, "Build snapshot exported")

    def _build_snapshot_library_card(self, vm: SnapshotLibraryCardVm) -> QWidget:
        entry = vm.entry
        card, card_layout = self._make_card_frame(
            changed=vm.staged_mode is not None,
            minimum_width=360,
        )

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        bucket_badge = QLabel(self._preset_bucket_ui_label(entry.library_bucket))
        bucket_badge.setObjectName("contentCardSlot")
        bucket_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        bucket_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(bucket_badge, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        source_badge = QLabel()
        source_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        source_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(source_badge, 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = QLabel(entry.display_name)
        name_label.setObjectName("contentCardMeta")
        name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        if entry.has_visual_sidecar:
            warn_badge = QLabel("Needs adjacent sidecar slots")
            warn_badge.setObjectName("contentCardNote")
            warn_badge.setWordWrap(True)
            card_layout.addWidget(warn_badge)
        if entry.requires_unresolved_global_visual_state:
            mode_text = (
                f"Uses extra 0x5577+{entry.global_visual_table_mode_offset:X} visual state not replayed in this preview"
                if entry.global_visual_table_mode_uniform_value is not None
                else "Uses extra 0x5577 visual state not replayed in this preview"
            )
            warn_badge = QLabel(mode_text)
            warn_badge.setObjectName("contentCardNote")
            warn_badge.setWordWrap(True)
            card_layout.addWidget(warn_badge)

        card_layout.addWidget(self._make_card_separator())

        card_layout.addWidget(self._make_card_field_label("Performance"))
        self._add_presets_perf_grid(card_layout, entry.performance_levels, self._presets_model_name(entry.primary_owned_record_template.signature, entry.display_name))

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        inject_my = self._make_card_action_button("Add to My Cars")
        inject_my.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "my_cars"))
        inject_my.setEnabled(
            self.savefile is not None
            and vm.plan_my is not None
            and vm.plan_my.refusal_reason is None
        )
        action_row.addWidget(inject_my)

        inject_career = self._make_card_action_button("Add to Career")
        inject_career.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "career"))
        inject_career.setEnabled(
            self.savefile is not None
            and vm.plan_career is not None
            and vm.plan_career.refusal_reason is None
        )
        action_row.addWidget(inject_career)

        unstage_btn = self._make_card_action_button("Unstage")
        unstage_btn.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_clear_snapshot_injection(sid))
        action_row.addWidget(unstage_btn)

        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        utility_label = QLabel()
        utility_label.setObjectName("mutedLabel")
        utility_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card_layout.addWidget(utility_label)
        self._snapshot_library_card_widgets[entry.snapshot_id] = card
        handle = SnapshotLibraryCardHandle(
            card=card,
            bucket_badge=bucket_badge,
            source_badge=source_badge,
            name_label=name_label,
            inject_my_btn=inject_my,
            inject_career_btn=inject_career,
            unstage_btn=unstage_btn,
            utility_label=utility_label,
        )
        self._snapshot_library_card_handles[entry.snapshot_id] = handle
        self._apply_snapshot_library_card_vm(handle, vm)
        card.setMinimumHeight(card.sizeHint().height() + 4)
        card.updateGeometry()
        refresh_widget_style(card)
        return card

    def _build_snapshot_library_card_for_key(self, snapshot_id: str) -> QWidget:
        vm = self._snapshot_library_live_vm_map.get(str(snapshot_id))
        if vm is None:
            raise KeyError(f"Missing presets VM for snapshot_id={snapshot_id}")
        return self._build_snapshot_library_card(vm)

    def _rebuild_snapshot_library_cards(self, *, animate: bool = False, reset_scroll: bool = False) -> None:
        if not hasattr(self, "snapshot_library_cards_layout"):
            return
        self._snapshot_library_card_widgets = {}
        self._snapshot_library_card_handles = {}
        view_models = self._snapshot_library_card_view_models()
        self._snapshot_library_visible_order = [vm.entry.snapshot_id for vm in view_models]
        self._snapshot_library_live_vm_map = {vm.entry.snapshot_id: vm for vm in view_models}
        columns = max(1, self._detect_library_card_columns())
        self._library_slot_columns = columns
        self._snapshot_library_render_controller.schedule_render(
            self._snapshot_library_visible_order,
            build_widget=self._build_snapshot_library_card_for_key,
            columns=columns,
            empty_widget_factory=self._snapshot_library_empty_widget,
            animate=animate,
            reset_scroll=reset_scroll,
        )
        self._snapshot_library_cards_dirty = False

    def _snapshot_cards_empty_widget(self, _: int) -> QWidget:
        if not self.savefile:
            text = "Open a save to inspect build snapshots from this save."
        elif self.snapshot_detection_error:
            text = f"Build snapshot tools unavailable: {self.snapshot_detection_error}"
        elif not self.build_snapshots:
            text = "No build snapshots were detected in this save."
        else:
            text = "No build snapshots match the current search."
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        return label

    def _snapshot_card_view_models(self) -> List[SnapshotCardVm]:
        if not self.savefile or self.snapshot_detection_error:
            return []
        return [SnapshotCardVm(snapshot=snapshot) for snapshot in self._snapshot_card_entries()]

    def _build_snapshot_card(self, vm: SnapshotCardVm) -> QWidget:
        snapshot = vm.snapshot
        card, card_layout = self._make_card_frame(minimum_width=360)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        slot_badge = QLabel(f"Parts Slot {snapshot.parts_slot}")
        slot_badge.setObjectName("contentCardSlot")
        slot_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        slot_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        header_row.addWidget(self._make_garage_source_badge(snapshot.source_kind), 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = QLabel(snapshot.display_name)
        name_label.setObjectName("contentCardMeta")
        name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        mode_label = QLabel(
            f"0x5577+{snapshot.global_visual_table_mode_offset:X} visual mode: "
            + (
                f"0x{snapshot.global_visual_table_mode_uniform_value:02X}"
                if snapshot.global_visual_table_mode_uniform_value is not None
                else "mixed"
            )
        )
        mode_label.setObjectName("contentCardNote")
        mode_label.setWordWrap(True)
        card_layout.addWidget(mode_label)

        card_layout.addWidget(self._make_card_separator())

        card_layout.addWidget(self._make_card_field_label("Performance"))
        self._add_presets_perf_grid(card_layout, snapshot.performance_levels, self._presets_model_name(snapshot.signature, snapshot.display_name))

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        save_btn = self._make_card_action_button("Save to My Builds")
        save_btn.clicked.connect(lambda _, off=snapshot.car_abs_off: self.on_save_build_to_user_library(off))
        action_row.addWidget(save_btn, 0, Qt.AlignLeft)
        export_btn = self._make_card_action_button("Export Snapshot...")
        export_btn.clicked.connect(lambda _, off=snapshot.car_abs_off: self.on_export_build_snapshot(off))
        action_row.addWidget(export_btn, 0, Qt.AlignLeft)
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        tooltip_parts = [
            f"Car #{snapshot.car_number:02X}",
            f"Loc 0x{snapshot.location_bits:02X} | Misc 0x{snapshot.misc_bits:02X}",
            f"Block 0x{snapshot.primary_build_block_abs_off:05X}",
        ]
        if snapshot.optional_visual_sidecar:
            sc = snapshot.optional_visual_sidecar
            tooltip_parts.append(f"Sidecar: slot {sc.sidecar_parts_slot}, block 0x{sc.sidecar_block_abs_off:05X}")
        if snapshot.global_visual_table_values:
            if snapshot.global_visual_table_mode_uniform_value is not None:
                tooltip_parts.append(
                    f"0x5577+{snapshot.global_visual_table_mode_offset:X} Mode: "
                    f"0x{snapshot.global_visual_table_mode_uniform_value:02X}"
                )
            else:
                tooltip_parts.append(f"0x5577+{snapshot.global_visual_table_mode_offset:X} Mode: mixed")
            if snapshot.global_visual_table_mode_tail_value is not None:
                tooltip_parts.append(
                    f"0x5577+{snapshot.global_visual_table_mode_offset:X} Tail: "
                    f"0x{snapshot.global_visual_table_mode_tail_value:02X}"
                )
            if snapshot.global_visual_table_uniform_value is not None:
                tooltip_parts.append(f"0x5577+0 Legacy: 0x{snapshot.global_visual_table_uniform_value:02X}")
            else:
                tooltip_parts.append("0x5577+0 Legacy: mixed values")
        card.setToolTip("\n".join(tooltip_parts))

        card.setMinimumHeight(card.sizeHint().height() + 4)
        card.updateGeometry()
        self._snapshot_card_widgets[snapshot.car_abs_off] = card
        refresh_widget_style(card)
        return card

    def _rebuild_snapshot_cards(self, *, animate: bool = False, reset_scroll: bool = False) -> None:
        if not hasattr(self, "snapshot_cards_layout"):
            return
        self._snapshot_card_widgets = {}
        columns = max(1, self._detect_snapshot_card_columns())
        self._snapshot_slot_columns = columns
        self._snapshot_render_controller.schedule_render(
            self._snapshot_card_view_models(),
            build_widget=self._build_snapshot_card,
            columns=columns,
            empty_widget_factory=self._snapshot_cards_empty_widget,
            animate=animate,
            reset_scroll=reset_scroll,
        )
        self._snapshot_cards_dirty = False

    def _refresh_presets_page(self, reason: str = "data_change") -> None:
        current_view = getattr(self, "presets_view", "Library")
        is_library = current_view == "Library"
        if hasattr(self, "presets_view_buttons"):
            for label, button in self.presets_view_buttons.items():
                button.setChecked(label == current_view)
        self._sync_presets_summary_chrome(loaded=bool(self.savefile))
        if hasattr(self, "presets_free_career_badge"):
            self.presets_free_career_badge.setVisible(is_library)
        if hasattr(self, "snapshot_library_filter_buttons"):
            for label, button in self.snapshot_library_filter_buttons.items():
                button.setVisible(is_library)
                button.setChecked(label == getattr(self, "snapshot_library_filter", "Main"))
        if hasattr(self, "snapshot_save_filter_buttons"):
            for label, button in self.snapshot_save_filter_buttons.items():
                button.setVisible(not is_library)
                button.setChecked(label == getattr(self, "snapshot_save_filter", "All"))
        if hasattr(self, "presets_stack"):
            self.presets_stack.setCurrentIndex(0 if is_library else 1)
        if hasattr(self, "presets_search"):
            self.presets_search.setPlaceholderText(
                "Search build library..." if is_library else "Search builds in this save..."
            )

        if not self._presets_page_visible():
            self._mark_presets_cards_dirty()
            return

        if is_library:
            if (
                getattr(self, "snapshot_library_filter", "Main") == "User"
                and reason in {"page_enter", "filter_change", "save_load_visible"}
            ):
                try:
                    self._reload_snapshot_library()
                except Exception as exc:
                    self.snapshot_library = []
                    self.snapshot_library_error = str(exc)
            columns = max(1, self._detect_library_card_columns())
            self._library_slot_columns = columns
            controller = self._snapshot_library_render_controller
            if (
                reason in {"page_enter", "reflow"}
                and not self._snapshot_library_cards_dirty
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
                self._patch_snapshot_library_cards_preserving_scroll()
                controller.replay_visible_reveal()
                return
            self._rebuild_snapshot_library_cards(
                animate=reason in {"page_enter", "filter_change", "reset_reveal", "save_load_visible"},
                reset_scroll=reason in {"search_change", "filter_change"},
            )
            return

        columns = max(1, self._detect_snapshot_card_columns())
        self._snapshot_slot_columns = columns
        controller = self._snapshot_render_controller
        if (
            reason in {"page_enter", "reflow"}
            and not self._snapshot_cards_dirty
            and controller.has_rendered_content()
            and not controller.is_rendering
        ):
            if reason == "page_enter" and columns == controller.current_columns:
                controller.replay_visible_reveal()
            else:
                controller.reflow(columns)
            return
        self._rebuild_snapshot_cards(
            animate=reason in {"page_enter", "filter_change", "reset_reveal", "save_load_visible"},
            reset_scroll=reason in {"search_change", "filter_change"},
        )

    def _sync_presets_summary_chrome(self, *, loaded: bool) -> None:
        if not hasattr(self, "presets_free_career_badge"):
            return
        if not loaded or not self.savefile:
            self.presets_free_career_badge.setText("Free Career Slots: -")
            return
        try:
            snapshot = self._current_allocator_snapshot()
        except Exception:
            snapshot = None
        if snapshot is None:
            self.presets_free_career_badge.setText("Free Career Slots: -")
            return
        self.presets_free_career_badge.setText(
            f"Free Career Slots: {len(snapshot.reusable_career_slots)}"
        )

    def on_stage_snapshot_injection(self, snapshot_id: str, target_mode: str) -> None:
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        library_by_id = self._snapshot_library_by_id()
        entry = library_by_id.get(str(snapshot_id))
        if entry is None:
            QMessageBox.warning(self, UI_TITLE_SNAPSHOT_UNAVAILABLE, "Could not resolve the selected library snapshot.")
            return
        plans, _, _, _ = self._current_snapshot_injection_plans(
            extra_snapshot_id=entry.snapshot_id,
            extra_target_mode=target_mode,
        )
        plan = plans.get(entry.snapshot_id)
        if plan is None or plan.refusal_reason:
            reason = plan.refusal_reason if plan is not None else "Unknown injector planner failure"
            QMessageBox.warning(self, UI_TITLE_BLOCKED, reason)
            return
        self.staged_state.snapshot_injections.stage(entry.snapshot_id, str(target_mode))
        self._snapshot_library_cards_dirty = True
        self._mark_garage_cards_dirty()
        self._sync_presets_summary_chrome(loaded=True)
        self._patch_snapshot_library_cards_preserving_scroll()
        self._update_action_states()

    def on_clear_snapshot_injection(self, snapshot_id: str) -> None:
        if self.staged_state.snapshot_injections.mode_for(str(snapshot_id)) is not None:
            self.staged_state.snapshot_injections.clear(str(snapshot_id))
            self._snapshot_library_cards_dirty = True
            self._mark_garage_cards_dirty()
            self._sync_presets_summary_chrome(loaded=True)
            self._patch_snapshot_library_cards_preserving_scroll()
            self._update_action_states()
