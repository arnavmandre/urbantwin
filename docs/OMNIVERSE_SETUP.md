# UrbanTwin AI — environment audit and scene setup

## Current status: Phase 8

Phases 1–8 have been implemented and visually confirmed through the staged demo.
The current entry point is `phase8/scene/main.usda`, which packages the Stressed
and Intervention OpenUSD variants. See the [Phase 8 guide](../phase8/README.md).
The Phase 1 base and intermediate phase scenes remain as reproducible checkpoints.

Use this setup guide for the real OSM city. `../legacy/synthetic_city/OMNIVERSE_SETUP.md`
describes the older synthetic example.

The JSON contract and mock fixtures are in `phase3/`; agents, routes, metrics,
and proposals are introduced in phases 4–7. Each phase README documents its own
checkpoint. Phase 9 waits for an actual teammate simulator output file.

The audit and initial manual instructions below are historical Phase 1 records.

Audited 2026-09-19. The following section records the original Phase 0 environment.

## AVAILABLE

- Windows 11 Home Single Language, build 10.0.26200.
- NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB VRAM; driver 582.05.
- Python 3.14.7; `pxr` OpenUSD 26.8 imports and opens existing binary USD.
- Running Omniverse app: `urbantwin.kit`, version 0.1.0, from
  `C:\Users\arnav\omniverse\kit-app-template`.
- Its app configuration includes `omni.kit.menu.file`, `omni.kit.window.stage`,
  `omni.kit.viewport.window`, and `omni.kit.viewport.menubar.camera`.
  These are inspected configuration entries; successful rendering still needs a viewport check.
- Local USD files need no Nucleus server, asset converter, or Blender connector.

## MISSING / NOT FOUND

- Blender executable not on PATH; no Blender installation found in the normal
  Program Files location or inspected Windows uninstall entries.
- No Blender user configuration/add-ons directory; BlenderGIS not found.
  A portable installation elsewhere is not ruled out.
- `usdview` and `usdcat` not on PATH. Python `pxr` supplies the required authoring/readback API.

## MANUAL INSTALL REQUIRED

None for the selected Phase 1 pipeline. The existing Kit app and `pxr` suffice.
Blender/BlenderGIS are optional, not prerequisites.

## Repository findings and blockers

Existing files are preserved. `legacy/synthetic_city/urbantwin_city.py` produces a synthetic grid,
not a real geographic import; it includes assumed shade/capacity calculations
that are outside this new visualization-only scope. `legacy/synthetic_city/city.json` is a
static synthetic city description, not an external simulator state contract.
`legacy/empty_omniverse_stage.usd` has an empty `/World`, light and render settings, Y-up and 0.01
metres/unit. Do not merge its centimetre/Y-up coordinates directly with this scene.
The new scene is Z-up, metres. The earlier files' Y-up mapping needs an explicit
adapter if used later; do not silently reinterpret coordinates.

Blocker to acceptance: the city must be opened and visually inspected in Kit.
GPU memory is finite; smooth navigation and RTX performance are unverified.
The downloaded OSM data is real, but heights/widths can be assumptions, terrain
is flat, relation/multipolygon assembly is not implemented, and polygons crossing
the study boundary are omitted. Road/path centerlines are clipped, but ribbons can
extend half a width beyond the boundary. OSM pedestrian data is incomplete and
may contain overlapping area boundaries; these visuals are not a routable graph.

## Selected pipeline and Phase 1 plan

OSM cached XML → Python OpenUSD authoring → modular USDA → existing UrbanTwin Kit app.
This is a project-specific importer using real OpenUSD APIs, not an NVIDIA OSM extension.
NVIDIA's supported application path is Kit App Template; the old Launcher was
deprecated on October 1, 2025. Reuse the working app instead of reinstalling it.

This section records archival Phase 1 setup, not the active city. Do not rebuild
the frozen Phase 1–8 assets. See `PUNE_CITY.md` for the sole Pune demo.

1. Download and cache a small OSM extract. **Done for the archival prototype.**
2. Build low-detail separate buildings, road/path ribbons, green areas, and transit
   markers, retaining OSM tags and identifiers. **Done.**
3. Save `city_base.usda`, `environment.usda`, and composing `main.usda`. **Done.**
4. Reopen with OpenUSD and check geometry, units, bounds, composition, and ID lookup.
5. Open in Kit and inspect navigation, appearance and performance. **MANUAL STEP REQUIRED.**
6. Correct any visual defects before Phase 1 is accepted. Later phases remain deferred.

