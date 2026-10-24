"""
Adapter: simulator report -> frontend mock API responses.

The web frontend in `frontend/` is built against the *proposed* HTTP API in
docs/FRONTEND_BACKEND_HANDOFF.md. That API does not exist yet: there is no
FastAPI service, no job queue and no run store. So that the dashboard is not
built against invented numbers, this script records the real simulator report
as fixtures shaped exactly like the proposed endpoints.

    Simulation/urbantwin_demo_output.json   (the real run, 0-100 metrics)
        -> THIS SCRIPT
        -> frontend/mocks/*.json            (recorded API responses)
        -> frontend/app/api/*               (route handlers serving them)

Every fixture is labelled `"source": "recorded_fixture"` and `/api/health`
reports `mode: "mock"` with every capability false, so the UI can never present
a recorded run as a live backend. When the Python API is built, point
`URBANTWIN_API_BASE` at it and the same route handlers proxy instead.

This script does NOT invent data. Metrics, advisor text, problem places and
behaviour counts are copied from the report; only the API envelope (run ids,
status, pagination, warnings) is added here.

Run:
    python integration/export_api_mocks.py
    python integration/export_api_mocks.py --report Simulation/urbantwin_demo_output.json
"""
from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from integration.cities import city_profile
except ModuleNotFoundError:  # run as a script: integration/ itself is sys.path[0]
    from cities import city_profile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_REPORT = ROOT / "Simulation" / "urbantwin_demo_output.json"
DEFAULT_MODEL_CARD = ROOT / "phase10" / "models" / "model_card.json"
DEFAULT_OUT = ROOT / "frontend" / "mocks"

RUN_ID = "run_20260919_001"
CITIZEN_SAMPLE = 200     # the report holds 1000; the fixture must stay small
AGENT_CAP = 500          # phase3 schema limit on rendered agents

BEHAVIORS = (
    "CONTINUE",
    "STRESSED",
    "SEEK_SHADE",
    "SEEK_SHELTER",
    "REROUTE",
    "AVOID_AREA",
)

# Shared integrity disclaimers (after the source-specific lead-in). The UI
# renders these; it must not write its own version of them.
_SHARED_RUN_WARNINGS = [
    "Environmental, comfort and intervention formulas are heuristic prototypes, "
    "not medical, meteorological, hydraulic or engineering models.",
    "Population is a population equivalent, not a headcount. At most 500 "
    "representative agents are rendered; 1,000 citizens are simulated.",
    "Citizen behavioural parameters are calibrated from 41 survey participants, "
    "but the survey scenarios confound temperature, crowding and shade. Home and "
    "destination placement is a heuristic, not survey data.",
    "Building heights: 223 of 623 meshes come from OSM data; the rest are "
    "inferred from building class or interpolated from neighbours.",
    "The animation interpolates positions between 60 fixed snapshots. It is not "
    "a time-evolving behavioural or collision simulation.",
]

RUN_WARNINGS = [
    "Recorded fixture: these numbers come from a real run of Simulation/main.py "
    "on city_osm.json, replayed by the mock API. No simulator process ran for "
    "this request.",
    *_SHARED_RUN_WARNINGS,
]

LIVE_RUN_WARNINGS = [
    "Live run: these numbers came from a just-executed simulator run of "
    "Simulation/main.py on city_osm.json for this request.",
    *_SHARED_RUN_WARNINGS,
]


def live_run_warnings(city=None) -> list[str]:
    """Integrity list for a completed live run. London keeps its exact wording; Pune states its own facts."""
    profile = city_profile(city)
    if profile["key"] == "london":
        return list(LIVE_RUN_WARNINGS)
    heuristic, _population, calibration = _SHARED_RUN_WARNINGS[:3]
    return [
        "Live run: these numbers came from a just-executed run of the same Simulation/main.py "
        f"on {profile['city_file']} for this request.",
        heuristic,
        "Population is a population equivalent, not a headcount. Every simulated citizen is animated "
        "as one walker on the 1 km model; the streamed 400 m view shows only those inside the square"
        + (f" (about {round(profile['walkers_visible_mean'])} at a time)." if profile.get("walkers_visible_mean")
           else "."),
        calibration,
        *profile["limitations"],
    ]

MOCK_HEALTH_NOTES = [
    "No Python HTTP API is running. Responses are recorded fixtures "
    "exported by integration/export_api_mocks.py.",
    "No streaming-enabled Kit application exists yet, so the viewport "
    "shows a recorded-stage placeholder rather than an RTX stream.",
    "The Random Forest models are trained but not wired into the "
    "simulator; the simulator still uses transparent rules.",
]

