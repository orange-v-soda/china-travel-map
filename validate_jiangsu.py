"""Validate the delivered Jiangsu extension independently of optimizer decisions."""
import json,math
from shapely.geometry import Point,LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from generate_map import ROOT,geometry_from_path as parse,polygon_parts,adjacent,topology_signature,rings,validate_step
from build_jiangsu import inputs,js_source,bodies,retained_old_sources
from validate_balanced import turn_count,validate as validate_balance
from soften_angles import acute_vertices
from simplify_shared import pair_stats

def validate(check_balance=True):
    text=(ROOT/'dist/jiangsu-data.js').read_text();d=json.loads(text.split(' = ',1)[1].split(';\n')[0]);refs=json.loads(text.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions'];report=json.loads((ROOT/'dist/jiangsu-report.json').read_text())
    old,oldrefs,fixed,sha=inputs();new,raw,source_sha=js_source();real=bodies(raw)
    assert report['frozenEastSha256']==sha and report['jiangsuSourceSha256']==source_sha
    assert len(d['regions'])==98 and len({r['id'] for r in d['regions']})==98
    polys=[parse(r['variants']['east']['path']) for r in d['regions']]
    assert all(p.equals(q) for p,q in zip(fixed,polys))
    assert validate_step(polys,topology_signature(polys)) is None
    union=unary_union(polys)
    assert all(not q.interiors for p in polys for q in polygon_parts(p))
    assert not any(p.interiors for p in polygon_parts(union))
    assert parse(d['variants']['east']['outline']).equals(union)
    assert len(polygon_parts(union))==10  # Retained Chongming joins Jiangsu.
    cross=set()
    for i,p in enumerate(retained_old_sources(oldrefs,fixed)):
        for j,q in enumerate(real):
            if q.boundary.intersection(p.boundary.buffer(.05)).length>3:cross.add((i,85+j))
    assert len(cross)==16
    assert adjacent(polys)==adjacent(fixed)|{(85+i,85+j) for i,j in adjacent(real)}|cross
    assert len(adjacent(polys))==235
    assert topology_signature(polys[85:])==topology_signature(real)
    assert report['sharedPairs']==pair_stats(polys,[r['name'] for r in d['regions']])
    expected_seams=unary_union([LineString(s['path']) for s in report['initialSeams']])
    actual_seams=unary_union([p.boundary for p in polys[85:]]).intersection(unary_union(fixed).boundary)
    assert actual_seams.equals(expected_seams)
    assert unary_union([LineString(s['path']) for s in report['seams']]).equals(actual_seams)
    possible={tuple(v['point']) for p in fixed for v in acute_vertices(p)}
    for p in polygon_parts(unary_union(fixed)):
        rr=list(orient(p,sign=1).exterior.coords)[:-1]
        for i,b in enumerate(rr):
            a=rr[i-1];c=rr[(i+1)%len(rr)];u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
            if 180-math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1]))>270.001:possible.add(tuple(b))
    for i,(r,p) in enumerate(zip(d['regions'],polys)):
        assert p.contains(Point(r['variants']['east']['label']))
        assert all(tuple(v['point']) in possible for v in acute_vertices(p)),r['name']
        for rr in rings(p):assert all(0<x+500<1660 and 140<y+690<1960 for x,y in rr)
        if i<85:
            assert r['variants']['east']['label']==old['regions'][i]['variants']['east']['label']
            for key in ['id','name','province','fullName','administrativeType']:assert r.get(key)==old['regions'][i].get(key)
        else:
            q=real[i-85]
            assert p.intersection(q).area/p.union(q).area>=.75
            assert abs(p.area-q.area)/q.area<=.15
            assert turn_count(p)==report['cities'][i-85]['turns']
            assert len(polygon_parts(p))==1
    assert len(refs)==98 and all(parse(r['path']).equals(q) for r,q in zip(refs[85:],raw))
    assert all(parse(r['path']).equals(parse(q['path'])) for r,q in zip(refs,oldrefs))
    assert all(parse(r['path']).contains(Point(r['label'])) for r in refs)
    assert report['preparation']['omittedParts']==2 and not report['islands']
    print(json.dumps({'cities':98,'frozenCities':85,'adjacencies':235,'crossProvincePairsAdded':16,'overlaps':0,'holes':0,'jiangsuTurns':[turn_count(p) for p in polys[85:]],'newFrozenSeamAcuteAngles':sum(len(acute_vertices(p)) for p in polys[85:])},ensure_ascii=False))
    if check_balance:validate_balance('jiangsu-data.js','jiangsu-balanced-data.js','jiangsu-balanced-report.json',canvas=(1660,500,690,140,1960))
if __name__=='__main__':validate()
