from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from ui.pages.constants import APP_NAME


@dataclass(frozen=True)
class ThemePreset:
    name: str
    accent: str
    background: str
    foreground: str
    tokens: dict[str, str] | None = None
    text_on_accent_mode: Literal["auto", "light", "dark"] = "auto"


DEFAULT_THEME_NAME = "Blueprint"
_SETTINGS_FILENAME = "ui_settings.json"
_SCOPED_POPUP_THEME_APPLYING_PROPERTY = "_scopedPopupThemeApplying"

THEME_PRESETS: dict[str, ThemePreset] = {
    "Ayu": ThemePreset("Ayu", "#E6B450", "#0B0E14", "#BFBDB6"),
    "Banana": ThemePreset(
        "Banana",
        "#F0C441",
        "#2E2E15",
        "#F5E6C4",
        text_on_accent_mode="dark",
    ),
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
            "LEVEL_SEG_LOW": "#3A5A82",
            "LEVEL_SEG_HIGH": "#5E80AF",
            "RADIUS_SM": "4px",
            "RADIUS_MD": "8px",
            "RADIUS_LG": "10px",
            "RADIUS_XL": "12px",
            "RADIUS_PILL": "14px",
        },
    ),
    "Catppuccin": ThemePreset(
        "Catppuccin",
        "#CBA6F7",
        "#1E1E2E",
        "#CDD6F4",
        text_on_accent_mode="dark",
    ),
    "Cherry": ThemePreset("Cherry", "#A61E3C", "#2A0F18", "#FBE9EE", text_on_accent_mode="light"),
    "Claude": ThemePreset("Claude", "#CC7D5E", "#2D2D2B", "#F9F9F7"),
    "Codex": ThemePreset("Codex", "#0169CC", "#111111", "#FCFCFC"),
    "Dracula": ThemePreset("Dracula", "#FF79C6", "#282A36", "#F8F8F2"),
    "Everforest": ThemePreset(
        "Everforest",
        "#A7C080",
        "#2D353B",
        "#D3C6AA",
        text_on_accent_mode="dark",
    ),
    "GitHub": ThemePreset("GitHub", "#1F6FEB", "#0D1117", "#E6EDF3"),
    "Gruvbox": ThemePreset("Gruvbox", "#458588", "#282828", "#EBDBB2"),
    "Kiwi": ThemePreset(
        "Kiwi",
        "#7CB342",
        "#141A14",
        "#E8F0E4",
        text_on_accent_mode="dark",
    ),
    "Linear": ThemePreset("Linear", "#5E6AD2", "#17181D", "#E6E9EF"),
    "Lobster": ThemePreset("Lobster", "#FF5C5C", "#111827", "#E4E4E7"),
    "Mango": ThemePreset("Mango", "#E3A43A", "#0F200F", "#FFF0D8", text_on_accent_mode="light"),
    "Material": ThemePreset("Material", "#80CBC4", "#212121", "#EEFFFF"),
    "Matrix": ThemePreset("Matrix", "#66d98a", "#0d1210", "#e4ece6"),
    "Monokai": ThemePreset("Monokai", "#99947C", "#272822", "#F8F8F2"),
    "Night Owl": ThemePreset("Night Owl", "#44596B", "#011627", "#D6DEEB"),
    "Nord": ThemePreset(
        "Nord",
        "#88C0D0",
        "#2E3440",
        "#D8DEE9",
        text_on_accent_mode="dark",
    ),
    "Notion": ThemePreset("Notion", "#3183D8", "#191919", "#D9D9D8"),
    "One": ThemePreset("One", "#4D78CC", "#282C34", "#ABB2BF"),
    "Oscurance": ThemePreset(
        "Oscurance",
        "#F9B98C",
        "#0B0B0F",
        "#E6E6E6",
        text_on_accent_mode="dark",
    ),
    "Raycast": ThemePreset("Raycast", "#FF6363", "#101010", "#FEFEFE"),
    "Rose Pine": ThemePreset(
        "Rose Pine",
        "#EA9A97",
        "#232136",
        "#E0DEF4",
        text_on_accent_mode="dark",
    ),
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


