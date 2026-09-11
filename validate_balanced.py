"""Validate serialized comparison assets independently of the optimizer."""
import json,hashlib,math
import shapely
from shapely.geometry import Point
from shapely.ops import unary_union
from generate_map import ROOT,geometry_from_path,polygon_parts,topology_signature,rings
from soften_angles import acute_vertices

def load(name):return json.loads((ROOT/'dist'/name).read_text().split(' = ',1)[1].split(';\n')[0])
def turn_count(p):
    count=0
    for ring in rings(p):
        rr=ring[:-1]
        for i,b in enumerate(rr):
            a=rr[i-1];c=rr[(i+1)%len(rr)];u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1]);count+=abs(u[0]*v[1]-u[1]*v[0])/(math.hypot(*u)*math.hypot(*v))>1e-7
    return count

def validate():
    d=load('balanced-data.js');old=load('south-data.js');report=json.loads((ROOT/'dist/balanced-report.json').read_text())
    assert hashlib.sha256((ROOT/'dist/south-data.js').read_bytes()).hexdigest()==report['sourceSha256']
    assert len(d['regions'])==82 and [r['id'] for r in d['regions']]==[r['id'] for r in old['regions']]
    assert all(r['variants']['east']==o['variants']['east'] for r,o in zip(d['regions'],old['regions']))
    pp=[geometry_from_path(r['variants']['balanced']['path']) for r in d['regions']];qq=[geometry_from_path(r['variants']['east']['path']) for r in old['regions']]
    assert all(p.is_valid for p in pp) and shapely.coverage_is_valid(pp)
    assert topology_signature(pp)==topology_signature(qq)
    assert abs(sum(p.area for p in pp)-unary_union(pp).area)<1e-5
    assert not any(p.interiors for p in polygon_parts(unary_union(pp)))
    outline=geometry_from_path(d['variants']['balanced']['outline']);assert outline.symmetric_difference(unary_union(pp)).area<1e-5
    for i,(p,q,r,m) in enumerate(zip(pp,qq,d['regions'],report['cities'])):
        assert turn_count(p)==turn_count(q),(r['name'],turn_count(p),turn_count(q))
        assert len(acute_vertices(p))==len(acute_vertices(q))
        assert p.contains(Point(r['variants']['balanced']['label']))
        assert abs(p.area-m['afterArea'])<1e-5
        for rr in rings(p):
            for a,b in zip(rr,rr[1:]):
                dx=abs(b[0]-a[0]);dy=abs(b[1]-a[1]);assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
            assert all(0<x+500<1660 and 140<y+530<1800 for x,y in rr),(r['name'],'canvas')
        parts=polygon_parts(p)
        for part in sorted(parts,key=lambda g:-g.area)[1:]:
            other=unary_union([x if j!=i else x.difference(part) for j,x in enumerate(pp)])
            assert part.distance(other)>=2.5-1e-6
    assert abs(max(p.area for p in pp)/min(p.area for p in pp)-report['afterRatio'])<1e-7
    print(json.dumps({'cities':82,'topology':'identical','turnsBefore':sum(turn_count(p) for p in qq),'turnsAfter':sum(turn_count(p) for p in pp),'acuteAngles':sum(len(acute_vertices(p)) for p in pp),'beforeRatio':report['beforeRatio'],'afterRatio':report['afterRatio'],'minimumNormalizedShapeIou':min(m['normalizedShapeIou'] for m in report['cities'])},ensure_ascii=False))
if __name__=='__main__':validate()
