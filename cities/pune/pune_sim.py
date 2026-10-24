"""
Pune live layers: run the Argus simulator on the full 1 km Pune model, animate it, add illustrative traffic.

Order: build_script.py (Blender) -> pune_sim.py -> pune_view.py, with any Python that has pxr + numpy.
Dashboard runs reuse simulate() + animate() through run_pune.py.

Inputs : pune_center.osm, city_base.usda (from build_script.py), Argus Simulation/main.py,
         Argus phase10/assign_homes.py + Simulation/citizens_survey.json (reused unchanged).
Outputs: city_pune.json, citizens_pune.json, pune_routes.json, traffic.usdc, main_live.usda (1 km, animated),
         and for the default scenario sim_report_pune.json + agents_before.usdc / agents_after.usdc.

Honesty notes (also written to manifest.generated.json["simulation"]):
- Route choice, travel time and behaviour come from the unmodified Argus simulator.
- Citizen behaviour is calibrated on the Argus phase10 survey (41 participants), not Pune residents.
- Home/destination is assign_homes.py's trip heuristic, not survey data.
- Route shade = share of the route within 10 m of a real OSM tree (greenery reuses it); base crowding by
  road class, drainage and flood exposure are fixed heuristics (no Pune data).
- Walkers move along their simulator-chosen route at their own speed in real time, keeping left on the
  pavement and looping back on the other side. Behaviour colour is one equilibrium, not a time-evolving
  simulation.
- Cars are ILLUSTRATIVE: no traffic data exists; density and speed are fixed assumptions.
"""
import heapq
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

HERE = Path(__file__).resolve().parent
ARGUS = HERE.parents[1]  # repo root: this file lives in cities/pune/
PY = sys.executable

LON0, LAT0 = 73.8553, 18.5195
EARTH_R = 6378137.0
BBOX = dict(south=18.5150, north=18.5240, west=73.8506, east=73.8600)

