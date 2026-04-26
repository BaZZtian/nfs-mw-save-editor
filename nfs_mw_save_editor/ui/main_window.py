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

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QBrush, QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
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
from ui.page_chrome import PageChromeMixin
from ui.pages.constants import *
from ui.pages.garage_mixin import GarageMixin
from ui.pages.junkman_mixin import JunkmanMixin
from ui.pages.parts_mixin import PartsMixin
from ui.pages.presets_mixin import PresetsMixin
from ui.pages.profile_mixin import ProfileMixin
from ui.pages.settings_mixin import SettingsMixin
from ui.staged_state import StagedEditState
from ui.theme import (
    _SCOPED_POPUP_THEME_APPLYING_PROPERTY,
    apply_popup_theme,
    apply_theme_palette,
    build_page_stylesheet,
    build_shell_stylesheet,
    ensure_scoped_theme_mode,
    load_ui_setting,
    load_saved_theme_name,
    resolve_theme_tokens,
    save_theme_name,
)
from ui.widgets import SplitTextProgressBar, ThemeTransitionOverlay, ToastNotification

logger = logging.getLogger(__name__)


def _appdata_dir() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Roaming"


def _user_catalog_path() -> Path:
    return _appdata_dir() / APP_NAME / CATALOG_FILENAME


