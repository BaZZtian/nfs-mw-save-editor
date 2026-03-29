from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ui.pages.constants import APP_NAME


@dataclass(frozen=True)
class ThemePreset:
    name: str
    accent: str
    background: str
    foreground: str
    tokens: dict[str, str] | None = None


DEFAULT_THEME_NAME = "Blueprint"
_SETTINGS_FILENAME = "ui_settings.json"

THEME_PRESETS: dict[str, ThemePreset] = {
    "Ayu": ThemePreset("Ayu", "#E6B450", "#0B0E14", "#BFBDB6"),
    "Blueprint": ThemePreset(
        "Blueprint",
        "#4A6B94",
        "#0B0F15",
        "#EAF0FA",
        tokens={
            "ACCENT": "#4A6B94",
            "ACCENT_BRIGHT": "#6F93C4",
            "ACCENT_SOFT": "#1A2536",
            "BG": "#0B0F15",
            "BG_PANEL": "#111828",
            "BG_CARD": "#131C2C",
            "TEXT": "#EAF0FA",
            "MUTED": "#94A4BC",
            "BORDER": "#27344A",
            "BG_INPUT": "#0F1524",
            "BG_BUTTON": "#141B2B",
            "BG_BUTTON_HOVER": "#1A2436",
            "BG_BUTTON_PRESS": "#121A28",
            "BG_NAV_ACTIVE": "#1B2740",
            "BG_NAV_HOVER": "#162133",
            "BORDER_NAV_ACTIVE": "#5878A3",
            "TEXT_NAV_ACTIVE": "#F3F7FF",
            "BG_BULK_BTN": "#152033",
            "BG_BULK_HOVER": "#1B2A42",
            "BG_DISABLED": "#111827",
            "CARD_HOVER_BG": "#182338",
            "CARD_HOVER_BORDER": "#3A5274",
            "CARD_CHANGED_BORDER": "#4A678E",
            "CARD_CHANGED_HOVER_BORDER": "#5E80AF",
            "CARD_CHANGED_BG": "rgba(74, 107, 148, 0.12)",
            "CARD_CHANGED_HOVER_BG": "rgba(111, 147, 196, 0.16)",
            "DISABLED_TEXT": "#6D7686",
            "DISABLED_BORDER": "#333C4B",
            "MUTED_DARK": "#6D7F98",
            "TOAST_SUCCESS_BG": "rgba(34, 84, 61, 0.92)",
            "TOAST_SUCCESS_BORDER": "#2D7A54",
            "TOAST_ERROR_BG": "rgba(120, 30, 30, 0.94)",
            "TOAST_ERROR_BORDER": "#D44444",
            "JUNKMAN_BG": "rgba(166, 227, 106, 0.14)",
            "JUNKMAN_BORDER": "#5E8F2E",
            "JUNKMAN_TEXT": "#A6E36A",
            "MAXED_BG": "rgba(232, 106, 95, 0.14)",
            "MAXED_BORDER": "#A64A42",
            "MAXED_TEXT": "#E86A5F",
            "LEVEL_SEG_LOW": "#3A5A82",
            "LEVEL_SEG_HIGH": "#5E80AF",
            "CAREER_SOURCE": "#7FA8E8",
            "CAREER_SOURCE_BORDER": "#4F73A8",
            "CAREER_SOURCE_BG": "rgba(79, 115, 168, 0.14)",
            "MY_CARS_SOURCE": "#B7A4F5",
            "MY_CARS_SOURCE_BORDER": "#6E5BA8",
            "MY_CARS_SOURCE_BG": "rgba(110, 91, 168, 0.14)",
            "GOLD": "#F08BB4",
            "GOLD_BORDER": "#B85B86",
            "GOLD_BG": "rgba(240, 139, 180, 0.14)",
            "ACTIVE_CAR": "#74D39A",
            "ACTIVE_CAR_BORDER": "#3E8A5D",
            "ACTIVE_CAR_BG": "rgba(62, 138, 93, 0.14)",
            "RADIUS_SM": "4px",
            "RADIUS_MD": "8px",
            "RADIUS_LG": "10px",
            "RADIUS_XL": "12px",
            "RADIUS_PILL": "14px",
        },
    ),
    "Catppuccin": ThemePreset("Catppuccin", "#CBA6F7", "#1E1E2E", "#CDD6F4"),
    "Claude": ThemePreset("Claude", "#CC7D5E", "#2D2D2B", "#F9F9F7"),
    "Codex": ThemePreset("Codex", "#0169CC", "#111111", "#FCFCFC"),
    "Dracula": ThemePreset("Dracula", "#FF79C6", "#282A36", "#F8F8F2"),
    "Everforest": ThemePreset("Everforest", "#A7C080", "#2D353B", "#D3C6AA"),
    "GitHub": ThemePreset("GitHub", "#1F6FEB", "#0D1117", "#E6EDF3"),
    "Gruvbox": ThemePreset("Gruvbox", "#458588", "#282828", "#EBDBB2"),
    "Linear": ThemePreset("Linear", "#5E6AD2", "#17181D", "#E6E9EF"),
    "Lobster": ThemePreset("Lobster", "#FF5C5C", "#111827", "#E4E4E7"),
    "Material": ThemePreset("Material", "#80CBC4", "#212121", "#EEFFFF"),
    "Matrix": ThemePreset("Matrix", "#1EFF5A", "#040805", "#B8FFCA"),
    "Monokai": ThemePreset("Monokai", "#99947C", "#272822", "#F8F8F2"),
    "Night Owl": ThemePreset("Night Owl", "#44596B", "#011627", "#D6DEEB"),
    "Nord": ThemePreset("Nord", "#88C0D0", "#2E3440", "#D8DEE9"),
    "Notion": ThemePreset("Notion", "#3183D8", "#191919", "#D9D9D8"),
    "One": ThemePreset("One", "#4D78CC", "#282C34", "#ABB2BF"),
    "Oscurance": ThemePreset("Oscurance", "#F9B98C", "#0B0B0F", "#E6E6E6"),
    "Rose Pine": ThemePreset("Rose Pine", "#EA9A97", "#232136", "#E0DEF4"),
    "Sentry": ThemePreset("Sentry", "#7055F6", "#2D2935", "#E6DFF9"),
    "Solarized": ThemePreset("Solarized", "#D30102", "#002B36", "#839496"),
    "Temple": ThemePreset("Temple", "#E4F222", "#02120C", "#C7E6DA"),
    "Tokyo Night": ThemePreset("Tokyo Night", "#3D59A1", "#1A1B26", "#A9B1D6"),
    "VS Code Plus": ThemePreset("VS Code Plus", "#007ACC", "#1E1E1E", "#D4D4D4"),
}


