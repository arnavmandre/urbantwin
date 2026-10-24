"""TCP probe for local Kit WebRTC signaling and stream config envelopes."""
from __future__ import annotations

import os
import secrets
import socket

from integration.cities import CITIES, DEFAULT_CITY, city_profile

DEFAULT_STREAM_HOST = "127.0.0.1"
DEFAULT_SIGNAL_PORT = 49100
# Local NVIDIA web-viewer-sample uses mediaPort: null so the client discovers
# the Kit media port. Only set URBANTWIN_STREAM_MEDIA_PORT to override.
DEFAULT_MEDIA_PORT = None


def stream_city() -> str:
    city = os.environ.get("URBANTWIN_STREAM_CITY", DEFAULT_CITY).strip().lower()
    return city if city in CITIES else DEFAULT_CITY


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_int_optional(name: str):
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else None


def probe_stream_endpoint(
    host=None,
    signal_port=None,
    media_port=...,
    timeout_s=0.35,
) -> dict:
    host = (
        host
        or os.environ.get("URBANTWIN_STREAM_HOST", DEFAULT_STREAM_HOST).strip()
        or DEFAULT_STREAM_HOST
    )
    signal_port = (
        signal_port
        if signal_port is not None
        else _env_int("URBANTWIN_STREAM_SIGNAL_PORT", DEFAULT_SIGNAL_PORT)
    )
    if media_port is ...:
        media_port = _env_int_optional("URBANTWIN_STREAM_MEDIA_PORT")
    if _env_bool("URBANTWIN_STREAM_FORCE"):
        return {
            "available": True,
            "host": host,
            "signal_port": signal_port,
            "media_port": media_port,
            "reason": None,
        }
    try:
        with socket.create_connection((host, signal_port), timeout=timeout_s):
            pass
        return {
            "available": True,
            "host": host,
            "signal_port": signal_port,
            "media_port": media_port,
            "reason": None,
        }
    except OSError:
        return {
            "available": False,
            "host": host,
            "signal_port": signal_port,
            "media_port": media_port,
            "reason": (
                "Kit signaling port is not accepting connections. "
                "Launch urbantwin_streaming.kit first (leave that window open)."
            ),
        }


def available_stream_config(checked_utc, probe: dict, *, source="live") -> dict:
    host = probe["host"]
    signal_port = probe["signal_port"]
    media_port = probe.get("media_port")
    return {
        "status": "available",
        "source": source,
        "checked_utc": checked_utc,
        "signaling_url": f"http://{host}:{signal_port}",
        "signaling_host": host,
        "signaling_port": signal_port,
        "media_host": host,
        "media_port": media_port,
        "ice_servers": [],
        # Local Kit has no session manager; token is for our API only.
        "session_token": secrets.token_urlsafe(24),
        # Which city Kit was launched on (tools/demo_launch.ps1 -City sets this); the probe cannot ask Kit.
        "city": stream_city(),
        "stage": city_profile(stream_city())["stage"],
        "desktop_fallback": ".\\tools\\demo_launch.ps1 -Inspector",
        "references": [
            "https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html",
            "https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/108.0/docs/streaming.html",
        ],
    }