FPS = 24
TIME_SCALE = 1.0       # real time: walkers at their survey speeds, vehicles at CAR_SPEED_KMH
DURATION_S = 120       # loop length; at real speed a short loop would barely move anyone
SAMPLE_HZ = 6          # positions stored 6x a second; USD interpolates the frames between
TIMECODES = [k * FPS // SAMPLE_HZ for k in range(DURATION_S * SAMPLE_HZ)]
HOMES = 90
CITIZENS = 600
CAR_SPACING_M = 70.0   # illustrative density: one car per 70 m of carriageway
CAR_SPEED_KMH = 20.0   # illustrative old-city speed

ROAD_CROWD = {"primary": 0.6, "trunk": 0.6, "trunk_link": 0.6, "secondary": 0.5, "secondary_link": 0.5,
              "tertiary": 0.4, "residential": 0.3, "living_street": 0.3, "service": 0.25,
              "footway": 0.2, "path": 0.2, "pedestrian": 0.35, "steps": 0.2, "corridor": 0.2}
CAR_ROADS = {"primary", "trunk", "trunk_link", "secondary", "secondary_link", "tertiary", "residential"}
# ribbon widths in metres; must match build_script.ROAD_WIDTHS (+ EXTENDED_WIDTHS) so walkers clear the carriageway
ROAD_WIDTH = {"primary": 10.0, "trunk": 10.0, "trunk_link": 10.0, "secondary": 8.0, "secondary_link": 8.0,
              "tertiary": 6.0, "residential": 6.0, "living_street": 6.0, "service": 4.0,
              "footway": 2.0, "path": 2.0, "pedestrian": 2.0, "steps": 2.0, "corridor": 2.0}
FOOTWAY_TYPES = {"footway", "path", "pedestrian", "steps", "corridor"}
SIM_TYPE = {"education": "school", "healthcare": "hospital", "retail": "market", "commercial": "market",
            "office": "office", "civic": "office", "hotel": "office", "religious": "religious",
            "heritage": "heritage"}
CAPACITY = {"school": 800, "hospital": 600, "market": 500, "office": 400, "religious": 600, "heritage": 1500}
COOLING = {"school": 0.5, "hospital": 0.9, "market": 0.5, "office": 0.7, "religious": 0.4, "heritage": 0.2}
CAR_COLORS = [(0.85, 0.85, 0.83), (0.62, 0.63, 0.64), (0.35, 0.36, 0.38), (0.05, 0.05, 0.06),
              (0.55, 0.06, 0.05), (0.08, 0.18, 0.40)]  # white, silver, grey, black, red, blue
AUTO_SHARE = 0.3


def project(lon, lat):  # must match build_script.project
    return (EARTH_R * math.radians(lon - LON0) * math.cos(math.radians(LAT0)),
            EARTH_R * math.radians(lat - LAT0))


def in_bbox(lat, lon):
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


def load_behavior_style():
    import importlib.util
    spec = importlib.util.spec_from_file_location("agents_instancer", ARGUS / "phase9" / "agents_instancer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.BEHAVIOR_STYLE


# ---------- OSM ----------

def parse_osm():
    root = ET.parse(HERE / "pune_center.osm").getroot()
    nodes, ways = {}, []
    for el in root:
        if el.tag == "node":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            nodes[el.get("id")] = (float(el.get("lat")), float(el.get("lon")), tags)
        elif el.tag == "way":
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            if "highway" in tags:
                ways.append((el.get("id"), [n.get("ref") for n in el.findall("nd")], tags))
    return nodes, ways


def build_graph(nodes, ways):
    xy, adj, edge_hw = {}, {}, {}
    for wid, refs, tags in ways:
        hw = tags["highway"]
        if hw not in ROAD_CROWD:
            continue
        for a, b in zip(refs, refs[1:]):
            if a not in nodes or b not in nodes or not in_bbox(*nodes[a][:2]) or not in_bbox(*nodes[b][:2]):
                continue
            for n in (a, b):
                xy.setdefault(n, project(nodes[n][1], nodes[n][0]))
            d = math.dist(xy[a], xy[b])
            adj.setdefault(a, {})[b] = d
            adj.setdefault(b, {})[a] = d
            edge_hw[frozenset((a, b))] = hw
    # keep the largest connected component so every snapped building is reachable
    seen, best = set(), set()
    for s in adj:
        if s in seen:
            continue
        comp, stack = set(), [s]
        while stack:
            n = stack.pop()
            if n in comp:
                continue
            comp.add(n)
            stack.extend(adj[n])
        seen |= comp
        best = max(best, comp, key=len)
    adj = {n: {m: d for m, d in nb.items() if m in best} for n, nb in adj.items() if n in best}
    return {n: xy[n] for n in best}, adj, edge_hw


def dijkstra(adj, src, penalty=None):
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist[n]:
            continue
        for m, w in adj[n].items():
            if penalty and frozenset((n, m)) in penalty:
                w *= 1.8
            nd = d + w
            if nd < dist.get(m, math.inf):
                dist[m], prev[m] = nd, n
                heapq.heappush(pq, (nd, m))
    return prev


def walk_back(prev, src, dst):
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


def resample(poly, step):
    out = [poly[0]]
    for a, b in zip(poly, poly[1:]):
        L = math.dist(a, b)
        for i in range(1, max(1, int(L // step)) + 1):
            t = min(1.0, i * step / L) if L else 1.0
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def poly_length(poly):
    return sum(math.dist(a, b) for a, b in zip(poly, poly[1:]))


def point_at(poly, cum, s):
    """Position and unit tangent at arc length s along poly (cum = cumulative lengths)."""
    i = max(0, min(int(np.searchsorted(cum, s, side="right")) - 1, len(poly) - 2))
    seg = cum[i + 1] - cum[i]
    t = (s - cum[i]) / seg if seg else 0.0
    (x0, y0), (x1, y1) = poly[i], poly[i + 1]
    tx, ty = (x1 - x0, y1 - y0)
    n = math.hypot(tx, ty) or 1.0
    return (x0 + tx * t, y0 + ty * t), (tx / n, ty / n)


def dedupe(poly, eps=0.05):
    out = [poly[0]]
    for p in poly[1:]:
        if math.dist(p, out[-1]) > eps:
            out.append(p)
    return out


def chaikin(poly, iterations=2):
    """Corner-cutting: rounds sharp polyline corners so headings turn gradually, keeps the end points."""
    for _ in range(iterations):
        if len(poly) < 3:
            return poly
        out = [poly[0]]
        for (ax, ay), (bx, by) in zip(poly, poly[1:]):
            out += [(0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by), (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)]
        out.append(poly[-1])
        poly = out
    return poly


def offset_path(poly, offsets):
    """Parallel path at a per-vertex signed offset (+ = left of travel). Mitred at corners, capped at 2x."""
    n = len(poly)
    dirs = []
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        d = math.hypot(bx - ax, by - ay) or 1.0
        dirs.append(((bx - ax) / d, (by - ay) / d))
    out = []
    for i, (x, y) in enumerate(poly):
        d0, d1 = dirs[max(0, i - 1)], dirs[min(i, n - 2)]
        tx, ty = d0[0] + d1[0], d0[1] + d1[1]
        tl = math.hypot(tx, ty)
        tx, ty = (tx / tl, ty / tl) if tl > 1e-6 else d1
        nx, ny = -ty, tx
        miter = min(2.0, 1.0 / max(0.5, nx * -d1[1] + ny * d1[0]))
        out.append((x + nx * offsets[i] * miter, y + ny * offsets[i] * miter))
    return out


def track(poly):
    """Smoothed path ready for animation: (points, cumulative lengths, total length)."""
    poly = chaikin(dedupe(poly))
    cum = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(poly, poly[1:])])])
    return poly, cum, float(cum[-1])


# ---------- city + citizens + simulator ----------

def read_buildings():
    stage = Usd.Stage.Open(str(HERE / "city_base.usda"))
    out = []
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        mesh = UsdGeom.Mesh(prim.GetChildren()[0])
        pts = [p for p in mesh.GetPointsAttr().Get() if abs(p[2]) < 1e-4]
        tags = json.loads(prim.GetAttribute("urbantwin:osmTags").Get())
        out.append({
            "name": prim.GetName(),
            "cls": prim.GetAttribute("urbantwin:materialClass").Get(),
            "label": tags.get("name") or tags.get("name:en") or prim.GetName(),
            "xy": (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)),
        })
    return out


