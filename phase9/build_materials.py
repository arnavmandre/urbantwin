"""
Give the city real materials, driven by the OSM tags already in the stage.

Phase 1 painted all 623 buildings one hardcoded grey and every road, path and
green space a single flat colour - but it also stored each object's complete
OSM tag dictionary on the prim as `urbantwin:osmTags`. The data for a realistic
city was already there; only the use of it was missing.

This authors `phase9/scene/materials.usda`: a set of shared UsdPreviewSurface
materials plus one `over` per prim binding the right one, inside a `cityLook`
variant set on /World:

    realistic - brick / stone / concrete / glass / render from building:material
                and building:colour, roofs coloured separately from roof:colour
    analytic  - desaturated, value ramped by height, so simulation colour
                overlays read clearly on top of it

Roofs are a separate material via a UsdGeom.Subset over face 0. Buildings are
extruded prisms whose face 0 is the roof cap and faces 1..n the walls
(phase1/build_city.py:62-68), so the split needs no new geometry. This is the
detail that stops buildings reading as solid extrusions.

Run:  python phase9/build_materials.py
Out:  phase9/scene/materials.usda
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT / "phase1" / "scene" / "main.usda"
OUT = HERE / "scene" / "materials.usda"

LOOKS = "/World/Phase9Looks"

# --- palette -------------------------------------------------------------
# (diffuse, roughness, metallic). Kept to a small shared set: 623 materials
# would bloat the stage for no visual gain.
MATERIALS = {
    # walls
    "brick_red":     ((0.478, 0.286, 0.216), 0.88, 0.0),
    "brick_brown":   ((0.392, 0.271, 0.208), 0.88, 0.0),
    "brick_yellow":  ((0.549, 0.467, 0.376), 0.86, 0.0),   # yellow stock brick
    "stone":         ((0.706, 0.678, 0.612), 0.80, 0.0),
    "portland":      ((0.788, 0.769, 0.714), 0.76, 0.0),
    "concrete":      ((0.588, 0.588, 0.573), 0.85, 0.0),
    "render_white":  ((0.839, 0.827, 0.800), 0.72, 0.0),
    "render_cream":  ((0.800, 0.749, 0.651), 0.74, 0.0),
    "glass":         ((0.298, 0.396, 0.447), 0.16, 0.30),
    "timber":        ((0.443, 0.333, 0.235), 0.82, 0.0),
    "civic":         ((0.643, 0.616, 0.580), 0.78, 0.0),
    "retail":        ((0.667, 0.596, 0.541), 0.80, 0.0),
    # roofs
    "roof_slate":    ((0.235, 0.243, 0.263), 0.72, 0.0),
    "roof_grey":     ((0.357, 0.365, 0.380), 0.76, 0.0),
    "roof_lead":     ((0.412, 0.427, 0.427), 0.62, 0.15),
    "roof_glass":    ((0.318, 0.427, 0.451), 0.18, 0.25),
    "roof_tile":     ((0.463, 0.286, 0.227), 0.84, 0.0),
    # ground plane types
    "asphalt":       ((0.157, 0.165, 0.180), 0.92, 0.0),
    "paving":        ((0.475, 0.459, 0.435), 0.84, 0.0),
    "setts":         ((0.373, 0.361, 0.349), 0.88, 0.0),
    "grass_park":    ((0.290, 0.435, 0.235), 0.92, 0.0),
    "grass_garden":  ((0.337, 0.486, 0.267), 0.90, 0.0),
    "pitch":         ((0.353, 0.518, 0.318), 0.90, 0.0),
    "playground":    ((0.545, 0.455, 0.302), 0.88, 0.0),
    "transit_blue":  ((0.157, 0.451, 0.729), 0.55, 0.0),
    # analytic look
    "an_low":        ((0.612, 0.620, 0.635), 0.85, 0.0),
    "an_mid":        ((0.525, 0.537, 0.561), 0.85, 0.0),
    "an_high":       ((0.427, 0.443, 0.475), 0.85, 0.0),
    "an_roof":       ((0.322, 0.337, 0.365), 0.85, 0.0),
    "an_ground":     ((0.243, 0.251, 0.267), 0.92, 0.0),
    "an_green":      ((0.310, 0.380, 0.325), 0.90, 0.0),
    "an_path":       ((0.447, 0.435, 0.412), 0.88, 0.0),
}

# OSM colour words seen in this extract, mapped onto the palette above.
COLOUR_WORDS = {
    "brown": "brick_brown", "darkbrown": "brick_brown", "dark_brown": "brick_brown",
    "red": "brick_red", "white": "render_white", "lightgrey": "stone",
    "light_grey": "stone", "grey": "concrete", "gray": "concrete",
    "black": "roof_slate", "green": "timber", "orange": "brick_red",
    "beige": "render_cream", "cream": "render_cream", "yellow": "brick_yellow",
}
MATERIAL_WORDS = {
    "brick": "brick_yellow", "stone": "stone", "concrete": "concrete",
    "glass": "glass", "plaster": "render_white", "wood": "timber",
    "timber_framing": "timber", "metal": "concrete",
}
TYPE_WALL = {
    "house": "brick_yellow", "terrace": "brick_yellow", "apartments": "brick_brown",
    "dormitory": "brick_brown", "residential": "brick_yellow",
    "university": "portland", "college": "portland", "school": "brick_red",
    "hospital": "portland", "hotel": "render_cream", "office": "glass",
    "commercial": "concrete", "retail": "retail", "supermarket": "retail",
    "kiosk": "timber", "church": "stone", "museum": "portland",
    "public": "civic", "train_station": "civic", "chimney": "brick_red",
}
ROOF_WORDS = {
    "darkgrey": "roof_slate", "dark_grey": "roof_slate", "black": "roof_slate",
    "grey": "roof_grey", "gray": "roof_grey", "lightgrey": "roof_lead",
    "white": "roof_lead", "blue": "roof_lead", "green": "roof_grey",
    "brown": "roof_tile", "red": "roof_tile", "beige": "roof_tile",
}
ROOF_MATERIAL = {"glass": "roof_glass", "slate": "roof_slate", "stone": "roof_grey",
                 "metal": "roof_lead", "tile": "roof_tile", "copper": "roof_lead"}


def tags_of(prim) -> dict:
    attr = prim.GetAttribute("urbantwin:osmTags")
    try:
        return json.loads(attr.Get()) if attr and attr.Get() else {}
    except (ValueError, TypeError):
        return {}


def hex_to_name(value: str) -> str | None:
    """Rough bucket for the handful of #rrggbb colours in this extract."""
    v = value.strip().lstrip("#")
    if len(v) != 6:
        return None
    try:
        r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum > 0.75:
        return "render_white"
    if lum < 0.28:
        return "roof_slate"
    return "brick_brown" if r > b else "concrete"


