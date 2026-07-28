from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from ui.pages.constants import (
    PARTS_GRID_SIDE_MARGIN,
    PARTS_GRID_SPACING,
    PARTS_TILE_MAX_COLUMNS,
    PARTS_TILE_MIN_WIDTH,
)
from ui.rendering import fit_columns

# Tuning grid geometry (parts_cards_layout): 12px side margins, 14px spacing.
MARGINS = 2 * PARTS_GRID_SIDE_MARGIN
SPACING = PARTS_GRID_SPACING


def _needed_width(columns: int, card_min: int) -> int:
    return MARGINS + columns * card_min + (columns - 1) * SPACING


def test_single_column_until_two_cards_actually_fit():
    card_min = 400
    two_columns_at = _needed_width(2, card_min)

    assert fit_columns(two_columns_at - MARGINS - 1, card_min, spacing=SPACING, max_columns=2) == 1
    assert fit_columns(two_columns_at - MARGINS, card_min, spacing=SPACING, max_columns=2) == 2


def test_column_count_never_exceeds_the_viewport():
    """The card scroll areas have no horizontal scrollbar - overflow is clipping."""
    for viewport in range(600, 2600, 7):
        columns = fit_columns(
            viewport - MARGINS,
            PARTS_TILE_MIN_WIDTH,
            spacing=SPACING,
            max_columns=PARTS_TILE_MAX_COLUMNS,
        )
        assert 1 <= columns <= PARTS_TILE_MAX_COLUMNS
        if columns > 1:
            assert _needed_width(columns, PARTS_TILE_MIN_WIDTH) <= viewport


def test_max_columns_caps_a_very_wide_viewport():
    assert fit_columns(10_000, 300, spacing=SPACING, max_columns=2) == 2
    assert fit_columns(10_000, 300, spacing=SPACING, max_columns=4) == 4


def test_degenerate_inputs_fall_back_to_one_column():
    assert fit_columns(0, 400, spacing=SPACING, max_columns=3) == 1
    assert fit_columns(-50, 400, spacing=SPACING, max_columns=3) == 1
    assert fit_columns(1200, 0, spacing=SPACING, max_columns=3) == 1
