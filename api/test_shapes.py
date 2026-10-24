import json
import unittest
from pathlib import Path
from unittest import mock

from api.shapes import live_run_summary, live_health, live_stream_config, live_warnings_for
from integration.export_api_mocks import LIVE_RUN_WARNINGS

ROOT = Path(__file__).resolve().parents[1]


class ShapeTests(unittest.TestCase):
    def test_live_summary_marks_source_live_and_drops_fixture_warning(self):
        report = json.loads(
            (ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(
                encoding="utf-8"
            )
        )
        summary = live_run_summary(report, "2026-09-19T12:00:00+00:00", "live-run-1")
        self.assertEqual(summary["source"], "live")
        self.assertEqual(summary["status"], "complete")
        self.assertTrue(all("Recorded fixture" not in w for w in summary["warnings"]))
        self.assertTrue(any("just-executed" in w for w in summary["warnings"]))

    def test_city_facts_follow_the_run_city(self):
        report = json.loads(
            (ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(encoding="utf-8")
        )
        london = live_run_summary(report, "2026-09-19T12:00:00+00:00", "r-london")
        pune = live_run_summary(report, "2026-09-19T12:00:00+00:00", "r-pune", city="pune")
        self.assertEqual(london["city"]["name"], "Russell Square, London")
        self.assertEqual(london["artifacts"]["omniverse_stage"], "phase9/scene/main.usda")
        self.assertEqual(pune["city"]["key"], "pune")
        self.assertEqual(pune["artifacts"]["omniverse_stage"], "cities/pune/main_view_400m.usda")
        self.assertIsNone(pune["artifacts"]["snapshot_pattern"])
        self.assertTrue(any("Vehicles are illustrative" in s for s in pune["city"]["limitations"]))
        self.assertFalse(any("223 of 623" in s for s in pune["city"]["limitations"]))

    def test_live_warnings_gated_by_status_and_report(self):
        report = json.loads(
            (ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(
                encoding="utf-8"
            )
        )
        for status in ("queued", "running", "cancelled"):
            with self.subTest(status=status):
                summary = live_run_summary(
                    report,
                    "2026-09-19T12:00:00+00:00",
                    "live-run-pending",
                    status=status,
                    has_report=False,
                )
                self.assertTrue(
                    all("just-executed" not in w for w in summary["warnings"]),
                    summary["warnings"],
                )
                self.assertNotEqual(summary["warnings"], LIVE_RUN_WARNINGS)
                self.assertEqual(
                    summary["warnings"],
                    live_warnings_for(status, has_report=False),
                )

        failed_without = live_run_summary(
            report,
            "2026-09-19T12:00:00+00:00",
            "live-run-failed",
            status="failed",
            has_report=False,
            error={"code": "simulation_failed", "message": "boom"},
        )
        self.assertTrue(
            all("just-executed" not in w for w in failed_without["warnings"])
        )
        self.assertEqual(
            failed_without["warnings"],
            live_warnings_for("failed", has_report=False),
        )

        failed_with = live_run_summary(
            report,
            "2026-09-19T12:00:00+00:00",
            "live-run-failed-report",
            status="failed",
            has_report=True,
            error={"code": "simulation_failed", "message": "validation"},
        )
        self.assertEqual(failed_with["warnings"], LIVE_RUN_WARNINGS)
        self.assertTrue(any("just-executed" in w for w in failed_with["warnings"]))

        complete = live_run_summary(
            report, "2026-09-19T12:00:00+00:00", "live-run-ok", status="complete"
        )
        self.assertEqual(complete["warnings"], LIVE_RUN_WARNINGS)

    def test_live_health_capabilities(self):
        unavailable = {
            "available": False,
            "host": "127.0.0.1",
            "signal_port": 49100,
            "media_port": 47998,
            "reason": "Kit signaling port is not accepting connections.",
        }
        with mock.patch("api.shapes.probe_stream_endpoint", return_value=unavailable), mock.patch.dict(
            "os.environ", {}, clear=True
        ):
            health = live_health("2026-09-19T12:00:00+00:00")
        self.assertEqual(health["mode"], "live")
        self.assertTrue(health["capabilities"]["http_api"])
        self.assertTrue(health["capabilities"]["live_simulation"])
        self.assertFalse(health["capabilities"]["omniverse_streaming"])
        self.assertFalse(health["capabilities"]["llm_advisor"])
        self.assertEqual(health["omniverse_stream"], "offline")

    def test_live_health_reports_configured_groq(self):
        unavailable = {
            "available": False,
            "host": "127.0.0.1",
            "signal_port": 49100,
            "media_port": 47998,
            "reason": "offline",
        }
        with mock.patch("api.shapes.probe_stream_endpoint", return_value=unavailable), mock.patch.dict(
            "os.environ", {"GROQ_API_KEY": "configured"}, clear=True
        ), mock.patch("api.shapes.importlib.util.find_spec", return_value=object()):
            health = live_health("2026-09-19T12:00:00+00:00")
        self.assertTrue(health["capabilities"]["llm_advisor"])

    def test_live_stream_config_offline_by_default(self):
        with mock.patch(
            "api.shapes.probe_stream_endpoint",
            return_value={
                "available": False,
                "host": "127.0.0.1",
                "signal_port": 49100,
                "media_port": 47998,
                "reason": "Kit signaling port is not accepting connections.",
            },
        ):
            cfg = live_stream_config("2026-09-20T00:00:00+00:00")
        self.assertEqual(cfg["status"], "offline")
        self.assertIsNone(cfg["signaling_url"])


if __name__ == "__main__":
    unittest.main()
