"""Deterministic block shortcuts on a shared octilinear boundary network.

No per-city vertex quotas. Every accepted shortcut strictly removes bends.
Input is geography-first initial fit; fidelity is checked against frozen input.
"""
import json, math
from pathlib import Path
import shapely
from shapely.geometry import LineString, Polygon, Point
from shapely.strtree import STRtree
from shapely.ops import unary_union, linemerge, polygonize
from generate_map import (ROOT, geometry_from_path, read_reference, topology_signature,
                          validate_step, svg_path, label_for, stats, rings)

DIRECTIONS=((1,0),(0,1),(1,1),(1,-1))

def clean(points):
    out=[]
    for p in points:
        p=tuple(p)
        if out and p==out[-1]:continue
        while len(out)>1:
            a,b=out[-2:];u=(b[0]-a[0],b[1]-a[1]);v=(p[0]-b[0],p[1]-b[1])
            if abs(u[0]*v[1]-u[1]*v[0])>1e-8 or u[0]*v[0]+u[1]*v[1]<=0:break
            out.pop()
        out.append(p)
    return out

def alternatives(a,b):
    dx=b[0]-a[0];dy=b[1]-a[1]
    if min(abs(dx),abs(dy))<1e-8 or abs(abs(dx)-abs(dy))<1e-8:
        yield [a,b]
    seen=set()
    for u in DIRECTIONS:
        for v in DIRECTIONS:
            det=u[0]*v[1]-u[1]*v[0]
            if not det:continue
            t=(dx*v[1]-dy*v[0])/det
            c=(a[0]+t*u[0],a[1]+t*u[1])
            # Monotone two-leg alternatives; no overshoot beyond the endpoints.
            if not (min(a[0],b[0])-1e-8<=c[0]<=max(a[0],b[0])+1e-8 and min(a[1],b[1])-1e-8<=c[1]<=max(a[1],b[1])+1e-8):continue
            p=clean([a,c,b]);key=tuple(p)
            if len(p)==3 and key not in seen:seen.add(key);yield p

def turns(poly):
    count=0
    for rr in rings(poly):
        pp=rr[:-1]
        for i,b in enumerate(pp):
            a=pp[i-1];c=pp[(i+1)%len(pp)]
            if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>1e-7:count+=1
    return count

def rotations(chains):
    nodes={}
    for k,g in enumerate(chains):
        pp=list(g.coords)
        for end,a,b in [(0,pp[0],pp[1]),(1,pp[-1],pp[-2])]:
            nodes.setdefault(a,[]).append((math.atan2(b[1]-a[1],b[0]-a[0]),(k,end)))
    result={}
    for point,arms in nodes.items():
        if len(arms)<3:continue
        ids=[v for angle,v in sorted(arms)]
        start=ids.index(min(ids));result[point]=tuple(ids[start:]+ids[:start])
    return result

def rebuild(chains,owners):
    groups=[[] for _ in owners];index=STRtree(owners)
    for face in polygonize(unary_union(chains)):
        # Bounds pruning preserves maximum-overlap ownership and lowest-index ties.
        candidates=sorted(map(int,index.query(face)))
        overlap=[(face.intersection(owners[i]).area,-i) for i in candidates]
        area,negative_owner=max(overlap,default=(0,0))
        owner=-negative_owner if area>0 else 0
        groups[owner].append(face)
    return [unary_union(g) for g in groups]

