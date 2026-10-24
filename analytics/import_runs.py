"""Copy finished Argus runs into PostgreSQL for the Grafana dashboards.

Reads, never writes, the simulator's own output:

* ``data/runs/<run_id>/manifest.json`` + ``simulation_report.json`` for every
  completed run (CLI and API alike), and
* ``data/run_events.jsonl``, the API's log of terminal states, which is the
  only record of failed and cancelled runs.

Idempotent: every run is upserted by ``run_id``. With ``--watch`` it re-imports
changed runs every few seconds, so a run finished in the web app shows up in
Grafana shortly after.

    python analytics/import_runs.py            # one pass
    python analytics/import_runs.py --watch    # keep in sync
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integration.export_api_mocks import scenarios_fixture  # noqa: E402

DEFAULT_DSN = "postgresql://argus_owner:argus_owner_local@127.0.0.1:5433/argus_analytics"

# key -> (label, unit, higher_is_better). Mirrors METRIC_META in
# frontend/lib/metric-format.ts; test_import_runs.py fails if they drift.
METRICS: dict[str, tuple[str, str, bool]] = {
    "human_experience_index": ("Human Experience Index", "score /100", True),
    "citizen_comfort": ("Citizen comfort", "score /100", True),
    "comfort": ("City comfort", "score /100", True),
    "safety": ("Safety", "score /100", True),
    "mobility": ("Mobility", "score /100", True),
    "heat_stress": ("Heat stress", "score /100", False),
    "cold_stress": ("Cold stress", "score /100", False),
    "rain_impact": ("Rain impact", "score /100", False),
    "crowding": ("Crowding", "score /100", False),
    "mean_travel_minutes": ("Mean travel time", "minutes", False),
}

ARMS = (("before", "baseline"), ("after", "intervention"))
INPUT_FIELDS = ("temperature", "humidity", "rainfall", "population")
PRESETS = scenarios_fixture()["presets"]


def preset_for(scenario: dict, presets: list[dict]) -> str | None:
    """The preset whose four inputs match exactly, else None (custom inputs)."""
    for preset in presets:
        try:
            if all(float(scenario[f]) == float(preset[f]) for f in INPUT_FIELDS):
                return preset["id"]
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _inputs(scenario: dict) -> dict:
    def number(key):
        value = scenario.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    population = number("population")
    return {
        "temperature_c": number("temperature"),
        "humidity_pct": number("humidity"),
        "rainfall_prototype": number("rainfall"),
        "population_equivalent": int(population) if population is not None else None,
    }


def _intervention_label(intervention: dict) -> str | None:
    parts = [
        f"{key.replace('_', ' ')} +{round(value * 100)}%"
        for key, value in intervention.items()
        if isinstance(value, (int, float))
    ]
    return ", ".join(parts) or None


def _city_from_stages(stages: list) -> str | None:
    """main.py takes citizens then city as positional paths."""
    for stage in stages:
        if stage.get("name") != "simulation":
            continue
        command = [str(part) for part in stage.get("command") or []]
        for index, part in enumerate(command):
            if part.replace("\\", "/").endswith("Simulation/main.py") and index + 2 < len(command):
                return Path(command[index + 2].replace("\\", "/")).name
    return None


def parse_run_dir(directory: Path, presets: list[dict]) -> dict | None:
    """One completed run directory -> record, or None if it has no report yet."""
    manifest_path = directory / "manifest.json"
    report_path = directory / "simulation_report.json"
    if not (manifest_path.is_file() and report_path.is_file()):
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    scenario = report.get("scenario") or manifest.get("scenario") or {}
    stages = manifest.get("stages") or []
    seconds = [s["seconds"] for s in stages if isinstance(s.get("seconds"), (int, float))]
    intervention = {
        k: float(v) for k, v in (report.get("intervention") or {}).items()
        if isinstance(v, (int, float))
    }

    metrics = []
    for report_arm, arm in ARMS:
        values = (report.get(report_arm) or {}).get("metrics") or {}
        for name, value in values.items():
            # Unknown metrics have no agreed direction, and missing ones are not
            # zero; both are left out rather than guessed.
            if name not in METRICS or not isinstance(value, (int, float)):
                continue
            label, unit, higher_is_better = METRICS[name]
            metrics.append({
                "arm": arm, "metric_name": name, "metric_label": label,
                "metric_value": float(value), "unit": unit,
                "higher_is_better": higher_is_better,
            })

    status = manifest.get("status", "complete")
    return {
        "run_id": manifest.get("run_id") or directory.name,
        "status": status if status in {"complete", "failed", "cancelled"} else "complete",
        "created_at": manifest["created_utc"],
        "finished_at": None,
        "pipeline_seconds": round(sum(seconds), 3) if seconds else None,
        "city_id": _city_from_stages(stages),
        "scenario_preset": preset_for(scenario, presets),
        "intervention": _intervention_label(intervention),
        "error_code": None,
        "record_source": "run_manifest",
        "source_path": str(directory.relative_to(ROOT)) if directory.is_relative_to(ROOT) else str(directory),
        "inputs": _inputs(scenario),
        "metrics": metrics,
        "interventions": sorted(intervention.items()),
    }


def parse_events(path: Path) -> dict[str, dict]:
    """run_id -> its last logged terminal event. Malformed lines are skipped."""
    events: dict[str, dict] = {}
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("run_id") and event.get("status"):
            events[event["run_id"]] = event
    return events


def record_from_event(event: dict, presets: list[dict]) -> dict:
    """A run the API saw end but that left no report (failed or cancelled)."""
    scenario = event.get("scenario") or {}
    return {
        "run_id": event["run_id"],
        "status": event["status"],
        "created_at": event["created_utc"],
        "finished_at": event.get("finished_utc"),
        "pipeline_seconds": None,
        "city_id": None,
        "scenario_preset": preset_for(scenario, presets),
        "intervention": None,
        "error_code": event.get("error_code"),
        "record_source": "api_event",
        "source_path": "data/run_events.jsonl",
        "inputs": _inputs(scenario),
        "metrics": [],
        "interventions": [],
    }


class RunSource:
    """Collects records, re-reading only run directories that changed."""

    def __init__(self, runs_dir: Path, events_path: Path):
        self.runs_dir = runs_dir
        self.events_path = events_path
        self._seen: dict[Path, float] = {}
        self._events_applied: set[tuple[str, str]] = set()

    def changed(self) -> list[dict]:
        records: dict[str, dict] = {}
        events = parse_events(self.events_path)
        new_events = {
            run_id for run_id, e in events.items()
            if (run_id, json.dumps(e, sort_keys=True)) not in self._events_applied
        }
        if self.runs_dir.is_dir():
            for directory in sorted(self.runs_dir.iterdir()):
                report = directory / "simulation_report.json"
                if not directory.is_dir() or not report.is_file():
                    continue
                stamp = report.stat().st_mtime
                # Re-read an unchanged run only when a new event names it.
                if self._seen.get(directory) == stamp and directory.name not in new_events:
                    continue
                try:
                    record = parse_run_dir(directory, PRESETS)
                except (OSError, ValueError, KeyError) as exc:
                    print(f"  skipped {directory.name}: {exc}", file=sys.stderr)
                    continue
                self._seen[directory] = stamp
                if record:
                    records[record["run_id"]] = record

        known = {d.name for d in self._seen}
        for run_id in new_events:
            event = events[run_id]
            if run_id in records:
                records[run_id]["finished_at"] = event.get("finished_utc")
                records[run_id]["error_code"] = event.get("error_code")
            elif run_id not in known:
                records[run_id] = record_from_event(event, PRESETS)
            self._events_applied.add((run_id, json.dumps(event, sort_keys=True)))
        return list(records.values())


UPSERT_RUN = """
INSERT INTO analytics.simulation_runs (
    run_id, status, created_at, finished_at, pipeline_seconds, city_id,
    scenario_preset, intervention, error_code, record_source, source_path, imported_at)
