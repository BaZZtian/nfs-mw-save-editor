"""Career page: current progression overview + career stage transplant.

Interaction contract (agreed 2026-07-07, see AGENT_CONTEXT.md):
- Transplant is immediate-with-confirm and writes to the in-memory buffer
  only, mirroring the app's "Apply (memory) -> Save + backup" model. The
  actual disk write stays with the standard Save + backup button.
- The transplant button is disabled while any staged edit is pending, so
  staged want-values can never race the transplanted have-values.
- After a transplant the staged state is reset and the whole UI refreshes
  through the same path used after opening a file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import career_transplant
from core.career_donor_library import (
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    CareerDonorEntry,
    default_user_career_donor_root,
    load_career_donor_library,
)
from ui.pages.constants import BLACKLIST_BOSS_NAMES
from ui.widgets import ToastNotification

_STAGE_ROLE = Qt.UserRole
_KEEPS_TEXT = "Keeps: money, alias, cars, installed parts, garage stats, Junkman inventory."
_CHANGES_TEXT = (
    "Changes: career stage, milestones, race progress, story SMS, shop unlocks."
)
_BOUNTY_CAVEAT_TEXT = (
    "Note: your cars keep their earned bounty; if the target stage implies "
    "more, the difference is added as sold-cars history."
)


def _stage_title(stage: int) -> str:
    boss = BLACKLIST_BOSS_NAMES.get(stage)
    return f"#{stage}: {boss}" if boss else f"#{stage}"


def _display_name_text(text: str) -> str:
    return text.replace(" \u2014 ", ": ")


class CareerMixin:
    def _build_career_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(12)

        self.career_donor_root = default_user_career_donor_root()
        self.career_donor_library: tuple[CareerDonorEntry, ...] = ()

        # ── Read-only progression strip ────────────────────────
        strip = QHBoxLayout()
        strip.setSpacing(10)

        self.career_stage_value = QLabel("-")
        self.career_stage_value.setObjectName("statTileValue")
        self.career_stage_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.career_stage_value.setAlignment(Qt.AlignCenter)
        self.career_stage_sub = QLabel("Current blacklist stage")
        self.career_stage_sub.setObjectName("statTileSub")
        self.career_stage_sub.setAlignment(Qt.AlignCenter)
        strip.addWidget(self._build_stat_tile("Stage", self.career_stage_value, self.career_stage_sub), 1)

        self.career_races_value = QLabel("-")
        self.career_races_value.setObjectName("statTileValue")
        self.career_races_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.career_races_value.setAlignment(Qt.AlignCenter)
        self.career_races_sub = QLabel("Completed events in the race table")
        self.career_races_sub.setObjectName("statTileSub")
        self.career_races_sub.setAlignment(Qt.AlignCenter)
        strip.addWidget(self._build_stat_tile("Races done", self.career_races_value, self.career_races_sub), 1)

        layout.addLayout(strip)

        # ── Transplant card ────────────────────────────────────
        card, card_layout = self._make_card_frame(vertical_policy=QSizePolicy.Expanding)

        title = self._make_card_field_label("Career stage transplant")
        card_layout.addWidget(title)

        intro = QLabel(
            "Move your profile to another blacklist stage by transplanting the "
            "career progression from a known-good donor save. Your property is untouched."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(intro)

        variant_row = QHBoxLayout()
        variant_row.setSpacing(12)
        self.career_variant_start = QRadioButton("Chapter start")
        self.career_variant_ready = QRadioButton("Boss fight ready")
        self.career_variant_start.setObjectName("careerVariantRadio")
        self.career_variant_ready.setObjectName("careerVariantRadio")
        self.career_variant_start.setChecked(True)
        self.career_variant_start.toggled.connect(self._on_career_variant_changed)
        variant_row.addStretch(1)
        variant_row.addWidget(self.career_variant_start)
        variant_row.addWidget(self.career_variant_ready)
        variant_row.addStretch(1)
        card_layout.addLayout(variant_row)

        self.career_stage_list = QListWidget()
        self.career_stage_list.setObjectName("careerStageList")
        self.career_stage_list.setUniformItemSizes(True)
        self.career_stage_list.currentItemChanged.connect(
            lambda *_: self._refresh_career_preview()
        )
        card_layout.addWidget(self.career_stage_list, 1)

        card_layout.addWidget(self._make_card_separator())

        self.career_preview_status = QLabel("")
        self.career_preview_status.setObjectName("contentCardMeta")
        self.career_preview_status.setWordWrap(True)
        self.career_preview_status.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_status)

        self.career_preview_changes = QLabel(_CHANGES_TEXT)
        self.career_preview_changes.setObjectName("contentCardNote")
        self.career_preview_changes.setWordWrap(True)
        self.career_preview_changes.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_changes)

        self.career_preview_keeps = QLabel(_KEEPS_TEXT)
        self.career_preview_keeps.setObjectName("contentCardNote")
        self.career_preview_keeps.setWordWrap(True)
        self.career_preview_keeps.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_keeps)

        self.career_preview_caveat = QLabel(_BOUNTY_CAVEAT_TEXT)
        self.career_preview_caveat.setObjectName("contentCardNote")
        self.career_preview_caveat.setWordWrap(True)
        self.career_preview_caveat.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.career_preview_caveat)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.btn_career_transplant = self._make_card_action_button("Transplant (memory)")
        self.btn_career_transplant.clicked.connect(self._on_career_transplant_clicked)
        action_row.addWidget(self.btn_career_transplant)
        action_row.addStretch(1)
        card_layout.addLayout(action_row)

        layout.addWidget(card, 1)

        self._reload_career_donor_library()
        self._rebuild_career_stage_list()
        self._refresh_career_preview()
        return w

    # ── Library / list state ───────────────────────────────────

    def _reload_career_donor_library(self) -> None:
        try:
            self.career_donor_library = load_career_donor_library(self.career_donor_root)
        except Exception:
            self.career_donor_library = ()

    def _career_selected_variant(self) -> str:
        if self.career_variant_ready.isChecked():
            return VARIANT_BOSS_READY
        return VARIANT_CHAPTER_START

    def _career_donors_for_variant(self, variant: str) -> Dict[int, CareerDonorEntry]:
        donors: Dict[int, CareerDonorEntry] = {}
        for entry in self.career_donor_library:
            if entry.is_loadable and entry.variant == variant and entry.stage_bin not in donors:
                donors[entry.stage_bin] = entry
        return donors

    def _rebuild_career_stage_list(self) -> None:
        selected_stage = None
        current = self.career_stage_list.currentItem()
        if current is not None:
            selected_stage = current.data(_STAGE_ROLE)

        donors = self._career_donors_for_variant(self._career_selected_variant())
        self.career_stage_list.blockSignals(True)
        self.career_stage_list.clear()
        for stage in range(15, 0, -1):
            item = QListWidgetItem(_stage_title(stage))
            item.setData(_STAGE_ROLE, stage)
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(0, 36))
            if stage not in donors:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
                item.setToolTip("No donor save for this stage in the library")
            self.career_stage_list.addItem(item)
            if stage == selected_stage and stage in donors:
                self.career_stage_list.setCurrentItem(item)
        self.career_stage_list.blockSignals(False)

    def _selected_career_donor(self) -> Optional[CareerDonorEntry]:
        item = self.career_stage_list.currentItem()
        if item is None or not (item.flags() & Qt.ItemIsEnabled):
            return None
        stage = item.data(_STAGE_ROLE)
        return self._career_donors_for_variant(self._career_selected_variant()).get(stage)

    # ── Refresh / preview ──────────────────────────────────────

    def _refresh_career_page(self) -> None:
        data = bytes(self.savefile.data) if self.savefile is not None else b""
        current_bin = career_transplant.read_current_bin(data)
        if current_bin is None:
            self.career_stage_value.setText("-")
            self.career_races_value.setText("-")
        else:
            self.career_stage_value.setText(_stage_title(current_bin))
            races = career_transplant.count_completed_races(data)
            self.career_races_value.setText("-" if races is None else str(races))
        self._reload_career_donor_library()
        self._rebuild_career_stage_list()
        self._refresh_career_preview()

    def _on_career_variant_changed(self, _checked: bool = False) -> None:
        self._rebuild_career_stage_list()
        self._refresh_career_preview()

    def _career_block_reason(self) -> Optional[str]:
        if self.savefile is None:
            return "Open a save first."
        if self._has_pending_changes():
            return "Apply or Reset pending edits first."
        if self._selected_career_donor() is None:
            return "Pick a target stage with an available donor."
        return None

    def _refresh_career_preview(self) -> None:
        lines: List[str] = []
        donor = self._selected_career_donor()
        block_reason = self._career_block_reason()

        if donor is not None and self.savefile is not None:
            try:
                donor_data = Path(donor.save_path).read_bytes()
                plan = self.savefile.plan_career_transplant(donor_data)
            except Exception as exc:
                lines.append(f"Donor could not be read: {exc}")
            else:
                if plan.refusal_reason:
                    lines.append(f"Refused: {plan.refusal_reason}")
                else:
                    current = career_transplant.read_current_bin(bytes(self.savefile.data))
                    lines.append(
                        f"Ready: {_stage_title(current)} -> {_stage_title(plan.donor_bin)}"
                        f" ({_display_name_text(donor.display_name)})"
                    )
                    if current == plan.donor_bin:
                        lines.append("Same stage: this resets the chapter's progress.")
                    if plan.bounty_compensation > 0:
                        lines.append(
                            f"Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history."
                        )
                    lines.extend(f"Warning: {w}" for w in plan.warnings)
        if block_reason:
            lines.append(block_reason)

        self.career_preview_status.setText("\n".join(lines))
        self.btn_career_transplant.setEnabled(block_reason is None)

    # ── Apply ──────────────────────────────────────────────────

    def _on_career_transplant_clicked(self) -> None:
        donor = self._selected_career_donor()
        if donor is None or self.savefile is None:
            return
        try:
            donor_data = Path(donor.save_path).read_bytes()
            plan = self.savefile.plan_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Transplant failed", str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, "Transplant refused", plan.refusal_reason)
            self._refresh_career_preview()
            return

        current = career_transplant.read_current_bin(bytes(self.savefile.data))
        warning_lines = "".join(f"\n- {w}" for w in plan.warnings)
        if plan.bounty_compensation > 0:
            warning_lines += (
                f"\n- Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history"
            )
        answer = QMessageBox.question(
            self,
            "Career stage transplant",
            (
                f"Transplant career progression?\n\n"
                f"{_stage_title(current)}  ->  {_stage_title(plan.donor_bin)}\n"
                f"Donor: {_display_name_text(donor.display_name)}\n\n"
                f"{_CHANGES_TEXT}\n{_KEEPS_TEXT}\n\n"
                f"This edits memory only; use Save + backup to write the file."
                f"{warning_lines}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.savefile.apply_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Transplant failed", str(exc))
            return

        self._reset_want_edit_state()
        self.refresh_state()
        ToastNotification.show_toast(
            self, "Career stage transplanted (memory). Save + backup to write"
        )
