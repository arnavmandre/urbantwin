# UrbanTwin AI — working notes for Claude

Hackathon project. Human-centric urban digital twin: Python simulation +
OpenUSD/Omniverse visualisation + survey-calibrated synthetic citizens.

## Before creating ANY new script, check whether it already exists

This repo has been built across several sessions. Long sessions get summarised,
and work done earlier can drop out of context — it has already happened once
that a whole set of tools was rebuilt from scratch under new filenames, creating
silent duplicates (`build_presentation.py` vs `make_cameras.py`+`set_scenario.py`,
`colorize_from_snapshot.py` vs `recolor_paths.py`, `build_route_mapping.py` vs
`propose_route_mapping.py`).

**So: `ls` the target directory and `git log --oneline -15` before writing a new
file.** If something close already exists, extend it rather than adding a
parallel implementation. If you genuinely think a rewrite is better, say so and
delete the old one — never leave both.

Commit at each working milestone. Commits are the checkpoint that survives
context loss.

## Layout

| Path | Owner | Notes |
|---|---|---|
| `Simulation/` | simulation | `main.py` is self-contained, dependency-free, deterministic. `python main.py` runs ~80 asserts then the demo. |
| `phase1/`–`phase8/` | visualisation | OSM city → semantics → contract → bridges → packaged states. **Treat as frozen.** |
| `integration/` | boundary | Snapshot loader, route-mapping proposal tooling, and `export_api_mocks.py` (simulator report -> frontend fixtures). |
| `api/` | local HTTP | Phase 12 stdlib server: `python -m api`. Single-worker Phase 11 runs; see `docs/PHASE12_LOCAL_API.md`. |
| `frontend/` | web | Next.js dashboard. Default = recorded fixtures (`mode: "mock"`). Set `URBANTWIN_API_BASE` to proxy Phase 12. See `frontend/README.md`. |
| `phase9/` | realism + demo | Materials, heights, trees, lighting, cameras, overlays — all `over` layers — plus `build_city_from_osm.py`. **Open `phase9/scene/main.usda` for the demo.** |
| `phase10/` | survey | Real survey -> calibrated synthetic citizens. `data/` holds the four-table dataset. |
| `analytics/` | run history | Phase 18: Postgres + Grafana (Docker) and `import_runs.py`, which copies `data/runs/` + `data/run_events.jsonl` into the DB. See `docs/PHASE18_GRAFANA_ANALYTICS.md`. |
| `docs/` | contracts | `INTEGRATION_CONTRACT.md` is authoritative. |

Frontend/backend product context is in `docs/FRONTEND_BACKEND_HANDOFF.md`. Local
live HTTP is documented in `docs/PHASE12_LOCAL_API.md`. Browser WebRTC is on
`main` (`docs/PHASE14_BROWSER_WEBRTC.md`). Do not present mocks as a live
backend. Omniverse streaming appears live only when Kit signaling passes the API
probe **and** the Chromium client connects; mock mode keeps stream offline. The
probe is only a TCP connect, so a stale "ghost" listener still reads as online:
trust the viewport chip, not the header. View commands: API allow-list, then
WebRTC `sendMessage` to Kit (`docs/PHASE15_KIT_COMMAND_DELIVERY.md`). **`delivered:
true` only means the browser's send resolved, not that Kit applied it.**

**The Kit half is NOT in this repo.** It lives in
`C:\Users\arnav\omniverse\kit-app-template` (branch `phase13-streaming-kit`): the
`omni.kit.livestream.messaging` dependency, the `urbantwin.view_commands` handler,
the `urbantwin.stage_autoload` clean-view extension, and the GPU settings. Without
it, commands are dropped. Read `docs/CLAUDE_HANDOFF_STREAMING.md` "Resolution".

## Hard rules

1. **Never edit `phase1/`–`phase8/` scene layers.** `city_id` is the SHA-256 of
   the frozen Phase 1 manifest; the scene contract depends on it. Add `over`
   layers in `phase9/` instead.
