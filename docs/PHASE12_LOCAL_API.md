# Phase 12 local HTTP API

Phase 12 wraps the **Phase 11 local pipeline** in a stdlib Python HTTP server so
the Next.js dashboard can proxy live runs. The simulator (`Simulation/main.py`)
remains the only authority for metrics and intervention effectiveness. This is
not a production service: no auth, no persistence across process restarts, no
job queue beyond a single in-memory worker.

## Prerequisites

- Run PowerShell from the repository root (the worktree root if you use one).
- Python that can import OpenUSD's `pxr` (same as Phase 11).
- Frontend deps when exercising the proxy: `cd frontend; npm ci`.

## Start the API

```powershell
python -m api --host 127.0.0.1 --port 8000
```

Banner: `UrbanTwin API listening on http://127.0.0.1:8000`.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
# expect mode: "live", source: "live", capabilities.http_api: true
```

## Point the frontend at it

```powershell
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend
npm run lint
npm run build
npm run dev   # or: npx next start -H 127.0.0.1 -p 3000
```

With `URBANTWIN_API_BASE` set, Next route handlers under `frontend/app/api/*`
forward to the Python service. There is **no** mock fallback: if the backend is
down, `/api/*` returns `502 upstream_unavailable`.

Unset the variable to serve recorded fixtures again (`mode: "mock"`).

Verify the proxy (with both processes up):

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
# expect mode: "live" (not "mock")
```

## POST a short live run

```powershell
$body = @{
  temperature = 38
  humidity = 70
  rainfall = 40
  population = 75000
  apply_recommended_interventions = $true
  animation_frames = 1
  animation_duration_seconds = 1
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/runs `
  -ContentType 'application/json' -Body $body
# 202 { run_id, status: "queued" }
# Optional: city = "pune" runs cities/pune/run_pune.py instead (default "london").
# Prepare Pune once first; see docs/PUNE_CITY.md.

do {
  Start-Sleep -Seconds 3
  $run = Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$($created.run_id)"
  $run.status
} while ($run.status -in @('queued', 'running'))

# complete run: source: "live", before/after.metrics populated
```

Optional fields `animation_frames` / `animation_duration_seconds` default to 60.
Use small values for smoke tests.

### Scenario that yields interventions

Phase 11 validation requires the advisor to produce at least one targeted
snapshot intervention. Mild weather (for example temperature **31 °C** with low
rain/crowd stress) can complete the simulator but **fail** the pipeline with
empty interventions. Prefer a heat-stress scenario (roughly temperature ≥ 35 °C
with non-trivial humidity/population) for live smoke, or accept `status:
"failed"` with a validation message.

## Single-worker semantics

Only **one** run may occupy the engine at a time (queued, running, or draining
after cancel). A second `POST /api/runs` while busy returns **409**
`conflict`. `GET /api/runs` reports `active_run_id` for the occupying run
(including cancel drain).

## Cancel

```powershell
Invoke-RestMethod -Method Delete -Uri "http://127.0.0.1:8000/api/runs/<run_id>"
# 200 live RunSummary with status: "cancelled"
```

Cancel flips status immediately for clients. The single-worker slot stays busy
until the worker thread finishes and any child Phase 11 process is terminated.
Already-terminal runs (`complete` / `failed` / `cancelled`) return **409**.

## Validation errors

Out-of-range or missing fields → **422** with
`error.code: "validation_failed"` and per-field messages. Ranges match
`docs/FRONTEND_BACKEND_HANDOFF.md` / `api/validation.py`.

## Streaming is still offline

`GET /api/stream/config` reports streaming offline. Omniverse / Kit WebRTC is
Phase 15 territory. The dashboard viewport may still show a recorded-stage
placeholder; that is not a live stream.

## Phase 11 is the engine

Each accepted run invokes `integration/run_pipeline.py` (subprocess) with the
request scenario, default citizens
`Simulation/citizens_survey_city_osm.json`, and city `Simulation/city_osm.json`.
Artifacts land under `data/runs/<run_id>/`. Successful publishes may refresh
`frontend/mocks/` and demo USD paths — restore those tracked files after local
smoke if you do not intend to refresh fixtures.

## Integrity: `source: "live"` vs fixtures

| Path | `source` / `mode` | Meaning |
|---|---|---|
| Mock frontend (`URBANTWIN_API_BASE` unset) | `mock` | Recorded fixtures; a "run" replays a prior report and warns that no simulator process ran for the submitted scenario. |
| Phase 12 API / proxied frontend | `live` | Numbers came from a just-executed Phase 11 → `Simulation/main.py` run for that request. |

Live summaries still carry heuristic and calibration disclaimers. Do not claim
medical/meteorological accuracy, time-evolving physics, or Omniverse streaming.

## Endpoints (summary)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `mode: "live"` |
| GET | `/api/scenarios` | constraints + presets |
| POST | `/api/runs` | 202 queued / 409 busy / 422 validation |
| GET | `/api/runs` | `{ source, active_run_id }` |
| GET | `/api/runs/{id}` | live RunSummary |
| DELETE | `/api/runs/{id}` | cancel → updated live summary |
| GET | `/api/runs/{id}/citizens` | paginated; 404 until report exists |
| GET | `/api/model-card` | Phase 10 card envelope |
| GET | `/api/stream/config` | offline |
| POST | `/api/runs/{id}/view` | allow-list; undelivered until Kit streaming |

See also: `docs/PHASE11_LOCAL_PIPELINE.md`, `docs/FRONTEND_BACKEND_HANDOFF.md`,
`frontend/README.md`.