def build_city(nodes, ways):
    gxy, adj, edge_hw = build_graph(nodes, ways)
    ids = list(gxy)
    arr = np.array([gxy[n] for n in ids])

    def snap(xy):
        d = np.hypot(arr[:, 0] - xy[0], arr[:, 1] - xy[1])
        i = int(d.argmin())
        return ids[i], float(d[i])

    trees = np.array([project(n[1], n[0]) for n in nodes.values() if n[2].get("natural") == "tree" and in_bbox(*n[:2])])
    stops = np.array([project(n[1], n[0]) for n in nodes.values() if "public_transport" in n[2] and in_bbox(*n[:2])])

    xmin, ymin = project(BBOX["west"], BBOX["south"])
    xmax, ymax = project(BBOX["east"], BBOX["north"])

    def zone_of(xy):
        c = min(2, max(0, int(3 * (xy[0] - xmin) / (xmax - xmin))))
        r = min(2, max(0, int(3 * (xy[1] - ymin) / (ymax - ymin))))
        return f"Zone {'ABC'[c]}{r + 1}"

    zones = []
    for c in range(3):
        for r in range(3):
            zid = f"Zone {'ABC'[c]}{r + 1}"
            n_trees = sum(1 for t in trees if zone_of(t) == zid)
            zones.append({"id": zid, "drainage": 0.5, "shade": round(min(1.0, n_trees / 60.0), 2)})

    buildings = read_buildings()
    dests, homes = [], []
    for b in buildings:
        node, d = snap(b["xy"])
        if d > 40.0:
            continue
        b["node"] = node
        (dests if b["cls"] in SIM_TYPE else homes).append(b)
    rng = random.Random(7)
    homes = rng.sample(homes, min(HOMES, len(homes)))

    sim_buildings = []
    for b in dests:
        t = SIM_TYPE[b["cls"]]
        sim_buildings.append({"id": b["name"], "name": b["label"], "type": t, "zone": zone_of(b["xy"]),
                              "capacity": CAPACITY[t], "cooling": COOLING[t], "flood_exposure": 0.3})
    for b in homes:
        sim_buildings.append({"id": b["name"], "name": b["label"], "type": "residential", "zone": zone_of(b["xy"]),
                              "capacity": 0, "cooling": 0.3, "flood_exposure": 0.3})

    routes, polylines, segment_hw = [], {}, {}

    def add_route(start, end, node_path):
        poly = [start["xy"]] + [gxy[n] for n in node_path] + [end["xy"]]
        samples = np.array(resample(poly, 5.0))
        L = poly_length(poly)
        shade = 0.0
        if len(trees):
            d = np.min(np.hypot(samples[:, None, 0] - trees[None, :, 0], samples[:, None, 1] - trees[None, :, 1]), axis=1)
            shade = float((d < 10.0).mean())
        transit = 0.0
        if len(stops):
            d = np.min(np.hypot(stops[:, None, 0] - samples[None, :, 0], stops[:, None, 1] - samples[None, :, 1]), axis=1)
            transit = min(1.0, 0.5 * int((d < 40.0).sum()))
        seg_len = [(edge_hw[frozenset((a, b))], math.dist(gxy[a], gxy[b])) for a, b in zip(node_path, node_path[1:])]
        tot = sum(l for _, l in seg_len) or 1.0
        crowd = sum(ROAD_CROWD[h] * l for h, l in seg_len) / tot if seg_len else 0.3
        rid = f"R{len(routes) + 1}"
        routes.append({"id": rid, "start": start["name"], "end": end["name"], "distance_km": round(L / 1000, 3),
                       "shade": round(shade, 2), "greenery": round(shade, 2), "drainage": 0.5,
                       "base_crowding": round(crowd, 2), "transit": round(transit, 2), "capacity_pph": 1500,
                       "via_zones": sorted({zone_of(tuple(s)) for s in samples})})
        # animate street-to-street only: building centroids are inside walls (distance above still counts the door walk)
        polylines[rid] = [gxy[n] for n in node_path]
        segment_hw[rid] = [edge_hw[frozenset((a, b))] for a, b in zip(node_path, node_path[1:])]

    for dst in dests:
        prev = dijkstra(adj, dst["node"])
        for home in homes:
            if home["node"] == dst["node"]:
                continue
            p1 = walk_back(prev, dst["node"], home["node"])[::-1]  # home -> dest
            add_route(home, dst, p1)
            pen = {frozenset(e) for e in zip(p1, p1[1:])}
            p2 = walk_back(dijkstra(adj, home["node"], pen), home["node"], dst["node"])
            if p2 != p1:
                add_route(home, dst, p2)

    city = {
        "schema_version": 1,
        "description": ("Simulator city for central Pune generated by pune_sim.py from pune_center.osm and "
                        "city_base.usda. Buildings are OSM buildings; routes are real OSM walking paths with "
                        "measured lengths. Shade = share of route within 10 m of a real OSM tree. Drainage, "
                        "flood exposure, capacity, cooling and base crowding are fixed heuristics. Do not hand-edit."),
        "zones": zones, "buildings": sim_buildings, "routes": routes,
    }
    return city, polylines, segment_hw, len(gxy)


