from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.milestone_names import (
    CAREER_TYPE_INFO,
    CHALLENGE_NODES,
    MILESTONE_TYPE_NAMES,
    SPEEDTRAP_NODES,
    resolve_challenge_node,
    resolve_speedtrap_node,
    resolve_type_name,
    speedtrap_ordinal,
    type_label_and_unit,
)

# Anchors from the decoded game milestone tables.
TYPE_COPS_DAMAGED = 0x850A64BC
TYPE_BOUNTY = 0x2377E50D
TYPE_HEAT_METER = 0xE9A4423C          # tracked stat, never a career milestone
CHALL_BIN1_COPS_DAMAGED = 0x78C71DD9
CHALL_BIN1_BOUNTY = 0x628647A7        # EA quirk: node named cops_destroyed
TRAP_BIN1_THIRD = 0x64AD9C28
UNKNOWN_KEY = 0xDEADBEEF


def test_table_sizes():
    assert len(MILESTONE_TYPE_NAMES) == 30
    assert len(CHALLENGE_NODES) == 55
    assert len(SPEEDTRAP_NODES) == 39


def test_resolve_type_name():
    assert resolve_type_name(TYPE_COPS_DAMAGED) == "cops_damaged"
    assert resolve_type_name(TYPE_BOUNTY) == "bounty_in_pursuit"
    assert resolve_type_name(UNKNOWN_KEY) is None


def test_career_type_labels_cover_used_types():
    # Every career display entry must point at a decoded stat name.
    names = set(MILESTONE_TYPE_NAMES.values())
    assert set(CAREER_TYPE_INFO) <= names
    label, unit = type_label_and_unit(TYPE_BOUNTY)
    assert label == "Bounty (single pursuit)"
    assert unit == "money"


def test_type_label_and_unit_fails_closed():
    assert type_label_and_unit(UNKNOWN_KEY) is None
    # Tracked-but-unused stats have a name but no career display entry.
    assert resolve_type_name(TYPE_HEAT_METER) == "heat_meter"
    assert type_label_and_unit(TYPE_HEAT_METER) is None


def test_challenge_nodes_shape():
    assert resolve_challenge_node(CHALL_BIN1_COPS_DAMAGED) == (
        "milestones/bin_01/challenge_1_cops_damaged"
    )
    # The EA rename quirk must be preserved verbatim, not "fixed".
    assert resolve_challenge_node(CHALL_BIN1_BOUNTY) == (
        "milestones/bin_01/challenge_1_cops_destroyed"
    )
    assert resolve_challenge_node(UNKNOWN_KEY) is None
    assert all(node.startswith("milestones/bin_") for node in CHALLENGE_NODES.values())


def test_speedtrap_nodes_shape():
    assert resolve_speedtrap_node(TRAP_BIN1_THIRD) == "speedtraps/bin_01/speedtrap3"
    assert resolve_speedtrap_node(UNKNOWN_KEY) is None
    assert all(node.startswith("speedtraps/bin_") for node in SPEEDTRAP_NODES.values())


def test_speedtrap_ordinals():
    assert speedtrap_ordinal(TRAP_BIN1_THIRD) == 3
    assert speedtrap_ordinal(UNKNOWN_KEY) is None
    ordinals = {speedtrap_ordinal(key) for key in SPEEDTRAP_NODES}
    assert ordinals == {1, 2, 3}
