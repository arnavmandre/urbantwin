# UrbanTwin AI — frontend/backend handoff

Use this document as the source context for a frontend coding agent. It separates
working code from the planned final product. Do not present planned endpoints or
streaming as already implemented.

## Product goal

UrbanTwin AI is a human-centric urban digital twin for comparing how weather,
population and design interventions affect pedestrians. The judge-facing loop is:

```text
choose scenario -> simulate -> inspect people and city -> receive suggestions
-> apply an intervention -> re-simulate -> compare before and after
```

The final web product should combine:

1. a live streamed NVIDIA Omniverse viewport;
2. scenario controls;
3. human-impact metrics and behavior counts;
4. problem zones/buildings/routes;
5. advisor explanations and supported interventions;
6. before/after comparison;
7. model-confidence and prototype disclaimers.

## What exists today

### Simulation engine

Source: `Simulation/main.py`. It is deterministic, dependency-free Python. It
accepts a city, citizens and a scenario, assigns routes iteratively, calculates
congestion and individual exposure, generates recommendations, applies supported
interventions, and runs the scenario again.

Current real-city command:

```powershell
cd C:\Users\arnav\Argus\Simulation
python main.py citizens_survey_city_osm.json city_osm.json
```

Machine-readable output:

```text
Simulation/urbantwin_demo_output.json
```

Accepted scenario ranges:

| Input | Range | Current demo |
|---|---:|---:|
| `temperature` | -10 to 45 °C | 40 |
| `humidity` | 20 to 90% | 80 |
| `rainfall` | 0 to 100 mm prototype scale | 80 |
| `population` | 25,000 to 100,000 equivalent | 100,000 |

These are synchronous prototype runs. Phase 12 wraps them in a local stdlib
HTTP API (`python -m api`; see `docs/PHASE12_LOCAL_API.md`). There is still no
FastAPI service, durable database, authentication, or multi-worker job queue.

### Current simulation output

Top-level report shape:

```ts
interface SimulationReport {
  scenario: ScenarioInput;
  before: SimulationState;
  advisor: AdvisorResult;
  intervention: InterventionParameters;
  after: SimulationState;
  delta: Record<string, number>;
  control: {
    scenario: ScenarioInput;
    metrics: SimulationMetrics;
    recommendations: string[];
  };
}
```

Current metrics:

```ts
interface SimulationMetrics {
  heat_stress: number;           // 0..100, higher is worse
  cold_stress: number;           // 0..100, higher is worse
  rain_impact: number;           // 0..100, higher is worse
  crowding: number;              // 0..100, higher is worse
  safety: number;                // 0..100, higher is better
  mobility: number;              // 0..100, higher is better
  comfort: number;               // city-level, 0..100, higher is better
  citizen_comfort: number;       // population-weighted, higher is better
  mean_travel_minutes: number;
  human_experience_index: number;// 0..100, higher is better
}
```

Current extreme-weather result:

| Metric | Before | After |
|---|---:|---:|
| Heat stress | 79.43 | 73.47 |
| Cold stress | 0.00 | 0.00 |
| Rain impact | 40.09 | 6.88 |
| Crowding | 36.27 | 36.29 |
| Safety | 52.61 | 75.39 |
| Mobility | 61.36 | 73.87 |
| City comfort | 45.80 | 55.96 |
| Citizen comfort | 66.26 | 75.97 |
| Mean travel time | 2.66 min | 2.67 min |
| Human Experience Index | 57.44 | 70.43 |

### Per-citizen output

The report contains all 1,000 simulated citizens. Omniverse renders at most 500
representative agents.

```ts
type CitizenBehavior =
  | "CONTINUE"
  | "STRESSED"
  | "SEEK_SHADE"
  | "SEEK_SHELTER"
  | "REROUTE"
  | "AVOID_AREA";

interface CitizenResult {
  id: string;
  archetype: string;
  home: string;
  destination: string;
  route: string;
  travel_minutes: number;
  heat_exposure: number;         // 0..100
  cold_exposure: number;         // 0..100
  rain_exposure: number;         // 0..100
  flood_risk: number;            // 0..100
  crowd_exposure: number;        // 0..100
  destination_crowding: number;  // 0..100
  comfort: number;               // 0..100, higher is better
  stress: number;                // 0..100, higher is worse
  behavior: CitizenBehavior;
  route_cost: number;            // relative heuristic cost
}
```