def run(cmd, cwd=HERE):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    res = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    print(res.stdout[-1500:], flush=True)
    if res.returncode:
        raise RuntimeError(f"{Path(str(cmd[1])).name} failed: {(res.stderr or res.stdout)[-3000:]}")


# ---------- USD layers ----------

def set_time(stage):
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(TIMECODES[-1])
    stage.SetTimeCodesPerSecond(FPS)
    stage.SetFramesPerSecond(FPS)


def new_layer(name):
    path = HERE / name  # name may also be an absolute Path (per-run staging dirs)
    path.unlink(missing_ok=True)  # CreateNew refuses to overwrite
    stage = Usd.Stage.CreateNew(str(path))
    stage.SetMetadata("upAxis", UsdGeom.Tokens.z)
    stage.SetMetadata("metersPerUnit", 1.0)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    set_time(stage)
    return stage


def preview_material(stage, path, color, roughness=0.6):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, f"{path}/PreviewSurface")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def part(stage, path, pts, faces, color, mat):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in pts])
    m.CreateFaceVertexCountsAttr([len(f) for f in faces])
    m.CreateFaceVertexIndicesAttr([i for f in faces for i in f])
    xs, ys, zs = zip(*pts)
    m.CreateExtentAttr([(min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))])
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    m.CreateDoubleSidedAttr(True)
    m.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(mat)


def prism(poly, z0, z1):
    """Vertical prism over a CCW 2D footprint -> (points, faces)."""
    n = len(poly)
    pts = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    faces = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return pts, faces


def rect(cx, cy, sx, sy):
    return [(cx - sx / 2, cy - sy / 2), (cx + sx / 2, cy - sy / 2), (cx + sx / 2, cy + sy / 2), (cx - sx / 2, cy + sy / 2)]


