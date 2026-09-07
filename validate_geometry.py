"""Independent geometry checks for both abstract map variants (no dependencies)."""
import json
import math
from pathlib import Path
from itertools import combinations
from generate_map import polygon_area
ROOT=Path(__file__).parent
D=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))
def edges(p):return list(zip(p,p[1:]+p[:1]))
def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def proper_intersect(a,b,c,d):return cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0
def inside(p,poly):
    x,y=p;result=False
    for a,b in edges(poly):
        if cross(a,b,p)==0 and min(a[0],b[0])<=x<=max(a[0],b[0]) and min(a[1],b[1])<=y<=max(a[1],b[1]):return False
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:result=not result
    return result

def shared(a,b,c,d):
    if cross(a,b,c)!=0 or cross(a,b,d)!=0:return 0
    axis=0 if a[0]!=b[0] else 1
    return max(0,min(max(a[axis],b[axis]),max(c[axis],d[axis]))-max(min(a[axis],b[axis]),min(c[axis],d[axis])))

for mode,outline in [('points','outline'),('diagonal','diagonalOutline')]:
    observed=set();diagonal_segments=0
    for r in D['regions']:
        p=r[mode];es=edges(p)
        assert polygon_area(p)>0
        assert inside(r['label'],p),('label',r['name'])
        for a,b in es:
            dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1]);assert dx+dy>0
            assert dx==0 or dy==0 or dx==dy,('non octilinear',a,b)
            diagonal_segments+=int(dx==dy and dx>0)
        for (a,b),(c,d) in combinations(es,2):assert not proper_intersect(a,b,c,d),('self intersection',r['name'])
    for a,b in combinations(D['regions'],2):
        shared_length=0
        for x,y in edges(a[mode]):
            for z,w in edges(b[mode]):
                assert not proper_intersect(x,y,z,w),('crossing',a['name'],b['name'])
                shared_length+=shared(x,y,z,w)
        assert not any(inside(p,b[mode]) for p in a[mode]),('overlap',a['name'],b['name'])
        assert not any(inside(p,a[mode]) for p in b[mode]),('overlap',a['name'],b['name'])
        if shared_length:observed.add(tuple(sorted([a['id'],b['id']])))
    expected={tuple(sorted([r['id'],n])) for r in D['regions'] for n in r['neighbors']}
    assert expected==observed,('adjacency changed',expected-observed,observed-expected)
    assert abs(sum(polygon_area(r[mode]) for r in D['regions'])-polygon_area(D[outline]))<1e-8,'coverage'
    areas=[polygon_area(r[mode]) for r in D['regions']]
    print(mode,': 11 valid regions; 19 adjacencies; no overlap or coverage gaps; labels inside; ratio',round(max(areas)/min(areas),3),'diagonal segments',diagonal_segments)
