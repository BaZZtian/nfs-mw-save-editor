"""Pure view-model logic for the Tuning card "Visual" summary row.

Turns an installed-parts build (slot id -> PartInfo, from
core.visual_parts.installed_parts) into one compact display line: paint swatch
RGB, a few notable parts, and a rival-livery callout when the vinyl layer is a
Blacklist boss vinyl (pink-slip cars keep their previous owner's colours).

No Qt imports here on purpose: everything is testable headless. Rendering
lives in parts_mixin.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from core.visual_parts import (
    PartInfo,
    SLOT_BASE_PAINT,
    SLOT_BODY,
    SLOT_FRONT_WHEEL,
    SLOT_HOOD,
    SLOT_PAINT_RIM,
    SLOT_ROOF,
    SLOT_SPOILER,
    SLOT_VINYL_LAYER0,
    SLOT_WINDOW_TINT,
    slot_name,
)

# Blacklist number -> nickname (MW 2005 roster; vinyl names carry full names,
# e.g. 13VICTORVASQUEZ = Vic, 14VINCEKILIC = Taz).
RIVAL_NICKNAMES: Dict[int, str] = {
    1: "Razor", 2: "Bull", 3: "Ronnie", 4: "JV", 5: "Webster",
    6: "Ming", 7: "Kaze", 8: "Jewels", 9: "Earl", 10: "Baron",
    11: "Big Lou", 12: "Izzy", 13: "Vic", 14: "Taz", 15: "Sonny",
}

_RIVAL_VINYL_RE = re.compile(r"^(\d{1,2})([A-Z]{4,})$")
_PAINT_RE = re.compile(r"^(GLOSS|METAL|PEARL)_L\d+_COLOR(\d+)$")
_CHROME_RE = re.compile(r"^CHROME(\d+)_PAINT$")
_PAINT_FAMILY_LABEL = {"GLOSS": "Gloss", "METAL": "Metallic", "PEARL": "Pearl"}

# Engine names that mean "nothing custom installed" for their slot.
_STOCK_NAMES = {
    SLOT_SPOILER: {"SPOILER"},
    SLOT_HOOD: {"STOCK"},
    SLOT_ROOF: {"NO ROOF SCOOP"},
    SLOT_FRONT_WHEEL: {"WHEEL"},
    SLOT_BODY: {"BASE KIT00", "BODY_00"},
    SLOT_WINDOW_TINT: {"STOCK WINDOW TINT"},
}

LIVERY_TOOLTIP_TEMPLATE = (
    "Livery — a race car's signature paint scheme, the owner's colours.\n"
    "This car still wears the battle vinyl of Blacklist #{number} {nickname}."
)

# Slots worth listing in the hover tooltip (customization-facing; structural
# slots like FRONT_LEFT_WINDOW are engine plumbing and stay hidden).
_TOOLTIP_SLOTS = frozenset(
    {SLOT_BODY, SLOT_SPOILER, SLOT_ROOF, SLOT_HOOD, SLOT_FRONT_WHEEL, 67, 68, 69}
    | set(range(70, 76))       # decal model slots
    | set(range(83, 131))      # decal texture slots
    | {SLOT_BASE_PAINT, SLOT_VINYL_LAYER0, SLOT_PAINT_RIM}
    | set(range(79, 83))       # vinyl colours
    | {SLOT_WINDOW_TINT}
    | set(range(132, 136))     # custom HUD + colours
)


@dataclass(frozen=True)
class VisualSummaryVm:
    swatch_rgb: Optional[Tuple[int, int, int]]
    text: str
    livery_text: Optional[str]
    livery_tooltip: Optional[str]
    tooltip: str


def _pretty_words(name: str) -> str:
    """LOWENHART LH2 20 -> Lowenhart LH2 20 (keep dotted/digit/CF tokens as-is)."""
    words = []
    for word in name.split():
        if word == "CF" or "." in word or any(ch.isdigit() for ch in word):
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _split_trailing_digits(name: str) -> Tuple[str, Optional[str]]:
    match = re.match(r"^(.*?)(\d+)$", name)
    if match and match.group(1):
        return match.group(1).rstrip("_ "), match.group(2)
    return name, None


def paint_label(name: str) -> str:
    match = _PAINT_RE.match(name)
    if match:
        return f"{_PAINT_FAMILY_LABEL[match.group(1)]} #{match.group(2)}"
    match = _CHROME_RE.match(name)
    if match:
        return f"Chrome #{match.group(1)}"
    return _pretty_words(name.replace("_", " "))


def wheel_label(name: str) -> str:
    """VOLK TE37 20 25 -> Volk TE37 20″ (last two numbers = diameter, offset)."""
    tokens = name.split()
    if len(tokens) >= 3 and tokens[-1].isdigit() and tokens[-2].isdigit():
        return f"{_pretty_words(' '.join(tokens[:-2]))} {tokens[-2]}″"
    return _pretty_words(name)


def rival_livery(part: Optional[PartInfo]) -> Optional[Tuple[int, str]]:
    """(blacklist number, nickname) when the vinyl is a boss livery."""
    if part is None:
        return None
    match = _RIVAL_VINYL_RE.match(part.name)
    if not match:
        return None
    number = int(match.group(1))
    nickname = RIVAL_NICKNAMES.get(number)
    if nickname is None:
        return None
    return number, nickname


def _is_stock(slot_id: int, part: Optional[PartInfo]) -> bool:
    return part is None or part.name in _STOCK_NAMES.get(slot_id, set())


def build_visual_summary(build: Mapping[int, PartInfo]) -> Optional[VisualSummaryVm]:
    if not build:
        return None

    paint = build.get(SLOT_BASE_PAINT)
    swatch = paint.rgb if paint is not None else None

    items: List[str] = []
    if paint is not None:
        items.append(paint_label(paint.name))

    body = build.get(SLOT_BODY)
    if not _is_stock(SLOT_BODY, body):
        _base, digits = _split_trailing_digits(body.name)
        items.append(f"Kit {digits}" if digits else _pretty_words(body.name))
    spoiler = build.get(SLOT_SPOILER)
    if not _is_stock(SLOT_SPOILER, spoiler):
        items.append(_pretty_words(spoiler.name))
    hood = build.get(SLOT_HOOD)
    if not _is_stock(SLOT_HOOD, hood):
        items.append(_pretty_words(hood.name))
    roof = build.get(SLOT_ROOF)
    if not _is_stock(SLOT_ROOF, roof):
        items.append(_pretty_words(roof.name))
    wheels = build.get(SLOT_FRONT_WHEEL)
    if not _is_stock(SLOT_FRONT_WHEEL, wheels):
        items.append(wheel_label(wheels.name))
    tint = build.get(SLOT_WINDOW_TINT)
    if not _is_stock(SLOT_WINDOW_TINT, tint):
        items.append(f"Tint: {_pretty_words(tint.name)}")

    livery_text: Optional[str] = None
    livery_tooltip: Optional[str] = None
    vinyl = build.get(SLOT_VINYL_LAYER0)
    livery = rival_livery(vinyl)
    if livery is not None:
        number, nickname = livery
        livery_text = f"Rival livery — #{number} {nickname}"
        livery_tooltip = LIVERY_TOOLTIP_TEMPLATE.format(number=number, nickname=nickname)
    elif vinyl is not None:
        base, digits = _split_trailing_digits(vinyl.name)
        pretty = _pretty_words(base.replace("_", " "))
        items.append(f"Vinyl: {pretty} #{digits}" if digits else f"Vinyl: {pretty}")

    if not items and livery_text is None:
        items.append("stock visuals")

    tooltip_lines: List[str] = []
    for slot_id in sorted(build):
        if slot_id not in _TOOLTIP_SLOTS:
            continue
        part = build[slot_id]
        label = slot_name(slot_id) or str(slot_id)
        extra = f"  RGB {part.rgb[0]},{part.rgb[1]},{part.rgb[2]}" if part.rgb else ""
        tooltip_lines.append(f"{label}: {part.name}{extra}")

    return VisualSummaryVm(
        swatch_rgb=swatch,
        text=" · ".join(items),
        livery_text=livery_text,
        livery_tooltip=livery_tooltip,
        tooltip="\n".join(tooltip_lines),
    )
