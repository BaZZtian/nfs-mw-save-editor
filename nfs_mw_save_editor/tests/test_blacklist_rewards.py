"""The reward offers are transcribed data, so guard the shape they must hold.

Source of truth is the game's career vaults, decoded by
RE/tools/dump_career_bins.py; that tool checks the same invariants against the
vault itself.  These tests keep the transcription from drifting.
"""
from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.blacklist_rewards import (
    BLACKLIST_REWARD_MARKERS,
    BONUS_MARKERS,
    CARDS_PER_OFFER,
    CARDS_TAKEN,
    PINK_SLIP_MARKER,
    reward_markers,
)
from core.marker_names import MARKER_CANON

# ePossibleMarker runs 1..21 (MARKER_LAST); core/junkman.py documents it.
MARKER_LAST = 21


def test_every_blacklist_stage_is_covered():
    assert set(BLACKLIST_REWARD_MARKERS) == set(range(1, 16))


def test_each_rival_offers_six_cards_with_one_pink_slip():
    for stage, markers in BLACKLIST_REWARD_MARKERS.items():
        if stage == 1:
            # Razor's chapter ends in the Final Pursuit, which is not a marker
            # race - the vault carries no rewards for him.
            assert markers == ()
            continue
        assert len(markers) == CARDS_PER_OFFER, stage
        assert markers.count(PINK_SLIP_MARKER) == 1, stage


def test_offers_use_real_marker_ids():
    for stage, markers in BLACKLIST_REWARD_MARKERS.items():
        for marker in markers:
            assert 1 <= marker <= MARKER_LAST, (stage, marker)
            # 15/16 are nameless in the FE table; every offered card has a name.
            assert marker in MARKER_CANON, (stage, marker)


def test_a_card_may_repeat_within_one_offer():
    """Vic hands out two separate cash bonuses - the row must not collapse."""
    vic = reward_markers(13)
    assert len(vic) == CARDS_PER_OFFER
    assert len(set(vic)) < len(vic)


def test_taken_is_fewer_than_offered():
    assert 0 < CARDS_TAKEN < CARDS_PER_OFFER


def test_every_offer_splits_three_bonus_and_three_upgrades():
    """The split the marker-select screen deals in, verified 14/14."""
    for stage, markers in BLACKLIST_REWARD_MARKERS.items():
        if not markers:
            continue
        bonus = [marker for marker in markers if marker in BONUS_MARKERS]
        assert len(bonus) == 3, stage
        assert len(markers) - len(bonus) == 3, stage


def test_display_order_leads_with_the_bonus_cards():
    """The vault's own order is different - the pink slip sits fourth for
    nine rivals out of fourteen, while the game deals it in the first three."""
    for stage in BLACKLIST_REWARD_MARKERS:
        ordered = reward_markers(stage)
        if not ordered:
            continue
        assert all(marker in BONUS_MARKERS for marker in ordered[:3]), stage
        assert not any(marker in BONUS_MARKERS for marker in ordered[3:]), stage
        assert PINK_SLIP_MARKER in ordered[:3], stage


def test_the_upgrade_three_are_not_one_per_category():
    """Guards the tempting wrong rule: they are any three upgrade cards."""
    big_lou = reward_markers(11)[3:]
    assert sorted(big_lou) == [6, 10, 11]  # tires, spoiler, rims - two Parts


def test_the_performance_card_is_always_last():
    """Every rival offers exactly one performance card, and the screen deals
    the upgrade three as visual, part, performance - so it closes the row."""
    for stage in BLACKLIST_REWARD_MARKERS:
        upgrades = reward_markers(stage)[3:]
        if not upgrades:
            continue
        categories = [MARKER_CANON[marker].fe_category for marker in upgrades]
        performance = [c for c in categories if "Performance" in c]
        assert len(performance) == 1, stage
        assert "Performance" in categories[-1], stage

        def rank(category: str) -> int:
            if "Visual" in category:
                return 1
            if "Part" in category:  # the FE name is singular
                return 2
            return 3

        ranks = [rank(category) for category in categories]
        assert ranks == sorted(ranks), (stage, categories)
