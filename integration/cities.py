"""The cities a run can target, and the facts the API, summaries and stream probe report for each.

London is the original Phase 1-11 city (canonical v1 snapshot pipeline). Pune runs through
cities/pune/run_pune.py, which skips canonical snapshots by design (docs/PUNE_CITY.md).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CITY = "london"

CITIES = {
    "london": {
        "name": "Russell Square, London",
        "stage": "phase9/scene/main.usda",
        "snapshot_pattern": "data/simulation_before_*.json",
        "citizens": "Simulation/citizens_survey_city_osm.json",
        "city_file": "Simulation/city_osm.json",
        "pipeline": "integration/run_pipeline.py",
        "visual_buildings": 623,
        "visual_trees": 511,
        "limitations": [
            "Not a time-evolving crowd simulation. The animation interpolates between 60 fixed "
            "snapshots at one equilibrium.",
            "Not a surveyed skyline: 223 of 623 building heights come from OSM, the rest are inferred.",
        ],
    },
    "pune": {
        "name": "Shaniwar Wada, central Pune",
        "stage": "cities/pune/main_view_400m.usda",
        "snapshot_pattern": None,  # no canonical snapshots for Pune
        "citizens": "cities/pune/citizens_pune.json",
        "city_file": "cities/pune/city_pune.json",
        "pipeline": "cities/pune/run_pune.py",
        "visual_buildings": None,  # read from the view's manifest below
        "visual_trees": None,
        "limitations": [
            "Not a time-evolving crowd simulation. Each walker replays its simulator-chosen route at "
            "3x real time; behaviour colours are one equilibrium.",
            "Vehicles are illustrative only: there is no traffic data for this area.",
            "Citizen behaviour is calibrated on the 41-person Argus survey, not on Pune residents.",
            "Facade windows, wall tints and the people and vehicle models are appearance, not data.",
        ],
    },
}


def city_profile(key: str | None) -> dict:
    """Profile for a city key (default London). Pune's rendered counts come from its manifest when present."""
    key = key or DEFAULT_CITY
    profile = dict(CITIES[key], key=key)
    profile["limitations"] = list(profile["limitations"])
    if key == "pune":
        try:
            manifest = json.loads((ROOT / "cities" / "pune" / "manifest.json").read_text(encoding="utf-8"))
            counts = manifest["view_400m"]["counts"]
            profile["visual_buildings"] = counts["buildings_kept"]
            profile["visual_trees"] = counts["trees_kept"]
            sources = manifest["height_source_counts"]
            tagged = sources.get("osm_height", 0) + sources.get("osm_levels", 0)
            profile["limitations"].append(
                f"Not a surveyed skyline: {tagged} of {sum(sources.values())} building heights come from OSM "
                "tags, the rest are interpolated from neighbours or inferred from building class.")
        except (OSError, KeyError, ValueError):
            pass
    return profile