def _relative_luminance(color: str) -> float:
    def _channel(value: int) -> float:
        normalized = value / 255.0
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    r, g, b = _hex_to_rgb(color)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast_ratio(color_a: str, color_b: str) -> float:
    lum_a = _relative_luminance(color_a)
    lum_b = _relative_luminance(color_b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def _hue_degrees(color: str) -> float:
    r, g, b = (channel / 255.0 for channel in _hex_to_rgb(color))
    max_channel = max(r, g, b)
    min_channel = min(r, g, b)
    delta = max_channel - min_channel
    if delta == 0:
        return 0.0
    if max_channel == r:
        hue = 60.0 * (((g - b) / delta) % 6.0)
    elif max_channel == g:
        hue = 60.0 * (((b - r) / delta) + 2.0)
    else:
        hue = 60.0 * (((r - g) / delta) + 4.0)
    return hue


def _saturation(color: str) -> float:
    r, g, b = (channel / 255.0 for channel in _hex_to_rgb(color))
    max_channel = max(r, g, b)
    if max_channel == 0:
        return 0.0
    min_channel = min(r, g, b)
    return (max_channel - min_channel) / max_channel


def _accent_seed(
    accent: str,
    bg: str,
    text: str,
    *,
    bg_pull: float = 0.0,
    text_pull: float = 0.0,
) -> str:
    seed = accent
    if bg_pull:
        seed = _mix(seed, bg, bg_pull)
    if text_pull:
        seed = _mix(seed, text, text_pull)
    return seed


def _derive_status_family(
    seed: str,
    bg: str,
    text: str,
    *,
    surface_mix: float = 0.15,
    border_mix: float = 0.34,
    text_mix: float = 0.46,
) -> dict[str, str]:
    return {
        "BG": _mix(bg, seed, surface_mix),
        "BORDER": _mix(bg, seed, border_mix),
        "FG": _mix(seed, text, text_mix),
    }


def _brand_aware_text_on_accent(accent: str, dark_ink: str) -> str:
    luminance = _relative_luminance(accent)
    hue = _hue_degrees(accent)
    saturation = _saturation(accent)
    if luminance >= 0.72:
        return dark_ink
    if luminance >= 0.50 and 35.0 <= hue <= 210.0 and saturation >= 0.28:
        return dark_ink
    return "#FFFFFF"


def _derive_semantic_status_tokens(tokens: dict[str, str]) -> dict[str, str]:
    accent = tokens["ACCENT"]
    bg = tokens["BG"]
    text = tokens["TEXT"]
    neutral_seed = tokens.get("MUTED", _mix(text, bg, 0.38))

    role_specs: dict[str, dict[str, str | float]] = {
        "STATUS_INFO": {
            "seed": _accent_seed(accent, bg, text, bg_pull=0.10, text_pull=0.04),
            "surface_mix": 0.10,
            "border_mix": 0.24,
            "text_mix": 0.30,
        },
        "STATUS_ALT_INFO": {
            "seed": _accent_seed(accent, bg, text, bg_pull=0.14, text_pull=0.02),
            "surface_mix": 0.13,
            "border_mix": 0.30,
            "text_mix": 0.34,
        },
        "STATUS_REWARD": {
            "seed": _accent_seed(accent, bg, text, text_pull=0.12),
            "surface_mix": 0.18,
            "border_mix": 0.46,
            "text_mix": 0.56,
        },
        "STATUS_ACTIVE": {
            "seed": _accent_seed(accent, bg, text, bg_pull=0.06, text_pull=0.08),
            "surface_mix": 0.15,
            "border_mix": 0.38,
            "text_mix": 0.48,
        },
        "STATUS_SUCCESS": {
            "seed": _accent_seed(accent, bg, text, bg_pull=0.04, text_pull=0.10),
            "surface_mix": 0.17,
            "border_mix": 0.40,
            "text_mix": 0.52,
        },
        "STATUS_WARNING": {
            "seed": _accent_seed(accent, bg, text, bg_pull=0.16),
            "surface_mix": 0.18,
            "border_mix": 0.38,
            "text_mix": 0.34,
        },
        "STATUS_NEUTRAL": {
            "seed": neutral_seed,
            "surface_mix": 0.10,
            "border_mix": 0.20,
            "text_mix": 0.28,
        },
        "STATUS_PENDING": {
            "seed": _accent_seed(accent, bg, text, text_pull=0.14),
            "surface_mix": 0.19,
            "border_mix": 0.44,
            "text_mix": 0.56,
        },
    }

    derived: dict[str, str] = {}
    for prefix, spec in role_specs.items():
        family = _derive_status_family(
            spec["seed"],
            bg,
            text,
            surface_mix=spec["surface_mix"],
            border_mix=spec["border_mix"],
            text_mix=spec["text_mix"],
        )
        for suffix, value in family.items():
            derived[f"{prefix}_{suffix}"] = value

    toast_success = _derive_status_family(
        _accent_seed(accent, bg, text, text_pull=0.14),
        bg,
        text,
        surface_mix=0.30,
        border_mix=0.56,
        text_mix=0.80,
    )
    toast_error = _derive_status_family(
        "#E37878",
        bg,
        text,
        surface_mix=0.28,
        border_mix=0.54,
        text_mix=0.80,
    )
    for suffix, value in toast_success.items():
        derived[f"TOAST_SUCCESS_{suffix}"] = value
    for suffix, value in toast_error.items():
        derived[f"TOAST_ERROR_{suffix}"] = value

    # Keep legacy semantic token names aligned with the new role-based families.
    derived.update({
        "JUNKMAN_BG": derived["STATUS_SUCCESS_BG"],
        "JUNKMAN_BORDER": derived["STATUS_SUCCESS_BORDER"],
        "JUNKMAN_TEXT": derived["STATUS_SUCCESS_FG"],
        "MAXED_BG": derived["STATUS_WARNING_BG"],
        "MAXED_BORDER": derived["STATUS_WARNING_BORDER"],
        "MAXED_TEXT": derived["STATUS_WARNING_FG"],
        "CAREER_SOURCE_BG": derived["STATUS_INFO_BG"],
        "CAREER_SOURCE_BORDER": derived["STATUS_INFO_BORDER"],
        "CAREER_SOURCE": derived["STATUS_INFO_FG"],
        "MY_CARS_SOURCE_BG": derived["STATUS_ALT_INFO_BG"],
        "MY_CARS_SOURCE_BORDER": derived["STATUS_ALT_INFO_BORDER"],
        "MY_CARS_SOURCE": derived["STATUS_ALT_INFO_FG"],
        "GOLD_BG": derived["STATUS_REWARD_BG"],
        "GOLD_BORDER": derived["STATUS_REWARD_BORDER"],
        "GOLD": derived["STATUS_REWARD_FG"],
        "ACTIVE_CAR_BG": derived["STATUS_ACTIVE_BG"],
        "ACTIVE_CAR_BORDER": derived["STATUS_ACTIVE_BORDER"],
        "ACTIVE_CAR": derived["STATUS_ACTIVE_FG"],
    })
    return derived


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


def load_ui_setting(key: str, default=None):
    return _load_ui_settings().get(key, default)


def save_ui_setting(key: str, value):
    settings = _load_ui_settings()
    settings[key] = value
    _save_ui_settings(settings)
    return value


def available_theme_names() -> list[str]:
    return list(THEME_PRESETS.keys())


def get_theme_preset(theme_name: str | None) -> ThemePreset:
    if theme_name and theme_name in THEME_PRESETS:
        return THEME_PRESETS[theme_name]
    return THEME_PRESETS[DEFAULT_THEME_NAME]


def load_saved_theme_name() -> str:
    theme_name = load_ui_setting("theme")
    if isinstance(theme_name, str) and theme_name in THEME_PRESETS:
        return theme_name
    return DEFAULT_THEME_NAME


def save_theme_name(theme_name: str) -> str:
    preset = get_theme_preset(theme_name)
    save_ui_setting("theme", preset.name)
    return preset.name


def _build_style_tokens(preset: ThemePreset) -> dict[str, str]:
    if preset.tokens is not None:
        tokens = dict(preset.tokens)
    else:
        accent = preset.accent
        bg = preset.background
        text = preset.foreground
        tokens = {
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
            "HEAT_SEGMENT_FILL": _rgba(text, 0.06),
            "HEAT_SEGMENT_ACTIVE_BG": _rgba(accent, 0.78),
            "DISABLED_TEXT": _mix(text, bg, 0.60),
            "DISABLED_BORDER": _mix(bg, text, 0.10),
            "MUTED_DARK": _mix(text, bg, 0.52),
            "LEVEL_SEG_LOW": _mix(accent, bg, 0.35),
            "LEVEL_SEG_HIGH": _mix(accent, text, 0.18),
            "RADIUS_SM": "4px",
            "RADIUS_MD": "8px",
            "RADIUS_LG": "10px",
            "RADIUS_XL": "12px",
            "RADIUS_PILL": "14px",
        }

    tokens.setdefault(
        "SCROLLBAR_THUMB_HOVER",
        _mix(tokens["BG_BUTTON_HOVER"], tokens["TEXT"], 0.12),
    )
    tokens.setdefault(
        "HEAT_SEGMENT_FILL",
        _rgba(tokens["TEXT"], 0.06),
    )
    tokens.setdefault(
        "HEAT_SEGMENT_ACTIVE_BG",
        _rgba(tokens["ACCENT"], 0.78),
    )
    dark_on_accent = _mix(tokens["BG"], "#000000", 0.36)
    if preset.text_on_accent_mode == "dark":
        tokens["TEXT_ON_ACCENT"] = dark_on_accent
    elif preset.text_on_accent_mode == "light":
        tokens["TEXT_ON_ACCENT"] = "#FFFFFF"
    else:
        tokens["TEXT_ON_ACCENT"] = _brand_aware_text_on_accent(
            tokens["ACCENT"],
            dark_on_accent,
        )
    tokens.update(_derive_semantic_status_tokens(tokens))
    return tokens


def resolve_theme_tokens(theme_name: str | None = None) -> dict[str, str]:
    resolved_name = theme_name
    if resolved_name is None:
        try:
            from PySide6.QtWidgets import QApplication
        except Exception:
            app = None
        else:
            app = QApplication.instance()
        if app is not None:
            app_theme = app.property("themeName")
            if isinstance(app_theme, str) and app_theme:
                resolved_name = app_theme
    preset = get_theme_preset(resolved_name or load_saved_theme_name())
    return _build_style_tokens(preset)


def _apply_theme_palette(app, tokens: dict[str, str]) -> None:
    try:
        from PySide6.QtGui import QColor, QPalette
    except Exception:
        return

    palette = app.palette()
    accent = QColor(tokens["ACCENT"])
    window = QColor(tokens["BG"])
    window_text = QColor(tokens["TEXT"])
    base = QColor(tokens["BG_INPUT"])
    alternate_base = QColor(tokens["BG_PANEL"])
    button = QColor(tokens["BG_BUTTON"])
    button_text = QColor(tokens["TEXT"])
    text = QColor(tokens["TEXT"])
    tooltip_base = QColor(tokens["BG_CARD"])
    tooltip_text = QColor(tokens["TEXT"])
    highlight = QColor(tokens["BG_NAV_ACTIVE"])
    highlighted_text = QColor(tokens["TEXT"])
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Accent, accent)
        palette.setColor(group, QPalette.ColorRole.Window, window)
        palette.setColor(group, QPalette.ColorRole.WindowText, window_text)
        palette.setColor(group, QPalette.ColorRole.Base, base)
        palette.setColor(group, QPalette.ColorRole.AlternateBase, alternate_base)
        palette.setColor(group, QPalette.ColorRole.Button, button)
        palette.setColor(group, QPalette.ColorRole.ButtonText, button_text)
        palette.setColor(group, QPalette.ColorRole.Text, text)
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, tooltip_base)
        palette.setColor(group, QPalette.ColorRole.ToolTipText, tooltip_text)
        palette.setColor(group, QPalette.ColorRole.Highlight, highlight)
        palette.setColor(group, QPalette.ColorRole.HighlightedText, highlighted_text)
    app.setPalette(palette)


