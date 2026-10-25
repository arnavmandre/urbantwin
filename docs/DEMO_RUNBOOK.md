# Argus AI — local demo runbook

**Repo:** `C:\Users\arnav\Argus` on **`main`** (Phases 11–17 streaming path are merged).

## What you are showing

- **Live backend:** Python API runs `Simulation/main.py` on real OSM city data for each scenario submit.
- **Optional stream:** NVIDIA Kit App Streaming (WebRTC) when the signaling port is up and Chromium connects.
- **Dashboard:** Next.js proxies to the API when `URBANTWIN_API_BASE` is set (`mode: "live"`). UI brand: **Argus AI**.

Metrics, comfort indices, and advisor text are **heuristic prototypes** — not medical, meteorological, or engineering models. Citizen parameters are **survey-calibrated** (41 participants) but scenario factors are confounded; home/destination placement is a heuristic.

**Mock vs live:** Without `URBANTWIN_API_BASE`, the frontend replays recorded fixtures and health reports `mode: "mock"`. Set the env var when starting `npm run dev` for live mode.

View commands are allow-listed by the API; **Kit must be running and the browser WebRTC session connected** for camera/overlay changes to apply.

## Prerequisites (once)

| Requirement | Notes |
| --- | --- |
| **RTX GPU** | Kit App Streaming host; laptop iGPU-only will not stream. |
| **Chrome or Edge** | Required for WebRTC. Firefox/Safari are not verified. |
| **Python** | On PATH; same env as Phase 11 (`pxr` for full pipeline). |
| **Node.js** | Once: `cd frontend; npm ci` |
| **Kit App Template** | Branch `phase13-streaming-kit`; bat at `C:\Users\arnav\omniverse\kit-app-template\launch_urbantwin_streaming.bat`. |

## Ports

| Service | Port | Check |
| --- | --- | --- |
| Argus API | **8000** | `Invoke-RestMethod http://127.0.0.1:8000/api/health` |
| Next.js dashboard | **3001** (3000 is taken by Kit's Python debugger) | Open **http://127.0.0.1:3001/** |
| Kit WebRTC signaling | **49100** | `GET /api/stream/config` → `status: "available"` when host is up |
| Kit media (DIRECT) | **47998** | Advertised in stream config; firewall must allow local TCP |

## Launch (recommended)

Open three terminals. Do **not** rely on `Start-UrbanTwin.bat` for demos.

```powershell
# 1) API
cd C:\Users\arnav\Argus
python -m api --host 127.0.0.1 --port 8000

# 2) Kit (separate shell — headless, no Omniverse editor window)
cd C:\Users\arnav\omniverse\kit-app-template
.\launch_urbantwin_streaming.bat

# 3) Frontend (separate shell)
cd C:\Users\arnav\Argus\frontend
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
npm run dev -- -p 3001   # 3001: Kit's Python debugger takes 127.0.0.1:3000
```

Then open:

```text
http://127.0.0.1:3001/
```

**Important:** streaming Kit uses `--no-window`. Success = Kit log shows `app ready` / `RTX ready` (no stream-server errors), `/api/stream/config` → `available`, viewport chip **Live** in Chrome/Edge.

Wait until health responds:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
# expect mode: "live"
Invoke-RestMethod http://127.0.0.1:8000/api/stream/config
# expect status: "available" when Kit signaling is open, else honest "offline"
```

Open **http://127.0.0.1:3001/** in Chrome or Edge.

## Expected UI states

1. **Header / health:** Live backend (`mode: "live"`), not mock fixtures.
2. **Stream panel:** `available` + video when Kit is up and WebRTC connected; otherwise offline placeholder (still honest).
3. **After Run:** Metrics and before/after summaries populate from a real simulator run (may take 1–3 minutes for default animation; smoke uses 3 frames).
4. **Viewport footer:** Camera / overlay / before-after controls; delivery to Kit only when stream is connected (Phase 15).
5. **Explain results** (optional): Deterministic template unless `URBANTWIN_LLM_URL` is set (Phase 16).

## Automated smoke test

With API on port 8000:

```powershell
cd C:\Users\arnav\Argus
python tools\demo_smoke.py
```

Checks: health, stream config, short live run, view allow-list, optional explain.

## Recovery

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Health never returns | API not started or port 8000 taken | Check the API terminal; free port 8000 or restart `python -m api` |
| `mode: "mock"` in UI | `URBANTWIN_API_BASE` unset | Restart frontend with `$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"` |
| Stream stays offline | Kit not running or signaling closed | Launch `launch_urbantwin_streaming.bat`; wait 30–60s; recheck `/api/stream/config` |
| Stream config `available` but no video | Non-Chromium browser or WebRTC blocked | Use Chrome/Edge; allow localhost media |
| Run stuck `running` | Pipeline error | `GET /api/runs/{id}` for status; see API window log |
| View changes not in Kit | No WebRTC session | Connect stream first; relaunch Kit if API started after Kit |
| `Failed to start the primary stream server` | Another Kit still holds port 49100 | Close all Kit consoles / `taskkill /F /IM kit.exe`; reopen browser tabs; restart Kit only once |
| `npm run dev -- -p 3001` EADDRINUSE | Port 3001 busy | Close the other dev server, or run `.\tools\demo_launch.ps1 -Force` |

## Related docs

- Design: `docs/superpowers/specs/2026-09-20-phase17-demo-hardening-design.md`
- API: `docs/PHASE12_LOCAL_API.md`
- WebRTC: `docs/PHASE14_BROWSER_WEBRTC.md`
- View commands: `docs/PHASE15_KIT_COMMAND_DELIVERY.md`
- Explain: `docs/PHASE16_CONSTRAINED_LLM.md`
- Kit host: `docs/PHASE13_STREAMING_KIT.md`