2. **Never write `integration/route_mapping.json` automatically.** That filename
   is reserved for a mapping the *team* has agreed. Tools emit
   `route_mapping.proposal.json`. Auto-chosen anchors are geometrically real but
   semantically provisional — nobody has agreed which OSM building is "the
   hospital".
3. **The simulator's `citizens.json` schema is fixed:** `id, archetype, home,
   destination, heat_tolerance, rain_tolerance, crowd_tolerance,
   walking_speed_kmh, green_preference, transit_preference` (+ optional
   `weight`). Unknown keys are ignored silently, so a typo = a dropped field.
4. **Visualisation reads canonical v1 snapshots**, not
   `Simulation/urbantwin_demo_output.json`. The exporter owns normalisation
   (0–100 → 0–1) and route→edge mapping.
5. **Metrics are heuristic prototypes**, not medical/meteorological models. Keep
   the disclaimers in output and docs.

## Integrity — this project is judged

Only claim what the code does when executed. Verified as of this writing:

- ✅ Deterministic; data-driven city and citizens; per-citizen route choice
  responds to heat/rain/crowd/transit/green; emergent corridor congestion
  (MSA-damped iterative assignment); citizen profiles move the HEI.
- ✅ Phase 9: 623 buildings carry 12 distinct OSM-derived materials and heights
  spanning 2–39 m; 511 trees at surveyed OSM positions; `city_osm.json` runs the
  simulator on real Russell Square geometry with `osm_edges` on every route.
- ✅ Phase 10: citizen behavioural parameters ARE calibrated from 41 real
  survey participants (copula-sampled, holdout-validated 5/5). But the scenario
  design is confounded (temp+crowd+shade move together) - say "calibrated",
  never "separately measured per factor". home/destination is a heuristic,
  not survey data.
- ⚠️ Building heights: only **223 of 623** come from real OSM data
  (`urbantwin:heightSource` records each one). The rest are inferred from
  building class or interpolated from neighbours. Do not call the skyline
  surveyed.
- ⚠️ The default 8-building `city.json` is still abstract, and
  `integration/route_mapping.proposal.json` is still provisional. Use
  `city_osm.json` when real geography matters.
- ✅ Agents animate from a 60-frame snapshot sequence; each walks at their own
  survey-calibrated speed. Positions between frames are interpolated for display
  and edge colours are one fixed equilibrium - do NOT call it a time-evolving
  simulation.
- ✅ The Phase 9 agent renderer can join stable citizen IDs back to the simulator
  report and display six explicit behavior colors without changing the frozen
  canonical snapshot contract.
- ✅ The `frontend/` dashboard defaults to recorded fixtures shaped like the API
  contract. Mock "runs" replay a prior report and warn that they do not respond
  to the submitted scenario. With `URBANTWIN_API_BASE` set, the same routes proxy
  to `python -m api` (`mode: "live"`). Still no durable job queue or cross-process
  run persistence.
- ✅ Phase 12: `python -m api` accepts scenario POSTs, runs the Phase 11 pipeline
  on a single worker, and returns `source: "live"` summaries.
- ✅ Phase 16: optional `POST /api/runs/{id}/explain` summarizes a bounded
  simulator payload. Default is a deterministic template (no LLM key required);
  `URBANTWIN_LLM_URL` enables an optional paraphrase with fallback. Not medical
  advice; the threshold advisor remains authoritative for recommendations.
- ✅ Phase 14: `@nvidia/ov-web-rtc@6.7.0` DIRECT WebRTC when `GET
  /api/stream/config` is `available` (Kit signaling port probe). Mock mode
  (`URBANTWIN_API_BASE` unset) never streams.
- ✅ Phase 15, verified in Kit's own log (not just the UI): real browser clicks
  arrive over the data channel, and with the Kit-repo handler a command applies
  (`viewport camera -> /World/Cameras/Street`, `demoState -> Intervention`).
  Before/After switches the Phase 8 `demoState` variant: a stress-versus-proposal
  comparison, **not** a measured improvement.
- ⚠️ Streaming needs Kit (with the Kit-repo changes) + live API + a Chromium
  browser. Without them the viewport stays offline; never claim it in mock mode.
  While streaming the GPU sits around 60% (720p30, RTX Real-Time 2.0), so do not
  describe it as lightweight.
- ✅ Phase 18: Grafana dashboard `argus-observatory` (http://localhost:3300) over
  every completed run in `data/runs/`, kept in sync by `import_runs.py --watch`.
  Baseline vs intervention = before/after arms of one run. Failed/cancelled
  counts cover only runs logged since `data/run_events.jsonl` existed. Grafana
  visualises output; it validates nothing.
- ✅ `integration/export_snapshot.py` closes the loop: simulator report ->
  canonical v1 snapshot -> USD. 12/12 integration tests pass, agents land within
  1mm of their route geometry, snapshots are `data_kind: simulation`.

## Commands

```powershell
cd Simulation; python main.py                        # tests + 8-building demo
cd Simulation; python main.py citizens_osm.json city_osm.json   # real OSM city
python phase9\set_scenario.py baseline|heat|rain|dusk
python phase8\switch_state.py stressed|intervention
python phase9\validate_phase9.py
python phase3\validate_mock_data.py <snapshot.json>