def circle(cx, cy, r, n):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def wheel(cx, cy, r, w, n=10):
    """Cylinder with its axis along Y (so it rolls along +X)."""
    ring = [(cx + r * math.cos(2 * math.pi * i / n), r + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    pts = [(x, cy - w / 2, z) for x, z in ring] + [(x, cy + w / 2, z) for x, z in ring]
    faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    faces += [[i, n + i, n + (i + 1) % n, (i + 1) % n] for i in range(n)]
    return pts, faces


class Mats:
    """One UsdPreviewSurface per colour, shared across prototypes."""
    def __init__(self, stage, root):
        self.stage, self.root, self.cache = stage, root, {}

    def __call__(self, color, roughness=0.6):
        key = (tuple(round(c, 3) for c in color), roughness)
        if key not in self.cache:
            self.cache[key] = preview_material(self.stage, f"{self.root}/m{len(self.cache)}", color, roughness)
        return self.cache[key]


def person_proto(stage, path, shirt, mats):
    """~1.7 m low-poly pedestrian facing +X: legs, torso (behaviour colour), arms, head."""
    UsdGeom.Xform.Define(stage, path)
    trousers, skin = (0.12, 0.13, 0.17), (0.48, 0.32, 0.22)
    for name, (pts, faces), col in [
        ("LegL", prism(circle(0, 0.09, 0.075, 6), 0.0, 0.86), trousers),
        ("LegR", prism(circle(0, -0.09, 0.075, 6), 0.0, 0.86), trousers),
        ("Torso", prism(rect(0, 0, 0.24, 0.40), 0.86, 1.44), shirt),
        ("ArmL", prism(circle(0, 0.25, 0.05, 6), 0.90, 1.42), shirt),
        ("ArmR", prism(circle(0, -0.25, 0.05, 6), 0.90, 1.42), shirt),
        ("Head", prism(circle(0, 0, 0.105, 8), 1.47, 1.70), skin),
    ]:
        part(stage, f"{path}/{name}", pts, faces, col, mats(col, 0.7))
    return Sdf.Path(path)


def car_proto(stage, path, paint, mats):
    """4.2 m hatchback facing +X: body, glass cabin, four wheels."""
    UsdGeom.Xform.Define(stage, path)
    part(stage, f"{path}/Body", *prism(rect(0, 0, 4.2, 1.75), 0.28, 0.95), paint, mats(paint, 0.3))
    part(stage, f"{path}/Cabin", *prism(rect(-0.25, 0, 2.3, 1.55), 0.95, 1.45), (0.07, 0.09, 0.11), mats((0.07, 0.09, 0.11), 0.1))
    for i, (x, y) in enumerate([(1.35, 0.78), (1.35, -0.78), (-1.35, 0.78), (-1.35, -0.78)]):
        part(stage, f"{path}/Wheel{i}", *wheel(x, y, 0.31, 0.22), (0.04, 0.04, 0.04), mats((0.04, 0.04, 0.04), 0.8))
    return Sdf.Path(path)


def auto_proto(stage, path, mats):
    """Pune auto-rickshaw facing +X: black lower body, yellow canopy, three wheels."""
    UsdGeom.Xform.Define(stage, path)
    black, yellow = (0.05, 0.05, 0.05), (0.92, 0.72, 0.06)
    part(stage, f"{path}/Body", *prism(rect(0, 0, 2.6, 1.3), 0.22, 0.95), black, mats(black, 0.4))
    part(stage, f"{path}/Canopy", *prism(rect(-0.1, 0, 2.4, 1.36), 0.95, 1.75), yellow, mats(yellow, 0.5))
    for i, (x, y) in enumerate([(1.0, 0.0), (-0.85, 0.58), (-0.85, -0.58)]):
        part(stage, f"{path}/Wheel{i}", *wheel(x, y, 0.22, 0.14, 8), (0.04, 0.04, 0.04), mats((0.04, 0.04, 0.04), 0.8))
    return Sdf.Path(path)


def yaw_quat(tx, ty):
    half = math.atan2(ty, tx) / 2
    return Gf.Quath(math.cos(half), 0, 0, math.sin(half))


def write_agents(citizens, routes, speeds, style, out_path):
    """One arm (before or after) of a simulator report -> animated PointInstancer layer."""
    stage = new_layer(out_path)
    UsdGeom.Scope.Define(stage, "/World/Agents")
    inst = UsdGeom.PointInstancer.Define(stage, "/World/Agents/Walkers")
    names = list(style)
    mats = Mats(stage, "/World/Agents/Materials")
    inst.CreatePrototypesRel().SetTargets(
        [person_proto(stage, f"/World/Agents/Walkers/Prototypes/{n}", style[n], mats) for n in names])

    rng = random.Random(11)  # same seed per arm: a citizen keeps its timing when Before/After is toggled
    ordered = sorted(speeds.values())
    walkers = []
    for c in citizens:
        poly, hws = routes["polylines"][c["route"]], routes["hw"][c["route"]]
        if c["home"] != routes["start"][c["route"]]:
            poly, hws = poly[::-1], hws[::-1]
        # Keep left (India): each direction of travel uses the pavement on its own left, so oncoming walkers are
        # on opposite pavements. Distance from the kerb grows with speed, so faster walkers overtake on a
        # different line instead of passing through slower ones.
        rank = ordered.index(speeds[c["id"]]) / max(1, len(ordered) - 1)
        kerb = [(ROAD_WIDTH[h] / 2 + 0.5 + 1.1 * rank) if h not in FOOTWAY_TYPES else (0.1 + 0.8 * rank) for h in hws]

        def side_path(points, kerbs):
            offs = [max(kerbs[max(0, i - 1)], kerbs[min(i, len(kerbs) - 1)]) for i in range(len(points))]
            return chaikin(dedupe(offset_path(points, offs)))
        # One closed loop: out on the left pavement, cross the street at the destination, back on the other
        # pavement, cross again at home. Continuous motion, no jump between pavements.
        loop = side_path(poly, kerb) + side_path(poly[::-1], kerb[::-1])
        loop.append(loop[0])
        cum = np.concatenate([[0.0], np.cumsum([math.dist(a, b) for a, b in zip(loop, loop[1:])])])
        walkers.append({"poly": loop, "cum": cum, "L": float(cum[-1]), "v": speeds[c["id"]] / 3.6 * TIME_SCALE,
                        "s0": rng.uniform(0, float(cum[-1])), "proto": names.index(c["behavior"])})
    inst.CreateProtoIndicesAttr([w["proto"] for w in walkers])
    inst.CreateIdsAttr(list(range(len(walkers))))
    pos_attr, ori_attr = inst.CreatePositionsAttr(), inst.CreateOrientationsAttr()
    for k, code in enumerate(TIMECODES):
        t = k / SAMPLE_HZ
        pts, oris = [], []
        for w in walkers:
            (x, y), (tx, ty) = point_at(w["poly"], w["cum"], (w["s0"] + w["v"] * t) % w["L"])
            pts.append(Gf.Vec3f(x, y, 0.0))
            oris.append(yaw_quat(tx, ty))
        pos_attr.Set(Vt.Vec3fArray(pts), code)
        ori_attr.Set(Vt.QuathArray(oris), code)
    inst.GetPrim().CreateAttribute("urbantwin:note", Sdf.ValueTypeNames.String, custom=True).Set(
        "One low-poly pedestrian per simulated citizen on its simulator-chosen route at its survey-calibrated "
        "speed, in real time, keeping left on the pavement beside the carriageway, looping out and back "
        "across the street at each end. Shirt colour = behaviour "
        "(one equilibrium). No collision avoidance: walkers can brush past each other.")
    stage.GetRootLayer().Save()
    return len(walkers)


def chain_streets(nodes, ways):
    """In-box carriageway runs as node-ref lists, with OSM way pieces of one street joined end to end.

    OSM splits a street into many short ways; driving each piece separately makes vehicles turn round at
    every split and meet head-on there. Pieces are joined where exactly two of them meet at a node that is
    not a junction (degree 2 in the carriageway graph) and they share a road class.
    """
    runs = []
    for _, refs, tags in ways:
        if tags["highway"] not in CAR_ROADS:
            continue
        oneway = tags.get("oneway") in ("yes", "true", "1", "-1")
        if tags.get("oneway") == "-1":
            refs = refs[::-1]  # store one-way streets in their legal direction of travel
        run = []
        for r in refs + [None]:
            if r is not None and r in nodes and in_bbox(*nodes[r][:2]):
                run.append(r)
                continue
            if len(run) >= 2:
                runs.append([(tags["highway"], oneway), run])
            run = []
    neighbours = {}
    for _, run in runs:
        for a, b in zip(run, run[1:]):
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
    merged = True
    while merged:
        merged = False
        ends = {}
        for i, (_, run) in enumerate(runs):
            for node in (run[0], run[-1]):
                ends.setdefault(node, []).append(i)
        for node, idx in ends.items():
            if len(idx) != 2 or idx[0] == idx[1] or len(neighbours[node]) != 2:
                continue
            (kind_a, a), (kind_b, b) = runs[idx[0]], runs[idx[1]]
            if kind_a != kind_b:
                continue
            if kind_a[1]:  # one-way: only join head-to-tail, never reverse a legal direction
                if a[-1] == node and b[0] == node:
                    joined = a + b[1:]
                elif b[-1] == node and a[0] == node:
                    joined = b + a[1:]
                else:
                    continue
            else:
                a = a if a[-1] == node else a[::-1]
                b = b if b[0] == node else b[::-1]
                joined = a + b[1:]
            runs[idx[0]] = [kind_a, joined]
            del runs[idx[1]]
            merged = True
            break
    return [(hw, oneway, run) for (hw, oneway), run in runs]


def write_traffic(nodes, ways):
    stage = new_layer("traffic.usdc")
    UsdGeom.Scope.Define(stage, "/World/Traffic")
    inst = UsdGeom.PointInstancer.Define(stage, "/World/Traffic/Cars")
    mats = Mats(stage, "/World/Traffic/Materials")
    protos = [car_proto(stage, f"/World/Traffic/Cars/Prototypes/car{i}", col, mats) for i, col in enumerate(CAR_COLORS)]
    protos.append(auto_proto(stage, "/World/Traffic/Cars/Prototypes/auto", mats))
    inst.CreatePrototypesRel().SetTargets(protos)
    auto_index = len(protos) - 1

    rng = random.Random(23)
    cars = []
    for hw, oneway, refs in chain_streets(nodes, ways):
        run_ = dedupe([project(nodes[r][1], nodes[r][0]) for r in refs])
        if len(run_) < 2:
            continue
        L = poly_length(run_)
        n = int(L // CAR_SPACING_M)
        v, phase = CAR_SPEED_KMH / 3.6 * TIME_SCALE * rng.uniform(0.85, 1.15), rng.uniform(0, 2 * L)
        if oneway:
            # one carriageway of a divided road: a single stream in the legal direction, entering upstream
            lanes = (track(run_),)
            for i in range(n):
                cars.append({"lanes": lanes, "L": L, "s0": phase + i * L / n, "v": v})
            continue
        lane = ROAD_WIDTH[hw] / 4  # centre of the left-hand lane
        lanes = (track(offset_path(run_, [lane] * len(run_))),
                 track(offset_path(run_[::-1], [lane] * len(run_))))
        # one speed per street and even spacing on the round trip, so vehicles never run through each other
        for i in range(n):
            cars.append({"lanes": lanes, "L": L, "s0": phase + i * 2 * L / n, "v": v})
    # illustrative mix: ~30% auto-rickshaws, rest cars in common paint colours
    inst.CreateProtoIndicesAttr([auto_index if rng.random() < AUTO_SHARE else rng.randrange(len(CAR_COLORS))
                                 for _ in cars])
    inst.CreateIdsAttr(list(range(len(cars))))
    pos_attr, ori_attr = inst.CreatePositionsAttr(), inst.CreateOrientationsAttr()
    for k, code in enumerate(TIMECODES):
        t = k / SAMPLE_HZ
        pts, oris = [], []
        for c in cars:
            if len(c["lanes"]) == 1:  # one-way: loop downstream, re-entering at the upstream end
                u = (c["s0"] + c["v"] * t) % c["L"]
                path, cum, length = c["lanes"][0]
            else:
                u = (c["s0"] + c["v"] * t) % (2 * c["L"])
                # out on the left lane, back on the other side's left lane (India drives on the left)
                path, cum, length = c["lanes"][0] if u < c["L"] else c["lanes"][1]
            (x, y), (tx, ty) = point_at(path, cum, (u % c["L"]) / c["L"] * length)
            pts.append(Gf.Vec3f(x, y, 0.02))
            oris.append(yaw_quat(tx, ty))
        pos_attr.Set(Vt.Vec3fArray(pts), code)
        ori_attr.Set(Vt.QuathArray(oris), code)
    inst.GetPrim().CreateAttribute("urbantwin:illustrative", Sdf.ValueTypeNames.Bool, custom=True).Set(True)
    inst.GetPrim().CreateAttribute("urbantwin:note", Sdf.ValueTypeNames.String, custom=True).Set(
        f"ILLUSTRATIVE traffic: no traffic data. One vehicle per {CAR_SPACING_M:g} m of road at ~{CAR_SPEED_KMH:g} km/h, "
        f"{AUTO_SHARE:.0%} auto-rickshaws, real time, driving on the left. One speed per road with even "
        "spacing, so vehicles on a road never overlap; vehicles on crossing roads can still meet at junctions.")
    stage.GetRootLayer().Save()
    return len(cars)


ARMS = (("before", "Stressed"), ("after", "Intervention"))  # report arm -> Kit demoState variant


def write_live_stage():
    """main_live.usda: traffic + static city, and a /World demoState variant choosing which arm's walkers show.

    The variant names match what the Kit urbantwin.view_commands handler already sets for Before/After, so the
    dashboard toggle drives Pune with no Kit changes. Pune's "after" is the simulator's intervention arm (the same
    citizens re-simulated under the applied intervention), not proposal geometry.
    """
    stage = new_layer("main_live.usda")  # keep the stage alive or its root layer expires
    root = stage.GetRootLayer()
    for sub in ("traffic.usdc", "main.usda"):
        root.subLayerPaths.append(sub)
    world = stage.GetPrimAtPath("/World")
    vset = world.GetVariantSets().AddVariantSet("demoState")
    for arm, variant in ARMS:
        vset.AddVariant(variant)
        vset.SetVariantSelection(variant)
        with vset.GetVariantEditContext():
            stage.OverridePrim("/World/Agents").GetReferences().AddReference(f"agents_{arm}.usdc", "/World/Agents")
    vset.SetVariantSelection("Stressed")
    root.Save()


def prepare():
    """One-time: simulator city, survey citizens placed on it, route polylines, illustrative traffic."""
    nodes, ways = parse_osm()
    city, polylines, segment_hw, graph_nodes = build_city(nodes, ways)
    (HERE / "city_pune.json").write_text(json.dumps(city, indent=1), encoding="utf-8")
    routes = {"start": {r["id"]: r["start"] for r in city["routes"]}, "polylines": polylines, "hw": segment_hw}
    (HERE / "pune_routes.json").write_text(json.dumps(routes), encoding="utf-8")
    print(f"city_pune.json: {len(city['buildings'])} buildings, {len(city['routes'])} routes, graph {graph_nodes} nodes")
    run([PY, ARGUS / "phase10" / "assign_homes.py", "--city", HERE / "city_pune.json",
         "--out", HERE / "citizens_pune.json", "--count", CITIZENS])
    n_cars = write_traffic(nodes, ways)
    write_live_stage()
    return city, graph_nodes, n_cars


def simulate(report_path, *, temperature=None, humidity=None, rainfall=None, population=None, interventions=()):
    """Run the unmodified Argus simulator on the Pune city. Omitted scenario values use the simulator defaults."""
    cmd = [PY, ARGUS / "Simulation" / "main.py", HERE / "citizens_pune.json", HERE / "city_pune.json",
           "--output", report_path]
    for flag, value in (("--temperature", temperature), ("--humidity", humidity),
                        ("--rainfall", rainfall), ("--population", population)):
        if value is not None:
            cmd += [flag, value]
    for intervention in interventions:
        cmd += ["--intervention-id", intervention]
    run(cmd, cwd=ARGUS / "Simulation")
    # the command is returned so run manifests can record it (analytics reads the city file from it)
    return json.loads(Path(report_path).read_text(encoding="utf-8")), [str(c) for c in cmd]


def animate(report, out_dir):
    """Both arms of a report -> agents_before.usdc / agents_after.usdc in out_dir. Returns walker counts."""
    routes = json.loads((HERE / "pune_routes.json").read_text(encoding="utf-8"))
    speeds = {c["id"]: c["walking_speed_kmh"]
              for c in json.loads((HERE / "citizens_pune.json").read_text(encoding="utf-8"))["citizens"]}
    style = load_behavior_style()
    return {arm: write_agents(report[arm]["citizens"], routes, speeds, style, Path(out_dir) / f"agents_{arm}.usdc")
            for arm, _ in ARMS}


def behaviour_counts(citizens):
    counts = {}
    for c in citizens:
        counts[c["behavior"]] = counts.get(c["behavior"], 0) + 1
    return counts


def main():
    city, graph_nodes, n_cars = prepare()
    report, _ = simulate(HERE / "sim_report_pune.json")
    walkers = animate(report, HERE)

    # generated facts go to a gitignored sidecar; manifest.json stays the committed Blender build record
    generated = read_generated()
    generated["simulation"] = {
        "note": ("User-approved extension beyond the original spec (which said no simulation files). "
                 "Agents come from the unmodified Argus simulator; cars are illustrative."),
        "simulator": "Argus Simulation/main.py (unmodified)",
        "citizens": len(report["before"]["citizens"]),
        "citizen_calibration": "Argus phase10 survey, 41 participants - not Pune residents",
        "home_destination": "phase10/assign_homes.py trip heuristic, not survey data",
        "sim_buildings": len(city["buildings"]), "sim_routes": len(city["routes"]),
        "pedestrian_graph_nodes": graph_nodes,
        "default_scenario": report["scenario"],
        "behaviour_counts": {arm: behaviour_counts(report[arm]["citizens"]) for arm, _ in ARMS},
        "headline_metrics_before": report["before"]["metrics"],
        "heuristic_inputs": ("drainage 0.5, flood_exposure 0.3, capacity/cooling by type, base_crowding by road "
                             "class, route greenery = route shade (share within 10 m of an OSM tree)"),
        "walkers": walkers, "vehicles_illustrative": n_cars, "auto_rickshaw_share": AUTO_SHARE,
        "agent_models": "low-poly people and vehicles, illustrative geometry (not data)",
        "before_after": "demoState variant on /World: Stressed = before arm, Intervention = simulator after arm",
        "playback": f"{DURATION_S} s loop in real time, positions sampled {SAMPLE_HZ}x/s and interpolated by USD",
    }
    write_generated(generated)
    print(f"walkers {walkers}, vehicles {n_cars}. Next: run pune_view.py")


GENERATED = HERE / "manifest.generated.json"


def read_generated():
    try:
        return json.loads(GENERATED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_generated(data):
    GENERATED.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
