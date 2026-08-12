"""The cop table is transcribed data joined to the save by EventID, so guard
both the shape it must hold and the join the Career page depends on.

Source of truth is the game's attribute vaults, decoded offline; the decoder
checks these same invariants against the vault itself.  These tests keep the
transcription - and the hash -> EventID -> cops chain - from drifting.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.race_chapters import RACE_OFFERING
from core.race_cops import (
    FORCED_HEAT,
    RACES_WITH_COPS,
    SCRIPTED_COPS,
    forced_heat,
    has_cops,
)
from core.race_names import resolve_event_id

# The Final Pursuit that closes the game (chapter 1 is Razor's): the only
# career race that forces a heat level, and the only race in the game whose
# cops are spawned by script rather than by heat.
FINAL_PURSUIT = "1.8.1"


def _career_event_ids():
    return [resolve_event_id(race_hash) for race_hash in RACE_OFFERING]


def test_every_career_race_resolves_to_a_known_event():
    """The join the chips ride on: hash -> EventID -> cop flag, no gaps."""
    ids = _career_event_ids()
    assert len(ids) == 168
    assert all(ids), "a career race hash has no EventID"
    assert len(set(ids)) == len(ids)


def test_the_cop_races_are_a_sparse_accent_across_the_career():
    """32 of 168, and every chapter has at least one - a badge worth drawing."""
    with_cops = [event_id for event_id in _career_event_ids() if has_cops(event_id)]
    assert len(with_cops) == 32
    chapters = {
        RACE_OFFERING[race_hash][0]
        for race_hash in RACE_OFFERING
        if has_cops(resolve_event_id(race_hash))
    }
    assert chapters == set(range(1, 16))


def test_career_heat_is_binary_apart_from_the_final_pursuit():
    """Why the badge does not grade: every other career race with cops runs at
    the open world's heat.  All graded heat lives in the challenge series."""
    graded = {
        event_id: forced_heat(event_id)
        for event_id in _career_event_ids()
        if forced_heat(event_id)
    }
    assert graded == {FINAL_PURSUIT: 6}
    assert SCRIPTED_COPS == frozenset({FINAL_PURSUIT})


def test_forced_heat_ignores_races_that_have_no_cops():
    """Two challenge tollbooths carry ForceHeatLevel with cops switched off -
    an inert setting the UI must not read as a pursuit."""
    inert = [event_id for event_id in FORCED_HEAT if not has_cops(event_id)]
    assert inert, "the guard has nothing left to guard"
    for event_id in inert:
        assert forced_heat(event_id) is None


def test_missing_or_unknown_events_are_not_cop_races():
    assert not has_cops(None)
    assert not has_cops("")
    assert not has_cops("0.0.0")
    assert forced_heat(None) is None


def test_table_holds_well_formed_event_ids():
    pattern = re.compile(r"^\d+\.\d+\.\d+(\.r)?$")
    for event_id in RACES_WITH_COPS | set(FORCED_HEAT):
        assert pattern.match(event_id), event_id
    assert all(1 <= level <= 7 for level in FORCED_HEAT.values())