def wall_material(tags: dict) -> str:
    """Explicit colour/material first, then building class, then a neutral."""
    colour = (tags.get("building:colour") or "").lower()
    if colour:
        hit = COLOUR_WORDS.get(colour) or hex_to_name(colour)
        if hit:
            return hit
    material = (tags.get("building:material") or "").lower()
    if material in MATERIAL_WORDS:
        return MATERIAL_WORDS[material]
    kind = (tags.get("building") or "").lower()
    if kind in TYPE_WALL:
        return TYPE_WALL[kind]
    if tags.get("shop") or tags.get("amenity") in ("restaurant", "cafe", "fast_food", "pub"):
        return "retail"
    if tags.get("amenity") in ("university", "library", "theatre", "hospital", "college"):
        return "civic"
    # `building=yes` with no other hint: vary by level count so blocks differ.
    try:
        levels = float(tags.get("building:levels", 0))
    except ValueError:
        levels = 0
    if levels >= 7:
        return "concrete"
    if levels >= 4:
        return "brick_yellow"
    return "brick_brown"


def roof_material(tags: dict) -> str:
    colour = (tags.get("roof:colour") or "").lower()
    if colour:
        hit = ROOF_WORDS.get(colour) or hex_to_name(colour)
        if hit:
            return hit if hit.startswith("roof_") else "roof_grey"
    material = (tags.get("roof:material") or "").lower()
    if material in ROOF_MATERIAL:
        return ROOF_MATERIAL[material]
    return "roof_slate"


