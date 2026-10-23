# Argus AI — end-to-end pipeline

How a scenario becomes metrics, USD, and (optionally) a live Omniverse stream.

## Slide-friendly summary (copy into a deck)

### One-line story

**You set a city scenario → Argus simulates people → it suggests fixes → you see results in the dashboard and optionally in a live 3D city.**

### Steps (keep this order on the slide)

1. **You choose conditions** — temperature, humidity, rain, population in the Argus AI dashboard.
2. **Live API accepts the run** — checks ranges, then starts one simulation job.
3. **Simulator runs “before”** — synthetic citizens pick routes on the real OSM city under that weather and crowding.
4. **Built-in advisor scores stress** — if heat / rain / crowding cross fixed thresholds, it suggests shade, drainage, or extra pedestrian capacity (no LLM required).
5. **Optional “after” re-sim** — applies those interventions and compares before vs after metrics.
6. **Export to the 3D twin** — report → canonical snapshots → USD agents and routes; a shade intervention becomes an `ADD_SHADE` proposal in the pipeline USD. The canopy seen in the streamed view is the packaged Phase 8 Intervention variant, not regenerated per run.
7. **Dashboard shows impact** — headline metrics, problem areas, recommendations.
8. **Optional live 3D** — Kit streams the RTX view into the browser; camera / overlay / play-pause are allow-listed then sent to Kit.
9. **Optional RAG advisor** — ranks grounded suggestions among the same executable actions; the simulator advisor stays the authority for what actually runs.

### What each box means (glossary for speakers)

| Piece | Plain language |
| --- | --- |
| Dashboard | Web UI operators use (Argus AI). |
| API | Local Python server that runs sims and validates commands. |
| Simulator | Deterministic pedestrian / stress model in `Simulation/`. |
| Threshold advisor | Rules like “heat ≥ 60 → suggest more shade”. |
| Snapshot / USD | Numbers and people placed into the Omniverse city file. |
| Kit streaming | Headless Omniverse app that renders and WebRTC-streams the view. |
| RAG advise | Optional LLM ranking over a local knowledge base — cannot invent new action types. |

### Integrity lines (use on the slide footer)

- Metrics are **heuristic prototypes**, not medical or engineering forecasts.
- Citizens are **survey-calibrated**; scenario factors are confounded.
- Shade canopy in 3D is a **proposal visualization**; drainage may improve metrics without a new 3D asset.

---

## Mermaid diagram (render in GitHub / Mermaid Live / Notion)

```mermaid
flowchart TB
  subgraph Operator["Operator / Browser"]
    UI["Argus AI dashboard<br/>Next.js frontend"]
    Scenario["Scenario inputs<br/>temp / humidity / rain / population"]
    Controls["Viewport controls<br/>camera · overlay · before/after · play/pause"]
    AdviseUI["Optional RAG advise UI"]
  end

  subgraph Frontend["Frontend process"]
    Proxy["Next.js /api/* proxy<br/>when URBANTWIN_API_BASE set"]
    Mock["Mock fixtures<br/>when env unset"]
    WebRTC["kit-webrtc-adapter<br/>@nvidia/ov-web-rtc DIRECT"]
  end

  subgraph API["Python API · python -m api :8000"]
    Health["GET /api/health"]
    StreamCfg["GET /api/stream/config<br/>TCP probe Kit signaling"]
    Runs["POST /api/runs<br/>validate ranges"]
    Poll["GET /api/runs/{id}"]
    View["POST /api/runs/{id}/view<br/>allow-list state/camera/overlay/playback"]
    Explain["POST /api/runs/{id}/explain"]
    Advise["POST /api/runs/{id}/advise<br/>optional RAG"]
    RM["RunManager<br/>single worker"]
  end

  subgraph Pipeline["Phase 11 · integration/run_pipeline.py"]
    Sim["Simulation/main.py<br/>before arm"]
    Advisor["urban_advisor<br/>threshold recommendations"]
    Interv["recommended_interventions<br/>shade / drainage / capacity boosts"]
    After["Simulation/main.py<br/>after arm if interventions"]
    Report["simulation report JSON"]
    Snap["export_snapshot.py<br/>canonical v1 snapshots"]
    USD["USD agents / routes / metrics<br/>phase9 over layers"]
    Validate["validate_integration.py<br/>gate"]
  end

  subgraph Kit["Omniverse Kit · kit-app-template"]
    StreamKit["urbantwin_streaming.kit<br/>--no-window · ports 49100 / media"]
    Autoload["urbantwin.stage_autoload<br/>opens phase9/scene/main.usda"]
    ViewCmd["urbantwin.view_commands<br/>camera · overlay · demoState · timeline"]
    Stage["OpenUSD stage<br/>city · agents · Phase 8 demoState variant"]
    RTX["RTX render → WebRTC"]
  end

  subgraph Data["Data / city"]
    OSM["city_osm.json · citizens survey-calibrated"]
    Phase9["phase9/scene/main.usda"]
    Knowledge["data/urban_interventions.json<br/>RAG index optional"]
  end

  Scenario --> UI
  UI --> Proxy
  UI -.-> Mock
  Proxy --> Health
  Proxy --> StreamCfg
  Proxy --> Runs
  Proxy --> Poll
  Proxy --> View
  Proxy --> Explain
  AdviseUI --> Advise

  StreamCfg -->|"signaling available?"| WebRTC
  WebRTC <-->|"WebRTC A/V + data channel"| StreamKit
  Controls -->|"view command"| View
  View -->|"accepted by allow-list"| WebRTC
  WebRTC -->|"sendMessage urbantwin.view_command<br/>delivered = send resolved, not applied"| ViewCmd

  Runs --> RM
  RM --> Pipeline
  OSM --> Sim
  Sim --> Advisor
  Advisor --> Interv
  Interv --> After
  Sim --> Report
  After --> Report
  Report --> Snap
  Snap --> USD
  Phase9 --> USD
  USD --> Validate
  Report --> Poll
  Report --> Explain
  Report --> Advise
  Knowledge --> Advise
  Advisor -.->|"fallback / authority"| Advise

  Autoload --> Stage
  USD -->|"publishes generated/agents.usda (before arm only)"| Phase9
  Phase9 --> Stage
  ViewCmd --> Stage
  StreamKit --> Autoload
  StreamKit --> ViewCmd
  Stage --> RTX
  RTX --> WebRTC
  WebRTC --> UI
  Poll --> UI
```

### Simplified Mermaid (better for a single slide)

```mermaid
flowchart LR
  A[Set scenario<br/>in dashboard] --> B[API validates<br/>and starts run]
  B --> C[Simulate before<br/>citizens + city]
  C --> D[Threshold advisor<br/>suggests interventions]
  D --> E[Optional after<br/>re-simulate]
  E --> F[Export snapshots<br/>to USD twin]
  F --> G[Show metrics<br/>in dashboard]
  F --> H[Optional Kit<br/>live 3D stream]
  G --> I[Optional RAG<br/>rank suggestions]
  H --> J[Camera / overlay<br/>play-pause in UI]
```

---

## Related docs

- Root [`README.md`](../README.md) — launch and verification
- [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) — operator demo
- [`INTEGRATION_CONTRACT.md`](INTEGRATION_CONTRACT.md) — snapshot contract
