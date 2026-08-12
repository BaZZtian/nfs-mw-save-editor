"""Which races run with cops, and the heat level a race forces.

Transcribed from the game's own attribute vaults in ``GLOBAL/gameplay.bin``,
decoded offline; the editor reads no game file at runtime.

Keyed by the EventID string the editor already derives from a race hash
(``core/race_names.resolve_event_id``): the vault carries its own ``EventID``
text attribute, and ``lookup2(EventID)`` matched the save-table hash on all
248 events, so nothing in the chain is guessed.

Facts worth keeping in mind:

- The naive read is backwards.  ``Attrib::Collection::GetNode`` walks the
  parent chain and the root ``race`` template sets ``CopsInRace=1``, so a race
  WITHOUT cops carries an explicit ``0`` while most races with cops say
  nothing at all.  Reading own entries only leaves 87 events undecided.
- ``CopDensity`` is not a dial: 100 for 247 of 248 events, and the
  single override sits on a race that has cops switched off anyway.  There is
  no "how many cops" number in the data.
- In the career the flag is effectively binary.  Every career race with cops
  runs at open-world heat; the one forced level belongs to ``1.8.1``, the
  Final Pursuit that closes the game (chapter 1 is Razor's, so its events are
  the finale, not the prologue).  That race is also the only
  ``ScriptedCopsInRace`` in the game.  All graded heat lives in the
  challenge series.
- ``PursuitRace`` is NOT a cop flag - the tollbooth challenges run with cops
  at ``PursuitRace=0``.

Generated - do not edit by hand.
"""
from __future__ import annotations

from typing import Optional

# EventIDs whose races run with cops (104 of 248).
RACES_WITH_COPS = frozenset({
    "1.2.2", "1.4.1", "1.5.1", "1.8.1", "10.2.2", "10.4.1",
    "11.5.1", "12.4.1", "13.2.1", "14.2.2", "14.2.3", "15.2.1",
    "19.8.1", "19.8.10", "19.8.11", "19.8.12", "19.8.13", "19.8.14",
    "19.8.15", "19.8.16", "19.8.17", "19.8.18", "19.8.19", "19.8.2",
    "19.8.20", "19.8.21", "19.8.22", "19.8.23", "19.8.24", "19.8.25",
    "19.8.26", "19.8.27", "19.8.28", "19.8.29", "19.8.3", "19.8.30",
    "19.8.31", "19.8.32", "19.8.33", "19.8.34", "19.8.35", "19.8.36",
    "19.8.37", "19.8.38", "19.8.39", "19.8.4", "19.8.40", "19.8.41",
    "19.8.42", "19.8.43", "19.8.44", "19.8.45", "19.8.46", "19.8.47",
    "19.8.48", "19.8.49", "19.8.5", "19.8.50", "19.8.51", "19.8.52",
    "19.8.53", "19.8.55", "19.8.57", "19.8.58", "19.8.59", "19.8.6",
    "19.8.60", "19.8.61", "19.8.62", "19.8.63", "19.8.64", "19.8.65",
    "19.8.66", "19.8.67", "19.8.68", "19.8.69", "19.8.7", "19.8.8",
    "19.8.9", "19.9.70", "2.4.3", "2.5.1", "21.1.1", "21.2.1",
    "21.2.2", "3.2.1.r", "3.4.1", "3.5.1", "4.4.1", "4.5.3",
    "5.1.1", "5.2.3", "5.4.1", "5.5.3", "6.4.1", "6.5.1",
    "7.2.1", "7.2.2.r", "7.4.2", "8.2.2", "8.5.2", "9.4.1",
    "9.5.2", "99.1.1",
})

# ForceHeatLevel where the race overrides the open world's heat.  Two
# entries here have cops switched off (the truck tollbooth challenges),
# where the setting is inert - always read the cop flag first.
FORCED_HEAT = {
    "1.8.1": 6,
    "19.8.1": 1,
    "19.8.10": 3,
    "19.8.11": 3,
    "19.8.12": 3,
    "19.8.13": 3,
    "19.8.14": 3,
    "19.8.15": 3,
    "19.8.16": 4,
    "19.8.17": 3,
    "19.8.18": 4,
    "19.8.19": 4,
    "19.8.2": 1,
    "19.8.20": 4,
    "19.8.21": 3,
    "19.8.22": 4,
    "19.8.23": 3,
    "19.8.24": 3,
    "19.8.25": 3,
    "19.8.26": 5,
    "19.8.27": 5,
    "19.8.28": 5,
    "19.8.29": 3,
    "19.8.3": 1,
    "19.8.30": 5,
    "19.8.36": 2,
    "19.8.37": 2,
    "19.8.38": 2,
    "19.8.39": 2,
    "19.8.4": 1,
    "19.8.40": 2,
    "19.8.41": 3,
    "19.8.42": 3,
    "19.8.43": 3,
    "19.8.44": 3,
    "19.8.45": 3,
    "19.8.46": 3,
    "19.8.47": 4,
    "19.8.48": 4,
    "19.8.49": 4,
    "19.8.5": 2,
    "19.8.50": 4,
    "19.8.51": 4,
    "19.8.52": 1,
    "19.8.53": 1,
    "19.8.54": 1,
    "19.8.55": 1,
    "19.8.56": 1,
    "19.8.57": 5,
    "19.8.58": 5,
    "19.8.59": 5,
    "19.8.6": 2,
    "19.8.60": 5,
    "19.8.61": 5,
    "19.8.62": 5,
    "19.8.63": 5,
    "19.8.64": 5,
    "19.8.65": 5,
    "19.8.66": 5,
    "19.8.67": 5,
    "19.8.68": 5,
    "19.8.69": 5,
    "19.8.7": 2,
    "19.8.8": 4,
    "19.8.9": 2,
    "19.9.70": 7,
}

# The only race that spawns its cops by script rather than by heat.
SCRIPTED_COPS = frozenset({"1.8.1"})


def has_cops(event_id: Optional[str]) -> bool:
    """Whether the race behind ``event_id`` runs with cops."""
    return bool(event_id) and event_id in RACES_WITH_COPS


def forced_heat(event_id: Optional[str]) -> Optional[int]:
    """Heat level the race forces, or None when it takes the world's heat.

    Only meaningful for a race that has cops - see FORCED_HEAT.
    """
    if not event_id or not has_cops(event_id):
        return None
    return FORCED_HEAT.get(event_id)
