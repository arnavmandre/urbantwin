"""Request validation for the UrbanTwin Python HTTP API."""
from __future__ import annotations

from integration.cities import CITIES, DEFAULT_CITY

CONSTRAINTS = {
    "temperature": (-10, 45),
    "humidity": (20, 90),
    "rainfall": (0, 100),
    "population": (25000, 100000),
}

VIEW_STATES = frozenset({"before", "after"})
VIEW_CAMERAS = frozenset({"Overview", "Street", "ProblemZone", "Aerial"})
VIEW_OVERLAYS = frozenset({"behavior", "congestion", "shade", "none"})
VIEW_PLAYBACK = frozenset({"play", "pause", "restart"})

DEFAULT_ANIMATION_FRAMES = 60
DEFAULT_ANIMATION_DURATION_SECONDS = 60
ALLOWED_RECOMMENDATION_IDS = frozenset({
    "increase_shade",
    "improve_drainage",
    "alternative_pedestrian_routes",
    "no_major_intervention",
})


def _validation_error(message: str, fields: dict | None = None) -> dict:
    error = {"code": "validation_failed", "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def _as_number(value, *, integer: bool = False):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if integer and not value.is_integer():
            return None
        return int(value) if integer else value
    return None


def validate_run_request(body: dict) -> tuple[dict | None, dict | None]:
    """Normalize a POST /api/runs body. Returns (normalized, None) or (None, error)."""
    if not isinstance(body, dict):
        return None, _validation_error("Request body must be a JSON object.")

    fields: dict[str, str] = {}
    normalized: dict = {}

    for name, (lo, hi) in CONSTRAINTS.items():
        if name not in body:
            fields[name] = "required"
            continue
        want_int = name == "population"
        value = _as_number(body[name], integer=want_int)
        if value is None:
            fields[name] = "must be a number" if not want_int else "must be an integer"
            continue
        if value < lo or value > hi:
            fields[name] = f"must be between {lo} and {hi}"
            continue
        normalized[name] = value

    if "apply_recommended_interventions" not in body:
        fields["apply_recommended_interventions"] = "required"
    else:
        flag = body["apply_recommended_interventions"]
        if not isinstance(flag, bool):
            fields["apply_recommended_interventions"] = "must be a boolean"
        else:
            normalized["apply_recommended_interventions"] = flag

    selected = body.get("selected_recommendation_ids")
    if selected is not None:
        if (
            not isinstance(selected, list)
            or not selected
            or any(not isinstance(value, str) for value in selected)
        ):
            fields["selected_recommendation_ids"] = (
                "must be a non-empty array of recommendation ids"
            )
        elif len(selected) != len(set(selected)):
            fields["selected_recommendation_ids"] = "must not contain duplicates"
        elif any(value not in ALLOWED_RECOMMENDATION_IDS for value in selected):
            fields["selected_recommendation_ids"] = "contains an unsupported action"
        elif "no_major_intervention" in selected and len(selected) > 1:
            fields["selected_recommendation_ids"] = (
                "no_major_intervention cannot be combined with another action"
            )
        else:
            normalized["selected_recommendation_ids"] = selected
        if body.get("apply_recommended_interventions") is not True:
            fields["selected_recommendation_ids"] = (
                "requires apply_recommended_interventions=true"
            )

    if "animation_frames" in body and body["animation_frames"] is not None:
        frames = _as_number(body["animation_frames"], integer=True)
        if frames is None:
            fields["animation_frames"] = "must be an integer"
        elif frames < 1:
            fields["animation_frames"] = "must be >= 1"
        else:
            normalized["animation_frames"] = frames
    else:
        normalized["animation_frames"] = DEFAULT_ANIMATION_FRAMES

    if "animation_duration_seconds" in body and body["animation_duration_seconds"] is not None:
        duration = _as_number(body["animation_duration_seconds"], integer=False)
        if duration is None:
            fields["animation_duration_seconds"] = "must be a number"
        elif duration <= 0:
            fields["animation_duration_seconds"] = "must be > 0"
        else:
            normalized["animation_duration_seconds"] = (
                int(duration) if isinstance(duration, float) and duration.is_integer()
                else duration
            )
    else:
        normalized["animation_duration_seconds"] = DEFAULT_ANIMATION_DURATION_SECONDS

    city = body.get("city", DEFAULT_CITY)
    if city not in CITIES:
        fields["city"] = f"must be one of {sorted(CITIES)}"
    else:
        normalized["city"] = city

    if fields:
        return None, _validation_error("One or more fields failed validation.", fields)
    return normalized, None


def validate_view_command(body: dict) -> tuple[dict | None, dict | None]:
    """Normalize a POST /api/runs/:id/view body. Allow-listed values only."""
    if not isinstance(body, dict):
        return None, _validation_error("Request body must be a JSON object.")

    fields: dict[str, str] = {}
    state = body.get("state")
    camera = body.get("camera")
    overlay = body.get("overlay")
    playback = body.get("playback", "play")

    if state not in VIEW_STATES:
        fields["state"] = f"must be one of {sorted(VIEW_STATES)}"
    if camera not in VIEW_CAMERAS:
        fields["camera"] = f"must be one of {sorted(VIEW_CAMERAS)}"
    if overlay not in VIEW_OVERLAYS:
        fields["overlay"] = f"must be one of {sorted(VIEW_OVERLAYS)}"
    if playback not in VIEW_PLAYBACK:
        fields["playback"] = f"must be one of {sorted(VIEW_PLAYBACK)}"

    if fields:
        return None, _validation_error("One or more fields failed validation.", fields)
    return {
        "state": state,
        "camera": camera,
        "overlay": overlay,
        "playback": playback,
    }, None
