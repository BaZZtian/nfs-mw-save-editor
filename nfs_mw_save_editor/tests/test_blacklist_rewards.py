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