VALUES (%(run_id)s, %(status)s, %(created_at)s, %(finished_at)s, %(pipeline_seconds)s,
        %(city_id)s, %(scenario_preset)s, %(intervention)s, %(error_code)s,
        %(record_source)s, %(source_path)s, now())
ON CONFLICT (run_id) DO UPDATE SET
    status = EXCLUDED.status,
    created_at = EXCLUDED.created_at,
    finished_at = COALESCE(EXCLUDED.finished_at, analytics.simulation_runs.finished_at),
    pipeline_seconds = EXCLUDED.pipeline_seconds,
    city_id = EXCLUDED.city_id,
    scenario_preset = EXCLUDED.scenario_preset,
    intervention = EXCLUDED.intervention,
    error_code = COALESCE(EXCLUDED.error_code, analytics.simulation_runs.error_code),
    record_source = EXCLUDED.record_source,
    source_path = EXCLUDED.source_path,
    imported_at = now()
"""

UPSERT_INPUTS = """
INSERT INTO analytics.scenario_inputs (
    run_id, temperature_c, humidity_pct, rainfall_prototype, population_equivalent)
VALUES (%(run_id)s, %(temperature_c)s, %(humidity_pct)s, %(rainfall_prototype)s,
        %(population_equivalent)s)
ON CONFLICT (run_id) DO UPDATE SET
    temperature_c = EXCLUDED.temperature_c,
    humidity_pct = EXCLUDED.humidity_pct,
    rainfall_prototype = EXCLUDED.rainfall_prototype,
    population_equivalent = EXCLUDED.population_equivalent
