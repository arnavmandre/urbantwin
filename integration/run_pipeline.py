"""Run the UrbanTwin simulator-to-frontend pipeline in an isolated directory."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict


ROOT = Path(__file__).resolve().parents[1]
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
RESERVED_RUN_ID_PATTERN = re.compile(
    r"(?:\.staging|\.backup)$|\.failed-", re.IGNORECASE
)
STAGE_OUTPUT_LIMIT = 4000


@dataclass(frozen=True)
class PipelineConfig:
    root: Path
    run_id: str
    citizens: Path
    city: Path
    temperature: float
    humidity: float
    rainfall: float
    population: int
    frames: int = 60
    duration: float = 60.0
    publish: bool = True
    selected_recommendation_ids: tuple[str, ...] = ()
    city_key: str = "london"  # selects the pipeline script (integration/cities.py); this module runs London


class StageResult(TypedDict):
    name: str
    command: list[str]
    seconds: float
    stdout: str
    stdout_truncated: NotRequired[bool]
    stderr: NotRequired[str]
    stderr_truncated: NotRequired[bool]


class PipelineError(RuntimeError):
    pass


def _tail(text: str, limit: int = STAGE_OUTPUT_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[-limit:], True


def run_stage(name, command, cwd) -> StageResult:
    """Execute one subprocess and retain bounded diagnostic evidence."""
    started = time.perf_counter()
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    elapsed = round(time.perf_counter() - started, 3)
    if result.returncode:
        stdout, stdout_cut = _tail(result.stdout, 8000)
        stderr, stderr_cut = _tail(result.stderr, 8000)
        raise PipelineError(
            f"{name} failed with exit {result.returncode}\n"
            f"stdout{' (tail)' if stdout_cut else ''}:\n{stdout}\n"
            f"stderr{' (tail)' if stderr_cut else ''}:\n{stderr}"
        )

    stdout, stdout_cut = _tail(result.stdout)
    stderr, stderr_cut = _tail(result.stderr)
    stage: StageResult = {
        "name": name,
        "command": [str(part) for part in command],
        "seconds": elapsed,
        "stdout": stdout,
    }
    if stdout_cut:
        stage["stdout_truncated"] = True
    if stderr:
        stage["stderr"] = stderr
    if stderr_cut:
        stage["stderr_truncated"] = True
    return stage


def _record_stage(name: str, command: list[object], root: Path) -> StageResult:
    """Normalize real and test-double stage results into manifest-safe data."""
    result = dict(run_stage(name, command, root))
    result["name"] = name
    result["command"] = [str(part) for part in command]
    result["seconds"] = float(result.get("seconds", 0.0))
    stdout, stdout_cut = _tail(str(result.get("stdout", "")))
    result["stdout"] = stdout
    if stdout_cut:
        result["stdout_truncated"] = True
    stderr = str(result.get("stderr", ""))
    if stderr:
        stderr, stderr_cut = _tail(stderr)
        result["stderr"] = stderr
        if stderr_cut:
            result["stderr_truncated"] = True
    return result  # type: ignore[return-value]


def _validate_config(config: PipelineConfig) -> None:
    if config.run_id.endswith((".", " ")):
        raise PipelineError(
            "run ID must not end with a Windows-unsafe trailing dot or space"
        )
    if not RUN_ID_PATTERN.fullmatch(config.run_id):
        raise PipelineError(
            "run ID must use 1-64 letters, digits, dot, underscore or hyphen"
        )
    if RESERVED_RUN_ID_PATTERN.search(config.run_id):
        raise PipelineError(
            "run ID uses a reserved pipeline scratch suffix or pattern"
        )
    if config.frames < 1:
        raise PipelineError("frames must be >= 1")
    if config.duration <= 0:
        raise PipelineError("duration must be > 0")


def _snapshot_paths(directory: Path, state: str) -> list[Path]:
    numbered = sorted(directory.glob(f"simulation_{state}_[0-9][0-9][0-9].json"))
    if numbered:
        return numbered
    still = directory / f"simulation_{state}.json"
    return [still] if still.exists() else []


def _normalize_single_snapshots(directory: Path) -> None:
    """Keep manifest patterns valid when the exporter emits a one-frame still."""
    for state in ("before", "after"):
        still = directory / f"simulation_{state}.json"
        numbered = directory / f"simulation_{state}_000.json"
        if still.exists() and not numbered.exists():
            os.replace(still, numbered)


def _require_artifacts(
    report: Path,
    snapshots: Path,
    runtime_scene: Path,
    usd: Path,
    mocks: Path,
    run_id: str,
    frames: int,
) -> tuple[list[Path], list[Path]]:
    before = _snapshot_paths(snapshots, "before")
    after = _snapshot_paths(snapshots, "after")
    required = [
        report,
        runtime_scene / "main.usda",
        usd / "agents_before.usda",
        usd / "agents_after.usda",
        mocks / "health.json",
        mocks / "scenarios.json",
        mocks / "stream-config.json",
        mocks / "model-card.json",
        mocks / "runs" / f"{run_id}.json",
        mocks / "runs" / f"{run_id}.citizens.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if len(before) != frames:
        missing.append(f"{snapshots}/simulation_before snapshots ({len(before)}/{frames})")
    if len(after) != frames:
        missing.append(f"{snapshots}/simulation_after snapshots ({len(after)}/{frames})")
    if missing:
        raise PipelineError("pipeline did not create required artifacts:\n  " + "\n  ".join(missing))
    return before, after


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


class _CompatibilityTransaction:
    """Journal compatibility file replacements for rollback or commit."""

    def __init__(self) -> None:
        self._changes: list[tuple[Path, Path | None]] = []

    def replace(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if destination.exists():
            backup = destination.with_name(
                f".{destination.name}.{uuid.uuid4().hex}.pipeline-backup"
            )
            os.replace(destination, backup)
        self._changes.append((destination, backup))
        _atomic_copy(source, destination)

    def delete(self, destination: Path) -> None:
        if not destination.exists():
            return
        backup = destination.with_name(
            f".{destination.name}.{uuid.uuid4().hex}.pipeline-backup"
        )
        os.replace(destination, backup)
        self._changes.append((destination, backup))

    def rollback(self) -> list[str]:
        errors = []
        for destination, backup in reversed(self._changes):
            try:
                if destination.exists():
                    destination.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, destination)
            except OSError as exc:
                errors.append(f"{destination}: {exc}")
        return errors

    def commit(self) -> list[str]:
        warnings = []
        for _destination, backup in self._changes:
            if backup is not None and backup.exists():
                try:
                    backup.unlink()
                except OSError as exc:
                    warnings.append(
                        f"compatibility backup cleanup failed for {backup}: {exc}"
                    )
        return warnings


def _publish_snapshots(
    source_dir: Path,
    destination_dir: Path,
    transaction: _CompatibilityTransaction,
) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    source_names: set[str] = set()
    for state in ("before", "after"):
        sources = _snapshot_paths(source_dir, state)
        for source in sources:
            source_names.add(source.name)
            transaction.replace(source, destination_dir / source.name)
        if sources:
            compatibility_name = f"simulation_{state}.json"
            source_names.add(compatibility_name)
            transaction.replace(
                sources[0], destination_dir / compatibility_name
            )

    for state in ("before", "after"):
        candidates = list(
            destination_dir.glob(f"simulation_{state}_[0-9][0-9][0-9].json")
        )
        candidates.append(destination_dir / f"simulation_{state}.json")
        for stale in candidates:
            if stale.exists() and stale.name not in source_names:
                transaction.delete(stale)


def _animation_timestamps(frames: int, duration: float) -> list[float]:
    """Match integration/export_snapshot.py frame timestamps."""
    if frames <= 1:
        return [0.0]
    step = duration / frames
    return [round(index * step, 4) for index in range(frames)]


def _stamp_demo_timeline(
    demo_stage: Path,
    *,
    timestamps: list[float],
    fps: float = 24.0,
) -> None:
    """Load phase9's shared stamp helper without importing the full instancer."""
    helper = ROOT / "phase9" / "stamp_demo_timeline.py"
    spec = importlib.util.spec_from_file_location(
        "_phase9_stamp_demo_timeline", helper
    )
    if spec is None or spec.loader is None:
        raise PipelineError(f"could not load demo timeline helper: {helper}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.stamp_demo_timeline(demo_stage, timestamps=timestamps, fps=fps)


def _publish_demo_timeline(
    root: Path,
    frames: int,
    duration: float,
    transaction: _CompatibilityTransaction,
) -> None:
    """Stamp Kit's demo root after agent layers are published."""
    demo_stage = root / "phase9" / "scene" / "main.usda"
    if not demo_stage.exists():
        return
    stamped = demo_stage.with_name(
        f".{demo_stage.stem}.{uuid.uuid4().hex}.pipeline-stamped.usda"
    )
    try:
        shutil.copy2(demo_stage, stamped)
        try:
            _stamp_demo_timeline(
                stamped,
                timestamps=_animation_timestamps(frames, duration),
            )
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(
                f"demo stage timeline stamp failed: {exc}"
            ) from exc
        transaction.replace(stamped, demo_stage)
    finally:
        if stamped.exists():
            stamped.unlink()


def _publish_compatibility(
    root: Path,
    report: Path,
    snapshots: Path,
    usd: Path,
    mocks: Path,
    transaction: _CompatibilityTransaction,
    *,
    frames: int,
    duration: float,
) -> None:
    transaction.replace(
        report, root / "Simulation" / "urbantwin_demo_output.json"
    )
    _publish_snapshots(snapshots, root / "data", transaction)
    generated = root / "phase9" / "scene" / "generated"
    transaction.replace(
        usd / "agents_before.usda", generated / "agents_before.usda"
    )
    transaction.replace(
        usd / "agents_after.usda", generated / "agents_after.usda"
    )
    transaction.replace(usd / "agents_before.usda", generated / "agents.usda")
    _publish_demo_timeline(root, frames, duration, transaction)
    for source in sorted(path for path in mocks.rglob("*") if path.is_file()):
        transaction.replace(
            source, root / "frontend" / "mocks" / source.relative_to(mocks)
        )


def _recover_stale_backup(final: Path, backup: Path) -> None:
    if not backup.exists():
        return
    if final.exists():
        shutil.rmtree(backup)
    else:
        os.replace(backup, final)


def _install_run(staging: Path, final: Path, backup: Path) -> bool:
    """Install staging while retaining the previous run backup."""
    moved_previous = False
    installed_staging = False
    try:
        if final.exists():
            os.replace(final, backup)
            moved_previous = True
        os.replace(staging, final)
        installed_staging = True
    except OSError as exc:
        rollback_errors = _restore_run(
            final, backup, moved_previous, installed_staging
        )
        detail = f"could not promote completed run: {exc}"
        if rollback_errors:
            detail += "\nrollback errors:\n  " + "\n  ".join(rollback_errors)
        raise PipelineError(detail) from exc
    return moved_previous


def _restore_run(
    final: Path,
    backup: Path,
    had_previous: bool,
    installed_staging: bool,
) -> list[str]:
    errors = []
    if installed_staging:
        try:
            if final.exists():
                shutil.rmtree(final)
        except OSError as exc:
            errors.append(f"remove failed promoted run {final}: {exc}")
    if had_previous and backup.exists():
        try:
            os.replace(backup, final)
        except OSError as exc:
            errors.append(f"restore previous run {final}: {exc}")
    return errors


def _promote_and_publish(
    root: Path,
    staging: Path,
    final: Path,
    backup: Path,
    publish: bool,
    *,
    frames: int,
    duration: float,
) -> list[str]:
    warnings = []
    had_previous = _install_run(staging, final, backup)
    if publish:
        transaction = _CompatibilityTransaction()
        try:
            _publish_compatibility(
                root,
                final / "simulation_report.json",
                final / "snapshots",
                final / "usd",
                final / "frontend-mocks",
                transaction,
                frames=frames,
                duration=duration,
            )
        except (OSError, PipelineError) as exc:
            rollback_errors = transaction.rollback()
            rollback_errors.extend(
                _restore_run(final, backup, had_previous, True)
            )
            detail = f"compatibility publication failed: {exc}"
            if rollback_errors:
                detail += "\nrollback errors:\n  " + "\n  ".join(rollback_errors)
            raise PipelineError(detail) from exc
        warnings.extend(transaction.commit())

    if backup.exists():
        try:
            shutil.rmtree(backup)
        except OSError as exc:
            warnings.append(f"run backup cleanup failed: {exc}")
    return warnings


def _cleanup_staging(staging: Path) -> str | None:
    try:
        if staging.exists():
            shutil.rmtree(staging)
    except OSError as exc:
        return f"could not clean staging directory {staging}: {exc}"
    return None


def run_pipeline(config: PipelineConfig) -> dict:
    _validate_config(config)
    root = Path(config.root).resolve()
    runs = root / "data" / "runs"
    staging = runs / f"{config.run_id}.staging"
    final = runs / config.run_id
    backup = runs / f"{config.run_id}.backup"
    try:
        runs.mkdir(parents=True, exist_ok=True)
        _recover_stale_backup(final, backup)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
    except OSError as exc:
        raise PipelineError(f"pipeline setup failed: {exc}") from exc

    report = staging / "simulation_report.json"
    snapshots = staging / "snapshots"
    runtime = staging / "runtime"
    runtime_scene = runtime / "scene"
    usd = staging / "usd"
    mocks = staging / "frontend-mocks"
    python = sys.executable
    stages: list[StageResult] = []

    try:
        simulation_command = [
            python,
            root / "Simulation" / "main.py",
            root / config.citizens,
            root / config.city,
            "--temperature", config.temperature,
            "--humidity", config.humidity,
            "--rainfall", config.rainfall,
            "--population", config.population,
            "--output", report,
        ]
        for recommendation_id in config.selected_recommendation_ids:
            simulation_command.extend(["--intervention-id", recommendation_id])
        stages.append(
            _record_stage(
                "simulation",
                simulation_command,
                root,
            )
        )
        stages.append(
            _record_stage(
                "snapshot_export",
                [
                    python,
                    root / "integration" / "export_snapshot.py",
                    "--report",
                    report,
                    "--city",
                    root / config.city,
                    "--state",
                    "both",
                    "--run-id",
                    config.run_id,
                    "--out-dir",
                    snapshots,
                    "--frames",
                    config.frames,
                    "--duration",
                    config.duration,
                ],
                root,
            )
        )
        _normalize_single_snapshots(snapshots)
        before = _snapshot_paths(snapshots, "before")
        after = _snapshot_paths(snapshots, "after")
        if not before or not after:
            raise PipelineError("snapshot export did not create both before and after states")

        stages.append(
            _record_stage(
                "runtime_stage",
                [
                    python,
                    root / "integration" / "load_snapshot.py",
                    before[0],
                    "--out",
                    runtime_scene,
                ],
                root,
            )
        )
        for state, frames in (("before", before), ("after", after)):
            stages.append(
                _record_stage(
                    f"agents_{state}",
                    [
                        python,
                        root / "phase9" / "agents_instancer.py",
                        *frames,
                        "--behavior-report",
                        report,
                        "--behavior-state",
                        state,
                        "--out",
                        usd / f"agents_{state}.usda",
                        "--demo-stage",
                        runtime_scene / "main.usda",
                    ],
                    root,
                )
            )
        stages.append(
            _record_stage(
                "frontend_fixtures",
                [
                    python,
                    root / "integration" / "export_api_mocks.py",
                    "--report",
                    report,
                    "--run-id",
                    config.run_id,
                    "--out",
                    mocks,
                ],
                root,
            )
        )

        before, after = _require_artifacts(
            report,
            snapshots,
            runtime_scene,
            usd,
            mocks,
            config.run_id,
            config.frames,
        )
        stages.append(
            _record_stage(
                "validation",
                [
                    python,
                    root / "integration" / "validate_integration.py",
                    "--report",
                    report,
                    "--snapshot",
                    before[0],
                    "--after",
                    after[0],
                    "--stage",
                    runtime_scene / "main.usda",
                    "--registry",
                    root / "phase2" / "scene" / "edge_registry.json",
                ],
                root,
            )
        )
        _require_artifacts(
            report,
            snapshots,
            runtime_scene,
            usd,
            mocks,
            config.run_id,
            config.frames,
        )

        manifest = {
            "schema_version": 1,
            "run_id": config.run_id,
            "status": "complete",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scenario": {
                "temperature": config.temperature,
                "humidity": config.humidity,
                "rainfall": config.rainfall,
                "population": config.population,
            },
            "animation": {
                "frames": config.frames,
                "duration_seconds": config.duration,
            },
            "artifacts": {
                "simulation_report": "simulation_report.json",
                "before_snapshots": "snapshots/simulation_before_*.json",
                "after_snapshots": "snapshots/simulation_after_*.json",
                "before_agents_usd": "usd/agents_before.usda",
                "after_agents_usd": "usd/agents_after.usda",
                "runtime_stage": "runtime/scene/main.usda",
                "frontend_fixtures": "frontend-mocks",
            },
            "stages": stages,
        }
        manifest_tmp = staging / "manifest.json.tmp"
        manifest_path = staging / "manifest.json"
        manifest_tmp.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(manifest_tmp, manifest_path)

        finalization_warnings = _promote_and_publish(
            root,
            staging,
            final,
            backup,
            config.publish,
            frames=config.frames,
            duration=config.duration,
        )
        if finalization_warnings:
            manifest["warnings"] = finalization_warnings
            final_manifest = final / "manifest.json"
            final_manifest_tmp = final / "manifest.json.tmp"
            try:
                final_manifest_tmp.write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
                )
                os.replace(final_manifest_tmp, final_manifest)
            except OSError as exc:
                print(
                    f"warning: could not record finalization warnings: {exc}; "
                    "run remains complete; unrecorded warnings: "
                    + "; ".join(finalization_warnings),
                    file=sys.stderr,
                )
                try:
                    manifest = json.loads(
                        final_manifest.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as reload_exc:
                    print(
                        "warning: could not reload the persisted complete "
                        f"manifest: {reload_exc}",
                        file=sys.stderr,
                    )
                    manifest.pop("warnings", None)
            finally:
                if final_manifest_tmp.exists():
                    try:
                        final_manifest_tmp.unlink()
                    except OSError:
                        pass
        return manifest
    except PipelineError as exc:
        cleanup_error = _cleanup_staging(staging)
        if cleanup_error:
            raise PipelineError(f"{exc}\n{cleanup_error}") from exc
        raise
    except OSError as exc:
        cleanup_error = _cleanup_staging(staging)
        detail = f"pipeline filesystem operation failed: {exc}"
        if cleanup_error:
            detail += f"\n{cleanup_error}"
        raise PipelineError(detail) from exc


def parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="urbantwin-local-001")
    parser.add_argument(
        "--citizens",
        type=Path,
        default=Path("Simulation/citizens_survey_city_osm.json"),
    )
    parser.add_argument("--city", type=Path, default=Path("Simulation/city_osm.json"))
    parser.add_argument("--temperature", type=float, default=40)
    parser.add_argument("--humidity", type=float, default=80)
    parser.add_argument("--rainfall", type=float, default=80)
    parser.add_argument("--population", type=int, default=100000)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument(
        "--intervention-id",
        action="append",
        dest="selected_recommendation_ids",
        default=[],
        choices=(
            "increase_shade", "improve_drainage",
            "alternative_pedestrian_routes", "no_major_intervention",
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_cli(argv)
    config = PipelineConfig(
        root=ROOT,
        run_id=args.run_id,
        citizens=args.citizens,
        city=args.city,
        temperature=args.temperature,
        humidity=args.humidity,
        rainfall=args.rainfall,
        population=args.population,
        frames=args.frames,
        duration=args.duration,
        publish=not args.no_publish,
        selected_recommendation_ids=tuple(args.selected_recommendation_ids),
    )
    try:
        run_pipeline(config)
    except PipelineError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(ROOT / "data" / "runs" / config.run_id / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
