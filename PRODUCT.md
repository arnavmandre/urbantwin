# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Near term: hackathon judges** (theme: AI for Good, urban planning) watching a live demo of about four
  minutes, usually on one laptop screen or a projector. They must understand the idea, see it work live,
  and trust the numbers, all within one viewing.
- **Long term: city planners and urban designers** who run "what-if" scenarios (extreme heat, heavy rain,
  crowding) on a real neighbourhood before construction, and compare interventions by their effect on people.
- Design priority: win the judge demo **without** misrepresenting the planner product. Anything shown to
  judges must be something a planner could genuinely use.

## Product Purpose

UrbanTwin AI is a human-centric urban digital twin: it simulates how people experience a city when
conditions change, before anything is built. A planner picks a city and a scenario; survey-calibrated
synthetic citizens choose routes through real OpenStreetMap streets; the system reports human-impact
metrics (comfort, stress, behaviour, the Human Experience Index) and shows the citizens moving in a live
NVIDIA Omniverse stream. An AI advisor explains the results, proposes interventions the simulator can test,
and compares the re-run with the planner. Success: a planner (or judge) can see *who* is affected, *why*,
and *what a specific intervention changes*, from one scenario run.

Tagline: "Simulate the human experience before building the city."

## Positioning

Most digital twins show buildings; UrbanTwin AI shows how people fare in them. Its distinct mechanism is the
combination of (1) behaviour calibrated from real survey responses, (2) real OSM geography end to end, (3) a
deterministic simulator that is the only source of numbers, and (4) an AI advisor that can only propose
actions the simulator can execute and re-test. Honesty about limits is part of the position: every run
carries its own caveats.

## Operating Context

- Demo flow: open the dashboard → pick a scenario → run (~10 s) → read impact → chat with the AI advisor →
  Apply & re-run its proposal → it reports what changed → toggle Before / After → jump to the problem zone.
- Runs locally on one Windows laptop: Python API, Next.js dashboard, headless Omniverse Kit streaming over
  WebRTC (Chromium browser required, roughly 60 % GPU at 720p30), optional Grafana run history.
- Kit streams to one viewer at a time; the advisor (an Agent 37 hosted agent) can take a while to answer
  when it wakes from sleep.
- Mock mode (no live API) serves recorded fixtures and must never be presented as live.

## Capabilities and Constraints

- **City scope: multi-city, with Pune as the lead city.** Pune (around Shaniwar Wada) is the primary demo
  city; the product supports more than one city, and London (Russell Square) may return. Do not design the
  interface as if only one city can ever exist.
- Scenario inputs: temperature, humidity, rainfall, population equivalent (a demand scale, not a headcount).
- The simulator can test exactly four interventions: increase shade, improve drainage, alternative
  pedestrian routes, no major intervention. Nothing else may be offered as testable.
- Before / After compares the same citizens re-simulated under the applied intervention (Pune).
- Metrics are heuristic prototype scores (0-100; travel time in minutes), not medical, meteorological,
  hydraulic or engineering predictions.
- The AI advisor never produces metrics; every number comes from the simulator.
- The streamed 3D view shows a 400 m square of the 1 km simulated area.
- Terminology: "citizens" (synthetic), "run", "scenario", "intervention", "Before / After", "problem zone",
  "Human Experience Index (HEI)", "population equivalent".

## Brand Commitments

- Name: **UrbanTwin AI** (confirmed). The dashboard header currently reads "Argus AI"; aligning it is an open
  task, and "Argus" survives as the repository/code name.
- Voice: plain, precise, honest. State limits before anyone asks; never overclaim. Integrity rules in
  `CLAUDE.md` ("Integrity — this project is judged") are binding on product copy.

## Evidence on Hand

- Real survey: 41 participants, 164 observations (`phase10/data/`); a newer survey export with option
  counts exists (`UrbanTwin AI — Answer Option Counts`), per-respondent data not yet integrated.
- Real geography: OpenStreetMap extracts for Pune (`cities/pune/pune_center.osm`) and London.
- Verified facts and figures: `docs/PITCH_OVERVIEW.md`, `docs/PUNE_CITY.md`, `CLAUDE.md`.
- Absent, and must not be fabricated: testimonials, customer or city-partner names, deployment claims,
  benchmarks against other tools, traffic data (vehicles are illustrative), pricing.

## Product Principles

1. **People first.** Every screen answers "how are the citizens experiencing this?" before anything else.
2. **The simulator is the only source of truth.** AI explains and proposes; it never invents numbers.
3. **Honest by construction.** Caveats travel with results; mock is never shown as live; untestable ideas
   are labelled as such.
4. **Test, don't assert.** Recommendations become re-runs, and the effect is shown, not claimed.
5. **Demo-legible, planner-real.** Understandable in one viewing, but never a fake that a planner couldn't use.