_SCOPED_THEME_ACTIVE_PROPERTY = "_scopedThemeStylesActive"

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
    background: {STATUS_INFO_BG};
    color: {STATUS_INFO_FG};
    border: 1px solid {STATUS_INFO_BORDER};
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
    color: {TEXT_ON_ACCENT};
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
QPushButton#filterButton {{
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
QWidget#partsPerfControlHost {{
    background: transparent;
    border: none;
}}

/* Inputs */
QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: {TEXT_ON_ACCENT};
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
    border-color: {BORDER};
    background: {BG_BUTTON_HOVER};
}}
QComboBox:focus {{
    border-color: {BORDER};
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
    background: transparent;
    color: {STATUS_PENDING_FG};
    font-weight: 600;
    padding: 0px;
}}
QLabel#unsavedLabel[pending="true"] {{
    background: {STATUS_PENDING_BG};
    border: 1px solid {STATUS_PENDING_BORDER};
    border-radius: {RADIUS_PILL};
    color: {STATUS_PENDING_FG};
    padding: 0px;
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
    color: {TEXT_ON_ACCENT};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 0 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_BUTTON_HOVER};
    min-height: 24px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: {SCROLLBAR_THUMB_HOVER}; }}
QScrollBar::handle:vertical:pressed {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    background: transparent;
    border: none;
    height: 0px;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0 2px 0 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BG_BUTTON_HOVER};
    min-width: 24px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background: {SCROLLBAR_THUMB_HOVER}; }}
