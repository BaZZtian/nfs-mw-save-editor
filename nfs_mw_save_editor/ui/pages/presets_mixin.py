"""Presets page: token preset I/O, build-library injection, save snapshot export."""
from __future__ import annotations

import json
from pathlib import Path
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

from core.models import FullCarBuildSnapshot, SnapshotLibraryEntry
from core.tuning_limits import get_model_tuning_limits
from ui.pages.constants import *
from ui.widgets import ToastNotification, build_perf_level_row


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
        self.snapshot_cards_scroll.setWidget(self.snapshot_cards)
        self.presets_stack.addWidget(self.snapshot_cards_scroll)

        layout.addWidget(self.presets_stack, 1)

        self._snapshot_card_widgets: Dict[int, QFrame] = {}
        self._snapshot_library_card_widgets: Dict[str, QFrame] = {}
        self._rebuild_snapshot_library_cards()
        self._rebuild_snapshot_cards()
        return w

    # ── View toggle / search ────────────────────────────────────

    def _on_presets_view_changed(self, view: str) -> None:
        self.presets_view = view
        is_library = (view == "Library")
        for btn in self.snapshot_library_filter_buttons.values():
            btn.setVisible(is_library)
        self.presets_stack.setCurrentIndex(0 if is_library else 1)
        self.presets_search.setPlaceholderText(
            "Search build library..." if is_library else "Search builds in this save...",
        )
        self._refresh_presets_page()

    def _on_presets_search_changed(self) -> None:
        self._refresh_presets_page()

    def on_snapshot_library_filter_changed(self, value: str) -> None:
        self.snapshot_library_filter = str(value)
        for label, button in self.snapshot_library_filter_buttons.items():
            button.setChecked(label == self.snapshot_library_filter)
        self._refresh_presets_page()

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
        self._maybe_reflow_cols(
            "snapshot_library_scroll", "_library_slot_columns", LIBRARY_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_snapshot_library_cards, force,
        )

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
        self._maybe_reflow_cols(
            "snapshot_cards_scroll", "_snapshot_slot_columns", SNAPSHOT_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_snapshot_cards, force,
        )

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
