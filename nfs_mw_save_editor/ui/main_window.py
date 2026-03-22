"""
NFS MW 2005 - Junkman Inventory Editor (main window)

MainWindow assembles the full UI from page mixins.  Each mixin owns one
page's build/handler/refresh methods; this file keeps only:
  - shared constants (via ui.pages.constants)
  - shared module-level helpers (catalog path, icon trimming, etc.)
  - UI skeleton: header, nav sidebar, footer, page switcher
  - Core coordination: refresh_state, apply, save, file ops
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import (
    FullCarBuildSnapshot,
    GarageAllocatorSnapshot,
    ResolvedGarageEntry,
    ResolvedMyCarsEntry,
    ResolvedPartsEntry,
    ResolvedTransferCarEntry,
    SnapshotLibraryEntry,
)
from core.savefile import SaveFile
from resources import resource_path
from ui.icon_map import nav_icon_path
from ui.pages.constants import *
from ui.pages.garage_mixin import GarageMixin
from ui.pages.junkman_mixin import JunkmanMixin
from ui.pages.my_cars_mixin import MyCarsMixin
from ui.pages.parts_mixin import PartsMixin
from ui.pages.presets_mixin import PresetsMixin
from ui.pages.profile_mixin import ProfileMixin
from ui.pages.settings_mixin import SettingsMixin
from ui.widgets import ToastNotification

logger = logging.getLogger(__name__)


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
            logger.warning("Failed to copy default catalog to %s", user_path, exc_info=True)
    return user_path




# ===================================================================
#  MAIN WINDOW
# ===================================================================
class MainWindow(
    JunkmanMixin,
    ProfileMixin,
    GarageMixin,
    PartsMixin,
    MyCarsMixin,
    PresetsMixin,
    SettingsMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        icon_path = resource_path("assets", "icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowTitle("NFS MW 2005 - Junkman Inventory (PC v1.3)")

    #  state
        self.savefile: Optional[SaveFile] = None
        self.have_counts: Dict[int, int] = {}
        self.want_counts: Dict[int, int] = {}
        self.have_money = 0
        self.want_money: Optional[int] = None
        self.garage_slots: List[ResolvedGarageEntry] = []
        self.garage_transfer_entries: List[ResolvedTransferCarEntry] = []
        self.garage_allocator_snapshot: Optional[GarageAllocatorSnapshot] = None
        self.parts_entries: List[ResolvedPartsEntry] = []
        self.my_cars_entries: List[ResolvedMyCarsEntry] = []
        self.build_snapshots: List[FullCarBuildSnapshot] = []
        self.snapshot_library: List[SnapshotLibraryEntry] = []
        self.have_parts_levels: Dict[int, Dict[str, int]] = {}
        self.want_parts_levels: Optional[Dict[int, Dict[str, int]]] = None
        self.have_parts_masks: Dict[int, int] = {}
        self.want_parts_masks: Optional[Dict[int, int]] = None
        self.have_slot_bounties: Dict[int, int] = {}
        self.want_slot_bounties: Optional[Dict[int, int]] = None
        self.have_slot_flags: Dict[int, int] = {}
        self.want_slot_flags: Optional[Dict[int, int]] = None
        self.have_owned_locations: Dict[int, int] = {}
        self.want_owned_locations: Optional[Dict[int, int]] = None
        self.have_owned_career_slots: Dict[int, int] = {}
        self.want_owned_career_slots: Optional[Dict[int, int]] = None
        self.want_cleared_pursuit_slots: Optional[set[int]] = None
        self.garage_detection_error: Optional[str] = None
        self.parts_detection_error: Optional[str] = None
        self.snapshot_detection_error: Optional[str] = None
        self.snapshot_library_error: Optional[str] = None
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
        self.my_cars_filter = "All"
        self._profile_refreshing = False
        self._parts_refreshing = False
        self._garage_slot_columns = 0
        self._parts_slot_columns = 0
        self._my_cars_slot_columns = 0
        self._snapshot_slot_columns = 0
        self._library_slot_columns = 0
        self._pink_slip_badge_pixmap: Optional[QPixmap] = None
        self.snapshot_library_root = SaveFile.default_snapshot_library_root()
        self.want_snapshot_injections: Dict[str, str] = {}
        self.snapshot_library_filter = "All"

        self.catalog_path = _ensure_user_catalog_path()
        self.load_catalog()
        self._build_ui()
        self.refresh_state()

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
        self.page_my_cars = self._build_my_cars_page()
        self.page_presets = self._build_presets_page()
        self.page_settings = self._build_settings_page()
        self.page_about = self._build_about_page()

        for p in [self.page_junk, self.page_profile, self.page_garage, self.page_parts, self.page_my_cars, self.page_presets,
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

    def _tight_icon(self, path: Path, size: QSize) -> QIcon:
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

    def _brand_pixmap(self, size: int) -> QPixmap:
        png_path = resource_path("assets", "icon.png")
        pix = QPixmap(str(png_path))
        if pix.isNull():
            ico_path = resource_path("assets", "icon.ico")
            if ico_path.exists():
                pix = QIcon(str(ico_path)).pixmap(size, size)
        if pix.isNull():
            return QPixmap()
        return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _build_nav(self):
        layout = QVBoxLayout()
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignTop)
        self.nav_buttons: Dict[str, QPushButton] = {}
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        for name in ["Junkman", "Profile", "Garage", "Parts", "My Cars", "Presets", "Settings", "About"]:
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

    def _select_page(self, name: str):
        for n, btn in self.nav_buttons.items():
            btn.setChecked(n == name)
        mapping = {
            "Junkman": self.page_junk,
            "Profile": self.page_profile,
            "Garage": self.page_garage,
            "Parts": self.page_parts,
            "My Cars": self.page_my_cars,
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
        elif name == "My Cars":
            self._maybe_reflow_my_cars_rows(force=True)
        elif name == "Presets":
            self._maybe_reflow_library_rows(force=True)
            self._maybe_reflow_snapshot_rows(force=True)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _build_stat_tile(self, title: str, value_widget: QWidget, sub_label: QLabel) -> QFrame:
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

    def _format_u32(self, value: int) -> str:
        return str(int(value))

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

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

    def _format_current_value(self, value: int) -> str:
        return f"Current: {value}"

    def _detect_col_count(self, scroll_attr: str, min_width: int, thresholds: tuple) -> int:
        """Return column count based on scroll-area viewport width.

        *thresholds* is a sequence of ``(min_available, col_count)`` pairs,
        sorted descending.  Returns 1 if no threshold matches.
        """
        if not hasattr(self, scroll_attr):
            return 1
        viewport = getattr(self, scroll_attr).viewport()
        if viewport is None:
            return 1
        available = max(min_width, viewport.width() - 56)
        for threshold, cols in thresholds:
            if available >= threshold:
                return cols
        return 1

    def _maybe_reflow_cols(
        self,
        scroll_attr: str,
        col_attr: str,
        min_width: int,
        thresholds: tuple,
        rebuild_fn,
        force: bool = False,
        post_fn=None,
    ) -> None:
        """Reflow a card grid when column count changes.

        *rebuild_fn* is called when the column count changes (or *force* is
        True).  Optional *post_fn* is called after *rebuild_fn*.
        """
        if not hasattr(self, scroll_attr):
            return
        cols = self._detect_col_count(scroll_attr, min_width, thresholds)
        if force or cols != getattr(self, col_attr):
            setattr(self, col_attr, cols)
            rebuild_fn()
            if post_fn is not None:
                post_fn()

    def _reset_all_edit_state(self) -> None:
        """Clear every have_* and want_* field — used when closing / failing to load a file."""
        self.have_counts = {}
        self.want_counts = {}
        self.have_money = 0
        self.want_money = None
        self.have_slot_bounties = {}
        self.have_slot_flags = {}
        self.want_slot_bounties = None
        self.want_slot_flags = None
        self.have_owned_locations = {}
        self.want_owned_locations = None
        self.have_owned_career_slots = {}
        self.want_owned_career_slots = None
        self.want_cleared_pursuit_slots = None
        self.have_parts_levels = {}
        self.want_parts_levels = None
        self.have_parts_masks = {}
        self.want_parts_masks = None
        self.want_snapshot_injections = {}

    def _reset_want_edit_state(self) -> None:
        """Clear all want_* fields back to None / {} — used after Apply or open-file."""
        self.want_counts = {}
        self.want_money = None
        self.want_slot_bounties = None
        self.want_slot_flags = None
        self.want_owned_locations = None
        self.want_owned_career_slots = None
        self.want_cleared_pursuit_slots = None
        self.want_parts_levels = None
        self.want_parts_masks = None
        self.want_snapshot_injections = {}

    def refresh_state(self):
        loaded = self.savefile is not None

        try:
            self.snapshot_library = SaveFile.load_snapshot_library(self.snapshot_library_root)
            self.snapshot_library_error = None
        except Exception as exc:
            self.snapshot_library = []
            self.snapshot_library_error = str(exc)

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
            self.snapshot_detection_error = None
            try:
                self.garage_slots = self.savefile.get_garage_slots()
                self.garage_transfer_entries = self.savefile.get_transfer_car_entries()
                self.garage_allocator_snapshot = self.savefile.get_garage_allocator_snapshot()
                self.have_slot_bounties = {
                    slot.career_slot: slot.bounty for slot in self.garage_slots
                }
                self.have_slot_flags = {
                    slot.career_slot: slot.flags for slot in self.garage_slots if slot.flags is not None
                }
                self.have_owned_locations = {
                    entry.abs_off: entry.location_bits for entry in self.garage_transfer_entries
                }
                self.have_owned_career_slots = {
                    entry.abs_off: entry.career_slot for entry in self.garage_transfer_entries
                }
            except Exception as exc:
                self.garage_detection_error = str(exc)
                self.garage_slots = []
                self.garage_transfer_entries = []
                self.garage_allocator_snapshot = None
                self.have_slot_bounties = {}
                self.have_slot_flags = {}
                self.have_owned_locations = {}
                self.have_owned_career_slots = {}
            if self.garage_detection_error:
                self.parts_entries = []
                self.my_cars_entries = []
                self.parts_detection_error = self.garage_detection_error
            else:
                try:
                    self.parts_entries = self.savefile.get_resolved_parts_entries()
                    self.my_cars_entries = self.savefile.get_my_cars_parts_entries()
                except Exception as exc:
                    self.parts_entries = []
                    self.my_cars_entries = []
                    self.parts_detection_error = str(exc)
            try:
                self.build_snapshots = self.savefile.get_full_car_build_snapshots()
            except Exception as exc:
                self.build_snapshots = []
                self.snapshot_detection_error = str(exc)
            if self.parts_detection_error:
                self.have_parts_levels = {}
                self.have_parts_masks = {}
                self.want_parts_levels = None
                self.want_parts_masks = None
            else:
                all_part_entries = list(self.parts_entries) + list(self.my_cars_entries)
                self.have_parts_levels = {
                    entry.parts_slot: (
                        self._parts_level_dict_from_entry(entry)
                        if hasattr(entry, "display_name")
                        else self._parts_level_dict_from_my_car(entry)
                    )
                    for entry in all_part_entries
                }
                self.have_parts_masks = {
                    entry.parts_slot: entry.junkman_mask
                    for entry in all_part_entries
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
                self.want_owned_locations = None
                self.want_owned_career_slots = None
                self.want_cleared_pursuit_slots = None
            elif self.want_slot_bounties is None:
                self.want_slot_bounties = dict(self.have_slot_bounties)
                self.want_slot_flags = dict(self.have_slot_flags)
                self.want_owned_locations = dict(self.have_owned_locations)
                self.want_owned_career_slots = dict(self.have_owned_career_slots)
                self.want_cleared_pursuit_slots = set()
            else:
                self.want_slot_bounties = {
                    slot.career_slot: self.want_slot_bounties.get(slot.career_slot, slot.bounty)
                    for slot in self.garage_slots
                }
                self.want_slot_flags = {
                    slot.career_slot: self.want_slot_flags.get(slot.career_slot, slot.flags)
                    for slot in self.garage_slots if slot.flags is not None and self.want_slot_flags is not None
                }
                self.want_owned_locations = {
                    entry.abs_off: (self.want_owned_locations or {}).get(entry.abs_off, entry.location_bits)
                    for entry in self.garage_transfer_entries
                }
                self.want_owned_career_slots = {
                    entry.abs_off: (self.want_owned_career_slots or {}).get(entry.abs_off, entry.career_slot)
                    for entry in self.garage_transfer_entries
                }
                self.want_cleared_pursuit_slots = {
                    int(slot)
                    for slot in (self.want_cleared_pursuit_slots or set())
                    if any(garage_slot.career_slot == int(slot) for garage_slot in self.garage_slots)
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
                    parts_slot: dict((self.want_parts_levels or {}).get(parts_slot, self.have_parts_levels.get(parts_slot, {})))
                    for parts_slot in self.have_parts_levels
                }
                self.want_parts_masks = {
                    parts_slot: (self.want_parts_masks or {}).get(
                        parts_slot,
                        self.have_parts_masks.get(parts_slot, 0),
                    )
                    for parts_slot in self.have_parts_masks
                }
        else:
            self.lbl_file.setText("File: (not opened)")
            self.lbl_status.setText("Status: -")
            self.profile_info.setText("")
            self._reset_all_edit_state()
            self.garage_slots = []
            self.garage_transfer_entries = []
            self.garage_allocator_snapshot = None
            self.garage_detection_error = None
            self.parts_entries = []
            self.my_cars_entries = []
            self.parts_detection_error = None
            self.build_snapshots = []
            self.snapshot_detection_error = None
            self.show_all_garage_slots = False

        self.lbl_limits.setText(
            f"Limits: Safe {min(63, self._slot_capacity())}, Advanced {min(255, self._slot_capacity())}"
        )
        self._refresh_profile_inputs()
        self._refresh_garage_page()
        self._refresh_parts_page()
        self._refresh_my_cars_page()
        self._refresh_presets_page()
        self.refresh_cards()

    def _has_pending_changes(self) -> bool:
        for tid in set(self.want_counts.keys()) | set(self.have_counts.keys()):
            have = self.have_counts.get(tid, 0)
            want = self.want_counts.get(tid, have)
            if want != have:
                return True
        return (
            self.clear_unknown_next
            or self._has_profile_pending_changes()
            or self._has_parts_pending_changes()
            or self._has_garage_transfer_pending_changes()
            or bool(self.want_snapshot_injections)
        )

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
        self._maybe_reflow_my_cars_rows()
        self._maybe_reflow_library_rows()
        self._maybe_reflow_snapshot_rows()

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

    def on_open_catalog_folder(self):
        folder = self.catalog_path.parent
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not opened and hasattr(os, "startfile"):
            try:
                os.startfile(folder)
            except Exception:
                logger.warning("Failed to open catalog folder %s", folder, exc_info=True)

    def on_open(self, filepath: str | None = None):
        path = filepath
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open save", str(Path.home()), "All files (*.*)")
        if not path:
            return
        try:
            self.savefile = SaveFile.load(path)
            self._reset_want_edit_state()
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
