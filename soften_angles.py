"""Remove negligible detached components and optimize acute polygon angles."""
import json,math
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union,linemerge,polygonize
from generate_map import ROOT,read_reference,geometry_from_path,polygon_parts,validate_step,topology_signature,svg_path,label_for,stats
from simplify_boundaries import clean,alternatives,rotations,rebuild,turns


def filter_parts(polys):
    total=sum(p.area for p in polys);out=[];removed=[]
    for i,p in enumerate(polys):
        parts=sorted(polygon_parts(p),key=lambda p:-p.area)
        keep=[parts[0]]
        for part in parts[1:]:
            if part.area/p.area<.005 and part.area/total<.0001:
                removed.append({'cityIndex':i,'area':part.area})
            else:keep.append(part)
        out.append(unary_union(keep))
    return out,removed


def acute_vertices(poly):
    result=[]
    for part in polygon_parts(poly):
        part=orient(part,sign=1)
        for ring in [part.exterior,*part.interiors]:
            pts=list(ring.coords)[:-1]
            for i,b in enumerate(pts):
                a=pts[i-1];c=pts[(i+1)%len(pts)]
                u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
                angle=180-math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1]))
                if angle<90-1e-6:result.append({'point':b,'angle':round(angle,5)})
    return result


def score(polys):return (sum(len(acute_vertices(p)) for p in polys),sum(turns(p) for p in polys))


def candidates(points,sharp,steps=(2,4,6,8)):
    # Junctions need a short initial leg in a new direction. A monotone
    # endpoint-to-endpoint route cannot repair every acute meeting angle.
    for reverse in [False,True]:
        pp=points[::-1] if reverse else points
        if pp[0] not in sharp:continue
        a,b=pp[:2]
        for size in steps:
            for dx,dy in [(1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)]:
                c=(a[0]+size*dx,a[1]+size*dy)
                for route in alternatives(c,b):
                    out=clean([a]+route+pp[2:])
                    yield out[::-1] if reverse else out
    # Re-route whole windows, including junction-adjacent legs. Allow extra
    # corners when they remove an acute angle; never optimize a polygon alone.
    for i in range(len(points)-2):
        for j in range(i+2,len(points)):
            for route in alternatives(points[i],points[j]):
                yield clean(points[:i]+route+points[j+1:])
    # Cut back a sharp bend. Relative L-infinity lengths keep integer/half-grid
    # 45-degree routes, with 1:1 / 1:2 ratios covering octilinear bevels.
    for i in range(1,len(points)-1):
        a,b,c=points[i-1:i+2]
        la=max(abs(a[0]-b[0]),abs(a[1]-b[1]));lc=max(abs(c[0]-b[0]),abs(c[1]-b[1]))
        if min(la,lc)==0:continue
        for size in steps:
            for ratio in [.5,1,2]:
                x=size;y=size*ratio
                if x>=la*.8 or y>=lc*.8:continue
                p=(b[0]+(a[0]-b[0])*x/la,b[1]+(a[1]-b[1])*x/la)
                q=(b[0]+(c[0]-b[0])*y/lc,b[1]+(c[1]-b[1])*y/lc)
                dx=abs(q[0]-p[0]);dy=abs(q[1]-p[1])
                if min(dx,dy)>1e-8 and abs(dx-dy)>1e-8:continue
                yield clean(points[:i]+[p,q]+points[i+1:])


