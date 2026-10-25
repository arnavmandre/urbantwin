# UrbanTwin AI

Human-centric urban digital twin: a **Python pedestrian simulator**, an **OpenUSD / Omniverse** city stage, and a **web dashboard** that can run live scenarios and (optionally) stream the RTX viewport in the browser.

Product name in the UI: **Argus AI**. Internal package/path names may still say `urbantwin` (Kit apps, env vars such as `URBANTWIN_API_BASE`).

Metrics, comfort indices, and advisor text are **heuristic prototypes** — not medical, meteorological, or engineering models. Citizen behavioural parameters are **survey-calibrated** (41 participants); scenario factors are confounded; home/destination placement is a heuristic.

---

Pune is the sole active demo: 1 km × 1 km simulation, 400 m × 400 m view, 2,069 buildings (272 in view), 329 OSM trees (115 in view), and 600 agents by default. The current calibration uses 41 survey participants, not surveyed Pune residents. The new 63-response experiment failed joint holdout checks and the coverage gate; it has not replaced the demo population. Frozen Phase 1–8 assets and the Phase 9 stage are archival, not the active city.

## What this repo contains

| Area | Path | What it does |
| --- | --- | --- |
| Simulator | `Simulation/` | Deterministic city + citizen model; route choice; heat/rain/crowd stress; threshold advisor; before/after interventions. Run `python main.py` for asserts + demo. |
| Local HTTP API | `api/` | `python -m api` — scenario POST, single-worker Phase 11 pipeline, health/stream probe, view allow-list, optional RAG advise. |
| Dashboard | `frontend/` | Next.js UI. Default = recorded fixtures (`mode: "mock"`). With `URBANTWIN_API_BASE` → live API (`mode: "live"`). |
| Integration | `integration/` | Snapshot export, route mapping proposals, pipeline orchestration, API mock export, validation gate. |
| Archival city / USD | `phase1/`–`phase9/` | OSM → semantics → bridges → packaged states → materials, trees, cameras, agents. **`phase1`–`phase8` scene layers are frozen**; add `over` layers in `phase9/`. |
| Active Pune | `cities/pune/` | Simulator bridge and 400 m streamed view; see `docs/PUNE_CITY.md`. |
| Survey | `phase10/` | Survey → calibrated synthetic citizens. |
| Docs | `docs/` | Contracts, phase notes, demo runbook, RAG notes. |

### End-to-end product loop

1. Operator sets temperature / humidity / rainfall / population in the dashboard.
2. API runs `Simulation/main.py` on OSM city data (and optional interventions).
3. Pune pipeline animates both simulator arms directly from route polylines for the Kit stage.
4. Dashboard shows metrics, problem areas, and advisor recommendations.
5. Optional: Kit App Streaming (WebRTC) shows the live RTX view; camera / overlay / playback commands are allow-listed then sent over the data channel.
6. Optional: RAG layer ranks grounded intervention suggestions; the **threshold advisor in the simulator** remains the execution authority.

---

## Quick start (manual — recommended)

**Prerequisites (once):** Python on PATH, Node.js (`cd frontend; npm ci`), RTX GPU + Kit App Template with `launch_urbantwin_streaming.bat` for streaming, **Chrome or Edge** for WebRTC.

Open **three** terminals.

Prepare and launch Pune from this worktree with `tools\demo_launch.ps1 -City pune`. For manual launch, set `URBANTWIN_STREAM_CITY=pune` for the API and `URBANTWIN_STAGE` to the absolute `cities/pune/main_view_400m.usda` path for Kit. API run requests may explicitly send `city: "pune"` (the current default).

### 1) API

```powershell
cd C:\Users\arnav\Argus\.worktrees\pune-city
$env:URBANTWIN_STREAM_CITY = "pune"
python -m api --host 127.0.0.1 --port 8000
```

