"""Presets page: token preset I/O, build-library injection, save snapshot export."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Dict, List

from PySide6.QtCore import Qt
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

from core.models import FullCarBuildSnapshot, SnapshotInjectionPlan, SnapshotLibraryEntry
from core.tuning_limits import get_model_tuning_limits
from ui.pages.constants import *
from ui.rendering import ViewportLazyGridController, refresh_widget_style
from ui.widgets import ToastNotification, build_perf_level_row

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
    # ── Page builder ────────────────────────────────────────────

    def _build_presets_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        # ── 1. Junkman Presets compact strip ──────────────────
        preset_frame = QFrame()
        preset_frame.setObjectName("settingsGroup")
        preset_inner = QVBoxLayout(preset_frame)
        preset_inner.setContentsMargins(12, 8, 12, 8)
        preset_inner.setSpacing(6)
        preset_title = QLabel("Token Presets")
        preset_title.setObjectName("settingsGroupTitle")
        preset_inner.addWidget(preset_title)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self.btn_load_preset = QPushButton("Import Tokens")
        self.btn_save_preset = QPushButton("Export Tokens")
        self.btn_export_have = QPushButton("Export Current Tokens")
        self.btn_load_preset.clicked.connect(self.on_load_preset)
        self.btn_save_preset.clicked.connect(self.on_save_preset)
        self.btn_export_have.clicked.connect(self.on_export_have)
        for btn in [self.btn_load_preset, self.btn_save_preset, self.btn_export_have]:
            preset_row.addWidget(btn)
        preset_row.addStretch(1)
        preset_inner.addLayout(preset_row)
        layout.addWidget(preset_frame)

        # ── 2. Car Builds header + view toggle ─────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        boss_label = QLabel("Car Builds")
        boss_label.setObjectName("sectionLabel")
        header_row.addWidget(boss_label)
        header_row.addStretch(1)
        self.presets_view_group = QButtonGroup(self)
        self.presets_view_group.setExclusive(True)
        self.presets_view_buttons: Dict[str, QPushButton] = {}
        for name in ["Library", "My Save"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("garageFilterBtn")
            btn.clicked.connect(lambda _, v=name: self._on_presets_view_changed(v))
            self.presets_view_group.addButton(btn)
            self.presets_view_buttons[name] = btn
            header_row.addWidget(btn)
        self.presets_view_buttons["Library"].setChecked(True)
        layout.addLayout(header_row)

        # ── 3. Library sub-filters + unified search ───────────
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.snapshot_library_filter_group = QButtonGroup(self)
        self.snapshot_library_filter_group.setExclusive(True)
        self.snapshot_library_filter_buttons: Dict[str, QPushButton] = {}
        for name in ["All", "Main", "Bonus"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("garageFilterBtn")
            btn.clicked.connect(lambda _, v=name: self.on_snapshot_library_filter_changed(v))
            self.snapshot_library_filter_group.addButton(btn)
            self.snapshot_library_filter_buttons[name] = btn
            controls.addWidget(btn)
        self.snapshot_library_filter_buttons["All"].setChecked(True)
        self.presets_search = QLineEdit()
        self.presets_search.setPlaceholderText("Search build library...")
        self.presets_search.textChanged.connect(self._on_presets_search_changed)
        controls.addWidget(self.presets_search, 1)
        layout.addLayout(controls)

        # ── 4. QStackedWidget: Library / My Save ──────────────
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
        )
        self._snapshot_render_controller = ViewportLazyGridController(
            self,
            name="PresetsMySave",
            layout=self.snapshot_cards_layout,
            scroll_area=self.snapshot_cards_scroll,
        )
        return w

    def _presets_page_visible(self) -> bool:
        return hasattr(self, "stack") and hasattr(self, "page_presets") and self.stack.currentWidget() is self.page_presets

    # ── View toggle / search ────────────────────────────────────

    def _on_presets_view_changed(self, view: str) -> None:
        self.presets_view = view
        is_library = view == "Library"
        for btn in self.snapshot_library_filter_buttons.values():
            btn.setVisible(is_library)
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

    # ── Shared perf grid (read-only) ────────────────────────────

    def _add_presets_perf_grid(self, parent: QVBoxLayout, performance_levels, model_name: str = "") -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        limits = get_model_tuning_limits(model_name)
        for idx, (name, level) in enumerate(performance_levels):
            max_level = max(level, int(limits.get(name, 0))) if limits is not None else None
            row_w, _ = build_perf_level_row(name, level, max_level)
            grid.addWidget(row_w, idx // 2, idx % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)

    # ── Library card columns / reflow ───────────────────────────

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

    # ── Library entries filter ──────────────────────────────────

    def _snapshot_library_entries(self) -> List[SnapshotLibraryEntry]:
        query = ""
        if hasattr(self, "presets_search"):
            query = self.presets_search.text().strip().lower()
        entries = list(self.snapshot_library)
        if self.snapshot_library_filter != "All":
            entries = [entry for entry in entries if entry.library_bucket == self.snapshot_library_filter]
        if query:
            entries = [
                entry for entry in entries
                if query in entry.display_name.lower() or query in entry.file_label.lower()
            ]
        return entries

    def _snapshot_library_empty_widget(self, _: int) -> QWidget:
        if self.snapshot_library_error:
            text = f"Build library unavailable: {self.snapshot_library_error}"
        elif not self.snapshot_library:
            text = f"No snapshot files found in {self.snapshot_library_root}."
        else:
            text = "No build-library entries match the current search."
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        label.setWordWrap(True)
        return label

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
                    staged_mode=self.want_snapshot_injections.get(entry.snapshot_id),
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
            return (
                "Staged to My Cars" if vm.staged_mode == "my_cars" else "Staged to Career",
                "\n".join(tooltip_parts) or "Injection is staged.",
            )
        if vm.plan_my is not None and vm.plan_my.refusal_reason:
            tooltip_parts.append(f"My Cars blocked: {vm.plan_my.refusal_reason}")
        if vm.plan_career is not None and vm.plan_career.refusal_reason:
            tooltip_parts.append(f"Career blocked: {vm.plan_career.refusal_reason}")
        if tooltip_parts:
            if len(tooltip_parts) == 2:
                return "All targets blocked", "\n".join(tooltip_parts)
            return (
                "My Cars blocked" if tooltip_parts[0].startswith("My Cars") else "Career blocked",
                "\n".join(tooltip_parts),
            )
        return "Ready to stage", "Both injection targets are currently available."

    def _snapshot_library_card_tooltip(self, vm: SnapshotLibraryCardVm) -> str:
        entry = vm.entry
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
        utility_text, utility_tooltip = self._snapshot_library_utility_summary(vm)
        tooltip_parts.append(f"State: {utility_text}")
        if utility_tooltip:
            tooltip_parts.append(utility_tooltip)
        return "\n".join(tooltip_parts)

    def _apply_snapshot_library_card_vm(self, handle: SnapshotLibraryCardHandle, vm: SnapshotLibraryCardVm) -> None:
        entry = vm.entry
        handle.card.setProperty("changed", vm.staged_mode is not None)
        handle.bucket_badge.setText(entry.library_bucket)
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

    # ── Library cards ───────────────────────────────────────────

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
            staged_mode = self.want_snapshot_injections.get(entry.snapshot_id)
            plan_my = None
            plan_career = None
            if self.savefile and not self.snapshot_library_error:
                plan_my = self._current_snapshot_injection_plans(extra=(entry.snapshot_id, "my_cars"))[0].get(entry.snapshot_id)
                plan_career = self._current_snapshot_injection_plans(extra=(entry.snapshot_id, "career"))[0].get(entry.snapshot_id)
            staged_plan = plans.get(entry.snapshot_id)

            card = QFrame()
            card.setObjectName("partsCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(360)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # Header: bucket badge + source badge
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            bucket_badge = QLabel(entry.library_bucket)
            bucket_badge.setObjectName("garageCardSlot")
            bucket_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bucket_badge.setAlignment(Qt.AlignCenter)
            source_badge = self._make_garage_source_badge(entry.source_kind)
            header_row.addWidget(bucket_badge, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_badge, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # Car name
            name_label = QLabel(entry.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # Capability / warning badges
            if entry.has_visual_sidecar:
                warn_badge = QLabel("Needs adjacent sidecar slots")
                warn_badge.setObjectName("partsCardNote")
                warn_badge.setWordWrap(True)
                card_layout.addWidget(warn_badge)
            if entry.requires_unresolved_global_visual_state:
                mode_text = (
                    f"Uses extra 0x5577+{entry.global_visual_table_mode_offset:X} visual state not replayed in this preview"
                    if entry.global_visual_table_mode_uniform_value is not None
                    else "Uses extra 0x5577 visual state not replayed in this preview"
                )
                warn_badge = QLabel(mode_text)
                warn_badge.setObjectName("partsCardNote")
                warn_badge.setWordWrap(True)
                card_layout.addWidget(warn_badge)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # Performance bars (read-only, proper caps)
            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)
            self._add_presets_perf_grid(card_layout, entry.performance_levels, entry.display_name)

            # Action row
            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            inject_my = QPushButton("Add to My Cars")
            inject_my.setObjectName("partsBulkBtn")
            inject_my.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "my_cars"))
            inject_career = QPushButton("Add to Career")
            inject_career.setObjectName("partsBulkBtn")
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
                unstage_btn = QPushButton("Unstage")
                unstage_btn.setObjectName("partsBulkBtn")
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

    # ── Snapshot card columns / reflow ──────────────────────────

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

    # ── Snapshot entries filter ─────────────────────────────────

    def _snapshot_card_entries(self) -> List[FullCarBuildSnapshot]:
        query = ""
        if hasattr(self, "presets_search"):
            query = self.presets_search.text().strip().lower()
        entries = list(self.build_snapshots)
        if query:
            entries = [entry for entry in entries if query in entry.display_name.lower()]
        return entries

    # ── Snapshot cards (My Save view) ───────────────────────────

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
            card = QFrame()
            card.setObjectName("partsCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(360)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # Header: parts slot badge + source badge
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_badge = QLabel(f"Parts Slot {snapshot.parts_slot}")
            slot_badge.setObjectName("garageCardSlot")
            slot_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_badge.setAlignment(Qt.AlignCenter)
            source_badge = self._make_garage_source_badge(snapshot.source_kind)
            header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_badge, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # Car name
            name_label = QLabel(snapshot.display_name)
            name_label.setObjectName("garageCardMeta")
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
            mode_label.setObjectName("partsCardNote")
            mode_label.setWordWrap(True)
            card_layout.addWidget(mode_label)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # Performance bars (read-only)
            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)
            self._add_presets_perf_grid(card_layout, snapshot.performance_levels, snapshot.display_name)

            # Export button
            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            export_btn = QPushButton("Export Snapshot")
            export_btn.setObjectName("partsBulkBtn")
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

    # ── Refresh ─────────────────────────────────────────────────

    def _refresh_presets_page(self) -> None:
        self._rebuild_snapshot_library_cards()
        self._rebuild_snapshot_cards()

    # ── Helpers ─────────────────────────────────────────────────

    def _snapshot_filename_slug(self, text: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip("_") or "snapshot"

    # ── Injection staging ───────────────────────────────────────

    def on_stage_snapshot_injection(self, snapshot_id: str, target_mode: str) -> None:
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        library_by_id = self._snapshot_library_by_id()
        entry = library_by_id.get(str(snapshot_id))
        if entry is None:
            QMessageBox.warning(self, UI_TITLE_SNAPSHOT_UNAVAILABLE, "Could not resolve the selected library snapshot.")
            return
        plans, _, _, _ = self._current_snapshot_injection_plans(extra=(entry.snapshot_id, target_mode))
        plan = plans.get(entry.snapshot_id)
        if plan is None or plan.refusal_reason:
            reason = plan.refusal_reason if plan is not None else "Unknown injector planner failure"
            QMessageBox.warning(self, UI_TITLE_BLOCKED, reason)
            return
        self.want_snapshot_injections[entry.snapshot_id] = str(target_mode)
        self._refresh_presets_page()
        self._refresh_garage_page()
        self._update_action_states()

    def on_clear_snapshot_injection(self, snapshot_id: str) -> None:
        if str(snapshot_id) in self.want_snapshot_injections:
            self.want_snapshot_injections.pop(str(snapshot_id), None)
            self._refresh_presets_page()
            self._refresh_garage_page()
            self._update_action_states()

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
        card = QFrame()
        card.setObjectName("partsCard")
        card.setProperty("changed", vm.staged_mode is not None)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumWidth(360)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        bucket_badge = QLabel(entry.library_bucket)
        bucket_badge.setObjectName("garageCardSlot")
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
        name_label.setObjectName("garageCardMeta")
        name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        name_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(name_label, 0, Qt.AlignLeft)

        if entry.has_visual_sidecar:
            warn_badge = QLabel("Needs adjacent sidecar slots")
            warn_badge.setObjectName("partsCardNote")
            warn_badge.setWordWrap(True)
            card_layout.addWidget(warn_badge)
        if entry.requires_unresolved_global_visual_state:
            mode_text = (
                f"Uses extra 0x5577+{entry.global_visual_table_mode_offset:X} visual state not replayed in this preview"
                if entry.global_visual_table_mode_uniform_value is not None
                else "Uses extra 0x5577 visual state not replayed in this preview"
            )
            warn_badge = QLabel(mode_text)
            warn_badge.setObjectName("partsCardNote")
            warn_badge.setWordWrap(True)
            card_layout.addWidget(warn_badge)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("garageCardSep")
        card_layout.addWidget(sep)

        perf_label = QLabel("Performance")
        perf_label.setObjectName("garageCardFieldLabel")
        perf_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(perf_label)
        self._add_presets_perf_grid(card_layout, entry.performance_levels, entry.display_name)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        inject_my = QPushButton("Add to My Cars")
        inject_my.setObjectName("partsBulkBtn")
        inject_my.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "my_cars"))
        inject_my.setEnabled(
            self.savefile is not None
            and vm.plan_my is not None
            and vm.plan_my.refusal_reason is None
        )
        action_row.addWidget(inject_my)

        inject_career = QPushButton("Add to Career")
        inject_career.setObjectName("partsBulkBtn")
        inject_career.clicked.connect(lambda _, sid=entry.snapshot_id: self.on_stage_snapshot_injection(sid, "career"))
        inject_career.setEnabled(
            self.savefile is not None
            and vm.plan_career is not None
            and vm.plan_career.refusal_reason is None
        )
        action_row.addWidget(inject_career)

        unstage_btn = QPushButton("Unstage")
        unstage_btn.setObjectName("partsBulkBtn")
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
        card = QFrame()
        card.setObjectName("partsCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumWidth(360)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        slot_badge = QLabel(f"Parts Slot {snapshot.parts_slot}")
        slot_badge.setObjectName("garageCardSlot")
        slot_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        slot_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(slot_badge, 0, Qt.AlignLeft)
        header_row.addStretch(1)
        header_row.addWidget(self._make_garage_source_badge(snapshot.source_kind), 0, Qt.AlignRight)
        card_layout.addLayout(header_row)

        name_label = QLabel(snapshot.display_name)
        name_label.setObjectName("garageCardMeta")
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
        mode_label.setObjectName("partsCardNote")
        mode_label.setWordWrap(True)
        card_layout.addWidget(mode_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("garageCardSep")
        card_layout.addWidget(sep)

        perf_label = QLabel("Performance")
        perf_label.setObjectName("garageCardFieldLabel")
        perf_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(perf_label)
        self._add_presets_perf_grid(card_layout, snapshot.performance_levels, snapshot.display_name)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        export_btn = QPushButton("Export Snapshot")
        export_btn.setObjectName("partsBulkBtn")
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
        if hasattr(self, "snapshot_library_filter_buttons"):
            for label, button in self.snapshot_library_filter_buttons.items():
                button.setVisible(is_library)
                button.setChecked(label == getattr(self, "snapshot_library_filter", "All"))
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
            columns = max(1, self._detect_library_card_columns())
            self._library_slot_columns = columns
            if (
                reason in {"page_enter", "reflow"}
                and not self._snapshot_library_cards_dirty
                and self._snapshot_library_render_controller.has_rendered_content()
            ):
                self._snapshot_library_render_controller.reflow(columns)
                return
            self._rebuild_snapshot_library_cards(
                animate=reason in {"page_enter", "filter_change"},
                reset_scroll=reason in {"search_change", "filter_change"},
            )
            return

        columns = max(1, self._detect_snapshot_card_columns())
        self._snapshot_slot_columns = columns
        if (
            reason in {"page_enter", "reflow"}
            and not self._snapshot_cards_dirty
            and self._snapshot_render_controller.has_rendered_content()
        ):
            self._snapshot_render_controller.reflow(columns)
            return
        self._rebuild_snapshot_cards(
            animate=reason in {"page_enter", "filter_change"},
            reset_scroll=reason in {"search_change", "filter_change"},
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
        plans, _, _, _ = self._current_snapshot_injection_plans(extra=(entry.snapshot_id, target_mode))
        plan = plans.get(entry.snapshot_id)
        if plan is None or plan.refusal_reason:
            reason = plan.refusal_reason if plan is not None else "Unknown injector planner failure"
            QMessageBox.warning(self, UI_TITLE_BLOCKED, reason)
            return
        self.want_snapshot_injections[entry.snapshot_id] = str(target_mode)
        self._snapshot_library_cards_dirty = True
        self._mark_garage_cards_dirty()
        self._patch_snapshot_library_cards_in_place()
        self._update_action_states()

    def on_clear_snapshot_injection(self, snapshot_id: str) -> None:
        if str(snapshot_id) in self.want_snapshot_injections:
            self.want_snapshot_injections.pop(str(snapshot_id), None)
            self._snapshot_library_cards_dirty = True
            self._mark_garage_cards_dirty()
            self._patch_snapshot_library_cards_in_place()
            self._update_action_states()
