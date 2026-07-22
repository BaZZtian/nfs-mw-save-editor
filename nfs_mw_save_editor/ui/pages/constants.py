"""Module-level constants shared across MainWindow and page mixins."""
from dataclasses import dataclass

# Marker categories follow the game's own 4-way FE grouping (the parts-shop
# tabs + bonus markers): Performance 1-7, Parts 8-12 (body kit, hood, spoiler,
# rims, roof scoop), Visual 13-16 (gauge, vinyl, decal, paint), Bonus Markers
# 17-21. "All" is the editor's filter pseudo-category.
CAT_LIST = ["All", "Performance", "Parts", "Visual", "Bonus Markers"]
APP_NAME = "NFS_MW_Junkman_Editor"
APP_DISPLAY_NAME = "NFS MW Save Editor"
APP_VERSION = "v1.5.0"
APP_PLATFORM = "PC"
APP_WINDOW_TITLE = f"{APP_DISPLAY_NAME} ({APP_PLATFORM} {APP_VERSION})"
UI_TITLE_BLOCKED = "Blocked"
UI_TITLE_UNAVAILABLE = "Unavailable"
UI_TITLE_SNAPSHOT_UNAVAILABLE = "Snapshot unavailable"
UI_TITLE_APPLY_FAILED = "Apply failed"
CATALOG_FILENAME = "token_catalog.json"
# Engine enum ePossibleMarker: MARKER_FIRST = 1, MARKER_LAST = 21 (confirmed
# on PC v1.3 via the MarkerSelectInfo table in speed.exe; IDs above 21 are
# inert - the game neither shows nor consumes them).
SAFE_TYPE_MIN = 1
SAFE_TYPE_MAX = 21
PERF_IDS = (1, 2, 3, 4, 5, 6, 7)
PERF_TOTAL = 7
DEFAULT_CARDS_PER_ROW = 3
MAX_CARDS_PER_ROW = 4
# Bottom inset for scrollable page content so fully-scrolled cards clear the
# floating footer cards (they occupy ~76px from the stack bottom: 44px buttons
# + card padding/border + 14px margin) with comfortable air above the glass.
FOOTER_CLEARANCE = 100
U32_MAX = 0xFFFFFFFF
GARAGE_TILE_MIN_WIDTH = 230
GARAGE_TILE_MAX_COLUMNS = 3
PARTS_TILE_MIN_WIDTH = 340
PARTS_TILE_MAX_COLUMNS = 2
MY_CARS_TILE_MIN_WIDTH = 340
MY_CARS_TILE_MAX_COLUMNS = 2
SNAPSHOT_TILE_MIN_WIDTH = 380
SNAPSHOT_TILE_MAX_COLUMNS = 2
LIBRARY_TILE_MIN_WIDTH = 380
LIBRARY_TILE_MAX_COLUMNS = 2

# Blacklist stage number -> boss name (stage == CareerSettings.CurrentBin).
BLACKLIST_BOSS_NAMES = {
    15: "Sonny",
    14: "Taz",
    13: "Vic",
    12: "Izzy",
    11: "Big Lou",
    10: "Baron",
    9: "Earl",
    8: "Jewels",
    7: "Kamikaze",
    6: "Ming",
    5: "Webster",
    4: "JV",
    3: "Ronnie",
    2: "Bull",
    1: "Razor",
}


@dataclass
class TokenEntry:
    id: int
    name: str
    category: str = "Unknown"
