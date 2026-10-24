"""In-memory single-worker run manager around the Phase 11 pipeline."""
from __future__ import annotations

import json
import math
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from integration.run_pipeline import (
    RESERVED_RUN_ID_PATTERN,
    RUN_ID_PATTERN,
    PipelineConfig,
    PipelineError,
)

from api.shapes import live_citizen_page, live_run_summary

DEFAULT_CITIZENS = Path("Simulation/citizens_survey_city_osm.json")
DEFAULT_CITY = Path("Simulation/city_osm.json")

# Placeholder report so queued/running/failed summaries can reuse live_run_summary
# before (or without) a real simulation_report.json on disk.
_EMPTY_STATE = {
    "metrics": {},
    "citizens": [],
    "problem_zones": [],
    "problem_buildings": [],
    "problem_routes": [],
    "zones": [],
    "buildings": [],
    "routes": [],
    "interventions": {},
}

_EMPTY_ADVISOR = {
    "summary": "",
    "problem_zones": [],
    "problem_buildings": [],
    "problem_routes": [],
    "recommendations": [],
    "affected_buildings": {},
    "explanation": [],
    "supported_interventions": {},
}


class ConflictError(Exception):
    """Raised when a new run cannot start because another is active."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _placeholder_report(scenario: dict) -> dict:
    return {
        "scenario": dict(scenario),
        "before": dict(_EMPTY_STATE),
        "after": dict(_EMPTY_STATE),
        "advisor": dict(_EMPTY_ADVISOR),
        "intervention": {},
        "delta": {},
        "control": {"scenario": {}, "metrics": {}, "recommendations": []},
    }


def _scenario_from_request(request: dict) -> dict:
    return {
        "temperature": request["temperature"],
        "humidity": request["humidity"],
        "rainfall": request["rainfall"],
        "population": request["population"],
    }


class RunManager:
    """Queue at most one live pipeline run and serve RunSummary-shaped state.

    ``apply_recommended_interventions`` is accepted on the request for forward
    compatibility, but Phase 12 still invokes the existing before/after Phase 11
    path: the current simulator always evaluates the advisor / intervention arm.

    The API may report ``cancelled`` immediately, but the single-worker slot stays
    busy (``list_active`` / ``create_run`` conflict) until the worker thread fully
    exits and any child process is cleared.
    """

    def __init__(self, root: Path, *, pipeline_fn=None, events_path: Path | None = None):
        self.root = Path(root)
        self._pipeline_fn = pipeline_fn or self._subprocess_pipeline
        # Optional JSON-lines log of every run's final status. Failed and
        # cancelled runs leave nothing in data/runs/, so this is the only
        # durable record of them (read by analytics/import_runs.py).
        self._events_path = Path(events_path) if events_path else None
        self._lock = threading.RLock()
        self._runs: dict[str, dict] = {}
        self._active_proc: subprocess.Popen | None = None
        self._cancel_flags: dict[str, threading.Event] = {}
        # Occupies the single-worker slot until the worker ``finally`` clears it,
        # even if the run status is already ``cancelled``.
        self._busy_run_id: str | None = None
        # Test hook: keep worker in queued until cleared (cancel-queued coverage).
        self._pause_workers = False

    def create_run(self, request: dict) -> dict:
        """Accept a validated run request. Returns ``{run_id, status: queued}``."""
        with self._lock:
            if self._busy_run_id is not None:
                raise ConflictError(
                    "Another simulation is already queued or running; "
                    "wait for it to finish or cancel it first."
                )
            run_id = self._allocate_run_id()
            created_utc = _utc_now()
            scenario = _scenario_from_request(request)
            cancel_flag = threading.Event()
            self._cancel_flags[run_id] = cancel_flag
            self._runs[run_id] = {
                "run_id": run_id,
                "status": "queued",
                "created_utc": created_utc,
                "request": dict(request),
                "scenario": scenario,
                "report": None,
                "error": None,
            }
            self._busy_run_id = run_id
            thread = threading.Thread(
                target=self._worker,
                args=(run_id,),
                name=f"run-manager-{run_id}",
                daemon=True,
            )
            thread.start()
            return {"run_id": run_id, "status": "queued"}

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            return self._summary_unlocked(record)

    def list_active(self) -> str | None:
        """Return the run occupying the engine slot (including cancel drain)."""
        with self._lock:
            return self._busy_run_id

    def cancel_run(self, run_id: str) -> dict:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return {
                    "error": {
                        "code": "not_found",
                        "message": f"Run {run_id!r} was not found.",
                    }
                }
            status = record["status"]
            if status in {"complete", "failed", "cancelled"}:
                return {
                    "error": {
                        "code": "conflict",
                        "message": (
                            f"Run {run_id!r} is already {status} and cannot be cancelled."
                        ),
                    }
                }
            flag = self._cancel_flags.get(run_id)
            if flag is not None:
                flag.set()
            # Status flips immediately for clients; the slot stays busy until
            # the worker ``finally`` clears ``_busy_run_id``.
            record["status"] = "cancelled"
            proc = self._active_proc
        if proc is not None and proc.poll() is None:
            self._terminate_process_tree(proc)
        return {"run_id": run_id, "status": "cancelled"}

    def get_citizens(self, run_id: str, state: str, limit: int, offset: int) -> dict | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            report = record.get("report")
            if report is None:
                return None
            return live_citizen_page(report, run_id, state, limit, offset)

    def get_report(self, run_id: str) -> dict | None:
        """Return the attached simulator report, or None if the run has not produced one."""
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            report = record.get("report")
            if report is None:
                return None
            return report

    # --- internals ---------------------------------------------------------

    def _allocate_run_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        candidate = f"run_{stamp}"
        if self._run_id_ok(candidate) and candidate not in self._runs:
            return candidate
        for _ in range(32):
            suffix = secrets.token_hex(2)
            candidate = f"run_{stamp}_{suffix}"
            if self._run_id_ok(candidate) and candidate not in self._runs:
                return candidate
        raise RuntimeError("could not allocate a unique Phase-11-safe run id")

    @staticmethod
    def _run_id_ok(run_id: str) -> bool:
        if run_id.endswith((".", " ")):
            return False
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return False
        if RESERVED_RUN_ID_PATTERN.search(run_id):
            return False
        return True

    def _summary_unlocked(self, record: dict) -> dict:
        has_report = record["report"] is not None
        report = record["report"] or _placeholder_report(record["scenario"])
        summary = live_run_summary(
            report,
            record["created_utc"],
            record["run_id"],
            status=record["status"],
            has_report=has_report,
            error=record.get("error"),
        )
        summary["progress"] = self._progress_unlocked(record)
        return summary

    def _progress_unlocked(self, record: dict) -> float:
        """0..1 progress for the dashboard bar (live API previously omitted this)."""
        status = record["status"]
        if status == "queued":
            return 0.05
        if status == "complete":
            return 1.0
        if status in {"failed", "cancelled"}:
            return float(record.get("last_progress") or 0.0)
        if status == "running":
            started = record.get("running_since")
            if started is None:
                return 0.15
            elapsed = max(0.0, time.time() - float(started))
            # The subprocess has no stage-level telemetry. Local runs normally
            # complete in a few seconds, so approach the publishing reserve
            # quickly instead of appearing stuck around 58%.
            value = 0.1 + 0.84 * (1.0 - math.exp(-elapsed / 1.5))
            value = min(0.94, value)
            record["last_progress"] = value
            return value
        return 0.0

    def _worker(self, run_id: str) -> None:
        try:
            self._run_pipeline_worker(run_id)
        finally:
            self._record_terminal(run_id)
            with self._lock:
                if self._busy_run_id == run_id:
                    self._busy_run_id = None

    def _record_terminal(self, run_id: str) -> None:
        """Append the run's final status to the events log, if one is configured.

        Never raises: losing an analytics line must not break a run.
        """
        if self._events_path is None:
            return
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            error = record.get("error") or {}
            event = {
                "run_id": run_id,
                "status": record["status"],
                "created_utc": record["created_utc"],
                "finished_utc": _utc_now(),
                "scenario": dict(record["scenario"]),
                "error_code": error.get("code"),
                "error_message": (error.get("message") or "")[:500] or None,
            }
        try:
            self._events_path.parent.mkdir(parents=True, exist_ok=True)
            with self._events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
        except OSError:
            pass

    def _run_pipeline_worker(self, run_id: str) -> None:
        while self._pause_workers:
            with self._lock:
                record = self._runs.get(run_id)
                if record is None or record["status"] == "cancelled":
                    return
            time.sleep(0.01)

        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            if record["status"] == "cancelled":
                return
            if record["status"] != "queued":
                return
            record["status"] = "running"
            record["running_since"] = time.time()
            request = dict(record["request"])
            cancel_flag = self._cancel_flags.get(run_id)

        config = PipelineConfig(
            root=self.root,
            run_id=run_id,
            citizens=DEFAULT_CITIZENS,
            city=DEFAULT_CITY,
            temperature=float(request["temperature"]),
            humidity=float(request["humidity"]),
            rainfall=float(request["rainfall"]),
            population=int(request["population"]),
            frames=int(request["animation_frames"]),
            duration=float(request["animation_duration_seconds"]),
            publish=True,
            selected_recommendation_ids=tuple(
                request.get("selected_recommendation_ids") or ()
            ),
        )

        try:
            if cancel_flag is not None and cancel_flag.is_set():
                self._mark_cancelled(run_id)
                return
            self._pipeline_fn(config)
            if cancel_flag is not None and cancel_flag.is_set():
                self._mark_cancelled(run_id)
                return
            report_path = (
                self.root / "data" / "runs" / run_id / "simulation_report.json"
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            with self._lock:
                record = self._runs.get(run_id)
                if record is None:
                    return
                if record["status"] == "cancelled" or (
                    cancel_flag is not None and cancel_flag.is_set()
                ):
                    record["status"] = "cancelled"
                    return
                record["report"] = report
                record["status"] = "complete"
                record["error"] = None
        except PipelineError as exc:
            if cancel_flag is not None and cancel_flag.is_set():
                self._mark_cancelled(run_id)
                return
            with self._lock:
                record = self._runs.get(run_id)
                if record is None or record["status"] == "cancelled":
                    return
                record["status"] = "failed"
                record["error"] = {
                    "code": "simulation_failed",
                    "message": str(exc),
                }
        except Exception as exc:  # noqa: BLE001 — surface unexpected worker faults
            if cancel_flag is not None and cancel_flag.is_set():
                self._mark_cancelled(run_id)
                return
            with self._lock:
                record = self._runs.get(run_id)
                if record is None or record["status"] == "cancelled":
                    return
                record["status"] = "failed"
                record["error"] = {
                    "code": "simulation_failed",
                    "message": str(exc),
                }

    def _mark_cancelled(self, run_id: str) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            record["status"] = "cancelled"

    def _subprocess_pipeline(self, config: PipelineConfig) -> dict:
        """Default engine: Phase 11 CLI in a child process so cancel can kill it."""
        script = self.root / "integration" / "run_pipeline.py"
        command = [
            sys.executable,
            str(script),
            "--run-id",
            config.run_id,
            "--citizens",
            str(config.citizens),
            "--city",
            str(config.city),
            "--temperature",
            str(config.temperature),
            "--humidity",
            str(config.humidity),
            "--rainfall",
            str(config.rainfall),
            "--population",
            str(config.population),
            "--frames",
            str(config.frames),
            "--duration",
            str(config.duration),
        ]
        for recommendation_id in config.selected_recommendation_ids:
            command.extend(["--intervention-id", recommendation_id])
        # publish=True is the CLI default (omit --no-publish).
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        proc = subprocess.Popen(
            command,
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        kill_now = False
        with self._lock:
            self._active_proc = proc
            flag = self._cancel_flags.get(config.run_id)
            # Close the race where cancel ran after the pre-pipeline check but
            # before this assignment: kill immediately so publish cannot finish.
            if flag is not None and flag.is_set():
                kill_now = True
        if kill_now:
            self._terminate_process_tree(proc)
        try:
            stdout, stderr = proc.communicate()
            if kill_now or (
                self._cancel_flags.get(config.run_id) is not None
                and self._cancel_flags[config.run_id].is_set()
            ):
                raise PipelineError("cancelled")
            if proc.returncode:
                detail = (stderr or stdout or "").strip() or f"exit {proc.returncode}"
                raise PipelineError(detail)
            return {"status": "complete", "run_id": config.run_id}
        finally:
            with self._lock:
                if self._active_proc is proc:
                    self._active_proc = None

    @staticmethod
    def _terminate_process_tree(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        if sys.platform == "win32":
            # Kill the whole tree started under CREATE_NEW_PROCESS_GROUP.
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
