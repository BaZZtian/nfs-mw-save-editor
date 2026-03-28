from __future__ import annotations

ACCENT = "#4A6B94"
ACCENT_BRIGHT = "#6F93C4"
ACCENT_SOFT = "#1A2536"
BG = "#0B0F15"
BG_PANEL = "#111828"
BG_CARD = "#131C2C"
TEXT = "#EAF0FA"
MUTED = "#94A4BC"
BORDER = "#27344A"

# Phase 1: Semantic color variables
BG_INPUT = "#0F1524"
BG_BUTTON = "#141B2B"
BG_BUTTON_HOVER = "#1A2436"
BG_BUTTON_PRESS = "#121A28"
BG_NAV_ACTIVE = "#1D2940"
BG_NAV_HOVER = "#182236"
BG_BULK_BTN = "#152033"
BG_BULK_HOVER = "#1B2A42"
BG_DISABLED = "#111827"
CARD_HOVER_BG = "#182338"
CARD_HOVER_BORDER = "#3A5274"
CARD_CHANGED_BORDER = "#4A678E"
CARD_CHANGED_HOVER_BORDER = "#5E80AF"
DISABLED_TEXT = "#6D7686"
DISABLED_BORDER = "#333C4B"
MUTED_DARK = "#6D7F98"
TOAST_SUCCESS_BG = "rgba(34, 84, 61, 0.92)"
TOAST_SUCCESS_BORDER = "#2D7A54"
TOAST_ERROR_BG = "rgba(120, 30, 30, 0.94)"
TOAST_ERROR_BORDER = "#D44444"
JUNKMAN_BG = "rgba(166, 227, 106, 0.14)"
JUNKMAN_BORDER = "#5E8F2E"
JUNKMAN_TEXT = "#A6E36A"
MAXED_BG = "rgba(232, 106, 95, 0.14)"
MAXED_BORDER = "#A64A42"
MAXED_TEXT = "#E86A5F"
LEVEL_SEG_LOW = "#3A5A82"
LEVEL_SEG_HIGH = "#5E80AF"
CAREER_SOURCE = "#7FA8E8"
CAREER_SOURCE_BORDER = "#4F73A8"
CAREER_SOURCE_BG = "rgba(79, 115, 168, 0.14)"
MY_CARS_SOURCE = "#B7A4F5"
MY_CARS_SOURCE_BORDER = "#6E5BA8"
MY_CARS_SOURCE_BG = "rgba(110, 91, 168, 0.14)"
GOLD = "#F08BB4"
GOLD_BORDER = "#B85B86"
GOLD_BG = "rgba(240, 139, 180, 0.14)"
ACTIVE_CAR = "#74D39A"
ACTIVE_CAR_BORDER = "#3E8A5D"
ACTIVE_CAR_BG = "rgba(62, 138, 93, 0.14)"

# Phase 3: Border-radius system
RADIUS_SM = "4px"
RADIUS_MD = "8px"
RADIUS_LG = "10px"
RADIUS_XL = "12px"
RADIUS_PILL = "14px"

STYLE = f"""
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
    text-align: left;
    padding: 8px 12px 8px 14px;
    border-left: 3px solid transparent;
    min-height: 36px;
}}
QPushButton#navButton:checked {{
    background: {BG_NAV_ACTIVE};
    border-left: 3px solid {ACCENT_BRIGHT};
    color: {TEXT};
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
    background: rgba(74, 107, 148, 0.12);
}}
QWidget#tokenCard[hovered="true"] {{
    border: 1px solid {CARD_HOVER_BORDER};
    background: {CARD_HOVER_BG};
}}
QWidget#tokenCard[changed="true"][hovered="true"] {{
    border: 1px solid {CARD_CHANGED_HOVER_BORDER};
    background: rgba(111, 147, 196, 0.16);
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
    background: rgba(74, 107, 148, 0.14);
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
    background: rgba(74, 107, 148, 0.12);
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
    background: rgba(74, 107, 148, 0.10);
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


def apply_theme(app) -> None:
    """Apply the dark blue theme."""
    app.setStyleSheet(STYLE)
