"""
UrbanTwin AI - Central Pune build script.
Run headless: "<blender.exe>" -b -P build_script.py
Pipeline: parse pune_center.osm -> Blender import/cleanup/heights/materials ->
USD export -> pxr post-process -> validate. All in one file per spec section 8.
"""
import bpy
import bmesh
import json
import math
import os
import datetime
from xml.etree import ElementTree as ET
from mathutils import Matrix

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OSM_PATH = os.path.join(PROJECT_DIR, "pune_center.osm")

LON0, LAT0 = 73.8553, 18.5195
BBOX = dict(south=18.5150, north=18.5240, west=73.8506, east=73.8600)
EARTH_R = 6378137.0

ROAD_WIDTHS = {
    "primary": 10.0, "trunk": 10.0,
    "secondary": 8.0,
    "tertiary": 6.0, "residential": 6.0,
    "service": 4.0,
    "footway": 2.0, "path": 2.0, "pedestrian": 2.0,
}
# Not in the spec's width table; user approved (2026-10-24) mapping each to its nearest spec class.
EXTENDED_WIDTHS = {
    "living_street": ("residential", 6.0), "trunk_link": ("trunk", 10.0),
    "secondary_link": ("secondary", 8.0), "steps": ("footway", 2.0), "corridor": ("footway", 2.0),
}
ROAD_WIDTHS.update({k: w for k, (_, w) in EXTENDED_WIDTHS.items()})
FOOTWAY_TYPES = {"footway", "path", "pedestrian", "steps", "corridor"}

GREEN_LEISURE = {"park", "garden", "pitch", "playground", "recreation_ground", "golf_course", "nature_reserve"}
GREEN_LANDUSE = {"grass", "forest", "meadow", "recreation_ground", "orchard", "vineyard", "allotments"}
GREEN_NATURAL = {"wood", "scrub", "grassland", "heath", "wetland"}

HEIGHT_CLASS = {
    "residential": 9.0, "commercial": 12.0, "retail": 12.0, "office": 15.0,
    "religious": 10.0, "education": 12.0, "healthcare": 15.0, "industrial": 8.0,
}

MATERIAL_COLORS = {
    "residential": ((0.82, 0.70, 0.55), 0.70),
    "commercial":  ((0.55, 0.60, 0.70), 0.50),
    "retail":      ((0.75, 0.55, 0.45), 0.50),
    "office":      ((0.45, 0.55, 0.60), 0.40),
    "religious":   ((0.80, 0.75, 0.55), 0.60),
    "education":   ((0.60, 0.70, 0.55), 0.60),
    "healthcare":  ((0.85, 0.60, 0.60), 0.50),
    "civic":       ((0.65, 0.65, 0.70), 0.55),
    "industrial":  ((0.55, 0.50, 0.45), 0.75),
    "hotel":       ((0.70, 0.50, 0.65), 0.45),
    "heritage":    ((0.70, 0.45, 0.30), 0.65),
    "other":       ((0.65, 0.65, 0.60), 0.60),
}
ROAD_COLOR = ((0.35, 0.35, 0.35), 0.9)
FOOTWAY_COLOR = ((0.55, 0.52, 0.45), 0.85)
GREEN_COLOR = ((0.40, 0.60, 0.35), 0.9)
TRANSIT_COLOR = ((0.80, 0.20, 0.20), 0.6)
TREE_TRUNK_COLOR = ((0.30, 0.20, 0.12), 0.8)
TREE_CANOPY_COLOR = ((0.25, 0.45, 0.20), 0.8)
GROUND_COLOR = ((0.45, 0.42, 0.36), 0.95)

manifest = {
    "bbox": BBOX,
    "origin_lon0_lat0": [LON0, LAT0],
    "projection": "local tangent-plane equirectangular (x = R*radians(lon-lon0)*cos(radians(lat0)), y = R*radians(lat-lat0))",
    "projection_reason": (
        "All layers use the scripted local-metres projection, matching the London scene's conventions. "
        "UTM 43N was not used for any layer because UTM grid north is ~0.36 deg off true north at this "
        "location, which would misalign UTM-projected layers against scripted ones by ~3 m at tile edges. "
        "The UTM 43N easting/northing of the origin is recorded below for reference only; no geometry was "
        "built from it."
    ),
    "import_path": "scripted (section 4 fallback projection) for buildings, roads, green spaces, trees. BlenderGIS not installed or used.",
    "blender_version": None,
    "counts": {},
    "height_source_counts": {},
    "material_class_counts": {},
    "skipped_buildings": [],
    "skipped_highways": {},
    "overpass": {},
    "attribution": "© OpenStreetMap contributors, ODbL",
}


# ---------- OSM parsing ----------

def parse_osm(path):
    tree = ET.parse(path)
    root = tree.getroot()
    nodes = {}
    ways = {}
    relations = {}
    osm_base = root.find("meta")
    manifest["overpass"]["osm_base_timestamp"] = osm_base.get("osm_base") if osm_base is not None else None
    for el in root:
        if el.tag == "node":
            nid = el.get("id")
            lat = float(el.get("lat"))
            lon = float(el.get("lon"))
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            nodes[nid] = (lat, lon, tags)
        elif el.tag == "way":
            wid = el.get("id")
            refs = [nd.get("ref") for nd in el.findall("nd")]
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            ways[wid] = {"refs": refs, "tags": tags}
        elif el.tag == "relation":
            rid = el.get("id")
            members = [(m.get("type"), m.get("ref"), m.get("role")) for m in el.findall("member")]
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            relations[rid] = {"members": members, "tags": tags}
    return nodes, ways, relations