def simplify(initial,real,tolerance=18.0,*,minimum_iou=.75):
    if not math.isfinite(tolerance) or tolerance<=0:raise ValueError('tolerance must be finite and positive')
    if not 0<minimum_iou<=1:raise ValueError('minimum_iou must be in (0, 1]')
    expected=topology_signature(real)
    network=linemerge(unary_union([p.boundary for p in initial]))
    chains=sorted([LineString(clean(g.coords)) for g in network.geoms],key=lambda g:tuple(g.coords))
    original=list(chains);expected_rotations=rotations(chains)
    corridors=[g.buffer(tolerance,quad_segs=16) for g in original]
    current=list(initial);accepted=0;rejections={};passes=0;trace=[sum(turns(p) for p in current)]
    source_limits=[p.boundary.hausdorff_distance(r.boundary)+tolerance for p,r in zip(initial,real)]
    source_corridors=[r.boundary.buffer(limit,quad_segs=16) for r,limit in zip(real,source_limits)]
    # Stable cyclic sweep: edits reduce the integer segment count, so termination
    # is guaranteed without an iteration cap. A full unchanged sweep ends it.
    while True:
        changed=False;passes+=1
        for k,line in enumerate(chains):
            pp=list(line.coords)
            if line.is_ring or len(pp)<4:continue # protect islands/closed rings
            others=unary_union([g for i,g in enumerate(chains) if i!=k])
            old_contacts=line.intersection(others)
            choices=[]
            for span in range(len(pp)-1,2,-1):
                for i in range(len(pp)-span):
                    j=i+span
                    for shortcut in alternatives(pp[i],pp[j]):
                        newpoints=clean(pp[:i]+shortcut+pp[j+1:])
                        gain=len(pp)-len(newpoints)
                        if gain<=0:continue
                        candidate=LineString(newpoints)
                        if not candidate.is_simple:continue
                        if not corridors[k].covers(candidate):continue
                        if not candidate.buffer(tolerance,quad_segs=16).covers(original[k]):continue
                        if not candidate.intersection(others).equals(old_contacts):continue
                        # Swept pockets may not swallow another boundary, island,
                        # or junction even when old/new intersections are equal.
                        swept=list(polygonize(unary_union([line,candidate])))
                        if any(p.buffer(-1e-6).intersects(others) for p in swept):continue
                        err=original[k].hausdorff_distance(candidate)
                        short=sum(math.dist(a,b)<6 for a,b in zip(newpoints,newpoints[1:]))
                        choices.append((-gain,short,err,tuple(newpoints),candidate))
            for _,_,_,_,candidate in sorted(choices,key=lambda c:c[:4]):
                proposed=list(chains);proposed[k]=candidate
                if rotations(proposed)!=expected_rotations:continue
                polys=rebuild(proposed,initial)
                error=validate_step(polys,expected)
                if error is None and sum(turns(p) for p in polys)>=sum(turns(p) for p in current):error='no_turn_reduction'
                if error is None and any(p.intersection(r).area/p.union(r).area < minimum_iou for p,r in zip(polys,real)):error='city_iou_budget'
                if error is None:
                    # Cumulative area error, measured against real source (not last pass).
                    if any(abs(p.area-r.area)/r.area>max(.15,abs(b.area-r.area)/r.area+1e-6) for p,b,r in zip(polys,initial,real)):error='area_budget'
                    elif any(not corridor.covers(p.boundary) or not p.boundary.buffer(limit,quad_segs=16).covers(r.boundary) for p,r,corridor,limit in zip(polys,real,source_corridors,source_limits)):error='source_distance_budget'
                if error:
                    rejections[error]=rejections.get(error,0)+1;continue
                chains=proposed;current=polys;accepted+=1;changed=True;trace.append(sum(turns(p) for p in current));break
        if not changed:break
        print('sweep',passes,'accepted',accepted,'turns',sum(turns(p) for p in current),flush=True)
    report={'algorithm':'shared-boundary-block-shortcuts','tolerance':tolerance,'areaErrorLimit':.15,'minimumCityIou':minimum_iou,'junctionRotationPreserved':rotations(chains)==expected_rotations,'acceptedShortcuts':accepted,'sweeps':passes,'stopReason':'no_feasible_reducing_shortcut','rejections':rejections,'beforeTurns':[turns(p) for p in initial],'afterTurns':[turns(p) for p in current],'chainMaxDeviation':max(a.hausdorff_distance(b) for a,b in zip(original,chains)),**stats(real,current)}
    report['turnTrace']=trace
    report['sourceBoundaryLimits']=source_limits
    report['chains']=[{'original':list(a.coords),'simplified':list(b.coords)} for a,b in zip(original,chains)]
    return current,report

def generate(tolerance=18.0):
    data=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))
    reference=read_reference();real=[geometry_from_path(r['path']) for r in reference['regions']]
    initial=[geometry_from_path(r['variants']['iteration_0']['path']) for r in data['regions']]
    polys,report=simplify(initial,real,tolerance)
    report['cities']=[{'name':r['name'],'previousTurns':turns(geometry_from_path(r['variants']['iteration_9']['path'])),'turns':turns(p),'areaError':round(abs(p.area-q.area)/q.area,4),'sourceBoundaryDeviation':round(p.boundary.hausdorff_distance(q.boundary),3)} for r,p,q in zip(data['regions'],polys,real)]
    mode='shortcuts'
    for r,p in zip(data['regions'],polys):r['variants'][mode]={'path':svg_path(p),'label':label_for(p,reference['regions'][data['regions'].index(r)]['label'])}
    data['variants'][mode]={'outline':svg_path(unary_union(polys)),**stats(real,polys)}
    data['defaultVariant']=mode;data['version']='0.5.0';data['basis']='shared-boundary-block-shortcuts';data['shortcutReport']=report
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'dist/shortcut-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('chains','turnTrace')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--tolerance',type=float,default=18)
    generate(parser.parse_args().tolerance)
