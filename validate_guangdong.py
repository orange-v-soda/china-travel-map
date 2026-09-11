"""Independent checks on delivered six-province geometry."""
import json
import shapely
from shapely.geometry import Point,LineString
from shapely.ops import unary_union
from generate_map import ROOT,rings,polygon_parts,adjacent,topology_signature
from validate_geometry import parse
from build_guangdong import inputs,gd_source,bodies
from simplify_boundaries import turns
from simplify_shared import pair_stats
from soften_angles import acute_vertices

def validate():
    s=(ROOT/'dist/south-data.js').read_text();d=json.loads(s.split(' = ',1)[1].split(';\n')[0]);ref=json.loads(s.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions'];report=json.loads((ROOT/'dist/guangdong-report.json').read_text())
    old,oldref,fixed,sha=inputs();regions,raw,source_sha=gd_source();real=bodies(raw)
    assert sha==report['frozenEastSha256'] and source_sha==report['guangdongSourceSha256']
    polys=[parse(r['variants']['east']['path']) for r in d['regions']];assert len(polys)==82 and len({r['id'] for r in d['regions']})==82
    assert all(p.equals(q) for p,q in zip(fixed,polys))
    assert all(p.is_valid and p.area>0 for p in polys) and shapely.coverage_is_valid(polys)
    assert all(not part.interiors for p in polys for part in polygon_parts(p))
    assert abs(sum(p.area for p in polys)-unary_union(polys).area)<1e-6
    assert parse(d['variants']['east']['outline']).equals(unary_union(polys))
    assert not any(part.interiors for part in polygon_parts(unary_union(polys)))
    assert len(polygon_parts(unary_union(polys)))==len(polygon_parts(unary_union(fixed)))+len(report['islands'])
    cross=set()
    for i,r in enumerate(oldref):
        p=max(polygon_parts(parse(r['path'])),key=lambda g:g.area)
        for j,q in enumerate(real):
            if q.boundary.intersection(p.boundary.buffer(.05)).length>3:cross.add((i,61+j))
    assert adjacent(polys)==adjacent(fixed)|{(i+61,j+61) for i,j in adjacent(real)}|cross
    assert topology_signature([max(polygon_parts(p),key=lambda g:g.area) for p in polys[61:]])==topology_signature(real)
    assert unary_union([LineString(x['path']) for x in report['seams']]).equals(unary_union([LineString(x['path']) for x in report['initialSeams']]))
    for seam in report['seams']:
        i=next(i for i,r in enumerate(d['regions']) if r['name']==seam['city'])
        assert polys[i].boundary.intersection(unary_union(fixed).boundary).equals(LineString(seam['path']))
    allowed=set(map(tuple,report['inheritedAcutePoints']))
    # A frozen 315-degree interior leaves only 45 degrees for a new neighbor.
    import math
    from shapely.geometry.polygon import orient
    frozen_angles={tuple(v['point']) for p in fixed for v in acute_vertices(p)}
    possible=set(frozen_angles)
    exterior=orient(max(polygon_parts(unary_union(fixed)),key=lambda g:g.area),sign=1)
    rr=list(exterior.exterior.coords)[:-1]
    for i,b in enumerate(rr):
        a=rr[i-1];c=rr[(i+1)%len(rr)];u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1]);angle=180-math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1]))
        if angle>270.001:possible.add(tuple(b))
    assert allowed<=possible and frozen_angles<=allowed
    actual=[]
    for i,(r,p) in enumerate(zip(d['regions'],polys)):
        assert p.contains(Point(r['variants']['east']['label']))
        if i<61:assert r['variants']['east']['label']==old['regions'][i]['variants']['east']['label']
        for v in acute_vertices(p):actual.append(tuple(v['point']));assert tuple(v['point']) in allowed
        for rr in rings(p):
            for a,b in zip(rr,rr[1:]):
                dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1]);assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
            assert all(0<=x+500<=1660 and 140<=y+530<=1800 for x,y in rr)
    assert set(actual)==allowed and len(actual)==len(allowed)
    for i,(p,r) in enumerate(zip(polys[61:],real)):
        mainland=max(polygon_parts(p),key=lambda g:g.area)
        assert mainland.intersection(r).area/mainland.union(r).area>=.75
        assert abs(mainland.area-r.area)/r.area<=.15
        assert turns(p)==report['cities'][i]['turns']
        assert turns(mainland)==report['cities'][i]['mainlandTurns']
    for island in report['islands']:
        city=next(i for i,r in enumerate(d['regions']) if r['name']==island['city']);g=parse(island['path'])
        assert polys[city].covers(g) and g.distance(unary_union([p if i!=city else p.difference(g) for i,p in enumerate(polys)]))>=2.5
    assert report['sharedPairs']==pair_stats(polys,[r['name'] for r in d['regions']])
    assert report['optimization']['afterObjective'][2]+sum(turns(parse(s['path'])) for s in report['islands'])==sum(turns(p) for p in polys)
    xiangxi=next(r for r in d['regions'] if r['id']=='433100')
    assert xiangxi['name']=='湘西' and xiangxi['fullName']=='湘西土家族苗族自治州' and xiangxi['administrativeType']=='自治州'
    assert report['preparation']['omittedParts']==sum(len(polygon_parts(p))-1 for p in raw)-len(report['islands'])
    assert len(report['preparation']['filledHoles'])==4
    assert len(report['islands'])==4
    huaihua=next(r for r in ref if r['name']=='怀化')
    assert sum(len(p.interiors) for p in polygon_parts(parse(huaihua['path'])))==1
    assert len(ref)==82
    assert all(parse(r['path']).equals(q) for r,q in zip(ref[61:],raw))
    assert all(parse(r['path']).equals(parse(q['path'])) for r,q in zip(ref,oldref))
    for r in ref:assert parse(r['path']).contains(Point(r['label']))
    print(json.dumps({'cities':82,'frozenCities':61,'crossProvincePairsAdded':len(cross),'adjacencies':len(adjacent(polys)),'overlaps':0,'unionHoles':0,'unionComponents':len(polygon_parts(unary_union(polys))),'inheritedAcuteAngles':len(actual),'guangdongInheritedAcuteAngles':sum(len(acute_vertices(p)) for p in polys[61:]),'unexpectedAcuteAngles':0,'guangdongTurns':[turns(p) for p in polys[61:]]},ensure_ascii=False))
if __name__=='__main__':validate()