def soften(initial,real,*,locked_count=0,expected_topology=None,split_rings=False,first_improvement=False,detail_steps=(2,4,6,8)):
    initial,removed=filter_parts(initial);real,source_removed=filter_parts(real)
    expected=topology_signature(real) if expected_topology is None else expected_topology
    assert validate_step(initial,expected) is None
    network=linemerge(unary_union([p.boundary for p in initial]))
    chains=sorted([LineString(clean(g.coords)) for g in network.geoms],key=lambda g:tuple(g.coords))
    if split_rings:
        expanded=[]
        for g in chains:
            if not g.is_ring:expanded.append(g);continue
            pp=list(g.coords)[:-1];k=min(range(len(pp)),key=lambda i:pp[i]);pp=pp[k:]+pp[:k];j=max(range(1,len(pp)),key=lambda i:(pp[i][0]-pp[0][0])**2+(pp[i][1]-pp[0][1])**2)
            expanded.extend([LineString(pp[:j+1]),LineString(pp[j:]+pp[:1])])
        chains=expanded
    frozen=unary_union(initial[:locked_count]) if locked_count else None
    original=list(chains);rotation=rotations(chains);current=initial
    trace=[score(current)];accepted=0
    while True:
        best=None;sharp={tuple(v["point"]) for p in current for v in acute_vertices(p)}
        for k,line in enumerate(chains):
            if line.is_ring:continue
            if frozen is not None and line.intersection(frozen.boundary).length>1e-7:continue
            others=unary_union([g for i,g in enumerate(chains) if i!=k]);contacts=line.intersection(others)
            seen=set()
            for pp in candidates(list(line.coords),sharp,detail_steps):
                key=tuple(pp)
                if key in seen:continue
                seen.add(key);candidate=LineString(pp)
                if candidate.equals(line) or not candidate.is_simple:continue
                if not original[k].buffer(8,quad_segs=16).covers(candidate) or not candidate.buffer(8,quad_segs=16).covers(original[k]):continue
                if not candidate.intersection(others).equals(contacts):continue
                pockets=list(polygonize(unary_union([line,candidate])))
                if any(p.buffer(-1e-6).intersects(others) for p in pockets):continue
                proposal=list(chains);proposal[k]=candidate
                if rotations(proposal)!=rotation:continue
                polys=rebuild(proposal,initial);s=score(polys)
                if s>=trace[-1]:continue
                if any(not a.equals(b) for a,b in zip(initial[:locked_count],polys[:locked_count])):continue
                if validate_step(polys,expected):continue
                if any(p.intersection(r).area/p.union(r).area<.75 or abs(p.area-r.area)/r.area>.15 for p,r in zip(polys,real)):continue
                rank=(s,original[k].hausdorff_distance(candidate),k,key)
                if best is None or rank<best[0]:best=(rank,proposal,polys)
                if first_improvement:break
            if best is not None and first_improvement:break
        if best is None:break
        _,chains,current=best;trace.append(score(current));accepted+=1
        print('angle improvement',accepted,trace[-1],flush=True)
    report={'algorithm':'acute-angle-priority','minimumPreferredAngle':90,'localDeviationLimit':8,'removedComponents':removed,'removedSourceComponents':source_removed,'beforeScore':trace[0],'afterScore':trace[-1],'scoreTrace':trace,'stopReason':'no_feasible_improving_candidate','junctionRotationPreserved':rotations(chains)==rotation,'chains':[{'original':list(a.coords),'simplified':list(b.coords)} for a,b in zip(original,chains)],**stats(real,current)}
    return current,report


def generate():
    data=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'))
    reference=read_reference();real=[geometry_from_path(r['path']) for r in reference['regions']]
    initial=[geometry_from_path(r['variants']['shortcuts']['path']) for r in data['regions']]
    polys,report=soften(initial,real)
    report['cities']=[{'name':r['name'],'turns':turns(p),'acuteAngles':acute_vertices(p)} for r,p in zip(reference['regions'],polys)]
    for r,p,ref in zip(data['regions'],polys,reference['regions']):r['variants']['softened']={'path':svg_path(p),'label':label_for(p,ref['label'])}
    data['variants']['softened']={'outline':svg_path(unary_union(polys)),**stats(real,polys)}
    data.update(version='0.6.0',defaultVariant='softened',angleReport=report)
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'dist/angle-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='chains'},ensure_ascii=False,indent=2))

if __name__=='__main__':generate()
