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
        from analytics.import_runs import _city_from_stages
        self.assertEqual(_city_from_stages(manifest["stages"]), "city_pune.json")
        self.assertEqual(report["scenario"]["temperature"], 38)
        self.assertEqual(manifest["walkers"]["before"], len(report["before"]["citizens"]))
        self.assertGreater(report["intervention"].get("shade_boost", 0), 0)

    def test_view_run_opinions_win_in_the_composed_view(self):
        """Everything view_run.usdc authors (ProblemZone camera, masks) must be what the 400 m view shows."""
        from pxr import Sdf, Usd
        stage = Usd.Stage.Open(str(HERE / "main_view_400m.usda"))
        run_layer = Sdf.Layer.FindOrOpen(str(HERE / "view_run.usdc"))
        checked = 0

        def visit(path):
            nonlocal checked
            spec = run_layer.GetPrimAtPath(path)
            for prop in spec.properties:
                if not isinstance(prop, Sdf.AttributeSpec) or prop.HasInfo("timeSamples"):
                    continue
                composed = stage.GetPrimAtPath(path).GetAttribute(prop.name)
                strongest = composed.GetPropertyStack(Usd.TimeCode.Default())[0].layer
                self.assertEqual(strongest.identifier, run_layer.identifier, f"{path}.{prop.name} is shadowed")
                checked += 1
            for child in spec.nameChildren:
                visit(child.path)
        visit(Sdf.Path("/World/Cameras"))
        self.assertGreater(checked, 0)

    def test_rejects_reserved_run_id(self):
        with self.assertRaises(run_pune.PipelineError):
            run_pune.run_pune("bad.staging", temperature=30, humidity=50, rainfall=0, population=50000,
                              root=Path(tempfile.gettempdir()), publish=False)


if __name__ == "__main__":
    unittest.main()


class CameraGeometryTests(unittest.TestCase):
    """Sight-line test behind the per-run camera placement (pune_view.blocked)."""

    def test_wall_triangle_blocks_and_open_line_does_not(self):
        import numpy as np
        import pune_view
        wall = np.array([[[5.0, -10.0, 0.0], [5.0, 10.0, 0.0], [5.0, 0.0, 20.0]]])  # plane x = 5
        no_trees = np.zeros((0, 6))
        self.assertTrue(pune_view.blocked((wall, no_trees), (0, 0, 2), (20, 0, 2)))
        self.assertFalse(pune_view.blocked((wall, no_trees), (0, 0, 2), (0, 20, 2)))
        # a person standing within 3 m behind the wall still counts as seen
        self.assertFalse(pune_view.blocked((wall, no_trees), (0, 0, 2), (6.5, 0, 2)))
        tree = np.array([[9.0, -1.0, 0.0, 11.0, 1.0, 6.0]])
        self.assertTrue(pune_view.blocked((np.zeros((0, 3, 3)), tree), (0, 0, 2), (20, 0, 2)))
