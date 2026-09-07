"""Validate the actual SVG paths shipped to the browser. Requires Shapely."""
import json
from itertools import combinations
from pathlib import Path
import shapely
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
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
    for mode in ['simplified','diagonal']:
        polys={r['id']:parse(r['variants'][mode]['path']) for r in data['regions']}
        assert len(polys)==11 and set(polys)==set(real)
        assert all(p.is_valid and p.area>0 for p in polys.values())
        assert shapely.coverage_is_valid(list(polys.values()))
        actual={(a,b) for a,b in combinations(sorted(polys),2) if polys[a].boundary.intersection(polys[b].boundary).length>1e-6}
        assert actual==expected
        merged=unary_union(list(polys.values()))
        assert abs(sum(p.area for p in polys.values())-merged.area)<1e-6
        assert merged.symmetric_difference(parse(data['variants'][mode]['outline'])).area<1e-5
        for r in data['regions']:
            assert polys[r['id']].contains(Point(r['variants'][mode]['label']))
            if mode=='diagonal':
                for a,b in edges(r['variants'][mode]['path']):
                    dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1]);assert min(dx,dy)<1e-6 or abs(dx-dy)<1e-6
        base=unary_union(list(real.values()));iou=base.intersection(merged).area/base.union(merged).area
        assert iou>.97
        print(mode,': 11 regions, 19 adjacencies, no overlaps, outline matches coverage, labels inside; province IoU',round(iou,4))
