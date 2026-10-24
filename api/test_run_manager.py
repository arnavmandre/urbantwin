"""Unit tests for the in-memory single-worker RunManager."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from integration.run_pipeline import PipelineError

from api.run_manager import ConflictError, RunManager


def _minimal_report_json(scenario: dict) -> str:
    # live_run_summary / state_summary need before/after/control structure.
    return (
        "{"
        f'"scenario":{ _json_obj(scenario) },'
        '"before":{"metrics":{},"citizens":[],"problem_zones":[],'
        '"problem_buildings":[],"problem_routes":[],"zones":[],'
        '"buildings":[],"routes":[],"interventions":{}},'
        '"after":{"metrics":{},"citizens":[],"problem_zones":[],'
        '"problem_buildings":[],"problem_routes":[],"zones":[],'
        '"buildings":[],"routes":[],"interventions":{}},'
        '"advisor":{"summary":"","problem_zones":[],"problem_buildings":[],'
        '"problem_routes":[],"recommendations":[],"affected_buildings":{},'
        '"explanation":[],"supported_interventions":{}},'
        '"intervention":{},'
        '"delta":{},'
        '"control":{"scenario":{},"metrics":{},"recommendations":[]}'
        "}\n"
    )


def _json_obj(obj: dict) -> str:
    import json

    return json.dumps(obj, separators=(",", ":"))


def _valid_request(**overrides):
    body = {
        "temperature": 31,
        "humidity": 55,
        "rainfall": 12,
        "population": 42000,
        "apply_recommended_interventions": True,
        "animation_frames": 1,
        "animation_duration_seconds": 1,
    }
    body.update(overrides)
    return body


def _write_report(config) -> None:
    report = Path(config.root) / "data" / "runs" / config.run_id / "simulation_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    scenario = {
        "temperature": config.temperature,
        "humidity": config.humidity,
        "rainfall": config.rainfall,
        "population": config.population,
    }
    report.write_text(_minimal_report_json(scenario), encoding="utf-8")


def _wait_until(predicate, timeout=2.0, interval=0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class RunManagerTests(unittest.TestCase):
    def test_running_progress_matches_short_local_runtime(self):
        manager = RunManager(Path("."), pipeline_fn=lambda config: None)
        record = {"status": "running", "running_since": time.time() - 5.0}

        progress = manager._progress_unlocked(record)

        self.assertGreater(progress, 0.9)
        self.assertLessEqual(progress, 0.94)

    def test_user_selection_reaches_pipeline_config(self):
        captured = []

        def pipeline(config):
            captured.append(config.selected_recommendation_ids)
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=pipeline)
            created = manager.create_run(
                _valid_request(selected_recommendation_ids=["improve_drainage"])
            )
            self.assertTrue(
                _wait_until(
                    lambda: manager.get_run(created["run_id"])["status"] == "complete"
                )
            )
            self.assertEqual(captured, [("improve_drainage",)])

    def test_pune_request_targets_pune_files_and_reports_pune(self):
        captured = []

        def pipeline(config):
            captured.append(config)
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=pipeline)
            created = manager.create_run(_valid_request(city="pune"))
            self.assertTrue(
                _wait_until(lambda: manager.get_run(created["run_id"])["status"] == "complete")
            )
            summary = manager.get_run(created["run_id"])
        config = captured[0]
        self.assertEqual(config.city_key, "pune")
        self.assertEqual(config.city, Path("cities/pune/city_pune.json"))
        self.assertEqual(config.citizens, Path("cities/pune/citizens_pune.json"))
        self.assertEqual(summary["city"]["key"], "pune")
        self.assertEqual(summary["artifacts"]["omniverse_stage"], "cities/pune/main_view_400m.usda")

    def test_pune_subprocess_runs_pune_pipeline_script(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory))
            config = mock.Mock(city_key="pune", run_id="r1", citizens="c", city="k", temperature=1,
                               humidity=1, rainfall=1, population=1, frames=1, duration=1,
                               selected_recommendation_ids=())
            proc = mock.Mock(returncode=0, communicate=mock.Mock(return_value=("", "")))
            with mock.patch("api.run_manager.subprocess.Popen", return_value=proc) as popen:
                manager._subprocess_pipeline(config)
        script = Path(popen.call_args.args[0][1])
        self.assertEqual(script.as_posix()[-len("cities/pune/run_pune.py"):], "cities/pune/run_pune.py")

    def test_second_create_conflicts_while_running(self):
        def slow_pipeline(config):
            time.sleep(0.2)
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=slow_pipeline)
            first = manager.create_run(_valid_request())
            with self.assertRaises(ConflictError):
                manager.create_run(
                    _valid_request(
                        temperature=26,
                        humidity=40,
                        rainfall=5,
                        population=30000,
                    )
                )
            for _ in range(50):
                summary = manager.get_run(first["run_id"])
                if summary["status"] in {"complete", "failed"}:
                    break
                time.sleep(0.05)
            self.assertEqual(manager.get_run(first["run_id"])["status"], "complete")
            self.assertEqual(manager.get_run(first["run_id"])["source"], "live")

    def test_cancel_queued_run(self):
        def pipeline(config):
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=pipeline)
            manager._pause_workers = True
            created = manager.create_run(_valid_request())
            time.sleep(0.05)
            self.assertEqual(manager.get_run(created["run_id"])["status"], "queued")
            result = manager.cancel_run(created["run_id"])
            self.assertEqual(result["status"], "cancelled")
            # Engine still draining while the paused worker has not exited.
            with self.assertRaises(ConflictError):
                manager.create_run(
                    _valid_request(
                        temperature=26,
                        humidity=40,
                        rainfall=5,
                        population=30000,
                    )
                )
            manager._pause_workers = False
            self.assertTrue(
                _wait_until(lambda: manager.list_active() is None),
                "engine should go idle after cancelled worker exits",
            )
            self.assertEqual(manager.get_run(created["run_id"])["status"], "cancelled")

    def test_failed_pipeline_becomes_failed_with_error(self):
        def failing_pipeline(config):
            raise PipelineError("simulator exploded")

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=failing_pipeline)
            created = manager.create_run(_valid_request())
            for _ in range(50):
                summary = manager.get_run(created["run_id"])
                if summary["status"] in {"complete", "failed", "cancelled"}:
                    break
                time.sleep(0.05)
            summary = manager.get_run(created["run_id"])
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["error"]["code"], "simulation_failed")
            self.assertIn("simulator exploded", summary["error"]["message"])
            self.assertIsNone(manager.list_active())

    def test_terminal_status_is_appended_to_events_log(self):
        def failing_pipeline(config):
            raise PipelineError("simulator exploded")

        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "data" / "run_events.jsonl"
            manager = RunManager(
                Path(directory), pipeline_fn=failing_pipeline, events_path=events
            )
            created = manager.create_run(_valid_request())
            self.assertTrue(
                _wait_until(lambda: events.exists() and manager.list_active() is None)
            )
            lines = events.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["run_id"], created["run_id"])
            self.assertEqual(event["status"], "failed")
            self.assertEqual(event["error_code"], "simulation_failed")
            self.assertEqual(event["scenario"]["population"], 42000)
            self.assertTrue(event["created_utc"] and event["finished_utc"])

    def test_events_log_is_off_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=_write_report)
            manager.create_run(_valid_request())
            self.assertTrue(_wait_until(lambda: manager.list_active() is None))
            self.assertFalse((Path(directory) / "data" / "run_events.jsonl").exists())

    def test_unknown_run_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=lambda config: None)
            self.assertIsNone(manager.get_run("run_missing_000000"))
            self.assertIsNone(
                manager.get_citizens("run_missing_000000", "before", 10, 0)
            )

    def test_list_active_and_citizens_after_complete(self):
        entered = threading.Event()
        release = threading.Event()

        def gated_pipeline(config):
            entered.set()
            release.wait(timeout=2)
            _write_report(config)
            # One citizen so pagination has something to return.
            path = Path(config.root) / "data" / "runs" / config.run_id / "simulation_report.json"
            import json

            report = json.loads(path.read_text(encoding="utf-8"))
            report["before"]["citizens"] = [
                {
                    "id": "c1",
                    "archetype": "student",
                    "behavior": "SEEK_SHADE",
                    "home": "A",
                    "destination": "B",
                }
            ]
            path.write_text(json.dumps(report), encoding="utf-8")
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=gated_pipeline)
            created = manager.create_run(_valid_request())
            self.assertTrue(entered.wait(timeout=2))
            self.assertEqual(manager.list_active(), created["run_id"])
            release.set()
            for _ in range(50):
                if manager.get_run(created["run_id"])["status"] == "complete":
                    break
                time.sleep(0.05)
            page = manager.get_citizens(created["run_id"], "before", 10, 0)
            self.assertIsNotNone(page)
            self.assertEqual(page["source"], "live")
            self.assertEqual(page["total_in_run"], 1)
            self.assertEqual(len(page["items"]), 1)

    def test_create_conflicts_while_cancelled_engine_still_busy(self):
        """P1: cancel must not free the slot until the worker/engine finishes."""
        entered = threading.Event()
        release = threading.Event()

        def blocking_pipeline(config):
            entered.set()
            release.wait(timeout=5)
            time.sleep(0.05)
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=blocking_pipeline)
            first = manager.create_run(_valid_request())
            self.assertTrue(entered.wait(timeout=2))
            cancelled = manager.cancel_run(first["run_id"])
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(manager.get_run(first["run_id"])["status"], "cancelled")
            with self.assertRaises(ConflictError):
                manager.create_run(
                    _valid_request(
                        temperature=26,
                        humidity=40,
                        rainfall=5,
                        population=30000,
                    )
                )
            release.set()
            self.assertTrue(
                _wait_until(lambda: manager.list_active() is None),
                "busy should clear only after worker finally exits",
            )
            self.assertEqual(manager.get_run(first["run_id"])["status"], "cancelled")
            second = manager.create_run(
                _valid_request(
                    temperature=26,
                    humidity=40,
                    rainfall=5,
                    population=30000,
                )
            )
            self.assertEqual(second["status"], "queued")
            self.assertTrue(
                _wait_until(
                    lambda: manager.get_run(second["run_id"])["status"]
                    in {"complete", "failed"}
                )
            )

    def test_cancel_while_running_keeps_cancelled_not_complete(self):
        entered = threading.Event()
        release = threading.Event()

        def blocking_pipeline(config):
            entered.set()
            release.wait(timeout=5)
            _write_report(config)
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=blocking_pipeline)
            created = manager.create_run(_valid_request())
            self.assertTrue(entered.wait(timeout=2))
            self.assertEqual(manager.list_active(), created["run_id"])
            result = manager.cancel_run(created["run_id"])
            self.assertEqual(result["status"], "cancelled")
            with self.assertRaises(ConflictError):
                manager.create_run(
                    _valid_request(
                        temperature=28,
                        humidity=50,
                        rainfall=10,
                        population=35000,
                    )
                )
            release.set()
            self.assertTrue(_wait_until(lambda: manager.list_active() is None))
            self.assertEqual(manager.get_run(created["run_id"])["status"], "cancelled")

    def test_cancel_during_popen_startup_kills_before_communicate(self):
        """P1: cancel between pre-check and _active_proc assign must still kill."""
        init_entered = threading.Event()
        allow_init = threading.Event()
        terminate_pids: list[int] = []

        class GatedPopen:
            def __init__(self, *args, **kwargs):
                init_entered.set()
                allow_init.wait(timeout=5)
                self.pid = 4242
                self.returncode = None

            def poll(self):
                return self.returncode

            def communicate(self):
                deadline = time.time() + 2
                while self.returncode is None and time.time() < deadline:
                    time.sleep(0.01)
                return ("", "terminated by cancel")

        def fake_terminate(proc):
            terminate_pids.append(proc.pid)
            proc.returncode = 1

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory))
            with mock.patch("api.run_manager.subprocess.Popen", GatedPopen), mock.patch.object(
                RunManager, "_terminate_process_tree", staticmethod(fake_terminate)
            ):
                created = manager.create_run(_valid_request())
                self.assertTrue(init_entered.wait(timeout=2))
                # Cancel while Popen __init__ is gated — _active_proc not set yet.
                cancelled = manager.cancel_run(created["run_id"])
                self.assertEqual(cancelled["status"], "cancelled")
                allow_init.set()
                self.assertTrue(
                    _wait_until(
                        lambda: manager.get_run(created["run_id"])["status"] == "cancelled"
                    )
                )
                self.assertTrue(
                    _wait_until(lambda: manager.list_active() is None),
                    "worker must finish after startup kill",
                )
                self.assertEqual(terminate_pids, [4242])
                self.assertEqual(manager.get_run(created["run_id"])["status"], "cancelled")
                report = (
                    Path(directory)
                    / "data"
                    / "runs"
                    / created["run_id"]
                    / "simulation_report.json"
                )
                self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
