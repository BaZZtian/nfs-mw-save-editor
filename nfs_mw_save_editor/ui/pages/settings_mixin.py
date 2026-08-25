"""Settings and About pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from resources import resource_path
from ui.pages.constants import *
from ui.theme import (
    apply_popup_theme,
    available_theme_names,
    get_theme_preset,
    resolve_theme_tokens,
    save_ui_setting,
)


def _parse_px(value: str, fallback: int) -> int:
    if isinstance(value, str) and value.endswith("px"):
        try:
            return int(float(value[:-2]))
        except ValueError:
            return fallback
    return fallback


OPEN_SOURCE_DOCUMENTS = (
    ("Third-party notices", ("THIRD_PARTY_NOTICES.md",)),
    ("GNU LGPL v3", ("licenses", "LGPL-3.0.txt")),
    ("GNU GPL v3", ("licenses", "GPL-3.0.txt")),
    ("Qt third-party licenses", ("licenses", "QT_THIRD_PARTY_LICENSES.txt")),
    ("Qt source and relinking", ("licenses", "QT_LGPL_COMPLIANCE.md")),
    ("Python license", ("licenses", "PYTHON-3.13.txt")),
    ("NumPy licenses", ("licenses", "NUMPY-2.5.1.txt")),
    ("PyInstaller license", ("licenses", "PYINSTALLER-6.18.0.txt")),
)


class ThemeComboItemDelegate(QStyledItemDelegate):
    """Popup delegate with compact 'Aa' theme preview icons."""

    _ICON_SIZE = 24
    _ICON_RADIUS = 7.0
    _ICON_FONT_PX = 11
    _ICON_GAP = 10  # gap between icon and theme name

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def _active_theme_name(self) -> str:
        active_name = self._combo.property("activeThemeName")
        if isinstance(active_name, str) and active_name:
            return active_name
        return self._combo.currentText()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return base.__class__(base.width(), max(base.height(), 30))

    # ── Drawing ──────────────────────────────────────────────────────

    def _draw_aa_icon(self, painter: QPainter, rect: QRectF,
                      bg: str, accent: str) -> None:
        """Draw a small rounded square filled with *bg*, containing 'Aa'
        in the theme's *accent* colour."""
        painter.save()

        # 1. Background square with subtle border
        border_color = QColor(255, 255, 255, 28)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                self._ICON_RADIUS, self._ICON_RADIUS)

        # 2. Font
        icon_font = QFont("Segoe UI", -1)
        icon_font.setPixelSize(self._ICON_FONT_PX)
        icon_font.setWeight(QFont.Weight.Bold)
        icon_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        painter.setFont(icon_font)

        fm = painter.fontMetrics()
        full_text = "Aa"
        text_w = fm.horizontalAdvance(full_text)
        # Centre the text inside the rect
        tx = rect.left() + (rect.width() - text_w) / 2.0
        ty = rect.top() + (rect.height() + fm.ascent()) / 2.0 - fm.descent() / 2.0

        # 3. Draw "Aa" with both letters in accent colour
        painter.setPen(QColor(accent))
        painter.drawText(tx, ty, full_text)

        painter.restore()

    @staticmethod
    def make_theme_icon(theme_name: str, size: int = 24) -> QIcon:
        """Render an 'Aa' icon for *theme_name* as a QIcon."""
        preset = get_theme_preset(theme_name)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, size, size)

        # Background
        border_color = QColor(255, 255, 255, 28)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QColor(preset.background))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7.0, 7.0)

        # Text
        font = QFont("Segoe UI", -1)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Bold)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text = "Aa"
        tw = fm.horizontalAdvance(text)
        tx = (size - tw) / 2.0
        ty = (size + fm.ascent()) / 2.0 - fm.descent() / 2.0
        painter.setPen(QColor(preset.accent))
        painter.drawText(tx, ty, text)
        painter.end()
        return QIcon(pixmap)

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

        # ── Row highlight ────────────────────────────────────────────
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

        # ── "Aa" icon ────────────────────────────────────────────────
        item_preset = get_theme_preset(item_text)
        icon_y = content_rect.center().y() - self._ICON_SIZE / 2.0
        icon_rect = QRectF(content_rect.left(), icon_y,
                           self._ICON_SIZE, self._ICON_SIZE)
        self._draw_aa_icon(
            painter, icon_rect,
            bg=item_preset.background,
            accent=item_preset.accent,
        )

        # ── Theme name ───────────────────────────────────────────────
        reserve = 24 if is_active_theme else 0
        name_left = content_rect.left() + self._ICON_SIZE + self._ICON_GAP
        text_rect = content_rect.adjusted(name_left - content_rect.left(), 0, -reserve, 0)

        painter.setPen(text_color)
        painter.setFont(option.font)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            item_text,
        )

        # ── Checkmark for active theme ───────────────────────────────
        if is_active_theme:
            check_rect = content_rect.adjusted(content_rect.width() - 18, 0, -2, 0)
            if is_selected:
                check_color = text_color
            else:
                check_color = QColor(tokens["BORDER_NAV_ACTIVE"])
            check_pen = QPen(check_color, 1.8)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            cy = check_rect.center().y()
            sx = check_rect.left() + 4
            mx = check_rect.left() + 8
            ex = check_rect.right() - 2
            painter.drawLine(sx, cy, mx, cy + 4)
            painter.drawLine(mx, cy + 4, ex, cy - 5)

        painter.restore()


