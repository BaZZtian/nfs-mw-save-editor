"""Marker-card offers decoded from the career vaults in ``gameplay.bin``.

Each eligible rival offers six cards and the player takes two. The save does
not record which cards were selected, so this module describes offers only.
Bonus-card order is session state; upgrade-card order is canonical. Vic has a
duplicate cash card, and Razor has no offer because his chapter ends in the
Final Pursuit.
"""
from __future__ import annotations

from typing import Dict, Tuple

from core.marker_names import MARKER_CANON

# ePossibleMarker ids, in the order the vault lists them.
BLACKLIST_REWARD_MARKERS: Dict[int, Tuple[int, ...]] = {
    1: (),                              # Razor - Final Pursuit, no marker race
    2: (13, 4, 17, 18, 21, 14),         # Bull
    3: (20, 17, 18, 11, 6, 12),         # Ronnie
    4: (8, 19, 2, 18, 21, 14),          # JV
    5: (20, 9, 4, 17, 18, 14),          # Webster
    6: (19, 5, 17, 18, 11, 14),         # Ming
    7: (17, 18, 21, 10, 6, 14),         # Kaze
    8: (20, 8, 17, 18, 7, 10),          # Jewels
    9: (20, 9, 4, 18, 21, 13),          # Earl
    10: (20, 5, 17, 18, 12, 9),         # Baron
    11: (19, 17, 18, 10, 6, 11),        # Big Lou
    12: (20, 8, 4, 18, 21, 14),         # Izzy
    13: (19, 19, 13, 18, 7, 8),         # Vic - two cash bonuses
    14: (20, 19, 5, 9, 18, 14),         # Taz
    15: (1, 19, 17, 18, 11, 14),        # Sonny
}

PINK_SLIP_MARKER = 18
CARDS_PER_OFFER = 6
CARDS_TAKEN = 2

# The game's "Bonus Markers" FE category (see core/marker_names.py): the pink
# slip, cash, the jail/impound cards.  Every rival offers exactly three of
# these and three upgrade cards.
BONUS_MARKERS = frozenset({17, 18, 19, 20, 21})


def _display_rank(marker: int) -> int:
    """Marker-select order: bonus cards, then visual, parts, performance."""
    if marker in BONUS_MARKERS:
        return 0
    # The FE category uses singular "Part"; plural matching is incorrect.
    category = MARKER_CANON[marker].fe_category if marker in MARKER_CANON else ""
    if "Visual" in category:
        return 1
    if "Part" in category:
        return 2
    return 3


def reward_markers(stage: int) -> Tuple[int, ...]:
    """Return marker ids in display order for ``stage``.

    Three bonus cards lead, followed by visual, part, and performance upgrades.
    Upgrade categories may repeat; each offer contains one performance card.
    """
    cards = BLACKLIST_REWARD_MARKERS.get(stage, ())
    return tuple(sorted(cards, key=_display_rank))
