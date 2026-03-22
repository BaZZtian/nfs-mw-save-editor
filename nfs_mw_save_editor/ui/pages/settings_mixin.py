"""Settings and About pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.pages.constants import *


class SettingsMixin:
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