class SettingsMixin:
    def on_toggle_technical_card_details(self) -> None:
        self.show_technical_card_details = self.chk_show_technical_card_details.isChecked()
        save_ui_setting("show_technical_card_details", self.show_technical_card_details)
        for mark_name, refresh_name in (
            ("_mark_garage_cards_dirty", "_refresh_garage_page"),
            ("_mark_parts_cards_dirty", "_refresh_parts_page"),
            ("_mark_presets_cards_dirty", "_refresh_presets_page"),
        ):
            mark = getattr(self, mark_name, None)
            refresh = getattr(self, refresh_name, None)
            if callable(mark):
                mark()
            if callable(refresh):
                refresh(reason="data_change")

    def on_toggle_profile_alias_unlock(self) -> None:
        self.unlock_profile_alias_16 = self.chk_unlock_profile_alias_16.isChecked()
        save_ui_setting("unlock_profile_alias_16", self.unlock_profile_alias_16)
        if hasattr(self, "alias_edit"):
            self._refresh_profile_inputs()
        self._update_action_states()

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
        """Create a content-card-styled settings group with a title and child widgets."""
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
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 10, 0, 10)

        section = QLabel("Settings")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        self.cmb_theme = QComboBox()
        self.cmb_theme.setIconSize(QSize(24, 24))
        for name in available_theme_names():
            icon = ThemeComboItemDelegate.make_theme_icon(name)
            self.cmb_theme.addItem(icon, name)
        self.cmb_theme.setMinimumWidth(220)
        theme_view = QListView(self.cmb_theme)
        theme_view.setUniformItemSizes(True)
        theme_view.setAutoScroll(False)
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

        # Token Limits
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

        # Data Safety
        self.chk_preserve_unknown = QCheckBox("Preserve invalid token data (recommended)")
        self.chk_preserve_unknown.setChecked(True)
        self.chk_preserve_unknown.stateChanged.connect(self.on_preserve_toggle)
        self.chk_unlock_profile_alias_16 = QCheckBox("Unlock profile alias editing up to 16 characters")
        self.chk_unlock_profile_alias_16.setChecked(bool(getattr(self, "unlock_profile_alias_16", False)))
        self.chk_unlock_profile_alias_16.stateChanged.connect(self.on_toggle_profile_alias_unlock)
        self.lbl_profile_alias_safety = QLabel(
            "Game save creation uses 7 characters. Aliases up to 16 are currently allowed; longer aliases are treated as unsafe."
        )
        self.lbl_profile_alias_safety.setObjectName("mutedLabel")
        self.lbl_profile_alias_safety.setWordWrap(True)
        self.btn_clear_unknown = QPushButton("Clear invalid token data")
        self.btn_clear_unknown.clicked.connect(self.on_clear_unknown_confirm)
        self.lbl_type_safety = QLabel(
            f"Real token types are {SAFE_TYPE_MIN}-{SAFE_TYPE_MAX} (engine enum ePossibleMarker). "
            "IDs above that do not exist in the game: they are invisible and only waste belt slots."
        )
        self.lbl_type_safety.setObjectName("mutedLabel")
        self.lbl_type_safety.setWordWrap(True)

        layout.addWidget(self._build_settings_group("Data Safety", [
            self.chk_preserve_unknown,
            self.chk_unlock_profile_alias_16,
            self.lbl_profile_alias_safety,
            self.btn_clear_unknown,
            self.lbl_type_safety,
        ]))

        # Display
        self.chk_show_integrity = QCheckBox("Show integrity panel on Profile")
        self.chk_show_integrity.setChecked(bool(self.show_integrity_panel))
        self.chk_show_integrity.stateChanged.connect(self.on_toggle_show_integrity)
        layout.addWidget(self._build_settings_group("Display", [
            self.chk_show_integrity,
        ]))

        # Diagnostics
        self.chk_show_technical_card_details = QCheckBox(
            "Show technical details on Garage, Tuning, and Builds cards"
        )
        self.chk_show_technical_card_details.setChecked(bool(self.show_technical_card_details))
        self.chk_show_technical_card_details.stateChanged.connect(self.on_toggle_technical_card_details)
        self.chk_show_garage_allocator_diagnostics = QCheckBox("Show allocator diagnostics on the Garage page")
        self.chk_show_garage_allocator_diagnostics.setChecked(bool(self.show_garage_allocator_diagnostics))
        self.chk_show_garage_allocator_diagnostics.stateChanged.connect(self.on_toggle_garage_allocator_diagnostics)
        self.chk_show_tuning_raw_diagnostics = QCheckBox("Show raw diagnostics on the Tuning page")
        self.chk_show_tuning_raw_diagnostics.setChecked(bool(self.show_tuning_raw_diagnostics))
        self.chk_show_tuning_raw_diagnostics.stateChanged.connect(self.on_toggle_tuning_raw_diagnostics)

        layout.addWidget(self._build_settings_group("Diagnostics", [
            self.chk_show_technical_card_details,
            self.chk_show_garage_allocator_diagnostics,
            self.chk_show_tuning_raw_diagnostics,
        ]))

        # Catalog
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

        self.btn_load_preset = QPushButton("Import Tokens")
        self.btn_save_preset = QPushButton("Export Tokens")
        self.btn_export_have = QPushButton("Export Current Tokens")
        self.btn_load_preset.clicked.connect(self.on_load_preset)
        self.btn_save_preset.clicked.connect(self.on_save_preset)
        self.btn_export_have.clicked.connect(self.on_export_have)

        legacy_hint = QLabel(
            "Legacy token preset actions are kept here for compatibility. Main build workflows now live in Builds."
        )
        legacy_hint.setObjectName("mutedLabel")
        legacy_hint.setWordWrap(True)
        legacy_row = QHBoxLayout()
        legacy_row.setSpacing(8)
        legacy_row.addWidget(self.btn_load_preset)
        legacy_row.addWidget(self.btn_save_preset)
        legacy_row.addWidget(self.btn_export_have)
        legacy_row.addStretch(1)
        layout.addWidget(self._build_settings_group("Legacy Tools", [
            legacy_hint,
            legacy_row,
        ]))

        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

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

        ver = QLabel(f"{APP_VERSION} - {APP_PLATFORM}")
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
            "  Ctrl+O  Open save - Ctrl+S  Save + backup - Ctrl+Z  Reset Want\n\n"
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
        self.btn_third_party_notices = QPushButton("Open-source software")
        self.btn_third_party_notices.clicked.connect(self._open_third_party_notices)
        btn_row.addWidget(self.btn_third_party_notices)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        return w

    def _open_third_party_notices(self) -> None:
        """Show concise open-source notices without exposing raw package files."""
        self._build_open_source_dialog().exec()

    def _build_open_source_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("openSourceDialog")
        dialog.setWindowTitle("Open-source software")
        dialog.setModal(True)
        dialog.setMinimumSize(620, 500)
        dialog.resize(660, 540)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        title = QLabel("Open-source software")
        title.setObjectName("aboutTitle")
        root.addWidget(title)

        intro = QLabel(
            "NFS MW Save Editor uses Qt and PySide6 under the GNU LGPL v3. "
            "You may replace and relink those libraries. Full license texts, "
            "source information, and relinking instructions are included with "
            "every packaged build."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(intro)

        components = (
            (
                "Qt / PySide6 / shiboken6 6.10.1",
                "GNU Lesser General Public License v3",
                (("Qt licensing", "https://doc.qt.io/qt-6/licensing.html"),),
            ),
            (
                "Python 3.13.14",
                "Python Software Foundation License",
                (("Python license", "https://docs.python.org/3.13/license.html"),),
            ),
            (
                "NumPy 2.5.1",
                "BSD 3-Clause License",
                (("NumPy license", "https://numpy.org/doc/stable/license.html"),),
            ),
            (
                "PyInstaller 6.18.0",
                "GPL v2 or later with the PyInstaller bootloader exception",
                (("PyInstaller license", "https://pyinstaller.org/en/stable/license.html"),),
            ),
        )
        for component, license_name, links in components:
            frame = QFrame()
            frame.setObjectName("settingsGroup")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)
            frame_layout.setSpacing(5)

            component_label = QLabel(component)
            component_label.setObjectName("settingsGroupTitle")
            frame_layout.addWidget(component_label)

            detail_row = QHBoxLayout()
            detail_row.setSpacing(8)
            license_label = QLabel(license_name)
            license_label.setObjectName("mutedLabel")
            license_label.setWordWrap(True)
            detail_row.addWidget(license_label, 1)
            for link_text, url in links:
                link_button = QPushButton(link_text)
                link_button.setObjectName("openSourceLink")
                link_button.clicked.connect(
                    lambda _checked=False, target=url: QDesktopServices.openUrl(QUrl(target))
                )
                detail_row.addWidget(link_button)
            frame_layout.addLayout(detail_row)
            root.addWidget(frame)

        root.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        license_texts_button = buttons.addButton(
            "License texts", QDialogButtonBox.ButtonRole.ActionRole
        )
        license_texts_button.setObjectName("viewLicenseTexts")
        license_texts_button.clicked.connect(
            lambda: self._build_license_text_dialog(dialog).exec()
        )
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        apply_popup_theme(dialog, self.theme_name)
        return dialog

    def _build_license_text_dialog(self, parent: QWidget | None = None) -> QDialog:
        dialog = QDialog(parent or self)
        dialog.setObjectName("licenseTextDialog")
        dialog.setWindowTitle("License texts")
        dialog.setModal(True)
        dialog.setMinimumSize(720, 560)
        dialog.resize(780, 640)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(10)

        title = QLabel("Bundled license texts")
        title.setObjectName("aboutTitle")
        root.addWidget(title)

        intro = QLabel(
            "These are the complete local notices and license texts distributed "
            "with this copy of the application."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        selector = QComboBox()
        selector.setObjectName("licenseDocumentSelector")
        for document_title, path_parts in OPEN_SOURCE_DOCUMENTS:
            selector.addItem(document_title, path_parts)
        root.addWidget(selector)

        viewer = QTextBrowser()
        viewer.setObjectName("licenseTextViewer")
        viewer.setReadOnly(True)
        viewer.setOpenExternalLinks(True)
        root.addWidget(viewer, 1)

        def show_document(index: int) -> None:
            path_parts = selector.itemData(index)
            path = resource_path(*path_parts)
            try:
                content = path.read_text(encoding="utf-8")
                if path.suffix.lower() == ".md":
                    viewer.setMarkdown(content)
                else:
                    viewer.setPlainText(content)
            except OSError as exc:
                viewer.setPlainText(f"Could not read the bundled document:\n{exc}")
            viewer.moveCursor(QTextCursor.MoveOperation.Start)

        selector.currentIndexChanged.connect(show_document)
        show_document(0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        apply_popup_theme(dialog, self.theme_name)
        return dialog
