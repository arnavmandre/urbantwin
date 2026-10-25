"""
400 m x 400 m Omniverse view of the Pune model, with a realistic look. The simulator still runs on the full 1 km.

Order: build_script.py (Blender) -> pune_sim.py -> pune_view.py, with any Python that has pxr + numpy.
Per-dashboard-run updates go through run_pune.py, which reuses write_run_layer().

Writes main_view_400m.usda (open this in Omniverse / stream it) + facade_tile.png + view_run.usdc.
Everything is an override on top of main_live.usda; the spec files are untouched and still validate.
Cameras /World/Cameras/{Overview,Aerial,Street,ProblemZone} match the Kit view_commands allow-list; all but Aerial are
placed per run where the walkers are (write_run_layer).

Nothing pokes out of the square:
- roads, footpaths and green areas are clipped polygon-by-polygon at the square edge,
- buildings, trees and transit markers are kept only if they lie fully inside (never half a building),
- the ground plane is exactly the square,
- walkers and vehicles are hidden (PointInstancer invisibleIds) on any frame they are not fully inside.

Look (appearance only, NOT data - recorded in manifest.generated.json["view_400m"]):
- building walls: one generated storey/window facade tile, UV-mapped in metres (3 m bay x 3.2 m storey),
  tinted with plaster colours picked per building from a hash of its OSM id; separate concrete/terracotta roofs.
  The windows do not come from OSM. Heritage and religious buildings stay plain stone, no windows.
- realistic albedo for asphalt, paving, grass, soil, tree canopy.
"""
import json
import math
import re
import struct
import zlib
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

import pune_sim  # reuse new_layer / preview_material / TIMECODES; importing does not run the simulator

HERE = Path(__file__).resolve().parent
HALF = 200.0  # 400 m x 400 m, centred on Shaniwar Wada (scene origin)
STOREY_M, BAY_M = 3.2, 3.0

FACADE_TINTS = [(0.80, 0.72, 0.56), (0.82, 0.80, 0.74), (0.78, 0.62, 0.40), (0.76, 0.60, 0.54),
                (0.64, 0.68, 0.70), (0.64, 0.70, 0.57), (0.70, 0.46, 0.34)]
ROOFS = [(0.40, 0.39, 0.37), (0.48, 0.46, 0.43), (0.32, 0.31, 0.30), (0.50, 0.28, 0.18)]
PLAIN = {"heritage": ((0.50, 0.36, 0.25), (0.42, 0.30, 0.21)),   # Shaniwar Wada stone/brick walls
         "religious": ((0.82, 0.72, 0.54), (0.60, 0.38, 0.24))}
LOOK = {"asphalt": ((0.09, 0.09, 0.10), 0.9), "paving": ((0.42, 0.40, 0.36), 0.85),
        "grass": ((0.18, 0.31, 0.11), 0.95), "soil": ((0.33, 0.30, 0.26), 0.95),
        "canopy": ((0.12, 0.26, 0.09), 0.85)}


# ---------- facade texture ----------

def write_png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def facade_tile(n=256):
    """Greyscale storey tile (u = one 3 m bay, v = one 3.2 m storey), multiplied by a plaster tint in the shader."""
    img = np.full((n, n), 232, np.uint8)
    u = np.linspace(0, 1, n)[None, :]
    v = np.linspace(0, 1, n)[:, None]  # row 0 = v 0 (bottom); flipped before writing

    def box(u0, u1, v0, v1, val):
        img[(u >= u0) & (u <= u1) & (v >= v0) & (v <= v1)] = val
    box(0, 1, 0.00, 0.05, 196)          # floor slab band
    box(0.18, 0.82, 0.25, 0.28, 214)    # sill
    box(0.20, 0.80, 0.28, 0.82, 165)    # window frame
    box(0.23, 0.77, 0.31, 0.79, 38)     # glass
    box(0.49, 0.51, 0.31, 0.79, 165)    # mullion
    box(0.14, 0.86, 0.84, 0.88, 128)    # chajja (sunshade) shadow line
    rng = np.random.default_rng(3)      # faint plaster grain so walls are not flat
    img = np.clip(img.astype(int) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)
    return np.repeat(img[::-1, :, None], 3, axis=2)


