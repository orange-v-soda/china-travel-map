"""Generate geography-first maps from the retained geographic SVG path data.

Requires Shapely 2.1.2; browser output remains dependency-free.
"""
import json
import math
from pathlib import Path
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union, polygonize, polylabel, linemerge

ROOT=Path(__file__).parent
TOLERANCE=6.0  # SVG units: coverage simplification threshold, not maximum displacement.
GRID=1.0
ITERATION_TOLERANCE=12.0
MAX_ITERATIONS=30
TINY_AREA=2.0

def read_reference():
    return json.loads((ROOT/'dist/reference-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))

def geometry_from_path(path):
    # Match SVG even-odd filling, including nested holes in later provinces.
    polys=[]
    for part in path.split('M')[1:]:
        coords=[tuple(map(float,p.split(','))) for p in part.split('Z')[0].strip().replace('L','').split()]
        polys.append(Polygon(coords))
    out=polys[0]
    for p in polys[1:]:out=out.symmetric_difference(p)
    return out

def polygon_parts(g):return list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
def rings(g):
    for p in polygon_parts(g):
        yield list(p.exterior.coords)
        for r in p.interiors:yield list(r.coords)

def adjacent(polys):
    return {(i,j) for i,p in enumerate(polys) for j,q in enumerate(polys) if i<j and p.boundary.intersection(q.boundary).length>1e-6}

def route(a,b,grid=GRID):
    """Canonical 0/45/90-degree routing. Both cities reuse the identical route."""
    a=tuple(round(x/grid)*grid for x in a);b=tuple(round(x/grid)*grid for x in b)
    if a>b:return route(b,a,grid)[::-1]
    dx=b[0]-a[0];dy=b[1]-a[1];sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
    d=min(abs(dx),abs(dy))
    if abs(dx)>=abs(dy):
        h=round((abs(dx)-d)/(2*grid))*grid;p=(a[0]+sx*h,a[1])
    else:
        h=round((abs(dy)-d)/(2*grid))*grid;p=(a[0],a[1]+sy*h)
    q=(p[0]+sx*d,p[1]+sy*d);out=[]
    for v in [a,p,q,b]:
        if not out or v!=out[-1]:out.append(v)
    return out

def octilinear(polys,grid=GRID):
    lines=[]
    for poly in polys:
        for ring in rings(poly):
            for a,b in zip(ring,ring[1:]):
                rr=route(a,b,grid)
                if len(rr)>1:lines.append(LineString(rr))
    # Polygonize the shared, noded network once, so faces cannot overlap.
    faces=list(polygonize(unary_union(lines)));groups=[[] for p in polys]
    for face in faces:
        overlaps=[face.intersection(p).area for p in polys]
        owner=max(range(len(polys)),key=lambda i:overlaps[i])
        if max(overlaps)==0:owner=min(range(len(polys)),key=lambda i:face.distance(polys[i]))
        groups[owner].append(face)
    return [unary_union(g) for g in groups]

def svg_path(g):
    return ' '.join(' '.join(('M' if i==0 else 'L')+f'{x:.4f},{y:.4f}' for i,(x,y) in enumerate(ring))+' Z' for ring in rings(g))

def label_for(g,preferred):
    if g.contains(Point(preferred)):return preferred
    p=max(polygon_parts(g),key=lambda p:p.area).representative_point()
    return [round(p.x,4),round(p.y,4)]

def stats(original,polys):
    merged=unary_union(polys);base=unary_union(original)
    return {'vertices':int(shapely.get_num_coordinates(polys).sum()),'provinceIou':round(base.intersection(merged).area/base.union(merged).area,4),'minCityIou':round(min(p.intersection(q).area/p.union(q).area for p,q in zip(original,polys)),4),'areaRatio':round(max(p.area for p in polys)/min(p.area for p in polys),3)}

def component_signature(g):
    return (len(polygon_parts(g)),tuple(sorted(len(p.interiors) for p in polygon_parts(g))))

from functools import lru_cache

@lru_cache(maxsize=8192)
def contact_signature(p,q):
    # Shapely geometries are immutable: unchanged borders can reuse exact results.
    x=p.boundary.intersection(q.boundary)
    if x.is_empty:return ('none',0)
    if x.length<1e-6:return ('point',len(x.geoms) if hasattr(x,'geoms') else 1)
    if x.geom_type=='LineString':return ('line',1)
    if x.geom_type=='MultiLineString':
        merged=linemerge(x);return ('line',len(merged.geoms) if hasattr(merged,'geoms') else 1)
    return (x.geom_type,len(x.geoms) if hasattr(x,'geoms') else 1)

def topology_signature(polys):
    pairs=[(i,j,contact_signature(p,polys[j])) for i,p in enumerate(polys) for j in range(i+1,len(polys))]
    return (tuple(component_signature(p) for p in polys),component_signature(unary_union(polys)),tuple(pairs))

def lock_tiny_components(real):
    locked=[]
    for g in real:
        tiny=[]
        for part in polygon_parts(g):
            if part.area>=TINY_AREA:continue
            c=polylabel(part,tolerance=.0001);x=round(c.x,3);y=round(c.y,3)
            radius=math.floor(c.distance(part.boundary)*.7*1000)/1000
            assert radius>0,'Tiny component needs finer local precision'
            diamond=Polygon([(x-radius,y),(x,y-radius),(x+radius,y),(x,y+radius)])
            assert part.covers(diamond),'Tiny component moved outside source'
            tiny.append(diamond)
        locked.append(tiny)
    return locked

def attach_locked(active,locked):return [unary_union([p,*ll]) for p,ll in zip(active,locked)]

def validate_step(polys,expected):
    if not all(p.is_valid and not p.is_empty for p in polys):return 'invalid_region'
    if not shapely.coverage_is_valid(polys):return 'invalid_coverage'
    if topology_signature(polys)!=expected:return 'topology_changed'
    if abs(sum(p.area for p in polys)-unary_union(polys).area)>1e-6:return 'overlap'
    for p in polys:
        for rr in rings(p):
            for a,b in zip(rr,rr[1:]):
                dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1])
                if min(dx,dy)>1e-6 and abs(dx-dy)>1e-6:return 'invalid_direction'
    return None

