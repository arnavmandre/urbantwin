"""Pune dispatch and file-transaction regression tests."""
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from integration.run_pipeline import (
    PipelineConfig, PipelineError, _CompatibilityTransaction, _install_run,
    _restore_run, _validate_config, run_pipeline,
)


class PipelineTests(unittest.TestCase):
    def config(self, root, run_id="pune-test"):
        return PipelineConfig(root=Path(root), run_id=run_id,
                              citizens=Path("cities/pune/citizens_pune.json"),
                              city=Path("cities/pune/city_pune.json"),
                              temperature=38, humidity=60, rainfall=0, population=50000,
                              publish=False, selected_recommendation_ids=("increase_shade",))

    def test_entrypoint_runs_pune_with_selected_actions(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cities" / "pune"))
        with patch("run_pune.run_pune", return_value={"status": "complete"}) as run:
            result = run_pipeline(self.config("."))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(run.call_args.args, ("pune-test",))
        self.assertEqual(run.call_args.kwargs["interventions"], ("increase_shade",))
        self.assertFalse(run.call_args.kwargs["publish"])

    def test_reserved_and_unsafe_ids_fail_before_running(self):
        for name in ("bad.staging", "bad.backup", "bad.failed-1", "../bad", "bad.", "bad "):
            with self.subTest(name=name), self.assertRaises(PipelineError):
                _validate_config(self.config(".", name))

    def test_rollback_restores_original_and_removes_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, old, new = root/"source", root/"old", root/"new"
            source.write_bytes(b"replacement")
            old.write_bytes(b"original")
            transaction = _CompatibilityTransaction()
            transaction.replace(source, old)
            transaction.replace(source, new)
            self.assertEqual(old.read_bytes(), b"replacement")
            self.assertEqual(transaction.rollback(), [])
            self.assertEqual(old.read_bytes(), b"original")
            self.assertFalse(new.exists())

    def test_run_promotion_can_restore_previous_completed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging, final, backup = root/"staging", root/"final", root/"backup"
            staging.mkdir()
            final.mkdir()
            (staging/"report").write_bytes(b"new")
            (final/"report").write_bytes(b"old")
            had_previous = _install_run(staging, final, backup)
            self.assertTrue(had_previous)
            self.assertEqual((final/"report").read_bytes(), b"new")
            self.assertEqual(_restore_run(final, backup, had_previous, True), [])
            self.assertEqual((final/"report").read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
