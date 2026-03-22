"""Junkman inventory page: catalog, card grid, apply, presets, junkman handlers."""
from __future__ import annotations

import json
import logging
from typing import Dict, List

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGraphicsOpacityEffect,
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
from core.tuning_limits import PERF_PART_NAMES
from ui.icon_map import cat_icon_path
from ui.pages.constants import *
from ui.widgets import TokenCard, ToastNotification

logger = logging.getLogger(__name__)


class JunkmanMixin:
    def _normalize_catalog_defaults(self) -> bool:
        changed = False
        expected: Dict[int, tuple[str, str]] = {
            17: ("Out of Jail", "Police"),
            18: ("Money Marker", "Police"),
            19: ("PinkSlip Marker", "Police"),
            20: ("Impound Strike Slot Add", "Police"),
            21: ("Impound Release", "Police"),
            22: ("Unknown ID 22 (valid)", "Unknown"),
        }
        legacy_names: Dict[int, set[str]] = {
            18: {"Unknown ID 18", "Imp. Strike?"},
            19: {"Imp. Release?"},
            20: {"Imp. Strike"},
        }
        idx = {t.id: t for t in self.tokens}
        for tid, (name, category) in expected.items():
            tok = idx.get(tid)
            if tok is None:
                self.tokens.append(TokenEntry(id=tid, name=name, category=category))
                changed = True
                continue
            if tok.name in legacy_names.get(tid, set()):
                tok.name = name
                changed = True
            if tok.category == "Unknown" and category == "Police":
                tok.category = category
                changed = True
        if changed:
            self.tokens.sort(key=lambda t: t.id)
        return changed

    def load_catalog(self):
        def from_list(toks):
            return [
                TokenEntry(
                    id=int(t.get("id")),
                    name=t.get("name", f"Token #{t.get('id')}"),
                    category=t.get("category", "Unknown"),
                )
                for t in toks if "id" in t
            ]

        def from_dict(obj):
            out = []
            for k, v in obj.items():
                try:
                    tid = int(k)
                except (ValueError, TypeError):
                    continue
                if not isinstance(v, dict):
                    v = {}
                out.append(TokenEntry(
                    id=tid,
                    name=v.get("name", f"Token #{tid}"),
                    category=v.get("category", "Unknown"),
                ))
            return out

        self.tokens = []
        if self.catalog_path.exists():
            try:
                raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "tokens" in raw and isinstance(raw["tokens"], list):
                    self.tokens = from_list(raw["tokens"])
                elif isinstance(raw, dict):
                    self.tokens = from_dict(raw)
            except Exception:
                logger.warning("Failed to load token catalog from %s", self.catalog_path, exc_info=True)
                self.tokens = []

        if not self.tokens:
            defaults = [
                (1, "Brakes", "Performance"), (2, "Engine", "Performance"),
                (3, "NOS", "Performance"), (4, "Turbo", "Performance"),
                (5, "Suspension", "Performance"), (6, "Tires", "Performance"),
                (7, "Transmission", "Performance"), (8, "Body", "Visual"),
                (9, "Hood", "Visual"), (10, "Spoiler", "Visual"),
                (11, "Rims", "Visual"), (12, "Roof", "Visual"),
                (13, "Gauge", "Visual"), (14, "Vinyl", "Visual"),
                (15, "Decal", "Visual"), (16, "Paint", "Visual"),
                (17, "Out of Jail", "Police"), (18, "Money Marker", "Police"),
                (19, "PinkSlip Marker", "Police"), (20, "Impound Strike Slot Add", "Police"),
                (21, "Impound Release", "Police"), (22, "Unknown ID 22 (valid)", "Unknown"),
            ]
            self.tokens = [TokenEntry(id=i, name=n, category=c) for i, n, c in defaults]
            self.save_catalog()
        if self._normalize_catalog_defaults():
            self.save_catalog()

    def save_catalog(self):
        data = {"tokens": [{"id": t.id, "name": t.name, "category": t.category} for t in self.tokens]}
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def ensure_token_entry(self, tid: int):
        if any(t.id == tid for t in self.tokens):
            return
        self.tokens.append(TokenEntry(id=tid, name=f"Token #{tid}", category="Unknown"))
        self.tokens.sort(key=lambda t: t.id)

    def _build_junk_page(self):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setSpacing(12)

    # -- left panel (filters, quick actions) ------------------------------
        left = QVBoxLayout()
        left.setSpacing(8)
        left.setAlignment(Qt.AlignTop)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tokens...")
        self.search.textChanged.connect(self.refresh_cards)
        left.addWidget(self.search)

        self.chk_show_changed = QCheckBox("Show only changed")
        self.chk_show_changed.stateChanged.connect(self.on_toggle_show_changed)
        left.addWidget(self.chk_show_changed)

        # category filter
        cat_box = QVBoxLayout()
        cat_box.setSpacing(4)
        self.cat_buttons: Dict[str, QPushButton] = {}
        self.cat_group = QButtonGroup(self)
        self.cat_group.setExclusive(True)
        for cat in CAT_LIST:
            btn = QPushButton(cat)
            btn.setObjectName("catButton")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(32)
            # Category icon
            c_icon = cat_icon_path(cat)
            if c_icon:
                btn.setIcon(self._tight_icon(c_icon, QSize(20, 20)))
                btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _, c=cat: self._select_category(c))
            self.cat_buttons[cat] = btn
            self.cat_group.addButton(btn)
            cat_box.addWidget(btn)
        self.cat_buttons["All"].setChecked(True)
        left.addLayout(cat_box)

        # quick actions
        left.addWidget(self._section_label("Quick actions"))
        self.btn_q_perf = QPushButton("Unlock Performance (1-7)")
        self.btn_q_vis = QPushButton("Unlock Visual (8-16)")
        self.btn_q_all = QPushButton("Unlock All (1-22)")
        self.btn_q_clear = QPushButton("Clear All (Want->0)")
        self.btn_q_perf.clicked.connect(lambda: self._quick_set(range(1, 8), 1))
        self.btn_q_vis.clicked.connect(lambda: self._quick_set(range(8, 17), 1))
        self.btn_q_all.clicked.connect(lambda: self._quick_set(range(SAFE_TYPE_MIN, SAFE_TYPE_MAX + 1), 1))
        self.btn_q_clear.clicked.connect(self.on_clear_all_want)
        for b in [self.btn_q_perf, self.btn_q_vis, self.btn_q_all, self.btn_q_clear]:
            left.addWidget(b)
        left.addStretch(1)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(220)
        layout.addWidget(left_widget, 0)

        # -- right panel: stacked widget (cards vs empty state) --
        self.right_stack = QStackedWidget()
        layout.addWidget(self.right_stack, 1)

        # Page 0: card grid inside scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("cardScroll")

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setSpacing(12)
        self.cards_grid.setContentsMargins(8, 8, 8, 8)
        self.cards_grid.setAlignment(Qt.AlignTop)

        self._cards_per_row = DEFAULT_CARDS_PER_ROW
        self.cards_container.setFixedWidth(self._card_area_width(self._cards_per_row))
        self.cards_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        self.cards_host = QWidget()
        self.cards_host_layout = QVBoxLayout(self.cards_host)
        self.cards_host_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_host_layout.setSpacing(0)
        self.cards_host_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.cards_host_layout.addWidget(self.cards_container, 0, Qt.AlignTop | Qt.AlignHCenter)

        self.scroll.setWidget(self.cards_host)
        self.right_stack.addWidget(self.scroll)           # index 0

        # Page 1: empty state (no file loaded)
        empty_page = QWidget()
        empty_page.setObjectName("emptyOverlay")
        ov_layout = QVBoxLayout(empty_page)
        ov_layout.setAlignment(Qt.AlignCenter)
        ov_layout.setSpacing(16)

        ov_icon = QLabel()
        ov_icon.setAlignment(Qt.AlignCenter)
        pix = self._brand_pixmap(64)
        if not pix.isNull():
            ov_icon.setPixmap(pix)
        ov_layout.addWidget(ov_icon)

        ov_title = QLabel("No save file loaded")
        ov_title.setObjectName("emptyTitle")
        ov_title.setAlignment(Qt.AlignCenter)
        ov_layout.addWidget(ov_title)

        ov_hint = QLabel('Click  "Open save"  to get started')
        ov_hint.setObjectName("emptyHint")
        ov_hint.setAlignment(Qt.AlignCenter)
        ov_layout.addWidget(ov_hint)

        self.right_stack.addWidget(empty_page)            # index 1
        self.right_stack.setCurrentIndex(1)                # start with empty

        # section headers & empty label
        self.section_labels: Dict[str, QLabel] = {}
        self.empty_label = QLabel("No tokens match your filter.")
        self.empty_label.setObjectName("mutedLabel")

        return w

    def _select_category(self, cat: str):
        for c, b in self.cat_buttons.items():
            b.setChecked(c == cat)
        self.refresh_cards()

    def _quick_set(self, ids, val: int):
        max_val = self._current_max()
        for tid in ids:
            self.want_counts[tid] = max(0, min(val, max_val))
            self.ensure_token_entry(tid)
        self.refresh_cards()

    def _slot_capacity(self) -> int:
        if self.savefile and self.savefile.junkman:
            return self.savefile.junkman.slot_count
        return 59

    def _current_max(self) -> int:
        cap = self._slot_capacity()
        if self.practical_cap10:
            return min(10, cap)
        return min(63, cap)

    def _unknown_ids(self) -> List[int]:
        return [t.id for t in self.tokens if t.category == "Unknown"]

    def _card_area_width(self, cols: int) -> int:
        margins = self.cards_grid.contentsMargins()
        return (
            margins.left()
            + margins.right()
            + cols * TokenCard.CARD_WIDTH
            + (cols - 1) * self.cards_grid.spacing()
        )

    def _detect_cards_per_row(self) -> int:
        if not hasattr(self, "scroll"):
            return DEFAULT_CARDS_PER_ROW
        viewport = self.scroll.viewport()
        if viewport is None:
            return getattr(self, "_cards_per_row", DEFAULT_CARDS_PER_ROW)
        available = max(320, viewport.width() - 8)
        for cols in range(MAX_CARDS_PER_ROW, 0, -1):
            if self._card_area_width(cols) <= available:
                return cols
        return 1

    def _sync_cards_per_row(self, force: bool = False) -> int:
        cols = self._detect_cards_per_row()
        current = getattr(self, "_cards_per_row", DEFAULT_CARDS_PER_ROW)
        if force or cols != current:
            self._cards_per_row = cols
            self.cards_container.setFixedWidth(self._card_area_width(cols))
        return getattr(self, "_cards_per_row", DEFAULT_CARDS_PER_ROW)

    def refresh_cards(self):
        """Rebuild the entire card grid."""
        # Clear everything from the grid
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            w = item.widget()
            if w and w is not self.empty_label:
                w.deleteLater()

        term = self.search.text().lower() if self.search else ""
        active_cat = next((c for c, b in self.cat_buttons.items() if b.isChecked()), "All")
        max_val = self._current_max()
        cards_per_row = self._sync_cards_per_row(force=True)

        def matches(tok: TokenEntry) -> bool:
            if active_cat != "All" and tok.category != active_cat:
                return False
            if term and term not in tok.name.lower() and term not in str(tok.id):
                return False
            if self.show_only_changed:
                have = self.have_counts.get(tok.id, 0)
                want = self.want_counts.get(tok.id, have)
                if want == have:
                    return False
            return True

        grid_row = 0
        grid_col = 0
        any_added = False

        for cat in ["Performance", "Visual", "Police", "Unknown"]:
            toks = [t for t in self.tokens if t.category == cat and matches(t)]
            if not toks:
                continue

            # Section header (spans full row)
            if grid_col != 0:
                grid_row += 1
                grid_col = 0

            header = self._section_label(cat)
            header.setObjectName("gridSectionLabel")
            self.cards_grid.addWidget(header, grid_row, 0, 1, cards_per_row)
            grid_row += 1
            grid_col = 0
            any_added = True

            for t in toks:
                have = self.have_counts.get(t.id, 0)
                want = self.want_counts.get(t.id, have)
                card = TokenCard(
                    token_id=t.id,
                    name=t.name,
                    have=have,
                    want=want,
                    max_val=max_val,
                    on_change=self.on_want_changed,
                    on_rename=self.on_token_renamed,
                )
                self.cards_grid.addWidget(card, grid_row, grid_col)
                self._fade_in_card(card, delay_ms=grid_col * 30)
                grid_col += 1
                if grid_col >= cards_per_row:
                    grid_col = 0
                    grid_row += 1

            # Move to next row after category
            if grid_col != 0:
                grid_row += 1
                grid_col = 0

        if not any_added:
            self.empty_label.setParent(None)
            self.cards_grid.addWidget(self.empty_label, 0, 0, 1, cards_per_row)
            self.empty_label.setVisible(True)
        else:
            self.empty_label.setVisible(False)

        self._update_free_label()
        self._update_action_states()

    def _projected_slot_usage(self) -> tuple[int, int, int]:
        """Return (used, free, cap) for current preview state (Want)."""
        cap = self._slot_capacity()
        want_full = self._build_want_full() if self.savefile else {}
        used = sum(want_full.values()) if self.savefile else sum(self.have_counts.values())
        free = cap - used
        return used, free, cap

    def _projected_perf_unlocked_count(self) -> int:
        """Return realtime unlocked coverage for performance IDs (1..7)."""
        mapping = self._build_want_full() if self.savefile else self.have_counts
        return sum(1 for tid in PERF_IDS if mapping.get(tid, 0) > 0)

    def _update_free_label(self):
        _used, free, cap = self._projected_slot_usage()
        if free < 0:
            self.lbl_free.setText(f"Free slots: 0/{cap} (over by {abs(free)})")
        else:
            self.lbl_free.setText(f"Free slots: {free}/{cap}")

        # Update progress bar — realtime performance coverage (IDs 1..7)
        perf_unlocked = self._projected_perf_unlocked_count()
        self.progress_bar.setRange(0, PERF_TOTAL)
        self.progress_bar.setValue(perf_unlocked)
        self.progress_bar.setFormat(f"{perf_unlocked}/{PERF_TOTAL} Performance")

        self._update_header_path()

    def _fade_in_card(self, card: TokenCard, delay_ms: int = 0):
        """Animate a card appearing with a quick opacity fade."""
        eff = QGraphicsOpacityEffect(card)
        eff.setOpacity(0.0)
        card.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", card)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Remove the effect after animation so scrolling doesn't glitch
        anim.finished.connect(lambda: card.setGraphicsEffect(None))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(delay_ms, anim.start)

    def on_token_renamed(self, tid: int, new_name: str):
        for t in self.tokens:
            if t.id == tid:
                t.name = new_name
                break
        self.save_catalog()
        self.refresh_cards()

    def on_want_changed(self, tid: int, val: int):
        have = self.have_counts.get(tid, 0)
        prev = self.want_counts.get(tid, have)
        self.want_counts[tid] = val
        if self.show_only_changed:
            # Rebuild only when the row should appear/disappear.
            if (prev == have) != (val == have):
                self.refresh_cards()
            else:
                self._update_free_label()
                self._update_action_states()
            return
        self._update_free_label()
        self._update_action_states()

    def on_range_toggle(self):
        if self.sender() == self.chk_safe and self.chk_safe.isChecked():
            self.chk_adv.setChecked(False)
            self.safe_mode = True
        elif self.sender() == self.chk_adv and self.chk_adv.isChecked():
            self.chk_safe.setChecked(False)
            self.safe_mode = False
        if not self.chk_safe.isChecked() and not self.chk_adv.isChecked():
            self.chk_safe.setChecked(True)
            self.safe_mode = True
        self.refresh_cards()

    def on_practical_cap_toggle(self):
        # Default mode is practical cap <=10. Checked means unlock up to <=63.
        self.practical_cap10 = not self.chk_practical_cap10.isChecked()
        self.refresh_cards()

    def on_preserve_toggle(self):
        self.preserve_unknown = self.chk_preserve_unknown.isChecked()

    def on_toggle_show_changed(self):
        self.show_only_changed = self.chk_show_changed.isChecked()
        self.refresh_cards()

    def on_clear_unknown_confirm(self):
        if not self.savefile:
            return
        res = QMessageBox.warning(
            self, "Clear Unknown",
            "This will clear all Unknown-category tokens on next Apply.\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            self.clear_unknown_next = True
            for tid in self._unknown_ids():
                self.want_counts[tid] = 0
            self.refresh_cards()

    def on_reset_want(self):
        self.want_counts = dict(self.have_counts)
        self.want_money = self.have_money
        self.want_slot_bounties = None if self.garage_detection_error else dict(self.have_slot_bounties)
        self.want_slot_flags = None if self.garage_detection_error else dict(self.have_slot_flags)
        self.want_owned_locations = None if self.garage_detection_error else dict(self.have_owned_locations)
        self.want_owned_career_slots = None if self.garage_detection_error else dict(self.have_owned_career_slots)
        self.want_cleared_pursuit_slots = None if self.garage_detection_error else set()
        self.want_parts_levels = None if self.parts_detection_error else {
            slot: dict(levels) for slot, levels in self.have_parts_levels.items()
        }
        self.want_parts_masks = None if self.parts_detection_error else dict(self.have_parts_masks)
        self.want_snapshot_injections = {}
        self._refresh_profile_inputs()
        self._refresh_garage_page()
        self._refresh_parts_page()
        self._refresh_presets_page()
        self.refresh_cards()

    def on_clear_all_want(self):
        self.want_counts = {t.id: 0 for t in self.tokens}
        self.refresh_cards()

    def _build_want_full(self) -> Dict[int, int]:
        mapping: Dict[int, int] = {}
        max_val = self._current_max()
        for t in self.tokens:
            want = self.want_counts.get(t.id, self.have_counts.get(t.id, 0))
            mapping[t.id] = max(0, min(want, max_val))
        if not self.preserve_unknown or self.clear_unknown_next:
            for tid in self._unknown_ids():
                mapping[tid] = 0
        return mapping

    def _summary_text(self, want_full: Dict[int, int]) -> str:
        total = self._slot_capacity()
        used = sum(self.have_counts.values())
        needed = sum(want_full.values())
        free = max(0, total - used)
        add = max(0, needed - used)
        remove = max(0, used - needed)
        unknown_preserved = 0
        if self.preserve_unknown and not self.clear_unknown_next:
            unknown_preserved = sum(want_full.get(tid, 0) for tid in self._unknown_ids())
        slot_changes = []
        transfer_changes: List[str] = []
        if not self.garage_detection_error:
            want_slot_bounties = self._current_slot_bounties()
            for slot in self.garage_slots:
                have = self.have_slot_bounties.get(slot.career_slot, 0)
                want = want_slot_bounties.get(slot.career_slot, have)
                if want != have:
                    slot_changes.append(f"Slot {slot.career_slot + 1} - {slot.display_name}: {have} -> {want}")
            current_locations = self._current_owned_locations()
            current_career_slots = self._current_owned_career_slots()
            for entry in self.garage_transfer_entries:
                have_loc = self.have_owned_locations.get(entry.abs_off, entry.location_bits)
                want_loc = current_locations.get(entry.abs_off, have_loc)
                have_slot = self.have_owned_career_slots.get(entry.abs_off, entry.career_slot)
                want_slot = current_career_slots.get(entry.abs_off, have_slot)
                if int(have_loc) != int(want_loc) or int(have_slot) != int(want_slot):
                    from_kind = SaveFile.derive_source_kind(have_loc)
                    to_kind = SaveFile.derive_source_kind(want_loc)
                    from_slot = "-" if have_slot == SaveFile.EMPTY_CAREER_SLOT else str(have_slot + 1)
                    to_slot = "-" if want_slot == SaveFile.EMPTY_CAREER_SLOT else str(want_slot + 1)
                    extra = ""
                    if (
                        int(want_loc) == SaveFile.MY_CARS_FLAG
                        and have_slot != SaveFile.EMPTY_CAREER_SLOT
                    ):
                        extra = f", frees slot {have_slot + 1}"
                    transfer_changes.append(
                        f"{entry.display_name}: {from_kind} (slot {from_slot}) -> {to_kind} (slot {to_slot}){extra}"
                    )
        have_total_bounty = sum(self.have_slot_bounties.values())
        want_total_bounty = sum(self._current_slot_bounties().values()) if not self.garage_detection_error else None
        parts_changes: List[str] = []
        injection_changes: List[str] = []
        if not self.parts_detection_error:
            current_levels = self._current_parts_levels()
            current_masks = self._current_parts_masks()
            part_targets: Dict[int, tuple[str, str]] = {}
            for entry in self.parts_entries:
                part_targets.setdefault(entry.parts_slot, (entry.display_name, f"Slot {entry.career_slot + 1}"))
            for entry in self.my_cars_entries:
                part_targets.setdefault(entry.parts_slot, (entry.resolved_model_name, f"My Car #{entry.car_number:02X}"))
            for parts_slot, (display_name, label) in part_targets.items():
                deltas: List[str] = []
                have_levels = self.have_parts_levels.get(parts_slot, {})
                want_levels = current_levels.get(parts_slot, have_levels)
                for name in PERF_PART_NAMES:
                    have = int(have_levels.get(name, 0))
                    want = int(want_levels.get(name, have))
                    if want != have:
                        deltas.append(f"{name} {have}->{want}")
                have_mask = int(self.have_parts_masks.get(parts_slot, 0))
                want_mask = int(current_masks.get(parts_slot, have_mask))
                if want_mask != have_mask:
                    deltas.append(f"Junkman 0x{have_mask:02X}->0x{want_mask:02X}")
                if deltas:
                    parts_changes.append(f"{label} - {display_name}: " + ", ".join(deltas))
        if self.savefile:
            plans, _, _, _ = self._current_snapshot_injection_plans()
            library_by_id = self._snapshot_library_by_id()
            for snapshot_id, target_mode in self._ordered_snapshot_injection_items():
                entry = library_by_id.get(snapshot_id)
                plan = plans.get(snapshot_id)
                if entry is None or plan is None:
                    continue
                if plan.refusal_reason:
                    injection_changes.append(f"{entry.display_name}: blocked ({plan.refusal_reason})")
                    continue
                slot_text = f"owned 0x{plan.target_owned_abs_off:05X}, parts {plan.target_parts_slot}"
                if plan.target_career_slot is not None:
                    slot_text += f", career {plan.target_career_slot + 1}"
                warn_text = " [0x5577 ignored]" if plan.warnings else ""
                injection_changes.append(f"{entry.display_name}: inject to {target_mode} -> {slot_text}{warn_text}")
        summary = (
            f"Total slots: {total}\n"
            f"Used (have): {used}\n"
            f"Free: {free}\n"
            f"Need (want): {needed}\n"
            f"Delta: +{add} / -{remove}\n"
            f"Unknown preserved: {unknown_preserved}"
        )
        summary += f"\n\nProfile changes:\nMoney: {self.have_money} -> {self.want_money if self.want_money is not None else self.have_money}"
        if self.garage_detection_error:
            summary += f"\nGarage: unavailable ({self.garage_detection_error})"
        else:
            summary += f"\nTotal Bounty / Rating: {have_total_bounty} -> {want_total_bounty}"
            if slot_changes:
                summary += "\n" + "\n".join(slot_changes)
            if transfer_changes:
                summary += "\n\nTransfer changes:\n" + "\n".join(transfer_changes)
        if self.parts_detection_error:
            summary += f"\n\nParts: unavailable ({self.parts_detection_error})"
        elif parts_changes:
            summary += "\n\nParts changes:\n" + "\n".join(parts_changes)
        if injection_changes:
            summary += "\n\nSnapshot injections:\n" + "\n".join(injection_changes)
        return summary

    def on_apply_changes(self):
        if not self.savefile:
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        want_full = self._build_want_full()
        unsafe_added = sorted(
            tid for tid, qty in want_full.items()
            if qty > self.have_counts.get(tid, 0) and not (SAFE_TYPE_MIN <= tid <= SAFE_TYPE_MAX)
        )
        if unsafe_added:
            ids = ", ".join(str(t) for t in unsafe_added)
            res = QMessageBox.warning(
                self, "Unsafe Type_ID",
                f"Type_ID(s) outside safe range {SAFE_TYPE_MIN}-{SAFE_TYPE_MAX}: {ids}\n"
                "These values may crash the game. Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return
        needed = sum(want_full.values())
        cap = self._slot_capacity()
        if needed > cap:
            QMessageBox.warning(
                self, "Not enough slots",
                f"Need {needed} slots, have {cap}.\nReduce Want values or clear a category.",
            )
            return
        summary = self._summary_text(want_full)
        res = QMessageBox.question(
            self, "Apply changes?",
            summary + "\n\nApply changes to loaded save (memory only)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        try:
            self.savefile.set_junkman_counts(want_full, clamp_max=self._current_max())
            self.savefile.set_money(self.want_money if self.want_money is not None else self.have_money)
            if not self.garage_detection_error:
                for slot_index, value in self._current_slot_bounties().items():
                    self.savefile.set_slot_bounty(slot_index, value)
                current_locations = self._current_owned_locations()
                current_career_slots = self._current_owned_career_slots()
                pending_transfers = []
                for entry in self.garage_transfer_entries:
                    have_loc = self.have_owned_locations.get(entry.abs_off, entry.location_bits)
                    want_loc = current_locations.get(entry.abs_off, have_loc)
                    have_slot = self.have_owned_career_slots.get(entry.abs_off, entry.career_slot)
                    want_slot = current_career_slots.get(entry.abs_off, have_slot)
                    if int(have_loc) == int(want_loc) and int(have_slot) == int(want_slot):
                        continue
                    if want_loc == SaveFile.MY_CARS_FLAG or want_slot == SaveFile.EMPTY_CAREER_SLOT:
                        target_mode = "my_cars"
                        desired_slot = None
                    elif want_loc == SaveFile.CAREER_FLAG:
                        target_mode = "career"
                        desired_slot = int(want_slot)
                    elif want_loc == (SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG):
                        target_mode = "pink_slip"
                        desired_slot = int(want_slot)
                    else:
                        raise ValueError(f"Unsupported staged transfer target 0x{int(want_loc):02X} for {entry.display_name}")
                    pending_transfers.append((target_mode, entry.abs_off, desired_slot))
                pending_transfers.sort(key=lambda item: 0 if item[0] == "my_cars" else 1)
                for target_mode, abs_off, desired_slot in pending_transfers:
                    self.savefile.transfer_owned_car(abs_off, target_mode, desired_career_slot=desired_slot)
            if self.want_snapshot_injections:
                plans, _, _, _ = self._current_snapshot_injection_plans()
                library_by_id = self._snapshot_library_by_id()
                for snapshot_id, target_mode in self._ordered_snapshot_injection_items():
                    entry = library_by_id.get(snapshot_id)
                    plan = plans.get(snapshot_id)
                    if entry is None:
                        raise ValueError("Could not resolve a staged snapshot library entry during apply")
                    if plan is None or plan.refusal_reason:
                        raise ValueError(plan.refusal_reason if plan is not None else f"Injector plan missing for {entry.display_name}")
                    self.savefile.inject_snapshot(
                        entry,
                        target_mode,
                        desired_career_slot=plan.target_career_slot,
                    )
            if not self.parts_detection_error:
                current_levels = self._current_parts_levels()
                current_masks = self._current_parts_masks()
                target_entries: Dict[int, object] = {}
                for entry in self.parts_entries:
                    target_entries.setdefault(entry.parts_slot, entry)
                for entry in self.my_cars_entries:
                    target_entries.setdefault(entry.parts_slot, entry)
                for parts_slot, entry in target_entries.items():
                    have_levels = self.have_parts_levels.get(parts_slot, {})
                    levels = current_levels.get(parts_slot, self.have_parts_levels.get(parts_slot, {}))
                    if any(int(levels.get(name, 0)) != int(have_levels.get(name, 0)) for name in PERF_PART_NAMES):
                        for name in PERF_PART_NAMES:
                            self.savefile.set_part_level_for_parts_slot(
                                parts_slot,
                                name,
                                int(levels.get(name, 0)),
                                model_name=self._entry_model_name(entry),
                            )
                    current_mask = int(current_masks.get(parts_slot, self.have_parts_masks.get(parts_slot, 0)))
                    have_mask = int(self.have_parts_masks.get(parts_slot, 0))
                    if current_mask != have_mask:
                        self.savefile.set_junkman_mask_for_parts_slot(
                            parts_slot,
                            current_mask,
                        )
            self._reset_want_edit_state()
            self.clear_unknown_next = False
            self.refresh_state()
            ToastNotification.show_toast(self, "Changes applied in memory")
        except Exception as e:
            QMessageBox.critical(self, "Apply failed", str(e))

    def on_load_preset(self):
        if not self.savefile:
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load preset", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            obj = json.loads(Path(path).read_text(encoding="utf-8"))
            counts_obj = obj.get("counts", obj)
            counts: Dict[int, int] = {}
            rejected: List[int] = []
            for k, v in counts_obj.items():
                tid = int(k)
                qty = int(v)
                if qty < 0:
                    continue
                if tid < SAFE_TYPE_MIN or tid > SAFE_TYPE_MAX:
                    rejected.append(tid)
                    continue
                counts[tid] = qty
            for tid in counts:
                self.ensure_token_entry(tid)
            self.want_counts.update(counts)
            self.refresh_cards()
            if rejected:
                uniq = ", ".join(str(t) for t in sorted(set(rejected)))
                QMessageBox.warning(
                    self, "Preset IDs skipped",
                    f"Skipped unsafe Type_ID(s): {uniq}\nAllowed range: {SAFE_TYPE_MIN}-{SAFE_TYPE_MAX}.",
                )
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))

    def on_save_preset(self):
        if not self.savefile:
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", str(Path.home() / "junkman_preset.json"), "JSON (*.json)"
        )
        if not path:
            return
        payload = {"counts": self.want_counts}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ToastNotification.show_toast(self, "Preset saved")

    def on_export_have(self):
        if not self.savefile:
            QMessageBox.warning(self, "No save", "Open a save first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Have", str(Path.home() / "junkman_have.json"), "JSON (*.json)"
        )
        if not path:
            return
        payload = {"counts": self.have_counts}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ToastNotification.show_toast(self, "Have exported")


