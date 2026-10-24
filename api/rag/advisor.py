"""Grounded intervention ranking with strict validation and fallback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

from api import agent37
from api.explain import build_explanation_payload
from api.rag.retrieval import KnowledgeRetriever

ALLOWED_RECOMMENDATION_IDS = frozenset({
    "increase_shade", "improve_drainage",
    "alternative_pedestrian_routes", "no_major_intervention",
})
MODEL_NAME = "openai/gpt-oss-120b"
ADVISOR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_problem": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "moderate", "high", "unknown"],
                },
                "target_id": {"type": ["string", "null"]},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["category", "severity", "target_id", "evidence"],
            "additionalProperties": False,
        },
        "recommendations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "knowledge_id": {"type": "string"},
                    "argus_recommendation_id": {
                        "type": "string",
                        "enum": sorted(ALLOWED_RECOMMENDATION_IDS),
                    },
                    "intervention": {"type": "string"},
                    "reason": {"type": "string"},
                    "target_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tradeoffs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "testable": {"type": "boolean"},
                },
                "required": [
                    "rank", "knowledge_id", "argus_recommendation_id",
                    "intervention", "reason", "target_metrics", "tradeoffs",
                    "testable",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["primary_problem", "recommendations"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = """You are the Argus AI urban-planning decision-support advisor.