def run_iterations(real):
    expected=topology_signature(real)
    # The current contour-simplified map is the input to the first fit.
    simplified=list(shapely.coverage_simplify(real,TOLERANCE))
    locked=lock_tiny_components(real)
    active=[unary_union([p for p in polygon_parts(g) if p.area>=TINY_AREA]) for g in simplified]
    active=octilinear(active);current=attach_locked(active,locked)
    assert validate_step(current,expected) is None,'Initial fit violates topology'
    snapshots=[current];logs=[{'iteration':0,'areaChange':None,'state':'initial',**stats(real,current)}]
    previous=[active];reason='iteration_limit';verified=False
    for iteration in range(1,MAX_ITERATIONS+1):
        candidate=octilinear(shapely.coverage_simplify(active,ITERATION_TOLERANCE))
        complete=attach_locked(candidate,locked)
        error=validate_step(complete,expected)
        if error:reason='topology_blocked';break
        delta=sum(p.symmetric_difference(q).area for p,q in zip(active,candidate))
        if delta>1e-8 and any(all(p.equals(q) for p,q in zip(old,candidate)) for old in previous):
            reason='cycle_detected';break
        snapshots.append(complete);logs.append({'iteration':iteration,'areaChange':round(delta,8),'state':'accepted',**stats(real,complete)})
        active=candidate;previous.append(active)
        if delta<1e-8:
            extra=octilinear(shapely.coverage_simplify(active,ITERATION_TOLERANCE))
            verified=all(p.equals(q) for p,q in zip(active,extra)) and validate_step(attach_locked(extra,locked),expected) is None
            if verified:reason='fixed_point';logs[-1]['state']='fixed_point';break
    return snapshots,logs,{'status':reason,'iteration':logs[-1]['iteration'],'verifiedExtraPass':verified,'protectedComponents':sum(map(len,locked)),'maxIterations':MAX_ITERATIONS}

def generate():
    reference=read_reference();real=[geometry_from_path(r['path']) for r in reference['regions']]
    assert all(p.is_valid for p in real) and shapely.coverage_is_valid(real)
    snapshots,logs,convergence=run_iterations(real)
    variants={f'iteration_{i}':polys for i,polys in enumerate(snapshots)}
    expected=adjacent(real);regions=[]
    for i,r in enumerate(reference['regions']):
        regions.append({'id':r['id'],'name':r['name'],'variants':{mode:{'path':svg_path(polys[i]),'label':label_for(polys[i],r['label'])} for mode,polys in variants.items()},'neighbors':sorted(reference['regions'][j if i==k else k]['id'] for k,j in expected if i in (k,j))})
    data={'version':'0.4.0','basis':'iterative-octilinear','sourceSha256':reference['sha256'],'tolerance':TOLERANCE,'iterationTolerance':ITERATION_TOLERANCE,'grid':GRID,'defaultVariant':list(variants)[-1],'convergence':convergence,'iterations':logs,'regions':regions,'variants':{mode:{'outline':svg_path(unary_union(polys)),**stats(real,polys)} for mode,polys in variants.items()},'sourceVertices':int(shapely.get_num_coordinates(real).sum())}
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'dist/iteration-report.json').write_text(json.dumps({'parameters':{'initialTolerance':TOLERANCE,'iterationTolerance':ITERATION_TOLERANCE,'grid':GRID},'convergence':convergence,'iterations':logs},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'convergence':convergence,'iterations':logs},ensure_ascii=False,indent=2))

if __name__=='__main__':
    generate()
    from simplify_boundaries import generate as generate_shortcuts
    generate_shortcuts()

    from soften_angles import generate as generate_softened
    generate_softened()

    from compact_lobes import generate as generate_compact
    generate_compact()

    from simplify_shared import generate as generate_shared
    generate_shared()
