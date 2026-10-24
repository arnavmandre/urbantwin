# Phase 14 — Browser WebRTC (operator notes)

For the active Pune demo, launch from the Pune worktree with `tools/demo_launch.ps1 -City pune`; see `PUNE_CITY.md`.

Branch **`phase13-streaming-kit`** in Argus wires the Next.js dashboard to local
NVIDIA Kit App Streaming using **`@nvidia/ov-web-rtc@6.7.0`**. You do **not**
need to merge this branch to `main` to try it locally; run everything from this
worktree / branch on an RTX machine.

Phase 13 still owns the streaming **Kit host** (`urbantwin_streaming.kit`).
Phase 14 adds the **browser client**, API **TCP probe**, and stream config
envelope. **Phase 15** still owns allow-listed **view commands** delivered into
Kit (camera, overlays, scenario state). Today those commands are validated and
**discarded** — they do not reach the running stream.

## What this phase delivers

- `frontend/lib/viewer/kit-webrtc-adapter.ts` — `AppStreamer` with
  `StreamType.DIRECT`, hidden off-DOM `<video>` / `<audio>` elements, MediaStream
  handoff to `OmniverseViewer`.
- `frontend/lib/viewer/select.ts` — picks the NVIDIA adapter only when
  `GET /api/stream/config` reports `status: "available"` and a `signaling_url`.
  No client flag can force “live” streaming.
- `api/stream_probe.py` — probes the Kit signaling port; when open, returns host,
  ports, and a short-lived `session_token` (no secrets in `NEXT_PUBLIC_*`).
- npm package **`@nvidia/ov-web-rtc@6.7.0`** via scoped registry in
  `frontend/.npmrc`:
  `https://edge.urm.nvidia.com/artifactory/api/npm/omniverse-client-npm/`.

Streaming is **honest**: the UI shows RTX video only when (1) the API probe sees
Kit signaling and (2) the browser WebRTC session connects. Otherwise the
viewport stays offline / placeholder.

## Prerequisites

- RTX GPU host with Kit App Template on branch **`phase13-streaming-kit`**
  (see `docs/PHASE13_STREAMING_KIT.md`).
- Argus on branch **`phase13-streaming-kit`** (this worktree).
- **Chromium-based browser** (Chrome or Edge). Kit App Streaming WebRTC is not
  supported for operator verification in Firefox or Safari.
- Python with the same deps as Phase 12; frontend deps installed (`npm ci` in
  `frontend/`).

## Environment variables (API probe)

The Python API reads these when serving `GET /api/health` and
`GET /api/stream/config` (live mode only):

| Variable | Default | Purpose |
| --- | --- | --- |
| `URBANTWIN_STREAM_HOST` | `127.0.0.1` | Hostname for signaling and media endpoints returned to the browser. |
| `URBANTWIN_STREAM_SIGNAL_PORT` | `49100` | Kit WebRTC **signaling** port to probe and advertise. |
| `URBANTWIN_STREAM_MEDIA_PORT` | `47998` | Kit WebRTC **media** port advertised for `StreamType.DIRECT`. |
| `URBANTWIN_STREAM_FORCE` | (unset) | If `1`, `true`, `yes`, or `on`, skip the TCP probe and always report stream **available** (debug only; do not use in demos). |

If your Kit build uses different ports, set the signal/media variables to match
the streaming `.kit` / livestream extension defaults on your machine.

## Operator sequence (local DIRECT WebRTC)

Run from the **Argus repository root** (this worktree). Order matters: start Kit
before expecting `available` stream config.

### 1. Launch the streaming Kit host

From the Kit App Template checkout (not inside Argus):

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
.\launch_urbantwin_streaming.bat
```

Wait until the log shows livestream extensions and `app ready`. Details and
recovery: `docs/PHASE13_STREAMING_KIT.md`.

If your Argus clone is not at `C:\Users\arnav\Argus`, edit the `STAGE` path in
`launch_urbantwin_streaming.bat`.

### 2. Start the Phase 12 / 14 Python API

Second shell, Argus root:

```powershell
python -m api --host 127.0.0.1 --port 8000
```

### 3. Verify stream config (Kit must be up)

Third shell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/stream/config
```