def facade_material(stage, path, tint):
    mat = UsdShade.Material.Define(stage, path)
    reader = UsdShade.Shader.Define(stage, f"{path}/stReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    tex = UsdShade.Shader.Define(stage, f"{path}/Facade")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set("facade_tile.png")
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    tex.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*tint, 1.0))
    tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    surf = UsdShade.Shader.Define(stage, f"{path}/PreviewSurface")
    surf.CreateIdAttr("UsdPreviewSurface")
    surf.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
    surf.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.85)
    mat.CreateSurfaceOutput().ConnectToSource(surf.ConnectableAPI(), "surface")
    return mat


# ---------- geometry ----------

def clip_poly(poly):
    """Sutherland-Hodgman against the square |x|,|y| <= HALF. poly: list of (x, y, z)."""
    for axis, sign in ((0, 1), (0, -1), (1, 1), (1, -1)):
        out = []
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            ina, inb = sign * a[axis] <= HALF, sign * b[axis] <= HALF
            if ina != inb:
                t = (HALF - sign * a[axis]) / (sign * b[axis] - sign * a[axis])
                out.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
            if inb:
                out.append(b)
        poly = out
        if not poly:
            break
    return poly


def clip_mesh(mesh):
    pts = mesh.GetPointsAttr().Get()
    counts, idx = mesh.GetFaceVertexCountsAttr().Get(), mesh.GetFaceVertexIndicesAttr().Get()
    new_pts, new_counts, new_idx, k = [], [], [], 0
    for c in counts:
        poly = clip_poly([tuple(pts[i]) for i in idx[k:k + c]])
        k += c
        if len(poly) >= 3:
            new_idx += range(len(new_pts), len(new_pts) + len(poly))
            new_pts += poly
            new_counts.append(len(poly))
    if not new_pts:
        return False
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*p) for p in new_pts]))
    mesh.GetFaceVertexCountsAttr().Set(new_counts)
    mesh.GetFaceVertexIndicesAttr().Set(new_idx)
    mesh.GetNormalsAttr().Block()  # flat faces; renderer derives the up normal
    xs, ys, zs = zip(*new_pts)
    mesh.GetExtentAttr().Set([(min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))])
    return True


def face_normal(p):
    n = [0.0, 0.0, 0.0]
    for i in range(len(p)):
        a, b = p[i], p[(i + 1) % len(p)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    L = math.sqrt(sum(c * c for c in n)) or 1.0
    return [c / L for c in n]


def dress_building(mesh, wall_mat, roof_mat):
    """Metre-scaled UVs (u along the wall, v = height / storey) and wall/roof material subsets."""
    pts = mesh.GetPointsAttr().Get()
    counts, idx = mesh.GetFaceVertexCountsAttr().Get(), mesh.GetFaceVertexIndicesAttr().Get()
    st, walls, roofs, k = [], [], [], 0
    for f, c in enumerate(counts):
        face = [pts[i] for i in idx[k:k + c]]
        k += c
        nx, ny, nz = face_normal(face)
        if abs(nz) > 0.5:
            roofs.append(f)
            st += [Gf.Vec2f(p[0] / BAY_M, p[1] / BAY_M) for p in face]
        else:
            walls.append(f)
            h = math.hypot(nx, ny) or 1.0
            tx, ty = -ny / h, nx / h
            st += [Gf.Vec2f((p[0] * tx + p[1] * ty) / BAY_M, p[2] / STOREY_M) for p in face]
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                            UsdGeom.Tokens.faceVarying).Set(st)
    api = UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
    for name, faces, mat in (("walls", walls, wall_mat), ("roof", roofs, roof_mat)):
        if faces:
            sub = api.CreateMaterialBindSubset(name, Vt.IntArray(faces))
            UsdShade.MaterialBindingAPI.Apply(sub.GetPrim()).Bind(mat)
    api.SetMaterialBindSubsetsFamilyType(UsdGeom.Tokens.partition)


