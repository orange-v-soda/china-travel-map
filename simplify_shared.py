"""Inspect and simplify every inter-city shared boundary, without city quotas."""
import json,math
from shapely.ops import unary_union,linemerge
from generate_map import ROOT,read_reference,geometry_from_path,svg_path,label_for,stats
from simplify_boundaries import clean,turns,alternatives
from compact_lobes import optimize


def shared_lines(polys):
    for i,p in enumerate(polys):
        for j in range(i+1,len(polys)):
            g=p.boundary.intersection(polys[j].boundary)
            if g.length<1e-6:continue
            if g.geom_type=='MultiLineString':g=linemerge(g)
            parts=[g] if g.geom_type=='LineString' else [x for x in g.geoms if x.geom_type=='LineString']
            yield i,j,parts


def pair_stats(polys,names):
    rows=[]
    for i,j,parts in shared_lines(polys):
        lengths=[math.dist(a,b) for g in parts for pp in [clean(g.coords)] for a,b in zip(pp,pp[1:])]
        rows.append({'cities':[names[i],names[j]],'segments':len(lengths),'chains':len(parts),'shortSegments':sum(d<12-1e-7 for d in lengths),'length':round(sum(lengths),3)})
    return rows


def objective(polys):
    counts=pair_stats(polys,list(range(len(polys))))
    return (sum(r['shortSegments'] for r in counts),sum(r['segments'] for r in counts),sum(turns(p) for p in polys))


def boundary(polys):return unary_union([g for _,_,parts in shared_lines(polys) for g in parts])


def shared_routes(a,b):
    yield from alternatives(a,b)
    dx=b[0]-a[0];dy=b[1]-a[1]
    sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
    d=min(abs(dx),abs(dy))
    for t in [.25,.5,.75]:
        # Three-leg alternatives keep endpoint tangents compatible with their
        # neighbors when an otherwise shorter two-leg route creates an acute angle.
        x=a[0]+t*dx;y=a[1]+t*dy
        yield clean([a,(x,a[1]),(x,b[1]),b])
        yield clean([a,(a[0],y),(b[0],y),b])
        if abs(dx)>=abs(dy):
            p=(a[0]+sx*t*(abs(dx)-d),a[1])
        else:p=(a[0],a[1]+sy*t*(abs(dy)-d))
        q=(p[0]+sx*d,p[1]+sy*d)
        yield clean([a,p,q,b])


def generate():
    data=json.loads((ROOT/'dist/map-data.js').read_text().split(' = ',1)[1].rstrip(';\n'));reference=read_reference()
    real=[geometry_from_path(r['path']) for r in reference['regions']];initial=[geometry_from_path(r['variants']['compact']['path']) for r in data['regions']];names=[r['name'] for r in data['regions']]
    polys,report=optimize(initial,real,names,target_names=names,objective_fn=objective,boundary_fn=boundary,limit=24,chain_routes=shared_routes)
    report.update(algorithm='all-shared-boundary-simplification',beforePairs=pair_stats(initial,names),afterPairs=pair_stats(polys,names),objectiveOrder=['sharedShortSegments','sharedSegments','cityTurns'])
    for r,p,ref in zip(data['regions'],polys,reference['regions']):r['variants']['shared']={'path':svg_path(p),'label':label_for(p,ref['label'])}
    data['variants']['shared']={'outline':svg_path(unary_union(polys)),**stats(real,polys)}
    data.update(version='0.8.0',defaultVariant='shared',sharedReport=report)
    (ROOT/'dist/map-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'dist/shared-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('chains','beforePairs')},ensure_ascii=False,indent=2))
if __name__=='__main__':generate()