LIVE_HEALTH_NOTES = [
    "Python HTTP API is live. Runs execute Simulation/main.py through the "
    "Phase 11 local pipeline; the simulator remains the only authority for "
    "metrics and intervention effectiveness.",
    "No streaming-enabled Kit application exists yet, so Omniverse streaming "
    "stays offline; the viewport may still show a recorded-stage placeholder.",
    "The Random Forest models are trained but not wired into the "
    "simulator; the simulator still uses transparent rules.",
]


def behavior_counts(citizens):
    """All six behaviours, zero-filled. The legend shows the full palette."""
    seen = collections.Counter(c["behavior"] for c in citizens)
    unknown = set(seen) - set(BEHAVIORS)
    if unknown:
        raise SystemExit(f"report contains unknown behaviours: {sorted(unknown)}")
    return {b: seen.get(b, 0) for b in BEHAVIORS}


def state_summary(state):
    """SimulationState -> the frontend-sized slice of RunSummary."""
    return {
        "metrics": state["metrics"],
        "behavior_counts": behavior_counts(state["citizens"]),
        "problem_zones": state["problem_zones"],
        "problem_buildings": state["problem_buildings"],
        "problem_routes": state["problem_routes"],
        "citizen_count": len(state["citizens"]),
        "interventions": state["interventions"],
    }


def run_summary(
    report,
    generated_at,
    run_id,
    *,
    source="recorded_fixture",
    status="complete",
    warnings=None,
    error=None,
    city=None,
):
    before, after = report["before"], report["after"]
    control = report["control"]
    profile = city_profile(city)
    payload = {
        "run_id": run_id,
        "status": status,
        "source": source,
        "created_utc": generated_at,
        "scenario": report["scenario"],
        "before": state_summary(before),
        "advisor": report["advisor"],
        "intervention": report["intervention"],
        "after": state_summary(after),
        "delta": report["delta"],
        # The calm-weather control arm of the same report. Not a second run:
        # the simulator emits metrics and recommendations for it, nothing more.
        "control_reference": {
            "scenario": control["scenario"],
            "metrics": control["metrics"],
            "recommendations": control["recommendations"],
        },
        "city": {
            "key": profile["key"],
            "name": profile["name"],
            "source": "OpenStreetMap",
            "zones": len(before["zones"]),
            "simulation_buildings": len(before["buildings"]),
            "routes": len(before["routes"]),
            "visual_buildings": profile["visual_buildings"],
            "visual_trees": profile["visual_trees"],
            # London renders through the phase3 schema cap; Pune's 400 m view shows those inside the square
            "rendered_agent_cap": (AGENT_CAP if profile["key"] == "london"
                                   else profile.get("walkers_visible_max") or len(before["citizens"])),
            "limitations": profile["limitations"],
        },
        "artifacts": {
            "omniverse_stage": profile["stage"],
            "snapshot_pattern": profile["snapshot_pattern"],
        },
        "advisor_source": {
            "kind": "deterministic_rules",
            "label": "Deterministic threshold advisor (Simulation/main.py)",
            "detail": "Not an LLM. The simulator is the only authority for "
                      "metrics and intervention effectiveness.",
        },
        "warnings": list(RUN_WARNINGS if warnings is None else warnings),
    }
    if error is not None:
        payload["error"] = error
    return payload


def citizen_page_fixture(report, generated_at, run_id):
    """A bounded slice per state. The full 1000 records never reach the browser."""
    states = {}
    for name in ("before", "after"):
        citizens = report[name]["citizens"]
        states[name] = {
            "items": citizens[:CITIZEN_SAMPLE],
            "total_in_run": len(citizens),
            "included_in_fixture": min(CITIZEN_SAMPLE, len(citizens)),
        }
    return {
        "run_id": run_id,
        "source": "recorded_fixture",
        "created_utc": generated_at,
        "states": states,
    }


def scenarios_fixture(run_id=None, *, source="recorded_fixture"):
    """Ranges are the simulator's accepted inputs, per the handoff."""
    payload = {
        "source": source,
        "constraints": {
            "temperature": [-10, 45],
            "humidity": [20, 90],
            "rainfall": [0, 100],
            "population": [25000, 100000],
        },
        "units": {
            "temperature": "\u00b0C",
            "humidity": "%",
            "rainfall": "mm (prototype scale)",
            "population": "population equivalent",
        },
        "presets": [
            {
                "id": "baseline",
                "label": "Calm day",
                "description": "The control arm of the recorded report.",
                "temperature": 26,
                "humidity": 40,
                "rainfall": 5,
                "population": 30000,
            },
            # Single-hazard presets: each makes the advisor pick a different
            # supported intervention (drainage vs shade). Values only; no new model.
            {
                "id": "extreme_rainfall",
                "label": "Extreme rainfall",
                "description": "Cool, very wet day. Drives the rain and flood-risk proxy, not flood depth.",
                "temperature": 18,
                "humidity": 85,
                "rainfall": 90,
                "population": 60000,
            },
            {
                "id": "heat_stress",
                "label": "Heat stress",
                "description": "Dry, very hot day. Drives the heat-stress heuristic.",
                "temperature": 40,
                "humidity": 55,
                "rainfall": 0,
                "population": 80000,
            },
            {
                "id": "extreme_heat_rain",
                "label": "Extreme heat and rain",
                "description": "The recorded run with full before/after data.",
                "temperature": 40,
                "humidity": 80,
                "rainfall": 80,
                "population": 100000,
            },
        ],
    }
    if run_id is not None:
        payload["recorded_scenario"] = {
            "run_id": run_id,
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
        }
    return payload


