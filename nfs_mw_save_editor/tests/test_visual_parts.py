from __future__ import annotations

import struct
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.visual_parts import (
    CAR_SLOT_NAMES,
    EMPTY_SLOT,
    INSTALLED_INDICES_SIZE,
    NUM_SLOTS,
    SLOT_BASE_PAINT,
    SLOT_BODY,
    SLOT_HOOD,
    SLOT_VINYL_LAYER0,
    SLOT_WINDOW_TINT,
    installed_parts,
    num_parts,
    part_at,
    read_installed_indices,
    slot_name,
)

# Anchors verified 2026-07-12 against controlled Ford GT saves
# (docs/PROFILE_REVERSE_NOTES.md + RE/tools/dump_save_visuals.py).
FORD_GT_GLOSS_A = 0x0E2E
FORD_GT_CHROME_B = 0x0ED3
FORD_GT_BODY_VINYL = 0x120D
FORD_GT_TINT_STOCK = 0x1523


def test_slot_table_shape():
    assert len(CAR_SLOT_NAMES) == NUM_SLOTS == 139
    assert slot_name(SLOT_BODY) == "BODY"
    assert slot_name(SLOT_HOOD) == "HOOD"
    assert slot_name(SLOT_BASE_PAINT) == "BASE_PAINT"
    assert slot_name(SLOT_VINYL_LAYER0) == "VINYL_LAYER0"
    assert slot_name(SLOT_WINDOW_TINT) == "WINDOW_TINT"
    assert slot_name(105) == "DECAL_LEFT_DOOR_TEX6"
    assert slot_name(138) == "MISC"
    assert slot_name(139) is None
    assert slot_name(-1) is None


def test_catalog_loads_full_database():
    assert num_parts() == 11925


def test_ford_gt_anchors_resolve():
    gloss = part_at(FORD_GT_GLOSS_A)
    assert gloss is not None
    assert gloss.name == "GLOSS_L1_COLOR24"
    assert gloss.category == "PAINT"
    assert gloss.owner == "PAINT"


def test_paint_swatches_and_label_hashes():
    # RGB anchors from RE/paint_attrs_decoded.txt (2026-07-12).
    assert part_at(FORD_GT_GLOSS_A).rgb == (191, 38, 38)
    assert part_at(0x0E34).rgb == (110, 255, 0)          # gloss_B: bright green
    assert part_at(FORD_GT_GLOSS_A).gloss == 128
    # non-paint parts carry no swatch
    assert part_at(FORD_GT_BODY_VINYL).rgb is None
    # window tints carry FE display-label hashes instead of RGB
    tint = part_at(FORD_GT_TINT_STOCK)
    assert tint.rgb is None
    assert tint.language_hash == 0x3D263938

    chrome = part_at(FORD_GT_CHROME_B)
    assert chrome is not None
    assert chrome.name == "CHROME09_PAINT"

    vinyl = part_at(FORD_GT_BODY_VINYL)
    assert vinyl is not None
    assert vinyl.name == "BODY02"
    assert vinyl.category == "VINYL"

    tint = part_at(FORD_GT_TINT_STOCK)
    assert tint is not None
    assert tint.name == "STOCK WINDOW TINT"
    assert tint.category == "WINDOW_TINT"
    assert part_at(FORD_GT_TINT_STOCK + 1).name == "LIGHT BLACK"


def test_canon_display_names_resolve():
    # LANGUAGEHASH -> English.bin resolution, generated into the catalog
    # (gen_visual_parts.py name anchors, probe session 2026-07-16).
    assert part_at(126).name == "HOOD 6"
    assert part_at(126).display_name == "Overdial"
    assert part_at(FORD_GT_BODY_VINYL).display_name == "Body 2"
    assert part_at(FORD_GT_TINT_STOCK).display_name == "No Window Tint"
    assert part_at(FORD_GT_TINT_STOCK + 1).display_name == "Light Black"
    # paints and wheels carry no LANGUAGEHASH by design
    assert part_at(FORD_GT_GLOSS_A).display_name is None


def test_display_name_coverage_and_placeholder_filter():
    named = unlocalized = 0
    for index in range(num_parts()):
        info = part_at(index)
        if info.display_name is not None:
            named += 1
            assert "Localization" not in info.display_name
        if info.language_hash is not None and info.display_name is None:
            unlocalized += 1
    assert named == 2689
    # 5 CUSTOM_HUD_PAINT colours missing from English.bin + PSRTEST/COPGTO
    # placeholder vinyls fall back to engine names
    assert unlocalized == 7


def test_part_at_rejects_empty_and_out_of_range():
    assert part_at(EMPTY_SLOT) is None
    assert part_at(-1) is None
    assert part_at(num_parts()) is None


def test_every_part_has_valid_category_and_owner():
    seen_categories = set()
    for index in range(num_parts()):
        info = part_at(index)
        assert info is not None
        assert not info.category.startswith("?")
        assert info.owner
        seen_categories.add(info.category)
    # the big visual families must all be present
    for expected in ("PAINT", "VINYL", "VINYL_PAINT", "RIM_PAINT",
                     "WINDOW_TINT", "CUSTOM_HUD", "HOOD", "SPOILER", "BODY"):
        assert expected in seen_categories


def test_read_installed_indices_roundtrip():
    values = [EMPTY_SLOT] * NUM_SLOTS
    values[SLOT_BASE_PAINT] = FORD_GT_GLOSS_A
    values[SLOT_WINDOW_TINT] = FORD_GT_TINT_STOCK
    blob = b"\xCD" * 16 + struct.pack(f"<{NUM_SLOTS}H", *values) + b"\xCD" * 8

    read = read_installed_indices(blob, 16)
    assert read[SLOT_BASE_PAINT] == FORD_GT_GLOSS_A
    assert read[SLOT_BODY] == EMPTY_SLOT

    build = installed_parts(blob, 16)
    assert set(build) == {SLOT_BASE_PAINT, SLOT_WINDOW_TINT}
    assert build[SLOT_BASE_PAINT].name == "GLOSS_L1_COLOR24"
    assert build[SLOT_WINDOW_TINT].name == "STOCK WINDOW TINT"


def test_read_installed_indices_truncated_raises():
    try:
        read_installed_indices(b"\x00" * (INSTALLED_INDICES_SIZE - 1), 0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on truncated block")
