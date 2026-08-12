"""Marker cards a Blacklist rival offers after the final race of his chapter.

Source: the game's own career vaults in ``gameplay.bin``, decoded by
``RE/tools/dump_career_bins.py`` (dump kept at ``RE/career_bins_decoded.txt``).
That tool self-checks what it reads: 15 chapter roots, boss races agreeing
with ``core/rival_challenge`` 15/15, and every offer holding exactly six cards
with exactly one pink slip.

Facts worth keeping in mind when showing these:

- The player takes TWO of the six.  Which two is not recorded anywhere the
  editor can read, so these are offers, never possessions - do not paint them
  as claimed because the rival is beaten.
- The three bonus cards are dealt in a random order by the game, rolled fresh
  each run.  The order here is the canonical one; the UI reshuffles that trio
  once per opened save (see the Career page), which is session state, not a
  property of the rival - hence it does not live in this table.
- A card can repeat: Vic (#13) offers two separate cash bonuses.
- Razor (#1) offers nothing.  His chapter ends in the Final Pursuit, which is
  not a marker race, so the vault carries no rewards for him at all.
- Ids are ``ePossibleMarker`` (see ``core/junkman.py`` and
  ``core/marker_names.py``), so the editor's own token icons and names apply.
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
    # The FE category is "Unique Part Upgrades" - singular; matching "Parts"
    # silently sorted every part card in with performance.
    category = MARKER_CANON[marker].fe_category if marker in MARKER_CANON else ""
    if "Visual" in category:
        return 1
    if "Part" in category:
        return 2
    return 3


def reward_markers(stage: int) -> Tuple[int, ...]:
    """Marker ids offered by ``stage`` (15 = Sonny, 1 = Razor).

    Ordered the way the marker-select screen deals them: the three bonus
    cards first (the pink slip is always one of them), then the three upgrade
    cards by category - visual, parts, performance.  The vault stores its own
    order, where the pink slip sits fourth for nine rivals out of fourteen.

    The bonus/upgrade split is exact - three of each, every rival - and every
    rival offers exactly ONE performance card, which is why it always lands
    last.  The other two are not one-per-category: Big Lou hands out spoiler,
    rims and tires (two Parts, no Visual), Bull hands out gauge, vinyl and a
    supercharger (two Visual, no Parts).
    """
    cards = BLACKLIST_REWARD_MARKERS.get(stage, ())
    return tuple(sorted(cards, key=_display_rank))
