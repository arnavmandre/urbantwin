"""End-to-end check of one Pune run into a temporary root (no publish). ~7 s.

    python -m unittest cities/pune/test_run_pune.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]

import run_pune  # noqa: E402

PREPARED = all((HERE / name).is_file() for name in run_pune.PREPARED)


@unittest.skipUnless(PREPARED, "Pune not prepared: run pune_sim.py then pune_view.py first")
class RunPuneTests(unittest.TestCase):
    def test_run_writes_standard_run_dir_with_both_arms(self):
        with tempfile.TemporaryDirectory() as root:
            result = run_pune.run_pune("pune-test", temperature=38, humidity=60, rainfall=0, population=50000,
                                       interventions=["increase_shade"], root=Path(root), publish=False)
            run = Path(root) / "data" / "runs" / "pune-test"
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((run / "simulation_report.json").read_text(encoding="utf-8"))
            for name in ("agents_before.usdc", "agents_after.usdc", "view_run.usdc"):
                self.assertTrue((run / "usd" / name).is_file(), name)
            self.assertFalse((Path(root) / "data" / "runs" / "pune-test.staging").exists())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(manifest["city"], "pune")
        self.assertEqual(report["scenario"]["temperature"], 38)
        self.assertEqual(manifest["walkers"]["before"], len(report["before"]["citizens"]))
        self.assertGreater(report["intervention"].get("shade_boost", 0), 0)

    def test_rejects_reserved_run_id(self):
        with self.assertRaises(run_pune.PipelineError):
            run_pune.run_pune("bad.staging", temperature=30, humidity=50, rainfall=0, population=50000,
                              root=Path(tempfile.gettempdir()), publish=False)


if __name__ == "__main__":
    unittest.main()
