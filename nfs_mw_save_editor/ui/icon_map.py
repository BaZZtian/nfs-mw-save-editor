"""Centralized mapping from token/nav IDs to icon file paths."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from resources import resource_path

_ICONS_ROOT = resource_path("assets", "icons")


# -- Token ID -> icon file (relative to _ICONS_ROOT) --
TOKEN_ICONS: Dict[int, str] = {
    1:  "perf/perf_brakes.png",
    2:  "perf/perf_engine.png",
    3:  "perf/perf_nos.png",
    4:  "perf/perf_turbo.png",
    5:  "perf/perf_suspension.png",
    6:  "perf/perf_tires.png",
    7:  "perf/perf_transmission.png",
    8:  "vis/vis_body.png",
    9:  "vis/vis_hood.png",
    10: "vis/vis_spoiler.png",
    11: "vis/vis_rims.png",
    12: "vis/vis_roof.png",
    13: "vis/vis_gauge.png",
    14: "vis/vis_vinyl.png",
    15: "vis/vis_decal.png",
    16: "vis/vis_spray.png",
    17: "pol/pol_jail.png",
    18: "pol/pol_badge.png",
    19: "pol/pol_money.png",
    20: "pol/pol_impound_strike.png",
    21: "pol/pol_impound_release.png",
}

# Fallback icon for IDs without a dedicated asset.
_FALLBACK_TOKEN_ICON = "nav/unknown.png"

# -- Token ID -> "back side" icon for the hover coin-flip (relative to
# _ICONS_ROOT). INDUCTION (4) is one engine type covering turbo AND
# supercharger, and the game ships marker icons for both; the card shows
# turbo and flips to supercharger on hover, echoing the in-game marker
# spin animation.
TOKEN_BACK_ICONS: Dict[int, str] = {
    4: "perf/perf_supercharger.png",
}


# -- Navigation page -> icon file (relative to _ICONS_ROOT) --
NAV_ICONS: Dict[str, str] = {
    "Junkman":  "nav/nav_junkman.png",
    "Profile":  "nav/nav_profile.png",
    "Career":   "nav/nav_career.png",
    "Garage":   "nav/nav_garage.png",
    "Tuning":   "nav/nav_tuning.png",
    "Builds":   "nav/nav_builds.png",
    "Settings": "nav/nav_settings.png",
    "About":    "nav/nav_info.png",
}


# -- Career UI icon assets (relative to _ICONS_ROOT) --
GAME_ICONS: Dict[str, str] = {
    "race":       "career/race_events.png",
    "rival_race": "career/rival_race.png",
    "milestone":  "career/milestone_main.png",
    "trap":       "milestone/speedtrap.png",
    "blacklist":  "career/blacklist_top_15.png",
    "heat":       "career/heat.png",
    "bounty":     "career/bounty.png",
    "cops_damaged": "career/cops_damaged.png",
    "race_circuit": "race/circuit.png",
    "race_drag": "race/drag.png",
    "race_lap_knockout": "race/lap_knockout.png",
    "race_sprint": "race/sprint.png",
    "milestone_cost_to_state": "milestone/cost_to_state.png",
    "milestone_infractions": "milestone/infractions.png",
    "milestone_pursuit_bounty": "milestone/pursuit_bounty.png",
    "milestone_pursuit_duration": "milestone/pursuit_duration.png",
    "milestone_pursuit_mintime": "milestone/pursuit_mintime.png",
    "milestone_roadblocks": "milestone/roadblocks.png",
    "milestone_spikestrips": "milestone/spikestrips.png",
    "milestone_tollbooth": "milestone/tollbooth.png",
    "status_defeated": "status/defeated_eng.png",
    "action_apply_memory": "action/apply_memory.png",
    "action_save": "action/save.png",
    "action_open": "action/open.png",
    "action_checksums": "action/checksums.png",
    "action_reset": "action/reset.png",
    "timeline_check": "timeline/check.png",
    "timeline_arrow": "timeline/arrow.png",
}


def token_icon_path(token_id: int) -> Optional[Path]:
    """Return token icon path; unmapped IDs fall back to the generic icon."""
    rel = TOKEN_ICONS.get(token_id, _FALLBACK_TOKEN_ICON)
    p = _ICONS_ROOT / rel
    if p.exists():
        return p
    # Final fallback in case mapped file is missing.
    fallback = _ICONS_ROOT / _FALLBACK_TOKEN_ICON
    return fallback if fallback.exists() else None


def token_back_icon_path(token_id: int) -> Optional[Path]:
    """Return the flip-side icon for a token card, or None (most tokens)."""
    rel = TOKEN_BACK_ICONS.get(token_id)
    if rel is None:
        return None
    p = _ICONS_ROOT / rel
    return p if p.exists() else None


def nav_icon_path(page_name: str) -> Optional[Path]:
    """Return absolute Path for a nav icon, or None if not mapped."""
    rel = NAV_ICONS.get(page_name)
    if rel is None:
        return None
    p = _ICONS_ROOT / rel
    return p if p.exists() else None


def game_icon_path(icon_name: str) -> Optional[Path]:
    """Return absolute Path for a game-sourced UI icon, or None if not mapped."""
    rel = GAME_ICONS.get(icon_name)
    if rel is None:
        return None
    p = _ICONS_ROOT / rel
    return p if p.exists() else None


def rival_asset_path(stage: int, asset_kind: str = "portrait") -> Optional[Path]:
    """Return a Blacklist rival asset for ``stage`` (15=Sonny, 1=Razor)."""
    suffixes = {
        "portrait": "",
        "graffiti": "_graf",
        "hero_portrait": "_hero_fg",
    }
    suffix = suffixes.get(asset_kind)
    if suffix is None or not 1 <= int(stage) <= 15:
        return None
    if asset_kind.startswith("hero"):
        path = _ICONS_ROOT / "rivals" / "hero" / f"rival_{int(stage):02d}{suffix}.png"
    else:
        path = _ICONS_ROOT / "rivals" / f"rival_{int(stage):02d}{suffix}.png"
    return path if path.exists() else None


# -- Category -> representative icon --
# All four faces are the game's own category markers from FRONTB, carried over
# pixel for pixel: MARKER_ICON_PERFORMANCE / _PARTS / _VISUAL / _MISC. The "?"
# on Bonus Markers is the game's surprise-marker glyph.
# "All" has no marker of its own; it borrows the nav rail's Junkman face, so the
# unfiltered row reads as "the whole page".
CAT_ICONS: Dict[str, str] = {
    "All":           "nav/nav_junkman.png",
    "Performance":   "cat/cat_performance.png",
    "Parts":         "cat/cat_parts.png",
    "Visual":        "cat/cat_visual.png",
    "Bonus Markers": "cat/cat_bonus_markers.png",
}


def cat_icon_path(category: str) -> Optional[Path]:
    """Return absolute Path for a category filter icon, or None."""
    rel = CAT_ICONS.get(category)
    if rel is None:
        return None
    p = _ICONS_ROOT / rel
    return p if p.exists() else None