def health_fixture(generated_at, *, source="recorded_fixture"):
    """Capability envelope. Fixture default stays fully mock; live flips API flags."""
    live = source == "live"
    return {
        "status": "ready" if live else "mock",
        "mode": "live" if live else "mock",
        "source": source,
        "checked_utc": generated_at,
        "simulator": live,
        "omniverse_stream": "offline",
        "model_card": True,
        "capabilities": {
            "http_api": live,
            "live_simulation": live,
            "omniverse_streaming": False,
            "llm_advisor": False,
            "random_forest_inference": False,
            "run_persistence": False,
        },
        "notes": list(LIVE_HEALTH_NOTES if live else MOCK_HEALTH_NOTES),
    }


def stream_config_fixture(generated_at, *, source="recorded_fixture"):
    return {
        "status": "offline",
        "source": source,
        "checked_utc": generated_at,
        "signaling_url": None,
        "signaling_host": None,
        "signaling_port": None,
        "media_host": None,
        "media_port": None,
        "ice_servers": [],
        "session_token": None,
        "stage": "phase9/scene/main.usda",
        "reason": "No urbantwin.streaming.kit application is configured. NVIDIA "
                  "Kit App Streaming has not been set up for this project yet.",
        "desktop_fallback": ".\\repo.bat launch -n urbantwin.kit",
        "references": [
            "https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html",
            "https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/108.0/docs/streaming.html",
        ],
    }


def model_card_fixture(card, generated_at, *, source="recorded_fixture"):
    """Sanitized subset: verdicts, holdout scores, limitations. No artifact hashes."""
    models = []
    for target, m in card["models"].items():
        entry = {
            "target": target,
            "kind": m["kind"],
            "trust_verdict": m["trust_verdict"],
            "labelled_rows": m["labelled_rows"],
            "final_holdout_rows": m["final_holdout_rows"],
            "final_holdout": m["final_holdout"],
            "final_holdout_baseline": m["final_holdout_baseline"],
            "beats_baseline": m["beats_baseline"],
            "beats_shuffled_labels": m["beats_shuffled_labels"],
        }
        if m.get("observed_classes"):
            entry["observed_classes"] = m["observed_classes"]
        models.append(entry)
    return {
        "source": source,
        "exported_utc": generated_at,
        "created_utc": card["created_utc"],
        "sklearn_version": card["sklearn_version"],
        "random_seed": card["random_seed"],
        "split_policy": card["split_policy"],
        "overall_verdict": card["overall_verdict"],
        "limitations": card["limitations"],
        "models": models,
        "wired_into_simulator": False,
        "survey": {
            "participants": 41,
            "scenario_response_rows": 164,
            "synthetic_citizens": 1000,
            "holdout_people": 5,
            "note": "A fresh generator fitted on 36 participants was checked "
                    "against five unseen people. This supports distributional "
                    "consistency, not prediction of an individual's behaviour.",
        },
    }


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    kb = path.stat().st_size / 1024
    print(f"  {path.relative_to(ROOT).as_posix():<52} {kb:7.1f} KB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model-card", type=Path, default=DEFAULT_MODEL_CARD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    card = json.loads(args.model_card.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"report     {args.report.relative_to(ROOT).as_posix()}")
    print(f"scenario   {report['scenario']}")
    print(f"citizens   {len(report['before']['citizens'])} simulated, "
          f"{CITIZEN_SAMPLE} recorded per state")
    print("writing:")

    out = args.out
    write(out / "health.json", health_fixture(generated_at))
    write(out / "scenarios.json", scenarios_fixture(args.run_id))
    write(out / "stream-config.json", stream_config_fixture(generated_at))
    write(out / "model-card.json", model_card_fixture(card, generated_at))
    write(out / "runs" / f"{args.run_id}.json",
          run_summary(report, generated_at, args.run_id))
    write(out / "runs" / f"{args.run_id}.citizens.json",
          citizen_page_fixture(report, generated_at, args.run_id))

    before = behavior_counts(report["before"]["citizens"])
    after = behavior_counts(report["after"]["citizens"])
    print(f"behaviour  before {before}")
    print(f"           after  {after}")
    print("done. The frontend serves these through frontend/app/api/*.")


if __name__ == "__main__":
    main()
