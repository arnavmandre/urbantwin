# Pune — second city

Central Pune (1 km × 1 km around Shaniwar Wada, 18.5195 N 73.8553 E) runs on the same
unmodified simulator as London and can be selected from the dashboard and streamed through Kit.
Everything lives in `cities/pune/`; London's Phase 1–11 path is untouched.

## Pipeline

```
pune_center.osm (Overpass, unmodified, stored as binary)
  -> build_script.py      Blender 4.x, headless: footprints, heights, materials, USD export,
                          pxr post-process, section-7 validation, render
                          -> city_base.usda, environment.usda, main.usda, manifest.json   (committed)
                          pune_sim/pune_view record their facts in manifest.generated.json (gitignored)
  -> pune_sim.py          simulator city + survey citizens + route polylines + illustrative traffic,
                          default-scenario run, both arms animated  -> main_live.usda (1 km)
  -> pune_view.py         400 m view: clipping, realistic look, cameras -> main_view_400m.usda
  -> run_pune.py          one dashboard run: simulate -> animate both arms -> view mask -> publish
```

Generated files are gitignored (`cities/pune/.gitignore`) and rebuild deterministically in ~15 s:

```powershell
cd cities\pune; python pune_sim.py; python pune_view.py
```

`build_script.py` needs Blender (`"<blender.exe>" -b -P build_script.py`); its outputs are committed
so normal use does not need Blender.

## How it connects

| Piece | Pune behaviour |
|---|---|
| API `POST /api/runs` | optional `"city": "london" \| "pune"` (default London). `api/run_manager.py` runs the city's pipeline from `integration/cities.py`. |
| Run folder | `data/runs/<id>/simulation_report.json` + `manifest.json` (`"city": "pune"`), same shape as London. The `simulation` stage records the simulator command, so `analytics/import_runs.py` stores `city_id = city_pune.json` (London: `city_osm.json`). Failed or cancelled runs still import without a city. |
| Run summary | city facts, limitations and warnings come from the city registry; a Pune run never shows London counts. Rendered-walker figures refer to the 400 m view (about 40 % of citizens at a time). |
| Dashboard | City switch in the Scenario drawer. Pune is disabled in mock mode (fixtures are London only). While streaming, the header names the streamed city, and a note on the viewport appears when the last run is for the other city. |
| Kit stream | `tools\demo_launch.ps1 -City pune` (add `-Force` to replace a running stream). Sets `URBANTWIN_STAGE` for the Kit launch scripts and `URBANTWIN_STREAM_CITY` for the API. |
| Before/After | `demoState` variant on `/World`: `Stressed` = before arm, `Intervention` = the simulator's after arm (same citizens re-simulated under the applied intervention). The existing Kit `view_commands` handler drives it unchanged. |
| Cameras | `/World/Cameras/{Overview, Aerial, Street, ProblemZone}`; ProblemZone is re-aimed per run at the run's first problem zone. |
| Publishing | a run copies `agents_before.usdc`, `agents_after.usdc`, `view_run.usdc` into `cities/pune/`; Kit started with auto-reload picks them up. |

## Deliberate exception: no canonical v1 snapshots

CLAUDE.md rule 4 says visualisation reads canonical v1 snapshots. That contract is bound to the frozen
London Phase 1 `city_id` and the Phase 2 edge registry, neither of which exists for Pune. Pune animates
directly from the simulator report over its own OSM route polylines (`pune_sim.animate`). London still
follows rule 4 exactly.

## What is real and what is not

- Real: OSM footprints, 2,069 buildings, roads/paths/greens, 329 trees at surveyed positions;
  route choice, travel time, behaviour and metrics from the unmodified simulator.
- Heights: 40 of 2,069 from OSM tags; 127 interpolated from neighbours; the rest inferred from class.
- Heuristic inputs (no Pune data): drainage 0.5, flood exposure 0.3, capacity/cooling by building type,
  base crowding by road class. Route shade = share of the route within 10 m of a real OSM tree, and route
  greenery reuses the same value.
- Citizens: calibrated on the 41-person Argus survey, not Pune residents; homes/destinations are the
  `phase10/assign_homes.py` heuristic.
- Animation: each walker follows its simulator-chosen route at its own survey speed, in real time,
  keeping left on the pavement beside the carriageway, crossing the street at each end and returning on
  the other pavement (corners rounded, no jumps). 120 s loop, sampled 6×/s and interpolated by USD.
  No collision avoidance: walkers can brush past each other (~1 %). Not a time-evolving simulation.
- Vehicles share one speed per road and are evenly spaced, so they never overlap on a road; vehicles on
  crossing roads can still meet at junctions (there is no traffic model).
- Vehicles: illustrative only (one per 70 m of road, ~20 km/h, ~30 % auto-rickshaws, driving on the left).
- Facade windows, wall tints, roofs and the people/vehicle models are appearance, not data.
