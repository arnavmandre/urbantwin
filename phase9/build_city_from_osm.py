"""
Build a simulator city from the REAL OSM city.

The simulator currently runs on 8 abstract buildings joined by 18 abstract
routes, while Omniverse renders 623 real buildings on a 2,291-edge pedestrian
network. That mismatch is the reason `integration/route_mapping.json` has to
exist at all, and the reason nobody can honestly say the simulation runs on real
geography.

This writes a city file in the simulator's own schema whose buildings ARE OSM
buildings and whose routes ARE real walking paths with measured lengths:

    Simulation/city_osm.json
    Simulation/citizens_osm.json

Run it through the existing CLI - the simulator needs no changes:

    cd Simulation
    python main.py citizens_osm.json city_osm.json

The 8-building demo is untouched; this is an additional city, not a replacement.

Reuses the graph and pathfinding in integration/propose_route_mapping.py rather
than reimplementing them.

Run:  python phase9/build_city_from_osm.py [--destinations 12] [--citizens 240]
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import math
from pathlib import Path

from pxr import UsdGeom, Usd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT / "phase1" / "scene" / "main.usda"
REGISTRY = ROOT / "phase2" / "scene" / "edge_registry.json"
OUT_CITY = ROOT / "Simulation" / "city_osm.json"
OUT_CITIZENS = ROOT / "Simulation" / "citizens_osm.json"

# Reuse the existing graph/pathfinding rather than writing a second copy.
_spec = importlib.util.spec_from_file_location(
    "urbantwin_route_proposal", ROOT / "integration" / "propose_route_mapping.py")
_rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rp)

ALTS_PER_PAIR = 2        # simulator needs >= 2 routes per pair to have a choice
ZONE_GRID = 3            # 3x3 spatial partition when landuse is unavailable

# OSM building class -> simulator building type
TYPE_MAP = {
    "apartments": "residential", "house": "residential", "terrace": "residential",
    "dormitory": "residential", "residential": "residential",
    "university": "school", "college": "school", "school": "school",
    "hospital": "hospital", "hotel": "office", "office": "office",
    "commercial": "office", "retail": "market", "supermarket": "market",
    "kiosk": "market", "museum": "school", "public": "office",
    "train_station": "transit_hub",
}
# Indoor refuge by type: how much shelter from heat the building itself offers.
COOLING = {"residential": 0.30, "school": 0.55, "hospital": 0.85,
           "office": 0.80, "market": 0.20, "transit_hub": 0.40}


def tags_of(prim) -> dict:
    a = prim.GetAttribute("urbantwin:osmTags")
    try:
        return json.loads(a.Get()) if a and a.Get() else {}
    except (ValueError, TypeError):
        return {}


def polygon_area(ring) -> float:
    return abs(sum(x0 * y1 - x1 * y0
                   for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))) / 2.0


def load_buildings(stage):
    """-> [{id, name, type, centroid, area, levels, height}] for usable buildings."""
    out = []
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        tags = tags_of(prim)
        kind = (tags.get("building") or "").lower()
        sim_type = TYPE_MAP.get(kind)
        if sim_type is None:
            # `building=yes` and friends: usable as housing, but only if it is
            # big enough to plausibly hold people.
            sim_type = "residential"
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
        if len(pts) < 6:
            continue
        n = len(pts) // 2
        ring = [(p[0], p[1]) for p in pts[:n]]
        area = polygon_area(ring)
        if area < 40:
            continue
        try:
            levels = max(1.0, float(tags.get("building:levels", 0)) or 0)
        except ValueError:
            levels = 0.0
        height = max((p[2] for p in pts), default=12.0)
        if not levels:
            levels = max(1.0, round(height / 3.0))
        # Prefer the real OSM name; `building=yes` carries no useful label, so
        # fall back to the simulator type plus a short id rather than "yes 123".
        label = tags.get("name")
        if not label:
            generic = kind in ("", "yes")
            stem = sim_type.replace("_", " ").title() if generic else kind.title()
            label = f"{stem} {prim.GetName().split('_')[-1][-4:]}"
        out.append({
            "prim": prim.GetName(),
            "name": label,
            "type": sim_type,
            "kind": kind,
            "centroid": (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n),
            "area": area,
            "levels": levels,
            "height": height,
            "named": bool(tags.get("name")),
        })
    return out


def load_greenspaces(stage):
    greens = []
    for prim in stage.GetPrimAtPath("/World/GreenSpaces").GetChildren():
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
        if len(pts) < 3:
            continue
        ring = [(p[0], p[1]) for p in pts]
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        greens.append(((cx, cy), polygon_area(ring)))
    return greens


def green_factor(point, greens, radius=90.0) -> float:
    """0..1 proxy for greenery near a point, from nearby green space area."""
    total = sum(a for c, a in greens if math.dist(point, c) < radius)
    return min(1.0, total / 25000.0)


def nearest_node(pos, point):
    return min(pos, key=lambda k: (pos[k][0] - point[0]) ** 2 + (pos[k][1] - point[1]) ** 2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destinations", type=int, default=12,
                    help="major destinations drawn from named/civic buildings")
    ap.add_argument("--origins", type=int, default=16, help="residential origins")
    ap.add_argument("--citizens", type=int, default=240)
    args = ap.parse_args()

    stage = Usd.Stage.Open(str(BASE))
    buildings = load_buildings(stage)
    greens = load_greenspaces(stage)
    print(f"{len(buildings)} usable OSM buildings, {len(greens)} green spaces")

    edges = json.loads(REGISTRY.read_text(encoding="utf-8"))["edges"]
    adj, pos, edge_len = _rp.build_graph(edges)
    comp = max(_rp.components(adj), key=len)
    pos = {k: v for k, v in pos.items() if k in comp}
    print(f"walking graph: {len(adj)} nodes, largest component {len(comp)}")

    # --- pick destinations and origins ---------------------------------
    # Destinations: the real civic/retail anchors, biggest first. These are the
    # buildings with actual OSM names, which is what makes the demo legible.
    dests = sorted((b for b in buildings if b["type"] != "residential"),
                   key=lambda b: (b["named"], b["area"] * b["levels"]), reverse=True)
    chosen_d, seen_names = [], set()
    for b in dests:
        if b["name"] in seen_names:
            continue
        if any(math.dist(b["centroid"], o["centroid"]) < 60 for o in chosen_d):
            continue            # spread them out; adjacent shops are one place
        chosen_d.append(b)
        seen_names.add(b["name"])
        if len(chosen_d) >= args.destinations:
            break

    origins = sorted((b for b in buildings if b["type"] == "residential"),
                     key=lambda b: b["area"] * b["levels"], reverse=True)
    chosen_o = []
    for b in origins:
        if any(math.dist(b["centroid"], o["centroid"]) < 70 for o in chosen_o):
            continue
        chosen_o.append(b)
        if len(chosen_o) >= args.origins:
            break

    print(f"selected {len(chosen_o)} origins, {len(chosen_d)} destinations")

    # --- zones ----------------------------------------------------------
    xs = [b["centroid"][0] for b in buildings]
    ys = [b["centroid"][1] for b in buildings]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    def zone_of(point):
        gx = min(ZONE_GRID - 1, int((point[0] - x0) / max(x1 - x0, 1e-9) * ZONE_GRID))
        gy = min(ZONE_GRID - 1, int((point[1] - y0) / max(y1 - y0, 1e-9) * ZONE_GRID))
        return f"Zone {chr(65 + gy)}{gx + 1}"

    zone_points = collections.defaultdict(list)
    for b in chosen_o + chosen_d:
        zone_points[zone_of(b["centroid"])].append(b["centroid"])

    zones = []
    for zid, pts in sorted(zone_points.items()):
        centre = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        shade = round(0.18 + 0.55 * green_factor(centre, greens, 140.0), 2)
        zones.append({"id": zid, "drainage": 0.55, "shade": min(shade, 1.0)})

    # --- buildings in simulator schema ----------------------------------
    sim_buildings = []
    for b in chosen_o + chosen_d:
        is_home = b in chosen_o
        capacity = 0 if is_home else int(min(6000, max(400, b["area"] * b["levels"] * 0.12)))
        sim_buildings.append({
            "id": b["prim"].replace("osm_way_", "B"),
            "name": b["name"][:48],
            "type": b["type"],
            "zone": zone_of(b["centroid"]),
            "capacity": capacity,
            "cooling": COOLING.get(b["type"], 0.4),
            # Archived flat terrain: shelter scales with building size.
            "flood_exposure": round(max(0.15, 0.75 - 0.03 * b["levels"]), 2),
        })
    by_prim = {b["prim"]: s for b, s in zip(chosen_o + chosen_d, sim_buildings)}

    # --- routes: real walking paths -------------------------------------
    anchors = {b["prim"]: nearest_node(pos, b["centroid"]) for b in chosen_o + chosen_d}

    routes, rid = [], 0
    pairs = [(o, d) for o in chosen_o for d in chosen_d]
    # Each origin serves the 3 nearest destinations: a full cross product would
    # make routes_between() (a linear scan, called per citizen) dominate runtime.
    per_origin = collections.defaultdict(list)
    for o, d in pairs:
        per_origin[o["prim"]].append((math.dist(o["centroid"], d["centroid"]), d))
    for o in chosen_o:
        for _, d in sorted(per_origin[o["prim"]], key=lambda t: t[0])[:3]:
            # dijkstra() takes a {edge_id: cost multiplier} dict; re-weighting
            # the edges already used is what makes the alternative different.
            penalty: dict[str, float] = {}
            found = []
            for _ in range(ALTS_PER_PAIR):
                path, metres = _rp.dijkstra(
                    adj, anchors[o["prim"]], anchors[d["prim"]], penalty)
                if not path or any(path == p for p, _ in found):
                    break
                found.append((path, metres))
                penalty.update({e: 3.0 for e in path})
            for path, metres in found:
                if metres < 30:
                    continue
                mid = edges[path[len(path) // 2]]["points"][0][:2]
                g = green_factor(tuple(mid), greens)
                widths = [edges[e].get("width_m", 2.5) for e in path]
                width = sum(widths) / len(widths)
                rid += 1
                routes.append({
                    "id": f"R{rid}",
                    "start": by_prim[o["prim"]]["id"],
                    "end": by_prim[d["prim"]]["id"],
                    "distance_km": round(metres / 1000.0, 3),
                    "shade": round(min(0.9, 0.12 + 0.7 * g), 2),
                    "greenery": round(min(1.0, g), 2),
                    "drainage": 0.6,
                    "base_crowding": round(min(0.6, 0.15 + 0.25 * (3.0 / max(width, 1.0))), 2),
                    "transit": 0.3,
                    # ~1 pedestrian/second/metre of width at comfortable density
                    "capacity_pph": int(width * 900),
                    "via_zones": sorted({zone_of(tuple(edges[e]["points"][0][:2])) for e in path}),
                    "osm_edges": path,
                })

    # Drop buildings nothing routes to, so the city validates.
    used = {r["start"] for r in routes} | {r["end"] for r in routes}
    sim_buildings = [b for b in sim_buildings if b["id"] in used]
    used_zones = {b["zone"] for b in sim_buildings} | {
        z for r in routes for z in r["via_zones"]}
    zones = [z for z in zones if z["id"] in used_zones]

    city = {
        "schema_version": 1,
        "description": (
            "Simulator city generated from the archived OSM tile. "
            "Buildings are OSM buildings, routes are real walking paths "
            "over the Phase 2 pedestrian graph with measured lengths. Each route "
            "carries osm_edges: the ordered Phase 2 edge ids it traverses, so no "
            "separate route mapping is required. Generated by "
            "phase9/build_city_from_osm.py - do not hand-edit."
        ),
        "zones": zones,
        "buildings": sim_buildings,
        "routes": [{k: v for k, v in r.items()} for r in routes],
    }
    OUT_CITY.write_text(json.dumps(city, indent=2) + "\n", encoding="utf-8")

    # --- citizens --------------------------------------------------------
    homes = [b["id"] for b in sim_buildings if b["capacity"] == 0]
    pairs_available = collections.defaultdict(list)
    for r in routes:
        pairs_available[r["start"]].append(r["end"])

    archetypes = [
        ("Young commuter", 0.70, 0.71, 0.63, 4.9, 0.36, 0.81),
        ("Student", 0.70, 0.68, 0.56, 4.7, 0.45, 0.77),
        ("Outdoor worker", 0.85, 0.79, 0.70, 4.2, 0.25, 0.34),
        ("Family / parent", 0.60, 0.58, 0.44, 3.7, 0.66, 0.65),
        ("Elderly citizen", 0.37, 0.48, 0.42, 3.1, 0.55, 0.69),
        ("Mobility-limited citizen", 0.55, 0.45, 0.50, 2.4, 0.28, 0.61),
        ("General pedestrian", 0.64, 0.66, 0.60, 4.4, 0.40, 0.46),
    ]
    citizens = []
    i = 0
    while len(citizens) < args.citizens and homes:
        home = homes[i % len(homes)]
        dests_here = pairs_available.get(home)
        i += 1
        if not dests_here:
            continue
        name, ht, rt, ct, sp, gp, tp = archetypes[len(citizens) % len(archetypes)]
        k = len(citizens)
        wob = ((k * 2654435761) % 1000) / 1000.0 - 0.5     # deterministic +-0.5
        citizens.append({
            "id": f"C{len(citizens) + 1:04d}",
            "archetype": name,
            "home": home,
            "destination": dests_here[k % len(dests_here)],
            "heat_tolerance": round(min(0.98, max(0.02, ht + 0.12 * wob)), 3),
            "rain_tolerance": round(min(0.98, max(0.02, rt + 0.12 * wob)), 3),
            "crowd_tolerance": round(min(0.98, max(0.02, ct + 0.12 * wob)), 3),
            "walking_speed_kmh": round(max(1.5, sp + 0.5 * wob), 2),
            "green_preference": round(min(0.98, max(0.02, gp + 0.12 * wob)), 3),
            "transit_preference": round(min(0.98, max(0.02, tp + 0.12 * wob)), 3),
            "weight": 1.0,
        })

    OUT_CITIZENS.write_text(json.dumps({
        "schema_version": 1,
        "description": (
            "Synthetic citizens for the OSM-derived city. Behavioural parameters "
            "are archetype means with a deterministic spread - NOT calibrated "
            "from survey responses. Generated by phase9/build_city_from_osm.py."
        ),
        "citizens": citizens,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(zones)} zones, {len(sim_buildings)} buildings, {len(routes)} routes, "
          f"{len(citizens)} citizens")
    lengths = [r["distance_km"] for r in routes]
    if lengths:
        print(f"route length {min(lengths):.2f}..{max(lengths):.2f} km (measured on the OSM graph)")
    named = [b["name"] for b in sim_buildings if not b["name"][0].isdigit()][:6]
    print("real named places:", ", ".join(named))
    print(f"\nwrote {OUT_CITY}\nwrote {OUT_CITIZENS}")
    print("\nRun it:  cd Simulation && python main.py citizens_osm.json city_osm.json")


if __name__ == "__main__":
    main()
