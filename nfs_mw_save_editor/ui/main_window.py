"""
NFS MW 2005 - Junkman Inventory Editor (main window)

The main window only keeps:
  - header (Open / Save / Fix + file path)
  - sidebar navigation with icons
  - QStackedWidget (pages are built here for simplicity)
  - footer (free slots, Apply, Save)
  - state coordination (refresh_state, apply, save, etc.)

Token cards are rendered as a grid of TokenCard widgets (see widgets.py).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRegularExpression, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.junkman import JunkmanInventory
from core.savefile import ResolvedGarageEntry, ResolvedPartsEntry, SaveFile
from core.tuning_limits import PERF_PART_NAMES, get_model_tuning_limits, get_tuning_limit
from resources import resource_path
from ui.icon_map import cat_icon_path, nav_icon_path
from ui.widgets import ShimmerFrame, TokenCard, ToastNotification, WantSpinBox


    # -- Constants -------------------------------------------------------
CAT_LIST = ["All", "Performance", "Visual", "Police", "Unknown"]
APP_NAME = "NFS_MW_Junkman_Editor"
CATALOG_FILENAME = "token_catalog.json"
SAFE_TYPE_MIN = 1
SAFE_TYPE_MAX = 22
PERF_IDS = (1, 2, 3, 4, 5, 6, 7)
PERF_TOTAL = 7
DEFAULT_CARDS_PER_ROW = 3
MAX_CARDS_PER_ROW = 4
U32_MAX = 0xFFFFFFFF
GARAGE_TILE_MIN_WIDTH = 230
GARAGE_TILE_MAX_COLUMNS = 3
PARTS_TILE_MIN_WIDTH = 340
PARTS_TILE_MAX_COLUMNS = 2


    # -- Helpers ---------------------------------------------------------

def _appdata_dir() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Roaming"


def _user_catalog_path() -> Path:
    return _appdata_dir() / APP_NAME / CATALOG_FILENAME


def _default_catalog_path() -> Path:
    return resource_path(CATALOG_FILENAME)


def _ensure_user_catalog_path() -> Path:
    user_path = _user_catalog_path()
    if user_path.exists():
        return user_path
    user_path.parent.mkdir(parents=True, exist_ok=True)
    default_path = _default_catalog_path()
    if default_path.exists():
        try:
            shutil.copyfile(default_path, user_path)
            return user_path
        except Exception:
            pass
    return user_path


@dataclass
class TokenEntry:
    id: int
    name: str
    category: str = "Unknown"


    # ===================================================================
#  MAIN WINDOW
    # ===================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        icon_path = resource_path("assets", "icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowTitle("NFS MW 2005 - Junkman Inventory (PC v1.3)")
        self.resize(1180, 720)

    #  state
        self.savefile: Optional[SaveFile] = None
        self.have_counts: Dict[int, int] = {}
        self.want_counts: Dict[int, int] = {}
        self.have_money = 0
        self.want_money: Optional[int] = None
        self.garage_slots: List[ResolvedGarageEntry] = []
        self.parts_entries: List[ResolvedPartsEntry] = []
        self.have_parts_levels: Dict[int, Dict[str, int]] = {}
        self.want_parts_levels: Optional[Dict[int, Dict[str, int]]] = None
        self.have_parts_masks: Dict[int, int] = {}
        self.want_parts_masks: Optional[Dict[int, int]] = None
        self.have_slot_bounties: Dict[int, int] = {}
        self.want_slot_bounties: Optional[Dict[int, int]] = None
        self.have_slot_flags: Dict[int, int] = {}
        self.want_slot_flags: Optional[Dict[int, int]] = None
        self.garage_detection_error: Optional[str] = None
        self.parts_detection_error: Optional[str] = None
        self.show_all_garage_slots = False
        self.show_integrity_panel = False
        self.show_unlinked_pursuits = False
        self.show_parts_diagnostics = False
        self.tokens: List[TokenEntry] = []
        self.safe_mode = True
        self.practical_cap10 = True
        self.preserve_unknown = True
        self.clear_unknown_next = False
        self.show_only_changed = False
        self.garage_filter = "All"
        self.parts_filter = "All"
        self._profile_refreshing = False
        self._parts_refreshing = False
        self._garage_slot_columns = 0
        self._parts_slot_columns = 0
        self._pink_slip_badge_pixmap: Optional[QPixmap] = None

        self.catalog_path = _ensure_user_catalog_path()
        self.load_catalog()
        self._build_ui()
        self.refresh_state()

    # ================================================================
    #  CATALOG
    # ================================================================

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
                except Exception:
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

    # ================================================================
    #  BUILD UI
    # ================================================================

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        base = QVBoxLayout(root)
        base.setContentsMargins(12, 12, 12, 12)
        base.setSpacing(10)

        base.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        base.addLayout(body, 1)

        body.addLayout(self._build_nav(), 0)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self.page_junk = self._build_junk_page()
        self.page_profile = self._build_profile_page()
        self.page_garage = self._build_garage_page()
        self.page_parts = self._build_parts_page()
        self.page_presets = self._build_presets_page()
        self.page_settings = self._build_settings_page()
        self.page_about = self._build_about_page()

        for p in [self.page_junk, self.page_profile, self.page_garage, self.page_parts, self.page_presets,
                   self.page_settings, self.page_about]:
            self.stack.addWidget(p)

        self._select_page("Junkman")
        base.addLayout(self._build_footer())

        # -- Keyboard shortcuts --
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.on_open)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.on_save)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.on_reset_want)

        # -- Drag & drop --
        self.setAcceptDrops(True)

    # -- Header ----------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_open = QPushButton("Open save")
        self.btn_save_header = QPushButton("Save + backup")
        self.btn_fix = QPushButton("Fix checksums")
        self.btn_open.clicked.connect(self.on_open)
        self.btn_save_header.clicked.connect(self.on_save)
        self.btn_fix.clicked.connect(self.on_fix_checksums)

        self.lbl_file = QLabel("File: (not opened)")
        self.lbl_file.setObjectName("filePath")
        self.lbl_file.setAlignment(Qt.AlignCenter)
        self.lbl_status = QLabel("Status: -")
        self.lbl_status.setObjectName("mutedLabel")
        self.lbl_unsaved = QLabel("")
        self.lbl_unsaved.setObjectName("unsavedLabel")

        for w in [self.btn_open, self.btn_save_header, self.btn_fix]:
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.lbl_file, 1)
        row.addWidget(self.lbl_unsaved)
        row.addWidget(self.lbl_status)
        return row

    @staticmethod
    def _tight_icon(path: Path, size: QSize) -> QIcon:
        """Load icon and trim transparent paddings so visual size is consistent."""
        pix = QPixmap(str(path))
        if pix.isNull():
            return QIcon(str(path))

        img = pix.toImage().convertToFormat(QImage.Format_RGBA8888)
        w, h = img.width(), img.height()
        min_x, min_y = w, h
        max_x, max_y = -1, -1
        for y in range(h):
            for x in range(w):
                alpha = (img.pixel(x, y) >> 24) & 0xFF
                if alpha:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if max_x >= min_x and max_y >= min_y:
            pix = pix.copy(min_x, min_y, (max_x - min_x + 1), (max_y - min_y + 1))
        pix = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return QIcon(pix)

    @staticmethod
    def _brand_pixmap(size: int) -> QPixmap:
        png_path = resource_path("assets", "icon.png")
        pix = QPixmap(str(png_path))
        if pix.isNull():
            ico_path = resource_path("assets", "icon.ico")
            if ico_path.exists():
                pix = QIcon(str(ico_path)).pixmap(size, size)
        if pix.isNull():
            return QPixmap()
        return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    # -- Navigation sidebar -----------------------------------------------

    def _build_nav(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignTop)
        self.nav_buttons: Dict[str, QPushButton] = {}
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        for name in ["Junkman", "Profile", "Garage", "Parts", "Presets", "Settings", "About"]:
            btn = QPushButton(name)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setMinimumHeight(48)
            btn.setMinimumWidth(130)

            # Load nav icon
            icon_p = nav_icon_path(name)
            if icon_p and icon_p.exists():
                btn.setIcon(self._tight_icon(icon_p, QSize(28, 28)))
                btn.setIconSize(QSize(28, 28))

            btn.clicked.connect(lambda _, n=name: self._select_page(n))
            self.nav_buttons[name] = btn
            self.nav_group.addButton(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        return layout

    # -- Footer ----------------------------------------------------------

    def _build_footer(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        self.lbl_free = QLabel("Free slots: -/-")
        self.lbl_free.setObjectName("pillLabel")

        # Progress bar: unlocked tokens
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("tokenProgress")
        self.progress_bar.setRange(0, PERF_TOTAL)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("0/7 Performance")

        self.btn_reset_want = QPushButton("Reset Want=Have")
        self.btn_apply = QPushButton("Apply (memory)")
        self.btn_save_footer = QPushButton("Save + backup")
        self.btn_reset_want.clicked.connect(self.on_reset_want)
        self.btn_apply.clicked.connect(self.on_apply_changes)
        self.btn_save_footer.clicked.connect(self.on_save)
        row.addWidget(self.lbl_free)
        row.addWidget(self.progress_bar)
        row.addStretch(1)
        row.addWidget(self.btn_reset_want)
        row.addWidget(self.btn_apply)
        row.addWidget(self.btn_save_footer)
        return row

    # -- Page select -----------------------------------------------------

    def _select_page(self, name: str):
        for n, btn in self.nav_buttons.items():
            btn.setChecked(n == name)
        mapping = {
            "Junkman": self.page_junk,
            "Profile": self.page_profile,
            "Garage": self.page_garage,
            "Parts": self.page_parts,
            "Presets": self.page_presets,
            "Settings": self.page_settings,
            "About": self.page_about,
        }
        self.stack.setCurrentWidget(mapping[name])
        if name == "Junkman" and hasattr(self, "cards_container") and hasattr(self, "lbl_free"):
            self._sync_cards_per_row(force=True)
            self.refresh_cards()
        elif name == "Garage":
            self._maybe_reflow_garage_rows(force=True)
        elif name == "Parts":
            self._maybe_reflow_parts_rows(force=True)

    # ================================================================
    #  JUNKMAN PAGE  (grid of TokenCards)
    # ================================================================

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

    # -- Other pages -----------------------------------------------------

    def _build_profile_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(12)

        self._profile_number_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9, ]*"), self,
        )

        # ── Stat strip (4 tiles) ────────────────────────────────
        stat_strip = QHBoxLayout()
        stat_strip.setSpacing(10)

        self.money_edit = QLineEdit()
        self.money_edit.setPlaceholderText("0")
        self.money_edit.setValidator(self._profile_number_validator)
        self.money_edit.setAlignment(Qt.AlignCenter)
        self.money_edit.setObjectName("statTileEdit")
        self.money_edit.editingFinished.connect(self.on_money_edit_finished)
        self.money_current_label = QLabel("Current: -")
        self.money_current_label.setObjectName("statTileSub")
        self.money_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Money", self.money_edit, self.money_current_label), 1,
        )

        self.total_bounty_label = QLabel("-")
        self.total_bounty_label.setObjectName("statTileValue")
        self.total_bounty_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.total_bounty_label.setAlignment(Qt.AlignCenter)
        self.total_bounty_current_label = QLabel("Current: -")
        self.total_bounty_current_label.setObjectName("statTileSub")
        self.total_bounty_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Total Bounty", self.total_bounty_label, self.total_bounty_current_label), 1,
        )

        self.escaped_total_label = QLabel("-")
        self.escaped_total_label.setObjectName("statTileValue")
        self.escaped_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.escaped_total_label.setAlignment(Qt.AlignCenter)
        self.escaped_total_current_label = QLabel("Current: -")
        self.escaped_total_current_label.setObjectName("statTileSub")
        self.escaped_total_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Escapes", self.escaped_total_label, self.escaped_total_current_label), 1,
        )

        self.busted_total_label = QLabel("-")
        self.busted_total_label.setObjectName("statTileValue")
        self.busted_total_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.busted_total_label.setAlignment(Qt.AlignCenter)
        self.busted_total_current_label = QLabel("Current: -")
        self.busted_total_current_label.setObjectName("statTileSub")
        self.busted_total_current_label.setAlignment(Qt.AlignCenter)
        stat_strip.addWidget(
            self._build_stat_tile("Busts", self.busted_total_label, self.busted_total_current_label), 1,
        )

        layout.addLayout(stat_strip)
        hint = QLabel(
            "Money is edited here. Per-car bounty is managed on the Garage page. Build diagnostics live on Parts."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # ── Garage section header ───────────────────────────────
        garage_header = QHBoxLayout()
        garage_header.setSpacing(8)
        self.garage_section_title = QLabel("Garage")
        self.garage_section_title.setObjectName("sectionLabel")
        garage_header.addWidget(self.garage_section_title)
        garage_header.addStretch(1)
        layout.addLayout(garage_header)

        # ── Garage card grid (scrollable) ───────────────────────
        self.garage_rows = QWidget()
        self.garage_rows.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.garage_rows_layout = QGridLayout(self.garage_rows)
        self.garage_rows_layout.setContentsMargins(8, 8, 8, 8)
        self.garage_rows_layout.setHorizontalSpacing(12)
        self.garage_rows_layout.setVerticalSpacing(12)
        self.garage_rows_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.garage_rows_scroll = QScrollArea()
        self.garage_rows_scroll.setObjectName("cardScroll")
        self.garage_rows_scroll.setWidgetResizable(True)
        self.garage_rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.garage_rows_scroll.setWidget(self.garage_rows)
        layout.addWidget(self.garage_rows_scroll, 1)

        # ── Integrity (togglable) ──────────────────────────────
        self.integrity_section_label = self._section_label("Integrity")
        layout.addWidget(self.integrity_section_label)
        self.profile_info = QTextEdit()
        self.profile_info.setReadOnly(True)
        self.profile_info.setMinimumHeight(120)
        self.profile_info.setMaximumHeight(160)
        self.profile_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.profile_info)

        self.garage_slot_edits: Dict[int, QLineEdit] = {}
        self.garage_slot_current_labels: Dict[int, QLabel] = {}
        self._garage_card_widgets: Dict[int, QFrame] = {}
        self._rebuild_garage_slot_rows()
        self.garage_section_title.setVisible(False)
        self.garage_rows_scroll.setVisible(False)
        self._sync_integrity_visibility()
        return w

    def _build_garage_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

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
        for label in ["All", "Career", "Pink Slip", "Unknown"]:
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
        self.garage_card_pink_toggles: Dict[int, QCheckBox] = {}
        self._garage_card_widgets_page: Dict[int, QFrame] = {}
        self._rebuild_garage_cards()
        self._sync_garage_diagnostics_visibility()
        return w

    def _build_parts_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(10)

        hint = QLabel(
            "Read-only parts viewer. Vehicle builds are resolved from parts_slot into the confirmed 0x198-byte "
            "per-car parts block. Regular performance levels and Junkman categories shown here are save-backed."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.parts_search = QLineEdit()
        self.parts_search.setPlaceholderText("Search parts by model name...")
        self.parts_search.textChanged.connect(self.on_parts_search_changed)
        controls.addWidget(self.parts_search, 1)
        self.chk_show_parts_diagnostics = QCheckBox("Show parts diagnostics")
        self.chk_show_parts_diagnostics.setChecked(False)
        self.chk_show_parts_diagnostics.stateChanged.connect(self.on_toggle_parts_diagnostics)
        controls.addWidget(self.chk_show_parts_diagnostics, 0)
        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.parts_filter_buttons: Dict[str, QPushButton] = {}
        self.parts_filter_group = QButtonGroup(self)
        self.parts_filter_group.setExclusive(True)
        for label in ["All", "Career", "Pink Slip", "Unknown"]:
            btn = QPushButton(label)
            btn.setObjectName("catButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, source=label: self._select_parts_filter(source))
            self.parts_filter_group.addButton(btn)
            self.parts_filter_buttons[label] = btn
            filter_row.addWidget(btn)
        self.parts_filter_buttons["All"].setChecked(True)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.parts_cards = QWidget()
        self.parts_cards.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.parts_cards_layout = QGridLayout(self.parts_cards)
        self.parts_cards_layout.setContentsMargins(12, 12, 12, 12)
        self.parts_cards_layout.setHorizontalSpacing(14)
        self.parts_cards_layout.setVerticalSpacing(14)
        self.parts_cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.parts_cards_scroll = QScrollArea()
        self.parts_cards_scroll.setObjectName("cardScroll")
        self.parts_cards_scroll.setWidgetResizable(True)
        self.parts_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.parts_cards_scroll.setWidget(self.parts_cards)
        layout.addWidget(self.parts_cards_scroll, 1)

        self._parts_card_widgets: Dict[int, QFrame] = {}
        self._rebuild_parts_cards()
        return w

    def _build_presets_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Presets"))
        self.btn_load_preset = QPushButton("Load preset JSON")
        self.btn_save_preset = QPushButton("Save preset JSON")
        self.btn_export_have = QPushButton("Export Have as preset")
        self.btn_load_preset.clicked.connect(self.on_load_preset)
        self.btn_save_preset.clicked.connect(self.on_save_preset)
        self.btn_export_have.clicked.connect(self.on_export_have)
        layout.addWidget(self.btn_load_preset)
        layout.addWidget(self.btn_save_preset)
        layout.addWidget(self.btn_export_have)
        layout.addStretch(1)
        return w

    def _build_settings_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Settings"))

        self.chk_preserve_unknown = QCheckBox("Preserve Unknown (default ON)")
        self.chk_preserve_unknown.setChecked(True)
        self.chk_preserve_unknown.stateChanged.connect(self.on_preserve_toggle)

        self.chk_safe = QCheckBox("Safe max (<= 63)")
        self.chk_safe.setChecked(True)
        self.chk_safe.stateChanged.connect(self.on_range_toggle)
        self.chk_adv = QCheckBox("Advanced (<= 255)")
        self.chk_adv.setChecked(False)
        self.chk_adv.stateChanged.connect(self.on_range_toggle)

        self.chk_practical_cap10 = QCheckBox("Unlock limit (<= 63)")
        self.chk_practical_cap10.setChecked(False)
        self.chk_practical_cap10.stateChanged.connect(self.on_practical_cap_toggle)

        self.chk_show_integrity = QCheckBox("Show Integrity panel on Profile")
        self.chk_show_integrity.setChecked(False)
        self.chk_show_integrity.stateChanged.connect(self.on_toggle_show_integrity)

        self.chk_show_unlinked_pursuits = QCheckBox("Show unlinked pursuit diagnostics")
        self.chk_show_unlinked_pursuits.setChecked(False)
        self.chk_show_unlinked_pursuits.stateChanged.connect(self.on_toggle_unlinked_pursuits)

        self.btn_clear_unknown = QPushButton("Clear Unknown (danger)")
        self.btn_clear_unknown.clicked.connect(self.on_clear_unknown_confirm)

        self.lbl_limits = QLabel("Limits: -")
        self.lbl_limits.setObjectName("mutedLabel")
        self.lbl_type_safety = QLabel(
            f"Safe Type_ID range: {SAFE_TYPE_MIN}-{SAFE_TYPE_MAX}. "
            "Using IDs outside this range may crash the game."
        )
        self.lbl_type_safety.setObjectName("mutedLabel")
        self.lbl_type_safety.setWordWrap(True)

        self.lbl_catalog_path = QLabel(f"Catalog: {self.catalog_path}")
        self.lbl_catalog_path.setObjectName("mutedLabel")
        self.lbl_catalog_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_open_catalog = QPushButton("Open folder")
        self.btn_open_catalog.clicked.connect(self.on_open_catalog_folder)
        catalog_row = QHBoxLayout()
        catalog_row.addWidget(self.lbl_catalog_path, 1)
        catalog_row.addWidget(self.btn_open_catalog)

        layout.addWidget(self.chk_preserve_unknown)
        layout.addWidget(self.chk_safe)
        layout.addWidget(self.chk_adv)
        layout.addWidget(self.chk_practical_cap10)
        layout.addWidget(self.chk_show_integrity)
        layout.addWidget(self.chk_show_unlinked_pursuits)
        layout.addWidget(self.btn_clear_unknown)
        layout.addWidget(self.lbl_limits)
        layout.addWidget(self.lbl_type_safety)
        layout.addLayout(catalog_row)
        layout.addStretch(1)
        return w

    def _build_about_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 32, 32, 32)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        pix = self._brand_pixmap(80)
        if not pix.isNull():
            logo_label.setPixmap(pix)
        layout.addWidget(logo_label)

        title = QLabel("NFS MW 2005 - Junkman Inventory Editor")
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel("v1.3  ·  PC")
        ver.setObjectName("mutedLabel")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        author = QLabel("Created by sprintstate")
        author.setObjectName("mutedLabel")
        author.setAlignment(Qt.AlignCenter)
        layout.addWidget(author)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        desc = QLabel(
            "Slot array is auto-detected per save (stride 0x0C).\n"
            "Apply writes to memory; Save+backup writes to disk.\n\n"
            "Keyboard shortcuts:\n"
            "  Ctrl+O  Open save · Ctrl+S  Save+backup · Ctrl+Z  Reset Want\n\n"
            "Drag & drop .sav files directly onto the window."
        )
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_github = QPushButton("GitHub")
        btn_github.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/sprintstate/nfs-mw-save-editor"))
        )
        btn_row.addWidget(btn_github)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        return w

    # -- UI helpers ------------------------------------------------------

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    @staticmethod
    def _build_stat_tile(title: str, value_widget: QWidget, sub_label: QLabel) -> QFrame:
        tile = QFrame()
        tile.setObjectName("statTile")
        tile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        vbox = QVBoxLayout(tile)
        vbox.setContentsMargins(12, 10, 12, 10)
        vbox.setSpacing(4)
        vbox.setAlignment(Qt.AlignCenter)
        heading = QLabel(title)
        heading.setObjectName("statTileHeading")
        heading.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        heading.setAlignment(Qt.AlignCenter)
        vbox.addWidget(heading, 0, Qt.AlignCenter)
        value_widget.setMaximumWidth(160)
        vbox.addWidget(value_widget, 0, Qt.AlignCenter)
        sub_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        vbox.addWidget(sub_label, 0, Qt.AlignCenter)
        return tile

    @staticmethod
    def _format_u32(value: int) -> str:
        return str(int(value))

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                MainWindow._clear_layout(child_layout)

    def _parse_u32_text(self, raw: str) -> int:
        text = raw.replace(",", "").replace(" ", "").strip()
        if not text:
            raise ValueError("Value cannot be empty.")
        if not text.isdigit():
            raise ValueError("Only decimal digits are allowed.")
        value = int(text)
        if value > U32_MAX:
            raise ValueError(f"Value must be between 0 and {U32_MAX}.")
        return value

    @staticmethod
    def _format_current_value(value: int) -> str:
        return f"Current: {value}"

    def _visible_garage_slots(self) -> List[ResolvedGarageEntry]:
        if self.show_all_garage_slots:
            return list(self.garage_slots)
        return [slot for slot in self.garage_slots if slot.occupied]

    def _detect_garage_slot_columns(self) -> int:
        if not hasattr(self, "garage_rows_scroll"):
            return 1
        viewport = self.garage_rows_scroll.viewport()
        if viewport is None:
            return 1
        available = max(240, viewport.width() - 44)
        if available >= 1280:
            return 3
        if available >= 760:
            return 2
        return 1

    def _maybe_reflow_garage_rows(self, force: bool = False) -> None:
        if not hasattr(self, "garage_rows_scroll"):
            return
        cols = self._detect_garage_slot_columns()
        if force or cols != self._garage_slot_columns:
            self._garage_slot_columns = cols
            self._rebuild_garage_slot_rows()
            if self.savefile is not None:
                self._refresh_profile_inputs()

    def _sync_integrity_visibility(self) -> None:
        visible = bool(self.show_integrity_panel)
        if hasattr(self, "integrity_section_label"):
            self.integrity_section_label.setVisible(visible)
        if hasattr(self, "profile_info"):
            self.profile_info.setVisible(visible)

    def _rebuild_garage_slot_rows(self) -> None:
        self._clear_layout(self.garage_rows_layout)
        self.garage_slot_edits = {}
        self.garage_slot_current_labels = {}
        self._garage_card_widgets = {}
        columns = max(1, self._detect_garage_slot_columns())
        self._garage_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect car bounty data.")
            label.setObjectName("mutedLabel")
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.garage_detection_error:
            label = QLabel(f"Garage bounty editor disabled: {self.garage_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_slots = self._visible_garage_slots()
        if not visible_slots:
            if self.garage_slots:
                msg = "No occupied garage slots. Enable 'Show empty valid garage slots' in Settings."
            else:
                msg = "No valid garage slots detected."
            label = QLabel(msg)
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.garage_rows_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, slot in enumerate(visible_slots):
            card = QFrame()
            card.setObjectName("garageCard")
            card.setProperty("changed", False)
            card.setProperty("occupied", slot.occupied)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(200)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # ── Header: slot number + car name ──────────────
            slot_label = QLabel(f"Slot {slot.career_slot + 1}")
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)

            name_label = QLabel(slot.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)

            card_layout.addWidget(slot_label, 0, Qt.AlignLeft)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # ── Separator ───────────────────────────────────
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # ── Bounty editor ───────────────────────────────
            bounty_label = QLabel("Bounty")
            bounty_label.setObjectName("garageCardFieldLabel")
            bounty_label.setAlignment(Qt.AlignCenter)

            edit = QLineEdit()
            edit.setPlaceholderText("0")
            edit.setValidator(self._profile_number_validator)
            edit.setAlignment(Qt.AlignCenter)
            edit.setObjectName("garageCardEdit")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            edit.editingFinished.connect(
                lambda idx=slot.career_slot: self.on_garage_slot_edit_finished(idx),
            )

            current = QLabel("Current: -")
            current.setObjectName("garageCardCurrent")
            current.setAlignment(Qt.AlignCenter)

            self.garage_slot_edits[slot.career_slot] = edit
            self.garage_slot_current_labels[slot.career_slot] = current
            self._garage_card_widgets[slot.career_slot] = card

            card_layout.addWidget(bounty_label)
            card_layout.addWidget(edit)
            card_layout.addWidget(current)

            # ── Stats row: escaped / busted ─────────────────
            stats_row = QHBoxLayout()
            stats_row.setSpacing(8)
            stats_row.setContentsMargins(0, 4, 0, 0)

            esc_lbl = QLabel(f"Escaped  {slot.escaped}")
            esc_lbl.setObjectName("garageCardStatBadge")
            esc_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            esc_lbl.setAlignment(Qt.AlignCenter)
            bust_lbl = QLabel(f"Busted  {slot.busted}")
            bust_lbl.setObjectName("garageCardStatBadge")
            bust_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            bust_lbl.setAlignment(Qt.AlignCenter)
            stats_row.addWidget(esc_lbl, 0, Qt.AlignLeft)
            stats_row.addStretch(1)
            stats_row.addWidget(bust_lbl, 0, Qt.AlignRight)
            card_layout.addLayout(stats_row)

            row = idx // columns
            col = idx % columns
            self.garage_rows_layout.addWidget(card, row, col)

        for c in range(columns):
            self.garage_rows_layout.setColumnStretch(c, 1)

    def _current_slot_bounties(self) -> Dict[int, int]:
        want_map = self.want_slot_bounties or {}
        return {
            slot.career_slot: want_map.get(slot.career_slot, self.have_slot_bounties.get(slot.career_slot, 0))
            for slot in self.garage_slots
        }

    def _set_profile_line_edit(self, edit: QLineEdit, value: int, enabled: bool) -> None:
        edit.blockSignals(True)
        edit.setText(self._format_u32(value) if enabled else "")
        edit.setEnabled(enabled)
        edit.blockSignals(False)

    def _refresh_garage_totals(self, loaded: bool) -> None:
        if not loaded:
            self.total_bounty_label.setText("-")
            self.total_bounty_current_label.setText("Current: -")
            self.escaped_total_label.setText("-")
            self.escaped_total_current_label.setText("Current: -")
            self.busted_total_label.setText("-")
            self.busted_total_current_label.setText("Current: -")
            return

        if self.garage_detection_error:
            self.total_bounty_label.setText("Unavailable")
            self.total_bounty_current_label.setText(self.garage_detection_error)
            self.escaped_total_label.setText("Unavailable")
            self.escaped_total_current_label.setText("Current: -")
            self.busted_total_label.setText("Unavailable")
            self.busted_total_current_label.setText("Current: -")
            return

        have_total = sum(self.have_slot_bounties.values())
        current_total = sum(self._current_slot_bounties().values())
        escaped_total = sum(slot.escaped for slot in self.garage_slots)
        busted_total = sum(slot.busted for slot in self.garage_slots)

        self.total_bounty_label.setText(self._format_u32(current_total))
        self.total_bounty_current_label.setText(self._format_current_value(have_total))
        self.escaped_total_label.setText(self._format_u32(escaped_total))
        self.escaped_total_current_label.setText(self._format_current_value(escaped_total))
        self.busted_total_label.setText(self._format_u32(busted_total))
        self.busted_total_current_label.setText(self._format_current_value(busted_total))

    def _refresh_profile_inputs(self) -> None:
        loaded = self.savefile is not None
        self.chk_show_all_garage_slots.blockSignals(True)
        self.chk_show_all_garage_slots.setChecked(self.show_all_garage_slots)
        self.chk_show_all_garage_slots.setEnabled(loaded and not self.garage_detection_error and bool(self.garage_slots))
        self.chk_show_all_garage_slots.blockSignals(False)
        self.chk_show_integrity.blockSignals(True)
        self.chk_show_integrity.setChecked(self.show_integrity_panel)
        self.chk_show_integrity.blockSignals(False)
        self._sync_integrity_visibility()
        self._rebuild_garage_slot_rows()

        self._profile_refreshing = True
        try:
            money_value = self.want_money if self.want_money is not None else self.have_money
            self._set_profile_line_edit(self.money_edit, money_value, loaded)
            self.money_current_label.setText(
                self._format_current_value(self.have_money) if loaded else "Current: -"
            )
            self._refresh_garage_totals(loaded)

            want_slot_bounties = self._current_slot_bounties() if loaded else {}
            for slot in self._visible_garage_slots():
                edit = self.garage_slot_edits.get(slot.career_slot)
                current = self.garage_slot_current_labels.get(slot.career_slot)
                if edit is None or current is None:
                    continue
                have_val = self.have_slot_bounties.get(slot.career_slot, 0)
                want_val = want_slot_bounties.get(slot.career_slot, have_val)
                self._set_profile_line_edit(edit, want_val, loaded)
                current.setText(self._format_current_value(have_val))
                # Highlight card if bounty was changed
                card_w = self._garage_card_widgets.get(slot.career_slot)
                if card_w is not None:
                    changed = want_val != have_val
                    card_w.setProperty("changed", changed)
                    card_w.style().unpolish(card_w)
                    card_w.style().polish(card_w)
        finally:
            self._profile_refreshing = False

    def _commit_profile_edit(self, edit: QLineEdit, fallback: int) -> Optional[int]:
        try:
            value = self._parse_u32_text(edit.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            self._set_profile_line_edit(edit, fallback, True)
            edit.setFocus()
            edit.selectAll()
            return None

        self._set_profile_line_edit(edit, value, True)
        return value

    def _has_profile_pending_changes(self) -> bool:
        if self.savefile is None:
            return False
        if (self.want_money if self.want_money is not None else self.have_money) != self.have_money:
            return True
        if self.garage_detection_error:
            return False
        for slot in self.garage_slots:
            have = self.have_slot_bounties.get(slot.career_slot, 0)
            want = self._current_slot_bounties().get(slot.career_slot, have)
            if want != have:
                return True
        return False

    def on_money_edit_finished(self) -> None:
        if self._profile_refreshing or not self.savefile:
            return
        fallback = self.want_money if self.want_money is not None else self.have_money
        value = self._commit_profile_edit(self.money_edit, fallback)
        if value is None:
            return
        self.want_money = value
        self._update_action_states()

    def on_toggle_show_all_garage_slots(self) -> None:
        self.show_all_garage_slots = self.chk_show_all_garage_slots.isChecked()
        self._refresh_profile_inputs()

    def on_toggle_show_integrity(self) -> None:
        self.show_integrity_panel = self.chk_show_integrity.isChecked()
        self._sync_integrity_visibility()

    def on_garage_slot_edit_finished(self, slot_index: int) -> None:
        if self._profile_refreshing or not self.savefile:
            return
        if self.garage_detection_error:
            return
        edit = self.garage_slot_edits.get(slot_index)
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
        # Update card highlight
        have_val = self.have_slot_bounties.get(slot_index, 0)
        card_w = self._garage_card_widgets.get(slot_index)
        if card_w is not None:
            changed = value != have_val
            card_w.setProperty("changed", changed)
            card_w.style().unpolish(card_w)
            card_w.style().polish(card_w)
        self._refresh_garage_totals(True)
        self._update_action_states()

    def _garage_card_entries(self) -> List[ResolvedGarageEntry]:
        current_flags = self._current_slot_flags()
        entries = [
            slot for slot in self.garage_slots
            if slot.occupied and (slot.car_abs_off is not None or slot.match_count > 1)
        ]
        term = self.garage_search.text().strip().lower() if hasattr(self, "garage_search") else ""
        source = self.garage_filter
        filtered: List[ResolvedGarageEntry] = []
        for slot in entries:
            if term and term not in slot.display_name.lower():
                continue
            if source != "All":
                source_kind = self._flags_to_source_kind(current_flags.get(slot.career_slot, slot.flags))
                if source == "Unknown":
                    if not source_kind.startswith("Unknown"):
                        continue
                elif source_kind != source:
                    continue
            filtered.append(slot)
        return filtered

    def _garage_unlinked_entries(self) -> List[ResolvedGarageEntry]:
        return [
            slot for slot in self.garage_slots
            if slot.car_abs_off is None and slot.match_count == 0
        ]

    def _detect_garage_slot_columns(self) -> int:
        if not hasattr(self, "garage_cards_scroll"):
            return 1
        viewport = self.garage_cards_scroll.viewport()
        if viewport is None:
            return 1
        available = max(300, viewport.width() - 56)
        if available >= 1420:
            return 3
        if available >= 860:
            return 2
        return 1

    def _maybe_reflow_garage_rows(self, force: bool = False) -> None:
        if not hasattr(self, "garage_cards_scroll"):
            return
        cols = self._detect_garage_slot_columns()
        if force or cols != self._garage_slot_columns:
            self._garage_slot_columns = cols
            self._rebuild_garage_cards()
            if self.savefile is not None:
                self._refresh_garage_page()

    def _sync_garage_diagnostics_visibility(self) -> None:
        visible = bool(self.show_unlinked_pursuits and self.savefile is not None)
        if hasattr(self, "garage_diag_label"):
            self.garage_diag_label.setVisible(visible)
        if hasattr(self, "garage_diag_text"):
            self.garage_diag_text.setVisible(visible)

    def _current_slot_bounties(self) -> Dict[int, int]:
        want_map = self.want_slot_bounties or {}
        return {
            slot.career_slot: want_map.get(slot.career_slot, self.have_slot_bounties.get(slot.career_slot, 0))
            for slot in self.garage_slots
        }

    def _current_slot_flags(self) -> Dict[int, int]:
        return {
            slot.career_slot: self.have_slot_flags.get(slot.career_slot, slot.flags or 0)
            for slot in self.garage_slots if slot.flags is not None
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

        current_flags = self._current_slot_flags()
        for idx, slot in enumerate(visible_slots):
            card = QFrame()
            card.setObjectName("garageCard")
            card.setProperty("changed", False)
            card.setProperty("occupied", slot.occupied)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(240)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_label = QLabel(f"Slot {slot.career_slot + 1}")
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)
            source_flags = current_flags.get(slot.career_slot, slot.flags)
            source_kind = self._flags_to_source_kind(source_flags)
            source_label = self._make_garage_source_badge(source_kind)
            card.setProperty("pinkslip", source_kind == "Pink Slip")
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
            parts_text = f"Parts Slot {slot.parts_slot}" if slot.parts_slot is not None else "Parts Slot ?"
            parts_label = QLabel(parts_text)
            parts_label.setObjectName("garageCardStatBadge")
            parts_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            parts_label.setAlignment(Qt.AlignCenter)
            meta_row.addWidget(parts_label, 0, Qt.AlignLeft)
            if source_flags is not None and not self._supports_pink_slip_toggle(source_flags):
                raw_flags = QLabel(f"Flags 0x{source_flags:02X}")
                raw_flags.setObjectName("garageCardStatBadge")
                raw_flags.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                raw_flags.setAlignment(Qt.AlignCenter)
                meta_row.addWidget(raw_flags, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

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
            edit.editingFinished.connect(lambda idx=slot.career_slot: self.on_garage_slot_edit_finished(idx))

            current = QLabel("Current: -")
            current.setObjectName("garageCardCurrent")
            current.setAlignment(Qt.AlignCenter)

            self.garage_card_edits[slot.career_slot] = edit
            self.garage_card_current_labels[slot.career_slot] = current
            self._garage_card_widgets_page[slot.career_slot] = card

            card_layout.addWidget(bounty_label)
            card_layout.addWidget(edit)
            card_layout.addWidget(current)

            stats_row = QHBoxLayout()
            stats_row.setSpacing(8)
            stats_row.setContentsMargins(0, 4, 0, 0)

            esc_lbl = QLabel(f"Escaped  {slot.escaped}")
            esc_lbl.setObjectName("garageCardStatBadge")
            esc_lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            esc_lbl.setAlignment(Qt.AlignCenter)
            bust_lbl = QLabel(f"Busted  {slot.busted}")
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

        self._sync_garage_diagnostics_visibility()
        self._rebuild_garage_cards()

        if not loaded:
            if hasattr(self, "garage_diag_text"):
                self.garage_diag_text.setText("")
            return

        current_bounties = self._current_slot_bounties()
        current_flags = self._current_slot_flags()
        for slot in self._garage_card_entries():
            edit = self.garage_card_edits.get(slot.career_slot)
            current_label = self.garage_card_current_labels.get(slot.career_slot)
            if edit is not None:
                self._set_profile_line_edit(edit, current_bounties.get(slot.career_slot, slot.bounty), True)
            if current_label is not None:
                current_label.setText(self._format_current_value(self.have_slot_bounties.get(slot.career_slot, 0)))
            card_w = self._garage_card_widgets_page.get(slot.career_slot)
            if card_w is not None:
                changed = self._garage_card_changed(slot.career_slot)
                card_w.setProperty("changed", changed)
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

    def _parts_card_entries(self) -> List[ResolvedPartsEntry]:
        entries = list(self.parts_entries)
        term = self.parts_search.text().strip().lower() if hasattr(self, "parts_search") else ""
        source = self.parts_filter
        filtered: List[ResolvedPartsEntry] = []
        for entry in entries:
            if term and term not in entry.display_name.lower():
                continue
            if source != "All":
                if source == "Unknown":
                    if not entry.source_kind.startswith("Unknown"):
                        continue
                elif entry.source_kind != source:
                    continue
            filtered.append(entry)
        return filtered

    def _detect_parts_card_columns(self) -> int:
        if not hasattr(self, "parts_cards_scroll"):
            return 1
        viewport = self.parts_cards_scroll.viewport()
        if viewport is None:
            return 1
        available = max(340, viewport.width() - 56)
        if available >= 1100:
            return 2
        return 1

    def _maybe_reflow_parts_rows(self, force: bool = False) -> None:
        if not hasattr(self, "parts_cards_scroll"):
            return
        cols = self._detect_parts_card_columns()
        if force or cols != self._parts_slot_columns:
            self._parts_slot_columns = cols
            self._rebuild_parts_cards()

    @staticmethod
    def _format_parts_raw(raw: bytes) -> str:
        return raw.hex(" ").upper()

    @staticmethod
    def _make_parts_badge(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("garageCardStatBadge")
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _parts_level_dict_from_entry(self, entry: ResolvedPartsEntry) -> Dict[str, int]:
        return {
            "Tires": entry.tires,
            "Brakes": entry.brakes,
            "Suspension": entry.suspension,
            "Transmission": entry.transmission,
            "Engine": entry.engine,
            "Turbo": entry.turbo,
            "NOS": entry.nos,
        }

    def _current_parts_levels(self) -> Dict[int, Dict[str, int]]:
        want_map = self.want_parts_levels or {}
        return {
            entry.career_slot: dict(
                want_map.get(
                    entry.career_slot,
                    self.have_parts_levels.get(entry.career_slot, self._parts_level_dict_from_entry(entry)),
                )
            )
            for entry in self.parts_entries
        }

    def _current_parts_masks(self) -> Dict[int, int]:
        want_map = self.want_parts_masks or {}
        return {
            entry.career_slot: int(
                want_map.get(entry.career_slot, self.have_parts_masks.get(entry.career_slot, entry.junkman_mask))
            )
            for entry in self.parts_entries
        }

    @staticmethod
    def _parts_limits(entry: ResolvedPartsEntry) -> Optional[Dict[str, int]]:
        return get_model_tuning_limits(entry.display_name)

    def _parts_card_changed(self, career_slot: int) -> bool:
        current_levels = self._current_parts_levels().get(career_slot, {})
        have_levels = self.have_parts_levels.get(career_slot, {})
        if any(int(current_levels.get(name, 0)) != int(have_levels.get(name, 0)) for name in PERF_PART_NAMES):
            return True
        current_mask = self._current_parts_masks().get(career_slot, self.have_parts_masks.get(career_slot, 0))
        return int(current_mask) != int(self.have_parts_masks.get(career_slot, 0))

    def _has_parts_pending_changes(self) -> bool:
        if self.savefile is None or self.parts_detection_error:
            return False
        return any(self._parts_card_changed(entry.career_slot) for entry in self.parts_entries)

    def _parts_junkman_reason(self, levels: Dict[str, int], category: str) -> Optional[str]:
        if category == "Turbo" and int(levels.get("Turbo", 0)) <= 0:
            return "Requires regular Turbo > 0"
        if category == "NOS" and int(levels.get("NOS", 0)) <= 0:
            return "Requires regular NOS > 0"
        return None

    def on_parts_level_changed(self, career_slot: int, part_name: str, value: int) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        entry = next((item for item in self.parts_entries if item.career_slot == career_slot), None)
        if entry is None:
            return
        limits = self._parts_limits(entry)
        if limits is None:
            return
        cap = int(limits.get(part_name, 0))
        wanted = max(0, min(int(value), cap))
        if self.want_parts_levels is None:
            self.want_parts_levels = {slot: dict(levels) for slot, levels in self.have_parts_levels.items()}
        if self.want_parts_masks is None:
            self.want_parts_masks = dict(self.have_parts_masks)
        self.want_parts_levels.setdefault(career_slot, dict(self.have_parts_levels.get(career_slot, {})))[part_name] = wanted

        current_levels = self._current_parts_levels().get(career_slot, {})
        current_mask = self._current_parts_masks().get(career_slot, self.have_parts_masks.get(career_slot, 0))
        turbo_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "Turbo"), 0)
        nos_bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == "NOS"), 0)
        if turbo_bit and int(current_levels.get("Turbo", 0)) <= 0:
            current_mask &= ~turbo_bit
        if nos_bit and int(current_levels.get("NOS", 0)) <= 0:
            current_mask &= ~nos_bit
        self.want_parts_masks[career_slot] = current_mask

        self._update_action_states()
        self._refresh_parts_page()

    def on_parts_junkman_toggled(self, career_slot: int, category: str, checked: bool) -> None:
        if self._parts_refreshing or not self.savefile or self.parts_detection_error:
            return
        bit = next((bit for bit, name in SaveFile.JUNKMAN_MASK_BITS if name == category), None)
        if bit is None:
            return
        levels = self._current_parts_levels().get(career_slot, self.have_parts_levels.get(career_slot, {}))
        if self._parts_junkman_reason(levels, category):
            return
        if self.want_parts_masks is None:
            self.want_parts_masks = dict(self.have_parts_masks)
        current = self._current_parts_masks().get(career_slot, self.have_parts_masks.get(career_slot, 0))
        self.want_parts_masks[career_slot] = current | bit if checked else current & ~bit
        self._update_action_states()
        self._refresh_parts_page()

    def _add_parts_perf_grid(self, parent: QVBoxLayout, entry) -> None:
        """Build a 2-column grid of staged level rows for performance parts."""
        current_levels = self._current_parts_levels().get(entry.career_slot, self._parts_level_dict_from_entry(entry))
        limits = self._parts_limits(entry)
        editable = limits is not None
        perf_items = [(name, int(current_levels.get(name, 0))) for name in PERF_PART_NAMES]
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for idx, (name, level) in enumerate(perf_items):
            max_level = max(int(level), int((limits or {}).get(name, get_tuning_limit(entry.display_name, name, default=4))))
            row_w = QWidget()
            row_w.setObjectName("partsLevelRow")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            lbl = QLabel(name)
            lbl.setObjectName("partsLevelLabel")
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addWidget(lbl)

            for seg_idx in range(1, max_level + 1):
                seg = QFrame()
                seg.setObjectName("partsLevelSeg")
                if level >= seg_idx:
                    seg.setProperty("filled", str(seg_idx))
                else:
                    seg.setProperty("filled", "0")
                seg.setFixedSize(20, 8)
                row_layout.addWidget(seg)

            num = QLabel(f"{level}/{max_level}")
            num.setObjectName("partsLevelNum")
            num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(num)

            if editable:
                spin = WantSpinBox()
                spin.setObjectName("partsLevelSpin")
                spin.setRange(0, max_level)
                spin.setValue(level)
                spin.setAlignment(Qt.AlignCenter)
                spin.setButtonSymbols(WantSpinBox.PlusMinus)
                spin.valueChanged.connect(
                    lambda val, slot=entry.career_slot, part=name: self.on_parts_level_changed(slot, part, val)
                )
                row_layout.addWidget(spin)
            else:
                row_layout.addWidget(self._make_parts_badge("Read-only"))

            gr = idx // 2
            gc = idx % 2
            grid.addWidget(row_w, gr, gc)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        parent.addLayout(grid)

    def _add_parts_junkman_section(self, parent: QVBoxLayout, entry) -> None:
        """Build Junkman category pills — teal accent for active, muted for none."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        if entry.junkman_categories:
            for cat in entry.junkman_categories:
                pill = QLabel(cat)
                pill.setObjectName("partsJunkmanActive")
                pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                pill.setAlignment(Qt.AlignCenter)
                row.addWidget(pill, 0, Qt.AlignLeft)
        else:
            pill = QLabel("None")
            pill.setObjectName("partsJunkmanNone")
            pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            pill.setAlignment(Qt.AlignCenter)
            row.addWidget(pill, 0, Qt.AlignLeft)
        row.addStretch(1)
        parent.addLayout(row)

    def _add_parts_junkman_section(self, parent: QVBoxLayout, entry) -> None:
        current_levels = self._current_parts_levels().get(entry.career_slot, self._parts_level_dict_from_entry(entry))
        current_mask = self._current_parts_masks().get(
            entry.career_slot,
            self.have_parts_masks.get(entry.career_slot, entry.junkman_mask),
        )
        editable = self._parts_limits(entry) is not None
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        blocked: List[str] = []
        active_any = False
        for bit, cat in SaveFile.JUNKMAN_MASK_BITS:
            enabled = bool(current_mask & bit)
            active_any = active_any or enabled
            reason = self._parts_junkman_reason(current_levels, cat)
            if editable:
                btn = QPushButton(cat)
                btn.setCheckable(True)
                btn.setChecked(enabled)
                btn.setEnabled(reason is None)
                btn.setObjectName("partsJunkmanToggle")
                btn.setProperty("active", enabled)
                if reason:
                    btn.setToolTip(reason)
                    blocked.append(f"{cat}: {reason}")
                btn.clicked.connect(
                    lambda checked, slot=entry.career_slot, category=cat: self.on_parts_junkman_toggled(slot, category, checked)
                )
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                row.addWidget(btn, 0, Qt.AlignLeft)
            elif enabled:
                pill = QLabel(cat)
                pill.setObjectName("partsJunkmanActive")
                pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                pill.setAlignment(Qt.AlignCenter)
                row.addWidget(pill, 0, Qt.AlignLeft)
        if not active_any and not editable:
            pill = QLabel("None")
            pill.setObjectName("partsJunkmanNone")
            pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            pill.setAlignment(Qt.AlignCenter)
            row.addWidget(pill, 0, Qt.AlignLeft)
        row.addStretch(1)
        parent.addLayout(row)
        if blocked:
            note = QLabel(" / ".join(blocked))
            note.setObjectName("partsCardNote")
            note.setWordWrap(True)
            parent.addWidget(note)

    def _rebuild_parts_cards(self) -> None:
        if not hasattr(self, "parts_cards_layout"):
            return
        self._clear_layout(self.parts_cards_layout)
        self._parts_card_widgets = {}
        columns = max(1, self._detect_parts_card_columns())
        self._parts_slot_columns = columns

        if not self.savefile:
            label = QLabel("Open a save to inspect resolved parts records.")
            label.setObjectName("mutedLabel")
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        if self.parts_detection_error:
            label = QLabel(f"Parts viewer disabled: {self.parts_detection_error}")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        visible_entries = self._parts_card_entries()
        if not visible_entries:
            label = QLabel("No parts entries match the current search/filter.")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self.parts_cards_layout.addWidget(label, 0, 0, 1, columns)
            return

        for idx, entry in enumerate(visible_entries):
            card = QFrame()
            card.setObjectName("partsCard")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card.setMinimumWidth(320)
            card.setProperty("changed", self._parts_card_changed(entry.career_slot))

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)

            # ── Header: slot + source badge ─────────────────
            header_row = QHBoxLayout()
            header_row.setSpacing(8)
            slot_label = QLabel(f"Slot {entry.career_slot + 1}")
            slot_label.setObjectName("garageCardSlot")
            slot_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            slot_label.setAlignment(Qt.AlignCenter)
            source_label = self._make_garage_source_badge(entry.source_kind)
            header_row.addWidget(slot_label, 0, Qt.AlignLeft)
            header_row.addStretch(1)
            header_row.addWidget(source_label, 0, Qt.AlignRight)
            card_layout.addLayout(header_row)

            # ── Car name ────────────────────────────────────
            name_label = QLabel(entry.display_name)
            name_label.setObjectName("garageCardMeta")
            name_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            name_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(name_label, 0, Qt.AlignLeft)

            # ── Meta badges ─────────────────────────────────
            meta_row = QHBoxLayout()
            meta_row.setSpacing(8)
            parts_label = QLabel(f"Parts Slot {entry.parts_slot}")
            parts_label.setObjectName("garageCardStatBadge")
            parts_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            parts_label.setAlignment(Qt.AlignCenter)
            meta_row.addWidget(parts_label, 0, Qt.AlignLeft)

            offset_label = QLabel(f"Block 0x{entry.block_abs_off:05X}")
            offset_label.setObjectName("garageCardStatBadge")
            offset_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            offset_label.setAlignment(Qt.AlignCenter)
            meta_row.addWidget(offset_label, 0, Qt.AlignLeft)
            meta_row.addStretch(1)
            card_layout.addLayout(meta_row)

            limits = self._parts_limits(entry)
            if limits is None:
                ro_label = QLabel("Read-only: no confirmed tuning cap mapping for this model.")
                ro_label.setObjectName("partsCardNote")
                ro_label.setWordWrap(True)
                card_layout.addWidget(ro_label)

            # ── Separator ───────────────────────────────────
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("garageCardSep")
            card_layout.addWidget(sep)

            # ── Performance (level bars) ────────────────────
            perf_label = QLabel("Performance")
            perf_label.setObjectName("garageCardFieldLabel")
            perf_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(perf_label)

            self._add_parts_perf_grid(card_layout, entry)

            # ── Junkman (accent pills) ──────────────────────
            junkman_label = QLabel("Junkman")
            junkman_label.setObjectName("garageCardFieldLabel")
            junkman_label.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(junkman_label)

            self._add_parts_junkman_section(card_layout, entry)

            # ── Diagnostics (toggle-gated) ──────────────────
            if self.show_parts_diagnostics:
                diag_sep = QFrame()
                diag_sep.setFrameShape(QFrame.HLine)
                diag_sep.setObjectName("garageCardSep")
                card_layout.addWidget(diag_sep)

                diag_label = QLabel("Diagnostics")
                diag_label.setObjectName("garageCardFieldLabel")
                diag_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(diag_label)

                marker_label = self._make_parts_badge(f"Marker {self._format_parts_raw(entry.marker)}")
                card_layout.addWidget(marker_label, 0, Qt.AlignLeft)

                mask_label = self._make_parts_badge(
                    f"Mask 0x{self._current_parts_masks().get(entry.career_slot, entry.junkman_mask):02X}"
                )
                card_layout.addWidget(mask_label, 0, Qt.AlignLeft)

                raw_label = QLabel("Confirmed Slice (+0x118..+0x137)")
                raw_label.setObjectName("partsCardNote")
                raw_label.setAlignment(Qt.AlignCenter)
                card_layout.addWidget(raw_label)

                raw_value = QLabel(self._format_parts_raw(entry.confirmed_raw))
                raw_value.setObjectName("partsCardRaw")
                raw_value.setAlignment(Qt.AlignCenter)
                raw_value.setWordWrap(True)
                raw_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(raw_value)

            row = idx // columns
            col = idx % columns
            self.parts_cards_layout.addWidget(card, row, col)
            self._parts_card_widgets[entry.career_slot] = card

        for col in range(columns):
            self.parts_cards_layout.setColumnStretch(col, 1)

    def _refresh_parts_page(self) -> None:
        loaded = self.savefile is not None
        if hasattr(self, "chk_show_parts_diagnostics"):
            self.chk_show_parts_diagnostics.blockSignals(True)
            self.chk_show_parts_diagnostics.setChecked(self.show_parts_diagnostics)
            self.chk_show_parts_diagnostics.setEnabled(loaded)
            self.chk_show_parts_diagnostics.blockSignals(False)
        self._rebuild_parts_cards()

    def _refresh_profile_inputs(self) -> None:
        loaded = self.savefile is not None
        self.chk_show_integrity.blockSignals(True)
        self.chk_show_integrity.setChecked(self.show_integrity_panel)
        self.chk_show_integrity.blockSignals(False)
        self._sync_integrity_visibility()

        self._profile_refreshing = True
        try:
            money_value = self.want_money if self.want_money is not None else self.have_money
            self._set_profile_line_edit(self.money_edit, money_value, loaded)
            self.money_current_label.setText(
                self._format_current_value(self.have_money) if loaded else "Current: -"
            )
            self._refresh_garage_totals(loaded)
            self._refresh_garage_page()
        finally:
            self._profile_refreshing = False

    def _has_profile_pending_changes(self) -> bool:
        if self.savefile is None:
            return False
        current_money = self.want_money if self.want_money is not None else self.have_money
        if current_money != self.have_money:
            return True
        if self.garage_detection_error:
            return False
        for slot in self.garage_slots:
            if self._garage_card_changed(slot.career_slot):
                return True
        return False

    def on_garage_search_changed(self) -> None:
        self._refresh_garage_page()

    def _select_garage_filter(self, source: str) -> None:
        self.garage_filter = source
        for label, button in self.garage_filter_buttons.items():
            button.setChecked(label == source)
        self._refresh_garage_page()

    def on_parts_search_changed(self) -> None:
        self._refresh_parts_page()

    def _select_parts_filter(self, source: str) -> None:
        self.parts_filter = source
        for label, button in self.parts_filter_buttons.items():
            button.setChecked(label == source)
        self._refresh_parts_page()

    def on_toggle_parts_diagnostics(self) -> None:
        self.show_parts_diagnostics = self.chk_show_parts_diagnostics.isChecked()
        self._refresh_parts_page()

    def on_toggle_unlinked_pursuits(self) -> None:
        self.show_unlinked_pursuits = self.chk_show_unlinked_pursuits.isChecked()
        self._sync_garage_diagnostics_visibility()

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

    def on_garage_pink_slip_toggled(self, slot_index: int) -> None:
        if self._profile_refreshing or not self.savefile or self.garage_detection_error:
            return
        toggle = self.garage_card_pink_toggles.get(slot_index)
        if toggle is None:
            return
        have_flags = self.have_slot_flags.get(slot_index)
        if not self._supports_pink_slip_toggle(have_flags):
            return
        new_flags = have_flags | SaveFile.PINK_SLIP_FLAG if toggle.isChecked() else have_flags & ~SaveFile.PINK_SLIP_FLAG
        if self.want_slot_flags is None:
            self.want_slot_flags = dict(self.have_slot_flags)
        self.want_slot_flags[slot_index] = new_flags
        self._update_action_states()
        self._refresh_garage_page()

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

    # ================================================================
    #  STATE & RENDERING
    # ================================================================

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

    def refresh_state(self):
        loaded = self.savefile is not None

        # Toggle empty state vs cards
        self.right_stack.setCurrentIndex(0 if loaded else 1)

        for btn in [
            self.btn_save_header, self.btn_save_footer, self.btn_fix,
            self.btn_apply, self.btn_reset_want,
            self.btn_q_perf, self.btn_q_vis, self.btn_q_all, self.btn_q_clear,
            self.btn_load_preset, self.btn_save_preset, self.btn_export_have,
            self.btn_clear_unknown,
        ]:
            btn.setEnabled(loaded)

        if loaded:
            self.lbl_file.setText(f"File: {self.savefile.path}")
            integrity = self.savefile.validate_integrity()
            parts = []
            if integrity.md5_ok is True:
                parts.append("MD5 OK")
            elif integrity.md5_ok is False:
                parts.append("MD5 BAD")
            for name, ok in [("CRC1", integrity.crc_block1_ok),
                             ("CRCdata", integrity.crc_data_ok),
                             ("CRC2", integrity.crc_block2_ok)]:
                if ok:
                    parts.append(f"{name} OK")
            self.lbl_status.setText("Status: " + ", ".join(parts) if parts else "Status: -")
            self.profile_info.setText(
                f"Hash scheme: {integrity.hash_scheme}\n"
                f"File size ok: {integrity.file_size_ok} ({integrity.actual_size})\n"
                f"MD5 stored: {integrity.stored_md5.hex()}\n"
                f"MD5 computed: {(integrity.computed_md5.hex() if integrity.computed_md5 else '-')}\n"
            )
            self.have_counts = self.savefile.get_junkman_counts()
            self.have_money = self.savefile.get_money()
            self.garage_detection_error = None
            self.parts_detection_error = None
            try:
                self.garage_slots = self.savefile.get_garage_slots()
                self.have_slot_bounties = {
                    slot.career_slot: slot.bounty for slot in self.garage_slots
                }
                self.have_slot_flags = {
                    slot.career_slot: slot.flags for slot in self.garage_slots if slot.flags is not None
                }
            except Exception as exc:
                self.garage_detection_error = str(exc)
                self.garage_slots = []
                self.have_slot_bounties = {}
                self.have_slot_flags = {}
            if self.garage_detection_error:
                self.parts_entries = []
                self.parts_detection_error = self.garage_detection_error
            else:
                try:
                    self.parts_entries = self.savefile.get_resolved_parts_entries()
                except Exception as exc:
                    self.parts_entries = []
                    self.parts_detection_error = str(exc)
            if self.parts_detection_error:
                self.have_parts_levels = {}
                self.have_parts_masks = {}
                self.want_parts_levels = None
                self.want_parts_masks = None
            else:
                self.have_parts_levels = {
                    entry.career_slot: {
                        "Tires": entry.tires,
                        "Brakes": entry.brakes,
                        "Suspension": entry.suspension,
                        "Transmission": entry.transmission,
                        "Engine": entry.engine,
                        "Turbo": entry.turbo,
                        "NOS": entry.nos,
                    }
                    for entry in self.parts_entries
                }
                self.have_parts_masks = {
                    entry.career_slot: entry.junkman_mask
                    for entry in self.parts_entries
                }
            for tid in self.have_counts:
                self.ensure_token_entry(tid)
            if not self.want_counts:
                self.want_counts = dict(self.have_counts)
            if self.want_money is None:
                self.want_money = self.have_money
            if self.garage_detection_error:
                self.want_slot_bounties = None
                self.want_slot_flags = None
            elif self.want_slot_bounties is None:
                self.want_slot_bounties = dict(self.have_slot_bounties)
                self.want_slot_flags = dict(self.have_slot_flags)
            else:
                self.want_slot_bounties = {
                    slot.career_slot: self.want_slot_bounties.get(slot.career_slot, slot.bounty)
                    for slot in self.garage_slots
                }
                self.want_slot_flags = {
                    slot.career_slot: self.want_slot_flags.get(slot.career_slot, slot.flags)
                    for slot in self.garage_slots if slot.flags is not None and self.want_slot_flags is not None
                }
            if self.parts_detection_error:
                self.want_parts_levels = None
                self.want_parts_masks = None
            elif self.want_parts_levels is None:
                self.want_parts_levels = {
                    slot_index: dict(levels) for slot_index, levels in self.have_parts_levels.items()
                }
                self.want_parts_masks = dict(self.have_parts_masks)
            else:
                self.want_parts_levels = {
                    entry.career_slot: dict(self.want_parts_levels.get(entry.career_slot, self.have_parts_levels.get(entry.career_slot, {})))
                    for entry in self.parts_entries
                }
                self.want_parts_masks = {
                    entry.career_slot: (self.want_parts_masks or {}).get(
                        entry.career_slot,
                        self.have_parts_masks.get(entry.career_slot, 0),
                    )
                    for entry in self.parts_entries
                }
        else:
            self.lbl_file.setText("File: (not opened)")
            self.lbl_status.setText("Status: -")
            self.profile_info.setText("")
            self.have_counts = {}
            self.want_counts = {}
            self.have_money = 0
            self.want_money = None
            self.garage_slots = []
            self.have_slot_bounties = {}
            self.have_slot_flags = {}
            self.want_slot_bounties = None
            self.want_slot_flags = None
            self.garage_detection_error = None
            self.parts_entries = []
            self.have_parts_levels = {}
            self.want_parts_levels = None
            self.have_parts_masks = {}
            self.want_parts_masks = None
            self.parts_detection_error = None
            self.show_all_garage_slots = False

        self.lbl_limits.setText(
            f"Limits: Safe {min(63, self._slot_capacity())}, Advanced {min(255, self._slot_capacity())}"
        )
        self._refresh_profile_inputs()
        self._refresh_parts_page()
        self.refresh_cards()

    # -- Card grid rendering ---------------------------------------------

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

    # -- Status helpers --------------------------------------------------

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

    def _has_pending_changes(self) -> bool:
        for tid in set(self.want_counts.keys()) | set(self.have_counts.keys()):
            have = self.have_counts.get(tid, 0)
            want = self.want_counts.get(tid, have)
            if want != have:
                return True
        return self.clear_unknown_next or self._has_profile_pending_changes() or self._has_parts_pending_changes()

    def _update_action_states(self):
        pending = self._has_pending_changes()
        enabled = self.savefile is not None
        self.btn_apply.setEnabled(enabled and pending)
        self.btn_reset_want.setEnabled(enabled)
        self.lbl_unsaved.setText("\u25cf Unsaved changes" if pending else "")

    def _update_header_path(self):
        text = "File: (not opened)" if not self.savefile else f"{self.savefile.path}"
        fm = self.lbl_file.fontMetrics()
        available = max(120, self.lbl_file.width())
        self.lbl_file.setText(fm.elidedText(text, Qt.ElideMiddle, available))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_header_path()
        if hasattr(self, "scroll") and hasattr(self, "cards_container"):
            prev = getattr(self, "_cards_per_row", DEFAULT_CARDS_PER_ROW)
            now = self._detect_cards_per_row()
            if now != prev:
                self._cards_per_row = now
                self.cards_container.setFixedWidth(self._card_area_width(now))
                self.refresh_cards()
            else:
                self.cards_container.setFixedWidth(self._card_area_width(prev))
        self._maybe_reflow_garage_rows()
        self._maybe_reflow_parts_rows()

    # -- Drag & drop ------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.on_open(filepath=path)
        event.acceptProposedAction()

    # -- Card fade-in animation -------------------------------------

    @staticmethod
    def _fade_in_card(card: TokenCard, delay_ms: int = 0):
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

    # ================================================================
    #  EVENTS
    # ================================================================

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
        self.want_parts_levels = None if self.parts_detection_error else {
            slot: dict(levels) for slot, levels in self.have_parts_levels.items()
        }
        self.want_parts_masks = None if self.parts_detection_error else dict(self.have_parts_masks)
        self._refresh_profile_inputs()
        self._refresh_parts_page()
        self.refresh_cards()

    def on_clear_all_want(self):
        self.want_counts = {t.id: 0 for t in self.tokens}
        self.refresh_cards()

    # -- Apply -----------------------------------------------------------

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
        if not self.garage_detection_error:
            want_slot_bounties = self._current_slot_bounties()
            for slot in self.garage_slots:
                have = self.have_slot_bounties.get(slot.career_slot, 0)
                want = want_slot_bounties.get(slot.career_slot, have)
                if want != have:
                    slot_changes.append(f"Slot {slot.career_slot + 1} - {slot.display_name}: {have} -> {want}")
        have_total_bounty = sum(self.have_slot_bounties.values())
        want_total_bounty = sum(self._current_slot_bounties().values()) if not self.garage_detection_error else None
        parts_changes: List[str] = []
        if not self.parts_detection_error:
            current_levels = self._current_parts_levels()
            current_masks = self._current_parts_masks()
            for entry in self.parts_entries:
                deltas: List[str] = []
                have_levels = self.have_parts_levels.get(entry.career_slot, {})
                want_levels = current_levels.get(entry.career_slot, have_levels)
                for name in PERF_PART_NAMES:
                    have = int(have_levels.get(name, 0))
                    want = int(want_levels.get(name, have))
                    if want != have:
                        deltas.append(f"{name} {have}->{want}")
                have_mask = int(self.have_parts_masks.get(entry.career_slot, 0))
                want_mask = int(current_masks.get(entry.career_slot, have_mask))
                if want_mask != have_mask:
                    deltas.append(f"Junkman 0x{have_mask:02X}->0x{want_mask:02X}")
                if deltas:
                    parts_changes.append(
                        f"Slot {entry.career_slot + 1} - {entry.display_name}: " + ", ".join(deltas)
                    )
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
        if self.parts_detection_error:
            summary += f"\n\nParts: unavailable ({self.parts_detection_error})"
        elif parts_changes:
            summary += "\n\nParts changes:\n" + "\n".join(parts_changes)
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
            if not self.parts_detection_error:
                current_levels = self._current_parts_levels()
                current_masks = self._current_parts_masks()
                for entry in self.parts_entries:
                    levels = current_levels.get(entry.career_slot, self.have_parts_levels.get(entry.career_slot, {}))
                    for name in PERF_PART_NAMES:
                        self.savefile.set_part_level(entry.career_slot, name, int(levels.get(name, 0)))
                for entry in self.parts_entries:
                    self.savefile.set_junkman_mask(
                        entry.career_slot,
                        int(current_masks.get(entry.career_slot, self.have_parts_masks.get(entry.career_slot, 0))),
                    )
            self.want_counts = {}
            self.want_money = None
            self.want_slot_bounties = None
            self.want_parts_levels = None
            self.want_parts_masks = None
            self.clear_unknown_next = False
            self.refresh_state()
            ToastNotification.show_toast(self, "Changes applied in memory")
        except Exception as e:
            QMessageBox.critical(self, "Apply failed", str(e))

    # -- Presets ---------------------------------------------------------

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

    # -- File operations --------------------------------------------------

    def on_open_catalog_folder(self):
        folder = self.catalog_path.parent
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not opened and hasattr(os, "startfile"):
            try:
                os.startfile(folder)
            except Exception:
                pass

    def on_open(self, filepath: str | None = None):
        path = filepath
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open save", str(Path.home()), "All files (*.*)")
        if not path:
            return
        try:
            self.savefile = SaveFile.load(path)
            self.want_counts = {}
            self.want_money = None
            self.want_slot_bounties = None
            self.want_slot_flags = None
            self.want_parts_levels = None
            self.want_parts_masks = None
            self.garage_detection_error = None
            self.refresh_state()
            ToastNotification.show_toast(self, "Save loaded")
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def on_save(self):
        if not self.savefile:
            QMessageBox.warning(self, "No file", "Open a save first.")
            return
        try:
            self.savefile.save(make_backup=True)
            ToastNotification.show_toast(self, "Saved with backup")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def on_fix_checksums(self):
        if not self.savefile:
            QMessageBox.warning(self, "No file", "Open a save first.")
            return
        status = self.savefile.fix_integrity()
        ToastNotification.show_toast(self, f"Checksums fixed ({status.hash_scheme})")
        self.refresh_state()


    # ===================================================================

def build_window() -> MainWindow:
    return MainWindow()
