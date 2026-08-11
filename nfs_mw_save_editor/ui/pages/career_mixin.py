"""Career page: current progression overview + career stage transplant.

Interaction contract (agreed 2026-07-07, see AGENT_CONTEXT.md):
- Transplant is immediate-with-confirm and writes to the in-memory buffer
  only, mirroring the app's "Apply (memory) -> Save + backup" model. The
  actual disk write stays with the standard Save + backup button.
- The transplant button is disabled while any staged edit is pending, so
  staged want-values can never race the transplanted have-values.
- After a transplant the staged state is reset and the whole UI refreshes
  through the same path used after opening a file.

The page hosts two animated views: the stage-change workflow above and a
read-only Blacklist dossier. Progress is parsed into one immutable summary per
save snapshot, then rendered as a hero, painted 15-node timeline, and selected
chapter inspector. Timeline browsing performs no writes.
"""

from __future__ import annotations

import math
import random
import struct
from collections import OrderedDict

try:
    import numpy as _np
except ImportError:  # degrade to the quarter-res + noise-tile backdrop path
    _np = None
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBitmap,
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QFontMetricsF,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core import (
    career_progress,
    career_transplant,
    milestone_names,
    race_display_names,
    rival_bios,
    rival_challenge,
)
from core.career_donor_library import (
    VARIANT_BOSS_READY,
    VARIANT_CHAPTER_START,
    CareerDonorEntry,
    default_user_career_donor_root,
    load_career_donor_library,
)
from ui.icon_map import game_icon_path, rival_asset_path
from ui.pages.constants import BLACKLIST_BOSS_NAMES
from ui.theme import resolve_theme_tokens
from ui.widgets import (
    AnimatedSegmentedControl,
    AnimatedStackedWidget,
    ThemeTransitionOverlay,
    ToastNotification,
)

_KEEPS_TEXT = "Keeps: money, alias, cars, installed parts, garage stats, Junkman inventory."
_CHANGES_TEXT = (
    "Changes: career stage, milestones, race progress, story SMS, shop unlocks."
)
_BOUNTY_CAVEAT_TEXT = (
    "Note: your cars keep their earned bounty; if the target stage implies "
    "more, the difference is added as sold-cars history."
)

_CAREER_CROSSFADE_MS = 140

# Bahnschrift ships as a single variable-font family: its condensed cuts are
# named styles, not families. Asking for the family "Bahnschrift Condensed"
# silently falls back to whatever the platform picks, so the style has to be
# selected by name - and only when the machine actually has it.
_HERO_DISPLAY_FAMILY = "Bahnschrift"
_HERO_DISPLAY_STYLE = "Bold SemiCondensed"

# Ink sample for the per-rival tagline: a capital's top and a descender's
# bottom. Eleven of the fifteen canon bios have a descender somewhere, so this
# keeps their exact positions and moves the four descender-less rivals (Big
# Lou, Baron, JV, Ronnie) into the same row instead of one pixel above it.
_TAGLINE_INK_SAMPLE = "Xg"

# Ink sample for the rank: every glyph "#N" can show. At the 68px display size
# the round digits (0, 2, 3, 8, 9) overshoot the flat-topped ones by a pixel -
# an optical correction inside the font - so measuring the actual "#7" vs "#8"
# re-dealt the blocks below by that pixel.
_RANK_INK_SAMPLE = "#0123456789"


_ELLIPSIS = "…"


class _HeroTagline(QLabel):
    """The banner's one-line rival tagline: it elides instead of wrapping.

    Wrapping was the original design, but the longest canon sentence (#2 Bull,
    653px) takes a second line as soon as the window narrows, and everything
    below it in the banner - the three plaques, PROGRESS / CHANGE RIVAL - drops
    by that line.  Elision keeps the whole banner still at any width; the full
    sentence stays one hover away in the tooltip.

    ``sizeHint`` deliberately reports the *unelided* width so shortening the
    painted string cannot feed back into the layout that decided the width.
    """

    _MIN_VISIBLE_WIDTH = 120

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setWordWrap(False)

    def full_text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._full_text = text or ""
        self._sync_elided_text()

    def clear(self) -> None:
        self._full_text = ""
        super().clear()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full_text), hint.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().minimumSizeHint()
        return QSize(min(self._MIN_VISIBLE_WIDTH, hint.width()), hint.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_elided_text()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._sync_elided_text()

    def _sync_elided_text(self) -> None:
        elided = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideRight, max(0, self.width())
        )
        if elided != self._full_text:
            elided = self._trim_to_whole_word(elided)
        if elided != super().text():
            super().setText(elided)

    @staticmethod
    def _trim_to_whole_word(elided: str) -> str:
        """Step an elided sentence back to its last whole word.

        Qt cuts at the pixel, which leaves a half-word before the ellipsis
        ("...of the Blac...") and reads like a rendering glitch rather than a
        deliberate trim. Sentences with no space to fall back to keep Qt's cut.
        """

        head = elided.rstrip(_ELLIPSIS).rstrip()
        cut = head.rfind(" ")
        if cut <= 0:
            return elided
        return head[:cut].rstrip(" ,;:") + _ELLIPSIS