**Kit running and probe succeeds** — expect roughly:

- `status`: `"available"`
- `source`: `"live"`
- `signaling_url`: e.g. `http://127.0.0.1:49100`
- `signaling_host`, `signaling_port`, `media_host`, `media_port` populated
- `session_token`: non-null short-lived token
- `stage`: `cities/pune/main_view_400m.usda`

**Kit not running** — expect:

- `status`: `"offline"`
- `signaling_url`: null
- `reason` mentioning signaling port not accepting connections

Optional health check (probe also flips stream capability when signaling is up):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
# omniverse_stream may be "online" when signaling port accepts TCP
```

### 4. Start the frontend against the live API

```powershell
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend
npm run dev
```

Open the dashboard in **Chrome or Edge**. With stream config `available`, the
viewport uses `kit-webrtc-adapter` and attempts DIRECT WebRTC to the host/ports
from the API. When connected, you should see the Pune stage
from the RTX host.

## Mock mode stays offline

With **`URBANTWIN_API_BASE` unset**, the Next.js app stays in **`mode: "mock"`**.
Recorded fixtures under `frontend/mocks/` drive health and stream config; stream
**always** reports offline and the **mock adapter** runs. No WebRTC connection is
attempted, even if Kit is running on the same machine.

Do not present mock mode as a live Omniverse stream.

## View commands (Phase 15 — not delivered yet)

The dashboard may POST allow-listed view commands to `/api/runs/{id}/view`. The
API validates them but **does not deliver** them to Kit over a message channel.
Operators should treat camera / overlay / state commands as **non-functional**
for the stream. Phase 15 adds Kit delivery — see
`docs/PHASE15_KIT_COMMAND_DELIVERY.md`.

## Reference client (optional)

NVIDIA’s [web-viewer-sample](https://github.com/NVIDIA-Omniverse/web-viewer-sample)
remains a useful **host-only** check without the Argus dashboard. Phase 14’s
path is the integrated `@nvidia/ov-web-rtc` adapter in this repo.

## Recovery

| Symptom | Check |
| --- | --- |
| Stream config `offline` | Kit launched with `launch_urbantwin_streaming.bat`; firewall; ports match env vars |
| Config `available` but viewport offline | Chromium browser; `@nvidia/ov-web-rtc` installed (`npm ci`); console for WebRTC errors |
| Mock dashboard never streams | Expected — set `URBANTWIN_API_BASE` and use live API |
| Wrong stage | `STAGE` in launch bat; `auto_load_usd` path |
| Forced “available” without Kit | Unset `URBANTWIN_STREAM_FORCE` for honest demos |

## Smoke evidence (2026-09-20)

Automated checks on branch `phase13-streaming-kit` (worktree):

| Check | Result |
| --- | --- |
| `python -m unittest api.test_stream_probe api.test_shapes api.test_server` | **19/19 OK** |
| `node --test frontend/tests/viewer-select.test.mjs` | **2/2 pass** |
| `npx tsc --noEmit` (frontend) | **exit 0** |
| `probe_stream_endpoint()` with Kit stopped | `available: false` (honest offline) |

Full browser WebRTC connect against a live `urbantwin_streaming.kit` host was
**not** re-run in this session (signaling port `49100` was closed at smoke time).
Operator path: launch the Kit bat, confirm `/api/stream/config` is `available`,
then open the dashboard in Chromium with `URBANTWIN_API_BASE` set.

## Related docs

- View delivery: `docs/PHASE15_KIT_COMMAND_DELIVERY.md`
- Judge demo: `docs/DEMO_RUNBOOK.md` (Phase 17)
- Kit host: `docs/PHASE13_STREAMING_KIT.md`
- Live simulation API: `docs/PHASE12_LOCAL_API.md`
- Product handoff: `docs/FRONTEND_BACKEND_HANDOFF.md`
