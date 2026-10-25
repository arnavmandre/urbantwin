"""Apply allow-listed urbantwin.view_command messages to the streamed viewport.

Message path, every hop of which is confirmed in Kit's log:

    browser AppStreamer.sendMessage
      -> WebRTC data channel
      -> omni.kit.livestream.messaging   (parses the JSON envelope)
      -> carb event `urbantwin.view_command`
      -> this extension

The handler is handed a `carb.eventdispatcher.Event`, NOT a dict. The payload
sits on `event.payload`, already flattened to {state, camera, overlay, id,
sender_id}. An earlier version treated the argument as the payload itself and
discarded every command as "non-dict", so the dashboard reported `delivered`
while Kit did nothing.
"""

from __future__ import annotations

import asyncio

import carb
import omni.ext
import omni.kit.app
import omni.timeline
import omni.usd
from carb.eventdispatcher import get_eventdispatcher
from pxr import Sdf, Usd, UsdGeom

EVENT_TYPE = "urbantwin.view_command"
SELF_TEST_KEY = "/exts/urbantwin.view_commands/selfTest"

ALLOWED_CAMERAS = frozenset({"Overview", "Street", "ProblemZone", "Aerial", "Corridor"})
ALLOWED_OVERLAYS = frozenset({"behavior", "congestion", "shade", "flood", "none"})
ALLOWED_STATES = frozenset({"before", "after"})
ALLOWED_PLAYBACK = frozenset({"play", "pause", "restart"})

CAMERA_ROOT = "/World/Cameras"
AGENTS_PATH = "/World/Agents"

# Before/After maps onto the Phase 8 `demoState` variant set that is already
# composed on /World. "after" adds the proposed intervention geometry; per the
# Phase 8 README this is a stress-versus-proposal comparison, NOT a measured
# improvement, and it must not be described as one.
STATE_VARIANT = {"before": "Stressed", "after": "Intervention"}


class ViewCommandsExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        self._subscriptions = []
        self._self_test_task = None
        self._autoplay_task = asyncio.ensure_future(self._start_playback_when_ready())
        self._register_inbound_handler()

        if carb.settings.get_settings().get(SELF_TEST_KEY):
            self._self_test_task = asyncio.ensure_future(self._self_test())

    def on_shutdown(self) -> None:
        if self._self_test_task is not None and not self._self_test_task.done():
            self._self_test_task.cancel()
        if self._autoplay_task is not None and not self._autoplay_task.done():
            self._autoplay_task.cancel()
        omni.timeline.get_timeline_interface().stop()
        self._subscriptions.clear()

    # ------------------------------------------------------------------ inbound

    def _register_inbound_handler(self) -> None:
        try:
            import omni.kit.livestream.messaging as messaging

            if hasattr(messaging, "observe"):

                @messaging.observe(EVENT_TYPE)
                def _observed(event):  # noqa: ANN001 - carb Event
                    self._on_view_command(event)

                self._subscriptions.append(_observed)
                carb.log_info(
                    f"urbantwin.view_commands: listening via messaging.observe({EVENT_TYPE})"
                )
                return
        except ImportError:
            carb.log_warn(
                "urbantwin.view_commands: omni.kit.livestream.messaging not importable; "
                "falling back to the local event bus. Browser messages will NOT arrive."
            )

        omni.kit.app.register_event_alias(
            carb.events.type_from_string(EVENT_TYPE), EVENT_TYPE
        )
        self._subscriptions.append(
            get_eventdispatcher().observe_event(
                observer_name=f"ViewCommands:{EVENT_TYPE}",
                event_name=EVENT_TYPE,
                on_event=self._on_view_command,
            )
        )
        carb.log_info(f"urbantwin.view_commands: listening on event bus for {EVENT_TYPE}")

    def _on_view_command(self, event) -> None:  # noqa: ANN001 - carb Event
        self._on_view_command_payload(self._payload_dict(event))

    @staticmethod
    def _payload_dict(event) -> object:  # noqa: ANN001
        """Return the event payload as a plain dict (or the raw value if it cannot be)."""
        payload = getattr(event, "payload", event)
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "get_dict"):
            return payload.get_dict()
        try:
            return dict(payload)
        except (TypeError, ValueError):
            return payload

    def _on_view_command_payload(self, payload) -> None:  # noqa: ANN001
        if not isinstance(payload, dict):
            carb.log_warn(f"urbantwin.view_commands: ignored non-dict payload: {payload!r}")
            return

        state = payload.get("state")
        camera = payload.get("camera")
        overlay = payload.get("overlay")
        playback = payload.get("playback", "play")

        if state not in ALLOWED_STATES:
            carb.log_warn(f"urbantwin.view_commands: rejected state {state!r}")
            return
        if camera not in ALLOWED_CAMERAS:
            carb.log_warn(f"urbantwin.view_commands: rejected camera {camera!r}")
            return
        if overlay not in ALLOWED_OVERLAYS:
            carb.log_warn(f"urbantwin.view_commands: rejected overlay {overlay!r}")
            return
        if playback not in ALLOWED_PLAYBACK:
            carb.log_warn(f"urbantwin.view_commands: rejected playback {playback!r}")
            return

        carb.log_warn(
            f"urbantwin.view_commands: applying state={state} camera={camera} "
            f"overlay={overlay} playback={playback}"
        )
        # State first, then overlay: "shade" may force the Intervention canopy
        # after the before/after variant is applied.
        self._apply_camera(str(camera))
        self._apply_state(str(state))
        self._apply_overlay(str(overlay))
        self._apply_playback(str(playback))

    # ------------------------------------------------------------------ actions

    def _apply_camera(self, camera: str) -> None:
        from omni.kit.viewport.utility import get_active_viewport

        cam_path = f"{CAMERA_ROOT}/{camera}"
        stage = omni.usd.get_context().get_stage()
        if stage is None or not stage.GetPrimAtPath(cam_path).IsValid():
            carb.log_warn(f"urbantwin.view_commands: camera prim missing: {cam_path}")
            return

        viewport = get_active_viewport()
        if viewport is None:
            carb.log_warn("urbantwin.view_commands: no active viewport")
            return

        viewport.camera_path = Sdf.Path(cam_path)
        carb.log_warn(f"urbantwin.view_commands: viewport camera -> {cam_path}")

    def _apply_overlay(self, overlay: str) -> None:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return

        agents = stage.GetPrimAtPath(AGENTS_PATH)
        routes_root = stage.GetPrimAtPath("/World/Routes")
        interventions = stage.GetPrimAtPath("/World/Interventions")
        # Pune demo flood water (cities/pune/pune_view.py); only the "flood" overlay shows it.
        self._set_visible(stage.GetPrimAtPath("/World/Flood"), overlay == "flood")
        # Pune interventions exist only in the After arm, so they stay visible in every lens but "none".
        self._set_visible(interventions, overlay != "none")

        if overlay == "behavior":
            # Agents only: /World/Routes holds the Pune heat map, shown by "congestion" (the Heat lens).
            self._set_visible(agents, True)
            self._set_visible(routes_root, False)
        elif overlay == "congestion":
            # Route network only - crowding / heat on edges without agents.
            self._set_visible(agents, False)
            self._set_visible(routes_root, True)
        elif overlay == "shade":
            # Phase 8 ADD_SHADE cyan canopy (demoState Intervention). This is the
            # implemented shade proposal from Simulation/main.py increase_shade —
            # visual-only; not a measured climate improvement.
            self._set_variant(stage, "demoState", "Intervention")
            self._set_visible(interventions, True)
            self._set_visible(agents, True)
            self._set_visible(routes_root, False)
            carb.log_warn(
                "urbantwin.view_commands: shade overlay -> Intervention canopy visible"
            )
        elif overlay == "flood":
            # Illustrative uniform water depth from the run's flood-risk score, with the agents.
            self._set_visible(agents, True)
            self._set_visible(routes_root, False)
        elif overlay == "none":
            # Bare city: no agents, no route ribbons.
            self._set_visible(agents, False)
            self._set_visible(routes_root, False)

    def _apply_state(self, state: str) -> None:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        self._set_variant(stage, "demoState", STATE_VARIANT[state])

    def _apply_playback(self, playback: str) -> None:
        timeline = omni.timeline.get_timeline_interface()
        timeline.set_looping(True)
        if playback == "pause":
            timeline.pause()
            carb.log_warn("urbantwin.view_commands: animation paused")
            return
        if playback == "restart":
            timeline.stop()
            timeline.set_current_time(self._stage_start_seconds())
        timeline.play()
        carb.log_warn(f"urbantwin.view_commands: animation {playback}")

    @staticmethod
    def _stage_start_seconds() -> float:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return 0.0
        time_codes = stage.GetTimeCodesPerSecond() or 24.0
        return float(stage.GetStartTimeCode()) / float(time_codes)

    async def _start_playback_when_ready(self) -> None:
        app = omni.kit.app.get_app()
        for _ in range(900):
            await app.next_update_async()
            stage = omni.usd.get_context().get_stage()
            if stage is not None and stage.GetPrimAtPath(AGENTS_PATH).IsValid():
                self._apply_playback("restart")
                carb.log_warn("urbantwin.view_commands: stage ready; autoplay enabled")
                return
        carb.log_warn("urbantwin.view_commands: autoplay skipped; stage never became ready")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _set_visible(prim, visible: bool) -> None:  # noqa: ANN001
        if prim is None or not prim.IsValid():
            return
        imageable = UsdGeom.Imageable(prim)
        if not imageable:
            return
        imageable.MakeVisible() if visible else imageable.MakeInvisible()

    @staticmethod
    def _set_variant(stage, set_name: str, variant: str) -> None:  # noqa: ANN001
        world = stage.GetPrimAtPath("/World")
        if not world.IsValid():
            return
        vset = world.GetVariantSets().GetVariantSet(set_name)
        if not vset:
            carb.log_warn(f"urbantwin.view_commands: variant set {set_name!r} missing")
            return
        if variant not in vset.GetVariantNames():
            carb.log_warn(f"urbantwin.view_commands: {set_name} has no variant {variant!r}")
            return
        if vset.GetVariantSelection() == variant:
            return
        # Session layer: a live view choice must never dirty the authored stage.
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            vset.SetVariantSelection(variant)
        carb.log_warn(f"urbantwin.view_commands: {set_name} -> {variant}")

    # ------------------------------------------------------------------ self test

    async def _self_test(self) -> None:
        """Feed the handler the exact event the messaging extension would queue.

        Off by default. Enable with `--/exts/urbantwin.view_commands/selfTest=true`
        to check the Kit half of the pipeline without a browser. It does NOT
        exercise the WebRTC leg; the log line `Processing custom kit message`
        from omni.kit.livestream.webrtc.plugin proves that one.
        """
        app = omni.kit.app.get_app()
        for _ in range(900):  # wait for the stage autoload to finish
            await app.next_update_async()
            stage = omni.usd.get_context().get_stage()
            if stage is not None and stage.GetPrimAtPath(f"{CAMERA_ROOT}/Street").IsValid():
                break
        else:
            carb.log_warn("urbantwin.view_commands SELFTEST: stage never became ready")
            return

        for step in (
            {"state": "after", "camera": "Street", "overlay": "behavior"},
            {"state": "before", "camera": "Aerial", "overlay": "behavior"},
            {"state": "before", "camera": "NotACamera", "overlay": "behavior"},
        ):
            for _ in range(60):
                await app.next_update_async()
            carb.log_warn(f"urbantwin.view_commands SELFTEST: sending {step}")
            omni.kit.app.queue_event(EVENT_TYPE, {**step, "id": "selftest", "sender_id": 0})
