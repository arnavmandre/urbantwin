"""Tests for the run importer's parsing. No database needed."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics import import_runs as ir  # noqa: E402


def _write_run(runs: Path, run_id: str, *, scenario=None, before=None, after=None,
               intervention=None, stages=None, status="complete") -> Path:
    scenario = scenario or {"temperature": 18.0, "humidity": 85.0, "rainfall": 90.0, "population": 60000}
    directory = runs / run_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "created_utc": "2026-10-24T07:19:58+00:00",
        "scenario": scenario,
        "stages": stages if stages is not None else [
            {"name": "simulation", "seconds": 0.8,
             "command": ["python.exe", "C:/x/Simulation/main.py", "C:/x/Simulation/citizens.json",
                         "C:/x/Simulation/city_osm.json", "--temperature", "18.0"]},
            {"name": "validation", "seconds": 0.7, "command": ["python.exe"]},
        ],
    }), encoding="utf-8")
    (directory / "simulation_report.json").write_text(json.dumps({
        "scenario": scenario,
        "before": {"metrics": before if before is not None else {"safety": 62.14, "rain_impact": 45.81}},
        "after": {"metrics": after if after is not None else {"safety": 86.81, "rain_impact": 7.86}},
        "intervention": intervention if intervention is not None else {"drainage_boost": 0.35},
    }), encoding="utf-8")
    return directory


class ParseRunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.runs = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_complete_run_maps_arms_inputs_and_metadata(self):
        record = ir.parse_run_dir(_write_run(self.runs, "run_20261024_071952"), ir.PRESETS)
        self.assertEqual(record["run_id"], "run_20261024_071952")
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["record_source"], "run_manifest")
        self.assertAlmostEqual(record["pipeline_seconds"], 1.5)
        self.assertEqual(record["city_id"], "city_osm.json")
        self.assertEqual(record["scenario_preset"], "extreme_rainfall")
        self.assertEqual(record["intervention"], "drainage boost +35%")
        self.assertEqual(record["inputs"]["population_equivalent"], 60000)
        metrics = {(m["arm"], m["metric_name"]): m for m in record["metrics"]}
        self.assertEqual(metrics[("baseline", "safety")]["metric_value"], 62.14)
        self.assertEqual(metrics[("intervention", "rain_impact")]["metric_value"], 7.86)
        self.assertTrue(metrics[("baseline", "safety")]["higher_is_better"])
        self.assertFalse(metrics[("baseline", "rain_impact")]["higher_is_better"])
        self.assertEqual(record["interventions"], [("drainage_boost", 0.35)])

    def test_missing_and_unknown_metrics_are_not_stored(self):
        directory = _write_run(
            self.runs, "run_20261024_000001",
            before={"safety": 50.0, "made_up_score": 3.0, "mobility": None},
            after={},
        )
        record = ir.parse_run_dir(directory, ir.PRESETS)
        names = [(m["arm"], m["metric_name"]) for m in record["metrics"]]
        self.assertEqual(names, [("baseline", "safety")])

    def test_custom_inputs_have_no_preset(self):
        directory = _write_run(self.runs, "run_20261024_000002", scenario={
            "temperature": 21.0, "humidity": 50.0, "rainfall": 10.0, "population": 40000})
        self.assertIsNone(ir.parse_run_dir(directory, ir.PRESETS)["scenario_preset"])

    def test_no_intervention_gives_no_label(self):
        directory = _write_run(self.runs, "run_20261024_000003", intervention={})
        record = ir.parse_run_dir(directory, ir.PRESETS)
        self.assertIsNone(record["intervention"])
        self.assertEqual(record["interventions"], [])

    def test_directory_without_report_is_skipped(self):
        (self.runs / "run_20261023_180855.staging").mkdir()
        self.assertIsNone(ir.parse_run_dir(self.runs / "run_20261023_180855.staging", ir.PRESETS))


class EventTests(unittest.TestCase):
    def test_last_event_per_run_wins_and_bad_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run_events.jsonl"
            path.write_text(
                json.dumps({"run_id": "run_a", "status": "failed", "created_utc": "2026-10-24T07:00:00+00:00",
                            "finished_utc": "2026-10-24T07:00:05+00:00",
                            "scenario": {"temperature": 31, "humidity": 55, "rainfall": 12, "population": 42000},
                            "error_code": "simulation_failed"}) + "\n"
                + "not json\n"
                + json.dumps({"run_id": "run_b", "status": "complete", "created_utc": "2026-10-24T08:00:00+00:00",
                              "finished_utc": "2026-10-24T08:00:09+00:00", "scenario": {}}) + "\n",
                encoding="utf-8",
            )
            events = ir.parse_events(path)
        self.assertEqual(set(events), {"run_a", "run_b"})
        self.assertEqual(events["run_a"]["status"], "failed")

    def test_event_only_run_becomes_record_without_metrics(self):
        record = ir.record_from_event({
            "run_id": "run_a", "status": "failed", "created_utc": "2026-10-24T07:00:00+00:00",
            "finished_utc": "2026-10-24T07:00:05+00:00",
            "scenario": {"temperature": 31, "humidity": 55, "rainfall": 12, "population": 42000},
            "error_code": "simulation_failed",
        }, ir.PRESETS)
        self.assertEqual(record["record_source"], "api_event")
        self.assertEqual(record["error_code"], "simulation_failed")
        self.assertEqual(record["metrics"], [])
        self.assertIsNone(record["pipeline_seconds"])


class MetricMetaTests(unittest.TestCase):
    def test_directions_match_the_frontend(self):
        """The dashboard and the web app must agree on what 'better' means."""
        source = (ROOT / "frontend" / "lib" / "metric-format.ts").read_text(encoding="utf-8")
        frontend = dict(re.findall(r'\n  (\w+): \{\s*key: "\w+",[^}]*?direction: "(\w+)"', source))
        self.assertEqual(set(frontend), set(ir.METRICS))
        for key, direction in frontend.items():
            self.assertEqual(ir.METRICS[key][2], direction == "higher_is_better", key)


if __name__ == "__main__":
    unittest.main()
