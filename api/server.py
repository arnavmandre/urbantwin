"""Stdlib ThreadingHTTPServer exposing the UrbanTwin frontend proxy contract."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from api.run_manager import ConflictError, RunManager
from api.shapes import (
    live_health,
    live_model_card,
    live_scenarios,
    live_stream_config,
)
from api.explain import build_explanation_payload, explain_run
from api.rag import advise_run
from api.validation import validate_run_request, validate_view_command

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_VIEW_UNDELIVERED_REASON = (
    "Allow-list passed. Delivery is via the connected WebRTC client "
    "(sendMessage urbantwin.view_command); the API does not push into Kit."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(root, manager=None, *, host="127.0.0.1", port=0):
    """Build a ThreadingHTTPServer.

    Defaults to an ephemeral port (``port=0``). Returns ``(server, manager)``.
    Callers start ``server.serve_forever()`` themselves (tests use a daemon
    thread; the CLI blocks).
    """
    root = Path(root)
    if manager is None:
        manager = RunManager(root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003 — stdlib signature
            # Quiet by default; operators still see start banner from the CLI.
            return

        def do_GET(self):  # noqa: N802
            self._dispatch("GET")

        def do_POST(self):  # noqa: N802
            self._dispatch("POST")

        def do_DELETE(self):  # noqa: N802
            self._dispatch("DELETE")

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query, keep_blank_values=False)

            try:
                if method == "GET" and path == "/api/health":
                    self._json(200, live_health(_utc_now()))
                    return
                if method == "GET" and path == "/api/scenarios":
                    self._json(200, live_scenarios())
                    return
                if method == "GET" and path == "/api/stream/config":
                    self._json(200, live_stream_config(_utc_now()))
                    return
                if method == "GET" and path == "/api/model-card":
                    self._handle_model_card()
                    return
                if method == "GET" and path == "/api/runs":
                    self._json(
                        200,
                        {
                            "source": "live",
                            "active_run_id": manager.list_active(),
                        },
                    )
                    return
                if method == "POST" and path == "/api/runs":
                    self._handle_create_run()
                    return

                run_match = re.fullmatch(r"/api/runs/([^/]+)", path)
                if run_match:
                    run_id = run_match.group(1)
                    if not _safe_run_id(run_id):
                        self._error(404, "not_found", f"Run {run_id!r} was not found.")
                        return
                    if method == "GET":
                        self._handle_get_run(run_id)
                        return
                    if method == "DELETE":
                        self._handle_cancel_run(run_id)
                        return

                citizens_match = re.fullmatch(r"/api/runs/([^/]+)/citizens", path)
                if method == "GET" and citizens_match:
                    run_id = citizens_match.group(1)
                    if not _safe_run_id(run_id):
                        self._error(404, "not_found", f"Run {run_id!r} was not found.")
                        return
                    self._handle_citizens(run_id, query)
                    return

                view_match = re.fullmatch(r"/api/runs/([^/]+)/view", path)
                if method == "POST" and view_match:
                    run_id = view_match.group(1)
                    if not _safe_run_id(run_id):
                        self._error(404, "not_found", f"Run {run_id!r} was not found.")
                        return
                    self._handle_view(run_id)
                    return

                explain_match = re.fullmatch(r"/api/runs/([^/]+)/explain", path)
                if method == "POST" and explain_match:
                    run_id = explain_match.group(1)
                    if not _safe_run_id(run_id):
                        self._error(404, "not_found", f"Run {run_id!r} was not found.")
                        return
                    self._handle_explain(run_id)
                    return

                advise_match = re.fullmatch(r"/api/runs/([^/]+)/advise", path)
                if method == "POST" and advise_match:
                    run_id = advise_match.group(1)
                    if not _safe_run_id(run_id):
                        self._error(404, "not_found", f"Run {run_id!r} was not found.")
                        return
                    self._handle_advise(run_id)
                    return

                self._error(404, "not_found", f"No route for {method} {path}.")
            except Exception as exc:  # noqa: BLE001 — last-resort JSON 500
                self._error(500, "internal_error", str(exc))

        def _handle_model_card(self) -> None:
            card_path = root / "phase10" / "models" / "model_card.json"
            card = json.loads(card_path.read_text(encoding="utf-8"))
            self._json(200, live_model_card(card, _utc_now()))

        def _handle_create_run(self) -> None:
            body, err = self._read_json_object()
            if err is not None:
                status, payload = err
                self._json(status, payload)
                return
            normalized, validation_error = validate_run_request(body)
            if validation_error is not None:
                self._json(422, validation_error)
                return
            try:
                created = manager.create_run(normalized)
            except ConflictError as exc:
                self._error(409, "conflict", str(exc))
                return
            self._json(202, created)

        def _handle_get_run(self, run_id: str) -> None:
            summary = manager.get_run(run_id)
            if summary is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            self._json(200, summary)

        def _handle_cancel_run(self, run_id: str) -> None:
            result = manager.cancel_run(run_id)
            if "error" in result:
                code = result["error"]["code"]
                status = 404 if code == "not_found" else 409
                self._json(status, result)
                return
            summary = manager.get_run(run_id)
            if summary is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            self._json(200, summary)

        def _handle_citizens(self, run_id: str, query: dict) -> None:
            if manager.get_run(run_id) is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            state = _first(query, "state", "before")
            try:
                limit = int(_first(query, "limit", "100"))
                offset = int(_first(query, "offset", "0"))
            except ValueError:
                self._error(
                    422,
                    "validation_failed",
                    "limit and offset must be integers.",
                )
                return
            if state not in ("before", "after"):
                self._error(
                    422,
                    "validation_failed",
                    "state must be 'before' or 'after'.",
                )
                return
            page = manager.get_citizens(run_id, state, limit, offset)
            if page is None:
                self._error(
                    404,
                    "not_found",
                    f"Citizens for run {run_id!r} are not available yet.",
                )
                return
            self._json(200, page)

        def _handle_explain(self, run_id: str) -> None:
            summary = manager.get_run(run_id)
            if summary is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            report = manager.get_report(run_id)
            if report is None:
                self._error(
                    409,
                    "conflict",
                    "Run has no simulator report yet; explain is available after "
                    "the run completes with a report.",
                )
                return
            payload = build_explanation_payload(report)
            envelope = explain_run(payload)
            self._json(200, {"run_id": run_id, **envelope})

        def _handle_advise(self, run_id: str) -> None:
            if manager.get_run(run_id) is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            report = manager.get_report(run_id)
            if report is None:
                self._error(
                    409,
                    "conflict",
                    "Run has no simulator report yet; advice is available after "
                    "the run completes with a report.",
                )
                return
            self._json(200, {"run_id": run_id, **advise_run(report, root=root)})

        def _handle_view(self, run_id: str) -> None:
            # "viewport" is a reserved id for camera/overlay commands before any
            # simulation run exists. Real run ids must still resolve.
            if run_id != "viewport" and manager.get_run(run_id) is None:
                self._error(404, "not_found", f"Run {run_id!r} was not found.")
                return
            body, err = self._read_json_object()
            if err is not None:
                status, payload = err
                self._json(status, payload)
                return
            command, validation_error = validate_view_command(body)
            if validation_error is not None:
                self._json(422, validation_error)
                return
            self._json(
                200,
                {
                    "accepted": True,
                    "delivered": False,
                    "delivery": "webrtc_client",
                    "reason": _VIEW_UNDELIVERED_REASON,
                    "command": command,
                },
            )

        def _read_json_object(self) -> tuple[dict | None, tuple[int, dict] | None]:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return None, (
                    400,
                    {
                        "error": {
                            "code": "bad_request",
                            "message": "Request body must be JSON.",
                        }
                    },
                )
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None, (
                    400,
                    {
                        "error": {
                            "code": "bad_request",
                            "message": "Request body must be valid JSON.",
                        }
                    },
                )
            if not isinstance(body, dict):
                return None, (
                    400,
                    {
                        "error": {
                            "code": "bad_request",
                            "message": "Request body must be a JSON object.",
                        }
                    },
                )
            return body, None

        def _json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, code: str, message: str) -> None:
            self._json(status, {"error": {"code": code, "message": message}})

    server = ThreadingHTTPServer((host, port), Handler)
    return server, manager


def _safe_run_id(run_id: str) -> bool:
    """Reject path traversal / odd ids before they touch the manager."""
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        return False
    return bool(_RUN_ID_RE.fullmatch(run_id))


def _first(query: dict, name: str, default: str) -> str:
    values = query.get(name)
    if not values:
        return default
    return values[0]


def serve(host: str, port: int, root: Path | None = None) -> None:
    """Bind to ``host:port`` and serve until interrupted."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    # Only the real server logs terminal run states; test apps stay side-effect free.
    manager = RunManager(root, events_path=root / "data" / "run_events.jsonl")
    server, _ = create_app(root, manager, host=host, port=port)
    print(f"UrbanTwin API listening on http://{host}:{port} (root={root})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.shutdown()
        server.server_close()