class _HeroRhythmColumn(QVBoxLayout):
    """Stacks the banner's blocks with one equal *optical* gap everywhere.

    Ordinary spacing measures widget boxes, and a label's box carries the blank
    ascent/descent of its font: with a 68px headline above a 15px tagline the
    same spacing looks nothing alike. This column measures the ink instead -
    the gap to the card's top edge, between every pair of blocks and to the
    bottom edge all come out the same. The step is whatever the card's height
    leaves over, so it adapts to the wide/compact banner by itself.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)
        self._ink_sources: Dict[int, QLabel] = {}
        self._ink_samples: Dict[int, str] = {}

    def set_ink_source(
        self, index: int, label: QLabel, sample: Optional[str] = None
    ) -> None:
        """Say which label's font decides the blank margins of block `index`.

        A block whose text changes at runtime must pass a `sample`: ink is
        then measured on that fixed string instead of the current text, so
        which glyphs a particular rival's sentence happens to use (descender
        or not, comma or not) cannot re-deal the whole column by a pixel or
        two on every rival switch.
        """
        self._ink_sources[index] = label
        if sample is not None:
            self._ink_samples[index] = sample

    def _block_height(self, index: int, width: int) -> int:
        item = self.itemAt(index)
        widget = item.widget()
        if widget is not None and widget.isHidden():
            return 0
        if widget is not None and widget.hasHeightForWidth() and width > 0:
            return widget.heightForWidth(width)
        return item.sizeHint().height()

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt override
        count = self.count()
        heights = [self._block_height(i, rect.width()) for i in range(count)]
        insets = []
        for index, height in enumerate(heights):
            label = self._ink_sources.get(index)
            if label is None:
                insets.append((0.0, 0.0))
            else:
                sample = self._ink_samples.get(index)
                insets.append(_ink_insets(label, height, sample=sample))
        active = [i for i in range(count) if heights[i] > 0]
        if not active:
            super().setGeometry(rect)
            return

        ink_total = sum(heights[i] - insets[i][0] - insets[i][1] for i in active)
        step = (rect.height() - ink_total) / (len(active) + 1)
        if step < 0:
            super().setGeometry(rect)
            return

        cursor = float(rect.top())
        for index in range(count):
            item = self.itemAt(index)
            if heights[index] <= 0:
                item.setGeometry(QRect(rect.left(), int(round(cursor)), rect.width(), 0))
                continue
            ink_top = cursor + step
            top = ink_top - insets[index][0]
            item.setGeometry(
                QRect(rect.left(), int(round(top)), rect.width(), heights[index])
            )
            cursor = ink_top + (heights[index] - insets[index][0] - insets[index][1])


def _label_block_height(label: QLabel) -> int:
    """Height the label actually needs, independent of any layout pass.

    Before the first layout a widget still reports a placeholder size, so the
    banner rhythm cannot trust height(); the text's own hint can be trusted.
    """
    hint = label.sizeHint().height()
    if label.hasHeightForWidth():
        width = label.width() if label.width() > 0 else label.maximumWidth()
        if 0 < width < 16_777_215:  # QWIDGETSIZE_MAX: an unconstrained width
            return max(hint, label.heightForWidth(width))
    return hint


def _ink_insets(
    label: QLabel, height: Optional[int] = None, sample: Optional[str] = None
) -> Tuple[float, float]:
    """Blank space a label carries above and below its actual glyphs.

    A font reserves ascent and descent room whether the text uses it or not, so
    two labels of different sizes with the same layout spacing between them do
    not look equally spaced. These insets are what has to be subtracted from a
    rhythm step to make gaps equal to the eye.

    With `sample`, ink is measured on that string instead of the label's own
    text - for labels whose text changes at runtime, so the measurement stays
    the same whatever is currently showing.
    """
    metrics = QFontMetrics(label.font())
    text = sample or label.text() or "X"
    tight = metrics.tightBoundingRect(text)
    block_height = _label_block_height(label) if height is None else height
    line_spacing = max(1, metrics.lineSpacing())
    lines = max(1, round(block_height / line_spacing))
    last_baseline = (lines - 1) * line_spacing + metrics.ascent()
    top = metrics.ascent() + tight.top()
    bottom = block_height - (last_baseline + tight.bottom())
    return max(0.0, float(top)), max(0.0, float(bottom))


def _apply_hero_display_font(label: QLabel) -> None:
    if _HERO_DISPLAY_STYLE in QFontDatabase.styles(_HERO_DISPLAY_FAMILY):
        font = QFontDatabase.font(_HERO_DISPLAY_FAMILY, _HERO_DISPLAY_STYLE, -1)
    else:
        font = label.font()
        font.setBold(True)
    label.setFont(font)

# EventID type digit -> packaged game icon (ground truth for the digits:
# the events' internal names in GLOBAL/gameplay.bin, see race_display_names).
_RACE_TYPE_ICONS = {
    1: "race_circuit",
    2: "race_sprint",
    3: "race_lap_knockout",
    4: "milestone_tollbooth",
    5: "trap",
    7: "race_drag",
}


def _norm_event_id(event_id: Optional[str]) -> str:
    if not event_id:
        return ""
    return event_id[:-2] if event_id.endswith(".r") else event_id


def _boss_series_rows(
    stage: int, boss_races: Sequence[career_progress.RaceRecord]
) -> list[_InspectorRow]:
    """Rival Challenge rows in the game's canon screen order.

    Series entries without a save slot (only 1.5.2, Razor's Warrent
    speedtrap) render synthetically; the guard on empty boss_races keeps
    ghost rows out of saves whose race table did not parse."""
    if not boss_races:
        return []
    series = rival_challenge.BOSS_SERIES.get(stage, ())
    tracked = {_norm_event_id(record.event_id): record for record in boss_races}
    rows = []
    used = set()
    for canon_id in series:
        record = tracked.get(_norm_event_id(canon_id))
        if record is not None:
            rows.append(_race_row(record, boss=True))
            used.add(_norm_event_id(canon_id))
        else:
            rows.append(_untracked_boss_row(canon_id, boss_races))
    for record in sorted(boss_races, key=_event_sort_key):
        if _norm_event_id(record.event_id) not in used:
            rows.append(_race_row(record, boss=True))
    return rows


def _untracked_boss_row(
    event_id: str, siblings: Sequence[career_progress.RaceRecord]
) -> _InspectorRow:
    if siblings and all(record.is_completed for record in siblings):
        state, detail = "done", "SERIES COMPLETE"
    elif any(
        record.flags & career_progress.RACE_FLAG_UNLOCKED_CAREER
        for record in siblings
    ):
        state, detail = "open", "AVAILABLE"
    else:
        state, detail = "locked", "LOCKED"
    title = race_display_names.display_name(event_id) or f"Event {event_id}"
    type_label = race_display_names.type_label(event_id) or "Event"
    return _InspectorRow(
        title=title,
        tag="",
        state=state,
        kind="boss",
        icon_path=game_icon_path(_race_type_icon(event_id)),
        detail=detail,
        fraction=None,
        tooltip=(
            f"{title} — rival race\n{type_label} · {event_id} · boss race\n"
            "The save keeps no record for this event — its state follows "
            "the rest of the rival series."
        ),
    )


def _race_type_icon(event_id: Optional[str]) -> str:
    if race_display_names.type_label(event_id) == "Pursuit":
        return "heat"
    if event_id:
        parts = event_id.split(".")
        if len(parts) >= 3:
            try:
                return _RACE_TYPE_ICONS.get(int(parts[1]), "race")
            except ValueError:
                pass
    return "race"


@dataclass(frozen=True)
class HeroPortraitLayout:
    """Per-rival normalized full-bust crop."""

    crop_x: float
    crop_y: float
    crop_width: float
    crop_height: float
    x_offset: float = 0.0


# Coordinates are normalized against each alpha-trimmed generated foreground.
# Every source crop includes the full head, chin, neck and shoulders, then the
# complete crop is fitted inside the Hero rather than enlarged beyond its clip.
HERO_PORTRAIT_LAYOUTS: Mapping[int, HeroPortraitLayout] = MappingProxyType({
    15: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    14: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, 0.00),
    13: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    12: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, -0.01),
    11: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    10: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    9: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    8: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    7: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    6: HeroPortraitLayout(0.00, 0.00, 1.00, 0.95, 0.00),
    5: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, -0.01),
    4: HeroPortraitLayout(0.00, 0.00, 1.00, 0.96, 0.00),
    3: HeroPortraitLayout(0.00, 0.00, 1.00, 0.98, 0.00),
    2: HeroPortraitLayout(0.00, 0.00, 1.00, 0.98, 0.00),
    1: HeroPortraitLayout(0.00, 0.00, 1.00, 0.94, 0.00),
})


_NOISE_TILE_SIZE = 128
_noise_tile: Optional[QImage] = None


def _blue_noise_tile() -> QImage:
    """Binary +1-level tile, high-frequency, half the pixels set.

    Any 8-bit rendering of the banner's shallow gradients leaves vertical
    structure the eye latches onto: Qt's own dither repeats per column
    (the originally reported stripes), and a clean quantization leaves
    step edges.
    Composited with Plus over the finished backdrop, this tile breaks that
    coherence with a half-level grain that does not line up into anything -
    white noise minus its local mean, thresholded at the median, so the
    energy is high-frequency and the density is exactly one half.
    """
    global _noise_tile
    if _noise_tile is not None:
        return _noise_tile
    size = _NOISE_TILE_SIZE
    rng = random.Random(0x5EED)
    white = [[rng.random() for _ in range(size)] for _ in range(size)]
    high_pass = []
    for y in range(size):
        row = []
        for x in range(size):
            acc = 0.0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    acc += white[(y + dy) % size][(x + dx) % size]
            row.append(white[y][x] - acc / 9.0)
        high_pass.append(row)
    ordered = sorted(value for row in high_pass for value in row)
    median = ordered[len(ordered) // 2]
    tile = QImage(size, size, QImage.Format_RGB32)
    for y in range(size):
        for x in range(size):
            v = 1 if high_pass[y][x] > median else 0
            tile.setPixelColor(x, y, QColor(v, v, v))
    _noise_tile = tile
    return tile


def _render_hero_backdrop_dithered(
    width: int, height: int, tokens: Mapping[str, str]
) -> QImage:
    """Full-resolution float compose with noise added BEFORE the rounding.

    Every earlier attempt left something vertical for the eye: Qt's own
    dither repeats per column, a clean quantization leaves step edges, and
    quantizing a quarter-res reference before upscaling stretches its steps
    into soft 10-15px bands (seen live in amplified screenshots). Randomized
    rounding -
    uniform half-level noise added to the float value, then rounded, fixed
    seed - decorrelates the quantization error completely: no stripes, no
    glow rings, only half-level grain with no structure. Needs numpy;
    ~30ms at banner size, cached per size and theme by the caller.
    """
    w, h = max(2, width), max(2, height)

    def rgb(token: str):
        color = QColor(tokens[token])
        return _np.array([color.red(), color.green(), color.blue()], dtype=_np.float64)

    panel, card, soft = rgb("BG_PANEL"), rgb("BG_CARD"), rgb("ACCENT_SOFT")
    bright = rgb("ACCENT_BRIGHT")

    t = _np.arange(w, dtype=_np.float64) / w
    base = _np.empty((w, 3), dtype=_np.float64)
    left = t < 0.48
    base[left] = panel + (card - panel) * (t[left] / 0.48)[:, None]
    base[~left] = card + (soft - card) * ((t[~left] - 0.48) / 0.52)[:, None]
    ts = _np.minimum(1.0, t / 0.72)
    shade = _np.where(
        ts < 0.52,
        255.0 + (205.0 - 255.0) * (ts / 0.52),
        205.0 * (1.0 - (ts - 0.52) / 0.48),
    ) / 255.0

    cx, cy, radius = w * 0.83, h * 0.38, w * 0.48
    r = _np.sqrt(
        (_np.arange(w, dtype=_np.float64)[None, :] - cx) ** 2
        + (_np.arange(h, dtype=_np.float64)[:, None] - cy) ** 2
    ) / radius
    glow = _np.where(
        r < 0.42,
        74.0 + (24.0 - 74.0) * (r / 0.42),
        _np.where(r < 1.0, 24.0 * (1.0 - (r - 0.42) / 0.58), 0.0),
    ) / 255.0

    image = base[None, :, :] * (1.0 - glow[..., None]) + bright * glow[..., None]
    image = image * (1.0 - shade[None, :, None]) + panel * shade[None, :, None]

    # One noise field for all three channels: luminance grain, no chroma.
    noise = _np.random.default_rng(0x5EED).random((h, w)) - 0.5
    out = _np.clip(_np.rint(image + noise[..., None]), 0, 255).astype(_np.uint8)
    bgra = _np.empty((h, w, 4), dtype=_np.uint8)
    bgra[..., 0] = out[..., 2]
    bgra[..., 1] = out[..., 1]
    bgra[..., 2] = out[..., 0]
    bgra[..., 3] = 255
    return QImage(bgra.tobytes(), w, h, w * 4, QImage.Format_RGB32).copy()


def _render_hero_backdrop(width: int, height: int, tokens: Mapping[str, str]) -> QImage:
    """The banner's three background gradients composed in float, quantized once.

    Qt dithers every gradient fill and the three layers dither independently
    (the old left_shade even re-covered the base it was cancelling, adding
    the two patterns) - and because that dither repeats per column it reads
    as vertical stripes on the shallow dark field. Composed in float there
    is nothing to dither. Rendered at quarter resolution - the compose is
    smooth, so the upscale adds nothing visible, and the pure-python cost
    drops to ~20ms once per size and theme. The caller upscales and lays
    the blue-noise tile over the result (see _blue_noise_tile): without it
    the quantization step edges are their own, cleaner, stripes.
    """
    w = max(2, width // 4)
    h = max(2, height // 4)

    def rgb(token: str) -> Tuple[int, int, int]:
        color = QColor(tokens[token])
        return color.red(), color.green(), color.blue()

    panel, card, soft = rgb("BG_PANEL"), rgb("BG_CARD"), rgb("ACCENT_SOFT")
    bright = rgb("ACCENT_BRIGHT")

    base_row: List[Tuple[float, float, float]] = []
    shade_row: List[float] = []
    for x in range(w):
        t = x / w
        if t < 0.48:
            k = t / 0.48
            a, b = panel, card
        else:
            k = (t - 0.48) / 0.52
            a, b = card, soft
        base_row.append(tuple(a[i] + (b[i] - a[i]) * k for i in range(3)))
        ts = min(1.0, x / (w * 0.72))
        if ts < 0.52:
            alpha = 255.0 + (205.0 - 255.0) * (ts / 0.52)
        else:
            alpha = 205.0 * (1.0 - (ts - 0.52) / 0.48)
        shade_row.append(alpha / 255.0)

    cx, cy = w * 0.83, h * 0.38
    radius = w * 0.48
    radius_sq = radius * radius
    buf = bytearray(w * h * 4)
    i = 0
    for y in range(h):
        dy_sq = (y - cy) ** 2
        for x in range(w):
            r, g, b = base_row[x]
            dist_sq = (x - cx) ** 2 + dy_sq
            if dist_sq < radius_sq:
                rr = math.sqrt(dist_sq) / radius
                if rr < 0.42:
                    ga = (74.0 + (24.0 - 74.0) * (rr / 0.42)) / 255.0
                else:
                    ga = (24.0 * (1.0 - (rr - 0.42) / 0.58)) / 255.0
                r += (bright[0] - r) * ga
                g += (bright[1] - g) * ga
                b += (bright[2] - b) * ga
            sa = shade_row[x]
            r += (panel[0] - r) * sa
            g += (panel[1] - g) * sa
            b += (panel[2] - b) * sa
            buf[i] = min(255, max(0, int(b + 0.5)))
            buf[i + 1] = min(255, max(0, int(g + 0.5)))
            buf[i + 2] = min(255, max(0, int(r + 0.5)))
            buf[i + 3] = 255
            i += 4
    return QImage(bytes(buf), w, h, w * 4, QImage.Format_RGB32).copy()


class _CareerHero(QFrame):
    """Theme-built rival banner with graffiti and portrait art layers."""

    # The banner's rhythm step is whatever these heights leave over after the
    # blocks' ink, so shortening the card is what tightens the spacing.
    _COMPACT_HEIGHT = 300
    _WIDE_HEIGHT = 316
    _WIDE_BREAKPOINT = 1450
    _COMPACT_STAMP_WIDTH = 175.0
    _WIDE_STAMP_WIDTH = 210.0
    _art_cache: "OrderedDict[int, tuple[QPixmap, QPixmap]]" = OrderedDict()
    _backdrop_cache: "OrderedDict[tuple, QImage]" = OrderedDict()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerHero")
        self.setFixedHeight(self._COMPACT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._stage: Optional[int] = None
        self._graffiti = QPixmap()
        self._portrait = QPixmap()
        self._defeated_stamp = QPixmap()
        # Mid-resize the backdrop paints from the latest same-theme reference
        # stretched to the new size; this settles the exact re-render.
        self._backdrop_timer = QTimer(self)
        self._backdrop_timer.setSingleShot(True)
        self._backdrop_timer.setInterval(150)
        self._backdrop_timer.timeout.connect(self._settle_backdrop)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._WIDE_HEIGHT if width >= self._WIDE_BREAKPOINT else self._COMPACT_HEIGHT

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1100, self.heightForWidth(max(1100, self.width())))

    def set_stage(self, stage: Optional[int]) -> None:
        if stage == self._stage:
            return
        self._stage = stage
        if stage is None:
            self._graffiti = QPixmap()
            self._portrait = QPixmap()
            self.update()
            return
        cached = self._art_cache.get(stage)
        if cached is not None:
            self._art_cache.move_to_end(stage)
            self._graffiti, self._portrait = cached
            self.update()
            return

        graffiti_path = rival_asset_path(stage, "graffiti")
        portrait_path = rival_asset_path(stage, "hero_portrait")
        graffiti = QPixmap(str(graffiti_path)) if graffiti_path is not None else QPixmap()
        portrait = QPixmap(str(portrait_path)) if portrait_path is not None else QPixmap()
        if portrait.isNull():
            portrait = self._fallback_portrait(stage)
        self._graffiti = graffiti
        self._portrait = portrait
        self._art_cache[stage] = (graffiti, portrait)
        while len(self._art_cache) > 3:
            self._art_cache.popitem(last=False)
        self.update()

    def set_defeated_stamp(self, stamp: QPixmap) -> None:
        self._defeated_stamp = QPixmap(stamp)
        self.update()

    @staticmethod
    def _fallback_portrait(stage: int) -> QPixmap:
        source = rival_asset_path(stage, "portrait")
        if source is None:
            return QPixmap()
        reader = QImageReader(str(source))
        reader.setScaledSize(QSize(1024, 1024))
        return QPixmap.fromImage(reader.read())

    def portraitSourceRect(self, stage: int) -> QRectF:  # noqa: N802
        """Normalized bust crop mapped onto the loaded foreground pixmap."""
        if self._portrait.isNull():
            return QRectF()
        layout = HERO_PORTRAIT_LAYOUTS[stage]
        return QRectF(
            self._portrait.width() * layout.crop_x,
            self._portrait.height() * layout.crop_y,
            self._portrait.width() * layout.crop_width,
            self._portrait.height() * layout.crop_height,
        )

    def portraitRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        """Bust target fully contained inside the Hero clip."""
        if self._portrait.isNull() or height <= 0:
            return QRectF()
        layout = HERO_PORTRAIT_LAYOUTS[stage]
        source = self.portraitSourceRect(stage)
        target_height = max(1.0, height - 14.0)
        target_width = target_height * source.width() / source.height()
        return QRectF(
            width - target_width - 7.0 + layout.x_offset * height,
            14.0,
            target_width,
            target_height,
        )

    def bustSafeRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        return self.portraitRect(stage, width, height)

    def defeatedStampRect(self, stage: int, width: int, height: int) -> QRectF:  # noqa: N802
        if self._defeated_stamp.isNull():
            return QRectF()
        portrait = self.portraitRect(stage, width, height)
        if portrait.isNull():
            return QRectF()
        stamp_width = (
            self._WIDE_STAMP_WIDTH
            if width >= self._WIDE_BREAKPOINT
            else self._COMPACT_STAMP_WIDTH
        )
        stamp_height = stamp_width * (
            self._defeated_stamp.height() / self._defeated_stamp.width()
        )
        return QRectF(
            portrait.center().x() - stamp_width * 0.55,
            portrait.top() + portrait.height() * 0.66,
            stamp_width,
            stamp_height,
        )

    @staticmethod
    def _backdrop_signature(tokens: Mapping[str, str]) -> tuple:
        return (
            tokens["BG_PANEL"],
            tokens["BG_CARD"],
            tokens["ACCENT_SOFT"],
            tokens["ACCENT_BRIGHT"],
        )

    @staticmethod
    def _build_backdrop(width: int, height: int, tokens: Mapping[str, str]) -> QImage:
        """Full-size cache entry.

        With numpy: full-res compose dithered before rounding - nothing
        coherent survives. Without: quarter-res compose, upscale, noise
        tile - the tile masks (not removes) the upscale's soft banding.
        """
        if _np is not None:
            return _render_hero_backdrop_dithered(width, height, tokens)
        quarter = _render_hero_backdrop(width, height, tokens)
        image = quarter.scaled(
            width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        tile = _blue_noise_tile()
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for tile_y in range(0, height, tile.height()):
            for tile_x in range(0, width, tile.width()):
                painter.drawImage(QPoint(tile_x, tile_y), tile)
        painter.end()
        return image

    def _settle_backdrop(self) -> None:
        tokens = resolve_theme_tokens()
        key = (self.width(), self.height(), self._backdrop_signature(tokens))
        if key not in self._backdrop_cache:
            self._backdrop_cache[key] = self._build_backdrop(
                self.width(), self.height(), tokens
            )
            while len(self._backdrop_cache) > 4:
                self._backdrop_cache.popitem(last=False)
        self.update()

    def _shade_faded(self, color: QColor, width: int) -> QBrush:
        """The old left_shade dimmed the grid and diagonal on its way out;
        with the shade baked into the backdrop, the same piecewise-linear
        attenuation is applied through the line color instead."""
        gradient = QLinearGradient(0, 0, width, 0)
        for pos, factor in ((0.0, 0.0), (0.374, 0.196), (0.72, 1.0), (1.0, 1.0)):
            stop = QColor(color)
            stop.setAlphaF(color.alphaF() * factor)
            gradient.setColorAt(pos, stop)
        return QBrush(gradient)

    def _paint_theme_background(self, painter: QPainter, tokens: Mapping[str, str]) -> None:
        width = self.width()
        height = self.height()
        signature = self._backdrop_signature(tokens)
        key = (width, height, signature)
        backdrop = self._backdrop_cache.get(key)
        if backdrop is None:
            stale = None
            for (_w, _h, sig), image in reversed(self._backdrop_cache.items()):
                if sig == signature:
                    stale = image
                    break
            if stale is not None:
                # Mid-resize: stretch the last reference now (the compose is
                # proportional, the difference is imperceptible in motion)
                # and re-render exactly once the size settles.
                backdrop = stale
                self._backdrop_timer.start()
            else:
                backdrop = self._build_backdrop(width, height, tokens)
                self._backdrop_cache[key] = backdrop
                while len(self._backdrop_cache) > 4:
                    self._backdrop_cache.popitem(last=False)
        else:
            self._backdrop_cache.move_to_end(key)
        painter.drawImage(self.rect(), backdrop)

        band = QColor(tokens["ACCENT"])
        band.setAlpha(24)
        diagonal = QPainterPath(QPointF(width * 0.56, height))
        diagonal.lineTo(width * 0.72, 0)
        diagonal.lineTo(width * 0.78, 0)
        diagonal.lineTo(width * 0.62, height)
        diagonal.closeSubpath()
        painter.fillPath(diagonal, self._shade_faded(band, width))

    def _graffiti_rect(self) -> QRectF:
        if self._stage is None or self._graffiti.isNull():
            return QRectF()
        portrait = self.portraitRect(self._stage, self.width(), self.height())
        max_width = min(self.width() * 0.36, 360.0)
        max_height = self.height() * 0.60
        scale = min(
            max_width / self._graffiti.width(),
            max_height / self._graffiti.height(),
        )
        target_width = self._graffiti.width() * scale
        target_height = self._graffiti.height() * scale
        # The signature bridges the empty middle and the portrait, but ends
        # underneath the subject so no isolated tail can survive at the edge.
        target_right = portrait.left() + portrait.width() * 0.20
        return QRectF(
            target_right - target_width,
            (self.height() - target_height) * 0.52,
            target_width,
            target_height,
        )

    def _paint_graffiti(self, painter: QPainter) -> None:
        target = self._graffiti_rect()
        if target.isNull():
            return
        painter.setOpacity(0.22)
        painter.drawPixmap(target, self._graffiti, QRectF(self._graffiti.rect()))
        painter.setOpacity(1.0)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(_event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 12.0, 12.0)
        painter.setClipPath(clip)
        self._paint_theme_background(painter, tokens)
        self._paint_graffiti(painter)

        if self._stage is not None and not self._portrait.isNull():
            painter.setOpacity(0.98)
            painter.drawPixmap(self.portraitRect(
                self._stage, self.width(), self.height()
            ), self._portrait, self.portraitSourceRect(self._stage))
            painter.setOpacity(1.0)
            if not self._defeated_stamp.isNull():
                painter.drawPixmap(
                    self.defeatedStampRect(self._stage, self.width(), self.height()),
                    self._defeated_stamp,
                    QRectF(self._defeated_stamp.rect()),
                )

        painter.setClipping(False)
        painter.setPen(QPen(QColor(tokens["BORDER"]), 1.0))
        painter.drawRoundedRect(rect, 12.0, 12.0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        desired_height = self.heightForWidth(event.size().width())
        if self.height() != desired_height:
            self.setFixedHeight(desired_height)
        super().resizeEvent(event)


def _stage_title(stage: int) -> str:
    boss = BLACKLIST_BOSS_NAMES.get(stage)
    return f"#{stage}: {boss}" if boss else f"#{stage}"


def _display_name_text(text: str) -> str:
    return text.replace(" — ", ": ")


def _fmt_num(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


def _fmt_compact(value: int) -> str:
    if value >= 1_000_000:
        number = value / 1_000_000
        return f"{number:.2f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        number = value / 1_000
        return f"{number:.1f}".rstrip("0").rstrip(".") + "K"
    return f"{value:,}"


def _milestone_display(type_key: int, value: float) -> str:
    info = milestone_names.type_label_and_unit(type_key)
    if info is None:
        return _fmt_num(value)
    _label, unit = info
    if unit == "money":
        return f"${int(round(value)):,}"
    if unit == "seconds":
        seconds = max(0, int(round(value)))
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{int(round(value)):,}"


def _milestone_icon(type_key: int) -> Optional[Path]:
    name = milestone_names.resolve_type_name(type_key)
    icon_names = {
        "bounty_in_pursuit": "milestone_pursuit_bounty",
        "cops_damaged": "cops_damaged",
        "cost_to_state_in_pursuit": "milestone_cost_to_state",
        "pursuit_evasion_time": "milestone_pursuit_mintime",
        "pursuit_length": "milestone_pursuit_duration",
        "roadblocks_dodged": "milestone_roadblocks",
        "tire_spikes_dodged": "milestone_spikestrips",
        "total_infractions": "milestone_infractions",
    }
    return game_icon_path(icon_names.get(name, "milestone"))


def _event_sort_key(record: career_progress.RaceRecord) -> Tuple[int, int, int]:
    parts = (record.event_id or "").split(".")
    try:
        return (int(parts[1]), int(parts[2]), 1 if record.is_reversed else 0)
    except (IndexError, ValueError):
        return (99, record.index, 0)


class _BlacklistTimeline(QWidget):
    """Single painted Blacklist ladder with read-only stage selection."""

    stageSelected = Signal(int)
    _glyph_cache: "OrderedDict[tuple[str, int], QPixmap]" = OrderedDict()
    _SELECTION_DURATION_MS = 190

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerTimeline")
        # A plain QWidget subclass drops the stylesheet's background and border
        # unless it opts in; QFrame does this for itself, which is why every
        # other card renders without the flag.  Without it the timeline's card
        # rule sat in the theme doing nothing.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._names_shown = False
        self._resizing = False
        self.setFixedHeight(self._card_height())
        self._summary: Optional[career_progress.CareerProgressSummary] = None
        self._selected_stage: Optional[int] = None
        self._selection_position: Optional[float] = None
        self._selection_animation = QVariantAnimation(self)
        self._selection_animation.setDuration(self._SELECTION_DURATION_MS)
        self._selection_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._selection_animation.valueChanged.connect(self._set_selection_position)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1000, self._card_height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        # Losing the names costs a label line, and the card has to give that
        # height back instead of leaving a hole under the numbers.  The latch
        # is required: setFixedHeight lands back here synchronously.
        if self._resizing:
            return
        self._resizing = True
        try:
            height = self._card_height()
            if self.height() != height:
                self.setFixedHeight(height)
        finally:
            self._resizing = False

    def set_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        selected_stage: Optional[int],
    ) -> None:
        self._selection_animation.stop()
        self._summary = summary
        self._selected_stage = selected_stage
        self._selection_position = self._stage_position(selected_stage)
        self.update()

    def set_selected_stage(self, stage: int) -> None:
        if stage != self._selected_stage:
            start = self._selection_position
            if start is None:
                start = self._stage_position(self._selected_stage)
            end = self._stage_position(stage)
            self._selected_stage = stage
            self._selection_animation.stop()
            if self.isVisible() and start is not None and end is not None:
                self._selection_animation.setStartValue(start)
                self._selection_animation.setEndValue(end)
                self._selection_animation.start()
            else:
                self._selection_position = end
                self.update()

    @staticmethod
    def _stage_position(stage: Optional[int]) -> Optional[float]:
        if stage is None or not 1 <= stage <= 15:
            return None
        return float(15 - stage)

    def _set_selection_position(self, value) -> None:
        self._selection_position = float(value)
        self.update()

    @staticmethod
    def _selection_bracket_path(
        center: QPointF, radius: float, arm: float
    ) -> QPainterPath:
        left = center.x() - radius
        right = center.x() + radius
        top = center.y() - radius
        bottom = center.y() + radius
        path = QPainterPath()
        path.moveTo(left + arm, top)
        path.lineTo(left, top)
        path.lineTo(left, top + arm)
        path.moveTo(right - arm, top)
        path.lineTo(right, top)
        path.lineTo(right, top + arm)
        path.moveTo(left, bottom - arm)
        path.lineTo(left, bottom)
        path.lineTo(left + arm, bottom)
        path.moveTo(right, bottom - arm)
        path.lineTo(right, bottom)
        path.lineTo(right - arm, bottom)
        return path

    # Card geometry.  Everything is measured from the content so the card hugs
    # the strip: the same padding above the selection bracket, below the label
    # lines, and beyond the outer labels.
    _CARD_PADDING = 20.0
    _NODE_RADIUS = 12.5
    _SELECTED_RADIUS = _NODE_RADIUS + 5.5
    _LABEL_GAP = 4.0
    _LABEL_HEIGHT = 30.0
    # Padding plus half of an outer label, so the ends of the strip keep the
    # same margin as the rest.  Two values because the outer label is either
    # "#15 SONNY" or a bare "#15".
    _EDGE_INSET = 46.0
    _EDGE_INSET_BARE = 32.0
    # Names are shown at the largest size that still leaves a gap between
    # neighbours; a hardcoded "wide enough" threshold used to hide them long
    # before the room actually ran out.
    _LABEL_SIZES = (9.0, 8.5, 8.0, 7.5)
    _LABEL_MIN_GAP = 8.0
    _LABEL_HEIGHT_BARE = 16.0

    def _name_font_size(self) -> Optional[float]:
        """Largest size at which every boss name fits between two nodes.

        Hysteresis, not a bare threshold: showing the names costs a label line,
        which changes the card's height, which can raise or drop the page's
        scrollbar, which changes this width again.  Without the extra margin to
        switch names ON, that loop oscillates - it overflowed the stack the
        first time the cards beside it changed the page's width.
        """
        span = max(1.0, self.width() - 2 * self._EDGE_INSET)
        pitch = span / 14.0
        needed_gap = self._LABEL_MIN_GAP + (0.0 if self._names_shown else 14.0)
        names = [
            BLACKLIST_BOSS_NAMES.get(stage, "?").upper() for stage in range(15, 0, -1)
        ]
        for size in self._LABEL_SIZES:
            font = QFont(self.font())
            font.setPointSizeF(size)
            font.setBold(True)
            metrics = QFontMetricsF(font)
            widest = max(metrics.horizontalAdvance(name) for name in names)
            if widest + needed_gap <= pitch:
                self._names_shown = True
                return size
        self._names_shown = False
        return None

    def _card_height(self) -> int:
        """Padding, the tallest thing above a node, the node, and its label."""
        label = (
            self._LABEL_HEIGHT
            if self._name_font_size() is not None
            else self._LABEL_HEIGHT_BARE
        )
        return round(
            self._CARD_PADDING
            + self._SELECTED_RADIUS
            + self._NODE_RADIUS
            + self._LABEL_GAP
            + label
            + self._CARD_PADDING
        )

    def _nodes(self) -> list[tuple[int, QPointF]]:
        inset = (
            self._EDGE_INSET
            if self._name_font_size() is not None
            else self._EDGE_INSET_BARE
        )
        left = inset
        right = max(left, self.width() - inset)
        span = max(1.0, right - left)
        centre_y = self._CARD_PADDING + self._SELECTED_RADIUS
        return [
            (stage, QPointF(left + index * span / 14.0, centre_y))
            for index, stage in enumerate(range(15, 0, -1))
        ]

    def _state(self, stage: int) -> str:
        if self._summary is None:
            return "locked"
        return self._summary.stage_state(stage)

    def _current_progress_line(
        self, nodes: Sequence[tuple[int, QPointF]]
    ) -> Optional[tuple[QPointF, QPointF]]:
        summary = self._summary
        if summary is None or summary.endgame or summary.current_stage <= 1:
            return None
        fraction = summary.requirement_progress(summary.current_stage)
        if fraction <= 0.0:
            return None
        points = dict(nodes)
        start = points.get(summary.current_stage)
        target = points.get(summary.current_stage - 1)
        if start is None or target is None:
            return None
        end = QPointF(
            start.x() + (target.x() - start.x()) * fraction,
            start.y() + (target.y() - start.y()) * fraction,
        )
        return start, end

    @classmethod
    def _glyph(cls, icon_name: str, size: int) -> QPixmap:
        key = (icon_name, size)
        cached = cls._glyph_cache.get(key)
        if cached is not None:
            cls._glyph_cache.move_to_end(key)
            return cached
        path = game_icon_path(icon_name)
        source = QPixmap(str(path)) if path is not None else QPixmap()
        if source.isNull():
            return QPixmap()
        bounds = QRegion(QBitmap.fromImage(
            source.toImage().createAlphaMask()
        )).boundingRect()
        if not bounds.isEmpty():
            source = source.copy(bounds)
        source = source.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        cls._glyph_cache[key] = source
        while len(cls._glyph_cache) > 8:
            cls._glyph_cache.popitem(last=False)
        return source

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(_event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        nodes = self._nodes()
        if not nodes:
            return

        base_pen = QPen(QColor(tokens["BORDER"]), 2.0)
        painter.setPen(base_pen)
        painter.drawLine(nodes[0][1], nodes[-1][1])
        for (stage, point), (next_stage, next_point) in zip(nodes, nodes[1:]):
            if self._state(stage) == "defeated" and self._state(next_stage) in {
                "defeated", "current", "boss_ready"
            }:
                painter.setPen(QPen(QColor(tokens["ACCENT"]), 3.0))
                painter.drawLine(point, next_point)
        current_progress = self._current_progress_line(nodes)
        if current_progress is not None:
            progress_pen = QPen(QColor(tokens["ACCENT"]), 3.0)
            progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            painter.drawLine(*current_progress)

        name_size = self._name_font_size()
        wide = name_size is not None
        node_radius = self._NODE_RADIUS
        selected_radius = self._SELECTED_RADIUS
        bracket_arm = 5.5
        if self._selection_position is not None:
            position = max(0.0, min(14.0, self._selection_position))
            selection_x = nodes[0][1].x() + position * (
                nodes[-1][1].x() - nodes[0][1].x()
            ) / 14.0
            painter.setBrush(Qt.NoBrush)
            selection_pen = QPen(QColor(tokens["ACCENT_BRIGHT"]), 2.0)
            selection_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
            selection_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(selection_pen)
            painter.drawPath(self._selection_bracket_path(
                QPointF(selection_x, nodes[0][1].y()), selected_radius, bracket_arm
            ))
        for stage, point in nodes:
            state = self._state(stage)
            selected = stage == self._selected_stage
            if state == "defeated":
                fill = QColor(tokens["ACCENT_BRIGHT"])
                border = QColor(tokens["ACCENT_BRIGHT"])
            elif state == "boss_ready":
                fill = QColor(tokens["ACCENT"])
                border = QColor(tokens["TEXT"])
            elif state == "current":
                fill = QColor(tokens["BG_PANEL"])
                border = QColor(tokens["ACCENT_BRIGHT"])
            else:
                fill = QColor(tokens["BG_DISABLED"])
                border = QColor(tokens["BORDER"])

            painter.setBrush(fill)
            painter.setPen(QPen(border, 2.0 if state in {"current", "boss_ready"} else 1.3))
            painter.drawEllipse(point, node_radius, node_radius)

            glyph_name = "timeline_check" if state == "defeated" else "timeline_arrow"
            if state == "defeated":
                glyph_size = 18 if wide else 17
            else:
                glyph_size = 10 if wide else 9
            glyph = self._glyph(glyph_name, glyph_size)
            if not glyph.isNull():
                painter.drawPixmap(
                    QRectF(
                        point.x() - glyph.width() / 2.0,
                        point.y() - glyph.height() / 2.0,
                        glyph.width(),
                        glyph.height(),
                    ),
                    glyph,
                    QRectF(glyph.rect()),
                )

            font = painter.font()
            font.setBold(selected or state in {"current", "boss_ready"})
            font.setPointSizeF(name_size if wide else 9.0)
            painter.setFont(font)
            label_color = QColor(tokens["TEXT"])
            if not selected:
                label_color.setAlpha(175)
            painter.setPen(label_color)
            text_rect = QRectF(
                point.x() - 44,
                point.y() + node_radius + 4,
                88,
                32,
            )
            if wide:
                label = f"#{stage}\n{BLACKLIST_BOSS_NAMES.get(stage, '?').upper()}"
            else:
                label = f"#{stage}"
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

    def _stage_at(self, pos: QPoint) -> Optional[int]:
        nearest: tuple[float, Optional[int]] = (22.0, None)
        for stage, point in self._nodes():
            distance = abs(point.x() - pos.x())
            if distance < nearest[0] and abs(point.y() - pos.y()) <= 24:
                nearest = (distance, stage)
        return nearest[1]

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            stage = self._stage_at(event.position().toPoint())
            if stage is not None:
                self.stageSelected.emit(stage)
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        stage = self._stage_at(event.position().toPoint())
        if stage is None:
            self.setToolTip("")
        else:
            state = self._state(stage).replace("_", " ")
            self.setToolTip(f"{_stage_title(stage)} — {state}")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._selected_stage is not None and event.key() in (Qt.Key_Left, Qt.Key_Right):
            delta = 1 if event.key() == Qt.Key_Left else -1
            stage = min(15, max(1, self._selected_stage + delta))
            self.stageSelected.emit(stage)
            return
        super().keyPressEvent(event)


@dataclass(frozen=True)
class _InspectorRow:
    title: str
    tag: str
    state: str
    kind: str
    icon_path: Optional[Path]
    detail: str
    fraction: Optional[float]
    tooltip: str


class _ChipPreviewCard(QFrame):
    """One row of chips standing in for a chapter's events.

    A preview, not a list: the boss chips are always shown and the rest of the
    row is filled with races in list order, so the card reads as full at every
    stage the game gives enough events for.  State is carried by fill, border
    and icon opacity - the same language the dossier rows use - because hue
    alone cannot survive 25 themes: in the yellow ones the boss gold and the
    accent are the same colour.
    """

    _pixmap_cache: "OrderedDict[tuple[str, int, str], QPixmap]" = OrderedDict()
    _PAD = 16
    _GAP = 8
    _HEADER = 24
    _HEADER_GAP = 12
    # The chip grows with the WINDOW, never with the card.  Deriving it from
    # the card made the card's height depend on its width, and the page's
    # scrollbar closes that loop: taller content raises the bar, the narrower
    # viewport shrinks the chips, the shorter card drops the bar again - an
    # oscillation that overflowed the stack.  A window is not resized by its
    # own scrollbar, so reading it is safe.  Each step is sized so all seven
    # milestones still fit their card at that width.
    _CHIP_STEPS = ((1600, 80), (1350, 68), (0, 56))
    _RADIUS = 12.0

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("careerInspectorSection")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._title = title
        self._subtitle = ""
        self._rows: Tuple[_InspectorRow, ...] = ()
        self._boss_rows: Tuple[_InspectorRow, ...] = ()
        self._chip_rects: list[tuple[QRect, _InspectorRow]] = []
        self.setFixedHeight(self._card_height())

    def _chip(self) -> int:
        window = self.window()
        width = window.width() if window is not None else 0
        for threshold, size in self._CHIP_STEPS:
            if width >= threshold:
                return size
        return self._CHIP_STEPS[-1][1]

    def _slots(self) -> int:
        """How many chips the row holds - the card is meant to look full."""
        room = self.width() - 2 * self._PAD
        return max(1, (room + self._GAP) // (self._chip() + self._GAP))

    def _card_height(self) -> int:
        return self._PAD + self._HEADER + self._HEADER_GAP + self._chip() + self._PAD

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(520, self._card_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(340, self._card_height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        height = self._card_height()
        if self.height() != height:
            self.setFixedHeight(height)

    def set_items(
        self,
        subtitle: str,
        rows: Sequence[_InspectorRow],
        boss_rows: Sequence[_InspectorRow] = (),
    ) -> None:
        self._subtitle = subtitle
        self._rows = tuple(rows)
        self._boss_rows = tuple(boss_rows)
        self.update()

    def _tinted(self, path: Optional[Path], size: int, colour: Optional[QColor]) -> QPixmap:
        if path is None:
            return QPixmap()
        key = (str(path), size, colour.name() if colour is not None else "-")
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            self._pixmap_cache.move_to_end(key)
            return cached
        source = QPixmap(str(path))
        if source.isNull():
            return source
        source = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if colour is not None:
            layer = QPixmap(source.size())
            layer.fill(Qt.transparent)
            painter = QPainter(layer)
            painter.drawPixmap(0, 0, source)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(layer.rect(), colour)
            painter.end()
            source = layer
        self._pixmap_cache[key] = source
        while len(self._pixmap_cache) > 96:
            self._pixmap_cache.popitem(last=False)
        return source

    def _draw_chip(self, painter: QPainter, rect: QRect, row: _InspectorRow, tokens) -> None:
        boss = row.kind == "boss"
        accent = "BOSS_GOLD" if boss else "ACCENT"
        bright = "BOSS_GOLD_BRIGHT" if boss else "ACCENT_BRIGHT"
        icon_colour: Optional[QColor] = None
        opacity = 1.0
        if row.state == "done":
            fill = QColor(tokens[accent])
            border = QColor(tokens[bright])
            # The theme itself says what reads on top of its accent; without
            # this the icon vanished into the fill on the yellow themes.
            icon_colour = QColor(tokens["TEXT_ON_ACCENT"])
        elif row.state == "open":
            fill = QColor(tokens["BG_INPUT"])
            border = QColor(tokens[accent])
        else:
            fill = QColor(tokens["BG_INPUT"])
            border = QColor(tokens["BOSS_GOLD_DIM" if boss else "BORDER"])
            opacity = 0.38
        painter.setBrush(fill)
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(QRectF(rect), self._RADIUS, self._RADIUS)
        icon = self._tinted(row.icon_path, round(rect.width() * 0.62), icon_colour)
        if not icon.isNull():
            painter.setOpacity(opacity)
            painter.drawPixmap(
                rect.left() + (rect.width() - icon.width()) // 2,
                rect.top() + (rect.height() - icon.height()) // 2,
                icon,
            )
            painter.setOpacity(1.0)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(_event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        header = QRect(
            self._PAD, self._PAD - 2, self.width() - 2 * self._PAD, self._HEADER
        )
        font = painter.font()
        font.setPointSizeF(10.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(tokens["TEXT"]))
        painter.drawText(header, Qt.AlignLeft | Qt.AlignVCenter, self._title)
        font.setPointSizeF(8.5)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(tokens["MUTED"]))
        painter.drawText(header, Qt.AlignRight | Qt.AlignVCenter, self._subtitle)

        size = self._chip()
        top = self._PAD + self._HEADER + self._HEADER_GAP
        shown = self._rows[: max(0, self._slots() - len(self._boss_rows))]
        self._chip_rects = []

        x = self._PAD
        for row in shown:
            rect = QRect(x, top, size, size)
            self._draw_chip(painter, rect, row, tokens)
            self._chip_rects.append((rect, row))
            x += size + self._GAP

        if self._boss_rows:
            # Boss chips hug the right edge; the slack lands between the
            # groups instead of trailing off the end of the row.
            count = len(self._boss_rows)
            x = self.width() - self._PAD - count * size - (count - 1) * self._GAP
            for row in self._boss_rows:
                rect = QRect(x, top, size, size)
                self._draw_chip(painter, rect, row, tokens)
                self._chip_rects.append((rect, row))
                x += size + self._GAP
        painter.end()

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            for rect, row in self._chip_rects:
                if rect.contains(event.pos()):
                    self.setToolTip(f"{row.title}\n{row.tooltip}")
                    break
            else:
                self.setToolTip("")
        return super().event(event)


class _ProgressRowList(QFrame):
    """Painted dossier list: one readable row per event with state and result."""

    _pixmap_cache: "OrderedDict[tuple[str, int], QPixmap]" = OrderedDict()
    _ROWS_TOP = 58
    _ROW_HEIGHT = 30
    _SECTION_GAP = 27
    _BOTTOM_PAD = 14

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("careerInspectorSection")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._title = title
        self._subtitle = ""
        self._rows: Tuple[_InspectorRow, ...] = ()
        self._boss_rows: Tuple[_InspectorRow, ...] = ()
        self._row_rects: list[tuple[QRect, _InspectorRow]] = []

    def _content_height(self) -> int:
        height = self._ROWS_TOP + len(self._rows) * self._ROW_HEIGHT
        if self._boss_rows:
            height += self._SECTION_GAP + len(self._boss_rows) * self._ROW_HEIGHT
        return height + self._BOTTOM_PAD

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(520, self._content_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(340, self._content_height())

    def set_items(
        self,
        subtitle: str,
        rows: Sequence[_InspectorRow],
        boss_rows: Sequence[_InspectorRow] = (),
    ) -> None:
        self._subtitle = subtitle
        self._rows = tuple(rows)
        self._boss_rows = tuple(boss_rows)
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    @classmethod
    def _source_pixmap(cls, path: Optional[Path], size: int) -> QPixmap:
        if path is None:
            return QPixmap()
        key = (str(path), size)
        cached = cls._pixmap_cache.get(key)
        if cached is not None:
            cls._pixmap_cache.move_to_end(key)
            return cached
        source = QPixmap(str(path))
        if source.isNull():
            return QPixmap()
        source = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        original = QPixmap(size, size)
        original.fill(Qt.transparent)
        painter = QPainter(original)
        x = (size - source.width()) // 2
        y = (size - source.height()) // 2
        painter.drawPixmap(x, y, source)
        painter.end()
        cls._pixmap_cache[key] = original
        while len(cls._pixmap_cache) > 128:
            cls._pixmap_cache.popitem(last=False)
        return original

    def _row_font(self, painter: QPainter, size: float, *, bold: bool) -> None:
        font = painter.font()
        font.setBold(bold)
        font.setPointSizeF(size)
        painter.setFont(font)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        tokens = resolve_theme_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        self._row_font(painter, 11.0, bold=True)
        painter.setPen(QColor(tokens["TEXT"]))
        painter.drawText(QRectF(15, 11, self.width() - 30, 20), Qt.AlignLeft, self._title)
        self._row_font(painter, 9.5, bold=False)
        painter.setPen(QColor(tokens["MUTED"]))
        painter.drawText(QRectF(15, 32, self.width() - 30, 20), Qt.AlignLeft, self._subtitle)

        self._row_rects = []
        top = self._paint_rows(painter, tokens, self._rows, self._ROWS_TOP)
        if self._boss_rows:
            self._row_font(painter, 9.0, bold=True)
            painter.setPen(QColor(tokens["BOSS_GOLD"]))
            painter.drawText(
                QRectF(15, top + 5, self.width() - 30, 16), Qt.AlignLeft, "BOSS"
            )
            self._paint_rows(painter, tokens, self._boss_rows, top + self._SECTION_GAP)

    def _paint_rows(
        self,
        painter: QPainter,
        tokens: Mapping[str, str],
        rows: Sequence[_InspectorRow],
        top: int,
    ) -> int:
        width = self.width()
        for index, row in enumerate(rows):
            rect = QRect(10, top, width - 20, self._ROW_HEIGHT)
            self._row_rects.append((rect, row))
            boss = row.kind == "boss"
            if row.state == "done":
                box_fill = QColor(tokens["BOSS_GOLD" if boss else "ACCENT"])
                box_border = QColor(tokens["BOSS_GOLD_BRIGHT" if boss else "ACCENT_BRIGHT"])
                title_color = QColor(tokens["TEXT"])
                detail_color = QColor(tokens["BOSS_GOLD_BRIGHT" if boss else "ACCENT_BRIGHT"])
                icon_opacity = 1.0
            elif row.state == "open":
                box_fill = QColor(tokens["BG_INPUT"])
                box_border = QColor(tokens["BOSS_GOLD" if boss else "ACCENT"])
                title_color = QColor(tokens["TEXT"])
                detail_color = QColor(tokens["MUTED"])
                icon_opacity = 1.0
            else:
                box_fill = QColor(tokens["BG_INPUT"])
                box_border = QColor(tokens["BOSS_GOLD_DIM" if boss else "BORDER"])
                title_color = QColor(tokens["MUTED_DARK"])
                detail_color = QColor(tokens["MUTED_DARK"])
                icon_opacity = 0.38

            box = QRectF(rect.left() + 5, rect.top() + 4, 22, 22)
            painter.setBrush(box_fill)
            painter.setPen(QPen(box_border, 1.2))
            box_radius = 4.0 if boss else 6.0
            painter.drawRoundedRect(box, box_radius, box_radius)
            icon = self._source_pixmap(row.icon_path, 16)
            if not icon.isNull():
                painter.setOpacity(icon_opacity)
                painter.drawPixmap(int(box.left()) + 3, int(box.top()) + 3, icon)
                painter.setOpacity(1.0)

            self._row_font(painter, 10.0, bold=False)
            title_x = rect.left() + 37
            title_advance = painter.fontMetrics().horizontalAdvance(row.title)
            painter.setPen(title_color)
            painter.drawText(
                QRectF(title_x, rect.top(), rect.width() - 37, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                row.title,
            )

            if row.tag:
                self._row_font(painter, 7.5, bold=True)
                tag_width = painter.fontMetrics().horizontalAdvance(row.tag) + 10
                tag_rect = QRectF(
                    title_x + title_advance + 8, rect.center().y() - 7.5, tag_width, 15
                )
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(tokens["MUTED_DARK"]), 1.0))
                painter.drawRoundedRect(tag_rect, 4.0, 4.0)
                painter.setPen(QColor(tokens["MUTED"]))
                painter.drawText(tag_rect, Qt.AlignCenter, row.tag)

            self._row_font(painter, 9.0, bold=True)
            detail_width = painter.fontMetrics().horizontalAdvance(row.detail)
            painter.setPen(detail_color)
            painter.drawText(
                QRectF(rect.right() - 5 - detail_width, rect.top(), detail_width, rect.height()),
                Qt.AlignRight | Qt.AlignVCenter,
                row.detail,
            )

            if row.fraction is not None and row.state == "open" and rect.width() >= 330:
                bar = QRectF(
                    rect.right() - 5 - detail_width - 10 - 64,
                    rect.center().y() - 2.5,
                    64,
                    5,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(tokens["BG_INPUT"]))
                painter.drawRoundedRect(bar, 2.5, 2.5)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(tokens["BORDER"]), 1.0))
                painter.drawRoundedRect(bar.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)
                filled = max(0.0, min(1.0, row.fraction))
                if filled > 0.0:
                    fill_rect = QRectF(bar)
                    fill_rect.setWidth(max(5.0, bar.width() * filled))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(tokens["ACCENT_BRIGHT"]))
                    painter.drawRoundedRect(fill_rect, 2.5, 2.5)

            if index < len(rows) - 1:
                separator = QColor(tokens["BORDER"])
                separator.setAlpha(120)
                painter.setPen(QPen(separator, 1.0))
                painter.drawLine(
                    rect.left() + 2, rect.bottom(), rect.right() - 2, rect.bottom()
                )
            top += self._ROW_HEIGHT
        return top

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        position = event.position().toPoint()
        for rect, row in self._row_rects:
            if rect.contains(position):
                self.setToolTip(row.tooltip)
                return super().mouseMoveEvent(event)
        self.setToolTip("")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        QToolTip.hideText()
        super().leaveEvent(event)


class _ResponsivePanelPair(QWidget):
    def __init__(
        self,
        first: QWidget,
        second: QWidget,
        *,
        breakpoint: int,
        fill: bool = False,
        equal_height_wide: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("careerResponsivePair")
        self._fill = fill
        self._equal_height_wide = equal_height_wide
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding if fill else QSizePolicy.Maximum,
        )
        self._first = first
        self._second = second
        self._breakpoint = breakpoint
        self._wide: Optional[bool] = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(12)
        self._layout.setVerticalSpacing(12)
        self._reflow(False)

    def _reflow(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        self._layout.removeWidget(self._first)
        self._layout.removeWidget(self._second)
        alignment = (
            Qt.Alignment()
            if self._fill or (wide and self._equal_height_wide)
            else Qt.AlignTop
        )
        if wide:
            self._layout.addWidget(self._first, 0, 0, alignment)
            self._layout.addWidget(self._second, 0, 1, alignment)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 1)
            self._layout.setRowStretch(0, 1 if self._fill else 0)
            self._layout.setRowStretch(1, 0)
        else:
            self._layout.addWidget(self._first, 0, 0, alignment)
            self._layout.addWidget(self._second, 1, 0, alignment)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 0)
            self._layout.setRowStretch(0, 1 if self._fill else 0)
            self._layout.setRowStretch(1, 1 if self._fill else 0)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._reflow(event.size().width() >= self._breakpoint)
        super().resizeEvent(event)


class _ChapterInspectorPage(QFrame):
    """Selected chapter dossier lists backed by one CareerProgressSummary.

    Identity and gate progress live on the Hero (which follows the selected
    stage), so this page deliberately has no header of its own."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("careerInspector")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.race_list = _ChipPreviewCard("RACE SCHEDULE")
        self.milestone_list = _ChipPreviewCard("MILESTONES")
        # The cards carry their own height now, so the pair must not stretch:
        # with fill=True the spare room was shared out around them and left
        # holes above and below.
        # Chips need far less width than the dossier rows did, so the pair
        # splits into two columns long before it used to (1150 kept them
        # stacked in a 1182 window, where they now fit side by side).
        self._body = _ResponsivePanelPair(
            self.race_list, self.milestone_list, breakpoint=820
        )
        root.addWidget(self._body)
        root.addStretch(1)

    def set_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        stage: Optional[int],
    ) -> None:
        if summary is None or stage is None:
            self.race_list.set_items("No race table loaded", ())
            self.milestone_list.set_items("No milestone table loaded", ())
            return

        chapter = summary.chapter(stage)
        requirement = chapter.requirement

        world_rank = {
            _norm_event_id(event_id): position
            for position, event_id in enumerate(
                rival_challenge.WORLD_ORDER.get(stage, ())
            )
        }
        race_rows = [
            _race_row(record, boss=False)
            for record in sorted(
                chapter.races,
                key=lambda r: (
                    world_rank.get(_norm_event_id(r.event_id), 99),
                    _event_sort_key(r),
                ),
            )
        ]
        boss_rows = _boss_series_rows(stage, chapter.boss_races)
        self.race_list.set_items(
            f"{chapter.race_wins}/{requirement.races} wins  ·  "
            f"{len(chapter.races)} events  ·  {len(boss_rows)} boss",
            race_rows,
            boss_rows,
        )

        milestone_rows = []
        for index, record in enumerate(chapter.milestones, 1):
            type_info = milestone_names.type_label_and_unit(record.type_key)
            title = type_info[0] if type_info is not None else f"Milestone {index}"
            required = _milestone_display(record.type_key, record.required_value)
            recorded = _milestone_display(record.type_key, record.recorded_value)
            # No progress bar: GMilestone.recorded stays zero while active
            # (the game writes it only at award time), so a bar could never
            # show anything but 0%. Speedtrap rows below keep theirs —
            # best_speed is live data.
            if record.is_awarded:
                state = "done"
                detail = f"AWARDED · {recorded}"
            else:
                state = "open"
                detail = f"{recorded} / {required}"
            status = "awarded" if record.is_awarded else f"state {record.state}"
            milestone_rows.append(_InspectorRow(
                title=title,
                tag="",
                state=state,
                kind="milestone",
                icon_path=_milestone_icon(record.type_key),
                detail=detail,
                fraction=None,
                tooltip=(
                    f"{title} — {status}\n"
                    f"Required {required} · recorded {recorded}"
                ),
            ))
        traps_in_route_order = sorted(
            chapter.speedtraps,
            key=lambda trap: milestone_names.speedtrap_ordinal(trap.trap_hash) or 99,
        )
        for index, trap in enumerate(traps_in_route_order, 1):
            ordinal = milestone_names.speedtrap_ordinal(trap.trap_hash) or index
            required_mph = trap.required_speed * 2.2369362920544
            best_mph = trap.best_speed * 2.2369362920544
            best = f"{best_mph:.1f} mph" if trap.best_speed > 0 else "—"
            # The 0..5 counter is chapter-wide (shared by every trap record of
            # the bin), so it never appears on individual rows — only the
            # trap's own speeds do; the shared counter stays in the tooltip.
            if trap.is_complete:
                state = "done"
                detail = f"DONE · BEST {best_mph:.0f} MPH" if trap.best_speed > 0 else "DONE"
                fraction: Optional[float] = None
            else:
                state = "open"
                if trap.best_speed > 0:
                    detail = f"BEST {best_mph:.0f} / {required_mph:.0f} MPH"
                    fraction = best_mph / required_mph if required_mph > 0 else None
                else:
                    detail = f"REQ {required_mph:.0f} MPH"
                    fraction = None
            milestone_rows.append(_InspectorRow(
                title=f"Speedtrap {ordinal}",
                tag="",
                state=state,
                kind="trap",
                icon_path=game_icon_path("trap"),
                detail=detail,
                fraction=fraction,
                tooltip=(
                    f"Speedtrap {ordinal} — required {required_mph:.1f} mph\n"
                    f"Chapter counter {trap.counter}/{career_progress.SPEEDTRAP_COMPLETE_COUNT}"
                    f" · best {best}"
                ),
            ))
        self.milestone_list.set_items(
            f"{chapter.milestone_wins}/{requirement.milestones} wins  ·  "
            f"{chapter.milestone_total} available",
            milestone_rows,
        )