def project(lon, lat):
    x = EARTH_R * math.radians(lon - LON0) * math.cos(math.radians(LAT0))
    y = EARTH_R * math.radians(lat - LAT0)
    return x, y


def haversine(n1, n2):
    """Great-circle metres between two (lat, lon, ...) nodes, WGS84 mean radius."""
    la1, lo1, la2, lo2 = map(math.radians, (n1[0], n1[1], n2[0], n2[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def in_bbox_latlon(lat, lon):
    return BBOX["south"] <= lat <= BBOX["north"] and BBOX["west"] <= lon <= BBOX["east"]


BBOX_XY = (
    *project(BBOX["west"], BBOX["south"]),
    *project(BBOX["east"], BBOX["north"]),
)  # (xmin, ymin, xmax, ymax)


def centroid_in_bbox(cx, cy):
    xmin, ymin, xmax, ymax = BBOX_XY
    return xmin <= cx <= xmax and ymin <= cy <= ymax


# ---------- UTM 43N (WGS84 Transverse Mercator, Snyder/USGS closed-form formulas) ----------

def latlon_to_utm(lat, lon, zone=43):
    a = 6378137.0
    f = 1.0 / 298.257223563
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    lon0 = math.radians(6 * zone - 183)
    phi = math.radians(lat)
    lam = math.radians(lon)

    N = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    T = math.tan(phi) ** 2
    C = ep2 * math.cos(phi) ** 2
    A = (lam - lon0) * math.cos(phi)
    M = a * (
        (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
        - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
        + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi)
        - (35 * e2 ** 3 / 3072) * math.sin(6 * phi)
    )
    easting = k0 * N * (
        A + (1 - T + C) * A ** 3 / 6
        + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120
    ) + 500000.0
    northing = k0 * (
        M + N * math.tan(phi) * (
            A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
            + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720
        )
    )
    return easting, northing


# ---------- geometry helpers ----------

def polygon_centroid(pts):
    n = len(pts)
    A = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        A += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    A *= 0.5
    if abs(A) < 1e-9:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return sum(xs) / n, sum(ys) / n
    return cx / (6 * A), cy / (6 * A)


def is_ccw(pts):
    area = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return area > 0


def dedup_consecutive(pts, tol=0.01):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < tol:
        out.pop()
    return out


def segments_intersect(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def polygon_self_intersects(pts):
    n = len(pts)
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            b1, b2 = pts[j], pts[(j + 1) % n]
            if segments_intersect(a1, a2, b1, b2):
                return True
    return False


def join_rings(segments):
    segments = [list(s) for s in segments]
    rings = []
    while segments:
        ring = segments.pop(0)
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, seg in enumerate(segments):
                if seg[0] == ring[-1]:
                    ring = ring + seg[1:]
                    segments.pop(i)
                    changed = True
                    break
                elif seg[-1] == ring[-1]:
                    ring = ring + list(reversed(seg))[1:]
                    segments.pop(i)
                    changed = True
                    break
                elif seg[-1] == ring[0]:
                    ring = seg[:-1] + ring
                    segments.pop(i)
                    changed = True
                    break
                elif seg[0] == ring[0]:
                    ring = list(reversed(seg))[:-1] + ring
                    segments.pop(i)
                    changed = True
                    break
        rings.append(ring)
    return rings


def clip_segment(p0, p1, box):
    xmin, ymin, xmax, ymax = box
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return None
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_polyline(pts, box):
    runs = []
    current = []
    for i in range(len(pts) - 1):
        c = clip_segment(pts[i], pts[i + 1], box)
        if c is None:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue
        a, b = c
        if not current:
            current = [a, b]
        elif math.hypot(current[-1][0] - a[0], current[-1][1] - a[1]) < 1e-6:
            current.append(b)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [a, b]
    if len(current) >= 2:
        runs.append(current)
    return runs


# ---------- classification ----------

def classify_building(tags):
    historic = tags.get("historic")
    if historic:
        return "heritage"
    amenity = tags.get("amenity", "")
    building = tags.get("building", "")
    tourism = tags.get("tourism")
    shop = tags.get("shop")
    office = tags.get("office")
    if amenity == "place_of_worship" or building in ("church", "mosque", "temple", "synagogue"):
        return "religious"
    if amenity in ("school", "university", "college", "kindergarten") or building in ("school", "university"):
        return "education"
    if amenity in ("hospital", "clinic", "doctors", "pharmacy") or building == "hospital":
        return "healthcare"
    if amenity in ("townhall", "public_building", "community_centre", "police", "fire_station", "courthouse") or building in ("civic", "public"):
        return "civic"
    if tourism == "hotel" or building == "hotel":
        return "hotel"
    if office:
        return "office"
    if shop:
        return "retail"
    if building in ("industrial", "warehouse", "factory"):
        return "industrial"
    if building in ("house", "residential", "apartments", "detached", "terrace", "semidetached_house", "bungalow", "dormitory"):
        return "residential"
    if amenity in ("restaurant", "cafe", "bar", "fast_food", "marketplace", "bank", "bureau_de_change"):
        return "commercial"
    if building == "commercial":
        return "commercial"
    if building == "retail":
        return "retail"
    return "other"


def parse_height_tag(val):
    if val is None:
        return None
    s = val.strip().lower().replace("meters", "").replace("metres", "").replace("m", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_levels_height(tags):
    bl = tags.get("building:levels")
    if bl is None:
        return None
    try:
        levels = float(bl)
    except ValueError:
        return None
    h = levels * 3.2
    rl = tags.get("roof:levels")
    if rl is not None:
        try:
            h += float(rl) * 3.2
        except ValueError:
            pass
    return h


# ---------- Blender scene helpers ----------

def ensure_collection(name):
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
    else:
        col = bpy.data.collections.new(name)
    scene_col = bpy.context.scene.collection
    if col.name not in scene_col.children:
        scene_col.children.link(col)
    return col


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)


def make_material(name, color, roughness):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*color, 1.0)
    return mat


def make_parent_empty(name, collection):
    empty = bpy.data.objects.new(name, None)
    collection.objects.link(empty)
    return empty


def finalize_object(bm, name, collection, material, parent=None):
    bmesh.ops.dissolve_degenerate(bm, dist=0.0001, edges=list(bm.edges))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    if material is not None:
        obj.data.materials.append(material)
    return obj


def point_in_polygon(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def make_building_bm(pts, height, holes=()):
    bm = bmesh.new()
    if holes:
        # bmesh faces cannot hold holes: scanfill outer+inner loops into a holed triangle cap
        edges = []
        for ring in [pts, *holes]:
            vs = [bm.verts.new((x, y, 0.0)) for x, y in ring]
            edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
        faces = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)["geom"]
        faces = [f for f in faces if isinstance(f, bmesh.types.BMFace)]
    else:
        faces = [bm.faces.new([bm.verts.new((x, y, 0.0)) for x, y in pts])]
    ret = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=(0, 0, height))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.01)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def faces_up(bm):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    down = [f for f in bm.faces if f.normal.z < 0]
    if down:
        bmesh.ops.reverse_faces(bm, faces=down)


def build_ribbon_bm(pts, width):
    bm = bmesh.new()
    half = width / 2.0
    n = len(pts)
    left = []
    right = []
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            dx, dy = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        else:
            dx1, dy1 = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
            dx2, dy2 = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            l1 = math.hypot(dx1, dy1) or 1.0
            l2 = math.hypot(dx2, dy2) or 1.0
            dx, dy = dx1 / l1 + dx2 / l2, dy1 / l1 + dy2 / l2
        length = math.hypot(dx, dy)
        if length < 1e-9:
            nx, ny = 0.0, 1.0
        else:
            nx, ny = -dy / length, dx / length
        x, y = pts[i]
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    lverts = [bm.verts.new((p[0], p[1], 0.0)) for p in left]
    rverts = [bm.verts.new((p[0], p[1], 0.0)) for p in right]
    for i in range(n - 1):
        bm.faces.new([lverts[i], lverts[i + 1], rverts[i + 1], rverts[i]])
    faces_up(bm)
    return bm


def build_polygon_bm(pts, holes=()):
    bm = bmesh.new()
    if holes:
        edges = []
        for ring in [pts, *holes]:
            vs = [bm.verts.new((x, y, 0.0)) for x, y in ring]
            edges += [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    else:
        bm.faces.new([bm.verts.new((x, y, 0.0)) for x, y in pts])
    faces_up(bm)
    return bm


def make_tree_bm():
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=6, radius1=0.15, radius2=0.15, depth=1.5, matrix=Matrix.Identity(4))
    bmesh.ops.translate(bm, verts=list(bm.verts), vec=(0, 0, 0.75))
    canopy = bmesh.new()
    bmesh.ops.create_cone(canopy, cap_ends=True, cap_tris=False, segments=8, radius1=1.2, radius2=0.0, depth=2.5, matrix=Matrix.Identity(4))
    bmesh.ops.translate(canopy, verts=list(canopy.verts), vec=(0, 0, 1.5 + 1.25))
    offset = len(bm.verts)
    vmap = {}
    for v in canopy.verts:
        nv = bm.verts.new(v.co)
        vmap[v] = nv
    for f in canopy.faces:
        bm.faces.new([vmap[v] for v in f.verts])
    canopy.free()
    bm.verts.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


# ---------- main build ----------

def main():
    manifest["blender_version"] = ".".join(str(v) for v in bpy.app.version)
    with open(os.path.join(PROJECT_DIR, "overpass_query.txt"), encoding="utf-8") as f:
        manifest["overpass"]["query"] = f.read()
    manifest["overpass"]["endpoint"] = "https://overpass-api.de/api/interpreter"
    # the download happened before this script; the file's mtime is when it landed on disk
    manifest["overpass"]["download_timestamp_utc"] = datetime.datetime.fromtimestamp(
        os.path.getmtime(OSM_PATH), datetime.timezone.utc).isoformat()

    utm_e, utm_n = latlon_to_utm(LAT0, LON0)
    manifest["utm43n_origin"] = {"easting": utm_e, "northing": utm_n, "epsg": "EPSG:32643"}

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

    clear_scene()
    col_buildings = ensure_collection("Buildings")
    col_roads = ensure_collection("Roads")
    col_footways = ensure_collection("PedestrianPaths")
    col_green = ensure_collection("GreenSpaces")
    col_transit = ensure_collection("Transit")
    col_trees = ensure_collection("Trees")
    # USD exporter builds prim hierarchy from object parenting, not collections
    par = {c.name: make_parent_empty(c.name, c) for c in (col_buildings, col_roads, col_footways, col_green, col_transit, col_trees)}

    materials = {cls: make_material(f"mat_{cls}", color, rough) for cls, (color, rough) in MATERIAL_COLORS.items()}
    mat_road = make_material("mat_road", *ROAD_COLOR)
    mat_footway = make_material("mat_footway", *FOOTWAY_COLOR)
    mat_green = make_material("mat_green", *GREEN_COLOR)
    mat_transit = make_material("mat_transit", *TRANSIT_COLOR)
    mat_canopy = make_material("mat_tree_canopy", *TREE_CANOPY_COLOR)

    nodes, ways, relations = parse_osm(OSM_PATH)

    # ---- buildings: ways ----
    building_candidates = []  # (name, pts, tags, osm_id)
    skipped = []

    def ring_to_pts(refs):
        """Closed ring of node refs -> (pts, None) or (None, reason). Centroid tested by caller."""
        if len(refs) >= 2 and refs[0] == refs[-1]:
            refs = refs[:-1]
        if any(r not in nodes for r in refs):
            return None, "referenced node(s) missing from downloaded data"
        pts = dedup_consecutive([project(nodes[r][1], nodes[r][0]) for r in refs])
        if len(pts) < 3:
            return None, "fewer than 3 distinct vertices"
        return pts, None

    def check_shape(pts):
        if polygon_self_intersects(pts):
            return "self-intersecting footprint"
        return None

    def centroid_of_refs(refs):
        known = [nodes[r] for r in refs if r in nodes]
        if not known:
            return None
        return polygon_centroid([project(n[1], n[0]) for n in known]) if len(known) >= 3 else project(known[0][1], known[0][0])

    for wid, way in ways.items():
        tags = way["tags"]
        if "building" not in tags:
            continue
        c = centroid_of_refs(way["refs"])
        if c is None or not centroid_in_bbox(*c):
            continue  # outside box: out of scope, not a skip
        pts, reason = ring_to_pts(way["refs"])
        reason = reason or check_shape(pts)
        if reason:
            skipped.append({"id": wid, "type": "way", "reason": reason})
            continue
        building_candidates.append((f"way_{wid}", pts, [], tags, wid))

    # ---- buildings: multipolygon relations, outer rings with their inner rings cut as holes ----
    relations_with_holes = 0
    for rid, rel in relations.items():
        tags = rel["tags"]
        if "building" not in tags:
            continue
        outer_segs, inner_segs = [], []
        for mtype, mref, role in rel["members"]:
            if mtype != "way" or mref not in ways:
                continue
            (inner_segs if role == "inner" else outer_segs).append(ways[mref]["refs"])
        if not outer_segs:
            skipped.append({"id": rid, "type": "relation", "reason": "no outer way members found"})
            continue
        outer_rings = join_rings(outer_segs)
        inner_pts = []
        inner_bad = None
        for ring in join_rings(inner_segs):
            if ring[0] != ring[-1]:
                inner_bad = "inner ring did not close"
                break
            ip, reason = ring_to_pts(ring)
            if reason or check_shape(ip):
                inner_bad = f"inner ring unusable ({reason or 'self-intersecting'})"
                break
            inner_pts.append(ip)
        for idx, ring in enumerate(outer_rings):
            c = centroid_of_refs(ring)
            if c is None or not centroid_in_bbox(*c):
                continue
            if ring[0] != ring[-1] or len(ring) < 4:
                skipped.append({"id": rid, "type": "relation", "reason": f"outer ring {idx} did not close"})
                continue
            if inner_bad:
                skipped.append({"id": rid, "type": "relation", "reason": inner_bad})
                continue
            pts, reason = ring_to_pts(ring)
            reason = reason or check_shape(pts)
            if reason:
                skipped.append({"id": rid, "type": "relation", "reason": reason})
                continue
            holes = [ip for ip in inner_pts if point_in_polygon(polygon_centroid(ip), pts)]
            if holes:
                relations_with_holes += 1
            name = f"relation_{rid}" if len(outer_rings) == 1 else f"relation_{rid}_{idx}"
            building_candidates.append((name, pts, holes, tags, rid))

    manifest["skipped_buildings"] = skipped
    manifest["building_relations_with_holes_cut"] = relations_with_holes

    # ---- heights: pass 1 (direct tags) ----
    direct = {}  # name -> (height, source)
    for name, pts, holes, tags, osm_id in building_candidates:
        h = parse_height_tag(tags.get("height"))
        if h is not None and h > 0:
            direct[name] = (h, "osm_height")
            continue
        h = parse_levels_height(tags)
        if h is not None and h > 0:
            direct[name] = (h, "osm_levels")

    centroids = {name: polygon_centroid(pts) for name, pts, holes, tags, osm_id in building_candidates}

    # ---- heights: pass 2 (interpolation from direct-tagged neighbours within 50 m) ----
    heights = dict(direct)
    direct_items = [(name, centroids[name][0], centroids[name][1], h) for name, (h, src) in direct.items()]
    for name, pts, holes, tags, osm_id in building_candidates:
        if name in heights:
            continue
        cx, cy = centroids[name]
        nearby = [h for n2, x2, y2, h in direct_items if n2 != name and math.hypot(cx - x2, cy - y2) <= 50.0]
        if nearby:
            nearby.sort()
            mid = len(nearby) // 2
            med = nearby[mid] if len(nearby) % 2 else (nearby[mid - 1] + nearby[mid]) / 2.0
            heights[name] = (med, "interpolated")

    # ---- heights: pass 3 (class default) ----
    building_class = {name: classify_building(tags) for name, pts, holes, tags, osm_id in building_candidates}
    for name, pts, holes, tags, osm_id in building_candidates:
        if name not in heights:
            heights[name] = (HEIGHT_CLASS.get(building_class[name], 9.0), "inferred_class")

    # ---- build building meshes ----
    height_source_counts = {}
    material_class_counts = {}
    sample_measure = None
    for name, pts, holes, tags, osm_id in building_candidates:
        height, source = heights[name]
        cls = building_class[name]
        bm = make_building_bm(pts, height, holes)
        obj = finalize_object(bm, name, col_buildings, materials[cls], par["Buildings"])
        obj["osm_id"] = str(osm_id)
        obj["osm_tags"] = json.dumps(tags)
        obj["urbantwin_height"] = float(height)
        obj["urbantwin_heightSource"] = source
        obj["urbantwin_materialClass"] = cls
        height_source_counts[source] = height_source_counts.get(source, 0) + 1
        material_class_counts[cls] = material_class_counts.get(cls, 0) + 1
        if name.startswith("way_"):
            refs = ways[osm_id]["refs"]
            for a, b in zip(refs, refs[1:]):
                d = haversine(nodes[a], nodes[b])
                if sample_measure is None or d > sample_measure["haversine_m"]:
                    sample_measure = {
                        "object": name, "node_a": a, "node_b": b, "haversine_m": d,
                        "expected_xy_a": project(nodes[a][1], nodes[a][0]),
                        "expected_xy_b": project(nodes[b][1], nodes[b][0]),
                    }

    manifest["height_source_counts"] = height_source_counts
    manifest["material_class_counts"] = material_class_counts
    manifest["sample_measurement"] = sample_measure

    for obj in list(bpy.context.scene.objects):
        bpy.context.view_layer.objects.active = obj
        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # ---- roads & footways ----
    road_count = 0
    footway_count = 0
    skipped_highway_types = {}
    for wid, way in ways.items():
        tags = way["tags"]
        hw = tags.get("highway")
        if hw is None:
            continue
        if hw not in ROAD_WIDTHS:
            skipped_highway_types[hw] = skipped_highway_types.get(hw, 0) + 1
            continue
        refs = way["refs"]
        missing = [r for r in refs if r not in nodes]
        if missing:
            continue
        pts = [project(nodes[r][1], nodes[r][0]) for r in refs]
        for run in clip_polyline(pts, BBOX_XY):
            width = ROAD_WIDTHS[hw]
            bm = build_ribbon_bm(run, width)
            is_footway = hw in FOOTWAY_TYPES
            col = col_footways if is_footway else col_roads
            mat = mat_footway if is_footway else mat_road
            name = f"{'footway' if is_footway else 'road'}_{wid}_{road_count + footway_count}"
            obj = finalize_object(bm, name, col, mat, par[col.name])
            obj.location.z = 0.02
            if is_footway:
                footway_count += 1
            else:
                road_count += 1
    manifest["skipped_highways"] = skipped_highway_types
    manifest["extended_highway_widths"] = {
        "note": "Highway types absent from the spec's width table, mapped to their nearest spec class at the user's request.",
        "mapping": {k: {"as_class": c, "width_m": w} for k, (c, w) in EXTENDED_WIDTHS.items()},
    }

    # ---- green spaces ----
    green_count = 0

    def is_green(tags):
        return tags.get("leisure") in GREEN_LEISURE or tags.get("landuse") in GREEN_LANDUSE or tags.get("natural") in GREEN_NATURAL

    for wid, way in ways.items():
        tags = way["tags"]
        if not is_green(tags):
            continue
        refs = way["refs"]
        if len(refs) >= 2 and refs[0] == refs[-1]:
            refs = refs[:-1]
        missing = [r for r in refs if r not in nodes]
        if missing or len(refs) < 3:
            continue
        pts = [project(nodes[r][1], nodes[r][0]) for r in refs]
        pts = dedup_consecutive(pts)
        if len(pts) < 3:
            continue
        cx, cy = polygon_centroid(pts)
        if not centroid_in_bbox(cx, cy):
            continue
        bm = build_polygon_bm(pts)
        obj = finalize_object(bm, f"green_{wid}", col_green, mat_green, par["GreenSpaces"])
        obj.location.z = 0.01
        green_count += 1
    green_relations = 0
    for rid, rel in relations.items():
        if not is_green(rel["tags"]):
            continue
        outer_segs, inner_segs = [], []
        for mtype, mref, role in rel["members"]:
            if mtype == "way" and mref in ways:
                (inner_segs if role == "inner" else outer_segs).append(ways[mref]["refs"])
        inner_pts = []
        for ring in join_rings(inner_segs):
            ip, reason = ring_to_pts(ring) if ring[0] == ring[-1] else (None, "open")
            if ip and not check_shape(ip):
                inner_pts.append(ip)
        for idx, ring in enumerate(join_rings(outer_segs)):
            if ring[0] != ring[-1]:
                continue
            pts, reason = ring_to_pts(ring)
            if reason or check_shape(pts) or not centroid_in_bbox(*polygon_centroid(pts)):
                continue
            holes = [ip for ip in inner_pts if point_in_polygon(polygon_centroid(ip), pts)]
            obj = finalize_object(build_polygon_bm(pts, holes), f"green_relation_{rid}_{idx}",
                                  col_green, mat_green, par["GreenSpaces"])
            obj.location.z = 0.01
            green_count += 1
            green_relations += 1
    manifest["counts"]["green_spaces"] = green_count
    manifest["counts"]["green_spaces_from_relations"] = green_relations

    # ---- transit: public_transport point markers (bus stops, platforms, stations) ----
    transit_count = 0
    for nid, (lat, lon, tags) in nodes.items():
        if "public_transport" not in tags and "highway" not in tags:
            continue
        if "public_transport" not in tags:
            continue
        if not in_bbox_latlon(lat, lon):
            continue
        x, y = project(lon, lat)
        bm = bmesh.new()
        segs = 10
        r = 1.0
        verts = []
        for i in range(segs):
            ang = 2 * math.pi * i / segs
            verts.append(bm.verts.new((x + r * math.cos(ang), y + r * math.sin(ang), 0.0)))
        bm.faces.new(verts)
        faces_up(bm)
        obj = finalize_object(bm, f"transit_{nid}", col_transit, mat_transit, par["Transit"])
        obj.location.z = 0.02
        transit_count += 1
    manifest["counts"]["transit_markers"] = transit_count
    manifest["counts"]["railway_ways_present_not_rendered"] = sum(1 for w in ways.values() if "railway" in w["tags"])
    manifest["note_railway"] = (
        "railway way geometry was not rendered: the spec gives explicit widths for road/footway classes only, "
        "and inventing a rail-track width was avoided. Railway way count is recorded for honesty; "
        "public_transport point features (stops/platforms) are rendered as markers in /World/Transit."
    )

    # ---- trees ----
    tree_bm_template = make_tree_bm()
    tree_mesh = bpy.data.meshes.new("tree_template_mesh")
    tree_bm_template.to_mesh(tree_mesh)
    tree_bm_template.free()
    tree_mesh.materials.append(mat_canopy)
    tree_count = 0
    for nid, (lat, lon, tags) in nodes.items():
        if tags.get("natural") != "tree":
            continue
        if not in_bbox_latlon(lat, lon):
            continue
        x, y = project(lon, lat)
        obj = bpy.data.objects.new(f"tree_{nid}", tree_mesh)
        obj.location = (x, y, 0.0)
        col_trees.objects.link(obj)
        obj.parent = par["Trees"]
        tree_count += 1
    manifest["counts"]["trees"] = tree_count
    manifest["counts"]["buildings"] = len(building_candidates)
    manifest["counts"]["roads"] = road_count
    manifest["counts"]["footways"] = footway_count

    for obj in bpy.context.scene.objects:
        if obj.name.startswith("tree_") and obj.data is tree_mesh:
            continue
        bpy.context.view_layer.objects.active = obj
        for o in bpy.data.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # ---- export to intermediate USD via Blender's bundled USD exporter ----
    tmp_usda = os.path.join(PROJECT_DIR, "_blender_export.usda")
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.wm.usd_export(
        filepath=tmp_usda,
        selected_objects_only=False,
        visible_objects_only=False,
        export_animation=False,
        export_hair=False,
        export_uvmaps=False,
        export_normals=True,
        export_materials=True,
        export_armatures=False,
        export_shapekeys=False,
        use_instancing=True,
        generate_preview_surface=True,
        export_textures=False,
        relative_paths=True,
        root_prim_path="/World",
        export_custom_properties=True,
        custom_properties_namespace="userProperties",
        export_meshes=True,
        export_lights=False,
        export_cameras=False,
        export_curves=False,
        export_points=False,
        export_volumes=False,
        triangulate_meshes=False,
        convert_scene_units='METERS',
        meters_per_unit=1.0,
    )

    manifest["counts"]["skipped_buildings_count"] = len(skipped)
    manifest["render"] = "render_aerial_45.png"
    post_process_and_write(tmp_usda)
    render_aerial(os.path.join(PROJECT_DIR, manifest["render"]))
    make_zip()


def render_aerial(path):
    """45-degree aerial of the whole tile. Camera/ground are added after USD export so they never reach the USD."""
    from mathutils import Vector
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=1400, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(make_material("mat_ground_render", *GROUND_COLOR))

    cam_data = bpy.data.cameras.new("AerialCam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 1450.0
    cam_data.clip_end = 10000.0
    cam = bpy.data.objects.new("AerialCam", cam_data)
    scene.collection.objects.link(cam)
    # from the SW: horizontal distance sqrt(2)*k equals height sqrt(2)*k -> 45 deg elevation
    cam.location = Vector((-1.0, -1.0, math.sqrt(2.0))) * 1000.0
    cam.rotation_euler = (-cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1440
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"Rendered {path}")


def make_zip():
    import zipfile
    files = ["pune_center.osm", "city_base.usda", "environment.usda", "main.usda",
             "manifest.json", "build_script.py", "overpass_query.txt", manifest["render"]]
    zpath = os.path.join(PROJECT_DIR, "pune_usd_deliverables.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(PROJECT_DIR, f), f)
    print(f"Wrote {zpath}")


# ---------- pxr post-process ----------

def post_process_and_write(tmp_usda):
    from pxr import Usd, UsdGeom, Sdf, UsdLux, UsdShade

    stage = Usd.Stage.Open(tmp_usda)
    stage.SetMetadata("upAxis", UsdGeom.Tokens.z)
    stage.SetMetadata("metersPerUnit", 1.0)

    world = stage.GetPrimAtPath("/World")
    if world:
        stage.SetDefaultPrim(world)

    attr_map = {
        "userProperties:osm_tags": ("urbantwin:osmTags", Sdf.ValueTypeNames.String),
        "userProperties:urbantwin_height": ("urbantwin:height", Sdf.ValueTypeNames.Float),
        "userProperties:urbantwin_heightSource": ("urbantwin:heightSource", Sdf.ValueTypeNames.String),
        "userProperties:urbantwin_materialClass": ("urbantwin:materialClass", Sdf.ValueTypeNames.String),
    }
    # building prim = the object Xform /World/Buildings/<osm name>; Blender writes userProperties there
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        for src_name, (dst_name, dst_type) in attr_map.items():
            src = prim.GetAttribute(src_name)
            if not src:
                raise RuntimeError(f"{prim.GetPath()} lacks {src_name}")
            val = src.Get()
            if dst_name == "urbantwin:osmTags":
                val = json.dumps(json.loads(val), sort_keys=True)
            elif dst_type == Sdf.ValueTypeNames.Float:
                val = float(val)
            prim.CreateAttribute(dst_name, dst_type, custom=True).Set(val)
            prim.RemoveProperty(src_name)

    for prim in stage.Traverse():
        mesh = UsdGeom.Mesh(prim)
        if not mesh:
            continue
        path = prim.GetPath().pathString
        is_building = path.startswith("/World/Buildings/")

        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)

        pts_attr = mesh.GetPointsAttr()
        pts = pts_attr.Get()
        if pts and len(pts) > 0:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            zs = [p[2] for p in pts]
            mesh.CreateExtentAttr([(min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))])

        color = None
        if is_building:
            cls = prim.GetParent().GetAttribute("urbantwin:materialClass").Get()
            color = MATERIAL_COLORS[cls][0]
        elif path.startswith("/World/Roads/"):
            color = ROAD_COLOR[0]
        elif path.startswith("/World/PedestrianPaths/"):
            color = FOOTWAY_COLOR[0]
        elif path.startswith("/World/GreenSpaces/"):
            color = GREEN_COLOR[0]
        elif path.startswith("/World/Transit/"):
            color = TRANSIT_COLOR[0]
        elif "tree" in path.lower():
            color = TREE_CANOPY_COLOR[0]
        if color is None:
            raise RuntimeError(f"no displayColor rule for mesh {path}")
        mesh.CreateDisplayColorAttr([color])

    # Blender writes a full mesh copy per tree; replace with real USD instancing of one prototype
    trees = stage.GetPrimAtPath("/World/Trees").GetChildren()
    layer = stage.GetRootLayer()
    stage.CreateClassPrim("/TreePrototype")
    Sdf.CopySpec(layer, trees[0].GetChildren()[0].GetPath(), layer, Sdf.Path("/TreePrototype/Tree"))
    for t in trees:
        for c in t.GetChildren():
            stage.RemovePrim(c.GetPath())
        t.GetReferences().AddInternalReference("/TreePrototype")
        t.SetInstanceable(True)
    manifest["counts"]["tree_prototypes"] = 1

    city_base_path = os.path.join(PROJECT_DIR, "city_base.usda")
    stage.GetRootLayer().Export(city_base_path)

    # environment.usda: ground plane + one distant light
    env_stage = Usd.Stage.CreateNew(os.path.join(PROJECT_DIR, "environment.usda"))
    env_stage.SetMetadata("upAxis", UsdGeom.Tokens.z)
    env_stage.SetMetadata("metersPerUnit", 1.0)
    env_world = UsdGeom.Xform.Define(env_stage, "/World")
    env_stage.SetDefaultPrim(env_world.GetPrim())
    ground = UsdGeom.Mesh.Define(env_stage, "/World/Ground")
    half = 1500.0
    ground.CreatePointsAttr([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)])
    ground.CreateFaceVertexCountsAttr([4])
    ground.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    ground.CreateExtentAttr([(-half, -half, 0), (half, half, 0)])
    ground.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    ground.CreateDoubleSidedAttr(True)
    ground.CreateDisplayColorAttr([GROUND_COLOR[0]])
    gmat = UsdShade.Material.Define(env_stage, "/World/EnvMaterials/Ground")
    gsh = UsdShade.Shader.Define(env_stage, "/World/EnvMaterials/Ground/PreviewSurface")
    gsh.CreateIdAttr("UsdPreviewSurface")
    gsh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(GROUND_COLOR[0])
    gsh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(GROUND_COLOR[1])
    gmat.CreateSurfaceOutput().ConnectToSource(gsh.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(ground.GetPrim()).Bind(gmat)
    # warm late-afternoon sun (low angle -> long shadows) plus a soft blue sky fill
    light = UsdLux.DistantLight.Define(env_stage, "/World/SunLight")
    light.CreateIntensityAttr(2500.0)
    light.CreateAngleAttr(0.53)
    light.CreateColorAttr((1.0, 0.92, 0.80))
    UsdLux.ShadowAPI.Apply(light.GetPrim()).CreateShadowEnableAttr(True)
    UsdGeom.Xformable(light.GetPrim()).AddRotateXYZOp().Set((-40.0, 0.0, 35.0))
    sky = UsdLux.DomeLight.Define(env_stage, "/World/SkyLight")
    sky.CreateIntensityAttr(600.0)
    sky.CreateColorAttr((0.62, 0.75, 0.95))
    env_stage.GetRootLayer().Save()

    # main.usda: sublayers environment then city_base, plus stage metadata
    main_stage = Usd.Stage.CreateNew(os.path.join(PROJECT_DIR, "main.usda"))
    main_stage.SetMetadata("upAxis", UsdGeom.Tokens.z)
    main_stage.SetMetadata("metersPerUnit", 1.0)
    main_root = main_stage.GetRootLayer()
    main_root.subLayerPaths.append("environment.usda")
    main_root.subLayerPaths.append("city_base.usda")
    main_root.defaultPrim = "World"
    main_root.Save()

    try:
        os.remove(tmp_usda)
    except OSError:
        pass

    validate(os.path.join(PROJECT_DIR, "main.usda"))
    write_manifest()


def validate(main_usda_path):
    from pxr import Usd, UsdGeom, UsdUtils

    print("\n=== SECTION 7 VALIDATION ===")
    stage = Usd.Stage.Open(main_usda_path)
    up_axis = stage.GetMetadata("upAxis")
    mpu = stage.GetMetadata("metersPerUnit")
    default_prim = stage.GetDefaultPrim()
    print(f"upAxis = {up_axis} (expect Z)")
    print(f"metersPerUnit = {mpu} (expect 1)")
    print(f"defaultPrim = {default_prim.GetPath() if default_prim else None} (expect /World)")

    required_attrs = ["urbantwin:osmTags", "urbantwin:height", "urbantwin:heightSource", "urbantwin:materialClass"]
    total_buildings = 0
    missing_attrs = 0
    zero_height = 0
    height_counts = {}
    material_counts = {}
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        total_buildings += 1
        ok = True
        for a in required_attrs:
            if not prim.HasAttribute(a):
                ok = False
        if not ok:
            missing_attrs += 1
            continue
        h = prim.GetAttribute("urbantwin:height").Get()
        if h is None or h <= 0:
            zero_height += 1
        src = prim.GetAttribute("urbantwin:heightSource").Get()
        cls = prim.GetAttribute("urbantwin:materialClass").Get()
        height_counts[src] = height_counts.get(src, 0) + 1
        material_counts[cls] = material_counts.get(cls, 0) + 1

    print(f"Buildings checked: {total_buildings}")
    print(f"Buildings missing one or more urbantwin: attributes: {missing_attrs}")
    print(f"Buildings with height <= 0: {zero_height}")
    print(f"heightSource counts (from USD): {height_counts}")
    print(f"materialClass counts (from USD): {material_counts}")
    print(f"Match manifest heightSource counts: {height_counts == manifest['height_source_counts']}")
    print(f"Match manifest materialClass counts: {material_counts == manifest['material_class_counts']}")

    # independent check: geodesic (haversine) length of an OSM edge vs the same edge read back from USD
    sm = manifest["sample_measurement"]
    mesh_prim = stage.GetPrimAtPath(f"/World/Buildings/{sm['object']}").GetChildren()[0]
    xf = UsdGeom.Xformable(mesh_prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    pts = [xf.Transform(p) for p in UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get() if abs(p[2]) < 1e-4]

    def nearest(xy):
        return min(pts, key=lambda p: (p[0] - xy[0]) ** 2 + (p[1] - xy[1]) ** 2)
    pa, pb = nearest(sm["expected_xy_a"]), nearest(sm["expected_xy_b"])
    usd_len = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
    err = abs(usd_len - sm["haversine_m"]) / sm["haversine_m"]
    print(f"Measured edge of {sm['object']} (OSM nodes {sm['node_a']} -> {sm['node_b']}): "
          f"OSM geodesic {sm['haversine_m']:.3f} m vs USD {usd_len:.3f} m, error {err * 100:.4f}% "
          f"-> {'PASS' if err < 0.01 else 'FAIL'} (<1%)")
    sm["usd_m"] = usd_len
    sm["error_pct"] = err * 100
    sm["within_1pct"] = err < 0.01

    checker = UsdUtils.ComplianceChecker()
    checker.CheckCompliance(main_usda_path)
    errors = checker.GetErrors()
    print(f"UsdUtils.ComplianceChecker errors: {len(errors)}")
    for e in errors:
        print("  ERROR:", e)
    manifest["validation"] = {
        "up_axis": str(up_axis),
        "meters_per_unit": mpu,
        "default_prim": str(default_prim.GetPath()) if default_prim else None,
        "buildings_checked": total_buildings,
        "buildings_missing_attrs": missing_attrs,
        "buildings_zero_height": zero_height,
        "compliance_errors": [str(e) for e in errors],
    }
    print("=== END VALIDATION ===\n")


def write_manifest():
    manifest_path = os.path.join(PROJECT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
