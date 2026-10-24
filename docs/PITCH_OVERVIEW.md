# Argus AI — Pitch Overview

> **Simulate the human experience before building the city.**

Argus AI (internally *UrbanTwin AI*) is a human-centric urban digital twin. A planner picks a city, sets a
scenario (heat, humidity, rain, crowding), and watches survey-calibrated synthetic citizens move through
real OpenStreetMap streets in a live NVIDIA Omniverse stream. The system then shows how their comfort, stress
and route choices change, and what happens when a proposed intervention is applied.

Theme: **AI for Good — Urban Planning**

---

## 1. The problem

Planners can already *see* a proposed city. What they can't easily see is how the people in it will
*experience* it when conditions change:

- A 45 °C afternoon on streets with little shade
- A cloudburst on poorly drained lanes
- A crowd twice the size the street was designed for

Answering that today means stitching together separate climate, traffic, architecture and behavioural studies.
The human experience, the thing a city is for, is usually the last layer to be considered.

> **The question we answer:** *what happens to the people when the conditions change, and which
> intervention actually helps them?*

## 2. Our solution

One interactive loop that puts people at the centre:

```text
Real city (OpenStreetMap)  ->  Scenario  ->  Synthetic citizens  ->  Simulation
        ^                                                             |
        |                                                             v
   Re-simulate  <-  Apply intervention  <-  Advisor  <-  Human-impact metrics
```

- **Real geography.** Buildings, streets, footpaths, parks and trees come from OpenStreetMap.
- **Real people's preferences.** Citizen behaviour (heat, rain and crowd tolerance, walking speed, preference
  for green or transit routes) is calibrated from a survey of 41 real participants.
- **Visible consequences.** Each citizen's chosen route and behaviour is animated in a live Omniverse stream
  inside a web dashboard.
- **Actionable advice.** A deterministic advisor names the problem places and recommends interventions the
  simulator can actually execute (more shade, better drainage, alternative routes). An optional LLM layer
  ranks and explains them.
- **Before vs after.** The same citizens are re-simulated under the applied intervention, so the planner sees
  the change in comfort, stress and behaviour on the same streets.

## 3. How it works

| Layer | What it does | Built with |
|---|---|---|
| City model | OSM footprints and streets -> heights, materials, trees -> OpenUSD stage | Python, Blender (headless), OpenUSD (`pxr`) |
| Synthetic citizens | Behaviour parameters sampled from a Gaussian copula fitted to the survey | Python, NumPy |
| Simulator | Per-citizen route choice over real walking paths, responding to heat, rain, crowding, shade and transit; emergent corridor congestion (damped iterative assignment); human-experience metrics | Pure Python, deterministic, ~80 built-in asserts |
| Advisor | Threshold rules find problem zones, buildings and routes and propose executable interventions; optional RAG + LLM ranks them | Python; optional Groq-hosted `gpt-oss-120b` |
| Visualisation | Citizens as animated low-poly people coloured by behaviour; illustrative traffic; Before/After switch | NVIDIA Omniverse Kit, RTX, OpenUSD |
| Dashboard | Scenario controls, city switch, live viewport, metrics, citizen inspector, advisor panels | Next.js, WebRTC (`@nvidia/ov-web-rtc`) |
| Backend | Runs the full pipeline per scenario on a local HTTP API | Python standard-library server |
| Analytics | History of every run (baseline vs intervention) | PostgreSQL + Grafana (Docker) |

**Headline metric: the Human Experience Index (HEI)**, a 0–100 weighted blend:
- citizen comfort 35 %: what simulated citizens actually experienced on the routes they chose
- city comfort 25 %
- safety 20 %
- mobility 20 %

## 4. Two real cities

| | **London — Russell Square** | **Pune — around Shaniwar Wada** |
|---|---|---|
| Area | Russell Square district | 1 km × 1 km simulated; 400 m × 400 m streamed |
| Buildings in model | 623 (12 OSM-derived materials) | 2,069 (272 in the streamed view) |
| Trees at surveyed OSM positions | 511 | 329 (115 in the streamed view) |
| Simulator city | 75 buildings, 254 real walking routes | 107 buildings, 3,011 real walking routes |
| Citizens | survey-calibrated | 600 survey-calibrated, every one animated |
| Run time | seconds | about 7 s per full run (simulate + animate both arms + publish) |

Pune shows the approach transfers: a dense, historic South Asian street grid built from raw OSM data, with
one-way streets respected, traffic on the left and auto-rickshaws in the illustrative traffic.

## 5. Demo script (about 3 minutes)

1. **Open the dashboard.** The live Omniverse viewport shows Pune around Shaniwar Wada. Walkers are on the
   pavements and traffic is moving, all in real time.
