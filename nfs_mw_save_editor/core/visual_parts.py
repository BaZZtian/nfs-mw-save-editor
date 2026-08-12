"""Visual customization catalog: save part indices -> engine part names.

The 0x198 parts block is a serialized engine FECustomizationRecord. Its first
0x116 bytes are InstalledPartIndices[139]: one u16 per CAR_SLOT_ID (23 BODY,
44 SPOILER, 63 HOOD, 76 BASE_PAINT, 77 VINYL_LAYER0, 78 PAINT_RIM,
131 WINDOW_TINT, ...), 0xFFFF = slot empty. Each value is a flat index into
the game's master CarPart pack (GLOBAL/GLOBALB.BUN), shipped offline as
assets/visual_parts_catalog.json so the editor needs no game install.

`name` is the engine-internal one (GLOSS_L1_COLOR24, BODY02, HOOD 6 CARBON);
`display_name` is the canon in-game label resolved at catalog-generation time
from the part's LANGUAGEHASH attribute via LANGUAGES/English.bin ("Overdial",
"Light Black") — present for 2689 parts (hoods/spoilers/roofs/bodies/vinyls/
tints/HUDs; paints and wheels have no LANGUAGEHASH by design). Prettifying
engine names stays a UI concern. The index space is install-specific: saves
made on installs with modded part data shift indices, so resolved names are
only authoritative for saves from a matching (vanilla PC v1.3) part database.

The catalog is generated from game data and checked against controlled saves.
Do not edit the JSON by hand.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CATALOG_FILENAME = "visual_parts_catalog.json"

#: InstalledPartIndices value meaning "nothing installed in this slot".
EMPTY_SLOT = 0xFFFF

#: Number of CAR_SLOT_ID entries (engine CARSLOTID_NUM).
NUM_SLOTS = 139

#: Byte length of the InstalledPartIndices array inside a parts block.
INSTALLED_INDICES_SIZE = NUM_SLOTS * 2

# Key slots (engine CAR_SLOT_ID values).
SLOT_BODY = 23
SLOT_SPOILER = 44
SLOT_ROOF = 62
SLOT_HOOD = 63
SLOT_FRONT_WHEEL = 66
SLOT_REAR_WHEEL = 67
SLOT_SPINNER = 68
SLOT_LICENSE_PLATE = 69
SLOT_BASE_PAINT = 76
SLOT_VINYL_LAYER0 = 77
SLOT_PAINT_RIM = 78
SLOT_VINYL_COLOUR0_0 = 79
SLOT_VINYL_COLOUR0_3 = 82
SLOT_WINDOW_TINT = 131
SLOT_CUSTOM_HUD = 132
SLOT_HUD_BACKING_COLOUR = 133
SLOT_HUD_NEEDLE_COLOUR = 134
SLOT_HUD_CHARACTER_COLOUR = 135


def _build_slot_names() -> Tuple[str, ...]:
    names: Dict[int, str] = {}
    fixed = {
        0: "BASE", 23: "BODY", 24: "FRONT_BRAKE", 25: "FRONT_LEFT_WINDOW",
        26: "FRONT_RIGHT_WINDOW", 27: "FRONT_WINDOW", 28: "INTERIOR",
        29: "LEFT_BRAKELIGHT", 30: "LEFT_BRAKELIGHT_GLASS", 31: "LEFT_HEADLIGHT",
        32: "LEFT_HEADLIGHT_GLASS", 33: "LEFT_SIDE_MIRROR", 34: "REAR_BRAKE",
        35: "REAR_LEFT_WINDOW", 36: "REAR_RIGHT_WINDOW", 37: "REAR_WINDOW",
        38: "RIGHT_BRAKELIGHT", 39: "RIGHT_BRAKELIGHT_GLASS", 40: "RIGHT_HEADLIGHT",
        41: "RIGHT_HEADLIGHT_GLASS", 42: "RIGHT_SIDE_MIRROR", 43: "DRIVER",
        44: "SPOILER", 45: "UNIVERSAL_SPOILER_BASE", 62: "ROOF", 63: "HOOD",
        64: "HEADLIGHT", 65: "BRAKELIGHT", 66: "FRONT_WHEEL", 67: "REAR_WHEEL",
        68: "SPINNER", 69: "LICENSE_PLATE", 70: "DECAL_FRONT_WINDOW",
        71: "DECAL_REAR_WINDOW", 72: "DECAL_LEFT_DOOR", 73: "DECAL_RIGHT_DOOR",
        74: "DECAL_LEFT_QUARTER", 75: "DECAL_RIGHT_QUARTER", 76: "BASE_PAINT",
        77: "VINYL_LAYER0", 78: "PAINT_RIM", 131: "WINDOW_TINT", 132: "CUSTOM_HUD",
        133: "HUD_BACKING_COLOUR", 134: "HUD_NEEDLE_COLOUR",
        135: "HUD_CHARACTER_COLOUR", 136: "CV", 137: "WHEEL_MANUFACTURER",
        138: "MISC",
    }
    names.update(fixed)
    damage = [
        "FRONT_WINDOW", "BODY", "COP_LIGHTS", "COP_SPOILER", "FRONT_WHEEL",
        "LEFT_BRAKELIGHT", "RIGHT_BRAKELIGHT", "LEFT_HEADLIGHT",
        "RIGHT_HEADLIGHT", "HOOD", "BUSHGUARD", "FRONT_BUMPER", "RIGHT_DOOR",
        "RIGHT_REAR_DOOR", "TRUNK", "REAR_BUMPER", "REAR_LEFT_WINDOW",
        "FRONT_LEFT_WINDOW", "FRONT_RIGHT_WINDOW", "REAR_RIGHT_WINDOW",
        "LEFT_DOOR", "LEFT_REAR_DOOR",
    ]
    for i, part in enumerate(damage, start=1):
        names[i] = f"DAMAGE_{part}"
    for i, zone in enumerate(
        ["FRONT", "FRONTLEFT", "FRONTRIGHT", "REAR", "REARLEFT", "REARRIGHT"],
        start=46,
    ):
        names[i] = f"DAMAGE0_{zone}"
    for i in range(52, 62):
        names[i] = f"ATTACHMENT{i - 52}"
    for i in range(79, 83):
        names[i] = f"VINYL_COLOUR0_{i - 79}"
    zones = [
        (83, "FRONT_WINDOW"), (91, "REAR_WINDOW"), (99, "LEFT_DOOR"),
        (107, "RIGHT_DOOR"), (115, "LEFT_QUARTER"), (123, "RIGHT_QUARTER"),
    ]
    for base, zone in zones:
        for k in range(8):
            names[base + k] = f"DECAL_{zone}_TEX{k}"
    assert len(names) == NUM_SLOTS and set(names) == set(range(NUM_SLOTS))
    return tuple(names[i] for i in range(NUM_SLOTS))


#: CAR_SLOT_ID -> engine slot name, all 139 slots.
CAR_SLOT_NAMES: Tuple[str, ...] = _build_slot_names()


@dataclass(frozen=True)
class PartInfo:
    """One entry of the game's master part database."""

    index: int
    category_id: int      # engine CAR_PART_ID
    category: str         # e.g. "PAINT", "HOOD", "VINYL"
    owner: str            # car type (FORDGT) or pseudo-group (PAINT, VINYL, ...)
    name: str             # engine part name, e.g. "GLOSS_L1_COLOR24"
    raw_group_upgrade: int
    rgb: Optional[Tuple[int, int, int]] = None   # paint-family swatch (RED/GREEN/BLUE attrs)
    gloss: Optional[int] = None                  # paint GLOSS strength attr (0..255)
    language_hash: Optional[int] = None          # FE display-label hash (English.bin)
    display_name: Optional[str] = None           # canon in-game label ("Overdial")


