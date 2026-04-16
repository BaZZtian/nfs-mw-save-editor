"""Module-level constants shared across MainWindow and page mixins."""
from dataclasses import dataclass

CAT_LIST = ["All", "Performance", "Visual", "Police", "Unknown"]
APP_NAME = "NFS_MW_Junkman_Editor"
APP_DISPLAY_NAME = "NFS MW Save Editor"
APP_VERSION = "v1.4.0"
APP_PLATFORM = "PC"
APP_WINDOW_TITLE = f"{APP_DISPLAY_NAME} ({APP_PLATFORM} {APP_VERSION})"
UI_TITLE_BLOCKED = "Blocked"
UI_TITLE_UNAVAILABLE = "Unavailable"
UI_TITLE_SNAPSHOT_UNAVAILABLE = "Snapshot unavailable"
UI_TITLE_APPLY_FAILED = "Apply failed"
CATALOG_FILENAME = "token_catalog.json"
SAFE_TYPE_MIN = 1
SAFE_TYPE_MAX = 22
PERF_IDS = (1, 2, 3, 4, 5, 6, 7)
PERF_TOTAL = 7
DEFAULT_CARDS_PER_ROW = 3
MAX_CARDS_PER_ROW = 4
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


@dataclass
class TokenEntry:
    id: int
    name: str
    category: str = "Unknown"