### 2) Omniverse Kit stream (headless — no editor window)

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
$env:URBANTWIN_STAGE = "C:/Users/arnav/Argus/.worktrees/pune-city/cities/pune/main_view_400m.usda"
.\launch_urbantwin_streaming.bat
```

Leave this console open. Wait until you see `app ready` / `RTX ready` and **no** `Failed to start the primary stream server`.

### 3) Dashboard

```powershell
cd C:\Users\arnav\Argus\.worktrees\pune-city\frontend
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
npm run dev -- -p 3001   # 3001: Kit's Python debugger takes 127.0.0.1:3000
```

### 4) Open UrbanTwin AI

In Chrome or Edge:

```text
http://127.0.0.1:3001/
```

(Port 3001, not 3000: when Kit runs, its Python debugger binds 127.0.0.1:3000 and would answer instead of the dashboard.)

Expect **Live backend** in the header. The Omniverse viewport should reach **Live** when Kit signaling is up (often 30–90s).

### Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
# expect mode: "live"
Invoke-RestMethod http://127.0.0.1:8000/api/stream/config
# expect status: "available" when Kit is up, else honest "offline"
```

### Stop

Close the three service windows (API, Kit, frontend).

Full operator notes: [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md).

---

## Optional: one-click launcher

`Start-UrbanTwin.bat` / `tools/demo_launch.ps1` exist but are **not** the preferred path (Kit port conflicts are common). Prefer the manual steps above and open **http://127.0.0.1:3001/**.

### Mock-only dashboard (no API / no Kit)

```powershell
cd C:\Users\arnav\Argus\.worktrees\pune-city\frontend
npm run dev -- -p 3001   # 3001: Kit's Python debugger takes 127.0.0.1:3000
```

Without `URBANTWIN_API_BASE`, the UI replays fixtures and must not be presented as a live backend.

---

## Using the dashboard

| Control | Behaviour |
| --- | --- |
| Scenario sliders | Accepted ranges (e.g. temperature **-10…45 °C**). Values outside the range are refused before a run starts. |
| Run simulation | Queues one Pune pipeline job (single worker). Limited animation frames are used for faster demos. |
| Before / After | Compares the Pune simulator's baseline and intervention arms using the same citizens; not measured real-world improvement. |
| Overlay | **Behavior** (agents + routes), **Routes only**, **Shade canopy** (archival Phase 8 proposal), **City only**. |
| Animation | Play / Pause / Restart on the Kit timeline (needs Live stream). |
| Advisor | Threshold recommendations from the simulator; optional RAG ranking if configured. |

Scenario sliders do **not** live-update the USD stage — they apply on the next **Run**.

---

## What we built (phases)

| Phase | Deliverable |
| --- | --- |
| 1–8 | OSM city → USD semantics, contract, bridges, stressed vs intervention packaged states (frozen layers). |
| 9 | Materials, heights, trees, lighting, cameras, agent instancing (archival stage). |
| 10 | Survey-calibrated synthetic citizens. |
| 11 | Local orchestration: sim → snapshots → USD (`integration/run_pipeline.py`). |
| 12 | Local stdlib HTTP API (`python -m api`). |
| 13 | Headless streaming Kit app + stage autoload. |
| 14 | Browser WebRTC client (`@nvidia/ov-web-rtc`) + stream TCP probe. |
| 15 | Allow-listed view commands → WebRTC → Kit `urbantwin.view_commands` (camera, overlay, before/after, playback). |
| 16 | Constrained explain endpoint (deterministic by default). |
| 17 | Runbook (`docs/DEMO_RUNBOOK.md`) + optional launcher (`Start-UrbanTwin.bat`, `tools/demo_launch.ps1`). |
| RAG | Optional grounded advisor over completed runs (`docs/RAG_URBAN_ADVISOR.md`). |

### Simulator advisor (no LLM required)

After the **before** arm, `urban_advisor()` in `Simulation/main.py` applies fixed thresholds:

- heat stress ≥ 60 → `increase_shade`
- rain impact ≥ 30 → `improve_drainage`
- crowding ≥ 55 → `alternative_pedestrian_routes`
- else → `no_major_intervention`

In the archival snapshot pipeline, those IDs map to `shade_boost` / `drainage_boost` / `route_capacity_boost` for the **after** re-sim. Shade is exported as an `ADD_SHADE` proposal in the run's snapshot and its pipeline USD (`integration/runtime/scene/`); drainage is metrics-only today (no separate USD type). The archival Phase 8 cyan canopy is not Pune per-run geometry; Pune compares simulator arms through `cities/pune/run_pune.py`.

---

## How we verified it

Run these from the repo root. Prefer claiming only what still passes on your machine.

### Simulator unit / demo asserts

```powershell
cd Simulation
python main.py
```