def _catalog_path() -> Path:
    try:
        from resources import resource_path
        return resource_path("assets", CATALOG_FILENAME)
    except ImportError:
        return Path(__file__).resolve().parents[1] / "assets" / CATALOG_FILENAME


@lru_cache(maxsize=1)
def _catalog() -> dict:
    with open(_catalog_path(), encoding="utf-8") as fh:
        return json.load(fh)


def num_parts() -> int:
    return len(_catalog()["parts"])


def catalog_source_md5() -> str:
    """MD5 of the GLOBALB.BUN the catalog was generated from (provenance)."""
    return _catalog()["source_md5"]


def slot_name(slot_id: int) -> Optional[str]:
    if 0 <= slot_id < NUM_SLOTS:
        return CAR_SLOT_NAMES[slot_id]
    return None


def part_at(index: int) -> Optional[PartInfo]:
    """Resolve a save slot value to a part; None for empty/out-of-range."""
    doc = _catalog()
    parts: List[list] = doc["parts"]
    if index == EMPTY_SLOT or not 0 <= index < len(parts):
        return None
    pid, tn_idx, upg, name = parts[index]
    cat_names = doc["carpartid_names"]
    category = cat_names[pid] if 0 <= pid < len(cat_names) else f"?{pid}"
    color = doc["colors"].get(str(index))
    return PartInfo(
        index=index,
        category_id=pid,
        category=category,
        owner=doc["typenames"][tn_idx],
        name=name,
        raw_group_upgrade=upg,
        rgb=tuple(color[:3]) if color else None,
        gloss=color[3] if color and len(color) > 3 else None,
        language_hash=doc["lang_hashes"].get(str(index)),
        display_name=doc.get("lang_names", {}).get(str(index)),
    )


def read_installed_indices(data: bytes, block_abs_off: int) -> Tuple[int, ...]:
    """Read InstalledPartIndices[139] from a parts block at block_abs_off."""
    raw = bytes(data[block_abs_off:block_abs_off + INSTALLED_INDICES_SIZE])
    if len(raw) != INSTALLED_INDICES_SIZE:
        raise ValueError("parts block truncated")
    return struct.unpack(f"<{NUM_SLOTS}H", raw)


def installed_parts(data: bytes, block_abs_off: int) -> Dict[int, PartInfo]:
    """Non-empty, resolvable slots of a build: slot_id -> PartInfo."""
    out: Dict[int, PartInfo] = {}
    for slot_id, value in enumerate(read_installed_indices(data, block_abs_off)):
        info = part_at(value)
        if info is not None:
            out[slot_id] = info
    return out
