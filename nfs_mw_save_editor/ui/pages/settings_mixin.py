"""Settings and About pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.pages.constants import *
from ui.theme import available_theme_names, get_theme_preset


class SettingsMixin:
    def _build_settings_group(self, title: str, widgets: list) -> QFrame:
        """Create a garageCard-styled settings group with a title and child widgets."""
        group = QFrame()
        group.setObjectName("settingsGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("settingsGroupTitle")
        layout.addWidget(title_label)

        for w in widgets:
            if isinstance(w, QWidget):
                layout.addWidget(w)
            else:
                layout.addLayout(w)
        return group

    def _build_theme_preview_item(self, label_text: str) -> tuple[QWidget, QFrame, QLabel]:
        item = QWidget()
        item.setObjectName("themePreviewRow")
        layout = QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        swatch = QFrame()
        swatch.setObjectName("themePreviewSwatch")
        swatch.setFixedSize(22, 22)
        layout.addWidget(swatch, 0)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        label = QLabel(label_text)
        label.setObjectName("themePreviewLabel")
        text_col.addWidget(label)

        value = QLabel("-")
        value.setObjectName("themePreviewValue")
        text_col.addWidget(value)

        layout.addLayout(text_col, 1)
        return item, swatch, value

    def _update_theme_preview(self, theme_name: str) -> None:
        preset = get_theme_preset(theme_name)
        preview_values = [
            (self.theme_accent_swatch, self.theme_accent_value, preset.accent),
            (self.theme_background_swatch, self.theme_background_value, preset.background),
            (self.theme_foreground_swatch, self.theme_foreground_value, preset.foreground),
        ]
        for swatch, value_label, color in preview_values:
            swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid rgba(0, 0, 0, 0.35); border-radius: 8px;"
            )
            value_label.setText(color.upper())
            value_label.setToolTip(color.upper())

    def _build_settings_page(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        section = QLabel("Settings")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(available_theme_names())
        self.cmb_theme.setMinimumWidth(220)
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentText(getattr(self, "theme_name", available_theme_names()[0]))
        self.cmb_theme.blockSignals(False)
        self.cmb_theme.currentTextChanged.connect(self.on_theme_changed)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        theme_label = QLabel("Theme preset")
        theme_label.setObjectName("mutedLabel")
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.cmb_theme, 1)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(14)
        accent_item, self.theme_accent_swatch, self.theme_accent_value = self._build_theme_preview_item("Accent")
        bg_item, self.theme_background_swatch, self.theme_background_value = self._build_theme_preview_item("Background")
        fg_item, self.theme_foreground_swatch, self.theme_foreground_value = self._build_theme_preview_item("Foreground")
        swatch_row.addWidget(accent_item, 1)
        swatch_row.addWidget(bg_item, 1)
        swatch_row.addWidget(fg_item, 1)

        self.lbl_theme_hint = QLabel("Applies instantly and is saved for the next launch.")
        self.lbl_theme_hint.setObjectName("themeHint")

        layout.addWidget(self._build_settings_group("Appearance", [
            theme_row, swatch_row, self.lbl_theme_hint,
        ]))
        self._update_theme_preview(self.cmb_theme.currentText())

        # ── Token Limits ─────────────────────────────────────
        self.chk_safe = QCheckBox("Standard mode")
        self.chk_safe.setChecked(True)
        self.chk_safe.stateChanged.connect(self.on_range_toggle)
        self.chk_adv = QCheckBox("Legacy alternate mode")
        self.chk_adv.setChecked(False)
        self.chk_adv.stateChanged.connect(self.on_range_toggle)
        self.chk_practical_cap10 = QCheckBox("Allow current save maximum (remove the 10-token cap)")
        self.chk_practical_cap10.setChecked(False)
        self.chk_practical_cap10.stateChanged.connect(self.on_practical_cap_toggle)
        self.lbl_limits = QLabel("Limits: -")
        self.lbl_limits.setObjectName("mutedLabel")

        layout.addWidget(self._build_settings_group("Token Limits", [
            self.chk_practical_cap10, self.lbl_limits,
        ]))

        # ── Data Safety ──────────────────────────────────────
        self.chk_preserve_unknown = QCheckBox("Preserve unknown token data (recommended)")
        self.chk_preserve_unknown.setChecked(True)
        self.chk_preserve_unknown.stateChanged.connect(self.on_preserve_toggle)
        self.btn_clear_unknown = QPushButton("Clear unknown data (unsafe)")
        self.btn_clear_unknown.clicked.connect(self.on_clear_unknown_confirm)
        self.lbl_type_safety = QLabel(
            f"Safe Type_ID range: {SAFE_TYPE_MIN}-{SAFE_TYPE_MAX}. "
            "Using IDs outside this range may crash the game."
        )
        self.lbl_type_safety.setObjectName("mutedLabel")
        self.lbl_type_safety.setWordWrap(True)

        layout.addWidget(self._build_settings_group("Data Safety", [
            self.chk_preserve_unknown, self.btn_clear_unknown, self.lbl_type_safety,
        ]))

        # ── Display ──────────────────────────────────────────
        self.chk_show_integrity = QCheckBox("Show integrity panel on Profile")
        self.chk_show_integrity.setChecked(False)
        self.chk_show_integrity.stateChanged.connect(self.on_toggle_show_integrity)
        self.chk_show_unlinked_pursuits = QCheckBox("Show pursuit diagnostics on the Garage page")
        self.chk_show_unlinked_pursuits.setChecked(False)
        self.chk_show_unlinked_pursuits.stateChanged.connect(self.on_toggle_unlinked_pursuits)

        layout.addWidget(self._build_settings_group("Display", [
            self.chk_show_integrity, self.chk_show_unlinked_pursuits,
        ]))

        # ── Catalog ──────────────────────────────────────────
        self.lbl_catalog_path = QLabel(f"Catalog: {self.catalog_path}")
        self.lbl_catalog_path.setObjectName("mutedLabel")
        self.lbl_catalog_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_open_catalog = QPushButton("Open folder")
        self.btn_open_catalog.clicked.connect(self.on_open_catalog_folder)
        catalog_row = QHBoxLayout()
        catalog_row.addWidget(self.lbl_catalog_path, 1)
        catalog_row.addWidget(self.btn_open_catalog)

        layout.addWidget(self._build_settings_group("Catalog", [
            catalog_row,
        ]))

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

        title = QLabel(APP_DISPLAY_NAME)
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"{APP_VERSION}  ·  {APP_PLATFORM}")
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
            "Token layout is detected automatically for each save file.\n"
            "Apply updates the open save in memory; Save + backup writes it to disk.\n\n"
            "Keyboard shortcuts:\n"
            "  Ctrl+O  Open save · Ctrl+S  Save + backup · Ctrl+Z  Reset Want\n\n"
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