def bound(cache, prim):
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    return r.GetMin(), r.GetMax()


def fully_inside(lo, hi):
    return lo[0] >= -HALF and hi[0] <= HALF and lo[1] >= -HALF and hi[1] <= HALF


def overlaps(lo, hi):
    return lo[0] <= HALF and hi[0] >= -HALF and lo[1] <= HALF and hi[1] >= -HALF


def rebind(prim, mat, color):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)
    UsdGeom.Mesh(prim).GetDisplayColorAttr().Set([Gf.Vec3f(*color)])


def meshes_under(prim):
    return [p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh)]


# ---------- main ----------

def build_view():
    """Static 400 m view over main_live.usda: clipping, look, ground, cameras. view_run.usdc (per run) sits on top."""
    write_png(HERE / "facade_tile.png", facade_tile())

    layer_stage = pune_sim.new_layer("main_view_400m.usda")
    root = layer_stage.GetRootLayer()
    root.subLayerPaths.append("view_run.usdc")
    root.subLayerPaths.append("main_live.usda")
    stage = Usd.Stage.Open(root)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])

    look = {k: pune_sim.preview_material(stage, f"/World/Look/{k}", c, r) for k, (c, r) in LOOK.items()}
    facades = [facade_material(stage, f"/World/Look/facade{i}", t) for i, t in enumerate(FACADE_TINTS)]
    roofs = [pune_sim.preview_material(stage, f"/World/Look/roof{i}", c, 0.9) for i, c in enumerate(ROOFS)]
    plain = {cls: (pune_sim.preview_material(stage, f"/World/Look/{cls}_wall", w, 0.9),
                   pune_sim.preview_material(stage, f"/World/Look/{cls}_roof", r, 0.9))
             for cls, (w, r) in PLAIN.items()}

    counts = {"buildings_kept": 0, "buildings_hidden": 0, "flat_kept": 0, "flat_clipped": 0, "flat_hidden": 0,
              "trees_kept": 0, "trees_hidden": 0}

    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        if not fully_inside(*bound(cache, prim)):
            prim.SetActive(False)
            counts["buildings_hidden"] += 1
            continue
        counts["buildings_kept"] += 1
        cls = prim.GetAttribute("urbantwin:materialClass").Get()
        h = zlib.crc32(prim.GetName().encode())
        mesh = UsdGeom.Mesh(prim.GetChildren()[0])
        if cls in plain:
            wall, roof = plain[cls]
            tint = PLAIN[cls][0]
        else:
            ti = 1 if cls == "healthcare" else h % len(FACADE_TINTS)
            wall, roof, tint = facades[ti], roofs[(h >> 8) % len(ROOFS)], FACADE_TINTS[ti]
        dress_building(mesh, wall, roof)
        mesh.GetDisplayColorAttr().Set([Gf.Vec3f(*tint)])

    for scope, key in (("Roads", "asphalt"), ("PedestrianPaths", "paving"), ("GreenSpaces", "grass")):
        for prim in stage.GetPrimAtPath(f"/World/{scope}").GetChildren():
            lo, hi = bound(cache, prim)
            if not overlaps(lo, hi):
                prim.SetActive(False)
                counts["flat_hidden"] += 1
                continue
            mesh_prim = meshes_under(prim)[0]
            if not fully_inside(lo, hi):
                if not clip_mesh(UsdGeom.Mesh(mesh_prim)):
                    prim.SetActive(False)
                    counts["flat_hidden"] += 1
                    continue
                counts["flat_clipped"] += 1
            counts["flat_kept"] += 1
            rebind(mesh_prim, look[key], LOOK[key][0])

    for scope in ("Trees", "Transit"):
        for prim in stage.GetPrimAtPath(f"/World/{scope}").GetChildren():
            inside = fully_inside(*bound(cache, prim))
            if not inside:
                prim.SetActive(False)
            if scope == "Trees":
                counts["trees_kept" if inside else "trees_hidden"] += 1
    rebind(stage.GetPrimAtPath("/TreePrototype/Tree"), look["canopy"], LOOK["canopy"][0])

    ground = stage.GetPrimAtPath("/World/Ground")
    g = UsdGeom.Mesh(ground)
    g.GetPointsAttr().Set([(-HALF, -HALF, 0), (HALF, -HALF, 0), (HALF, HALF, 0), (-HALF, HALF, 0)])
    g.GetExtentAttr().Set([(-HALF, -HALF, 0), (HALF, HALF, 0)])
    rebind(ground, look["soil"], LOOK["soil"][0])

    # cameras the Kit view_commands handler switches between (/World/Cameras/<name>)
    look_at_camera(stage, "Aerial", (0, 0, 480), (0, 0, 0), 24, up=(0, 1, 0))  # whole square, ~420 m frame
    # Overview, Street and ProblemZone follow the walkers, so they are authored per run in view_run.usdc:
    # an opinion in this root layer would be stronger and pin them forever.
    root.Save()

    generated = pune_sim.read_generated()
    generated["view_400m"] = {
        "file": "main_view_400m.usda", "square_m": 2 * HALF, "centre": "scene origin (Shaniwar Wada)",
        "note": "Display subset only; the simulator runs on the full 1 km tile.",
        "clipping": "flat layers clipped at the edge; buildings/trees/transit kept only if fully inside; "
                    "walkers/vehicles hidden per frame unless fully inside (view_run.usdc)",
        "counts": counts,
        "cameras": ["Aerial (whole square)", "Overview, Street, ProblemZone (placed per run where the walkers are; "
                    "view_run.usdc)"],
        "appearance_not_data": ("Facade windows (facade_tile.png), per-building plaster tints and roof colours are "
                                "illustrative appearance, not OSM data. Heights and footprints are unchanged."),
    }
    pune_sim.write_generated(generated)
    print(json.dumps(counts))