def _fmt_race_time(seconds: float) -> str:
    if seconds < 60.0:
        return f"{seconds:.2f}"
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:05.2f}"


def _race_best_result(record: career_progress.RaceRecord, type_label: str) -> Optional[str]:
    """Human reading of the race-table high_score field.

    The u32 stores IEEE-754 float bits: the best TIME in seconds for every
    mode except speedtrap races, which accumulate a speed score (the HUD's
    running total). Out-of-range values fall back to the raw int."""
    if record.high_score == 0:
        return None
    value = struct.unpack("<f", struct.pack("<I", record.high_score))[0]
    if not 1.0 <= value < 100_000.0:
        return f"{record.high_score:,}"
    if type_label == "Speedtrap":
        return f"SCORE {value:,.0f}"
    return _fmt_race_time(value)


def _race_row(record: career_progress.RaceRecord, *, boss: bool) -> _InspectorRow:
    event = record.event_id or f"slot {record.index}"
    fallback = f"Event {event[:-2] if event.endswith('.r') else event}"
    # A few save slots track a route with a different EventID (slot 8.3.2
    # drives 13.3.1.r); name, type and icon follow the DRIVEN route.
    route_id = rival_challenge.ROUTE_REMAP.get(record.event_id or "", record.event_id)
    title = race_display_names.display_name(route_id) or fallback
    type_label = race_display_names.type_label(route_id) or "Event"
    kind_line = f"{type_label} · {record.event_id}" + (" · boss race" if boss else "")
    if route_id != record.event_id:
        kind_line += f" · route {route_id}"
    if record.is_completed:
        state = "done"
        best = _race_best_result(record, type_label)
        detail = f"WON · {best}" if best else "WON"
        tooltip_detail = (
            f"completed{f' · best {best}' if best else ''}\n"
            f"top {record.top_speed:.1f} · avg {record.average_speed:.1f}"
        )
    elif record.flags & career_progress.RACE_FLAG_UNLOCKED_CAREER:
        state = "open"
        detail = "AVAILABLE"
        tooltip_detail = "available"
    else:
        state = "locked"
        detail = "LOCKED"
        tooltip_detail = "locked"
    reversed_route = record.is_reversed or bool(route_id and route_id.endswith(".r"))
    return _InspectorRow(
        title=title,
        tag="REVERSED" if reversed_route else "",
        state=state,
        kind="boss" if boss else "race",
        icon_path=game_icon_path(_race_type_icon(route_id)),
        detail=detail,
        fraction=None,
        tooltip=f"{title} — {tooltip_detail}\n{kind_line}",
    )


