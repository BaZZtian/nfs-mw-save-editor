"""Presets page: snapshot library cards, snapshot injection workflow."""
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
    QVBoxLayout,
    QWidget,
)

from core.models import FullCarBuildSnapshot, SnapshotLibraryEntry
from core.savefile import SaveFile
from ui.pages.constants import *
from ui.widgets import ToastNotification


class PresetsMixin:
    def _build_presets_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        section = QLabel("Inventory Presets")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        hint = QLabel(
            "Legacy Junkman preset import/export stays here. The boss-car injector library below stages snapshot "
            "injections into the current save, while the inspector section remains a read-only reverse/debug view."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self.btn_load_preset = QPushButton("Load preset JSON")
        self.btn_save_preset = QPushButton("Save preset JSON")
        self.btn_export_have = QPushButton("Export Have as preset")
        self.btn_load_preset.clicked.connect(self.on_load_preset)
        self.btn_save_preset.clicked.connect(self.on_save_preset)
        self.btn_export_have.clicked.connect(self.on_export_have)
        preset_row.addWidget(self.btn_load_preset)
        preset_row.addWidget(self.btn_save_preset)
        preset_row.addWidget(self.btn_export_have)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        sep = QFrame()
        sep.setObjectName("sectionLine")
        layout.addWidget(sep)

        library_label = QLabel("Boss Car Injector Library")
        library_label.setObjectName("sectionLabel")
        layout.addWidget(library_label)

        library_hint = QLabel(
            "Snapshots are loaded from your Desktop `unique_cars` library. Injector v1 copies the confirmed primary "
            "`0x198` build block into allocator-picked slots. The unresolved `0x5577` global visual table is not "
            "replayed yet, so injected visuals may be slightly incomplete."
        )
        library_hint.setObjectName("mutedLabel")
        library_hint.setWordWrap(True)
        layout.addWidget(library_hint)

        library_controls = QHBoxLayout()
        library_controls.setSpacing(8)
        self.snapshot_library_search = QLineEdit()
        self.snapshot_library_search.setPlaceholderText("Search boss-car library by model or file name...")
        self.snapshot_library_search.textChanged.connect(self.on_snapshot_library_search_changed)
        library_controls.addWidget(self.snapshot_library_search, 1)

        self.snapshot_library_filter_group = QButtonGroup(self)
        self.snapshot_library_filter_group.setExclusive(True)
        self.snapshot_library_filter_buttons: Dict[str, QPushButton] = {}
        for name in ["All", "Main", "Bonus"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("garageFilterBtn")
            btn.clicked.connect(lambda checked=False, value=name: self.on_snapshot_library_filter_changed(value))
            self.snapshot_library_filter_group.addButton(btn)
            self.snapshot_library_filter_buttons[name] = btn
            library_controls.addWidget(btn)
        self.snapshot_library_filter_buttons["All"].setChecked(True)
        library_controls.addStretch(1)
        layout.addLayout(library_controls)

        self.snapshot_library_cards = QWidget()
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
        layout.addWidget(self.snapshot_library_scroll, 1)

        sep = QFrame()
        sep.setObjectName("sectionLine")
        layout.addWidget(sep)

        snapshot_label = QLabel("Boss Car Snapshot Inspector")
        snapshot_label.setObjectName("sectionLabel")
        layout.addWidget(snapshot_label)

        snapshot_hint = QLabel(
            "Build snapshots are extracted from owned-car records. The inspector reports the primary `0x198` build "
            "block, optional `parts_slot + 1` visual sidecars, and whether the unresolved `0x5577` visual table also "
            "changed in this save."
        )
        snapshot_hint.setObjectName("mutedLabel")
        snapshot_hint.setWordWrap(True)
        layout.addWidget(snapshot_hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.snapshot_search = QLineEdit()
        self.snapshot_search.setPlaceholderText("Search build snapshots by model name...")
        self.snapshot_search.textChanged.connect(self.on_snapshot_search_changed)
        controls.addWidget(self.snapshot_search, 1)
        layout.addLayout(controls)

        self.snapshot_cards = QWidget()
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
        layout.addWidget(self.snapshot_cards_scroll, 1)

        self._snapshot_card_widgets: Dict[int, QFrame] = {}
        self._snapshot_library_card_widgets: Dict[str, QFrame] = {}
        self._rebuild_snapshot_library_cards()
        self._rebuild_snapshot_cards()
        return w

    def on_snapshot_library_search_changed(self) -> None:
        self._refresh_presets_page()

    def on_snapshot_library_filter_changed(self, value: str) -> None:
        self.snapshot_library_filter = str(value)
        for label, button in self.snapshot_library_filter_buttons.items():
            button.setChecked(label == self.snapshot_library_filter)
        self._refresh_presets_page()

    def _detect_library_card_columns(self) -> int:
        return self._detect_col_count("snapshot_library_scroll", LIBRARY_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_library_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols(
            "snapshot_library_scroll", "_library_slot_columns", LIBRARY_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_snapshot_library_cards, force,
        )

    def _snapshot_library_entries(self) -> List[SnapshotLibraryEntry]:
        query = ""
        if hasattr(self, "snapshot_library_search"):
            query = self.snapshot_library_search.text().strip().lower()
        entries = list(self.snapshot_library)
        if self.snapshot_library_filter != "All":
            entries = [entry for entry in entries if entry.library_bucket == self.snapshot_library_filter]
        if query:
            entries = [
                entry for entry in entries
                if query in entry.display_name.lower() or query in entry.file_label.lower()
            ]
        return entries

    def _library_entry_subtitle(self, entry: SnapshotLibraryEntry) -> str:
        label = entry.file_label
        if label.startswith("boss_car_snapshot_"):
            label = label[len("boss_car_snapshot_"):]
        return label.replace("_", " ")

    def _rebuild_snapshot_library_cards(self) -> None:
        if not hasattr(self, "snapshot_library_cards_layout"):
            return
        self._clear_layout(self.snapshot_library_cards_layout)
        self._snapshot_library_card_widgets = {}
        columns = max(1, self._detect_library_card_columns())
        self._library_slot_columns = columns

        if self.snapshot_library_error:
            label = QLabel(f"Snapshot library unavailable: {self.snapshot_library_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.snapshot_library_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._snapshot_library_entries()
        if not visible_entries:
            label = QLabel(
                f"No snapshot files found in {self.snapshot_library_root}."
                if not self.snapshot_library
                else "No snapshot library entries match the current search."
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

            name_label = QLabel(entry.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            subtitle = QLabel(self._library_entry_subtitle(entry))
            subtitle.setObjectName("partsCardNote")
            subtitle.setWordWrap(True)
            card_layout.addWidget(subtitle)

            status_row = QHBoxLayout()
            status_row.setSpacing(8)
            for text in [
                "Primary only" if not entry.has_visual_sidecar else "Sidecar blocked",
                "0x5577 ignored in v1" if entry.requires_unresolved_global_visual_state else "No global visual warning",
            ]:
                badge = QLabel(text)
                badge.setObjectName("garageCardStatBadge")
                badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                badge.setAlignment(Qt.AlignCenter)
                status_row.addWidget(badge, 0, Qt.AlignLeft)
            status_row.addStretch(1)
            card_layout.addLayout(status_row)

            plan_label = QLabel()
            plan_label.setObjectName("mutedLabel")
            plan_label.setWordWrap(True)
            if not self.savefile:
                plan_label.setText("Open a save to plan injection targets.")
            elif staged_plan is not None and staged_plan.refusal_reason is None:
                slot_text = f"owned 0x{staged_plan.target_owned_abs_off:05X}, parts {staged_plan.target_parts_slot}"
                if staged_plan.target_career_slot is not None:
                    slot_text += f", career {staged_plan.target_career_slot + 1}"
                plan_label.setText(f"Staged: {staged_plan.target_mode} -> {slot_text}")
            elif staged_plan is not None and staged_plan.refusal_reason:
                plan_label.setText(f"Staged plan blocked: {staged_plan.refusal_reason}")
            else:
                ready_targets: List[str] = []
                if plan_my is not None and plan_my.refusal_reason is None:
                    ready_targets.append(
                        f"My Cars: owned 0x{plan_my.target_owned_abs_off:05X}, parts {plan_my.target_parts_slot}"
                    )
                if plan_career is not None and plan_career.refusal_reason is None:
                    ready_targets.append(
                        f"Career: owned 0x{plan_career.target_owned_abs_off:05X}, parts {plan_career.target_parts_slot}, career {plan_career.target_career_slot + 1}"
                    )
                plan_label.setText(" | ".join(ready_targets) if ready_targets else "No validated injector target is currently available.")
            card_layout.addWidget(plan_label)

            if entry.requires_unresolved_global_visual_state:
                warn = QLabel("Warning: the unresolved global visual table `0x5577` is not injected in v1.")
                warn.setObjectName("partsCardNote")
                warn.setWordWrap(True)
                card_layout.addWidget(warn)

            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            inject_my = QPushButton("Inject to My Cars")
            inject_my.setObjectName("partsBulkBtn")
            inject_my.clicked.connect(lambda _, snapshot_id=entry.snapshot_id: self.on_stage_snapshot_injection(snapshot_id, "my_cars"))
            inject_career = QPushButton("Inject to Career")
            inject_career.setObjectName("partsBulkBtn")
            inject_career.clicked.connect(lambda _, snapshot_id=entry.snapshot_id: self.on_stage_snapshot_injection(snapshot_id, "career"))
            clear_btn = QPushButton("Clear staged")
            clear_btn.setObjectName("partsBulkBtn")
            clear_btn.clicked.connect(lambda _, snapshot_id=entry.snapshot_id: self.on_clear_snapshot_injection(snapshot_id))

            inject_my.setEnabled(self.savefile is not None and (plan_my is not None and plan_my.refusal_reason is None))
            inject_career.setEnabled(self.savefile is not None and (plan_career is not None and plan_career.refusal_reason is None))
            clear_btn.setEnabled(staged_mode is not None)
            if staged_mode == "my_cars":
                inject_my.setText("Staged to My Cars")
                inject_my.setEnabled(False)
            elif staged_mode == "career":
                inject_career.setText("Staged to Career")
                inject_career.setEnabled(False)

            action_row.addWidget(inject_my, 0, Qt.AlignLeft)
            action_row.addWidget(inject_career, 0, Qt.AlignLeft)
            action_row.addWidget(clear_btn, 0, Qt.AlignLeft)
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)

            perf_value = QLabel(" / ".join(f"{name}:{value}" for name, value in entry.performance_levels))
            perf_value.setObjectName("partsCardRaw")
            perf_value.setAlignment(Qt.AlignCenter)
            perf_value.setWordWrap(True)
            card_layout.addWidget(perf_value)

            row = idx // columns
            col = idx % columns
            self.snapshot_library_cards_layout.addWidget(card, row, col)
            self._snapshot_library_card_widgets[entry.snapshot_id] = card

        for col in range(columns):
            self.snapshot_library_cards_layout.setColumnStretch(col, 1)

    def on_snapshot_search_changed(self) -> None:
        self._refresh_presets_page()

    def _detect_snapshot_card_columns(self) -> int:
        return self._detect_col_count("snapshot_cards_scroll", SNAPSHOT_TILE_MIN_WIDTH, ((1100, 2),))

    def _maybe_reflow_snapshot_rows(self, force: bool = False) -> None:
        self._maybe_reflow_cols(
            "snapshot_cards_scroll", "_snapshot_slot_columns", SNAPSHOT_TILE_MIN_WIDTH,
            ((1100, 2),), self._rebuild_snapshot_cards, force,
        )

    def _snapshot_card_entries(self) -> List[FullCarBuildSnapshot]:
        query = ""
        if hasattr(self, "snapshot_search"):
            query = self.snapshot_search.text().strip().lower()
        entries = list(self.build_snapshots)
        if query:
            entries = [entry for entry in entries if query in entry.display_name.lower()]
        return entries

    def _snapshot_perf_text(self, snapshot: FullCarBuildSnapshot) -> str:
        return " / ".join(f"{name}:{value}" for name, value in snapshot.performance_levels)

    def _snapshot_filename_slug(self, text: str) -> str:
        safe = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
        while "__" in safe:
            safe = safe.replace("__", "_")
        return safe.strip("_") or "snapshot"

    def _snapshot_global_table_text(self, snapshot: FullCarBuildSnapshot) -> str:
        if not snapshot.global_visual_table_values:
            return "Visual Table N/A"
        if snapshot.global_visual_table_uniform_value is not None:
            if snapshot.global_visual_table_uniform_value == SaveFile.VISUAL_TABLE_DEFAULT_VALUE:
                return f"Visual Table default (0x{snapshot.global_visual_table_uniform_value:02X})"
            return f"Visual Table changed (0x{snapshot.global_visual_table_uniform_value:02X})"
        values = ", ".join(f"0x{value:02X}" for value in sorted(set(snapshot.global_visual_table_values)))
        return f"Visual Table mixed ({values})"

    def _rebuild_snapshot_cards(self) -> None:
        if not hasattr(self, "snapshot_cards_layout"):
            return
        self._clear_layout(self.snapshot_cards_layout)
        self._snapshot_card_widgets = {}
        columns = max(1, self._detect_snapshot_card_columns())
        self._snapshot_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect boss-car build snapshots.")
            label.setObjectName("mutedLabel")
            self.snapshot_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.snapshot_detection_error:
            label = QLabel(f"Snapshot inspector unavailable: {self.snapshot_detection_error}")
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

            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            source_label = self._make_garage_source_badge(snapshot.source_kind)
            primary_label = QLabel(f"Primary Slot {snapshot.parts_slot}")
            primary_label.setObjectName("garageCardSlot")
            primary_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            primary_label.setAlignment(Qt.AlignCenter)
            header_row.addWidget(primary_label, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_label, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            name_label = QLabel(snapshot.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            for text in [
                f"Car #{snapshot.car_number:02X}",
                f"Loc 0x{snapshot.location_bits:02X}",
                f"Misc 0x{snapshot.misc_bits:02X}",
                f"Block 0x{snapshot.primary_build_block_abs_off:05X}",
            ]:
                badge = QLabel(text)
                badge.setObjectName("garageCardStatBadge")
                badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                badge.setAlignment(Qt.AlignCenter)
                meta_row.addWidget(badge, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            status_row = QHBoxLayout()
            status_row.setSpacing(8)
            sidecar_text = (
                f"Sidecar +1 (slot {snapshot.optional_visual_sidecar.sidecar_parts_slot})"
                if snapshot.optional_visual_sidecar
                else "Primary only"
            )
            for text in [sidecar_text, self._snapshot_global_table_text(snapshot)]:
                status = QLabel(text)
                status.setObjectName("garageCardStatBadge")
                status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                status.setAlignment(Qt.AlignCenter)
                status_row.addWidget(status, 0, Qt.AlignLeft)
            status_row.addStretch(1)
            card_layout.addLayout(status_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(8)
            export_btn = QPushButton("Export Snapshot JSON")
            export_btn.setObjectName("partsBulkBtn")
            export_btn.clicked.connect(lambda _, abs_off=snapshot.car_abs_off: self.on_export_build_snapshot(abs_off))
            action_row.addWidget(export_btn, 0, Qt.AlignLeft)
            action_row.addStretch(1)
            card_layout.addLayout(action_row)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)

            perf_value = QLabel(self._snapshot_perf_text(snapshot))
            perf_value.setObjectName("partsCardRaw")
            perf_value.setAlignment(Qt.AlignCenter)
            perf_value.setWordWrap(True)
            card_layout.addWidget(perf_value)

            visuals_label = QLabel("Primary Visual Fields")
            visuals_label.setObjectName("garageCardFieldLabel")
            visuals_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(visuals_label)

            visual_grid = QGridLayout()
            visual_grid.setContentsMargins(0, 0, 0, 0)
            visual_grid.setHorizontalSpacing(12)
            visual_grid.setVerticalSpacing(6)
            for field_idx, (label_text, value_text) in enumerate(snapshot.primary_visual_fields):
                row = field_idx // 2
                col = (field_idx % 2) * 2
                name = QLabel(label_text)
                name.setObjectName("partsCardNote")
                value = QLabel(value_text)
                value.setObjectName("garageCardStatBadge")
                value.setAlignment(Qt.AlignCenter)
                value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                visual_grid.addWidget(name, row, col)
                visual_grid.addWidget(value, row, col + 1)
            visual_grid.setColumnStretch(0, 0)
            visual_grid.setColumnStretch(1, 1)
            visual_grid.setColumnStretch(2, 0)
            visual_grid.setColumnStretch(3, 1)
            card_layout.addLayout(visual_grid)

            if snapshot.optional_visual_sidecar is not None:
                sidecar_sep = QFrame()
                sidecar_sep.setFrameShape(QFrame.HLine)
                sidecar_sep.setObjectName("garageCardSep")
                card_layout.addWidget(sidecar_sep)

                sidecar_label = QLabel("Visual Sidecar")
                sidecar_label.setObjectName("garageCardFieldLabel")
                sidecar_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(sidecar_label)

                sidecar = snapshot.optional_visual_sidecar
                sidecar_row = QHBoxLayout()
                sidecar_row.setSpacing(8)
                for text in [
                    f"Owned 0x{sidecar.owned_record_abs_off:05X}",
                    f"Parts Slot {sidecar.sidecar_parts_slot}",
                    f"Block 0x{sidecar.sidecar_block_abs_off:05X}",
                ]:
                    badge = QLabel(text)
                    badge.setObjectName("garageCardStatBadge")
                    badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                    badge.setAlignment(Qt.AlignCenter)
                    sidecar_row.addWidget(badge, 0, Qt.AlignLeft)
                sidecar_row.addStretch(1)
                card_layout.addLayout(sidecar_row)

                sidecar_note = QLabel(
                    f"Signature clone: {sidecar.owned_record_signature_clone.hex(' ').upper()} | "
                    f"Loc 0x{sidecar.owned_record_location_bits:02X} | Misc 0x{sidecar.owned_record_misc_bits:02X}"
                )
                sidecar_note.setObjectName("partsCardNote")
                sidecar_note.setWordWrap(True)
                card_layout.addWidget(sidecar_note)

            row = idx // columns
            col = idx % columns
            self.snapshot_cards_layout.addWidget(card, row, col)
            self._snapshot_card_widgets[snapshot.car_abs_off] = card

        for col in range(columns):
            self.snapshot_cards_layout.setColumnStretch(col, 1)

    def _refresh_presets_page(self) -> None:
        self._rebuild_snapshot_library_cards()
        self._rebuild_snapshot_cards()

    def on_stage_snapshot_injection(self, snapshot_id: str, target_mode: str) -> None:
        if not self.savefile:
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        library_by_id = self._snapshot_library_by_id()
        entry = library_by_id.get(str(snapshot_id))
        if entry is None:
            QMessageBox.warning(self, "Snapshot unavailable", "Could not resolve the selected boss-car snapshot.")
            return
        plans, _, _, _ = self._current_snapshot_injection_plans(extra=(entry.snapshot_id, target_mode))
        plan = plans.get(entry.snapshot_id)
        if plan is None or plan.refusal_reason:
            reason = plan.refusal_reason if plan is not None else "Unknown injector planner failure"
            QMessageBox.warning(self, "Injector blocked", reason)
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
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        snapshot = next((item for item in self.build_snapshots if item.car_abs_off == abs_off), None)
        if snapshot is None:
            QMessageBox.warning(self, "Snapshot unavailable", "Could not resolve the requested build snapshot.")
            return
        default_name = f"boss_car_snapshot_{self._snapshot_filename_slug(snapshot.display_name)}.json"
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