def look_at_camera(stage, name, eye, target, focal_mm, up=(0, 0, 1)):
    cam = UsdGeom.Camera.Define(stage, f"/World/Cameras/{name}")
    cam.CreateFocalLengthAttr(focal_mm)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.5, 10000.0))
    xf = UsdGeom.Xformable(cam)
    xf.ClearXformOpOrder()
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up))
    xf.AddTransformOp().Set(view.GetInverse())  # look-at gives world->camera; the prim needs camera->world


# Kit/USD default horizontal aperture (mm) and the stream width, for on-screen person size.
APERTURE_MM, STREAM_PX, PERSON_M = 20.955, 1280, 1.7
# name: (distance from target m, eye height m, focal mm, aim height m). Sized so a person is roughly
# 13 px (Overview), 35 px (ProblemZone) and 90 px (Street) tall at the target on the 1280 px stream.
SHOTS = {"Overview": (200.0, 110.0, 24.0, 0.0),
         "ProblemZone": (55.0, 32.0, 28.0, 0.0),
         "Street": (24.0, 2.4, 24.0, 1.1)}


def obstacles():
    """Line-of-sight blockers in the 400 m view: building triangles (world space; a box would wrongly fill
    courtyards such as Shaniwar Wada's) and tree AABBs (xmin, ymin, zmin, xmax, ymax, zmax)."""
    stage = Usd.Stage.Open(str(HERE / "main_view_400m.usda"))
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    tris = []
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        if not prim.IsActive():
            continue
        for mesh_prim in meshes_under(prim):
            mesh = UsdGeom.Mesh(mesh_prim)
            xf = np.array(mesh.ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
            pts = np.array(mesh.GetPointsAttr().Get())
            pts = pts @ xf[:3, :3] + xf[3, :3]
            start = 0
            idx = mesh.GetFaceVertexIndicesAttr().Get()
            for n in mesh.GetFaceVertexCountsAttr().Get():
                face = idx[start:start + n]
                tris += [(pts[face[0]], pts[face[k]], pts[face[k + 1]]) for k in range(1, n - 1)]
                start += n
    boxes = [[*r.GetMin(), *r.GetMax()]
             for r in (cache.ComputeWorldBound(p).ComputeAlignedRange()
                       for p in stage.GetPrimAtPath("/World/Trees").GetChildren() if p.IsActive())]
    return np.array(tris).reshape(-1, 3, 3), np.array(boxes).reshape(-1, 6)


def walker_samples(positions_attr, every=12):
    """Walker positions inside the view, pooled over every n-th time sample."""
    codes = pune_sim.TIMECODES[::every]
    p = np.concatenate([np.array(positions_attr.Get(c))[:, :2] for c in codes])
    return p[(np.abs(p[:, 0]) < HALF - 2) & (np.abs(p[:, 1]) < HALF - 2)]


def hotspots(points, centre=None, radius=None, cell=12.0, k=5, spacing=30.0):
    """Up to k busiest walker spots, densest first and at least `spacing` apart (optionally only within radius
    of centre). Each is the mean walker position around a dense cell. Empty if there are too few walkers."""
    if centre is not None:
        points = points[np.hypot(points[:, 0] - centre[0], points[:, 1] - centre[1]) < radius]
    if len(points) < 20:
        return []
    edges = np.arange(-HALF, HALF + cell, cell)
    h, _, _ = np.histogram2d(points[:, 0], points[:, 1], bins=[edges, edges])
    spots = []
    for flat in np.argsort(-h.ravel()):
        i, j = np.unravel_index(flat, h.shape)
        if h[i, j] < 5 or len(spots) == k:
            break
        cxy = (edges[i] + cell / 2, edges[j] + cell / 2)
        if any(math.dist(cxy, s) < spacing for s in spots):
            continue
        near = points[(np.abs(points[:, 0] - cxy[0]) < cell) & (np.abs(points[:, 1] - cxy[1]) < cell)]
        spots.append(tuple(map(float, near.mean(axis=0))))
    return spots


def blocked(obstacle_set, a, b, steps=48):
    """True if the segment a->b crosses a building triangle or passes through a tree box (inflated 0.5 m).
    The last 3 m before the target are ignored, so a walker beside a wall still counts as visible."""
    tris, boxes = obstacle_set
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = np.linalg.norm(b - a)
    end = max(0.0, 1.0 - 3.0 / length)
    t = np.linspace(0.0, end, steps)[:, None]
    pts = a + t * (b - a)
    lo, hi = boxes[:, :3] - 0.5, boxes[:, 3:] + 0.5
    if ((pts[:, None, :] >= lo[None]) & (pts[:, None, :] <= hi[None])).all(axis=2).any():
        return True
    # Moller-Trumbore, all triangles at once, for the segment a -> a + end * (b - a)
    d = (b - a) * end
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = a - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    v = (q @ d) * inv
    w = np.einsum("ij,ij->i", e2, q) * inv
    return bool((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (w > 0) & (w < 1)).any())


def frame_leaks(obstacle_set, eye, fwd, half_h, half_v):
    """Rays across the upper frame and the horizon that hit the ground outside the square with no building in
    between, i.e. where the unmodelled void would show. Rays at or above the horizon see sky and are fine."""
    right = np.cross(fwd, (0.0, 0.0, 1.0))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    leaks = 0
    for sy in (1.0, 0.5, 0.0, -0.3):
        for sx in (-1.0, -0.5, 0.0, 0.5, 1.0):
            r = fwd + math.tan(half_h) * sx * right + math.tan(half_v) * sy * up
            if r[2] >= 0:
                continue
            hit = eye + r * (eye[2] / -r[2])
            if max(abs(hit[0]), abs(hit[1])) > HALF and not blocked(obstacle_set, eye, hit):
                leaks += 1
    return leaks


def place_camera(obstacle_set, walkers, target, shot, keep_inside):
    """Best clear viewpoint around target for a SHOTS entry, as (rank, eye, aim, focal). Among azimuths whose
    line of sight to the target is not blocked, rank = (rays showing the void past the square, -score), where
    score counts the walkers it frames and can see, weighted by on-screen size and by how open the frame is."""
    dist, height, focal, aim_z = shot
    tx, ty = target
    aim = np.array([tx, ty, aim_z])
    half_h = math.atan(APERTURE_MM / 2 / focal)
    half_v = math.atan(APERTURE_MM * 9 / 16 / 2 / focal)
    best = None
    for az in np.radians(np.arange(0, 360, 15)):
        eye = np.array([tx + dist * math.cos(az), ty + dist * math.sin(az), height])
        if keep_inside and max(abs(eye[0]), abs(eye[1])) > HALF - 5:
            continue
        if blocked(obstacle_set, eye, aim):
            continue
        fwd = aim - eye
        fwd /= np.linalg.norm(fwd)
        rel = np.column_stack([walkers - eye[:2], np.full(len(walkers), PERSON_M / 2 - eye[2])])
        d = np.linalg.norm(rel, axis=1)
        yaw = np.arctan2(rel[:, 1], rel[:, 0]) - math.atan2(fwd[1], fwd[0])
        yaw = (yaw + np.pi) % (2 * np.pi) - np.pi
        pitch = np.arcsin(rel[:, 2] / d) - math.asin(fwd[2])
        framed = np.nonzero((np.abs(yaw) < half_h) & (np.abs(pitch) < half_v) & (d > 3))[0]
        framed = framed[np.argsort(d[framed])][:24]  # the nearest ones carry the shot; bounds the cost
        seen = [i for i in framed
                if not blocked(obstacle_set, eye, (*walkers[i], PERSON_M * 0.8), steps=24)]
        px = PERSON_M * focal / d[seen] * STREAM_PX / APERTURE_MM
        # Openness: rays across the frame that hit a wall well before the target mean a wall fills the shot.
        right = np.cross(fwd, (0.0, 0.0, 1.0))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        rays = [fwd + math.tan(half_h) * sx * right + math.tan(half_v) * sy * up
                for sx in (-0.8, -0.3, 0.3, 0.8) for sy in (-0.6, 0.0, 0.6)]
        open_rays = 0
        for r in rays:
            r = r / np.linalg.norm(r)
            reach = dist + 20.0 if r[2] >= 0 else min(dist + 20.0, eye[2] / -r[2])  # through the target; stop at the ground
            open_rays += not blocked(obstacle_set, eye, eye + r * (reach + 3.0), steps=16)
        score = float(np.minimum(px, 60).sum()) * (0.25 + 0.75 * open_rays / len(rays))
        # never frame the void past the square: fewest leaking rays first, then the best people shot
        rank = (frame_leaks(obstacle_set, eye, fwd, half_h, half_v), -score)
        if best is None or rank < best[0]:
            best = (rank, eye)
    if best is None:  # every direction blocked: straight down from above the target
        return (0, 0.0), (float(tx), float(ty) + 1e-3, height + dist), (float(tx), float(ty), aim_z), focal
    return best[0], tuple(map(float, best[1])), tuple(map(float, aim)), focal


ZONE_RE = re.compile(r"^Zone ([ABC])([123])$")


def zone_centre(zone_id):
    """Centre of a pune_sim 3x3 zone over the 1 km tile, clamped so the camera target stays in the 400 m view."""
    m = ZONE_RE.match(zone_id)
    xmin, ymin = pune_sim.project(pune_sim.BBOX["west"], pune_sim.BBOX["south"])
    xmax, ymax = pune_sim.project(pune_sim.BBOX["east"], pune_sim.BBOX["north"])
    cx = xmin + ("ABC".index(m.group(1)) + 0.5) * (xmax - xmin) / 3
    cy = ymin + (int(m.group(2)) - 0.5) * (ymax - ymin) / 3
    lim = HALF - 50
    return max(-lim, min(lim, cx)), max(-lim, min(lim, cy))


def write_run_layer(agents_dir, report, out_path):
    """Per-run overrides for the 400 m view, written next to the agents they mask.

    - walkers: invisibleIds per frame for each arm, inside the same demoState variant that picks the arm,
    - vehicles: invisibleIds per frame (traffic.usdc is static, but the mask belongs with the view),
    - ProblemZone camera aimed at the run's first problem zone (falls back to the Wada).
    """
    stage = pune_sim.new_layer(Path(out_path))
    root = stage.GetRootLayer()
    visible = {}

    def mask(positions_attr, inv_attr, margin):
        lim, seen = HALF - margin, []
        for code in pune_sim.TIMECODES:  # invisibleIds hold between samples; margins cover one sample of motion
            p = np.array(positions_attr.Get(code))
            out = np.nonzero((np.abs(p[:, 0]) > lim) | (np.abs(p[:, 1]) > lim))[0]
            inv_attr.Set(Vt.Int64Array(out.tolist()), code)
            seen.append(len(p) - len(out))
        return {"total": len(p), "visible_per_frame_mean": round(float(np.mean(seen)), 1),
                "visible_per_frame_max": int(max(seen))}

    vset = stage.GetPrimAtPath("/World").GetVariantSets().AddVariantSet("demoState")
    walker_positions, sources = {}, []
    for arm, variant in pune_sim.ARMS:
        src = Usd.Stage.Open(str(Path(agents_dir) / f"agents_{arm}.usdc"))
        sources.append(src)  # keep the stage alive while its attribute is used below
        positions = UsdGeom.PointInstancer(src.GetPrimAtPath("/World/Agents/Walkers")).GetPositionsAttr()
        walker_positions[arm] = positions
        vset.AddVariant(variant)
        vset.SetVariantSelection(variant)
        with vset.GetVariantEditContext():
            walkers = UsdGeom.PointInstancer(stage.OverridePrim("/World/Agents/Walkers"))
            visible[f"walkers_{arm}"] = mask(positions, walkers.CreateInvisibleIdsAttr(), 0.6)  # half a body (0.25 m) + one sample (0.33 m)
    vset.ClearVariantSelection()  # selection stays with main_live.usda / the Kit handler

    traffic = Usd.Stage.Open(str(HERE / "traffic.usdc"))
    cars = UsdGeom.PointInstancer(stage.OverridePrim("/World/Traffic/Cars"))
    visible["vehicles"] = mask(UsdGeom.PointInstancer(traffic.GetPrimAtPath("/World/Traffic/Cars")).GetPositionsAttr(),
                               cars.CreateInvisibleIdsAttr(), 3.2)  # half a car (2.1 m) + one sample (1.1 m)

    # People-facing cameras go where this run's (baseline) walkers actually are, with a clear line of sight.
    zones = [z for z in report["before"].get("problem_zones", []) if isinstance(z, str) and ZONE_RE.match(z)]
    cx, cy = zone_centre(zones[0]) if zones else (0.0, 0.0)
    obstacle_set = obstacles()
    walkers = walker_samples(walker_positions["before"])
    busy = hotspots(walkers) or [(0.0, 0.0)]
    # candidate targets per shot; the best-scoring clear view among them wins
    targets = {"Overview": [(busy[0][0] / 2, busy[0][1] / 2)],  # between the Wada and the busiest spot
               "Street": busy,
               "ProblemZone": hotspots(walkers, (cx, cy), 110.0) or [(cx, cy)]}
    cameras = {}
    for name, candidates in targets.items():
        _, eye, aim, focal = min(
            (place_camera(obstacle_set, walkers, t, SHOTS[name], keep_inside=name == "Street") for t in candidates),
            key=lambda shot: shot[0])
        look_at_camera(stage, name, eye, aim, focal)
        cameras[name] = {"eye": [round(v, 1) for v in eye], "target": [round(v, 1) for v in aim]}
    root.Save()
    return {"visible": visible, "problem_zone": zones[0] if zones else None, "cameras": cameras}


def main():
    build_view()
    report = json.loads((HERE / "sim_report_pune.json").read_text(encoding="utf-8"))
    result = write_run_layer(HERE, report, HERE / "view_run.usdc")
    generated = pune_sim.read_generated()
    generated["view_400m"]["default_run_visibility"] = result["visible"]
    pune_sim.write_generated(generated)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
