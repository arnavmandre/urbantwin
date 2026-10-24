"""Agent 37 hosted Hermes agent as Argus' advisor LLM.

Agent 37 (agent37.com) runs the agent on its own machine; we only send it text. Contract, from
https://www.agent37.com/docs/agents-api/agent-quickstart.md and .../urls.md:

    POST {AGENT37_AGENT_URL}/v1/responses   header X-Agent37-Key: sk_live_...
    body {"input": "...", "session_id": "<optional, continues a conversation>"}
    -> {"status": "completed" | "failed", "output_text": "...", "session_id": "...", "error": ...}

Configure with AGENT37_API_KEY and AGENT37_AGENT_URL (the repo-root .env is loaded by api/env.py).
The key is never logged or echoed in errors.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# Free-tier agents sleep when idle and wake on a request; give the wake-up room.
TIMEOUT_S = 150
MODEL_LABEL = "agent37:hermes"


def configured() -> bool:
    return bool(os.environ.get("AGENT37_API_KEY", "").strip() and os.environ.get("AGENT37_AGENT_URL", "").strip())


def send(text: str, session_id: str | None = None, *, timeout: float = TIMEOUT_S) -> tuple[str, str | None]:
    """One turn. Returns (output_text, session_id). Raises RuntimeError on any failure."""
    base = os.environ.get("AGENT37_AGENT_URL", "").strip().rstrip("/")
    key = os.environ.get("AGENT37_API_KEY", "").strip()
    if not (base and key):
        raise RuntimeError("Agent 37 is not configured (AGENT37_API_KEY, AGENT37_AGENT_URL).")
    body = {"input": text}
    if session_id:
        body["session_id"] = session_id
    request = urllib.request.Request(
        f"{base}/v1/responses", method="POST", data=json.dumps(body).encode("utf-8"),
        headers={"X-Agent37-Key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Agent 37 returned HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Agent 37 unreachable: {exc}") from None
    except ValueError:
        raise RuntimeError("Agent 37 returned a non-JSON response.") from None
    # a failed turn can come back as HTTP 200 with status "failed"
    if data.get("status") != "completed":
        raise RuntimeError(f"Agent 37 turn {data.get('status')!r}: {data.get('error')}")
    return str(data.get("output_text") or ""), data.get("session_id")


def extract_json(text: str) -> object:
    """The JSON object in a model reply, tolerating ```json fences or prose around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("reply contains no JSON object")
    return json.loads(text[start:end + 1])
