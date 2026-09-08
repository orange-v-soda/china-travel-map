"""Validate the actual SVG paths shipped to the browser. Requires Shapely."""
import json
from itertools import combinations
from pathlib import Path
import shapely
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from soften_angles import filter_parts, acute_vertices, score
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
        expected_polys=filter_parts(list(real.values()))[0] if mode in ('softened','compact') else list(real.values())
        assert topology_signature([polys[k] for k in real])==topology_signature(expected_polys)
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
        assert iou>(.90 if mode=='compact' else .92 if mode in ('shortcuts','softened') else .95)
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
    print('Historical iteration_9 geometry: an extra legacy pass produces identical geometry.')

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

    angle=data['angleReport']
    soft=[parse(r['variants']['softened']['path']) for r in data['regions']]
    base,removed=filter_parts(compact)
    assert angle['removedComponents']==removed
    baseline,source_removed=filter_parts(list(real.values()))
    assert angle['removedSourceComponents']==source_removed
    old=[LineString(c['original']) for c in angle['chains']]
    new=[LineString(c['simplified']) for c in angle['chains']]
    assert unary_union(old).equals(unary_union([p.boundary for p in base]))
    assert unary_union(new).equals(unary_union([p.boundary for p in soft]))
    assert rotations(old)==rotations(new)
    for a,b in zip(old,new):
        assert a.coords[0]==b.coords[0] and a.coords[-1]==b.coords[-1]
        assert a.buffer(8,quad_segs=16).covers(b) and b.buffer(8,quad_segs=16).covers(a)
    for i,j in combinations(range(len(old)),2):
        assert old[i].intersection(old[j]).equals(new[i].intersection(new[j]))
    assert list(score(soft))==angle['afterScore']
    assert angle['afterScore'][0]==0, 'Jiangxi delivery must have no acute interior angles'
    assert all(tuple(b)<tuple(a) for a,b in zip(angle['scoreTrace'],angle['scoreTrace'][1:]))
    for p,r in zip(soft,baseline):
        assert abs(p.area-r.area)/r.area<=.15
        assert p.intersection(r).area/p.union(r).area>=.75
    assert len(acute_vertices(Polygon([(0,0),(4,0),(0,4)])))==2
    assert len(acute_vertices(Polygon([(0,4),(4,0),(0,0)])))==2
    assert not acute_vertices(Polygon([(0,0),(4,0),(4,2),(2,2),(2,4),(0,4)]))
    assert json.loads((ROOT/'dist/angle-report.json').read_text())==angle
    print('Softened: component filtering, polygon interior angles, 45-degree edges, shared contacts/rotations, cumulative displacement, area/IoU budgets and decreasing objective verified:',angle['afterScore'])

    from compact_lobes import rotation_signature, short_edges
    report=data['compactReport']
    final=[parse(r['variants']['compact']['path']) for r in data['regions']]
    old=[LineString(c['original']) for c in report['chains']]
    new=[LineString(c['simplified']) for c in report['chains']]
    assert unary_union(old).equals(unary_union([p.boundary for p in soft]))
    assert unary_union(new).equals(unary_union([p.boundary for p in final]))
    assert rotation_signature(old)==rotation_signature(new)
    for a,b in zip(old,new):
        assert a.buffer(24,quad_segs=16).covers(b) and b.buffer(24,quad_segs=16).covers(a)
    for a,p,r in zip(soft,final,baseline):
        assert not acute_vertices(p)
        assert a.boundary.buffer(24,quad_segs=16).covers(p.boundary)
        assert p.boundary.buffer(24,quad_segs=16).covers(a.boundary)
        assert abs(p.area-r.area)/r.area<=.15
        assert p.intersection(r).area/p.union(r).area>=.75
    assert all(tuple(b)<tuple(a) for a,b in zip(report['objectiveTrace'],report['objectiveTrace'][1:]))
    target=[p for r,p in zip(data['regions'],final) if r['name'] in report['targetCities']]
    assert report['afterObjective']==[sum(short_edges(p) for p in target),sum(turns(p) for p in final)]
    assert json.loads((ROOT/'dist/compact-report.json').read_text())==report
    print('Compact: moved junction rotation, source chain identity, cumulative distance, zero acute angles, shape budgets and target short edges verified:',report['afterObjective'])
