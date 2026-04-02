"""Settings and About pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ui.pages.constants import *
from ui.theme import available_theme_names, get_theme_preset, resolve_theme_tokens


def _parse_px(value: str, fallback: int) -> int:
    if isinstance(value, str) and value.endswith("px"):
        try:
            return int(float(value[:-2]))
        except ValueError:
            return fallback
    return fallback


class ThemeComboItemDelegate(QStyledItemDelegate):
    """Popup delegate that marks the currently applied theme with a calm check state."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def _active_theme_name(self) -> str:
        active_name = self._combo.property("activeThemeName")
        if isinstance(active_name, str) and active_name:
            return active_name
        return self._combo.currentText()

    def paint(self, painter: QPainter, option, index) -> None:
        theme_name = self._active_theme_name()
        tokens = resolve_theme_tokens(theme_name)
        item_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_active_theme = item_text == theme_name

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        row_rect = option.rect.adjusted(6, 2, -6, -2)
        radius = _parse_px(tokens.get("RADIUS_MD", "8px"), 8)

        selected_fill = QColor(tokens["BG_NAV_ACTIVE"])
        active_fill = QColor(tokens["BG_NAV_ACTIVE"])
        active_fill.setAlpha(155)
        active_border = QColor(tokens["BORDER_NAV_ACTIVE"])
        active_border.setAlpha(180)
        text_color = QColor(tokens["TEXT"])

        if is_selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(selected_fill)
            painter.drawRoundedRect(row_rect, radius, radius)
        elif is_active_theme:
            painter.setPen(QPen(active_border, 1.0))
            painter.setBrush(active_fill)
            painter.drawRoundedRect(row_rect, radius, radius)

        content_rect = row_rect.adjusted(12, 0, -12, 0)
        reserve = 20 if is_active_theme else 0
        text_rect = content_rect.adjusted(0, 0, -reserve, 0)

        painter.setPen(text_color)
        painter.setFont(option.font)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            item_text,
        )

        if is_active_theme:
            check_rect = content_rect.adjusted(content_rect.width() - 18, 0, 0, 0)
            check_font = painter.font()
            check_font.setBold(True)
            painter.setFont(check_font)
            if is_selected:
                painter.setPen(text_color)
            else:
                painter.setPen(QColor(tokens["BORDER_NAV_ACTIVE"]))
            painter.drawText(
                check_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                "✓",
            )

        painter.restore()


class SettingsMixin:
    def _update_theme_combo_active_marker(self, theme_name: str) -> None:
        if not hasattr(self, "cmb_theme"):
            return
        self.cmb_theme.setProperty("activeThemeName", theme_name)
        self.cmb_theme.update()
        view = self.cmb_theme.view()
        if view is not None:
            view.update()
            if view.viewport() is not None:
                view.viewport().update()

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
        theme_view = QListView(self.cmb_theme)
        theme_view.setUniformItemSizes(True)
        self.cmb_theme.setView(theme_view)
        self.cmb_theme.setItemDelegate(ThemeComboItemDelegate(self.cmb_theme))
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentText(getattr(self, "theme_name", available_theme_names()[0]))
        self.cmb_theme.blockSignals(False)
        self._update_theme_combo_active_marker(self.cmb_theme.currentText())
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
