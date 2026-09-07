"""Generate geography-first maps from the retained geographic SVG path data.

Requires Shapely 2.1.2; browser output remains dependency-free.
"""
import json
import re
from pathlib import Path
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union, polygonize

ROOT=Path(__file__).parent
TOLERANCE=6.0  # SVG units: coverage simplification threshold, not maximum displacement.
GRID=1.0

def read_reference():
    return json.loads((ROOT/'dist/reference-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))

def geometry_from_path(path):
    # The retained source consists of exterior rings, including Jiujiang islands.
    polys=[]
    for part in path.split('M')[1:]:
        coords=[tuple(map(float,p.split(','))) for p in part.split('Z')[0].strip().replace('L','').split()]
        polys.append(Polygon(coords))
    return MultiPolygon(polys) if len(polys)>1 else polys[0]

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

def octilinear(polys):
    lines=[]
    for poly in polys:
        for ring in rings(poly):
            for a,b in zip(ring,ring[1:]):
                rr=route(a,b)
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

def generate():
    reference=read_reference();real=[geometry_from_path(r['path']) for r in reference['regions']]
    assert all(p.is_valid for p in real) and shapely.coverage_is_valid(real)
    expected=adjacent(real)
    simplified=list(shapely.coverage_simplify(real,TOLERANCE))
    diagonal=octilinear(simplified)
    variants={'simplified':simplified,'diagonal':diagonal}
    for mode,polys in variants.items():
        assert all(p.is_valid and not p.is_empty for p in polys)
        assert shapely.coverage_is_valid(polys),mode
        assert adjacent(polys)==expected,(mode,'adjacency changed')
        assert abs(sum(p.area for p in polys)-unary_union(polys).area)<1e-6
    regions=[]
    for i,r in enumerate(reference['regions']):
        regions.append({'id':r['id'],'name':r['name'],'variants':{mode:{'path':svg_path(polys[i]),'label':label_for(polys[i],r['label'])} for mode,polys in variants.items()},'neighbors':sorted(reference['regions'][j if i==k else k]['id'] for k,j in expected if i in (k,j))})
    data={'version':'0.3.0','basis':'geographic-boundaries','sourceSha256':reference['sha256'],'tolerance':TOLERANCE,'grid':GRID,'regions':regions,'variants':{mode:{'outline':svg_path(unary_union(polys)),**stats(real,polys)} for mode,polys in variants.items()},'sourceVertices':int(shapely.get_num_coordinates(real).sum())}
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    print(json.dumps({'sourceVertices':data['sourceVertices'],'variants':{k:{x:y for x,y in v.items() if x!='outline'} for k,v in data['variants'].items()},'adjacencies':len(expected)},ensure_ascii=False,indent=2))

if __name__=='__main__':generate()
