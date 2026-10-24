"""Phase 1 only: cached OSM XML -> lightweight, semantically separated OpenUSD.
No simulation calculations. Requires the installed pxr (usd-core) package.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux


def build(source, output):
    root = ET.parse(source).getroot()
    bounds = root.find('bounds').attrib
    west, south, east, north = [float(bounds[k]) for k in ('minlon', 'minlat', 'maxlon', 'maxlat')]
    lon0, lat0 = (west + east) / 2, (south + north) / 2
    def project(lon, lat):
        return (6378137 * math.radians(lon-lon0) * math.cos(math.radians(lat0)),
                6378137 * math.radians(lat-lat0))
    xmin, ymin = project(west, south)
    xmax, ymax = project(east, north)
    nodes = {n.attrib['id']: project(float(n.attrib['lon']), float(n.attrib['lat'])) for n in root.findall('node')}
    def inside(p):
        return xmin <= p[0] <= xmax and ymin <= p[1] <= ymax
    def clip(a, b):
        dx, dy = b[0]-a[0], b[1]-a[1]
        lo, hi = 0., 1.
        for p, q in ((-dx,a[0]-xmin),(dx,xmax-a[0]),(-dy,a[1]-ymin),(dy,ymax-a[1])):
            if p == 0:
                if q < 0: return None
            elif p < 0: lo = max(lo,q/p)
            else: hi = min(hi,q/p)
        if lo >= hi: return None
        return [(a[0]+lo*dx,a[1]+lo*dy),(a[0]+hi*dx,a[1]+hi*dy)]
    output.mkdir(parents=True, exist_ok=True)
    def stage(name):
        s = Usd.Stage.CreateNew(str(output/name))
        UsdGeom.SetStageUpAxis(s, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(s, 1)
        s.SetDefaultPrim(UsdGeom.Xform.Define(s, '/World').GetPrim())
        return s
    city = stage('city_base.usda')
    groups = ['Buildings','Roads','PedestrianPaths','GreenSpaces','Transit']
    for name in groups: UsdGeom.Scope.Define(city, '/World/'+name)
    counts = collections.Counter()
    def mesh(path, points, faces, color, tags=None):
        m = UsdGeom.Mesh.Define(city, path)
        m.CreatePointsAttr(points)
        m.CreateFaceVertexCountsAttr([len(f) for f in faces])
        m.CreateFaceVertexIndicesAttr([i for f in faces for i in f])
        m.CreateSubdivisionSchemeAttr('none')
        m.CreateDoubleSidedAttr(True)
        m.CreateDisplayColorAttr([color])
        m.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(m.GetPointsAttr().Get()))
        if tags:
            m.GetPrim().CreateAttribute('urbantwin:osmTags', Sdf.ValueTypeNames.String).Set(json.dumps(tags,sort_keys=True))
        counts[path.split('/')[2]] += 1
        return m.GetPrim()
    def polygon(path, xy, height, color, tags):
        n = len(xy)
        pts = [(x,y,.04) for x,y in xy]
        faces = [list(range(n))]
        if height:
            pts += [(x,y,height) for x,y in xy]
            faces = [list(range(n,2*n))] + [[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
        return mesh(path,pts,faces,color,tags)
    edges = {}
    skipped = collections.Counter()
    for way in root.findall('way'):
        wid = way.attrib['id']
        tags = {t.attrib['k']:t.attrib['v'] for t in way.findall('tag')}
        ids = [n.attrib['ref'] for n in way.findall('nd')]
        if not all(i in nodes for i in ids):
            skipped['missing_nodes'] += 1
            continue
        xy = [nodes[i] for i in ids]
        closed = len(ids)>3 and ids[0] == ids[-1]
        building = tags.get('building') not in (None,'no')
        green = tags.get('leisure') in ('park','garden') or tags.get('landuse') in ('grass','recreation_ground') or tags.get('natural') in ('wood','scrub')
        if closed and (building or green):
            if not all(inside(p) for p in xy):
                skipped['boundary_polygons'] += 1
                continue
            height, height_source = 0, 'not_applicable'
            if building:
                try:
                    height = float(tags['height'].removesuffix(' m'))
                    height_source = 'osm_height'
                except (KeyError,ValueError):
                    try:
                        height = float(tags['building:levels'])*3
                        height_source = 'assumed_3m_per_osm_level'
                    except (KeyError,ValueError):
                        height, height_source = 12, 'assumed_12m'
                if not 0 < height < 300: height, height_source = 12, 'assumed_12m'
            group = 'Buildings' if building else 'GreenSpaces'
            p = polygon(f'/World/{group}/osm_way_{wid}',xy[:-1],height,(.63,.69,.75) if building else (.25,.48,.23),tags)
            p.CreateAttribute('urbantwin:heightSource',Sdf.ValueTypeNames.String).Set(height_source)
        highway = tags.get('highway')
        if not highway: continue
        pedestrian = highway in ('footway','pedestrian','path','steps')
        if not pedestrian and highway not in ('residential','service','tertiary','secondary','primary','unclassified','living_street','cycleway'): continue
        # OSM segments are visual identifiers, not a routable simulation graph.
        width = 2.5 if pedestrian else 7.
        group = 'PedestrianPaths' if pedestrian else 'Roads'
        for a,b,na,nb in zip(xy,xy[1:],ids,ids[1:]):
            segment = clip(a,b)
            if segment is None: continue
            a,b = segment
            length = math.dist(a,b)
            if length < .05: continue
            nx,ny = -(b[1]-a[1])/length*width/2,(b[0]-a[0])/length*width/2
            key = f'osm_w{wid}_n{na}_n{nb}'
            path = f'/World/{group}/{key}'
            z = .10 if pedestrian else .06
            pts = [(a[0]+nx,a[1]+ny,z),(a[0]-nx,a[1]-ny,z),(b[0]-nx,b[1]-ny,z),(b[0]+nx,b[1]+ny,z)]
            mesh(path,pts,[[0,1,2,3]],(.88,.76,.49) if pedestrian else (.20,.23,.27),tags)
            if pedestrian:
                edges[key] = {'prim_path':path,'points':[[*a,z],[*b,z]],'osm_way_id':wid,'osm_node_ids':[na,nb],'width_m':width,'width_source':'visual_assumption'}
    for node in root.findall('node'):
        tags = {t.attrib['k']:t.attrib['v'] for t in node.findall('tag')}
        if tags.get('railway') not in ('station','subway_entrance') and tags.get('highway') != 'bus_stop': continue
        x,y = nodes[node.attrib['id']]
        if not inside((x,y)): continue
        polygon('/World/Transit/osm_node_'+node.attrib['id'],[(x-1,y-1),(x+1,y-1),(x+1,y+1),(x-1,y+1)],3,(.18,.55,.86),tags)
    city.GetRootLayer().customLayerData = {'source':'OpenStreetMap','attribution':'© OpenStreetMap contributors https://www.openstreetmap.org/copyright','studyArea':'ARCHIVAL SAMPLE: frozen Phase 1 OSM tile','geometry':'OSM footprints; approximate heights and widths; flat terrain'}
    city.GetRootLayer().Save()
    env = stage('environment.usda')
    UsdGeom.Scope.Define(env,'/World/Environment')
    ground = UsdGeom.Cube.Define(env,'/World/Environment/Ground')
    ground.CreateSizeAttr(1)
    ground.AddTranslateOp().Set(Gf.Vec3d(0,0,-.3))
    ground.AddScaleOp().Set(Gf.Vec3f(xmax-xmin+10,ymax-ymin+10,.5))
    ground.CreateDisplayColorAttr([(.38,.40,.36)])
    sun = UsdLux.DistantLight.Define(env,'/World/Environment/Sun')
    sun.CreateIntensityAttr(2500)
    sun.AddRotateXYZOp().Set(Gf.Vec3f(25,-30,-25))
    UsdLux.DomeLight.Define(env,'/World/Environment/Sky').CreateIntensityAttr(500)
    for name,eye,target in [('Overview',(650,-800,850),(0,0,0)),('StudyArea',(200,-250,200),(0,0,0))]:
        cam = UsdGeom.Camera.Define(env,'/World/Cameras/'+name)
        cam.CreateClippingRangeAttr(Gf.Vec2f(.1,10000))
        cam.CreateFocalLengthAttr(30)
        view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*target),Gf.Vec3d(0,0,1))
        cam.AddTransformOp().Set(view.GetInverse())
    env.GetRootLayer().Save()
    main = stage('main.usda')
    main.GetRootLayer().subLayerPaths = ['environment.usda','city_base.usda']
    main.GetRootLayer().Save()
    manifest = {'status':'TEMPORARY REAL-WORLD SAMPLE / NO SIMULATION DATA','origin_wgs84':{'longitude':lon0,'latitude':lat0},'projection':'local equirectangular, R=6378137m; appropriate only for a small study area','axes':{'x':'east','y':'north','z':'up'},'meters_per_unit':1,'bounds_wgs84':bounds,'size_m':[xmax-xmin,ymax-ymin],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source':'https://www.openstreetmap.org/api/0.6/map?bbox='+','.join(map(str,[west,south,east,north])),'attribution':'© OpenStreetMap contributors','license_url':'https://www.openstreetmap.org/copyright','counts':dict(counts),'skipped':dict(skipped),'limitations':['Relations/multipolygons not assembled','Boundary-crossing polygons omitted; road/path centerlines clipped','Flat terrain; visual widths assumed; some heights assumed','No inferred sidewalks, no route-choice graph, no simulation metrics'],'edges':edges}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'counts':dict(counts),'skipped':dict(skipped),'size_m':manifest['size_m'],'edges':len(edges)},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).parent/'data/sample.osm')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'scene')
    args = parser.parse_args()
    build(args.source,args.out)