Current behavior counts across 1,000 citizens:

```json
{"CONTINUE": 527, "SEEK_SHADE": 400, "STRESSED": 73}
```

Other behaviors appear when their thresholds are reached. For example, the
validated -10 °C test produces `SEEK_SHELTER` and `AVOID_AREA`.

Behavior display colors in Omniverse:

| Behavior | Color |
|---|---|
| `CONTINUE` | green |
| `STRESSED` | orange |
| `SEEK_SHADE` | yellow |
| `SEEK_SHELTER` | cyan |
| `REROUTE` | purple |
| `AVOID_AREA` | red |

### Spatial results

Each `SimulationState` also contains:

```ts
interface SimulationState {
  inputs: ScenarioInput;
  metrics: SimulationMetrics;
  zones: ZoneResult[];
  buildings: BuildingResult[];
  routes: RouteResult[];
  citizens: CitizenResult[];
  problem_zones: string[];
  problem_buildings: ProblemBuilding[];
  problem_routes: ProblemRoute[];
  interventions: Record<string, number>;
}
```

The current OSM-backed simulation contains 9 zones, 75 simulation buildings,
254 routes and 1,000 citizens. The visual city contains 623 building meshes and
511 OSM-positioned trees. Route rows include congestion, capacity, utilization,
shade, greenery and stable OSM-edge mappings.

### Advisor

The working advisor is deterministic threshold logic. It is not currently an
LLM. The simulator remains the only authority for metrics and effectiveness.

```ts
interface AdvisorResult {
  summary: string;
  problem_zones: string[];
  problem_buildings: ProblemBuilding[];
  problem_routes: ProblemRoute[];
  recommendations: Array<
    | "increase_shade"
    | "improve_drainage"
    | "alternative_pedestrian_routes"
    | "no_major_intervention"
  >;
  affected_buildings: Record<string, string[]>;
  explanation: string[];
  supported_interventions: Record<string, {
    changes: Record<string, number>;
    effect: string;
  }>;
}
```

Implemented intervention parameters:

```ts
interface InterventionParameters {
  shade_boost?: number;
  drainage_boost?: number;
  route_capacity_boost?: number;
}
```

The LLM layer planned for the final product may explain structured simulator
results and trade-offs. It must not invent metrics, problem locations, supported
commands or effectiveness numbers.

### Survey and synthetic population

Working pipeline: `phase10/`.

```text
41 anonymous survey participants
-> 164 scenario-response rows
-> six fitted behavioral parameters per participant
-> Gaussian-copula population generator
-> 1,000 statistically related synthetic citizens
-> heuristic home/destination placement
-> simulator
```

Citizen input traits are heat, rain and crowd tolerance, walking speed, green
preference and transit preference. The survey sample is young: about 73% are
under 25. Home and destination do not come from the survey.

The generator has a genuine training-only holdout check: a fresh generator is
fitted on 36 participants and checked against five unseen people. This supports
distributional consistency, not prediction of an individual's behavior.

### Random Forest models

Training pipeline: `phase10/train_random_forest.py`.
Model card: `phase10/models/model_card.json`.
Readable report: `phase10/models/MODEL_REPORT.md`.

| Target | Final real holdout | Verdict |
|---|---:|---|
| Comfort | MAE 0.82; R2 0.35 | promising |
| Stress | MAE 0.71; R2 0.14 | supported for prototype |
| Walking likelihood | MAE 0.70; R2 0.56 | supported for prototype |
| Avoidance likelihood | MAE 1.28; R2 -0.08 | not validated |
| Route choice | macro F1 0.22 | not validated |

The models are not connected to the simulator yet. The simulator still uses
transparent rules. A frontend may show these validation results, but must not
say the entire behavior model is accurate.

### Omniverse/OpenUSD

Demo stage:

```text
C:\Users\arnav\Argus\phase9\scene\main.usda
```

Kit app source lives outside this repository:

```text
C:\Users\arnav\omniverse\kit-app-template
```

Desktop launch:

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
.\repo.bat launch -n urbantwin.kit
```

Generate the current behavior-colored animation:

```powershell
cd C:\Users\arnav\Argus
python integration\export_snapshot.py --state before --frames 60 --duration 60
python phase9\agents_instancer.py data\simulation_before_*.json `
  --behavior-report Simulation\urbantwin_demo_output.json `
  --behavior-state before