2. **Pick a scenario.** For example *Extreme heat and rain*: 40 °C, 80 % humidity, 80 mm rain, 100,000
   population equivalent. Keep "apply recommended interventions" ticked and press **Run**.
3. **Read the impact.** In about 10 seconds the stream updates with that run's citizens, and the headline
   metrics and pressure points fill in. In one such Pune run, HEI went from **57.4 to 68.5** after the
   advisor applied +25 % shade and +35 % drainage. That is a single heuristic run, not a forecast.
4. **Toggle Before / After.** Many walkers change from yellow (seeking shade) and red (stressed) to green
   (continuing comfortably). These are the same citizens, re-simulated.
5. **Jump the camera to the Problem Zone** the run flagged, then open a citizen in the inspector to see their
   route, exposure and behaviour.
6. **Switch city to London** to show the same pipeline on a second city. Optionally open the Grafana history
   of every run.

## 6. Why it's different

- **People, not just pixels.** Most digital twins show buildings; we show how *people* fare in them.
- **Grounded behaviour.** Citizens are calibrated from real survey responses (41 participants, 164
  observations, holdout check passed 5/5), not hand-tuned.
- **Real cities, end to end.** From a raw OpenStreetMap extract to a live RTX stream with one command
  (`tools\demo_launch.ps1 -City pune`).
- **Honest by design.** Every run carries its own caveats, mock data is never presented as live, and the UI
  states the city-specific limits (below).
- **Executable advice.** The advisor only recommends what the simulator can actually apply and re-test,
  closing the design -> simulate -> improve loop.

## 7. What we do NOT claim (say this before the judges ask)

- **Metrics are heuristic prototypes**, not medical, meteorological, hydraulic or engineering predictions.
- **Calibrated, not separately measured:** the survey scenarios move temperature, crowding and shade together.
  Home and destination assignment is a heuristic, not survey data. Pune citizens use the same calibration;
  they are not surveyed Pune residents.
- **Not a time-evolving crowd simulation.** Each run is one equilibrium; the animation replays each citizen's
  chosen route. Walkers have no collision avoidance and vehicles have no signal model, so crossing traffic can
  meet at junctions.
- **Vehicles are illustrative.** There is no traffic data.
- **Heights are partly inferred.** OSM tags give 223 of 623 heights in London and 40 of 2,069 in Pune; the
  rest are interpolated or inferred from building class.
- **London's Before/After** switches between a stress state and a proposal state (a comparison, not a measured
  improvement). **Pune's** compares the simulator's own before and after arms.
- **Appearance is not data:** Pune's facade windows, wall tints and the people and vehicle models are visual
  only.
- **Random Forest models** are trained and documented (`phase10/models/`) but are not yet wired into the
  simulator. The LLM layer is optional and never the authority on metrics.
- **Streaming is not lightweight:** about 60 % GPU at 720p30, and it needs a Chromium browser.

## 8. Impact and who it's for

- **City planners and urban designers:** test heat, flood and crowding scenarios before construction.
- **Climate-adaptation teams:** compare shade and drainage interventions by their effect on people.
- **Public engagement:** show residents, visually, how a proposal changes their walk to school or the
  hospital.
- **Equity lens:** seven citizen archetypes (elderly, mobility-limited, families, outdoor workers, students,
  transit-dependent and general pedestrians) show *who* is most affected, not just averages.

## 9. Roadmap

1. Wire the trained Random Forest models into route choice and stress, behind a validation gate.
2. Generalise the city pipeline so any OSM area becomes a simulator city in one step.
3. Add real data where we now use heuristics: drainage maps, measured shade, traffic counts.
4. A time-evolving mode with collision-aware pedestrians and signalised junctions.
5. Hosted streaming for multi-user sessions and stakeholder reviews.

## 10. Under the hood (for technical judges)

- `Simulation/main.py`: deterministic, dependency-free simulator with its own test suite.
- `phase10/`: survey -> calibrated synthetic citizens (copula sampling, holdout validation).
- `phase9/`, `cities/pune/`: OpenUSD city stages built as override layers on top of the source data.
- `integration/run_pipeline.py`, `cities/pune/run_pune.py`: atomic per-run pipelines with staging and
  rollback.
- `api/`: local HTTP API for runs, citizens, advisor and stream config (63 tests).
- `frontend/`: Next.js dashboard with WebRTC streaming from Omniverse Kit.
- `analytics/`: Postgres + Grafana run history.
- Docs: `docs/INTEGRATION_CONTRACT.md`, `docs/PUNE_CITY.md`, `docs/DEMO_RUNBOOK.md`.

---

*Data: © OpenStreetMap contributors, ODbL. All figures above are from the current code, tests or a recorded
run; see the repository docs for how each is produced.*
