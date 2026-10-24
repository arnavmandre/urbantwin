"""One dashboard/API run on the Pune city: simulate -> animate both arms -> view mask -> publish.

The Pune counterpart of integration/run_pipeline.py, called by api/run_manager.py for `city: "pune"`.
It writes the same data/runs/<run_id>/ shape (simulation_report.json + manifest.json) so the run manager,
explain/advisor endpoints and analytics/import_runs.py read Pune runs unchanged, and it reuses
run_pipeline's staging, promotion and rollback helpers rather than copying them.

Deliberate exception to the canonical-snapshot rule (CLAUDE.md rule 4): Pune skips canonical v1 snapshots.
That contract is bound to the frozen London Phase 1 city_id and edge registry; Pune animates straight from
the simulator report over its own OSM route polylines (pune_sim.animate). See docs/PUNE_CITY.md.

Publishing copies agents_before.usdc, agents_after.usdc and view_run.usdc into cities/pune/, which
main_view_400m.usda composes; a Kit started with auto-reload picks the new run up without a restart.

    python cities/pune/run_pune.py --run-id demo1 --temperature 38 --humidity 60 --rainfall 0 --population 50000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]

import pune_sim  # noqa: E402
import pune_view  # noqa: E402
from integration.run_pipeline import (  # noqa: E402
    RESERVED_RUN_ID_PATTERN,
    RUN_ID_PATTERN,
    PipelineError,
    _CompatibilityTransaction,
    _cleanup_staging,
    _install_run,
    _recover_stale_backup,
    _restore_run,
)

STAGE = "cities/pune/main_view_400m.usda"
PUBLISHED = ("agents_before.usdc", "agents_after.usdc", "view_run.usdc")


def _check_run_id(run_id: str) -> None:
    if run_id.endswith((".", " ")) or not RUN_ID_PATTERN.fullmatch(run_id) or RESERVED_RUN_ID_PATTERN.search(run_id):
        raise PipelineError(f"invalid run id {run_id!r}")


PREPARED = ("city_pune.json", "citizens_pune.json", "pune_routes.json", "traffic.usdc",
            "main_live.usda", "main_view_400m.usda")


def run_pune(run_id, *, temperature, humidity, rainfall, population, interventions=(),
             root: Path = ROOT, publish: bool = True) -> dict:
    _check_run_id(run_id)
    missing = [name for name in PREPARED if not (HERE / name).is_file()]
    if missing:
        raise PipelineError(f"Pune city is not prepared (missing {', '.join(missing)}). "
                            "Run: python cities/pune/pune_sim.py && python cities/pune/pune_view.py")
    runs = Path(root) / "data" / "runs"
    staging, final, backup = runs / f"{run_id}.staging", runs / run_id, runs / f"{run_id}.backup"
    try:
        runs.mkdir(parents=True, exist_ok=True)
        _recover_stale_backup(final, backup)
        _cleanup_staging(staging)
        (staging / "usd").mkdir(parents=True)
    except OSError as exc:
        raise PipelineError(f"pipeline setup failed: {exc}") from exc

    stages = []

    def timed(name, fn):
        t0 = time.perf_counter()
        result = fn()
        stages.append({"name": name, "seconds": round(time.perf_counter() - t0, 3)})
        return result

    try:
        report, sim_command = timed("simulation", lambda: pune_sim.simulate(
            staging / "simulation_report.json", temperature=temperature, humidity=humidity,
            rainfall=rainfall, population=population, interventions=interventions))
        # same shape as London's stage record; analytics/import_runs.py reads the city file from this command
        stages[-1]["command"] = sim_command
        walkers = timed("agents", lambda: pune_sim.animate(report, staging / "usd"))
        view = timed("view_mask", lambda: pune_view.write_run_layer(staging / "usd", report,
                                                                   staging / "usd" / "view_run.usdc"))
        manifest = {
            "schema_version": 1, "run_id": run_id, "status": "complete", "city": "pune",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scenario": {"temperature": temperature, "humidity": humidity,
                         "rainfall": rainfall, "population": population},
            "selected_recommendation_ids": list(interventions),
            "animation": {"duration_seconds": pune_sim.DURATION_S, "samples_per_second": pune_sim.SAMPLE_HZ,
                          "time_scale": pune_sim.TIME_SCALE},
            "artifacts": {"simulation_report": "simulation_report.json",
                          "before_agents_usd": "usd/agents_before.usdc",
                          "after_agents_usd": "usd/agents_after.usdc",
                          "view_run_layer": "usd/view_run.usdc",
                          "omniverse_stage": STAGE},
            "walkers": walkers, "view": view,
            "notes": ["No canonical v1 snapshots: Pune animates from the report (documented exception).",
                      "Vehicles are illustrative; no traffic data."],
            "stages": stages,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        _cleanup_staging(staging)
        raise PipelineError(f"pune pipeline failed: {exc}") from exc

    had_previous = _install_run(staging, final, backup)
    warnings = []
    if publish:
        transaction = _CompatibilityTransaction()
        try:
            for name in PUBLISHED:
                transaction.replace(final / "usd" / name, HERE / name)
        except OSError as exc:
            errors = transaction.rollback() + _restore_run(final, backup, had_previous, True)
            raise PipelineError(f"publishing Pune layers failed: {exc}; rollback: {errors}") from exc
        warnings += transaction.commit()
    _cleanup_staging(backup)
    return {"run_id": run_id, "status": "complete", "warnings": warnings, "manifest": manifest}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--temperature", type=float, required=True)
    ap.add_argument("--humidity", type=float, required=True)
    ap.add_argument("--rainfall", type=float, required=True)
    ap.add_argument("--population", type=int, required=True)
    ap.add_argument("--intervention-id", action="append", default=[])
    # Accepted for parity with run_pipeline.py, which api/run_manager.py always calls with them.
    # Pune's city/citizen files and animation length are fixed (see manifest "animation").
    ap.add_argument("--citizens", default=None)
    ap.add_argument("--city", default=None)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args()
    try:
        result = run_pune(args.run_id, temperature=args.temperature, humidity=args.humidity,
                          rainfall=args.rainfall, population=args.population,
                          interventions=args.intervention_id, publish=not args.no_publish)
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in result.items() if k != "manifest"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
