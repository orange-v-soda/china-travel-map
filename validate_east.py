"""Check delivered SVG paths independently of the generation pipeline."""
import json,hashlib
import shapely
from shapely.geometry import LineString,Point
from shapely.ops import unary_union
from generate_map import ROOT,rings,topology_signature,adjacent
from validate_geometry import parse
from build_east import source,bodies,freeze
from soften_angles import acute_vertices
from simplify_boundaries import turns
from simplify_shared import pair_stats

def validate():
    s=(ROOT/'dist/east-data.js').read_text();data=json.loads(s.split('const MAP_DATA = ',1)[1].split(';\nconst REFERENCE_MAP = ',1)[0]);ref=json.loads(s.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'));report=json.loads((ROOT/'dist/east-report.json').read_text())
    fixed=[parse(r['path']) for r in freeze()['regions']];polys=[parse(r['variants']['east']['path']) for r in data['regions']]
    assert len(polys)==22 and len(set(r['id'] for r in data['regions']))==22
    assert hashlib.sha256((ROOT/'dist/map-data.js').read_bytes()).hexdigest()==freeze()['sourceDataSha256']==report['frozenJiangxiSha256']
    assert all(a.equals(b) for a,b in zip(fixed,polys))
    assert all(p.is_valid and p.area>0 for p in polys) and shapely.coverage_is_valid(polys)
    assert abs(sum(p.area for p in polys)-unary_union(polys).area)<1e-6
    assert unary_union(polys).equals(parse(data['variants']['east']['outline']))
    _,raw,sha=source();filtered=bodies(raw);assert sha==report['zhejiangSourceSha256']
    assert topology_signature(polys[11:])==topology_signature(filtered)
    expected=adjacent(fixed)|{(a+11,b+11) for a,b in adjacent(filtered)}|{(10,18)}
    assert adjacent(polys)==expected
    assert polys[10].boundary.intersection(polys[18].boundary).equals(LineString(report['seam']))
    for i in range(11):
        for j in range(11,22):
            if (i,j)!=(10,18):assert polys[i].boundary.intersection(polys[j].boundary).is_empty
    for r,p in zip(data['regions'],polys):
        assert p.contains(Point(r['variants']['east']['label'])) and not acute_vertices(p)
        for rr in rings(p):
            for a,b in zip(rr,rr[1:]):
                dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1]);assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
            assert all(0<=x+40<=1160 and 140<=y+140<=950 for x,y in rr)
    for p,r in zip(polys[11:],filtered):
        assert p.intersection(r).area/p.union(r).area>=.75 and abs(p.area-r.area)/r.area<=.15
    assert report['sharedPairs']==pair_stats(polys,[r['name'] for r in data['regions']])
    assert [r['turns'] for r in report['cities']]==[turns(p) for p in polys[11:]]
    assert len(ref['regions'])==22
    for r in ref['regions']:assert parse(r['path']).contains(Point(r['label']))
    print(json.dumps({'cities':22,'adjacencies':len(expected),'frozenJiangxiUnchanged':True,'exactSeam':True,'overlaps':0,'acuteAngles':0,'zhejiangTurns':[turns(p) for p in polys[11:]]},ensure_ascii=False))
if __name__=='__main__':validate()
