from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.visual_parts import (
    PartInfo,
    SLOT_BASE_PAINT,
    SLOT_BODY,
    SLOT_FRONT_WHEEL,
    SLOT_HOOD,
    SLOT_ROOF,
    SLOT_SPOILER,
    SLOT_VINYL_LAYER0,
    SLOT_WINDOW_TINT,
)
from ui.pages.visual_summary import (
    build_visual_summary,
    paint_label,
    rival_livery,
    wheel_label,
)


def _part(name: str, category: str = "X", rgb=None) -> PartInfo:
    return PartInfo(
        index=0, category_id=0, category=category, owner="X",
        name=name, raw_group_upgrade=0, rgb=rgb,
    )


def test_paint_labels():
    assert paint_label("GLOSS_L1_COLOR24") == "Gloss #24"
    assert paint_label("METAL_L1_COLOR51") == "Metallic #51"
    assert paint_label("PEARL_L2_COLOR03") == "Pearl #03"
    assert paint_label("CHROME09_PAINT") == "Chrome #09"


def test_wheel_labels():
    assert wheel_label("VOLK TE37 20 25") == "Volk TE37 20″"
    assert wheel_label("O.Z. SUPERLEGGERA 20 25") == "O.Z. Superleggera 20″"


def test_rival_livery_detection():
    assert rival_livery(_part("13VICTORVASQUEZ")) == (13, "Vic")
    assert rival_livery(_part("14VINCEKILIC")) == (14, "Taz")
    assert rival_livery(_part("BODYSTRIPE09")) is None
    assert rival_livery(None) is None


def test_summary_full_build():
    build = {
        SLOT_BASE_PAINT: _part("GLOSS_L1_COLOR46", "PAINT", rgb=(95, 66, 0)),
        SLOT_BODY: _part("BODY_03", "BODY"),
        SLOT_SPOILER: _part("SPOILER 36 CF", "SPOILER"),
        SLOT_HOOD: _part("HOOD 26", "HOOD"),
        SLOT_ROOF: _part("TEMPEST CF", "ROOF"),
        SLOT_FRONT_WHEEL: _part("VOLK TE37 20 25", "WHEEL"),
        SLOT_WINDOW_TINT: _part("MEDIUM RED", "WINDOW_TINT"),
        SLOT_VINYL_LAYER0: _part("14VINCEKILIC", "VINYL"),
    }
    vm = build_visual_summary(build)
    assert vm is not None
    assert vm.swatch_rgb == (95, 66, 0)
    assert "Gloss #46" in vm.text
    assert "Kit 03" in vm.text
    assert "Spoiler 36 CF" in vm.text
    assert "Tempest CF" in vm.text
    assert "Volk TE37 20″" in vm.text
    assert "Tint: Medium Red" in vm.text
    assert vm.livery_text == "Rival livery — #14 Taz"
    assert "Livery" in vm.livery_tooltip
    assert "GLOSS_L1_COLOR46" in vm.tooltip
    assert "RGB 95,66,0" in vm.tooltip


def test_summary_stock_build_filters_noise():
    build = {
        SLOT_BASE_PAINT: _part("GLOSS_L1_COLOR24", "PAINT", rgb=(191, 38, 38)),
        SLOT_BODY: _part("BODY_00", "BODY"),
        SLOT_SPOILER: _part("SPOILER", "SPOILER"),
        SLOT_HOOD: _part("STOCK", "HOOD"),
        SLOT_ROOF: _part("NO ROOF SCOOP", "ROOF"),
        SLOT_FRONT_WHEEL: _part("WHEEL", "WHEEL"),
        SLOT_WINDOW_TINT: _part("STOCK WINDOW TINT", "WINDOW_TINT"),
    }
    vm = build_visual_summary(build)
    assert vm is not None
    assert vm.text == "Gloss #24"
    assert vm.livery_text is None


def test_summary_plain_vinyl_and_empty():
    build = {SLOT_VINYL_LAYER0: _part("BODYSTRIPE09", "VINYL")}
    vm = build_visual_summary(build)
    assert vm is not None
    assert vm.swatch_rgb is None
    assert vm.text == "Vinyl: Bodystripe #09"
    assert vm.livery_text is None

    assert build_visual_summary({}) is None
