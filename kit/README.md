# Kit side of UrbanTwin AI (mirror)

The Omniverse Kit half of the streaming demo. It runs inside NVIDIA's `kit-app-template`
(`C:\Users\arnav\omniverse\kit-app-template`, branch `phase13-streaming-kit`); this folder is a copy so
the code the dashboard depends on is versioned with the rest of the project.

| Path | Goes to (in kit-app-template) | What it does |
|---|---|---|
| `extensions/urbantwin.view_commands/` | `source/extensions/` | Applies allow-listed browser commands: camera, Before/After (`demoState`), overlays `behavior`, `congestion` (Pune heat map, `/World/Routes`), `flood` (Pune demo water, `/World/Flood`), `shade`, `none`. Keeps `/World/Interventions` (Pune After arm) visible in every lens but `none`. |
| `extensions/urbantwin.stage_autoload/` | `source/extensions/` | Opens the stage from `/app/auto_load_usd` with a clean view (no editor chrome). |
| `apps/urbantwin_streaming.kit` | `source/apps/` | The headless streaming app. |
| `launch_urbantwin_streaming.bat`, `launch_urbantwin_inspector.bat` | repo root | Launchers; `URBANTWIN_STAGE` selects the stage (`tools/demo_launch.ps1 -City pune` sets it). |

After copying, relaunch Kit (`.\tools\demo_launch.ps1 -City pune -Force` from the Argus repo). The API
(`api/validation.py`) and dashboard (`frontend/lib/types.ts`) carry the same overlay allow-list; change all
three together.