```

The browser cannot render this stage with normal React/Three.js and preserve the
actual RTX/Kit application. The intended web path is NVIDIA Kit App Streaming:

```text
Next.js browser client <-- WebRTC --> streaming-enabled UrbanTwin Kit app
```

The GPU host performs RTX rendering. The browser receives video/audio frames and
sends input. NVIDIA references:

- https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html
- https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/108.0/docs/streaming.html
- https://docs.omniverse.nvidia.com/embedded-web-viewer/latest/workflow/streaming-and-messaging.html

On branch **`phase13-streaming-kit`**, local **DIRECT WebRTC** exists when the
streaming Kit host is up and the dashboard proxies a live API that probes
signaling (`docs/PHASE14_BROWSER_WEBRTC.md`). On `main` or in mock mode, streaming
is still offline. On `phase13-streaming-kit`, allow-listed view commands are
validated by the API then sent with `AppStreamer.sendMessage` when WebRTC is
connected (`docs/PHASE15_KIT_COMMAND_DELIVERY.md`).

### Canonical visualization boundary

`integration/export_snapshot.py` converts the full simulator report into frozen
canonical v1 visualization snapshots. `integration/load_snapshot.py` applies a
validated snapshot to the integration USD stage. The canonical contract is
documented in `docs/INTEGRATION_CONTRACT.md` and validated against
`phase3/simulation_state.schema.json`.

Canonical metrics use 0..1, while simulator metrics use 0..100. A canonical
snapshot contains at most 500 agents with local metre XYZ positions and stable
OSM edge IDs. Behavior colors are joined by stable citizen ID in the Phase 9
renderer rather than changing the frozen v1 contract.

All 12 current end-to-end checks pass. Agent positions are within 1 mm of their
routes, route chains join within 0.54 m in the worst case, and sampled animation
transitions contain no backward movement.

### Web frontend

Source: `frontend/`. Next.js App Router, TypeScript, Tailwind. It implements the
dashboard described below. **Default = recorded fixtures** in `frontend/mocks/`,
exported from the real simulator report by `integration/export_api_mocks.py`.

With `URBANTWIN_API_BASE` unset, `/api/health` reports `mode: "mock"` with every
capability false, and the UI is driven by that rather than by build flags, so a
recorded run cannot be presented as a live backend. Setting `URBANTWIN_API_BASE`
(for example `http://127.0.0.1:8000` after `python -m api`) makes the same route
handlers forward to the Phase 12 Python service instead; there is no fallback
from live to mock. Operator steps: `docs/PHASE12_LOCAL_API.md`.

The Omniverse viewport is isolated behind `frontend/lib/viewer/`. Mock mode uses
the placeholder adapter (no picture). On `phase13-streaming-kit` with live API +
Kit up, `kit-webrtc-adapter.ts` (`@nvidia/ov-web-rtc@6.7.0`) connects when
`/api/stream/config` reports `available`.

### Local HTTP API (Phase 12)

Working code: `api/` — stdlib `python -m api` (not FastAPI). It accepts scenario
POSTs, runs the Phase 11 pipeline in a **single in-memory worker**, and returns
live `RunSummary` envelopes with `source: "live"`. Runs are asynchronous
(`202` + poll). State does not survive process restart.

Still out of scope for Phase 12 alone: FastAPI, durable DB, auth, multi-worker
queue, and LLM advisor. Local Kit WebRTC on branch `phase13-streaming-kit` is
documented in `docs/PHASE14_BROWSER_WEBRTC.md`. See `docs/PHASE12_LOCAL_API.md`.

## What has not been built

Do not assume any of the following exists:

- FastAPI or production-hardened HTTP backend;
- durable run persistence or multi-worker job queue;
- database or authentication;
- production web streaming session manager (local DIRECT WebRTC exists on
  `phase13-streaming-kit` when Kit + API are up);
- browser-to-Kit messaging on `main` (Phase 15 lives on `phase13-streaming-kit`);
- LLM advisor integration;
- Random Forest inference inside the simulator;
- uncertainty intervals in simulation output;
- accessibility/emergency-access model;
- vehicle, cyclist or scheduled-transit simulation;
- physical CFD, UTCI/WBGT or hydraulic flood model.

## Planned final architecture