Use simulation numbers only from simulator_evidence and intervention knowledge only
from retrieved_knowledge. Do not invent metrics, locations, evidence, effectiveness,
cost, ROI, or post-intervention outcomes. Only use allowed_recommendation_ids when
testable is true. Rank candidates for simulator testing; do not claim they work.
Return one JSON object only, with primary_problem and recommendations."""

_CACHE: dict[str, dict] = {}


def build_retrieval_query(payload: dict) -> str:
    scenario = payload.get("scenario") or {}
    metrics = payload.get("before_metrics") or {}
    fragments = [
        f"temperature {scenario.get('temperature')} heat exposure heat stress",
        f"rainfall {scenario.get('rainfall')} rain flooding drainage rain impact",
        f"population {scenario.get('population')} crowding congestion pedestrian route",
        str(payload.get("advisor_summary") or ""),
        "problem zones " + " ".join(payload.get("problem_zones") or []),
        "metrics " + " ".join(f"{key} {value}" for key, value in metrics.items()),
    ]
    return ". ".join(fragments)


def advise_run(
    report: dict,
    *,
    root: Path,
    top_k: int = 5,
    llm_callable: Callable[[dict], object] | None = None,
    retriever: KnowledgeRetriever | None = None,
) -> dict:
    payload = build_explanation_payload(report)
    deterministic = _deterministic_fallback(report, "RAG is disabled or unavailable.")
    knowledge_path = Path(root) / "data" / "urban_interventions.json"
    try:
        retriever = retriever or KnowledgeRetriever(knowledge_path)
        retrieved = retriever.retrieve(build_retrieval_query(payload), top_k=top_k)
        deterministic_ids = {
            item.get("id")
            for item in payload.get("recommendations") or []
            if isinstance(item, dict)
        }
        if deterministic_ids - {"no_major_intervention"}:
            retrieved = [
                item for item in retrieved
                if item["argus_recommendation_id"] != "no_major_intervention"
            ]
        if not retrieved:
            return _deterministic_fallback(report, "The knowledge base returned no records.")
    except Exception as exc:  # noqa: BLE001 - availability must never break demo
        return _deterministic_fallback(report, f"Knowledge retrieval failed: {exc}")

    model_label = MODEL_NAME
    if llm_callable is None:
        llm_callable, model_label = _default_llm()
        if llm_callable is None:
            deterministic["retrieved_knowledge"] = retrieved
            deterministic["retrieval_backend"] = retriever.backend
            deterministic["unavailable_reason"] = (
                "No advisor LLM is configured (set AGENT37_API_KEY and AGENT37_AGENT_URL).")
            return deterministic

    request = {
        "simulator_evidence": payload,
        "retrieved_knowledge": retrieved,
        "allowed_recommendation_ids": sorted(ALLOWED_RECOMMENDATION_IDS),
        "limitations": [
            "The simulator is authoritative for all before/after values.",
            "Metrics are heuristic prototype scores, not engineering predictions.",
            "NEEDS_SOURCE records are contextual leads, not verified evidence.",
        ],
    }
    cache_key = hashlib.sha256(json.dumps({
        "request": request, "knowledge_hash": retriever.knowledge_hash,
        "model": model_label,
    }, sort_keys=True).encode()).hexdigest()
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])

    error = ""
    for attempt in range(2):
        try:
            call_payload = dict(request)
            if attempt:
                call_payload["correction"] = f"Previous response was invalid: {error}. Return corrected JSON only."
            candidate = _normalize_candidate(_coerce_json(llm_callable(call_payload)))
            validated = validate_advisor_response(candidate, retrieved, payload)
            result = {
                "source": "rag_llm", "advisor_mode": "rag_llm",
                "model": model_label, "fallback_used": False,
                "retrieval_backend": retriever.backend,
                "knowledge_hash": retriever.knowledge_hash,
                "primary_problem": validated["primary_problem"],
                "recommendations": validated["recommendations"],
                "retrieved_knowledge": retrieved,
            }
            _CACHE[cache_key] = result
            return dict(result)
        except Exception as exc:  # noqa: BLE001 - retry then safe fallback
            error = str(exc)
    fallback = _deterministic_fallback(report, f"RAG response rejected: {error}")
    fallback["retrieved_knowledge"] = retrieved
    fallback["retrieval_backend"] = retriever.backend
    return fallback


def validate_advisor_response(candidate: object, retrieved: list[dict], payload: dict) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("response must be an object")
    primary = candidate.get("primary_problem")
    recommendations = candidate.get("recommendations")
    if not isinstance(primary, dict) or not isinstance(recommendations, list):
        raise ValueError("primary_problem and recommendations are required")
    known = {item["knowledge_id"]: item for item in retrieved}
    valid_targets = set(payload.get("problem_zones") or [])
    valid_targets.update(item.get("id") for item in payload.get("problem_buildings") or [])
    valid_targets.update(item.get("id") for item in payload.get("problem_routes") or [])
    target = primary.get("target_id")
    if target not in (None, "") and target not in valid_targets:
        raise ValueError(f"unknown target_id {target!r}")
    output = []
    for rank, rec in enumerate(recommendations, start=1):
        if not isinstance(rec, dict):
            raise ValueError("each recommendation must be an object")
        knowledge_id = rec.get("knowledge_id")
        if knowledge_id not in known:
            raise ValueError(f"knowledge_id {knowledge_id!r} was not retrieved")
        action = rec.get("argus_recommendation_id")
        expected = known[knowledge_id]["argus_recommendation_id"]
        if action != expected or action not in ALLOWED_RECOMMENDATION_IDS:
            raise ValueError(f"unsupported recommendation {action!r}")
        if rec.get("testable") is not True:
            raise ValueError("returned recommendations must be executable and testable")
        output.append({
            "rank": rank, "knowledge_id": knowledge_id,
            "argus_recommendation_id": action,
            "intervention": known[knowledge_id]["intervention"],
            "reason": (
                f"Retrieved record {knowledge_id} maps the reported scenario to "
                f"the executable Argus action {action}. Argus must re-simulate "
                "the action to measure any modeled change."
            ),
            "target_metrics": known[knowledge_id]["target_metrics"],
            "tradeoffs": known[knowledge_id]["tradeoffs"], "testable": True,
            "source": known[knowledge_id]["source"],
        })
    if not output:
        raise ValueError("at least one recommendation is required")
    actions = {item["argus_recommendation_id"] for item in output}
    if "no_major_intervention" in actions and len(actions) > 1:
        raise ValueError("no_major_intervention cannot accompany another action")
    severity = primary.get("severity")
    if severity not in {"low", "moderate", "high", "unknown"}:
        severity = "unknown"
    first_record = known[output[0]["knowledge_id"]]
    metrics = payload.get("before_metrics") or {}
    grounded_evidence = [
        f"before_metrics.{key}={metrics[key]}"
        for key in first_record["target_metrics"]
        if key in metrics
    ]
    if target:
        grounded_evidence.append(f"target_id={target}")
    return {
        "primary_problem": {
            "category": first_record["problem_category"],
            "severity": severity,
            "target_id": target or None,
            "evidence": grounded_evidence,
        },
        "recommendations": output,
    }


def _deterministic_fallback(report: dict, reason: str) -> dict:
    advisor = report.get("advisor") if isinstance(report.get("advisor"), dict) else {}
    return {
        "source": "deterministic", "advisor_mode": "deterministic_fallback",
        "fallback_used": True, "unavailable_reason": reason,
        "recommendations": [
            {"rank": index + 1, "argus_recommendation_id": action, "testable": True}
            for index, action in enumerate(advisor.get("recommendations") or [])
            if action in ALLOWED_RECOMMENDATION_IDS
        ],
        "retrieved_knowledge": [],
    }


def _coerce_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _normalize_candidate(value: object) -> object:
    """Normalize the earlier JSON-object shape before applying strict validation."""
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    primary = normalized.get("primary_problem")
    if isinstance(primary, str):
        normalized["primary_problem"] = {
            "category": primary,
            "severity": "unknown",
            "target_id": None,
            "evidence": [],
        }
    recommendations = normalized.get("recommendations")
    if isinstance(recommendations, list):
        rows = []
        for raw in recommendations:
            if not isinstance(raw, dict):
                rows.append(raw)
                continue
            row = dict(raw)
            if "knowledge_id" not in row and isinstance(row.get("evidence_id"), str):
                row["knowledge_id"] = row["evidence_id"]
            if "argus_recommendation_id" not in row and isinstance(row.get("id"), str):
                row["argus_recommendation_id"] = row["id"]
            row.setdefault("testable", True)
            rows.append(row)
        normalized["recommendations"] = rows
    return normalized


def _default_llm() -> tuple[Callable[[dict], object] | None, str]:
    """Agent 37 is the advisor LLM; Groq gpt-oss-120b remains only as a fallback when Agent 37 is unset."""
    if agent37.configured():
        return _agent37_call, agent37.MODEL_LABEL
    if os.environ.get("GROQ_API_KEY", "").strip():
        return _groq_call, MODEL_NAME
    return None, ""


def _agent37_call(payload: dict) -> object:
    # Agent 37 has no response_format, so the schema goes in the prompt and validation stays strict.
    prompt = (f"{SYSTEM_PROMPT}\nThe JSON object must match this JSON Schema:\n"
              f"{json.dumps(ADVISOR_RESPONSE_SCHEMA)}\n\nRequest:\n{json.dumps(payload, ensure_ascii=False)}")
    text, _ = agent37.send(prompt)  # fresh session per ranking: no history leaks between runs
    return agent37.extract_json(text)


def _groq_call(payload: dict) -> object:
    try:
        from groq import Groq  # type: ignore
    except ImportError as exc:
        raise RuntimeError("groq package is not installed") from exc
    completion = Groq().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.3, max_completion_tokens=2048, top_p=1,
        reasoning_effort="medium", stream=False,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "argus_advisor_response",
                "strict": True,
                "schema": ADVISOR_RESPONSE_SCHEMA,
            },
        },
    )
    return completion.choices[0].message.content
