"""Validate the actual SVG paths shipped to the browser. Requires Shapely."""
import json
from itertools import combinations
from pathlib import Path
import shapely
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from generate_map import topology_signature, octilinear, ITERATION_TOLERANCE, TINY_AREA
ROOT=Path(__file__).parent

def parse(path):
    rings=[]
    for part in path.split('M')[1:]:
        points=[tuple(map(float,p.split(','))) for p in part.split('Z')[0].strip().replace('L','').split()]
        rings.append(Polygon(points))
    out=rings[0]
    for ring in rings[1:]:out=out.symmetric_difference(ring)
    return out

def edges(path):
    for part in path.split('M')[1:]:
        pp=[tuple(map(float,p.split(','))) for p in part.split('Z')[0].strip().replace('L','').split()]
        yield from zip(pp,pp[1:])

if __name__=='__main__':
    data=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))
    reference=json.loads((ROOT/'dist/reference-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))
    assert data['sourceSha256']==reference['sha256']
    real={r['id']:parse(r['path']) for r in reference['regions']}
    expected={(a,b) for a,b in combinations(sorted(real),2) if real[a].boundary.intersection(real[b].boundary).length>1e-6}
    assert len(expected)==19
    for mode in data['variants']:
        polys={r['id']:parse(r['variants'][mode]['path']) for r in data['regions']}
        assert len(polys)==11 and set(polys)==set(real)
        assert all(p.is_valid and p.area>0 for p in polys.values())
        assert shapely.coverage_is_valid(list(polys.values()))
        assert topology_signature([polys[k] for k in real])==topology_signature(list(real.values()))
        actual={(a,b) for a,b in combinations(sorted(polys),2) if polys[a].boundary.intersection(polys[b].boundary).length>1e-6}
        assert actual==expected
        merged=unary_union(list(polys.values()))
        assert abs(sum(p.area for p in polys.values())-merged.area)<1e-6
        assert merged.symmetric_difference(parse(data['variants'][mode]['outline'])).area<1e-5
        for r in data['regions']:
            assert polys[r['id']].contains(Point(r['variants'][mode]['label']))
            for a,b in edges(r['variants'][mode]['path']):
                dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1]);assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
        base=unary_union(list(real.values()));iou=base.intersection(merged).area/base.union(merged).area
        assert iou>(.92 if mode=='shortcuts' else .95)
        print(mode,': 11 regions, 19 adjacencies, no overlaps, outline matches coverage, labels inside; province IoU',round(iou,4))

    # Replay one more simplify/refit pass on the serialized final geometry.
    final={r['id']:parse(r['variants']['iteration_9']['path']) for r in data['regions']}
    active=[];locked=[]
    for p in final.values():
        parts=list(p.geoms) if p.geom_type=='MultiPolygon' else [p]
        active.append(unary_union([g for g in parts if g.area>=TINY_AREA]))
        locked.append([g for g in parts if g.area<TINY_AREA])
    candidate=octilinear(shapely.coverage_simplify(active,ITERATION_TOLERANCE))
    assert all(a.equals(b) for a,b in zip(active,candidate)), 'Final serialized shape is not a fixed point'
    assert data['convergence']['status']=='fixed_point' and data['convergence']['verifiedExtraPass']
    assert data['iterations'][-1]['areaChange']==0
    print('Serialized final geometry: an extra pass produces identical geometry; component/hole/contact signatures match source in every stage.')

    from simplify_boundaries import rotations, turns
    from shapely.geometry import LineString
    report=data['shortcutReport']
    old=[LineString(c['original']) for c in report['chains']]
    new=[LineString(c['simplified']) for c in report['chains']]
    initial=[parse(r['variants']['iteration_0']['path']) for r in data['regions']]
    compact=[parse(r['variants']['shortcuts']['path']) for r in data['regions']]
    assert unary_union(old).equals(unary_union([p.boundary for p in initial]))
    assert unary_union(new).equals(unary_union([p.boundary for p in compact]))
    assert rotations(old)==rotations(new)
    for a,b in zip(old,new):
        assert a.coords[0]==b.coords[0] and a.coords[-1]==b.coords[-1]
        assert a.buffer(report['tolerance'],quad_segs=16).covers(b)
        assert b.buffer(report['tolerance'],quad_segs=16).covers(a)
    for i,j in combinations(range(len(old)),2):
        assert old[i].intersection(old[j]).equals(new[i].intersection(new[j]))
    for p,r,limit in zip(compact,real.values(),report['sourceBoundaryLimits']):
        assert abs(p.area-r.area)/r.area <= report['areaErrorLimit']+1e-8
        assert p.intersection(r).area/p.union(r).area >= report['minimumCityIou']-1e-8
        assert r.boundary.buffer(limit,quad_segs=16).covers(p.boundary)
        assert p.boundary.buffer(limit,quad_segs=16).covers(r.boundary)
    assert report['afterTurns']==[turns(p) for p in compact]
    assert all(b<a for a,b in zip(report['turnTrace'],report['turnTrace'][1:]))
    assert json.loads((ROOT/'dist/shortcut-report.json').read_text())==report
    print('Shortcuts: serialized shared-chain provenance, junction rotations, contacts, cumulative distance/area/IoU budgets and strict turn reduction verified.')
