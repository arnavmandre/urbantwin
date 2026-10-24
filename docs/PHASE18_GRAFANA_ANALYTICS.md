# Phase 18: Grafana run analytics

Grafana shows the history of Argus simulator runs and compares each run's
baseline with its intervention. It is an analytics layer over existing output:
it does not run simulations and does not make results more accurate.

## What runs

```text
Argus API (python -m api) ── writes ──> data/runs/<run_id>/       completed runs
                          └─ appends ─> data/run_events.jsonl     every final status
                                              │
analytics/import_runs.py --watch ── reads ────┘── upserts ──> PostgreSQL (Docker, :5433)
                                                                     │ read-only role
                                                              Grafana (Docker, :3300)
```

| Piece | Where |
|---|---|
| Postgres + Grafana | `analytics/docker-compose.yml`; ports bound to 127.0.0.1 only |
| Schema, comparison view | `analytics/db/init/01_schema.sql` |
| Grafana's DB account | `analytics/db/init/02_grafana_reader.sh`: `SELECT` on `analytics` only, read-only transactions |
| Dashboard | `analytics/grafana/dashboards/argus-observatory.json` (provisioned, uid `argus-observatory`) |
| Importer | `analytics/import_runs.py`; tests in `analytics/test_import_runs.py` |
| Analytics link in Argus | Header button, shown only when `URBANTWIN_GRAFANA_URL` is set; deep-links `var-run=<run_id>` for a completed live run |

## Run it

`tools\demo_launch.ps1` does all of this when Docker Desktop is running (skip
with `-NoAnalytics`). By hand:

```powershell
pip install -r analytics\requirements.txt
docker compose -f analytics\docker-compose.yml up -d
python analytics\import_runs.py --watch          # second shell
$env:URBANTWIN_GRAFANA_URL = "http://localhost:3300"   # before npm run dev
```

Open http://localhost:3300/d/argus-observatory. Viewing needs no login
(anonymous Viewer). Editing needs `admin` / `argus-admin` (override with
`GRAFANA_ADMIN_PASSWORD`). Schema changes need a fresh volume:
`docker compose -f analytics\docker-compose.yml down -v`.

## What the numbers are

- **Baseline vs intervention** are the before and after arms of the *same run*:
  same scenario, same metric definitions. Relative change is blank when the
  baseline is 0. "Better" uses each metric's direction, shared with
  `frontend/lib/metric-format.ts` (a test fails if they drift).
- **Temperature, humidity, rainfall, population** are scenario inputs someone
  typed, never observed weather. Population is an equivalent, not a headcount.
- **Missing metrics are absent**, not zero; metrics with no agreed direction are
  skipped.
- **Pipeline time** is the sum of the pipeline's recorded stage times, without
  queueing.
- **Failed / cancelled counts** only include runs the API logged after
  `data/run_events.jsonl` was introduced. Older failures and CLI failures left
  no record and are not counted.
- **Preset** is derived: the preset whose four inputs match exactly, else
  `custom`.
- All scores are heuristic prototype estimates from synthetic, survey-calibrated
  citizens. Grafana makes them easier to inspect; it does not validate them.
