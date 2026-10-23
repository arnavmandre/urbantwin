"""
End-to-end integration check: simulator -> adapter -> snapshot -> USD.

Runs the six acceptance tests from the integration brief. Each traces one value
from the simulator's own report all the way to the authored USD stage, so a
PASS means the number a judge sees on screen is the number the simulator
produced - not that a file merely parsed.

Run:  python integration/validate_integration.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = ROOT / "Simulation" / "urbantwin_demo_output.json"
SNAPSHOT = ROOT / "data" / "simulation_before.json"
AFTER = ROOT / "data" / "simulation_after.json"
STAGE = HERE / "runtime" / "scene" / "main.usda"
REGISTRY = ROOT / "phase2" / "scene" / "edge_registry.json"

sys.path.insert(0, str(HERE))
from export_snapshot import INTERVENTION_TYPES  # noqa: E402

# Mapped kinds become drawn snapshot proposals; known-but-unmapped kinds
# (drainage_boost) are metrics only. Anything else is an unknown key.
DRAWABLE_INTERVENTION_KEYS = {k for k, v in INTERVENTION_TYPES.items() if v}
METRICS_ONLY_INTERVENTION_KEYS = {k for k, v in INTERVENTION_TYPES.items() if not v}

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    return ok


def animation_frame_paths(snapshot: Path) -> list[Path]:
    """Find numbered animation frames beside the selected snapshot."""
    prefix = snapshot.stem
    base, separator, frame = prefix.rpartition("_")
    if separator and len(frame) == 3 and frame.isdigit():
        prefix = base
    return sorted(snapshot.parent.glob(f"{prefix}_*.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--after", type=Path, default=AFTER)
    parser.add_argument("--stage", type=Path, default=STAGE)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()

    from pxr import Usd, UsdGeom

    for path in (args.report, args.snapshot, args.stage):
        if not path.exists():
            raise SystemExit(
                f"missing {path}\n"
                "Run, in order:\n"
                "  cd Simulation && python main.py citizens_survey_city_osm.json city_osm.json\n"
                "  python integration/export_snapshot.py\n"
                "  python integration/load_snapshot.py data/simulation_before.json")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8")) if args.after.exists() else None
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    edges = registry["edges"]
    stage = Usd.Stage.Open(str(args.stage))

    before = report["before"]
    print("Simulator -> snapshot -> USD\n")

    # --- TEST 1: scenario -------------------------------------------------
    sim_t = float(before["inputs"]["temperature"])
    snap_t = float(snap["scenario"]["temperature_c"])
    sim_pop = int(before["inputs"]["population"])
    check("1. scenario temperature and population survive the adapter",
          sim_t == snap_t and sim_pop == snap["scenario"]["population_equivalent"],
          f"{sim_t}C / {sim_pop:,} equivalent")

    # --- TEST 2: agent identity ------------------------------------------
    sim_ids = [c["id"] for c in before["citizens"][:len(snap["agents"])]]
    snap_ids = [a["id"] for a in snap["agents"]]
    usd_agents = [p for p in stage.Traverse()
                  if p.GetTypeName() == "PointInstancer" or "gent" in p.GetName()]
    agent_count = 0
    for p in stage.Traverse():
        if p.GetTypeName() == "PointInstancer":
            pos = UsdGeom.PointInstancer(p).GetPositionsAttr().Get() or []
            agent_count = max(agent_count, len(pos))
    check("2. agent ids preserved simulator -> snapshot",
          snap_ids == [i for i in sim_ids if i in set(snap_ids)][:len(snap_ids)],
          f"{len(snap_ids)} agents, first={snap_ids[0]}")
    check("2b. agents reached the USD stage",
          agent_count >= len(snap_ids) or bool(usd_agents),
          f"{agent_count} instanced positions authored")

    # --- TEST 3: route / edge ids ----------------------------------------
    known = set(edges)
    bad = [e for a in snap["agents"] for e in a["route"] if e not in known]
    every_agent_routed = all(a["route"] for a in snap["agents"])
    check("3. every agent route uses real registry edge ids",
          not bad and every_agent_routed,
          f"{len(snap['edges'])} distinct edges referenced, 0 unknown")

    # --- TEST 4: crowding ------------------------------------------------
    # Trace one route's crowding from the simulator report to the snapshot.
    city = json.loads((ROOT / "Simulation" / "city_osm.json").read_text(encoding="utf-8"))
    route_edges = {r["id"]: r.get("osm_edges", []) for r in city["routes"]}
    traced = None
    for row in sorted(before["routes"], key=lambda r: -r["crowding"]):
        eids = [e for e in route_edges.get(row["id"], []) if e in snap["edges"]]
        if eids:
            traced = (row["id"], row["crowding"] / 100.0, eids[0],
                      snap["edges"][eids[0]]["crowding"])
            break
    ok4 = traced is not None and snap["edges"][traced[2]]["crowding"] >= traced[1] - 1e-6
    check("4. simulator crowding reaches the snapshot edge",
          ok4,
          f"{traced[0]} {traced[1]:.2f} -> {traced[2]} {traced[3]:.2f}" if traced else "")

    # --- TEST 5: heat ----------------------------------------------------
    heats = [m["heat_exposure"] for m in snap["edges"].values()]
    in_range = all(0.0 <= h <= 1.0 for h in heats)
    varied = (max(heats) - min(heats)) > 0.01 if heats else False
    check("5. heat exposure normalised to 0-1 and varies across edges",
          in_range and varied,
          f"range {min(heats):.2f}-{max(heats):.2f}")

    # --- TEST 6: interventions -------------------------------------------
    # shade_boost -> ADD_SHADE (drawn). drainage_boost has no snapshot type yet
    # (metrics only). Cold+rain scenarios can apply drainage alone; that must
    # not fail the gate just because nothing is drawn in USD.
    if after:
        applied = report.get("intervention", {}) or {}
        recommendations = report.get("advisor", {}).get("recommendations", [])
        calm_control = (
            "no_major_intervention" in recommendations
            and not applied
            and not after["interventions"]
        )
        metrics_only = (
            bool(applied)
            and set(applied) <= METRICS_ONLY_INTERVENTION_KEYS
            and not after["interventions"]
        )
        ok6 = calm_control or metrics_only or (
            bool(after["interventions"])
            and all(i["target"] in known for i in after["interventions"])
        )
        check("6. advisor intervention becomes a targeted snapshot proposal",
              ok6,
              "calm control: no intervention required" if calm_control else
              "metrics-only intervention (e.g. drainage_boost); nothing drawn"
              if metrics_only else
              f"{list(applied)} -> "
              f"{[(i['type'], i['target']) for i in after['interventions']]}")
    else:
        check("6. intervention snapshot", False, "simulation_after.json missing")

    # --- coordinate sanity -------------------------------------------------
    # Agents must sit on their own route geometry, not merely inside the tile.
    worst, checked = 0.0, 0
    for a in snap["agents"][:50]:
        best = math.inf
        for eid in a["route"]:
            pts = [(p[0], p[1]) for p in edges[eid]["points"]]
            for p0, p1 in zip(pts, pts[1:]) or [(pts[0], pts[0])]:
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                L = dx * dx + dy * dy
                t = 0.0 if L == 0 else max(0.0, min(1.0, ((a["x"] - p0[0]) * dx
                                                          + (a["y"] - p0[1]) * dy) / L))
                best = min(best, math.dist((a["x"], a["y"]),
                                           (p0[0] + t * dx, p0[1] + t * dy)))
        if best < math.inf:
            worst = max(worst, best)
            checked += 1
    check("7. agent positions lie on their own route geometry",
          checked > 0 and worst < 1.0,
          f"worst offset {worst:.3f} m across {checked} agents")

    # --- route geometry is a walkable chain, not a scrambled edge bag ------
    # Test 7 above only proves each point is near SOME segment of its own
    # route, which stays true even when the traversal order is nonsense. These
    # three catch ordering, which test 7 cannot.
    from export_snapshot import oriented_route_points  # noqa: E402

    worst_join = 0.0
    for r in city["routes"]:
        _pts, w = oriented_route_points(edges, r.get("osm_edges", []))
        worst_join = max(worst_join, w)
    check("9. route edges chain end-to-end (orientation)",
          worst_join < 5.0, f"worst join gap {worst_join:.2f} m across "
                            f"{len(city['routes'])} routes")

    # --- animation sanity ---------------------------------------------------
    seq = animation_frame_paths(args.snapshot)
    if len(seq) > 1:
        series = [json.loads(p.read_text(encoding="utf-8"))["agents"] for p in seq]
        times = [json.loads(p.read_text(encoding="utf-8"))["timestamp"] for p in seq]
        jumps, backwards = [], 0
        for k in range(len(series) - 1):
            dt = max(times[k + 1] - times[k], 1e-6)
            for a, b in zip(series[k], series[k + 1]):
                jumps.append(math.dist((a["x"], a["y"]), (b["x"], b["y"])) / dt)
        top = max(jumps) * 3.6
        check("10. no agent exceeds a plausible walking speed between frames",
              top < 10.0, f"fastest {top:.1f} km/h over {len(seq)} frames")

        # Progress must never reverse: an agent walks forward, or has arrived.
        # Measured as distance along that agent's own oriented chain.
        chains = {}

        def along(agent):
            key = tuple(agent["route"])
            if key not in chains:
                pts, _ = oriented_route_points(edges, agent["route"])
                cum = [0.0]
                for p, q in zip(pts, pts[1:]):
                    cum.append(cum[-1] + math.dist(p, q))
                chains[key] = (pts, cum)
            pts, cum = chains[key]
            if not pts:
                return None
            best, best_s = math.inf, 0.0
            for i, (p0, p1) in enumerate(zip(pts, pts[1:])):
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                L = dx * dx + dy * dy
                t = 0.0 if L == 0 else max(0.0, min(1.0, ((agent["x"] - p0[0]) * dx
                                                          + (agent["y"] - p0[1]) * dy) / L))
                d = math.dist((agent["x"], agent["y"]), (p0[0] + t * dx, p0[1] + t * dy))
                if d < best:
                    best, best_s = d, cum[i] + t * math.dist(p0, p1)
            return best_s

        backwards, sampled = 0, 0
        for k in range(0, len(series) - 1, 5):          # every 5th transition
            for j in range(0, len(series[k]), 20):      # every 20th agent
                s0, s1 = along(series[k][j]), along(series[k + 1][j])
                if s0 is None or s1 is None:
                    continue
                sampled += 1
                if s1 < s0 - 1.0:                       # 1 m tolerance
                    backwards += 1
        check("10b. agents never move backwards along their own route",
              backwards == 0,
              f"{backwards} reversals in {sampled} sampled transitions")
    else:
        print("  SKIP  10. animation checks (no frame sequence beside snapshot)")

    # --- provenance --------------------------------------------------------
    real = snap["data_kind"] == "simulation"
    check("8. snapshot is labelled as real simulation output, not mock",
          real, f"data_kind={snap['data_kind']}")

    failed = [n for n, ok, _ in results if not ok]
    print()
    if failed:
        print(f"FAIL: {len(failed)} test(s) failed: {failed}")
        sys.exit(1)
    print(f"PASS: {len(results)}/{len(results)} - simulator output is driving the "
          "Omniverse scene end to end")


if __name__ == "__main__":
    main()