```text
┌──────────────────────── Next.js ──────────────────────────┐
│ Omniverse stream | scenario form | metrics | comparison   │
│ behavior chart   | problem places | advisor | model trust │
└──────────┬──────────────────────┬─────────────────────────┘
           │ HTTPS / SSE          │ WebRTC + message channel
           ▼                      ▼
┌──────────────────────┐   ┌───────────────────────────────┐
│ Python API/orchestrator│   │ UrbanTwin streaming Kit app │
│ validates scenarios   │   │ opens phase9 main.usda      │
│ runs simulation       │   │ renders RTX viewport        │
│ exports snapshots     │   │ receives view/state commands│
│ returns summaries     │   └───────────────────────────────┘
└──────────┬───────────┘
           ▼
 simulator report + canonical snapshots + generated USD layers
```

For a local hackathon demo, all processes may run on the same Windows RTX
machine. Production deployment would need an RTX GPU worker per active stream,
session orchestration, TURN/network configuration, access control and durable
run storage.

## HTTP API contract (Phase 12 local + remaining gaps)

The frontend depends on a small stable API rather than importing large
simulation JSON files directly. Phase 12 implements these shapes in stdlib
Python (`python -m api`). Next still defaults to fixtures until
`URBANTWIN_API_BASE` points at that process. Full operator notes:
`docs/PHASE12_LOCAL_API.md`.

What Phase 12 does **not** add: FastAPI, durable DB, auth, streaming Kit, or
LLM. Endpoint contract:

### `GET /api/health`

```json
{
  "status": "ready",
  "simulator": true,
  "omniverse_stream": "offline",
  "model_card": true
}
```

### `GET /api/scenarios`

Returns presets and input constraints.

```json
{
  "constraints": {
    "temperature": [-10, 45],
    "humidity": [20, 90],
    "rainfall": [0, 100],
    "population": [25000, 100000]
  },
  "presets": [
    {"id":"baseline","temperature":26,"humidity":40,"rainfall":5,"population":30000},
    {"id":"extreme_heat_rain","temperature":40,"humidity":80,"rainfall":80,"population":100000}
  ]
}
```

### `POST /api/runs`

```json
{
  "temperature": 40,
  "humidity": 80,
  "rainfall": 80,
  "population": 100000,
  "apply_recommended_interventions": true,
  "animation_frames": 60,
  "animation_duration_seconds": 60
}
```

Phase 12 accepts the POST with `202` and an in-memory queue entry:

```json
{"run_id":"run_20260919_001","status":"queued"}
```

Poll `GET /api/runs/:runId` until `complete`, `failed`, or `cancelled`. The UI
must handle all five statuses. Only complete runs (or failed runs that actually
produced a simulator report) carry the full “just-executed simulator run”
warning list; queued / running / cancelled / failed-without-report summaries use
shorter status notes.

### `GET /api/runs/:runId`

Return a frontend-sized summary, not all 1,000 citizen records by default:

```ts
interface RunSummary {
  run_id: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled";
  scenario: ScenarioInput;
  before?: {
    metrics: SimulationMetrics;
    behavior_counts: Record<CitizenBehavior, number>;
    problem_zones: string[];
    problem_buildings: ProblemBuilding[];
    problem_routes: ProblemRoute[];
  };
  advisor?: AdvisorResult;
  intervention?: InterventionParameters;
  after?: RunSummary["before"];
  delta?: Record<string, number>;
  artifacts?: {
    omniverse_stage: string;
    snapshot_pattern: string;
  };
  warnings: string[];
}
```

### `GET /api/runs/:runId/citizens?state=before&limit=100&offset=0`

Optional paginated citizen inspection. Do not load all citizens into the initial
page bundle.

### `GET /api/model-card`

Expose a sanitized subset of `phase10/models/model_card.json`, including target
verdicts, holdout scores and limitations.

### `GET /api/stream/config`

Return only public WebRTC connection settings or a short-lived session token.
Never expose infrastructure credentials through `NEXT_PUBLIC_*` variables.

### `POST /api/runs/:runId/view`

Optional high-level view command forwarded to Kit messaging:

```json
{"state":"before","camera":"ProblemZone","overlay":"behavior"}
```

The server must allow-list commands and values. Do not forward arbitrary prim
paths, file paths or Python expressions from the browser.

## Frontend implementation brief

Recommended stack: Next.js App Router, TypeScript, Tailwind CSS and a small chart
library. Keep the Omniverse stream in a client-only component because WebRTC and
browser media APIs are unavailable during server rendering.