QScrollBar::handle:horizontal:pressed {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    background: transparent;
    border: none;
    width: 0px;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QScrollBar::up-arrow,
QScrollBar::down-arrow,
QScrollBar::left-arrow,
QScrollBar::right-arrow {{
    background: transparent;
    width: 0px;
    height: 0px;
}}
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
    font-size: 10px;
    font-weight: 600;
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
    color: {TOAST_SUCCESS_FG};
    border: 1px solid {TOAST_SUCCESS_BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QLabel#toastError {{
    background: {TOAST_ERROR_BG};
    color: {TOAST_ERROR_FG};
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
QFrame#pageControlsRow {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL};
    padding: 0px;
}}
QFrame#pageControlsRow QWidget#pageControlsSection {{
    background: transparent;
}}
QFrame#pageControlsRow QWidget#pageControlsSearchHost {{
    background: transparent;
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
QLineEdit#statTileEdit[invalid="true"] {{
    border: 1px solid {TOAST_ERROR_BORDER};
}}
QLabel#statTileSub[status="error"] {{
    color: {TOAST_ERROR_FG};
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
QFrame#garageCard QWidget#garageHeatRow {{
    background: transparent;
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
    background: {STATUS_SUCCESS_BG};
    border: 1px solid {STATUS_SUCCESS_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_SUCCESS_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#partsJunkmanNone {{
    background: {STATUS_NEUTRAL_BG};
    border: 1px solid {STATUS_NEUTRAL_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_NEUTRAL_FG};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#partsJunkmanToggle {{
    background: {STATUS_NEUTRAL_BG};
    border: 1px solid {STATUS_NEUTRAL_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_NEUTRAL_FG};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#partsJunkmanToggle[active="true"] {{
    background: {STATUS_SUCCESS_BG};
    border: 1px solid {STATUS_SUCCESS_BORDER};
    color: {STATUS_SUCCESS_FG};
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
    background: {STATUS_NEUTRAL_BG};
    border: 1px solid {STATUS_NEUTRAL_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_NEUTRAL_FG};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#heatBtn {{
    background: {HEAT_SEGMENT_FILL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 4px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#heatBtn:checked {{
    background: {HEAT_SEGMENT_ACTIVE_BG};
    border-color: {BORDER_NAV_ACTIVE};
    color: {TEXT_ON_ACCENT};
}}
QPushButton#heatBtn:hover:!checked {{
    background: {BG_BULK_HOVER};
    border-color: {ACCENT};
    color: {TEXT};
}}
QPushButton#heatBtn:disabled {{
    background: {BG_DISABLED};
    border-color: {BORDER};
    color: {MUTED_DARK};
}}
QLabel#tuningStatusStock {{
    background: {STATUS_NEUTRAL_BG};
    border: 1px solid {STATUS_NEUTRAL_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_NEUTRAL_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusModified {{
    background: {STATUS_INFO_BG};
    border: 1px solid {STATUS_INFO_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_INFO_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusMaxed {{
    background: {STATUS_WARNING_BG};
    border: 1px solid {STATUS_WARNING_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_WARNING_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusJunkman {{
    background: {STATUS_SUCCESS_BG};
    border: 1px solid {STATUS_SUCCESS_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_SUCCESS_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#tuningStatusReadOnly {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {TEXT};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#pinkSlipBadgeText {{
    background: {STATUS_REWARD_BG};
    border: 1px solid {STATUS_REWARD_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_REWARD_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#careerSourceBadge {{
    background: {STATUS_INFO_BG};
    border: 1px solid {STATUS_INFO_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_INFO_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#myCarsSourceBadge {{
    background: {STATUS_ALT_INFO_BG};
    border: 1px solid {STATUS_ALT_INFO_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_ALT_INFO_FG};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#activeCarBadge {{
    background: {STATUS_ACTIVE_BG};
    border: 1px solid {STATUS_ACTIVE_BORDER};
    border-radius: {RADIUS_MD};
    padding: 3px 8px;
    color: {STATUS_ACTIVE_FG};
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


@lru_cache(maxsize=None)
def _render_stylesheet(theme_name: str) -> str:
    return STYLE_TEMPLATE.format_map(resolve_theme_tokens(theme_name))


def build_stylesheet(theme_name: str | None = None) -> str:
    preset = get_theme_preset(theme_name or load_saved_theme_name())
    return _render_stylesheet(preset.name)


def build_shell_stylesheet(theme_name: str | None = None) -> str:
    return build_stylesheet(theme_name)


def build_page_stylesheet(theme_name: str | None = None) -> str:
    return build_stylesheet(theme_name)


def build_popup_stylesheet(theme_name: str | None = None) -> str:
    return build_stylesheet(theme_name)


def apply_theme_palette(app, theme_name: str | None = None) -> str:
    """Apply only app-level theme state and palette, without global QSS."""
    preset = get_theme_preset(theme_name or load_saved_theme_name())
    tokens = resolve_theme_tokens(preset.name)
    app.setProperty("themeName", preset.name)
    _apply_theme_palette(app, tokens)
    return preset.name


def apply_popup_theme(widget, theme_name: str | None = None) -> str:
    """Apply scoped popup styling to a dialog/toast root without touching app-wide QSS."""
    if widget is None:
        return theme_name or load_saved_theme_name()
    resolved_name = theme_name
    if not resolved_name:
        app = None
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None
        app_theme = app.property("themeName") if app is not None else None
        resolved_name = app_theme if isinstance(app_theme, str) and app_theme else load_saved_theme_name()
    if bool(widget.property(_SCOPED_POPUP_THEME_APPLYING_PROPERTY)):
        return resolved_name
    stylesheet = build_popup_stylesheet(resolved_name)
    applied_name = widget.property("_scopedThemeName")
    if applied_name == resolved_name and widget.styleSheet() == stylesheet:
        return resolved_name
    widget.setProperty(_SCOPED_POPUP_THEME_APPLYING_PROPERTY, True)
    try:
        widget.setStyleSheet(stylesheet)
        widget.setProperty("_scopedThemeName", resolved_name)
        return resolved_name
    finally:
        widget.setProperty(_SCOPED_POPUP_THEME_APPLYING_PROPERTY, False)


def ensure_scoped_theme_mode(app) -> bool:
    """Clear any app-wide stylesheet once and mark scoped-theme mode active."""
    had_global_stylesheet = bool(app.styleSheet())
    if had_global_stylesheet:
        app.setStyleSheet("")
    if had_global_stylesheet or not bool(app.property(_SCOPED_THEME_ACTIVE_PROPERTY)):
        app.setProperty(_SCOPED_THEME_ACTIVE_PROPERTY, True)
    return had_global_stylesheet


def apply_theme(app, theme_name: str | None = None) -> str:
    """Apply app-level theme state and switch the app into scoped-theme mode."""
    resolved_name = apply_theme_palette(app, theme_name)
    ensure_scoped_theme_mode(app)
    return resolved_name