Self-contained deterministic tests plus a short demo write to `urbantwin_demo_output.json`.

### Local API contract

```powershell
python -m unittest discover -s api -p "test_*.py"
```

Covers validation (scenario ranges, view allow-list including playback), run manager behaviour, shapes, optional RAG tests when deps are present.

### Archival integration gate (sim → snapshot → USD)

```powershell
python integration\validate_integration.py
```

Traces simulator values into snapshots and authored stage geometry (agent placement, edge ids, heat normalisation, intervention proposals). Metrics-only interventions such as `drainage_boost` are allowed without a drawn USD proposal.

### Pipeline / export interfaces

```powershell
python -m unittest integration.test_export_interfaces integration.test_run_pipeline
```

### Frontend typecheck

```powershell
cd frontend
npx tsc --noEmit
```

### Demo smoke (API must be up)

```powershell
python tools\demo_smoke.py
```

Health, stream config, short live run, view allow-list, optional explain.

### Manual streaming check

1. Start API, Kit and frontend with the manual steps above (`Start-UrbanTwin.bat` is optional).
2. Header: **Live backend**; `/api/stream/config` → `available` when Kit is up.
3. Viewport chip: **Live** (not only “stream online” in the header).
4. Change Camera / Overlay / Play–Pause; Kit should respond when WebRTC is connected.
5. Extreme heat scenario → Run → metrics update; Before/After compares the Pune simulator arms. Do not present the archival Phase 8 shade canopy as Pune per-run geometry.

---

## Integrity notes (do not over-claim)

- Building heights: only 40 of 2,069 come from real OSM (`urbantwin:heightSource`); the rest are inferred from class or neighbours — do not call the skyline surveyed.
- Default small `city.json` is abstract; use `cities/pune/city_pune.json` for the active demo.
- Agent motion between frames is interpolated for display; edge colours are equilibrium — not a continuously evolving physics sim.
- Omniverse stream stays offline until Kit signaling is actually listening; mocks must not be presented as live.
- `integration/route_mapping.json` is reserved for a **team-agreed** mapping; tools emit `route_mapping.proposal.json` only.
- Never edit `phase1/`–`phase8/` scene layers; extend with `over` layers in `phase9/`.

---

## Documentation map

| Doc | Topic |
| --- | --- |
| [`docs/PIPELINE_MERMAID.md`](docs/PIPELINE_MERMAID.md) | End-to-end pipeline Mermaid + slide wording |
| [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) | Judge / local demo launch and recovery |
| [`docs/PHASE12_LOCAL_API.md`](docs/PHASE12_LOCAL_API.md) | HTTP API |
| [`docs/PHASE13_STREAMING_KIT.md`](docs/PHASE13_STREAMING_KIT.md) | Streaming Kit host |
| [`docs/PHASE14_BROWSER_WEBRTC.md`](docs/PHASE14_BROWSER_WEBRTC.md) | Browser WebRTC |
| [`docs/PHASE15_KIT_COMMAND_DELIVERY.md`](docs/PHASE15_KIT_COMMAND_DELIVERY.md) | View commands |
| [`docs/PHASE16_CONSTRAINED_LLM.md`](docs/PHASE16_CONSTRAINED_LLM.md) | Explain |
| [`docs/RAG_URBAN_ADVISOR.md`](docs/RAG_URBAN_ADVISOR.md) | Optional RAG advisor |
| [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md) | Snapshot / integration contract |
| [`docs/FRONTEND_BACKEND_HANDOFF.md`](docs/FRONTEND_BACKEND_HANDOFF.md) | Frontend ↔ API product contract |
| [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md) | Project context |
| [`frontend/README.md`](frontend/README.md) | Dashboard specifics |
| [`phase9/README.md`](phase9/README.md) | Demo stage notes |

---

## Kit / Omniverse (without the web stream)

Open the Pune composed stage in the UrbanTwin Kit app:

```text
C:\Users\arnav\Argus\.worktrees\pune-city\cities\pune\main_view_400m.usda
```

Kit app (outside this repo): `C:\Users\arnav\omniverse\kit-app-template`  
Launch desktop editor: `.\repo.bat launch -n urbantwin.kit`  
Launch streaming host: `.\launch_urbantwin_streaming.bat`

Use the dashboard Before/After control for Pune; keep frozen Phase 1–8 assets unchanged.