Regenerate from the cache (no network and no Blender required):

```powershell
cd C:\Users\arnav\Argus
python phase1\build_city.py
```

The script accepts `--source path\to\extract.osm --out path\to\scene`.
It derives origin and dimensions from the XML bounds, using the source extract.
Use an approximately 500–1000 m study area. The local equirectangular projection
is an approximation for small areas, not a survey-grade or terrain model.
The camera presets may need adjustment for a different study area's size.

## MANUAL STEP REQUIRED — do this now

1. Switch to the already-running **urbantwin** window. Save any unsaved work under
   its own filename before opening a different stage.
2. Choose **File → Open** and enter
   `C:\Users\arnav\Argus\phase1\scene\main.usda`. Click **Open**.
3. Wait for loading/shader compilation. In the viewport camera dropdown, select
   `/World/Cameras/Overview` (it may be listed as `Overview`).
4. In the **Stage** panel, expand `/World`. Confirm `Buildings`, `Roads`,
   `PedestrianPaths`, `GreenSpaces`, `Transit`, `Environment`, and `Cameras` exist.
5. Grey-blue extrusions are buildings; dark ribbons are roads; tan ribbons are
   mapped pedestrian paths; green surfaces are green areas; blue blocks mark
   OSM transit nodes. These colours are categories, not heat/crowd metrics.
6. Switch the viewport back to **Perspective** to navigate without editing the
   saved camera. Select a building in Stage and press **F** to frame it; orbit
   with **Alt + left mouse drag**. Return to `Overview` for the full scene.
7. Check that buildings, roads, paths and green areas are visible and navigation
   responds smoothly. Report any blank viewport, errors, floating geometry, or
   slow navigation. A screenshot helps diagnose appearance.

Stop here. Phase 1 is not visually accepted until you perform this check.
No GUI operation has been automated or claimed successful.

## Proposed final USD organization (later phases)

```text
main.usda
  city_base.usda        existing static geometry
  environment.usda     lighting and cameras
  simulation.usda      future agents/routes/metric overlays
  interventions.usda   future proposed geometry

/World
  /Buildings
  /Roads
  /PedestrianPaths/<stable edge id>
  /GreenSpaces
  /Transit
  /Environment
  /Cameras
  /Simulation
    /Agents
    /Routes
    /HeatZones
    /CrowdZones
  /Interventions
```

All layers will use metres and Z-up. Use sublayers for these independent scopes.
For later before/after, prefer separate complete snapshot layers sharing the same
base city; replace the active snapshot rather than accumulating stale overrides.
Variants can package curated demo states later, but are not needed for file playback.
`manifest.json` maps current OSM segment IDs to exact prim paths and coordinates.
Do not regenerate ordinal `edge_001` IDs from import order. If the teammate wants
those aliases, freeze an explicit alias mapping against the manifest hash.

## Optional Blender route

If mesh editing becomes necessary, install Blender from its official distribution
and check that exact version against BlenderGIS's documentation before installing
the add-on. BlenderGIS supports OSM XML import. No compatibility has been tested here.
Import the cached extract, retain geographic origin/scale and separate objects,
then export with Blender's built-in USD exporter. Validate metres, up-axis and
prim IDs after export. Avoid FBX/OBJ detours that discard semantic structure.
No Blender GUI action is required by the selected pipeline.

## Sources and attribution

- [NVIDIA USD Composer build route](https://docs.omniverse.nvidia.com/composer/latest/how-to-build.html)
- [NVIDIA Launcher migration](https://developer.nvidia.com/omniverse/legacy-tools)
- [Blender USD import/export](https://docs.blender.org/manual/en/4.4/files/import_export/usd.html)
- [BlenderGIS OSM import](https://github.com/domlysz/BlenderGIS/wiki/OSM-import)
- [OpenUSD stage units](https://openusd.org/25.11/api/group___usd_geom_linear_units__group.html)
- [OpenUSD composition](https://openusd.org/dev/glossary.html)

Map data © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).
Retain attribution with scene distribution and display it in demo captions/screenshots.
Source XML and SHA-256 are retained for reproducibility. This scene contains no
real or mock simulation results.
