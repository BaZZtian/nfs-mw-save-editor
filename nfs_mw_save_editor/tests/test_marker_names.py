"""Canonical marker names (core/marker_names.py) must match the engine.

Anchors come from the MarkerSelectInfo table in speed.exe v1.3 resolved
through Labels.bin/English.bin — see RE/tools/gen_token_names.py. The
18/19 anchor doubles as the guard against the historical pink-slip/cash
swap ever coming back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import marker_names
from core.marker_names import MARKER_CANON, canon_description, canon_fe_category, canon_name


def test_coverage_is_every_marker_except_nameless_decal_paint():
    # 1..21 minus DECAL (15) and PAINT (16), which carry null label hashes
    # in the FE table.
    assert set(MARKER_CANON) == set(range(1, 22)) - {15, 16}


def test_name_anchors():
    assert canon_name(1) == "Unique Brake Upgrades"
    assert canon_name(17) == "Get out of jail for free."
    assert canon_name(21) == "Release car from impound"


def test_pinkslip_cash_guard():
    # 18 = PINK_SLIP, 19 = CASH (older editor catalogs had them swapped).
    assert MARKER_CANON[18].label == "MARKER_NAME_PINKSLIP"
    assert canon_name(18) == "Pink slip to Blacklist rival"
    assert MARKER_CANON[19].label == "MARKER_NAME_CASH"
    assert canon_name(19) == "Extra Cash Reward"


def test_fe_categories_are_the_engine_four():
    # The game groups markers 4-way; the editor's 3-way grouping is its own.
    assert {c.fe_category for c in MARKER_CANON.values()} == {
        "Unique Performance Upgrades",
        "Unique Part Upgrades",
        "Unique Visual Upgrades",
        "Bonus Markers",
    }
    assert all(
        MARKER_CANON[tid].fe_category == "Unique Performance Upgrades"
        for tid in range(1, 8)
    )


def test_every_entry_has_a_description():
    assert all(canon_description(tid) for tid in MARKER_CANON)


def test_unknown_ids_resolve_to_none():
    for tid in (0, 15, 16, 22):
        assert canon_name(tid) is None
        assert canon_description(tid) is None
        assert canon_fe_category(tid) is None


def test_induction_turbo_variant():
    # FE wires supercharger for INDUCTION (4); the language files also ship
    # an unused turbo variant, which the editor prefers for the card title.
    assert canon_name(4) == "Unique Supercharger Upgrades"
    assert marker_names.INDUCTION_TURBO_NAME == "Unique Turbo Upgrades"
    assert "turbo" in marker_names.INDUCTION_TURBO_DESCRIPTION