# complete local regeneration (Phase 11 is the source of truth)
python integration\run_pipeline.py `
  --run-id phase11-smoke `
  --citizens Simulation\citizens_survey_city_osm.json `
  --city Simulation\city_osm.json `
  --temperature 40 `
  --humidity 80 `
  --rainfall 80 `
  --population 100000 `
  --frames 60 `
  --duration 60

# animated agents (60 frames of real walking, then press play in Kit)
python integration\export_snapshot.py --state before --frames 60 --duration 60
python phase9\agents_instancer.py data\simulation_before_*.json --behavior-report Simulation\urbantwin_demo_output.json

# web dashboard — mock fixtures (default)
python integration\export_api_mocks.py      # refresh fixtures after a new run
cd frontend; npm install; npm run dev

# Phase 12 local HTTP API + proxied frontend
python -m api --host 127.0.0.1 --port 8000
# second shell:
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend; npm run dev
# operator notes: docs/PHASE12_LOCAL_API.md

# Phase 18 Grafana run analytics (demo_launch.ps1 does this when Docker runs)
docker compose -f analytics\docker-compose.yml up -d
python analytics\import_runs.py --watch
$env:URBANTWIN_GRAFANA_URL = "http://localhost:3300"   # Analytics link in the header
python -m unittest analytics.test_import_runs

# Phase 14 browser WebRTC (branch phase13-streaming-kit; Chromium required)
# 1) Kit host: cd kit-app-template; .\launch_urbantwin_streaming.bat
# 2) API + frontend as above; verify: Invoke-RestMethod http://127.0.0.1:8000/api/stream/config
# full steps: docs/PHASE14_BROWSER_WEBRTC.md

# Phase 17 judge demo (branch phase13-streaming-kit; phases 11–17 on this branch)
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
.\tools\demo_launch.ps1          # API + Kit + frontend; logs in tools/demo_logs/
python tools\demo_smoke.py       # health, stream config, short run, view allow-list
# operator runbook: docs/DEMO_RUNBOOK.md
# LLM explain is optional (URBANTWIN_LLM_URL); relaunch Kit if view_commands miss Kit
```

Open `phase9/scene/main.usda` in Kit for the demo stage.
Kit app lives outside the repo: `C:\Users\arnav\omniverse\kit-app-template`,
launch desktop with `.\repo.bat launch -n urbantwin.kit`.
Streaming layer (branch `phase13-streaming-kit` in the kit-app-template):
`.\launch_urbantwin_streaming.bat` — see `docs/PHASE13_STREAMING_KIT.md`.