def _appdata_dir() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Roaming"


def _settings_path() -> Path:
    return _appdata_dir() / APP_NAME / _SETTINGS_FILENAME


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[idx:idx + 2], 16) for idx in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def _mix(color_a: str, color_b: str, amount_b: float) -> str:
    amount_b = max(0.0, min(1.0, amount_b))
    ar, ag, ab = _hex_to_rgb(color_a)
    br, bg, bb = _hex_to_rgb(color_b)
    mixed = (
        round(ar * (1.0 - amount_b) + br * amount_b),
        round(ag * (1.0 - amount_b) + bg * amount_b),
        round(ab * (1.0 - amount_b) + bb * amount_b),
    )
    return _rgb_to_hex(mixed)


def _rgba(color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(color)
    alpha = max(0.0, min(1.0, alpha))
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def _load_ui_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ui_settings(settings: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def available_theme_names() -> list[str]:
    return list(THEME_PRESETS.keys())


def get_theme_preset(theme_name: str | None) -> ThemePreset:
    if theme_name and theme_name in THEME_PRESETS:
        return THEME_PRESETS[theme_name]
    return THEME_PRESETS[DEFAULT_THEME_NAME]


def load_saved_theme_name() -> str:
    theme_name = _load_ui_settings().get("theme")
    if isinstance(theme_name, str) and theme_name in THEME_PRESETS:
        return theme_name
    return DEFAULT_THEME_NAME


def save_theme_name(theme_name: str) -> str:
    preset = get_theme_preset(theme_name)
    settings = _load_ui_settings()
    settings["theme"] = preset.name
    _save_ui_settings(settings)
    return preset.name


def _build_style_tokens(preset: ThemePreset) -> dict[str, str]:
    if preset.tokens is not None:
        return dict(preset.tokens)

    accent = preset.accent
    bg = preset.background
    text = preset.foreground
    return {
        "ACCENT": accent,
        "ACCENT_BRIGHT": _mix(accent, text, 0.18),
        "ACCENT_SOFT": _mix(bg, accent, 0.25),
        "BG": bg,
        "BG_PANEL": _mix(bg, text, 0.05),
        "BG_CARD": _mix(bg, text, 0.07),
        "TEXT": text,
        "MUTED": _mix(text, bg, 0.38),
        "BORDER": _mix(bg, text, 0.16),
        "BG_INPUT": _mix(bg, text, 0.03),
        "BG_BUTTON": _mix(bg, text, 0.06),
        "BG_BUTTON_HOVER": _mix(bg, text, 0.10),
        "BG_BUTTON_PRESS": _mix(bg, text, 0.02),
        "BG_NAV_ACTIVE": _mix(bg, accent, 0.18),
        "BG_NAV_HOVER": _mix(bg, text, 0.08),
        "BORDER_NAV_ACTIVE": _mix(accent, text, 0.12),
        "TEXT_NAV_ACTIVE": _mix(text, accent, 0.06),
        "BG_BULK_BTN": _mix(bg, accent, 0.12),
        "BG_BULK_HOVER": _mix(bg, accent, 0.18),
        "BG_DISABLED": _mix(bg, text, 0.04),
        "CARD_HOVER_BG": _rgba(accent, 0.12),
        "CARD_HOVER_BORDER": _mix(accent, text, 0.10),
        "CARD_CHANGED_BORDER": _mix(accent, text, 0.06),
        "CARD_CHANGED_HOVER_BORDER": _mix(accent, text, 0.18),
        "CARD_CHANGED_BG": _rgba(accent, 0.12),
        "CARD_CHANGED_HOVER_BG": _rgba(_mix(accent, text, 0.18), 0.16),
        "DISABLED_TEXT": _mix(text, bg, 0.60),
        "DISABLED_BORDER": _mix(bg, text, 0.10),
        "MUTED_DARK": _mix(text, bg, 0.52),
        "TOAST_SUCCESS_BG": "rgba(34, 84, 61, 0.92)",
        "TOAST_SUCCESS_BORDER": "#2D7A54",
        "TOAST_ERROR_BG": "rgba(120, 30, 30, 0.94)",
        "TOAST_ERROR_BORDER": "#D44444",
        "JUNKMAN_BG": "rgba(166, 227, 106, 0.14)",
        "JUNKMAN_BORDER": "#5E8F2E",
        "JUNKMAN_TEXT": "#A6E36A",
        "MAXED_BG": "rgba(232, 106, 95, 0.14)",
        "MAXED_BORDER": "#A64A42",
        "MAXED_TEXT": "#E86A5F",
        "LEVEL_SEG_LOW": _mix(accent, bg, 0.35),
        "LEVEL_SEG_HIGH": _mix(accent, text, 0.18),
        "CAREER_SOURCE": "#7FA8E8",
        "CAREER_SOURCE_BORDER": "#4F73A8",
        "CAREER_SOURCE_BG": "rgba(79, 115, 168, 0.14)",
        "MY_CARS_SOURCE": "#B7A4F5",
        "MY_CARS_SOURCE_BORDER": "#6E5BA8",
        "MY_CARS_SOURCE_BG": "rgba(110, 91, 168, 0.14)",
        "GOLD": "#F08BB4",
        "GOLD_BORDER": "#B85B86",
        "GOLD_BG": "rgba(240, 139, 180, 0.14)",
        "ACTIVE_CAR": "#74D39A",
        "ACTIVE_CAR_BORDER": "#3E8A5D",
        "ACTIVE_CAR_BG": "rgba(62, 138, 93, 0.14)",
        "RADIUS_SM": "4px",
        "RADIUS_MD": "8px",
        "RADIUS_LG": "10px",
        "RADIUS_XL": "12px",
        "RADIUS_PILL": "14px",
    }


STYLE_TEMPLATE = """
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', 'Bahnschrift', sans-serif;
    font-size: 12.5px;
}}
QMainWindow {{ background-color: {BG}; }}
QLabel {{ color: {TEXT}; }}
QLabel#mutedLabel {{ background: transparent; color: {MUTED}; }}
QLabel#sectionLabel {{
    color: {TEXT};
    font-size: 14px;
    font-weight: 700;
    margin-top: 4px;
}}
QLabel#gridSectionLabel {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 700;
    padding: 8px 4px 2px 4px;
    border-bottom: 1px solid {BORDER};
    margin-bottom: 2px;
}}
QFrame#sectionLine {{
    background: {BORDER};
    max-height: 1px;
}}
QLabel#pillLabel {{
    background: {ACCENT_SOFT};
    color: {ACCENT_BRIGHT};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS_PILL};
    padding: 6px 12px;
    font-weight: 600;
}}

/* Buttons */
QPushButton {{
    background-color: {BG_BUTTON};
    color: {TEXT};
    border: 1px solid {ACCENT_SOFT};
    border-radius: {RADIUS_MD};
    padding: 8px 12px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {BG_BUTTON_HOVER}; }}
QPushButton:pressed {{ background-color: {BG_BUTTON_PRESS}; }}
QPushButton:disabled {{ color: {DISABLED_TEXT}; border-color: {DISABLED_BORDER}; }}
QPushButton:checked {{
    background: {ACCENT};
    color: {TEXT};
    border-color: {ACCENT_BRIGHT};
}}
QPushButton#navButton {{
    background: transparent;
    text-align: left;
    padding: 8px 14px;
    border: 1px solid transparent;
    border-radius: 10px;
    min-height: 36px;
}}
QPushButton#navButton:checked {{
    background: {BG_NAV_ACTIVE};
    border: 1px solid {BORDER_NAV_ACTIVE};
    color: {TEXT_NAV_ACTIVE};
}}
QPushButton#navButton:hover {{
    background: {BG_NAV_HOVER};
}}
QPushButton#catButton {{
    padding: 6px 12px;
    min-height: 28px;
    text-align: left;
}}
QPushButton#cardBtn {{
    padding: 0px;
    min-height: 24px;
    min-width: 24px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#partsLevelBtn {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    padding: 0px;
    min-height: 24px;
    min-width: 24px;
    border-radius: 6px;
    color: {TEXT};
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#partsLevelBtn:hover {{
    background: {BG_BUTTON_HOVER};
    border-color: {ACCENT};
}}
QPushButton#partsLevelBtn:pressed {{
    background: {BG_BUTTON_PRESS};
    border-color: {ACCENT_BRIGHT};
}}
QPushButton#partsLevelBtn:disabled {{
    background: {BG_DISABLED};
    border-color: {DISABLED_BORDER};
    color: {MUTED_DARK};
}}
QPushButton#iconBtn {{
    padding: 0px 0px;
    min-height: 24px;
}}

/* Token Card */
QWidget#tokenCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
    padding: 0px;
}}
QWidget#tokenCard[changed="true"] {{
    border: 1px solid {CARD_CHANGED_BORDER};
    background: {CARD_CHANGED_BG};
}}
QWidget#tokenCard[hovered="true"] {{
    border: 1px solid {CARD_HOVER_BORDER};
    background: {CARD_HOVER_BG};
}}
QWidget#tokenCard[changed="true"][hovered="true"] {{
    border: 1px solid {CARD_CHANGED_HOVER_BORDER};
    background: {CARD_CHANGED_HOVER_BG};
}}
QWidget#tokenCard QLabel#haveLabel {{
    color: {MUTED};
    font-size: 11px;
}}
QWidget#tokenCard QLineEdit#cardName {{
    background: transparent;
    border: none;
    padding: 2px 4px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
}}
QWidget#tokenCard QSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 2px 4px;
    font-size: 12px;
}}

/* Slider */
QSlider#cardSlider::groove:horizontal {{
    background: {BORDER};
    height: 6px;
    border-radius: 3px;
}}
QSlider#cardSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QSlider#cardSlider::handle:horizontal:hover {{
    background: {ACCENT_BRIGHT};
}}
QSlider#cardSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* Legacy TokenRow (compat) */
QWidget#tokenRow {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG};
}}
QWidget#tokenRow[changed="true"] {{
    border: 1px solid {ACCENT};
    background: {CARD_CHANGED_BG};
}}
QLabel#haveLabel {{
    color: {MUTED};
    font-size: 11.5px;
}}
QWidget#tokenRow QLineEdit {{
    background: transparent;
    border: none;
    padding: 4px 6px;
}}
QWidget#tokenRow QSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
}}

/* Inputs */
QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px;
    border: 0px;
    background: transparent;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow {{ width: 8px; height: 8px; }}
QComboBox {{
    background: {BG_BUTTON};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 7px 12px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
    background: {BG_BUTTON_HOVER};
}}
QComboBox:focus {{
    border-color: {ACCENT_BRIGHT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {BG_NAV_ACTIVE};
    selection-color: {TEXT};
    outline: 0;
}}

/* Scroll */
QScrollArea {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG};
    background: {BG_PANEL};
}}
QScrollArea#cardScroll {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
    background: {BG};
}}

/* Misc */
QToolButton {{
    background-color: {BG_BUTTON};
    color: {TEXT};
    border: 1px solid {ACCENT_SOFT};
    border-radius: {RADIUS_MD};
    padding: 8px 12px;
}}
QLabel#unsavedLabel {{
    color: {ACCENT_BRIGHT};
    font-weight: 600;
    padding-left: 6px;
}}
QLabel#filePath {{
    color: {TEXT};
}}
QMenu {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: {TEXT};
}}
QScrollBar:vertical {{
    background: {BG_PANEL};
    width: 12px;
    margin: 2px 0 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT};
    min-height: 20px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_BRIGHT}; }}
QCheckBox {{
    spacing: 6px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    background: {BG_PANEL};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT_BRIGHT};
}}

/* Progress Bar */
QProgressBar#tokenProgress {{
    background: {BORDER};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    text-align: center;
    color: {TEXT};
    font-size: 10px;
    font-weight: 600;
}}
QProgressBar#tokenProgress::chunk {{
    background: {ACCENT};
    border-radius: {RADIUS_MD};
}}

/* Empty State Overlay */
QWidget#emptyOverlay {{
    background: transparent;
}}
QLabel#emptyTitle {{
    color: {MUTED};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#emptyHint {{
    color: {MUTED_DARK};
    font-size: 13px;
}}

/* Toast Notifications */
QLabel#toastSuccess {{
    background: {TOAST_SUCCESS_BG};
    color: {TEXT};
    border: 1px solid {TOAST_SUCCESS_BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#toastError {{
    background: {TOAST_ERROR_BG};
    color: {TEXT};
    border: 1px solid {TOAST_ERROR_BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
}}

/* Stat Tiles (Profile summary strip) */
QFrame#statTile {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
    padding: 0px;
}}
QLabel#statTileHeading {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel#statTileValue {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 4px 12px;
    color: {ACCENT_BRIGHT};
    font-size: 18px;
    font-weight: 700;
}}
QLineEdit#statTileEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 4px 8px;
    font-size: 16px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#statTileSub {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 10.5px;
}}

/* Garage Car Cards */
QFrame#garageCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
}}
QFrame#garageCard[changed="true"] {{
    border: 1px solid {CARD_CHANGED_BORDER};
    background: {CARD_CHANGED_BG};
}}
QFrame#garageCard[occupied="false"] {{
    opacity: 0.6;
}}
QFrame#partsCard {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
}}
QFrame#partsCard[changed="true"] {{
    border: 1px solid {CARD_CHANGED_BORDER};
    background: {CARD_CHANGED_BG};
}}
/* Parts level bar rows */
QWidget#partsLevelRow {{
    background: transparent;
}}
QLabel#partsLevelLabel {{
    background: transparent;
    color: {MUTED};
    font-size: 10.5px;
    font-weight: 600;
    min-width: 80px;
}}
QLabel#partsLevelNum {{
    background: transparent;
    color: {TEXT};
    font-size: 11px;
    font-weight: 700;
    min-width: 18px;
}}
QSpinBox#partsLevelSpin {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 6px;
    min-width: 52px;
    color: {TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QSpinBox#partsLevelSpin:disabled {{
    color: {MUTED};
    background: {BG_DISABLED};
}}
QFrame#partsLevelSeg {{
    background: {BG_INPUT};
    border: 1px solid {ACCENT_SOFT};
    border-radius: 2px;
    min-width: 18px;
    min-height: 8px;
    max-height: 8px;
}}
QFrame#partsLevelSeg[filled="1"] {{
    background: {LEVEL_SEG_LOW};
    border-color: {LEVEL_SEG_LOW};
}}
QFrame#partsLevelSeg[filled="2"] {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QFrame#partsLevelSeg[filled="3"] {{
    background: {LEVEL_SEG_HIGH};
    border-color: {LEVEL_SEG_HIGH};
}}
QFrame#partsLevelSeg[filled="4"] {{
    background: {ACCENT_BRIGHT};
    border-color: {ACCENT_BRIGHT};
}}
/* Junkman accent badges */
QLabel#partsJunkmanActive {{
    background: {JUNKMAN_BG};
    border: 1px solid {JUNKMAN_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {JUNKMAN_TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#partsJunkmanNone {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#partsJunkmanToggle {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#partsJunkmanToggle[active="true"] {{
    background: {JUNKMAN_BG};
    border: 1px solid {JUNKMAN_BORDER};
    color: {JUNKMAN_TEXT};
}}
QPushButton#partsJunkmanToggle:disabled {{
    background: {BG_DISABLED};
    border-color: {BORDER};
    color: {MUTED_DARK};
}}
QPushButton#partsBulkBtn {{
    background: {BG_BULK_BTN};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 5px 10px;
    color: {TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#partsBulkBtn:hover {{
    background: {BG_BULK_HOVER};
    border-color: {ACCENT};
}}
QPushButton#partsBulkBtn:disabled {{
    background: {BG_DISABLED};
    border-color: {BORDER};
    color: {MUTED_DARK};
}}
QLabel#garageCardSlot {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 10.5px;
    font-weight: 600;
}}
QLabel#garageCardMeta {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 4px 9px;
    color: {TEXT};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#garageCardFieldLabel {{
    background: transparent;
    color: {MUTED};
    font-size: 10.5px;
    font-weight: 600;
}}
QFrame#garageCardSep {{
    color: {BORDER};
}}
QLineEdit#garageCardEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 5px 8px;
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#garageCardCurrent {{
    background: transparent;
    color: {MUTED};
    font-size: 10.5px;
}}
QLabel#partsCardRaw {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 7px 10px;
    color: {TEXT};
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    font-size: 11.5px;
    font-weight: 600;
}}
QLabel#partsCardNote {{
    background: transparent;
    color: {MUTED};
    font-size: 10.5px;
}}
QLabel#garageCardStatBadge {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusStock {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusModified {{
    background: rgba(79, 115, 168, 0.14);
    border: 1px solid {CAREER_SOURCE_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {CAREER_SOURCE};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusMaxed {{
    background: {MAXED_BG};
    border: 1px solid {MAXED_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MAXED_TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusJunkman {{
    background: {JUNKMAN_BG};
    border: 1px solid {JUNKMAN_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {JUNKMAN_TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#pinkSlipBadgeText {{
    background: {GOLD_BG};
    border: 1px solid {GOLD_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {GOLD};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#careerSourceBadge {{
    background: {CAREER_SOURCE_BG};
    border: 1px solid {CAREER_SOURCE_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {CAREER_SOURCE};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#myCarsSourceBadge {{
    background: {MY_CARS_SOURCE_BG};
    border: 1px solid {MY_CARS_SOURCE_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {MY_CARS_SOURCE};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#activeCarBadge {{
    background: {ACTIVE_CAR_BG};
    border: 1px solid {ACTIVE_CAR_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {ACTIVE_CAR};
    font-size: 11px;
    font-weight: 600;
}}

/* Settings Page Group Cards */
QFrame#settingsGroup {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
}}
QLabel#settingsGroupTitle {{
    background: transparent;
    color: {TEXT};
    font-size: 13px;
    font-weight: 700;
}}
QFrame#settingsGroup QCheckBox {{
    background: transparent;
}}
QFrame#settingsGroup QPushButton {{
    background-color: {BG_BUTTON};
}}
QWidget#themePreviewRow {{
    background: transparent;
}}
QLabel#themePreviewLabel {{
    background: transparent;
    color: {MUTED};
    font-size: 10.5px;
    font-weight: 600;
}}
QLabel#themePreviewValue {{
    background: transparent;
    color: {TEXT};
    font-size: 12px;
    font-weight: 700;
}}
QFrame#themePreviewSwatch {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}
QLabel#themeHint {{
    background: transparent;
    color: {MUTED};
    font-size: 11px;
}}

/* About Page */
QLabel#aboutTitle {{
    color: {TEXT};
    font-size: 18px;
    font-weight: 700;
}}
QFrame#separator {{
    color: {BORDER};
    max-height: 1px;
}}
"""


def build_stylesheet(theme_name: str | None = None) -> str:
    preset = get_theme_preset(theme_name)
    return STYLE_TEMPLATE.format_map(_build_style_tokens(preset))


def apply_theme(app, theme_name: str | None = None) -> str:
    """Apply the selected UI theme and return the resolved preset name."""
    preset = get_theme_preset(theme_name or load_saved_theme_name())
    app.setProperty("themeName", preset.name)
    app.setStyleSheet(build_stylesheet(preset.name))
    return preset.name