"""

INSERT_METRIC = """
INSERT INTO analytics.simulation_metrics (
    run_id, arm, metric_name, metric_label, metric_value, unit, higher_is_better)
VALUES (%(run_id)s, %(arm)s, %(metric_name)s, %(metric_label)s, %(metric_value)s,
        %(unit)s, %(higher_is_better)s)
"""


def write(conn, records: list[dict]) -> None:
    with conn.transaction(), conn.cursor() as cur:
        for record in records:
            cur.execute(UPSERT_RUN, record)
            cur.execute(UPSERT_INPUTS, {"run_id": record["run_id"], **record["inputs"]})
            # An event-only record carries no metrics; never wipe a run's
            # metrics on its account.
            if record["record_source"] != "run_manifest":
                continue
            cur.execute("DELETE FROM analytics.simulation_metrics WHERE run_id = %s", (record["run_id"],))
            cur.execute("DELETE FROM analytics.interventions WHERE run_id = %s", (record["run_id"],))
            cur.executemany(INSERT_METRIC, [{"run_id": record["run_id"], **m} for m in record["metrics"]])
            cur.executemany(
                "INSERT INTO analytics.interventions (run_id, parameter, value) VALUES (%s, %s, %s)",
                [(record["run_id"], key, value) for key, value in record["interventions"]],
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", default=os.environ.get("ARGUS_ANALYTICS_DSN", DEFAULT_DSN))
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "data" / "runs")
    parser.add_argument("--events", type=Path, default=ROOT / "data" / "run_events.jsonl")
    parser.add_argument("--watch", action="store_true", help="keep importing changed runs")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between --watch passes")
    args = parser.parse_args(argv)

    import psycopg  # imported here so the parsing helpers and tests need no driver

    source = RunSource(args.runs_dir, args.events)
    while True:
        try:
            with psycopg.connect(args.dsn, connect_timeout=5) as conn:
                while True:
                    records = source.changed()
                    if records:
                        write(conn, records)
                        print(f"imported {len(records)} run(s): "
                              + ", ".join(r["run_id"] for r in records[-3:])
                              + (" ..." if len(records) > 3 else ""), flush=True)
                    if not args.watch:
                        return 0
                    time.sleep(args.interval)
        except psycopg.OperationalError as exc:
            if not args.watch:
                print(f"cannot reach the analytics database: {exc}", file=sys.stderr)
                return 1
            print(f"database unavailable, retrying: {str(exc).strip()[:120]}", file=sys.stderr, flush=True)
            time.sleep(max(args.interval, 5.0))


if __name__ == "__main__":
    raise SystemExit(main())
