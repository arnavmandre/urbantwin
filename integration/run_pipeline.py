"""Pune run entrypoint and shared transactional file helpers."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
RESERVED_RUN_ID_PATTERN = re.compile(r"(?:\.staging|\.backup)$|\.failed-", re.IGNORECASE)

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
    city_key: str = "pune"


class PipelineError(RuntimeError):
    pass


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


def _cleanup_staging(staging: Path) -> str | None:
    try:
        if staging.exists():
            shutil.rmtree(staging)
    except OSError as exc:
        return f"could not clean staging directory {staging}: {exc}"
    return None


def run_pipeline(config: PipelineConfig) -> dict:
    _validate_config(config)
    # The archived integration/cities.py script can occupy the name "cities".
    sys.path.insert(0, str(ROOT / "cities" / "pune"))
    from run_pune import run_pune
    return run_pune(
        config.run_id, temperature=config.temperature, humidity=config.humidity,
        rainfall=config.rainfall, population=config.population,
        interventions=config.selected_recommendation_ids, publish=config.publish, root=config.root,
    )


def parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="urbantwin-local-001")
    parser.add_argument(
        "--citizens",
        type=Path,
        default=Path("cities/pune/citizens_pune.json"),
    )
    parser.add_argument("--city", type=Path, default=Path("cities/pune/city_pune.json"))
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