def _user_snapshot_library_path() -> Path:
    return _appdata_dir() / APP_NAME / SaveFile.USER_SNAPSHOT_LIBRARY_DIRNAME


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
    PageChromeMixin,
    JunkmanMixin,
    ProfileMixin,
    GarageMixin,
    PartsMixin,
    PresetsMixin,
    SettingsMixin,
    QMainWindow,
):
    """Main UI controller.

    Staged-state cleanup note: ``want_slot_flags`` and
    ``want_cleared_pursuit_slots`` remain projection caches owned by
    MainWindow refresh/garage-transfer logic, not staged helper fields.
    """

    def __init__(self):
        super().__init__()
        icon_path = resource_path("assets", "icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowTitle(APP_WINDOW_TITLE)
        app = QApplication.instance()
        app_theme = app.property("themeName") if app is not None else None
        self.theme_name = app_theme if isinstance(app_theme, str) and app_theme else load_saved_theme_name()
        saved_alias_unlock = load_ui_setting("unlock_profile_alias_16", False)
        self.unlock_profile_alias_16 = bool(saved_alias_unlock) if isinstance(saved_alias_unlock, bool) else False
        self._theme_transition_overlay: Optional[ThemeTransitionOverlay] = None
        self._page_transition_overlay: Optional[ThemeTransitionOverlay] = None
        self.staged_state = StagedEditState()

    #  state
        self.savefile: Optional[SaveFile] = None
        self.have_counts: Dict[int, int] = {}
        self.have_money = 0
        self.have_profile_alias: str = ""
        self.profile_alias_error: Optional[str] = None
        self.garage_slots: List[ResolvedGarageEntry] = []
        self.garage_transfer_entries: List[ResolvedTransferCarEntry] = []
        self.garage_allocator_snapshot: Optional[GarageAllocatorSnapshot] = None
        self.parts_entries: List[ResolvedPartsEntry] = []
        self.my_cars_entries: List[ResolvedMyCarsEntry] = []
        self.build_snapshots: List[FullCarBuildSnapshot] = []
        self.snapshot_library: List[SnapshotLibraryEntry] = []
        self.have_parts_levels: Dict[int, Dict[str, int]] = {}
        self.have_parts_masks: Dict[int, int] = {}
        self.have_slot_bounties: Dict[int, int] = {}
        self.have_slot_heats: Dict[int, int] = {}
        self.have_slot_flags: Dict[int, int] = {}
        self.want_slot_flags: Optional[Dict[int, int]] = None
        self.have_owned_locations: Dict[int, int] = {}
        self.have_owned_career_slots: Dict[int, int] = {}
        self.want_cleared_pursuit_slots: Optional[set[int]] = None
        self.garage_detection_error: Optional[str] = None
        self.parts_detection_error: Optional[str] = None
        self.snapshot_detection_error: Optional[str] = None
        self.snapshot_library_error: Optional[str] = None
        self.show_all_garage_slots = False
        self.show_integrity_panel = False
        self.show_garage_allocator_diagnostics = False
        self.show_parts_diagnostics = False
        self.tokens: List[TokenEntry] = []
        self.safe_mode = True
        self.practical_cap10 = True
        self.preserve_unknown = True
        self.clear_unknown_next = False
        self.show_only_changed = False
        self.garage_filter = "All"
        self.tuning_filter = "All"
        self._profile_refreshing = False
        self._parts_refreshing = False
        self._popup_theme_event_filter_applying = False
        self._garage_slot_columns = 0
        self._parts_slot_columns = 0
        self._snapshot_slot_columns = 0
        self._library_slot_columns = 0
        self._pink_slip_badge_pixmap: Optional[QPixmap] = None
        self.snapshot_library_root = SaveFile.default_snapshot_library_root()
        self.user_snapshot_library_root = _user_snapshot_library_path()
        self.want_snapshot_injections: Dict[str, str] = {}
        self.snapshot_library_filter = "Main"
        self.snapshot_save_filter = "All"
        self.presets_view = "Library"
        self._garage_cards_dirty = True
        self._parts_cards_dirty = True
        self._snapshot_cards_dirty = True
        self._snapshot_library_cards_dirty = True

        self.catalog_path = _ensure_user_catalog_path()
        self.load_catalog()
        self._build_ui()
        if app is not None:
            app.installEventFilter(self)
        self._apply_scoped_theme_to_visible_roots(self.theme_name, mark_hidden_dirty=True)
        self._setup_render_timers()
        self.refresh_state()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("appChromeRoot")
        root.setAutoFillBackground(True)
        self.setCentralWidget(root)
        base = QVBoxLayout(root)
        base.setContentsMargins(12, 12, 12, 12)
        base.setSpacing(10)

        self.header_chrome = QWidget()
        self.header_chrome.setLayout(self._build_header())
        base.addWidget(self.header_chrome)

        body = QHBoxLayout()
        body.setSpacing(12)
        base.addLayout(body, 1)

        self.nav_chrome = QWidget()
        self.nav_chrome.setLayout(self._build_nav())
        self.nav_chrome.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
        body.addWidget(self.nav_chrome, 0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.setAutoFillBackground(True)
        body.addWidget(self.stack, 1)

        self.page_junk = self._build_junk_page()
        self.page_profile = self._build_profile_page()
        self.page_garage = self._build_garage_page()
        self.page_parts = self._build_parts_page()
        self.page_presets = self._build_presets_page()
        self.page_settings = self._build_settings_page()
        self.page_about = self._build_about_page()
        self._page_theme_roots = {
            "Junkman": self.page_junk,
            "Profile": self.page_profile,
            "Garage": self.page_garage,
            "Tuning": self.page_parts,
            "Builds": self.page_presets,
            "Settings": self.page_settings,
            "About": self.page_about,
        }
        self._page_theme_dirty = {name: False for name in self._page_theme_roots}
        self._shell_theme_roots = [self.header_chrome, self.nav_chrome]
        self._backdrop_theme_roots = [root, self.stack]

        for p in [self.page_junk, self.page_profile, self.page_garage, self.page_parts, self.page_presets,
                   self.page_settings, self.page_about]:
            self.stack.addWidget(p)

        self._select_page("Junkman")
        self.footer_chrome = QWidget()
        self.footer_chrome.setLayout(self._build_footer())
        base.addWidget(self.footer_chrome)
        self._shell_theme_roots.append(self.footer_chrome)

        # -- Keyboard shortcuts --
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.on_open)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.on_save)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.on_reset_want)

        # -- Drag & drop --
        self.setAcceptDrops(True)

    def _setup_render_timers(self) -> None:
        self._resize_reflow_timer = QTimer(self)
        self._resize_reflow_timer.setSingleShot(True)
        self._resize_reflow_timer.timeout.connect(self._on_heavy_page_reflow_timeout)

        self._garage_search_timer = QTimer(self)
        self._garage_search_timer.setSingleShot(True)
        self._garage_search_timer.timeout.connect(lambda: self._refresh_garage_page(reason="search_change"))

        self._parts_search_timer = QTimer(self)
        self._parts_search_timer.setSingleShot(True)
        self._parts_search_timer.timeout.connect(lambda: self._refresh_parts_page(reason="search_change"))

        self._presets_search_timer = QTimer(self)
        self._presets_search_timer.setSingleShot(True)
        self._presets_search_timer.timeout.connect(lambda: self._refresh_presets_page(reason="search_change"))

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
        self.lbl_unsaved.setAlignment(Qt.AlignCenter)
        self.lbl_unsaved.setContentsMargins(14, 5, 14, 5)
        self.lbl_unsaved.setMinimumHeight(28)
        self.lbl_unsaved.setProperty("pending", False)
        self.lbl_unsaved.setVisible(False)

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

        for name in ["Junkman", "Profile", "Garage", "Tuning", "Builds", "Settings", "About"]:
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
        self.progress_bar = SplitTextProgressBar()
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
        if self._current_stack_page_name() == name:
            return
        for n, btn in self.nav_buttons.items():
            btn.setChecked(n == name)
        mapping = {
            "Junkman": self.page_junk,
            "Profile": self.page_profile,
            "Garage": self.page_garage,
            "Tuning": self.page_parts,
            "Builds": self.page_presets,
            "Settings": self.page_settings,
            "About": self.page_about,
        }
        overlay = self._start_page_transition_overlay()
        self.stack.setCurrentWidget(mapping[name])
        self._ensure_page_theme(name)
        if name == "Profile":
            self._refresh_profile_inputs()
        elif name == "Junkman" and hasattr(self, "cards_container") and hasattr(self, "lbl_free"):
            self._sync_cards_per_row(force=True)
            self.refresh_cards()
        elif name == "Garage":
            self._refresh_garage_page(reason="page_enter")
        elif name == "Tuning":
            self._refresh_parts_page(reason="page_enter")
        elif name == "Builds":
            self._refresh_presets_page(reason="page_enter")
        if overlay is not None:
            overlay.start()

    def _current_stack_page_name(self) -> Optional[str]:
        if not hasattr(self, "stack"):
            return None
        current = self.stack.currentWidget()
        if current is self.page_garage:
            return "Garage"
        if current is self.page_parts:
            return "Tuning"
        if current is self.page_presets:
            return "Builds"
        if current is self.page_profile:
            return "Profile"
        if current is self.page_junk:
            return "Junkman"
        if current is self.page_settings:
            return "Settings"
        if current is self.page_about:
            return "About"
        return None

    def _apply_stylesheet_to_root(self, root: Optional[QWidget], stylesheet: str, *, theme_name: str) -> None:
        if root is None:
            return
        applied_name = root.property("_scopedThemeName")
        if applied_name == theme_name and root.styleSheet() == stylesheet:
            return
        root.setStyleSheet(stylesheet)
        root.setProperty("_scopedThemeName", theme_name)

    def _apply_shell_theme(self, theme_name: str) -> None:
        stylesheet = build_shell_stylesheet(theme_name)
        for root in getattr(self, "_shell_theme_roots", []):
            self._apply_stylesheet_to_root(root, stylesheet, theme_name=theme_name)

    def _apply_backdrop_palette(self, theme_name: str) -> None:
        try:
            from PySide6.QtGui import QColor, QPalette
        except Exception:
            return
        bg = resolve_theme_tokens(theme_name)["BG"]
        brush = QBrush(QColor(bg))
        for root in getattr(self, "_backdrop_theme_roots", []):
            if root is None:
                continue
            palette = root.palette()
            palette.setBrush(QPalette.ColorRole.Window, brush)
            root.setPalette(palette)

    def _apply_page_theme(self, page_name: str) -> None:
        root = getattr(self, "_page_theme_roots", {}).get(page_name)
        if root is None:
            return
        stylesheet = build_page_stylesheet(self.theme_name)
        self._apply_stylesheet_to_root(root, stylesheet, theme_name=self.theme_name)
        if hasattr(self, "_page_theme_dirty"):
            self._page_theme_dirty[page_name] = False

    def _popup_owned_by_main_window(self, widget: QWidget) -> bool:
        current = widget
        while current is not None:
            if current is self:
                return True
            current = current.parent()
        return False

    def _iter_owned_popup_widgets(self) -> list[QWidget]:
        app = QApplication.instance()
        if app is None:
            return []
        widgets: list[QWidget] = []
        for widget in app.topLevelWidgets():
            if not isinstance(widget, (QDialog, QMessageBox)):
                continue
            if isinstance(widget, QFileDialog):
                continue
            if not self._popup_owned_by_main_window(widget):
                continue
            widgets.append(widget)
        return widgets

    def _apply_popup_theme_to_visible_widgets(self) -> None:
        for widget in self._iter_owned_popup_widgets():
            apply_popup_theme(widget, self.theme_name)
        toasts = [toast for toast in self.findChildren(ToastNotification) if toast.isVisible()]
        for toast in toasts:
            apply_popup_theme(toast, self.theme_name)
        if toasts:
            ToastNotification.reposition_active(self)

    def _clear_theme_transition_overlay(self) -> None:
        overlay = self._theme_transition_overlay
        self._theme_transition_overlay = None
        if overlay is not None:
            overlay.finish_immediately()

    def _clear_page_transition_overlay(self) -> None:
        overlay = self._page_transition_overlay
        self._page_transition_overlay = None
        if overlay is not None:
            overlay.finish_immediately()

    def _start_theme_transition_overlay(self) -> Optional[ThemeTransitionOverlay]:
        root = self.centralWidget()
        if root is None or not root.isVisible():
            return None
        snapshot = root.grab()
        if snapshot.isNull() or snapshot.size().isEmpty():
            return None

        self._clear_theme_transition_overlay()

        overlay = ThemeTransitionOverlay(root, snapshot)
        overlay.show()
        overlay.raise_()
        overlay.destroyed.connect(
            lambda _obj=None, overlay=overlay: (
                setattr(self, "_theme_transition_overlay", None)
                if self._theme_transition_overlay is overlay
                else None
            )
        )
        self._theme_transition_overlay = overlay
        return overlay

    def _start_page_transition_overlay(self) -> Optional[ThemeTransitionOverlay]:
        if not hasattr(self, "stack") or not self.stack.isVisible():
            return None
        snapshot = self.stack.grab()
        if snapshot.isNull() or snapshot.size().isEmpty():
            return None

        self._clear_page_transition_overlay()

        overlay = ThemeTransitionOverlay(self.stack, snapshot, duration_ms=120)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.show()
        overlay.raise_()
        overlay.destroyed.connect(
            lambda _obj=None, overlay=overlay: (
                setattr(self, "_page_transition_overlay", None)
                if self._page_transition_overlay is overlay
                else None
            )
        )
        self._page_transition_overlay = overlay
        return overlay

    def _mark_hidden_pages_theme_dirty(self, current_page_name: Optional[str]) -> None:
        if not hasattr(self, "_page_theme_dirty"):
            return
        for page_name in self._page_theme_dirty:
            self._page_theme_dirty[page_name] = page_name != current_page_name

    def _ensure_page_theme(self, page_name: str) -> None:
        if not hasattr(self, "_page_theme_dirty"):
            return
        root = self._page_theme_roots.get(page_name)
        if root is None:
            return
        if not self._page_theme_dirty.get(page_name, False):
            applied_name = root.property("_scopedThemeName")
            if applied_name == self.theme_name and root.styleSheet():
                return
        self._apply_page_theme(page_name)

    def _apply_scoped_theme_to_visible_roots(self, theme_name: str, *, mark_hidden_dirty: bool) -> None:
        app = QApplication.instance()
        if app is not None:
            ensure_scoped_theme_mode(app)
        self.theme_name = theme_name
        self._apply_backdrop_palette(theme_name)
        self._apply_shell_theme(theme_name)
        current_page = self._current_stack_page_name()
        if current_page:
            self._apply_page_theme(current_page)
        if mark_hidden_dirty:
            self._mark_hidden_pages_theme_dirty(current_page)

    def _mark_garage_cards_dirty(self) -> None:
        self._garage_cards_dirty = True
        if hasattr(self, "_garage_render_controller"):
            self._garage_render_controller.cancel()

    def _mark_parts_cards_dirty(self) -> None:
        self._parts_cards_dirty = True
        if hasattr(self, "_parts_render_controller"):
            self._parts_render_controller.cancel()

    def _mark_presets_cards_dirty(self, *, library: bool = True, snapshot: bool = True) -> None:
        if library:
            self._snapshot_library_cards_dirty = True
            if hasattr(self, "_snapshot_library_render_controller"):
                self._snapshot_library_render_controller.cancel()
        if snapshot:
            self._snapshot_cards_dirty = True
            if hasattr(self, "_snapshot_render_controller"):
                self._snapshot_render_controller.cancel()

    def _mark_all_heavy_pages_dirty(self) -> None:
        self._mark_garage_cards_dirty()
        self._mark_parts_cards_dirty()
        self._mark_presets_cards_dirty()

    def _on_heavy_page_reflow_timeout(self) -> None:
        current = self._current_stack_page_name()
        if current == "Garage":
            self._maybe_reflow_garage_rows()
        elif current == "Tuning":
            self._maybe_reflow_parts_rows()
        elif current == "Builds":
            self._maybe_reflow_library_rows()
            self._maybe_reflow_snapshot_rows()

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
        self.staged_state.counts.clear()
        self.have_money = 0
        self.have_profile_alias = ""
        self.staged_state.money.clear()
        self.staged_state.profile_alias.clear()
        self.profile_alias_error = None
        self.have_slot_bounties = {}
        self.have_slot_heats = {}
        self.have_slot_flags = {}
        self.staged_state.slot_bounties.clear()
        self.staged_state.slot_heats.clear()
        self.want_slot_flags = None
        self.have_owned_locations = {}
        self.have_owned_career_slots = {}
        self.staged_state.owned_locations.clear()
        self.staged_state.owned_career_slots.clear()
        self.want_cleared_pursuit_slots = None
        self.have_parts_levels = {}
        self.have_parts_masks = {}
        self.staged_state.parts_levels.clear()
        self.staged_state.parts_masks.clear()
        self.want_snapshot_injections = {}

    def _reset_want_edit_state(self) -> None:
        """Clear all want_* fields back to None / {} — used after Apply or open-file."""
        self.staged_state.counts.clear()
        self.staged_state.money.clear()
        self.staged_state.profile_alias.clear()
        self.profile_alias_error = None
        self.staged_state.slot_bounties.clear()
        self.staged_state.slot_heats.clear()
        self.want_slot_flags = None
        self.staged_state.owned_locations.clear()
        self.staged_state.owned_career_slots.clear()
        self.want_cleared_pursuit_slots = None
        self.staged_state.parts_levels.clear()
        self.staged_state.parts_masks.clear()
        self.want_snapshot_injections = {}

    def refresh_state(self):
        loaded = self.savefile is not None

        try:
            self.snapshot_library = SaveFile.load_snapshot_library(
                self.snapshot_library_root,
                user_root=self.user_snapshot_library_root,
            )
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
            self.have_profile_alias = self.savefile.get_profile_alias()
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
                self.have_slot_heats = {
                    slot.career_slot: slot.heat_level
                    for slot in self.garage_slots
                    if slot.occupied and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
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
                self.have_slot_heats = {}
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
                self.staged_state.parts_levels.clear()
                self.staged_state.parts_masks.clear()
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
            if self.garage_detection_error:
                self.staged_state.slot_bounties.clear()
                self.staged_state.slot_heats.clear()
                self.want_slot_flags = None
                self.staged_state.owned_locations.clear()
                self.staged_state.owned_career_slots.clear()
                self.want_cleared_pursuit_slots = None
            else:
                have_slot_bounties = {
                    slot.career_slot: self.have_slot_bounties.get(slot.career_slot, slot.bounty)
                    for slot in self.garage_slots
                }
                self.staged_state.slot_bounties.prune_to_keys(set(have_slot_bounties), have_slot_bounties)
                have_slot_heats = {
                    slot.career_slot: self.have_slot_heats.get(slot.career_slot, slot.heat_level)
                    for slot in self.garage_slots
                    if slot.occupied and slot.career_slot != SaveFile.EMPTY_CAREER_SLOT
                }
                self.staged_state.slot_heats.prune_to_keys(set(have_slot_heats), have_slot_heats)
                if self.want_slot_flags is None:
                    self.want_slot_flags = dict(self.have_slot_flags)
                    self.want_cleared_pursuit_slots = set()
                else:
                    self.want_slot_flags = {
                        slot.career_slot: self.want_slot_flags.get(slot.career_slot, slot.flags)
                        for slot in self.garage_slots if slot.flags is not None and self.want_slot_flags is not None
                    }
                    self.want_cleared_pursuit_slots = {
                        int(slot)
                        for slot in (self.want_cleared_pursuit_slots or set())
                        if any(garage_slot.career_slot == int(slot) for garage_slot in self.garage_slots)
                    }
                have_owned_locations = {
                    entry.abs_off: self.have_owned_locations.get(entry.abs_off, entry.location_bits)
                    for entry in self.garage_transfer_entries
                }
                self.staged_state.owned_locations.prune_to_keys(set(have_owned_locations), have_owned_locations)
                have_owned_career_slots = {
                    entry.abs_off: self.have_owned_career_slots.get(entry.abs_off, entry.career_slot)
                    for entry in self.garage_transfer_entries
                }
                self.staged_state.owned_career_slots.prune_to_keys(set(have_owned_career_slots), have_owned_career_slots)
            if self.parts_detection_error:
                self.staged_state.parts_levels.clear()
                self.staged_state.parts_masks.clear()
            else:
                have_parts_levels = {
                    slot: dict(levels) for slot, levels in self.have_parts_levels.items()
                }
                self.staged_state.parts_levels.prune_to_keys(set(have_parts_levels), have_parts_levels)
                self.staged_state.parts_masks.prune_to_keys(set(self.have_parts_masks), self.have_parts_masks)
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

        default_cap = min(10, self._slot_capacity())
        unlocked_cap = min(63, self._slot_capacity())
        self.lbl_limits.setText(f"Limits: Default {default_cap}, Unlocked {unlocked_cap}")
        self._mark_all_heavy_pages_dirty()
        self._refresh_profile_inputs()
        current_page = self._current_stack_page_name()
        if current_page == "Garage":
            self._refresh_garage_page(reason="save_load_visible")
        elif current_page == "Tuning":
            self._refresh_parts_page(reason="save_load_visible")
        elif current_page == "Builds":
            self._refresh_presets_page(reason="save_load_visible")
        self.refresh_cards()
        if hasattr(self, "_schedule_parts_pool_prewarm"):
            self._schedule_parts_pool_prewarm(delay_ms=0)

    def _has_pending_changes(self) -> bool:
        return (
            self.staged_state.counts.has_pending(self.have_counts)
            or self.clear_unknown_next
            or self._has_profile_pending_changes()
            or self._has_parts_pending_changes()
            or self._has_garage_transfer_pending_changes()
            or self._has_garage_pursuit_pending_changes()
            or bool(self.want_snapshot_injections)
        )

    def _update_action_states(self):
        pending = self._has_pending_changes()
        enabled = self.savefile is not None
        has_error = bool(self.profile_alias_error)
        self.btn_apply.setEnabled(enabled and pending and not has_error)
        self.btn_reset_want.setEnabled(enabled)
        self.lbl_unsaved.setText("Unsaved changes" if pending else "")
        self.lbl_unsaved.setProperty("pending", pending)
        self.lbl_unsaved.setVisible(pending)
        self.lbl_unsaved.style().unpolish(self.lbl_unsaved)
        self.lbl_unsaved.style().polish(self.lbl_unsaved)

    def _update_header_path(self):
        text = "File: (not opened)" if not self.savefile else f"{self.savefile.path}"
        fm = self.lbl_file.fontMetrics()
        available = max(120, self.lbl_file.width())
        self.lbl_file.setText(fm.elidedText(text, Qt.ElideMiddle, available))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._theme_transition_overlay is not None:
            self._theme_transition_overlay.sync_to_parent()
        if self._page_transition_overlay is not None:
            self._page_transition_overlay.sync_to_parent()
        ToastNotification.reposition_active(self)
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
        if hasattr(self, "_resize_reflow_timer"):
            self._resize_reflow_timer.start(120)

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

    def on_theme_changed(self, theme_name: str) -> None:
        resolved_name = save_theme_name(theme_name)
        overlay = self._start_theme_transition_overlay()
        app = QApplication.instance()
        if app is not None:
            apply_theme_palette(app, resolved_name)
        self._apply_scoped_theme_to_visible_roots(resolved_name, mark_hidden_dirty=True)
        self._apply_popup_theme_to_visible_widgets()
        if hasattr(self, "_on_parts_theme_changed"):
            self._on_parts_theme_changed()
        if hasattr(self, "cmb_theme"):
            self.cmb_theme.blockSignals(True)
            self.cmb_theme.setCurrentText(resolved_name)
            self.cmb_theme.blockSignals(False)
        if hasattr(self, "_update_theme_combo_active_marker"):
            self._update_theme_combo_active_marker(resolved_name)
        if hasattr(self, "_update_theme_preview"):
            self._update_theme_preview(resolved_name)
        self.update()
        if overlay is not None:
            overlay.start()

    def eventFilter(self, watched, event):
        if not isinstance(watched, (QDialog, QMessageBox)):
            return False
        if isinstance(watched, QFileDialog):
            return False
        if not self._popup_owned_by_main_window(watched):
            return False
        if getattr(self, "_popup_theme_event_filter_applying", False):
            return False
        if bool(watched.property(_SCOPED_POPUP_THEME_APPLYING_PROPERTY)):
            return False
        if event is not None and event.type() == QEvent.Type.Show:
            self._popup_theme_event_filter_applying = True
            try:
                apply_popup_theme(watched, self.theme_name)
            finally:
                self._popup_theme_event_filter_applying = False
        return False

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