Suggested structure:

```text
frontend/
  app/
    page.tsx
    runs/[runId]/page.tsx
  components/
    OmniverseViewer.tsx
    ScenarioControls.tsx
    MetricGrid.tsx
    BeforeAfterChart.tsx
    BehaviorLegend.tsx
    ProblemAreas.tsx
    AdvisorChat.tsx
    ModelTrustPanel.tsx
    RunStatus.tsx
  lib/
    api.ts
    types.ts
    metric-format.ts
  public/
```

Primary screen layout:

```text
header: UrbanTwin AI — Simulate the human experience before building the city
left 2/3: streamed Omniverse viewport
right 1/3: scenario controls, run status and headline metrics
below: before/after charts, behavior distribution, problem locations,
       advisor recommendations and model-trust disclosure
```

Required UI behavior:

- show explicit loading, stream-offline, simulation-failed and validation-failed states;
- disable Run while a local single-worker run is active;
- label population as `population equivalent`, distinct from visible agents;
- use `higher is worse` for heat/rain/crowding/stress and `higher is better`
  for safety/mobility/comfort/HEI;
- show before and after with the same scale;
- display behavior colors exactly as defined above;
- show the deterministic advisor's source label;
- show model verdicts per target rather than one misleading accuracy percentage;
- keep prototype limitations visible but compact;
- default to recorded fixtures; use `URBANTWIN_API_BASE` only when `python -m api`
  is running (see `docs/PHASE12_LOCAL_API.md`);
- do not import or parse the multi-megabyte full report in a React component.

## Product language and integrity

Use:

- “survey-calibrated synthetic citizens”;
- “population equivalent”;
- “prototype estimate”;
- “decision-support suggestion”;
- “simulated behavior”;
- “real OSM geometry with inferred/assumed attributes where recorded.”

Do not use:

- “predicts exactly what people will do”;
- “scientifically proven comfort index”;
- “real-time crowd simulation”;
- “all 100,000 citizens are rendered”;
- “AI advisor” without identifying the current deterministic advisor;
- “validated Random Forest” for avoidance or route choice;
- “flood simulation” — the current value is a rainfall/flood-risk proxy.

The visualization animation interpolates positions between 60 fixed snapshots.
It is not a time-evolving behavioral or collision simulation. Environmental and
intervention formulas are heuristic prototypes, not medical, meteorological,
hydraulic or engineering models.

## Frontend agent acceptance criteria

The frontend milestone is complete when:

1. TypeScript types cover `RunSummary`, metrics, behaviors and advisor output.
2. The main page works against committed mock responses without the Python API.
3. Scenario inputs enforce backend ranges and explain population equivalent.
4. Metrics correctly express direction and before/after changes.
5. The behavior legend uses the six fixed colors.
6. Problem areas and advisor recommendations render from structured data.
7. The model panel shows per-target verdicts and limitations.
8. `OmniverseViewer` has clear connecting, connected, offline and failed states.
9. WebRTC implementation is isolated behind a component/adapter so the NVIDIA
   client can replace the mock viewport without rewriting the dashboard.
10. No backend, streaming or model capability is presented as live unless its
    health/config endpoint confirms it.

## Immediate build sequence

1. ~~Scaffold Next.js and implement typed mock dashboard.~~ Done: `frontend/`.
2. ~~Build the one-command local simulation/orchestration workflow.~~ Done: Phase 11
   (`integration/run_pipeline.py`, `docs/PHASE11_LOCAL_PIPELINE.md`).
3. ~~Implement the small Python HTTP API around that workflow.~~ Done: Phase 12
   stdlib `python -m api` (`docs/PHASE12_LOCAL_API.md`). Next defaults to fixtures;
   set `URBANTWIN_API_BASE` for live. Still no FastAPI, durable DB, auth, or LLM.
4. ~~Streaming Kit + local browser WebRTC on branch `phase13-streaming-kit`.~~
   See `docs/PHASE13_STREAMING_KIT.md` and `docs/PHASE14_BROWSER_WEBRTC.md`.
5. ~~Allow-listed browser-to-Kit messages for state, camera and overlay.~~ Done on
   `phase13-streaming-kit`: `docs/PHASE15_KIT_COMMAND_DELIVERY.md`.
6. Add the LLM explanation layer only after the deterministic data path is stable.

