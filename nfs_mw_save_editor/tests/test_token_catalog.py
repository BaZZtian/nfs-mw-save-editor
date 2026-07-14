"""Token catalog defaults must follow the engine enum ePossibleMarker.

Decoded from PS2 debug symbols and confirmed on PC v1.3 via the
MarkerSelectInfo table in speed.exe: markers are 1..21 (MARKER_LAST = 21),
with 17 GET_OUT_OF_JAIL, 18 PINK_SLIP, 19 CASH, 20 ADD_IMPOUND_BOX,
21 IMPOUND_RELEASE. Older catalogs had 18/19 swapped and carried entries
for nonexistent IDs (22+); _normalize_catalog_defaults must migrate the
swap and purge the ghosts.

Since 2026-07-12 the default card names are the game's own marker-select
strings (core/marker_names.py); every default an earlier editor version
shipped is treated as legacy and upgraded, user renames are left alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.pages.constants import SAFE_TYPE_MAX, SAFE_TYPE_MIN, TokenEntry
from ui.pages.junkman_mixin import JunkmanMixin

# The current canon defaults, as shipped in token_catalog.json.
CANON_DEFAULTS = [
    (1, "Unique Brake Upgrades", "Performance"),
    (2, "Unique Engine Upgrades", "Performance"),
    (3, "Unique Nitrous Upgrades", "Performance"),
    (4, "Unique Turbo Upgrades", "Performance"),
    (5, "Unique Suspension Upgrades", "Performance"),
    (6, "Unique Tire Upgrades", "Performance"),
    (7, "Unique Transmission Upgrades", "Performance"),
    (8, "Unique Body Kit Upgrades", "Parts"),
    (9, "Unique Hood Upgrades", "Parts"),
    (10, "Unique Spoiler Upgrades", "Parts"),
    (11, "Unique Rim Upgrades", "Parts"),
    (12, "Unique Roof Scoop Upgrades", "Parts"),
    (13, "Unique Custom Gauge Upgrades", "Visual"),
    (14, "Unique Vinyl Upgrades", "Visual"),
    (15, "Decal", "Visual"),
    (16, "Paint", "Visual"),
    (17, "Get out of jail for free.", "Bonus Markers"),
    (18, "Pink slip to Blacklist rival", "Bonus Markers"),
    (19, "Extra Cash Reward", "Bonus Markers"),
    (20, "Extra impound strike", "Bonus Markers"),
    (21, "Release car from impound", "Bonus Markers"),
]


class _CatalogHost(JunkmanMixin):
    """Bare host exposing only what _normalize_catalog_defaults touches."""

    def __init__(self, tokens):
        self.tokens = tokens


def test_safe_type_range_matches_engine_enum():
    assert SAFE_TYPE_MIN == 1
    assert SAFE_TYPE_MAX == 21  # ePossibleMarker MARKER_LAST


def test_normalize_migrates_swapped_pinkslip_and_cash_names():
    host = _CatalogHost([
        TokenEntry(id=18, name="Money Marker", category="Bonus Markers"),
        TokenEntry(id=19, name="PinkSlip Marker", category="Bonus Markers"),
    ])
    assert host._normalize_catalog_defaults() is True
    names = {t.id: t.name for t in host.tokens}
    assert names[18] == "Pink slip to Blacklist rival"
    assert names[19] == "Extra Cash Reward"


def test_normalize_purges_nonexistent_ids():
    host = _CatalogHost([
        TokenEntry(id=22, name="Unknown ID 22 (valid)", category="Unknown"),
        TokenEntry(id=23, name="Token #23", category="Unknown"),
        TokenEntry(id=30, name="Token #30", category="Unknown"),
    ])
    assert host._normalize_catalog_defaults() is True
    ids = {t.id for t in host.tokens}
    assert ids == set(range(SAFE_TYPE_MIN, SAFE_TYPE_MAX + 1))


def test_normalize_upgrades_pre_canon_defaults():
    # Every default name an earlier editor version shipped is legacy now.
    host = _CatalogHost([
        TokenEntry(id=1, name="Brakes", category="Performance"),
        TokenEntry(id=4, name="Turbo", category="Performance"),
        TokenEntry(id=13, name="Gauge", category="Visual"),
        TokenEntry(id=17, name="Out of Jail", category="Bonus Markers"),
        TokenEntry(id=20, name="Impound Strike Slot Add", category="Bonus Markers"),
        TokenEntry(id=9, name="Token #9", category="Bonus Markers"),  # placeholder
    ])
    assert host._normalize_catalog_defaults() is True
    names = {t.id: t.name for t in host.tokens}
    assert names[1] == "Unique Brake Upgrades"
    assert names[4] == "Unique Turbo Upgrades"  # unwired game string, not FE's supercharger
    assert names[13] == "Unique Custom Gauge Upgrades"
    assert names[17] == "Get out of jail for free."
    assert names[20] == "Extra impound strike"
    assert names[9] == "Unique Hood Upgrades"


def test_normalize_respects_user_renames():
    tokens = [
        TokenEntry(id=tid, name=name, category=cat)
        for tid, name, cat in CANON_DEFAULTS
    ]
    tokens[17] = TokenEntry(id=18, name="My Custom Name", category="Bonus Markers")
    host = _CatalogHost(tokens)
    assert host._normalize_catalog_defaults() is False
    assert next(t.name for t in host.tokens if t.id == 18) == "My Custom Name"


def test_normalize_builds_full_engine_table_from_empty():
    host = _CatalogHost([])
    assert host._normalize_catalog_defaults() is True
    entries = {t.id: t for t in host.tokens}
    assert set(entries) == set(range(1, 22))
    assert all(entries[i].category == "Performance" for i in range(1, 8))
    assert all(entries[i].category == "Parts" for i in range(8, 13))
    assert all(entries[i].category == "Visual" for i in range(13, 17))
    assert all(entries[i].category == "Bonus Markers" for i in range(17, 22))
    for tid, name, cat in CANON_DEFAULTS:
        assert entries[tid].name == name
        assert entries[tid].category == cat


def test_normalize_coerces_stray_categories():
    host = _CatalogHost([
        TokenEntry(id=5, name="Unique Suspension Upgrades", category="Unknown"),
    ])
    host._normalize_catalog_defaults()
    assert next(t.category for t in host.tokens if t.id == 5) == "Performance"


def test_shipped_catalog_matches_canon_defaults():
    import json

    catalog_path = Path(__file__).resolve().parents[1] / "token_catalog.json"
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    shipped = [(t["id"], t["name"], t["category"]) for t in raw["tokens"]]
    assert shipped == CANON_DEFAULTS