def ground_material(scope: str, tags: dict) -> str:
    if scope == "Roads":
        surface = (tags.get("surface") or "").lower()
        if surface in ("paving_stones", "sett", "cobblestone"):
            return "setts"
        return "asphalt"
    if scope == "PedestrianPaths":
        surface = (tags.get("surface") or "").lower()
        return "setts" if surface in ("sett", "cobblestone") else "paving"
    if scope == "GreenSpaces":
        leisure = (tags.get("leisure") or "").lower()
        if leisure == "garden":
            return "grass_garden"
        if leisure == "pitch":
            return "pitch"
        if leisure == "playground":
            return "playground"
        return "grass_park"
    return "transit_blue"


def analytic_material(scope: str, height: float) -> str:
    if scope == "Buildings":
        return "an_low" if height < 10 else "an_mid" if height < 20 else "an_high"
    if scope == "GreenSpaces":
        return "an_green"
    if scope == "PedestrianPaths":
        return "an_path"
    return "an_ground"


def define_materials(stage):
    UsdGeom.Scope.Define(stage, LOOKS)
    for name, (rgb, rough, metal) in MATERIALS.items():
        mat = UsdShade.Material.Define(stage, f"{LOOKS}/{name}")
        sh = UsdShade.Shader.Define(stage, f"{LOOKS}/{name}/Shader")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")


def collect(stage):
    """-> [(scope, prim_path, tags, height, face_count)]"""
    rows = []
    for scope in ("Buildings", "Roads", "PedestrianPaths", "GreenSpaces", "Transit"):
        parent = stage.GetPrimAtPath(f"/World/{scope}")
        if not parent:
            continue
        for prim in parent.GetChildren():
            mesh = UsdGeom.Mesh(prim)
            pts = mesh.GetPointsAttr().Get() or []
            counts = mesh.GetFaceVertexCountsAttr().Get() or []
            height = max((p[2] for p in pts), default=0.0)
            rows.append((scope, prim.GetPath().pathString, tags_of(prim),
                         float(height), len(counts)))
    return rows


def bind(stage, path, material, roof=None):
    prim = stage.OverridePrim(path)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(
        UsdShade.Material.Get(stage, f"{LOOKS}/{material}"))
    if roof:
        # Face 0 is the roof cap on every extruded building.
        subset = UsdGeom.Subset.Define(stage, f"{path}/RoofFace")
        subset.CreateElementTypeAttr(UsdGeom.Tokens.face)
        subset.CreateFamilyNameAttr("materialBind")
        subset.CreateIndicesAttr([0])
        UsdShade.MaterialBindingAPI.Apply(subset.GetPrim()).Bind(
            UsdShade.Material.Get(stage, f"{LOOKS}/{roof}"))


def build() -> Path:
    src = Usd.Stage.Open(str(BASE))
    rows = collect(src)
    print(f"{len(rows)} prims across 5 scopes")

    stage = Usd.Stage.CreateNew(str(OUT)) if not OUT.exists() else Usd.Stage.Open(str(OUT))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    stage.GetRootLayer().documentation = (
        "City materials resolved from the OSM tags already stored on each prim "
        "as urbantwin:osmTags. Variant set 'cityLook': realistic | analytic. "
        "Regenerate with phase9/build_materials.py."
    )
    define_materials(stage)

    vset = world.GetPrim().GetVariantSets().AddVariantSet("cityLook")
    used = {}

    for variant in ("realistic", "analytic"):
        vset.AddVariant(variant)
        vset.SetVariantSelection(variant)
        counter = collections.Counter()
        with vset.GetVariantEditContext():
            for scope, path, tags, height, faces in rows:
                if variant == "realistic":
                    if scope == "Buildings":
                        wall, roof = wall_material(tags), roof_material(tags)
                    else:
                        wall, roof = ground_material(scope, tags), None
                else:
                    wall = analytic_material(scope, height)
                    roof = "an_roof" if scope == "Buildings" else None
                bind(stage, path, wall, roof if faces > 1 else None)
                counter[wall] += 1
        used[variant] = counter

    vset.SetVariantSelection("realistic")
    stage.GetRootLayer().Save()

    for variant, counter in used.items():
        top = ", ".join(f"{k}:{v}" for k, v in counter.most_common(6))
        print(f"  {variant:9s} {len(counter):2d} distinct materials  ({top})")
    print(f"\nwrote {OUT}")
    return OUT


if __name__ == "__main__":
    build()
