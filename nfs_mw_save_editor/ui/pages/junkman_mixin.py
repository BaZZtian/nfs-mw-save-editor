"""Token inventory page: catalog, card grid, apply flow, presets, and handlers."""
from __future__ import annotations

import json
import logging
from typing import Dict, List

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
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

from core import marker_names
from core.savefile import SaveFile
from core.tuning_limits import PERF_PART_NAMES
from ui.icon_map import cat_icon_path
from ui.pages.constants import *
from ui.widgets import ApplyConfirmDialog, TokenCard, ToastNotification

logger = logging.getLogger(__name__)


class JunkmanMixin:
    # Card-title defaults are the game's own marker-select strings
    # (core/marker_names.py) with three editor overrides: INDUCTION (4)
    # uses the game's unwired turbo wording, DECAL/PAINT (15/16) are
    # nameless in FE so the editor keeps its short names.
    _DEFAULT_NAME_OVERRIDES = {
        4: marker_names.INDUCTION_TURBO_NAME,
        15: "Decal",
        16: "Paint",
    }
    _DEFAULT_DESC_OVERRIDES = {4: marker_names.INDUCTION_TURBO_DESCRIPTION}

    @staticmethod
    def _default_token_fields(tid: int) -> tuple[str, str]:
        """(default card name, category) for a marker id.

        Categories mirror the game's 4-way grouping (see CAT_LIST).
        """
        name = (JunkmanMixin._DEFAULT_NAME_OVERRIDES.get(tid)
                or marker_names.canon_name(tid))
        category = ("Performance" if tid in PERF_IDS
                    else "Parts" if tid <= 12
                    else "Visual" if tid <= 16 else "Bonus Markers")
        return name, category

    @staticmethod
    def _token_description(tid: int) -> str | None:
        """Canonical in-game marker description (card tooltip), or None."""
        return (JunkmanMixin._DEFAULT_DESC_OVERRIDES.get(tid)
                or marker_names.canon_description(tid))

    def _normalize_catalog_defaults(self) -> bool:
        changed = False
        # 17..21 follow the engine enum ePossibleMarker: 17 GET_OUT_OF_JAIL,
        # 18 PINK_SLIP, 19 CASH, 20 ADD_IMPOUND_BOX, 21 IMPOUND_RELEASE.
        # 18/19 never appear in organic saves (pink slips and cash are applied
        # instantly at the marker-select screen, never inventoried), which is
        # how they ended up swapped in older catalogs. IDs above 21 are not
        # marker types at all (MARKER_LAST = 21): purge them from the catalog;
        # save-side leftovers are handled as invalid data (see _invalid_ids).
        real = [t for t in self.tokens if SAFE_TYPE_MIN <= t.id <= SAFE_TYPE_MAX]
        if len(real) != len(self.tokens):
            self.tokens = real
            changed = True
        # Names earlier editor versions shipped as defaults: these upgrade to
        # the current canon defaults; anything else is a user rename and is
        # left alone.
        legacy_names: Dict[int, set[str]] = {
            1: {"Brakes"}, 2: {"Engine"}, 3: {"NOS"}, 4: {"Turbo"},
            5: {"Suspension"}, 6: {"Tires"}, 7: {"Transmission"},
            8: {"Body"}, 9: {"Hood"}, 10: {"Spoiler"}, 11: {"Rims"},
            12: {"Roof"}, 13: {"Gauge"}, 14: {"Vinyl"},
            17: {"Out of Jail"},
            18: {"Unknown ID 18", "Imp. Strike?", "Money Marker", "Pink Slip Marker"},
            19: {"Imp. Release?", "PinkSlip Marker", "Cash Marker"},
            20: {"Imp. Strike", "Impound Strike Slot Add"},
            21: {"Impound Release"},
        }
        idx = {t.id: t for t in self.tokens}
        for tid in range(SAFE_TYPE_MIN, SAFE_TYPE_MAX + 1):
            name, category = self._default_token_fields(tid)
            tok = idx.get(tid)
            if tok is None:
                self.tokens.append(TokenEntry(id=tid, name=name, category=category))
                changed = True
                continue
            if tok.name != name and (tok.name in legacy_names.get(tid, set())
                                     or tok.name == f"Token #{tid}"):
                tok.name = name
                changed = True
            if tok.category != category:
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

        # An empty/missing catalog is fine: normalization below rebuilds the
        # full 21-entry default table and persists it.
        if self._normalize_catalog_defaults():
            self.save_catalog()

    def save_catalog(self):
        data = {"tokens": [{"id": t.id, "name": t.name, "category": t.category} for t in self.tokens]}
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def ensure_token_entry(self, tid: int):
        if not (SAFE_TYPE_MIN <= tid <= SAFE_TYPE_MAX):
            # Not a real marker type (engine MARKER_LAST = 21): no card.
            # Save-side leftovers are reported via _invalid_ids instead.
            return
        if any(t.id == tid for t in self.tokens):
            return
        name, category = self._default_token_fields(tid)
        self.tokens.append(TokenEntry(id=tid, name=name, category=category))
        self.tokens.sort(key=lambda t: t.id)

    def _build_junk_page(self):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 6, 0, 8)
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
            btn.setObjectName("filterButton")
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
        self.btn_q_parts = QPushButton("Unlock Parts (8-12)")
        self.btn_q_vis = QPushButton("Unlock Visual (13-16)")
        self.btn_q_all = QPushButton(f"Unlock All ({SAFE_TYPE_MIN}-{SAFE_TYPE_MAX})")
        self.btn_q_clear = QPushButton("Clear All (Want->0)")
        self.btn_q_perf.clicked.connect(lambda: self._quick_set(range(1, 8), 1))
        self.btn_q_parts.clicked.connect(lambda: self._quick_set(range(8, 13), 1))
        self.btn_q_vis.clicked.connect(lambda: self._quick_set(range(13, 17), 1))
        self.btn_q_all.clicked.connect(lambda: self._quick_set(range(SAFE_TYPE_MIN, SAFE_TYPE_MAX + 1), 1))
        self.btn_q_clear.clicked.connect(self.on_clear_all_want)
        for b in [self.btn_q_perf, self.btn_q_parts, self.btn_q_vis, self.btn_q_all, self.btn_q_clear]:
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
        self.cards_grid.setContentsMargins(8, 8, 8, FOOTER_CLEARANCE)
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
        staged_counts = self.staged_state.counts.ensure(self.have_counts)
        for tid in ids:
            staged_counts[tid] = max(0, min(val, max_val))
            self.ensure_token_entry(tid)
        self.refresh_cards()

    def _slot_capacity(self) -> int:
        if self.savefile and self.savefile.junkman:
            return self.savefile.junkman.slot_count
        return 63  # engine OwnedMarkers[63]

    def _current_max(self) -> int:
        cap = self._slot_capacity()
        if self.practical_cap10:
            return min(10, cap)
        return min(63, cap)

    def _invalid_ids(self) -> List[int]:
        """Type IDs present in the save that are not real marker types.

        The engine enum ends at 21; anything above is inert leftovers from
        the early hand-written token experiments. They get no cards - only
        the preserve/clear machinery sees them.
        """
        return sorted(
            tid for tid in self.have_counts
            if not (SAFE_TYPE_MIN <= tid <= SAFE_TYPE_MAX)
        )

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
                want = self.staged_state.counts.get_item(tok.id, self.have_counts, have)
                if want == have:
                    return False
            return True

        grid_row = 0
        grid_col = 0
        any_added = False

        for cat in CAT_LIST[1:]:  # section order = game category order, sans "All"
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
                want = self.staged_state.counts.get_item(t.id, self.have_counts, have)
                card = TokenCard(
                    token_id=t.id,
                    name=t.name,
                    have=have,
                    want=want,
                    max_val=max_val,
                    description=self._token_description(t.id),
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
        prev = self.staged_state.counts.get_item(tid, self.have_counts, have)
        self.staged_state.counts.set_item(tid, val, self.have_counts)
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
        invalid = self._invalid_ids()
        if not invalid:
            ToastNotification.show_toast(self, "No invalid token data in this save")
            return
        ids = ", ".join(str(t) for t in invalid)
        res = QMessageBox.warning(
            self, "Clear invalid tokens",
            f"This save carries token IDs that do not exist in the game\n"
            f"(engine max is {SAFE_TYPE_MAX}): {ids}\n\n"
            "They are invisible in game and only waste belt slots.\n"
            "Clear them on next Apply?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            self.clear_unknown_next = True
            self.refresh_cards()

    def on_reset_want(self):
        self.staged_state.counts.reset_to(self.have_counts)
        self.staged_state.money.reset_to(self.have_money)
        self.staged_state.profile_alias.reset_to(self.have_profile_alias)
        self.profile_alias_error = None
        self.clear_unknown_next = False
        if self.garage_detection_error:
            self.staged_state.slot_bounties.clear()
            self.staged_state.slot_heats.clear()
            self.staged_state.owned_locations.clear()
            self.staged_state.owned_career_slots.clear()
        else:
            self.staged_state.slot_bounties.reset_to(self.have_slot_bounties)
            self.staged_state.slot_heats.reset_to(self.have_slot_heats)
            self.staged_state.owned_locations.reset_to(self.have_owned_locations)
            self.staged_state.owned_career_slots.reset_to(self.have_owned_career_slots)
        if self.parts_detection_error:
            self.staged_state.parts_levels.clear()
            self.staged_state.parts_masks.clear()
        else:
            self.staged_state.parts_levels.reset_to(
                {slot: dict(levels) for slot, levels in self.have_parts_levels.items()}
            )
            self.staged_state.parts_masks.reset_to(self.have_parts_masks)
        self.staged_state.snapshot_injections.clear_all()
        self._mark_all_heavy_pages_dirty()
        self._refresh_profile_inputs()
        current_page = self._current_stack_page_name()
        if current_page == "Garage":
            self._refresh_garage_page(reason="reset_reveal")
        elif current_page == "Tuning":
            self._refresh_parts_page(reason="reset_reveal")
        elif current_page == "Builds":
            self._refresh_presets_page(reason="reset_reveal")
        self.refresh_cards()
        ToastNotification.show_toast(self, "Want reset to Have")

    def on_clear_all_want(self):
        self.staged_state.counts.reset_to({t.id: 0 for t in self.tokens})
        self.refresh_cards()

    def _build_want_full(self) -> Dict[int, int]:
        mapping: Dict[int, int] = {}
        max_val = self._current_max()
        for t in self.tokens:
            have = self.have_counts.get(t.id, 0)
            want = self.staged_state.counts.get_item(t.id, self.have_counts, have)
            mapping[t.id] = max(0, min(want, max_val))
        if not self.preserve_unknown or self.clear_unknown_next:
            for tid in self._invalid_ids():
                mapping[tid] = 0
        return mapping

    def _build_apply_summary(self, want_full: Dict[int, int]) -> Dict[str, object]:
        total = self._slot_capacity()
        used = sum(self.have_counts.values())
        needed = sum(want_full.values())
        free = max(0, total - used)
        add = max(0, needed - used)
        remove = max(0, used - needed)
        unknown_preserved = 0
        if self.preserve_unknown and not self.clear_unknown_next:
            unknown_preserved = sum(self.have_counts.get(tid, 0) for tid in self._invalid_ids())
        slot_changes = []
        transfer_changes: List[str] = []
        if not self.garage_detection_error:
            staged_slot_bounties = self._current_slot_bounties()
            for slot in self.garage_slots:
                have = self.have_slot_bounties.get(slot.career_slot, 0)
                want = staged_slot_bounties.get(slot.career_slot, have)
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
                        and entry.has_pursuit_link
                    ):
                        extra = f", frees slot {have_slot + 1}"
                    transfer_changes.append(
                        f"{entry.display_name}: {from_kind} (slot {from_slot}) -> {to_kind} (slot {to_slot}){extra}"
                    )
        have_total_bounty = sum(self.have_slot_bounties.values())
        want_total_bounty = sum(self._current_slot_bounties().values()) if not self.garage_detection_error else None
        heat_changes = 0 if self.garage_detection_error else len(self._pending_slot_heats())
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
                warn_text = f" [warning: {'; '.join(plan.warnings)}]" if plan.warnings else ""
                injection_changes.append(f"{entry.display_name}: inject to {target_mode} -> {slot_text}{warn_text}")
        money_want = self.staged_state.money.current(self.have_money)
        alias_want = self.staged_state.profile_alias.current(self.have_profile_alias)
        summary_lines = [
            f"Token slots: {total} total, {used} used, {free} free, {needed} needed, delta +{add} / -{remove}",
            f"Invalid token data preserved: {unknown_preserved}",
            f"Money: {self.have_money} -> {money_want}",
        ]
        if alias_want != self.have_profile_alias:
            summary_lines.append(f"Alias: '{self.have_profile_alias}' -> '{alias_want}'")
        if self.garage_detection_error:
            summary_lines.append(f"Garage: unavailable ({self.garage_detection_error})")
        else:
            summary_lines.append(f"Bounty / Rating: {have_total_bounty} -> {want_total_bounty}")
        summary_lines.append(f"Garage transfers: {len(transfer_changes)}")
        summary_lines.append(f"Heat changes: {heat_changes}")
        summary_lines.append(f"Tuning changes: {len(parts_changes)}")
        summary_lines.append(f"Preset injections: {len(injection_changes)}")

        profile_detail = [f"Money: {self.have_money} -> {money_want}"]
        if alias_want != self.have_profile_alias:
            profile_detail.append(f"Alias: '{self.have_profile_alias}' -> '{alias_want}'")
        detail_sections: List[tuple[str, List[str]]] = [
            ("Profile", profile_detail),
        ]
        if self.garage_detection_error:
            detail_sections[0][1].append(f"Garage unavailable: {self.garage_detection_error}")
        else:
            detail_sections[0][1].append(f"Bounty / Rating: {have_total_bounty} -> {want_total_bounty}")
            detail_sections[0][1].extend(slot_changes)
        if transfer_changes:
            detail_sections.append(("Garage transfers", transfer_changes))
        if self.parts_detection_error:
            detail_sections.append(("Tuning", [f"Unavailable: {self.parts_detection_error}"]))
        elif parts_changes:
            detail_sections.append(("Tuning", parts_changes))
        if injection_changes:
            detail_sections.append(("Preset injections", injection_changes))
        return {
            "summary_lines": summary_lines,
            "detail_sections": detail_sections,
        }

    def on_apply_changes(self):
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
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
                self, UI_TITLE_BLOCKED,
                f"Need {needed} slots, have {cap}.\nReduce Want values or clear a category.",
            )
            return
        if not self.garage_detection_error and self._staged_career_vehicle_count() <= 0:
            QMessageBox.warning(self, UI_TITLE_BLOCKED, self._career_empty_block_reason())
            return
        summary = self._build_apply_summary(want_full)
        dialog = ApplyConfirmDialog(
            self,
            summary_lines=list(summary["summary_lines"]),
            detail_sections=list(summary["detail_sections"]),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.savefile.set_junkman_counts(want_full, clamp_max=self._current_max())
            self.savefile.set_money(self.staged_state.money.current(self.have_money))
            alias_want = self.staged_state.profile_alias.current(self.have_profile_alias)
            if alias_want != self.have_profile_alias:
                self.savefile.set_profile_alias(alias_want)
            pending_transfers = []
            if not self.garage_detection_error:
                for slot_index, value in self._current_slot_bounties().items():
                    self.savefile.set_slot_bounty(slot_index, value)
                for slot_index, level in self._pending_slot_heats().items():
                    self.savefile.set_slot_heat(slot_index, float(level))
                current_locations = self._current_owned_locations()
                current_career_slots = self._current_owned_career_slots()
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
            if self.staged_state.snapshot_injections.has_pending():
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
            if not self.garage_detection_error and (
                pending_transfers or self.staged_state.snapshot_injections.has_pending()
            ):
                self.savefile.ensure_active_career_pointer_valid()
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
            QMessageBox.critical(self, UI_TITLE_APPLY_FAILED, str(e))

    def on_load_preset(self):
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
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
            self.staged_state.counts.ensure(self.have_counts).update(counts)
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
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", str(Path.home() / "junkman_preset.json"), "JSON (*.json)"
        )
        if not path:
            return
        payload = {"counts": self.staged_state.counts.current(self.have_counts)}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ToastNotification.show_toast(self, "Preset saved")

    def on_export_have(self):
        if not self.savefile:
            QMessageBox.warning(self, UI_TITLE_UNAVAILABLE, "Open a save first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Have", str(Path.home() / "junkman_have.json"), "JSON (*.json)"
        )
        if not path:
            return
        payload = {"counts": self.have_counts}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ToastNotification.show_toast(self, "Have exported")
