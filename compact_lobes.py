"""Remove small attached hooks by shared-chain shortcuts and junction relocation."""
import json,math,itertools
from shapely.geometry import LineString, Point
from shapely.ops import unary_union,linemerge
from generate_map import ROOT,read_reference,geometry_from_path,validate_step,topology_signature,svg_path,label_for,stats,rings
from simplify_boundaries import clean,alternatives,rotations,rebuild,turns
from soften_angles import filter_parts,acute_vertices
TARGETS={'赣州','吉安','上饶'}
LIMIT=24


def corners(poly):
    for rr in rings(poly):
        pp=rr[:-1];out=[]
        for i,b in enumerate(pp):
            a=pp[i-1];c=pp[(i+1)%len(pp)]
            if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))>1e-7:out.append(b)
        yield out


def short_edges(poly):
    return sum(math.dist(a,b)<12-1e-7 for pp in corners(poly) for a,b in zip(pp,pp[1:]+pp[:1]))


def rotation_signature(chains):return sorted(rotations(chains).values())


def optimize(initial,real,names):
    real,_=filter_parts(real);expected=topology_signature(real)
    network=linemerge(unary_union([p.boundary for p in initial]))
    chains=sorted([LineString(clean(g.coords)) for g in network.geoms],key=lambda g:tuple(g.coords))
    original=list(chains);rotation=rotation_signature(chains);current=initial
    targets=[i for i,n in enumerate(names) if n in TARGETS]
    def objective(polys):return (sum(short_edges(polys[i]) for i in targets),sum(turns(p) for p in polys))
    trace=[objective(current)];edits=[]
    def check(proposal):
        if rotation_signature(proposal)!=rotation:return None
        if any(not g.is_simple or not a.buffer(LIMIT,quad_segs=16).covers(g) or not g.buffer(LIMIT,quad_segs=16).covers(a) for a,g in zip(original,proposal)):return None
        polys=rebuild(proposal,initial)
        score=objective(polys)
        if score>=trace[-1] or any(acute_vertices(p) for p in polys):return None
        if validate_step(polys,expected):return None
        if any(p.intersection(r).area/p.union(r).area<.75 or abs(p.area-r.area)/r.area>.15 for p,r in zip(polys,real)):return None
        # Keep each city's change bounded against the frozen v0.6 geometry.
        if any(not a.boundary.buffer(LIMIT,quad_segs=16).covers(p.boundary) or not p.boundary.buffer(LIMIT,quad_segs=16).covers(a.boundary) for a,p in zip(initial,polys)):return None
        delta=sum(a.symmetric_difference(p).area for a,p in zip(initial,polys))
        return score,delta,polys
    while True:
        best=None
        def consider(proposal,kind):
            nonlocal best
            result=check(proposal)
            if result is None:return
            score,delta,polys=result;rank=(score,delta,tuple(tuple(g.coords) for g in proposal))
            if best is None or rank<best[0]:best=(rank,proposal,polys,kind)
        # Straighten entire groups of edges; a wider frozen corridor permits
        # removing long narrow tips that the 8-unit angle pass had to preserve.
        target_boundary=unary_union([current[i].boundary for i in targets])
        for k,line in enumerate(chains):
            if line.is_ring or line.intersection(target_boundary).length<1e-6:continue
            pp=list(line.coords)
            for i in range(len(pp)-2):
                for j in range(i+2,len(pp)):
                    for route in alternatives(pp[i],pp[j]):
                        out=clean(pp[:i]+route+pp[j+1:])
                        if len(out)>=len(pp):continue
                        proposal=list(chains);proposal[k]=LineString(out);consider(proposal,{'type':'chain','chain':k})
        # Move a shared junction and re-route all its incident chains together.
        nodes={}
        for k,line in enumerate(chains):
            pp=list(line.coords)
            for reverse,a in [(False,pp[0]),(True,pp[-1])]:nodes.setdefault(a,[]).append((k,reverse))
        for node,arms in sorted(nodes.items()):
            if len(arms)!=3 or target_boundary.distance(Point(node))>1e-6:continue
            local=[]
            for k,rev in arms:
                pp=list(chains[k].coords);pp=pp[::-1] if rev else pp
                local.extend(p for p in pp[1:4] if math.dist(node,p)<=LIMIT)
            # Corners plus intersections of nearby horizontal/vertical supports.
            xs={p[0] for p in local}|{node[0]};ys={p[1] for p in local}|{node[1]}
            positions=sorted(set(local)|{(x,y) for x in xs for y in ys})
            for position in positions:
                if position==node or math.dist(position,node)>LIMIT:continue
                options=[]
                for k,rev in arms:
                    pp=list(chains[k].coords);pp=pp[::-1] if rev else pp;routes={}
                    for cut in range(1,min(4,len(pp))):
                        if cut>1 and any(math.dist(node,p)>LIMIT for p in pp[1:cut]):continue
                        for route in alternatives(position,pp[cut]):
                            out=clean(route+pp[cut+1:]);out=out[::-1] if rev else out
                            if len(out)<2:continue
                            g=LineString(out)
                            if g.is_simple and original[k].buffer(LIMIT,quad_segs=16).covers(g) and g.buffer(LIMIT,quad_segs=16).covers(original[k]):routes[tuple(out)]=g
                    if not routes:break
                    options.append(list(routes.values()))
                if len(options)!=3:continue
                for combination in itertools.product(*options):
                    proposal=list(chains)
                    for (k,_),g in zip(arms,combination):proposal[k]=g
                    consider(proposal,{'type':'junction','from':node,'to':position})
        if best is None:break
        _,chains,current,kind=best;trace.append(objective(current));edits.append(kind)
        print('compact',len(edits),trace[-1],kind,flush=True)
    report={'algorithm':'shared-junction-lobe-removal','targetCities':sorted(TARGETS),'shortEdgeThreshold':12,'deviationLimit':LIMIT,'beforeObjective':trace[0],'afterObjective':trace[-1],'objectiveTrace':trace,'edits':edits,'stopReason':'no_feasible_improving_candidate','chains':[{'original':list(a.coords),'simplified':list(b.coords)} for a,b in zip(original,chains)],'cities':[{'name':name,'beforeShortEdges':short_edges(a),'shortEdges':short_edges(p),'beforeTurns':turns(a),'turns':turns(p),'acuteAngles':len(acute_vertices(p))} for name,a,p in zip(names,initial,current)],**stats(real,current)}
    return current,report


def generate():
    data=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'));reference=read_reference()
    real=[geometry_from_path(r['path']) for r in reference['regions']];initial=[geometry_from_path(r['variants']['softened']['path']) for r in data['regions']]
    polys,report=optimize(initial,real,[r['name'] for r in data['regions']])
    for r,p,ref in zip(data['regions'],polys,reference['regions']):r['variants']['compact']={'path':svg_path(p),'label':label_for(p,ref['label'])}
    data['variants']['compact']={'outline':svg_path(unary_union(polys)),**stats(real,polys)}
    data.update(version='0.7.0',defaultVariant='compact',compactReport=report)
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'dist/compact-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='chains'},ensure_ascii=False,indent=2))
if __name__=='__main__':generate()
