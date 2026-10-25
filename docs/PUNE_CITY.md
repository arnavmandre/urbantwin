# Pune — the active demo

Pune is the sole active demo: 1 km × 1 km simulation, 400 m × 400 m view, 2,069 buildings (272 in view), 329 OSM trees (115 in view), and 600 agents by default. The current calibration uses 41 survey participants, not surveyed Pune residents. The new 63-response experiment failed joint holdout checks and the coverage gate; it has not replaced the demo population. Frozen Phase 1–8 assets and the Phase 9 stage are archival, not the active city.

Central Pune is centred around Shaniwar Wada (18.5195 N, 73.8553 E).

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
Push-Location cities\pune; python pune_sim.py; python pune_view.py; Pop-Location
```

`build_script.py` needs Blender (`"<blender.exe>" -b -P build_script.py`); its outputs are committed
so normal use does not need Blender.

## How it connects

| Piece | Pune behaviour |
|---|---|
| API `POST /api/runs` | `"city": "pune"` is the default and may be sent explicitly. `api/run_manager.py` runs the city's pipeline from `integration/cities.py`. |
| Run folder | `data/runs/<id>/simulation_report.json` + `manifest.json` (`"city": "pune"`). The `simulation` stage records the simulator command, so `analytics/import_runs.py` stores `city_id = city_pune.json`. Failed or cancelled runs still import without a city. |
| Run summary | city facts, limitations and warnings come from the city registry; use the Pune profile. Rendered-walker figures refer to the 400 m view (about 40 % of citizens at a time). |
| Dashboard | Use live Pune runs and the Pune stream; recorded mock fixtures do not demonstrate a live Pune simulation. The dashboard presents Pune only. |
| Kit stream | `tools\demo_launch.ps1 -City pune` (add `-Force` to replace a running stream). Sets `URBANTWIN_STAGE` for the Kit launch scripts and `URBANTWIN_STREAM_CITY` for the API. |
| Before/After | `demoState` variant on `/World`: `Stressed` = before arm, `Intervention` = the simulator's after arm (same citizens re-simulated under the applied intervention). The existing Kit `view_commands` handler drives it unchanged. |
| Cameras | `/World/Cameras/{Overview, Aerial, Street, ProblemZone}`. Aerial is fixed (whole square). Overview, Street and ProblemZone are placed per run (`view_run.usdc`) at the busiest walker spots (ProblemZone: within the first problem zone), choosing the viewpoint with a clear line of sight that frames the most visible people without a wall filling the shot, always looking inward. |
| Heat map | Per run, in `view_run.usdc` under `/World/Routes/Heat`, one layer per arm inside `demoState`: each street segment of a chosen route coloured by the mean `heat_exposure` of the citizens whose route uses it, on one fixed 20-80 scale for both arms and every run (blue -> cyan -> yellow -> red, the dashboard legend's stops). Hidden by default; Kit's `congestion` overlay (the dashboard's Heat lens) shows it and hides the agents. Needs the Kit-repo handler change that hides `/World/Routes` for `behavior`/`shade`. Exposure per street is pooled from route choice; it is not a surface-temperature map. |
| Flood (demo) | Per run, `/World/Flood/Water` per arm: water over the whole street network whose depth (0.6 m at flood risk 100) and width (full 7 m carriageway at risk >= 25) scale with the arm's mean citizen `flood_risk`. Uniform on every street: Pune routes share one drainage value and there is no elevation data, so it shows how much water, never where it pools. Shown only by Kit's `flood` overlay (Kit-repo change); Before vs After is flooding without vs with the run's changes. |
| Interventions (demo) | Per run, `/World/Interventions` in the After arm only, for the actions the run applied: shade sails over the hottest walked streets (`shade_boost`), kerb drain channels along walked streets (`drainage_boost`), extra footpaths beside the before arm's problem routes (`route_capacity_boost`). The simulator applies each action city-wide, so positions are illustrative. Visible in every lens (Kit-repo change), so Before/After always means without/with the changes; the dashboard key lists what is drawn. |
| Publishing | a run copies `agents_before.usdc`, `agents_after.usdc`, `view_run.usdc` into `cities/pune/`; Kit started with auto-reload picks them up. |

## Deliberate exception: no canonical v1 snapshots

The canonical v1 snapshot contract belongs to the archival frozen Phase 1 `city_id`
and Phase 2 edge registry. Pune animates directly from the simulator report over
its own OSM route polylines (`pune_sim.animate`). Do not regenerate frozen assets.

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
