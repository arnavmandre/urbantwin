"""Open /app/auto_load_usd after Kit startup, then present it as a clean stream.

`omni.kit.livestream.app` streams the ENTIRE application framebuffer, so without
this the browser shows Kit's whole editor: menu bar, Stage / Property / Console /
Content panels, the left toolbar, a transform gizmo and an FPS / GPU-memory
overlay, with the real 3D viewport squeezed into a small rectangle.

Set `--/exts/urbantwin.stage_autoload/cleanView=false` to keep the editor UI for
authoring.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import carb
import omni.ext
import omni.kit.app

CLEAN_VIEW_KEY = "/exts/urbantwin.stage_autoload/cleanView"
VIEWPORT_WINDOW = "Viewport"
# Docked windows we never hide. "DockSpace" is the root container that holds the
# viewport itself; hiding it would blank the whole stream.
KEEP_WINDOWS = {"DockSpace"}
# Editor furniture that is NOT docked (so the docked-only rule below would skip
# it) but still eats stream pixels. The floating left toolbar reserves a 48px
# strip, which is why the viewport used to start at x=48.
ALWAYS_HIDE = {"Main ToolBar"}

# The saved user config persists these PER WINDOW (Viewport/Viewport0), and a
# persisted value beats any default set in the .kit file, so they have to be
# forced at runtime. Viewport overlays react to these settings live.
VIEWPORT_OVERLAYS_OFF = (
    "hud/visible",
    "hud/renderFPS/visible",
    "hud/renderResolution/visible",
    "hud/renderProgress/visible",
    "hud/deviceMemory/visible",
    "hud/hostMemory/visible",
    "hud/processMemory/visible",
    "hud/cameraSpeed/visible",
    "hud/toastMessage/visible",
    "hud/metrics/assembler/visible",
    "guide/axis/visible",
    "guide/grid/visible",
    "guide/selection/visible",
    "guide/boundingBox/visible",
    # Camera and light icons drawn into the scene (the plane-shaped markers
    # around the city and the arrow at its centre).
    "scene/cameras/visible",
    "scene/lights/visible",
)

# Viewport layers to switch off, as (name, category). "Menubar" is the
# viewport's own toolbar (renderer, camera, display menus); in the stream it sat
# under the dashboard's floating controls. This is the same lookup the viewport
# window uses for /app/window/hideUi, which would also hide things we keep.
VIEWPORT_LAYERS_OFF = (("Menubar", "menubar"),)


class StageAutoloadExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        self._task = asyncio.ensure_future(self._open_stage())

    def on_shutdown(self) -> None:
        task = getattr(self, "_task", None)
        if task is not None and not task.done():
            task.cancel()

    async def _open_stage(self) -> None:
        # Import late: usd may not be importable during module load.
        import omni.usd

        app = omni.kit.app.get_app()
        for _ in range(60):
            await app.next_update_async()

        settings = carb.settings.get_settings()
        url = (settings.get_as_string("/app/auto_load_usd") or "").strip()
        if not url:
            carb.log_warn(
                "urbantwin.stage_autoload: /app/auto_load_usd is empty; "
                "leaving the default empty stage."
            )
        else:
            try:
                path = Path(url)
                if path.exists():
                    url = str(path.resolve())
            except OSError:
                pass

            carb.log_info(f"urbantwin.stage_autoload: opening {url}")
            await omni.usd.get_context().open_stage_async(url)

        clean = settings.get(CLEAN_VIEW_KEY)
        if clean is None or bool(clean):
            await self._present_clean_view(app)
        else:
            carb.log_info("urbantwin.stage_autoload: cleanView disabled; editor UI kept")

    async def _present_clean_view(self, app) -> None:
        """Strip the editor chrome. Repeated because layout finishes over several frames."""
        # Passes at increasing delays: the dock layout and late-created windows
        # (Content, Console) can appear after the stage opens, and would
        # otherwise be re-shown over a single early pass.
        for wait in (0, 30, 120, 300):
            for _ in range(wait):
                await app.next_update_async()
            self._hide_editor_ui(first=(wait == 0))

    def _hide_editor_ui(self, first: bool) -> None:
        import omni.ui as ui
        import omni.usd

        settings = carb.settings.get_settings()
        hidden, kept = [], []

        if first:
            inventory = [
                f"{getattr(h, 'title', '?')}(docked={getattr(h, 'docked', '?')},"
                f"visible={getattr(h, 'visible', '?')})"
                for h in ui.Workspace.get_windows()
            ]
            carb.log_warn(f"urbantwin.stage_autoload: window inventory: {inventory}")

        for handle in ui.Workspace.get_windows():
            title = getattr(handle, "title", "") or ""
            if not title:
                continue
            if title == VIEWPORT_WINDOW or title.startswith("Viewport") or title in KEEP_WINDOWS:
                kept.append(title)
                continue
            # Only real panels. Transient popups and tooltips are undocked and
            # manage their own lifetime, unless we know the window by name.
            if title not in ALWAYS_HIDE and not getattr(handle, "docked", False):
                continue
            if getattr(handle, "visible", False):
                try:
                    handle.visible = False
                    hidden.append(title)
                except Exception as exc:  # noqa: BLE001
                    carb.log_warn(f"urbantwin.stage_autoload: could not hide {title!r}: {exc}")

        try:
            from omni.kit.mainwindow import get_main_window

            main = get_main_window()
            menu_bar = main.get_main_menu_bar() if main else None
            status_bar = main.get_status_bar_frame() if main else None
            if menu_bar is not None and menu_bar.visible:
                menu_bar.visible = False
                hidden.append("<menu bar>")
            if status_bar is not None and status_bar.visible:
                status_bar.visible = False
                hidden.append("<status bar>")
        except ImportError:
            pass

        # Overlays: persisted per-window values would otherwise win.
        base = f"/persistent/app/viewport/{VIEWPORT_WINDOW}/Viewport0"
        for key in VIEWPORT_OVERLAYS_OFF:
            settings.set(f"{base}/{key}", False)
        settings.set("/app/viewport/forceHideFps", True)

        try:
            from omni.kit.viewport.utility import get_active_viewport_window

            vp_window = get_active_viewport_window()
            for name, category in VIEWPORT_LAYERS_OFF:
                layer = vp_window._find_viewport_layer(name, category) if vp_window else None  # noqa: SLF001
                if layer is not None and getattr(layer, "visible", False):
                    layer.visible = False
                    hidden.append(f"<viewport {name}>")
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"urbantwin.stage_autoload: could not hide viewport layers: {exc}")

        # No selection => no transform gizmo drawn at the origin.
        try:
            omni.usd.get_context().get_selection().clear_selected_prim_paths()
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"urbantwin.stage_autoload: could not clear selection: {exc}")

        vp = ui.Workspace.get_window(VIEWPORT_WINDOW)
        geometry = "viewport window not found"
        if vp is not None:
            geometry = (
                f"viewport {getattr(vp, 'width', '?')}x{getattr(vp, 'height', '?')} "
                f"at ({getattr(vp, 'position_x', '?')},{getattr(vp, 'position_y', '?')})"
            )
        carb.log_warn(
            f"urbantwin.stage_autoload: clean view pass -> hidden {len(hidden)} "
            f"{hidden}; {geometry}"
            + (f"; kept {kept}" if first else "")
        )
