"""Live-mode API response envelopes built from simulator reports."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.stream_probe import (  # noqa: E402
    available_stream_config,
    probe_stream_endpoint,
)
from integration.export_api_mocks import (  # noqa: E402
    health_fixture,
    live_run_warnings,
    model_card_fixture,
    run_summary,
    scenarios_fixture,
    stream_config_fixture,
)

# Shorter status notes when there is no completed / executed report yet.
# Do not claim "just-executed simulator run" for these.
_LIVE_STATUS_WARNINGS = {
    "queued": [
        "Live run: queued. The simulator has not executed for this request yet; "
        "any metrics below are placeholders until the run completes.",
    ],
    "running": [
        "Live run: running. The simulator is in progress; any metrics below are "
        "placeholders until the run completes.",
    ],
    "cancelled": [
        "Live run: cancelled. No complete simulator report was published for "
        "this request.",
    ],
    "failed": [
        "Live run: failed before a simulator report was available for this "
        "request.",
    ],
}


def live_warnings_for(status: str, *, has_report: bool = False, city=None) -> list[str]:
    """Full live integrity list only when a report was actually produced.

    Complete runs always qualify. Failed runs qualify only when the worker
    attached a real simulator report (``has_report=True``). Queued, running,
    cancelled, and failed-without-report use short status notes instead.
    """
    if status == "complete" or (status == "failed" and has_report):
        return live_run_warnings(city)
    notes = _LIVE_STATUS_WARNINGS.get(status)
    if notes is not None:
        return list(notes)
    return [
        f"Live run: status is {status!r}. Full live-result warnings apply only "
        "after a simulator report exists."
    ]


def live_run_summary(
    report,
    created_utc,
    run_id,
    *,
    status="complete",
    warnings=None,
    has_report=None,
    error=None,
    city=None,
) -> dict:
    """Shape a simulator report as a live RunSummary envelope."""
    if warnings is None:
        if has_report is None:
            has_report = status == "complete"
        warnings = live_warnings_for(status, has_report=bool(has_report), city=city)
    return run_summary(
        report,
        created_utc,
        run_id,
        source="live",
        status=status,
        warnings=warnings,
        error=error,
        city=city,
    )


def live_citizen_page(report, run_id, state, limit, offset) -> dict:
    """Paginated citizen page for a live run (serves the full simulated set)."""
    if state not in ("before", "after"):
        raise ValueError(f"state must be 'before' or 'after', got {state!r}")
    citizens = report[state]["citizens"]
    total_in_run = len(citizens)
    start = max(0, int(offset))
    size = max(0, int(limit))
    items = citizens[start : start + size]
    return {
        "run_id": run_id,
        "state": state,
        "source": "live",
        "limit": size,
        "offset": start,
        "total": total_in_run,
        "total_in_run": total_in_run,
        "items": items,
        "notes": [
            f"Live run serves {total_in_run} simulated citizens paginated.",
            "Citizens are survey-calibrated synthetic people, not real individuals.",
        ],
    }


def live_health(checked_utc) -> dict:
    health = health_fixture(checked_utc, source="live")
    groq_ready = bool(os.environ.get("GROQ_API_KEY", "").strip()) and (
        importlib.util.find_spec("groq") is not None
    )
    health["capabilities"]["llm_advisor"] = groq_ready
    health["notes"] = list(health.get("notes") or []) + [
        (
            "Groq RAG advisor is configured; the /advise response still reports "
            "whether a specific request used the LLM or deterministic fallback."
            if groq_ready
            else "Groq RAG advisor is not configured in this API process; /advise "
            "will use deterministic fallback."
        )
    ]
    probe = probe_stream_endpoint()
    if probe["available"]:
        health["omniverse_stream"] = "online"
        health["capabilities"]["omniverse_streaming"] = True
        health["notes"] = list(health.get("notes") or []) + [
            "Local Kit signaling port is accepting connections; browser WebRTC "
            "still requires the Phase 14 client.",
        ]
    return health


def live_scenarios() -> dict:
    return scenarios_fixture(source="live")


def live_stream_config(checked_utc) -> dict:
    probe = probe_stream_endpoint()
    if probe["available"]:
        return available_stream_config(checked_utc, probe, source="live")
    cfg = stream_config_fixture(checked_utc, source="live")
    cfg["reason"] = probe["reason"] or cfg.get("reason")
    cfg["signaling_host"] = None
    cfg["signaling_port"] = None
    cfg["media_host"] = None
    cfg["media_port"] = None
    return cfg


def live_model_card(card, exported_utc) -> dict:
    return model_card_fixture(card, exported_utc, source="live")
