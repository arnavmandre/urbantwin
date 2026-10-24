"""Conversational advisor: the planner chats with the Agent 37 LLM about a simulator run.

Grounding: the first turn of a session carries the advisor rules plus the run's real facts
(build_explanation_payload); later turns send only the planner's message, because the agent keeps the
conversation via session_id. When the planner applies a proposal and a new run completes, that run's facts
are injected into the same conversation so the advisor can compare the two.

Proposals: the agent may end a reply with one line `PROPOSE: {"proposals": [...]}`. Only actions the
simulator can execute survive validation; the dashboard turns them into "Apply & re-run" cards that use the
existing selected_recommendation_ids path. The LLM never produces metrics: numbers come from the simulator.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from api import agent37
from api.explain import build_explanation_payload
from api.rag.advisor import ALLOWED_RECOMMENDATION_IDS

MAX_MESSAGE_CHARS = 2000

ACTIONS = {
    "increase_shade": "add shade/canopy along the pedestrian corridors (simulator raises route and zone shade)",
    "improve_drainage": "improve drainage in flood-prone zones (simulator raises drainage)",
    "alternative_pedestrian_routes": "open alternative pedestrian routes to spread crowding",
    "no_major_intervention": "conditions are acceptable; change nothing",
}

RULES = f"""You are the Argus AI planning advisor, chatting with an urban planner about simulator runs of a
human-centric city digital twin. Rules:
- Use numbers only from the RUN FACTS you are given; never invent metrics, places, costs or outcomes.
  Metrics are heuristic prototype scores (0-100; mean_travel_minutes is minutes), not engineering predictions.
- The simulator can test only these actions: {json.dumps(ACTIONS)}.
- Always answer in normal text first. To recommend testing actions, add after that answer exactly one line:
  PROPOSE: {{"proposals": [{{"action": "<id>", "reason": "<one sentence>"}}]}}
  Use only the ids above; no_major_intervention cannot be combined with another action.
- If the planner suggests something the simulator cannot test (e.g. new buildings, traffic signals), say it
  cannot be simulated here, and offer the closest testable action only if it genuinely fits.
- An "after" arm means the same citizens re-simulated with the applied intervention.
- When comparing runs, report the effect honestly: if an action barely moved the metrics, say so plainly.
- Be concise (under 150 words), plain text, no tables."""

_PROPOSE = re.compile(r"^\s*PROPOSE:\s*(\{.*\})\s*$", re.MULTILINE)
_SESSIONS: dict[str, str] = {}  # agent session_id -> run_id the agent last saw facts for


def run_facts(report: dict, run_id: str, city: str | None) -> str:
    payload = build_explanation_payload(report)
    payload.pop("warnings_and_limitations", None)  # long boilerplate; rules already state the limits
    payload["applied_intervention"] = report.get("intervention") or {}
    payload["city"] = city or "london"
    payload["run_id"] = run_id
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_reply(text: str) -> tuple[str, list[dict]]:
    """Split the agent's reply into visible text and validated proposals."""
    proposals: list[dict] = []
    match = None
    for match in _PROPOSE.finditer(text):
        pass  # keep the last PROPOSE line
    if match is None:
        return text.strip(), proposals
    visible = (text[:match.start()] + text[match.end():]).strip()
    try:
        raw = json.loads(match.group(1)).get("proposals") or []
    except (ValueError, AttributeError):
        return visible, proposals
    seen = set()
    for item in raw if isinstance(raw, list) else []:
        action = item.get("action") if isinstance(item, dict) else None
        if action in ALLOWED_RECOMMENDATION_IDS and action not in seen:
            seen.add(action)
            proposals.append({"action": action, "reason": str(item.get("reason") or "")[:300]})
    if "no_major_intervention" in seen and len(seen) > 1:
        proposals = [p for p in proposals if p["action"] != "no_major_intervention"]
    return visible, proposals


def chat(report: dict, run_id: str, message: str, session_id: str | None = None, *, city: str | None = None,
         send: Callable[[str, str | None], tuple[str, str | None]] | None = None) -> dict:
    send = send or (agent37.send if agent37.configured() else None)
    if send is None:
        return _fallback(report, "The AI advisor is not configured (AGENT37_API_KEY, AGENT37_AGENT_URL).")

    if not session_id or session_id not in _SESSIONS:
        text = f"{RULES}\n\nRUN FACTS (run {run_id}):\n{run_facts(report, run_id, city)}\n\nPLANNER: {message}"
        session_id = None  # an unknown id (e.g. after an API restart) starts a fresh, grounded conversation
    elif _SESSIONS[session_id] != run_id:
        text = (f"NEW RUN FACTS (run {run_id}, the planner re-ran the simulator; compare with the previous run "
                f"where useful):\n{run_facts(report, run_id, city)}\n\nPLANNER: {message}")
    else:
        text = f"PLANNER: {message}"

    try:
        reply, new_session = send(text, session_id)
    except Exception as exc:  # noqa: BLE001 - the advisor must never break the dashboard
        return _fallback(report, str(exc))
    if new_session:
        _SESSIONS[new_session] = run_id
    visible, proposals = parse_reply(reply)
    # a reply that is only a PROPOSE line still has its reasoning in the proposals
    visible = visible or " ".join(p["reason"] for p in proposals if p["reason"]) or "(no reply text)"
    return {"source": "agent37", "model": agent37.MODEL_LABEL, "reply": visible,
            "proposals": proposals, "session_id": new_session or session_id}


def _fallback(report: dict, reason: str) -> dict:
    advisor = report.get("advisor") if isinstance(report.get("advisor"), dict) else {}
    actions = [a for a in advisor.get("recommendations") or [] if a in ALLOWED_RECOMMENDATION_IDS]
    summary = str(advisor.get("summary") or "").strip()
    reply = ("The AI advisor is unavailable right now, so this is the simulator's own rule-based advice."
             + (f" {summary}" if summary else ""))
    return {"source": "deterministic", "reply": reply, "session_id": None, "unavailable_reason": reason,
            "proposals": [{"action": a, "reason": "Recommended by the simulator's threshold advisor."}
                          for a in actions]}
