# Argus AI — web frontend

Next.js App Router + TypeScript + Tailwind dashboard for the Argus AI
simulator, built against the API in `docs/FRONTEND_BACKEND_HANDOFF.md`.

**Default = recorded fixtures.** With `URBANTWIN_API_BASE` unset, every `/api/*`
handler serves `mocks/` and labels `mode: "mock"`. A "run" replays a prior
report and warns that no simulator process ran for the submitted scenario.

**Optional live backend (Phase 12).** Start `python -m api` and set
`URBANTWIN_API_BASE` so the same handlers proxy to the Python service
(`mode: "live"`, `source: "live"`). Omniverse streaming is still offline. See
`docs/PHASE12_LOCAL_API.md`.

```powershell
cd C:\Users\arnav\Argus\frontend
npm install
npm run dev            # http://localhost:3000  (mock mode; use -- -p 3001 while Kit runs: its debugger takes 3000)

# live mode (second shell: python -m api --host 127.0.0.1 --port 8000)
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
npm run dev
```

## Where the data comes from

```text
Simulation/main.py
  -> Simulation/urbantwin_demo_output.json      real simulator report
  -> integration/export_api_mocks.py            THIS repo's exporter
  -> frontend/mocks/*.json                      recorded API responses
  -> frontend/app/api/*                         route handlers
  -> the dashboard
```

Regenerate the complete validated local run and recorded fixtures from the
repository root:

```powershell
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
```

This is synchronous local orchestration, not an HTTP service, job queue, or
live stream. The displayed agent motion interpolates fixed equilibrium
snapshots. See `docs/PHASE11_LOCAL_PIPELINE.md` for artifacts and recovery.

For fixture-only maintenance after an existing simulator report changes, run
`python integration\export_api_mocks.py`.

The fixtures carry the real numbers from that run — metrics, advisor text,
problem buildings, behaviour counts. Only the API envelope (run ids, status,
pagination, warnings) is added by the exporter.

## Mock mode vs live mode

| | `URBANTWIN_API_BASE` unset | `URBANTWIN_API_BASE=http://127.0.0.1:8000` |
|---|---|---|
| `/api/*` | serves `mocks/` | forwards to `python -m api` |
| `/api/health` | `mode: "mock"`, live-sim capabilities `false` | `mode: "live"`, `source: "live"` |
| Backend down | n/a | `502 upstream_unavailable`, the page says so |

There is deliberately **no** fallback from live to mock. If a configured backend
is unreachable the dashboard shows an error rather than quietly displaying
recorded numbers as if they were live output.

Every claim in the UI is driven by `/api/health` and `/api/stream/config`, not by
build flags. In mock mode a recorded run is labelled *Recorded data* in the
header, *Recorded fixture* in the run card, and the first warning on every
replayed run states that no simulator process ran. In live mode the header
follows the proxied health payload (`mode: "live"`); streaming stays offline
until a Kit signaling URL exists.

## Swapping in the real Omniverse stream

The viewport contains no transport code. `lib/viewer/` owns it:

| File | Role |
|---|---|
| `adapter.ts` | The `ViewerAdapter` interface and `ViewerState`. |
| `mock-adapter.ts` | Reports offline from `/api/stream/config`. Renders no picture. |
| `kit-webrtc-adapter.ts` | The NVIDIA Kit App Streaming path, with the connect call marked. |
| `index.ts` | Picks the adapter from what the server reports. |

`components/OmniverseViewer.tsx` renders whatever state the adapter reports and
is mounted client-only (`ssr: false`), because WebRTC and media APIs do not exist
during server rendering. To go live: build `urbantwin.streaming.kit`, return a
signaling URL, ICE servers and a short-lived token from `/api/stream/config`
server-side, then finish `kit-webrtc-adapter.ts`. No dashboard component changes.

View commands (`state`, `camera`, `overlay`) are checked against a fixed
allow-list in `app/api/runs/[runId]/view/route.ts`. Prim paths, file paths and
arbitrary strings are rejected before anything could reach Kit.

## Layout

```text
app/
  page.tsx                     server-rendered dashboard
  runs/[runId]/page.tsx        permalink for one run
  api/                         mock-serving / proxying route handlers
components/                    OmniverseViewer, ScenarioControls, MetricGrid,
                               BeforeAfterChart, BehaviorLegend, ProblemAreas,
                               AdvisorChat, ModelTrustPanel, RunStatus, ...
lib/
  types.ts                     the API contract in TypeScript
  api.ts                       browser client
  metric-format.ts             metric direction, formatting, delta polarity
  behaviors.ts                 the six fixed behaviour colours
  viewer/                      the Omniverse transport boundary
  server/                      fixtures, run store, bootstrap (server only)
mocks/                         recorded API responses
```

## Conventions worth keeping

- Metric direction lives in `lib/metric-format.ts`. Never decide "higher is
  better" inside a component; a raw delta sign is meaningless on its own.
- Behaviour colours are derived from the linear RGB triples in
  `phase9/agents_instancer.py`, so the legend cannot drift from the viewport.
- The large payloads stay on the server. The citizen fixture is ~220 KB and is
  sliced by `app/api/runs/[runId]/citizens`; it is never imported by a component.
- Population is always labelled *population equivalent* and kept distinct from
  the ≤ 500 rendered agents.