class CareerMixin:
    def _build_career_page(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(0)
        self.career_canvas = QWidget()
        self.career_canvas.setObjectName("careerCanvas")
        # Keep a ceiling for ultra-wide monitors, but anchor the canvas to the
        # nav side: leftover width goes right, not into a nav/content gutter.
        self.career_canvas.setMaximumWidth(1800)
        self.career_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self.career_canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        outer.addWidget(self.career_canvas, 1)
        # Zero stretch: the spacer stays empty until the canvas reaches its
        # ceiling, so no strip of width is held back on ordinary monitors.
        outer.addStretch(0)

        self.career_donor_root = default_user_career_donor_root()
        self.career_donor_library: tuple[CareerDonorEntry, ...] = ()
        self._career_donor_signature: Optional[tuple] = None
        self._career_snapshot_cache: Optional[bytes] = None
        self._career_summary_cache: Optional[career_progress.CareerProgressSummary] = None
        self._career_selected_stage: Optional[int] = None
        self._career_defeated_stamp: Optional[QPixmap] = None

        # ── Current target hero + compact progression summary ──
        self.career_hero = _CareerHero()
        self._career_hero_transition: Optional[ThemeTransitionOverlay] = None
        hero_layout = QHBoxLayout(self.career_hero)
        hero_layout.setContentsMargins(28, 0, 20, 0)
        hero_layout.setSpacing(14)

        # Vertical spacing here is not authored by hand: the column keeps one
        # optical step between every block and both card edges.
        self.career_hero_copy = _HeroRhythmColumn()
        hero_copy = self.career_hero_copy

        eyebrow = QLabel("BLACKLIST")
        eyebrow.setObjectName("careerHeroEyebrow")
        eyebrow.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.career_hero_eyebrow = eyebrow
        hero_copy.addWidget(eyebrow)
        hero_copy.set_ink_source(0, eyebrow)

        headline = QHBoxLayout()
        headline.setSpacing(12)
        self.career_stage_value = QLabel("-")
        self.career_stage_value.setObjectName("careerHeroRank")
        _apply_hero_display_font(self.career_stage_value)
        self.career_stage_value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        headline.addWidget(self.career_stage_value)
        self.career_boss_value = QLabel("NO SAVE LOADED")
        self.career_boss_value.setObjectName("careerHeroBoss")
        _apply_hero_display_font(self.career_boss_value)
        self.career_boss_value.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        headline.addWidget(self.career_boss_value)
        self.career_hero_status = QLabel("NO DATA")
        self.career_hero_status.setObjectName("careerHeroStatus")
        self.career_hero_status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        headline.addWidget(self.career_hero_status, 0, Qt.AlignVCenter)
        headline.addStretch(1)
        hero_copy.addLayout(headline)
        hero_copy.set_ink_source(
            1, self.career_stage_value, sample=_RANK_INK_SAMPLE
        )
        self.career_hero_tagline = _HeroTagline()
        self.career_hero_tagline.setObjectName("careerHeroTagline")
        # 680: Bull's canon sentence is the longest at 653px, so at the banner's
        # full width every rival's tagline still shows whole. Below that the
        # label elides rather than wrapping - see _HeroTagline.
        self.career_hero_tagline.setMaximumWidth(680)
        self.career_hero_tagline.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.career_hero_tagline.setVisible(False)
        hero_copy.addWidget(self.career_hero_tagline)
        hero_copy.set_ink_source(
            2, self.career_hero_tagline, sample=_TAGLINE_INK_SAMPLE
        )

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.career_races_value = QLabel("-")
        self.career_races_metric = self._build_career_hero_metric(
            "RACE WINS", self.career_races_value, "race"
        )
        metrics.addWidget(self.career_races_metric)
        self.career_milestones_value = QLabel("-")
        self.career_milestones_metric = self._build_career_hero_metric(
            "MILESTONES", self.career_milestones_value, "milestone"
        )
        metrics.addWidget(self.career_milestones_metric)
        self.career_bounty_value = QLabel("-")
        self.career_bounty_metric = self._build_career_hero_metric(
            "BOUNTY", self.career_bounty_value, "bounty"
        )
        metrics.addWidget(self.career_bounty_metric)
        metrics.addStretch(1)
        hero_copy.addLayout(metrics)

        # ── View switch: safe progress overview | stage change ──
        self.career_view_switch = AnimatedSegmentedControl(
            ("PROGRESS", "CHANGE RIVAL"),
            button_object_name="careerViewTab",
            fixed_height=42,
        )
        self.career_view_switch.setFixedWidth(280)
        self.career_view_rapsheet_btn = self.career_view_switch.button(0)
        self.career_view_transplant_btn = self.career_view_switch.button(1)
        hero_switch_row = QHBoxLayout()
        hero_switch_row.addWidget(self.career_view_switch)
        hero_switch_row.addStretch(1)
        hero_copy.addLayout(hero_switch_row)

        hero_layout.addLayout(hero_copy, 3)
        hero_layout.addStretch(2)
        layout.addWidget(self.career_hero)

        self.career_view_stack = AnimatedStackedWidget(duration_ms=180)
        self._career_view_transition: Optional[ThemeTransitionOverlay] = None
        self.career_view_stack.addWidget(self._build_career_transplant_view())
        self.career_view_stack.addWidget(self._build_career_progress_view())
        self.career_view_stack.setCurrentIndex(1)
        self.career_view_switch.currentChanged.connect(self._on_career_view_changed)
        layout.addWidget(self.career_view_stack, 1)

        self._reload_career_donor_library(force=True)
        self._rebuild_career_stage_list()
        self._refresh_career_preview()
        self._refresh_career_progress(None, animate=False)
        return w

    def _build_career_hero_metric(
        self, caption: str, value: QLabel, icon_name: str
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("careerHeroMetric")
        frame.setProperty("met", False)
        frame.setFixedSize(204, 76)
        metric_layout = QHBoxLayout(frame)
        metric_layout.setContentsMargins(12, 9, 14, 9)
        metric_layout.setSpacing(10)

        icon_path = game_icon_path(icon_name)
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon = QLabel()
                icon.setObjectName("careerHeroMetricIcon")
                icon.setFixedSize(32, 32)
                icon.setAlignment(Qt.AlignCenter)
                icon.setPixmap(self._tight_icon(
                    icon_path, QSize(30, 30)
                ).pixmap(30, 30))
                metric_layout.addWidget(icon, 0, Qt.AlignVCenter)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(0)
        value.setObjectName("careerHeroMetricValue")
        value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label = QLabel(caption)
        label.setObjectName("careerHeroMetricLabel")
        copy.addWidget(value)
        copy.addWidget(label)
        metric_layout.addLayout(copy)
        return frame

    def _build_career_transplant_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("careerTransplantView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(0)

        target_card, target_layout = self._make_card_frame(
            object_name="careerTargetPanel",
            vertical_policy=QSizePolicy.Preferred,
        )
        self.career_target_panel = target_card
        target_layout.setContentsMargins(18, 16, 18, 16)
        target_layout.setSpacing(9)
        step = QLabel("STEP 01")
        step.setObjectName("careerStepLabel")
        target_layout.addWidget(step)
        title = QLabel("Pick the target chapter")
        title.setObjectName("careerPanelTitle")
        target_layout.addWidget(title)
        intro = QLabel(
            "Choose where the Blacklist story should resume. Only stages backed by "
            "a validated donor snapshot can be selected."
        )
        intro.setObjectName("careerPanelCopy")
        intro.setWordWrap(True)
        target_layout.addWidget(intro)

        self.career_variant_switch = AnimatedSegmentedControl(
            ("CHAPTER START", "CHALLENGE RIVAL"),
            button_object_name="careerVariantButton",
        )
        self.career_variant_start = self.career_variant_switch.button(0)
        self.career_variant_ready = self.career_variant_switch.button(1)
        self.career_variant_switch.currentChanged.connect(self._on_career_variant_changed)
        target_layout.addWidget(self.career_variant_switch)

        self.career_stage_grid_host = QWidget()
        self.career_stage_grid_host.setObjectName("careerStageGrid")
        stage_grid = QGridLayout(self.career_stage_grid_host)
        stage_grid.setContentsMargins(0, 2, 0, 2)
        stage_grid.setHorizontalSpacing(6)
        stage_grid.setVerticalSpacing(6)
        self.career_stage_buttons: Dict[int, QPushButton] = {}
        self.career_stage_group = QButtonGroup(view)
        self.career_stage_group.setExclusive(True)
        for pos, stage in enumerate(range(15, 0, -1)):
            button = QPushButton(f"#{stage}  {BLACKLIST_BOSS_NAMES.get(stage, '?').upper()}")
            button.setObjectName("careerStageButton")
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("stage", stage)
            button.toggled.connect(
                lambda checked, s=stage: self._on_career_stage_toggled(s, checked)
            )
            self.career_stage_group.addButton(button)
            self.career_stage_buttons[stage] = button
            stage_grid.addWidget(button, pos // 3, pos % 3)
        for column in range(3):
            stage_grid.setColumnStretch(column, 1)
        target_layout.addWidget(self.career_stage_grid_host, 1)

        self.career_library_status = QLabel("")
        self.career_library_status.setObjectName("careerLibraryStatus")
        target_layout.addWidget(self.career_library_status)

        review_card, review_layout = self._make_card_frame(
            object_name="careerReviewPanel",
            vertical_policy=QSizePolicy.Preferred,
        )
        review_layout.setContentsMargins(18, 16, 18, 16)
        review_layout.setSpacing(9)
        self.career_review_panel = review_card
        self._career_review_transition: Optional[ThemeTransitionOverlay] = None
        step = QLabel("STEP 02")
        step.setObjectName("careerStepLabel")
        review_layout.addWidget(step)
        title = QLabel("Review the transfer")
        title.setObjectName("careerPanelTitle")
        review_layout.addWidget(title)

        route = QFrame()
        route.setObjectName("careerRoute")
        route_layout = QHBoxLayout(route)
        route_layout.setContentsMargins(12, 10, 12, 10)
        route_layout.setSpacing(8)
        self.career_route_from = QLabel("OPEN A SAVE")
        self.career_route_from.setObjectName("careerRouteStage")
        self.career_route_from.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(self.career_route_from, 1)
        arrow = QLabel("→")
        arrow.setObjectName("careerRouteArrow")
        arrow.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(arrow)
        self.career_route_to = QLabel("SELECT TARGET")
        self.career_route_to.setObjectName("careerRouteStage")
        self.career_route_to.setAlignment(Qt.AlignCenter)
        route_layout.addWidget(self.career_route_to, 1)
        review_layout.addWidget(route)

        self.career_preview_status = QLabel("")
        self.career_preview_status.setObjectName("careerPreviewStatus")
        self.career_preview_status.setWordWrap(True)
        # Normal previews vary between one and four lines (same-stage warning,
        # bounty compensation, donor warnings). Keep the full four-line slot so
        # changing targets cannot alter sizeHint and nudge the whole workflow.
        self.career_preview_status.setFixedHeight(96)
        self.career_preview_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        review_layout.addWidget(self.career_preview_status)

        impact_row = QHBoxLayout()
        impact_row.setSpacing(8)
        changes, changes_layout = self._build_career_impact_box("CHANGES", "changes")
        self.career_preview_changes = QLabel(
            "Career stage\nRace & milestone progress\nStory SMS & shop unlocks"
        )
        self.career_preview_changes.setObjectName("careerImpactItems")
        self.career_preview_changes.setWordWrap(True)
        changes_layout.addWidget(self.career_preview_changes)
        impact_row.addWidget(changes, 1)
        keeps, keeps_layout = self._build_career_impact_box("STAYS YOURS", "keeps")
        self.career_preview_keeps = QLabel(
            "Money & profile alias\nCars, parts & garage stats\nJunkman inventory"
        )
        self.career_preview_keeps.setObjectName("careerImpactItems")
        self.career_preview_keeps.setWordWrap(True)
        keeps_layout.addWidget(self.career_preview_keeps)
        impact_row.addWidget(keeps, 1)
        review_layout.addLayout(impact_row)

        self.career_preview_caveat = QLabel(_BOUNTY_CAVEAT_TEXT)
        self.career_preview_caveat.setObjectName("careerSafetyNote")
        self.career_preview_caveat.setWordWrap(True)
        review_layout.addWidget(self.career_preview_caveat)
        review_layout.addStretch(1)

        self.btn_career_transplant = self._make_card_action_button(
            "APPLY STAGE TO MEMORY", object_name="careerTransplantButton"
        )
        self.btn_career_transplant.setMinimumHeight(42)
        self.btn_career_transplant.setCursor(Qt.PointingHandCursor)
        self.btn_career_transplant.clicked.connect(self._on_career_transplant_clicked)
        review_layout.addWidget(self.btn_career_transplant)
        disk_note = QLabel("Disk stays untouched until you choose Save + backup.")
        disk_note.setObjectName("careerDiskNote")
        disk_note.setAlignment(Qt.AlignCenter)
        review_layout.addWidget(disk_note)

        self.career_transplant_pair = _ResponsivePanelPair(
            target_card,
            review_card,
            breakpoint=1200,
            equal_height_wide=True,
        )
        layout.addWidget(self.career_transplant_pair, 0, Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setObjectName("cardScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(view)
        return scroll

    def _build_career_impact_box(
        self, title: str, impact: str
    ) -> tuple[QFrame, QVBoxLayout]:
        box = QFrame()
        box.setObjectName("careerImpactBox")
        box.setProperty("impact", impact)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(11, 9, 11, 9)
        box_layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("careerImpactTitle")
        box_layout.addWidget(heading)
        return box, box_layout

    # ── Rap Sheet view (read-only dossier) ─────────────────────

    def _build_career_progress_view(self) -> QWidget:
        host = QWidget()
        host.setObjectName("careerProgressView")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 6, 0)
        host_layout.setSpacing(10)
        host_layout.setAlignment(Qt.AlignTop)

        self.career_timeline = _BlacklistTimeline()
        self.career_timeline.stageSelected.connect(self._on_career_timeline_selected)
        host_layout.addWidget(self.career_timeline)

        self.career_inspector_stack = AnimatedStackedWidget(
            duration_ms=_BlacklistTimeline._SELECTION_DURATION_MS
        )
        self._career_inspector_transition: Optional[ThemeTransitionOverlay] = None
        self.career_inspector_stack.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        self.career_inspector_pages = (_ChapterInspectorPage(), _ChapterInspectorPage())
        for page in self.career_inspector_pages:
            self.career_inspector_stack.addWidget(page)
        self.career_inspector_stack.setCurrentIndex(0)
        self.career_inspector_stack.currentChanged.connect(
            self._sync_career_inspector_height
        )
        self._sync_career_inspector_height(0)
        # The stack takes the spare room so the plate can close the page from
        # the bottom.  A stretch in the host layout instead would push the
        # plate past the footer: with nothing to scroll, the content widget is
        # stretched to a viewport that runs under it.
        host_layout.addWidget(self.career_inspector_stack, 1)
        self.career_totals_plate = self._build_career_totals_plate()
        host_layout.addWidget(self.career_totals_plate)

        scroll = QScrollArea()
        scroll.setObjectName("cardScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(host)
        return scroll

    def _sync_career_inspector_height(self, index: int) -> None:
        """Let the stack follow the page on screen.

        The inspector exists twice so stages can crossfade, and a stack asks
        every page for its hint and keeps the tallest.  The off-screen twin has
        never had a real width, so its panel pair still thinks it is stacked and
        asks for two rows - which showed up as a hole between the cards and the
        totals plate.
        """
        for position, page in enumerate(self.career_inspector_pages):
            page.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Preferred if position == index else QSizePolicy.Ignored,
            )
            page.updateGeometry()

    def _build_career_totals_plate(self) -> QFrame:
        """Lifetime totals as the page's closing plate.

        They used to ride in the shell footer, where they were chrome shared
        with every other page's actions.  They belong to Career, so they sit at
        the end of Career: one panel, four cells of equal width, hairlines
        between them.
        """
        plate = QFrame()
        plate.setObjectName("careerTotalsPlate")
        plate.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(plate)
        row.setContentsMargins(24, 22, 24, 22)
        row.setSpacing(0)
        self.career_total_races_value = QLabel("—")
        self.career_total_milestones_value = QLabel("—")
        self.career_total_bounty_value = QLabel("—")
        self.career_total_prologue_value = QLabel("—")
        cells = (
            ("race", "RACES", self.career_total_races_value),
            ("milestone", "MILESTONES", self.career_total_milestones_value),
            ("bounty", "BOUNTY", self.career_total_bounty_value),
            ("rival_race", "PROLOGUE", self.career_total_prologue_value),
        )
        for position, (icon_name, caption, value) in enumerate(cells):
            if position:
                divider = QFrame()
                divider.setObjectName("careerTotalsDivider")
                divider.setFrameShape(QFrame.NoFrame)
                divider.setFixedWidth(1)
                divider.setFixedHeight(38)
                row.addWidget(divider, 0, Qt.AlignVCenter)
            cell = QWidget()
            cell.setObjectName("careerTotalsCell")
            cell_row = QHBoxLayout(cell)
            cell_row.setContentsMargins(0, 0, 0, 0)
            cell_row.setSpacing(16)
            cell_row.addStretch(1)
            icon_path = game_icon_path(icon_name)
            if icon_path is not None:
                icon = QLabel()
                icon.setObjectName("careerTotalsIcon")
                icon.setFixedSize(32, 32)
                icon.setAlignment(Qt.AlignCenter)
                icon.setPixmap(self._tight_icon(
                    icon_path, QSize(30, 30)
                ).pixmap(30, 30))
                cell_row.addWidget(icon, 0, Qt.AlignVCenter)
            copy = QVBoxLayout()
            copy.setContentsMargins(0, 0, 0, 0)
            copy.setSpacing(0)
            caption_label = QLabel(caption)
            caption_label.setObjectName("careerTotalsCaption")
            value.setObjectName("careerTotalsValue")
            copy.addWidget(caption_label)
            copy.addWidget(value)
            cell_row.addLayout(copy)
            cell_row.addStretch(1)
            row.addWidget(cell, 1)
        return plate

    def _on_career_view_changed(self, index: int) -> None:
        view_snapshot = self._career_crossfade_snapshot(
            self.career_view_stack, "_career_view_transition"
        )
        target = 1 if index == 0 else 0
        summary = self._career_summary_cache
        if summary is not None:
            hero_stage = (
                self._career_selected_stage if index == 0 else summary.current_stage
            )
            self._update_career_hero(summary, hero_stage)
        if index == 1:
            self._rebuild_career_stage_list(
                preferred_stage=summary.current_stage if summary is not None else None
            )
            self._refresh_career_preview()
        self.career_view_stack.setCurrentIndex(target)
        self.career_view_stack.updateGeometry()
        self._start_career_crossfade(
            self.career_view_stack,
            view_snapshot,
            "_career_view_transition",
            "careerViewTransitionOverlay",
        )

    def _on_career_timeline_selected(self, stage: int) -> None:
        summary = self._career_summary_cache
        if summary is None or stage == self._career_selected_stage:
            return
        hero_snapshot = self._career_crossfade_snapshot(
            self.career_hero, "_career_hero_transition"
        )
        inspector_snapshot = self._career_crossfade_snapshot(
            self.career_inspector_stack, "_career_inspector_transition"
        )
        self._career_selected_stage = stage
        self.career_timeline.set_selected_stage(stage)
        self._update_career_hero(summary, stage)
        target_index = 1 - self.career_inspector_stack.currentIndex()
        self.career_inspector_pages[target_index].set_progress(summary, stage)
        self.career_inspector_pages[target_index].updateGeometry()
        self.career_inspector_stack.setCurrentIndex(target_index)
        self.career_inspector_stack.updateGeometry()
        self._start_career_crossfade(
            self.career_hero,
            hero_snapshot,
            "_career_hero_transition",
            "careerHeroTransitionOverlay",
        )
        self._start_career_crossfade(
            self.career_inspector_stack,
            inspector_snapshot,
            "_career_inspector_transition",
            "careerInspectorTransitionOverlay",
        )

    def _refresh_career_progress(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        *,
        animate: bool,
    ) -> None:
        if summary is not None and self._career_selected_stage is None:
            self._career_selected_stage = summary.default_stage
        stage = self._career_selected_stage if summary is not None else None
        self.career_timeline.set_progress(summary, stage)
        current = self.career_inspector_stack.currentIndex()
        self.career_inspector_pages[current].set_progress(summary, stage)
        self.career_inspector_pages[current].updateGeometry()
        self.career_inspector_stack.updateGeometry()
        self._update_career_totals(summary)
        self._update_career_hero(summary, stage)

    def _update_career_totals(
        self, summary: Optional[career_progress.CareerProgressSummary]
    ) -> None:
        if summary is None:
            for label in (
                self.career_total_races_value,
                self.career_total_milestones_value,
                self.career_total_bounty_value,
                self.career_total_prologue_value,
            ):
                label.setText("—")
            if hasattr(self, "_sync_footer_context_visibility"):
                self._sync_footer_context_visibility()
            return
        self.career_total_races_value.setText(
            f"{summary.lifetime_race_wins} / {summary.lifetime_race_total}"
        )
        self.career_total_milestones_value.setText(
            f"{summary.lifetime_milestone_wins} / {summary.lifetime_milestone_total}"
        )
        self.career_total_bounty_value.setText(_fmt_compact(summary.total_bounty))
        prologue_done = sum(record.is_completed for record in summary.prologue_races)
        self.career_total_prologue_value.setText(
            f"{prologue_done} / {len(summary.prologue_races)}"
        )
        if hasattr(self, "_sync_footer_context_visibility"):
            self._sync_footer_context_visibility()

    def _update_career_hero(
        self,
        summary: Optional[career_progress.CareerProgressSummary],
        stage: Optional[int],
    ) -> None:
        if summary is None or stage is None:
            self.career_hero.set_stage(None)
            self.career_stage_value.setText("-")
            self.career_boss_value.setText("NO SAVE LOADED")
            self.career_hero_tagline.setVisible(False)
            self.career_hero_tagline.clear()
            self.career_hero_tagline.setToolTip("")
            self._set_career_hero_status("NO DATA", "locked")
            for frame, label in (
                (self.career_races_metric, self.career_races_value),
                (self.career_milestones_metric, self.career_milestones_value),
                (self.career_bounty_metric, self.career_bounty_value),
            ):
                self._set_career_metric(frame, label, "-", False)
            self._polish_career_hero_status()
            return

        chapter = summary.chapter(stage)
        requirement = chapter.requirement
        state = summary.stage_state(stage)
        status_text = {
            "defeated": "DEFEATED",
            "current": "CURRENT TARGET",
            "boss_ready": "BOSS READY",
            "locked": "LOCKED",
        }[state]
        if summary.endgame and stage == 1:
            status_text = "BLACKLIST CLEARED"
        boss = BLACKLIST_BOSS_NAMES.get(stage, "Unknown")
        self.career_hero.set_stage(stage)
        self.career_stage_value.setText(f"#{stage}")
        self.career_boss_value.setText(boss.upper())
        tagline = rival_bios.tagline(stage)
        if tagline:
            self.career_hero_tagline.setText(tagline)
            self.career_hero_tagline.setToolTip(rival_bios.bio(stage) or "")
            self.career_hero_tagline.setVisible(True)
        else:
            self.career_hero_tagline.setVisible(False)
            self.career_hero_tagline.clear()
            self.career_hero_tagline.setToolTip("")
        self._set_career_hero_status(status_text, state)
        self._set_career_metric(
            self.career_races_metric,
            self.career_races_value,
            f"{chapter.race_wins} / {requirement.races}",
            chapter.race_wins >= requirement.races,
        )
        self._set_career_metric(
            self.career_milestones_metric,
            self.career_milestones_value,
            f"{chapter.milestone_wins} / {requirement.milestones}",
            chapter.milestone_wins >= requirement.milestones,
        )
        self._set_career_metric(
            self.career_bounty_metric,
            self.career_bounty_value,
            f"{_fmt_compact(summary.total_bounty)} / {_fmt_compact(requirement.bounty)}",
            summary.total_bounty >= requirement.bounty,
        )
        self._polish_career_hero_status()

    @staticmethod
    def _set_career_metric(frame: QFrame, label: QLabel, text: str, met: bool) -> None:
        label.setText(text)
        if frame.property("met") != met:
            frame.setProperty("met", met)
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def _polish_career_hero_status(self) -> None:
        self.career_hero_status.style().unpolish(self.career_hero_status)
        self.career_hero_status.style().polish(self.career_hero_status)

    def _set_career_hero_status(self, text: str, state: str) -> None:
        label = self.career_hero_status
        label.clear()
        label.setProperty("state", state)
        label.setAccessibleName(text)
        label.setToolTip(text if state == "defeated" else "")
        stamp = self._defeated_stamp_pixmap() if state == "defeated" else QPixmap()
        self.career_hero.set_defeated_stamp(stamp)
        show_portrait_stamp = state == "defeated" and not stamp.isNull()
        self.career_hero.setAccessibleDescription(
            "DEFEATED" if state == "defeated" else ""
        )
        label.setProperty("stamp", False)
        label.setHidden(state == "current" or show_portrait_stamp)

        if state == "current" or show_portrait_stamp:
            label.setMinimumSize(0, 0)
            label.setMaximumSize(QSize(16777215, 16777215))
            label.updateGeometry()
            return

        label.setMinimumSize(0, 0)
        label.setMaximumSize(QSize(16777215, 16777215))
        label.setText(text)
        label.updateGeometry()

    def _defeated_stamp_pixmap(self) -> QPixmap:
        if self._career_defeated_stamp is not None:
            return self._career_defeated_stamp

        path = game_icon_path("status_defeated")
        if path is None:
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        # Keep the game texture at native resolution through tinting and rotation.
        # The previous 146x36 intermediate was later enlarged to 175/210 px in the
        # Hero, so its already-antialiased edges became visibly soft.  These
        # reference dimensions now define composition only; all raster work stays
        # at the source texture's substantially larger native scale.
        source_texture = QPixmap(str(path))
        if source_texture.isNull():
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        reference_source = QSize(146, 36)
        render_scale = source_texture.height() / reference_source.height()
        source = QPixmap(
            round(reference_source.width() * render_scale),
            source_texture.height(),
        )
        source.fill(Qt.transparent)
        source_painter = QPainter(source)
        source_painter.drawPixmap(
            (source.width() - source_texture.width()) // 2,
            0,
            source_texture,
        )
        source_painter.end()
        if source.isNull():
            self._career_defeated_stamp = QPixmap()
            return self._career_defeated_stamp

        def tinted_layer(color: str) -> QPixmap:
            layer = QPixmap(source.size())
            layer.fill(Qt.transparent)
            layer_painter = QPainter(layer)
            layer_painter.drawPixmap(0, 0, source)
            layer_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            layer_painter.fillRect(layer.rect(), QColor(color))
            layer_painter.end()
            return layer

        # The game stamp is not a flat red mask: weak ink reads almost black while
        # dense lettering and frame edges carry the brighter crimson.  Layering the
        # same worn mask in two tones recreates that range on our uniform navy Hero
        # instead of making every variation look like blue background transparency.
        dark_ink = tinted_layer("#430506")
        bright_ink = tinted_layer("#930A0A")
        inked = QPixmap(source.size())
        inked.fill(Qt.transparent)
        painter = QPainter(inked)
        backing = QPainterPath()
        backing.moveTo(3.0, 5.0)
        backing.lineTo(141.0, 1.0)
        backing.lineTo(145.0, 27.0)
        backing.lineTo(139.0, 33.0)
        backing.lineTo(7.0, 35.0)
        backing.lineTo(1.0, 30.0)
        backing.closeSubpath()
        painter.save()
        painter.scale(render_scale, render_scale)
        painter.fillPath(backing, QColor(7, 8, 9, 234))
        painter.restore()
        painter.drawPixmap(0, 0, dark_ink)
        painter.drawPixmap(0, 0, bright_ink)
        painter.end()

        rotated = inked.transformed(
            QTransform().rotate(-4.0), Qt.SmoothTransformation
        )
        canvas = QPixmap(round(180 * render_scale), round(56 * render_scale))
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(
            (canvas.width() - rotated.width()) // 2,
            (canvas.height() - rotated.height()) // 2,
            rotated,
        )
        painter.end()
        self._career_defeated_stamp = canvas
        return canvas

    # ── Library / list state ───────────────────────────────────

    def _career_donor_directory_signature(self) -> tuple:
        root = Path(self.career_donor_root)
        if not root.is_dir():
            return ()
        entries = []
        try:
            for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file():
                    continue
                stat = path.stat()
                entries.append((path.name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            return ()
        return tuple(entries)

    def _reload_career_donor_library(self, *, force: bool = False) -> None:
        signature = self._career_donor_directory_signature()
        if not force and signature == self._career_donor_signature:
            return
        try:
            self.career_donor_library = load_career_donor_library(self.career_donor_root)
        except Exception:
            self.career_donor_library = ()
        self._career_donor_signature = signature

    def _career_selected_variant(self) -> str:
        if self.career_variant_switch.currentIndex() == 1:
            return VARIANT_BOSS_READY
        return VARIANT_CHAPTER_START

    def _career_donors_for_variant(self, variant: str) -> Dict[int, CareerDonorEntry]:
        donors: Dict[int, CareerDonorEntry] = {}
        for entry in self.career_donor_library:
            if entry.is_loadable and entry.variant == variant and entry.stage_bin not in donors:
                donors[entry.stage_bin] = entry
        return donors

    def _rebuild_career_stage_list(
        self, *, preferred_stage: Optional[int] = None
    ) -> None:
        selected_stage = (
            preferred_stage
            if preferred_stage is not None
            else self._selected_career_stage()
        )
        donors = self._career_donors_for_variant(self._career_selected_variant())
        if selected_stage not in donors:
            current = (
                career_transplant.read_current_bin(bytes(self.savefile.data))
                if self.savefile is not None else None
            )
            selected_stage = (
                current
                if current in donors
                else (max(donors) if donors and self.savefile is not None else None)
            )
        for stage, button in self.career_stage_buttons.items():
            button.blockSignals(True)
            available = stage in donors
            button.setEnabled(available)
            button.setChecked(available and stage == selected_stage)
            button.setToolTip(
                "" if available else "No donor save for this stage in the library"
            )
            button.blockSignals(False)
        variant_label = (
            "boss-ready" if self._career_selected_variant() == VARIANT_BOSS_READY
            else "chapter-start"
        )
        self.career_library_status.setText(
            f"{len(donors)} / 15 {variant_label} donor snapshots ready"
        )

    def _selected_career_stage(self) -> Optional[int]:
        for stage, button in self.career_stage_buttons.items():
            if button.isChecked() and button.isEnabled():
                return stage
        return None

    def _selected_career_donor(self) -> Optional[CareerDonorEntry]:
        stage = self._selected_career_stage()
        if stage is None:
            return None
        return self._career_donors_for_variant(self._career_selected_variant()).get(stage)

    def _on_career_stage_toggled(self, _stage: int, checked: bool) -> None:
        if checked:
            snapshot = self._career_crossfade_snapshot(
                self.career_review_panel, "_career_review_transition"
            )
            self._refresh_career_preview()
            self._start_career_crossfade(
                self.career_review_panel,
                snapshot,
                "_career_review_transition",
                "careerReviewTransitionOverlay",
            )

    def _clear_career_crossfade(self, transition_attribute: str) -> None:
        overlay = getattr(self, transition_attribute, None)
        setattr(self, transition_attribute, None)
        if overlay is not None:
            overlay.finish_immediately()

    def _career_crossfade_snapshot(
        self, widget: QWidget, transition_attribute: str
    ) -> QPixmap:
        self._clear_career_crossfade(transition_attribute)
        if not widget.isVisible() or widget.size().isEmpty():
            return QPixmap()
        return widget.grab()

    def _start_career_crossfade(
        self,
        widget: QWidget,
        snapshot: QPixmap,
        transition_attribute: str,
        object_name: str,
    ) -> None:
        if snapshot.isNull() or snapshot.size().isEmpty():
            return
        overlay = ThemeTransitionOverlay(
            widget,
            snapshot,
            duration_ms=_CAREER_CROSSFADE_MS,
        )
        overlay.setObjectName(object_name)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.destroyed.connect(
            lambda _obj=None, overlay=overlay, attr=transition_attribute: (
                setattr(self, attr, None)
                if getattr(self, attr, None) is overlay
                else None
            )
        )
        setattr(self, transition_attribute, overlay)
        overlay.start()

    # ── Refresh / preview ──────────────────────────────────────

    def _refresh_career_page(self) -> None:
        data = bytes(self.savefile.data) if self.savefile is not None else b""
        previous = self._career_summary_cache
        snapshot_changed = data != self._career_snapshot_cache
        if snapshot_changed:
            self._career_snapshot_cache = data
            self._career_summary_cache = career_progress.build_career_progress(data)
        summary = self._career_summary_cache
        if summary is None:
            self._career_selected_stage = None
        elif (
            self._career_selected_stage is None
            or previous is None
            or previous.current_stage != summary.current_stage
            or previous.endgame != summary.endgame
        ):
            self._career_selected_stage = summary.default_stage

        self._refresh_career_progress(summary, animate=False)
        self._reload_career_donor_library()
        current_bin = summary.current_stage if summary is not None else None
        self._rebuild_career_stage_list(
            preferred_stage=current_bin if snapshot_changed else None
        )
        for stage, button in self.career_stage_buttons.items():
            is_current = current_bin is not None and stage == current_bin
            if button.property("current") != is_current:
                button.setProperty("current", is_current)
                button.style().unpolish(button)
                button.style().polish(button)
        self._refresh_career_preview()

    def _on_career_variant_changed(self, _index: int) -> None:
        self._rebuild_career_stage_list()
        self._refresh_career_preview()

    def _career_block_reason(self) -> Optional[str]:
        if self.savefile is None:
            return "Open a save first."
        if self._has_pending_changes():
            return "Apply or Reset pending edits first."
        if self._selected_career_donor() is None:
            return "Pick a target stage with an available donor."
        return None

    def _refresh_career_preview(self) -> None:
        lines: List[str] = []
        donor = self._selected_career_donor()
        block_reason = self._career_block_reason()
        current = (
            career_transplant.read_current_bin(bytes(self.savefile.data))
            if self.savefile is not None else None
        )
        self.career_route_from.setText(
            _stage_title(current).replace(":", "").upper()
            if current is not None else "OPEN A SAVE"
        )
        self.career_route_to.setText(
            _stage_title(donor.stage_bin).replace(":", "").upper()
            if donor is not None else "SELECT TARGET"
        )
        state = "idle"
        can_apply = block_reason is None

        if donor is not None and self.savefile is not None:
            try:
                donor_data = Path(donor.save_path).read_bytes()
                plan = self.savefile.plan_career_transplant(donor_data)
            except Exception as exc:
                lines.append(f"Donor could not be read: {exc}")
                state = "blocked"
                can_apply = False
            else:
                if plan.refusal_reason:
                    lines.append(f"Refused: {plan.refusal_reason}")
                    state = "blocked"
                    can_apply = False
                else:
                    lines.append(
                        f"{_display_name_text(donor.display_name)} is ready. "
                        "The profile will change in memory only."
                    )
                    state = "ready"
                    if current == plan.donor_bin:
                        lines.append("Same stage: this resets the chapter's progress.")
                        state = "warning"
                    if plan.bounty_compensation > 0:
                        lines.append(
                            f"Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history."
                        )
                    elif plan.user_total_bounty > plan.donor_total_bounty:
                        lines.append(
                            f"Earned bounty {plan.user_total_bounty:,} is above the snapshot's "
                            f"{plan.donor_total_bounty:,}: keep it or normalize on apply."
                        )
                    if plan.warnings:
                        state = "warning"
                        lines.extend(f"Warning: {w}" for w in plan.warnings)
        if block_reason:
            if self.savefile is None:
                lines.append("Open a save before building a stage-change plan.")
            elif donor is None:
                lines.append("Choose a target stage to assemble the transplant plan.")
            else:
                lines.append(block_reason)
            state = "blocked" if self.savefile is None or self._has_pending_changes() else "idle"

        self.career_preview_status.setText("\n".join(lines))
        self.career_preview_status.setProperty("state", state)
        self.career_preview_status.style().unpolish(self.career_preview_status)
        self.career_preview_status.style().polish(self.career_preview_status)
        self.btn_career_transplant.setEnabled(can_apply)

    # ── Apply ──────────────────────────────────────────────────

    def _on_career_transplant_clicked(self) -> None:
        donor = self._selected_career_donor()
        if donor is None or self.savefile is None:
            return
        try:
            donor_data = Path(donor.save_path).read_bytes()
            plan = self.savefile.plan_career_transplant(donor_data)
        except Exception as exc:
            QMessageBox.critical(self, "Stage change failed", str(exc))
            return
        if plan.refusal_reason:
            QMessageBox.warning(self, "Stage change blocked", plan.refusal_reason)
            self._refresh_career_preview()
            return

        current = career_transplant.read_current_bin(bytes(self.savefile.data))
        warning_lines = "".join(f"\n- {w}" for w in plan.warnings)
        if plan.bounty_compensation > 0:
            warning_lines += (
                f"\n- Bounty compensation: +{plan.bounty_compensation:,} via sold-cars history"
            )
        base_text = (
            f"Change career progression in memory?\n\n"
            f"{_stage_title(current)}  ->  {_stage_title(plan.donor_bin)}\n"
            f"Target snapshot: {_display_name_text(donor.display_name)}\n\n"
            f"{_CHANGES_TEXT}\n{_KEEPS_TEXT}\n\n"
            f"This edits memory only; use Save + backup to write the file."
            f"{warning_lines}"
        )
        bounty_mode = career_transplant.BOUNTY_MODE_KEEP
        if plan.user_total_bounty > plan.donor_total_bounty:
            # Rollback case: the two bounty modes diverge, so the choice is
            # part of the confirmation. Normalize lands the total exactly on
            # the target; every value it lowers is listed here explicitly.
            slot_names = {
                slot.career_slot: slot.display_name
                for slot in getattr(self, "garage_slots", [])
            }
            car_lines = "".join(
                f"\n  {slot_names.get(slot, f'Slot {slot + 1}')}: "
                f"{old:,} -> {new:,}"
                for slot, old, new in plan.normalized_car_bounties
            )
            if car_lines:
                car_lines = "\nCar bounties scale proportionally:" + car_lines
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Confirm career stage change")
            box.setText(
                base_text
                + (
                    f"\n\nEarned bounty {plan.user_total_bounty:,} is above this "
                    f"snapshot's own bounty of {plan.donor_total_bounty:,}.\n"
                    f"Keep earned bounty: total stays {plan.user_total_bounty:,}.\n"
                    f"Normalize: total becomes exactly the snapshot's "
                    f"{plan.donor_total_bounty:,}."
                    + car_lines
                )
            )
            # ActionRole on both keeps the insertion order: Normalize first
            # and default (the rollback intent is already explicit; every
            # lowered value is listed above), Keep as the safety option.
            normalize_btn = box.addButton("Normalize to snapshot", QMessageBox.ActionRole)
            keep_btn = box.addButton("Keep earned bounty", QMessageBox.ActionRole)
            cancel_btn = box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(normalize_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn or clicked is None:
                return
            if clicked is normalize_btn:
                bounty_mode = career_transplant.BOUNTY_MODE_NORMALIZE
        else:
            answer = QMessageBox.question(
                self,
                "Confirm career stage change",
                base_text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        hero_snapshot = self._career_crossfade_snapshot(
            self.career_hero, "_career_hero_transition"
        )
        try:
            self.savefile.apply_career_transplant(donor_data, bounty_mode)
        except Exception as exc:
            QMessageBox.critical(self, "Stage change failed", str(exc))
            return

        self._reset_want_edit_state()
        self.refresh_state()
        self._start_career_crossfade(
            self.career_hero,
            hero_snapshot,
            "_career_hero_transition",
            "careerHeroTransitionOverlay",
        )
        ToastNotification.show_toast(
            self, "Career stage changed in memory. Save + backup to write"
        )
