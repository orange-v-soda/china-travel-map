"""Extend frozen Jiangxi using source topology and a single shared seam."""
import json,math,hashlib,argparse
import shapely
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union,substring
from generate_map import ROOT,read_reference,geometry_from_path,svg_path,label_for,polygon_parts,octilinear,topology_signature,validate_step,adjacent,route
from simplify_boundaries import simplify,rebuild,turns
from soften_angles import soften,acute_vertices

def save(name,data):
    (ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def load(name):return json.loads((ROOT/name).read_text())
def freeze():
    p=ROOT/'data/jiangxi-v08-frozen.json'
    if not p.exists():
        raw=(ROOT/'dist/map-data.js').read_bytes();d=json.loads(raw.decode().split(' = ',1)[1].rstrip(';\n'))
        save('data/jiangxi-v08-frozen.json',{'sourceDataSha256':hashlib.sha256(raw).hexdigest(),'regions':[{'id':r['id'],'name':r['name'],**r['variants']['shared']} for r in d['regions']]})
    return load('data/jiangxi-v08-frozen.json')
def source():
    raw=(ROOT/'data/zhejiang-source.geojson').read_bytes();d=json.loads(raw);c=load('data/jiangxi-projection.json')
    def xy(p):
        x=math.radians(p[0]);y=-math.log(math.tan(math.pi/4+math.radians(p[1])/2))
        return round(c['dx']+(x-c['left'])*c['scale'],2),round(c['dy']+(y-c['top'])*c['scale'],2)
    regions=[];polys=[]
    for f in d['features']:
        parts=f['geometry']['coordinates'] if f['geometry']['type']=='MultiPolygon' else [f['geometry']['coordinates']]
        g=unary_union([Polygon([xy(p) for p in pp[0]],[[xy(p) for p in rr] for rr in pp[1:]]) for pp in parts]);polys.append(g)
        props=f['properties'];regions.append({'id':str(props['adcode']),'name':props['name'].removesuffix('市'),'province':'浙江','path':svg_path(g),'label':label_for(g,xy(props.get('centroid',props['center'])))})
    return regions,polys,hashlib.sha256(raw).hexdigest()
def bodies(polys):return [max(polygon_parts(p),key=lambda q:q.area) for p in polys]
def base():
    regions,real,sha=source();filtered=bodies(real)
    initial=octilinear(shapely.coverage_simplify(filtered,6),grid=.5)
    pairs=adjacent(filtered)
    for i,p in enumerate(filtered):
        if any(i in pair for pair in pairs):continue
        for tol in [6,4,2,1,.5]:
            q=octilinear(shapely.coverage_simplify([p],tol),grid=.5)[0]
            if topology_signature([q])==topology_signature([p]) and q.intersection(p).area/q.union(p).area>=.8 and abs(q.area-p.area)/p.area<=.1:
                initial[i]=q;break
    assert validate_step(initial,topology_signature(filtered)) is None
    result,report=simplify(initial,filtered,18)
    save('data/zhejiang-base.json',{'regions':regions,'paths':[svg_path(p) for p in result],'report':report})
    print('Base turns',[turns(p) for p in result],flush=True)
def arcs(ring,a,b):
    line=LineString(ring);x=line.project(Point(a));y=line.project(Point(b))
    if x>y:
        return [list(reversed(v)) for v in arcs(ring,b,a)]
    direct=list(substring(line,x,y).coords)
    around=list(substring(line,0,x).coords)[::-1]+list(substring(line,y,line.length).coords)[::-1]
    # Around follows a backwards through ring origin, then from ring end to b.
    return [direct,around]
def anchor():
    fixed=[geometry_from_path(r['path']) for r in freeze()['regions']];ref=read_reference();jx=unary_union([geometry_from_path(r['path']) for r in ref['regions']]);union=unary_union(fixed)
    z=[geometry_from_path(p) for p in load('data/zhejiang-base.json')['paths']];_,raw,_=source();qindex=7
    rr=list(bodies(raw)[qindex].exterior.coords)[:-1];near=[jx.boundary.distance(Point(p))<=1 for p in rr];runs=[]
    for i in range(len(rr)):
        if near[i] and not near[i-1]:
            run=[];k=i
            while near[k%len(rr)] and len(run)<len(rr):run.append(rr[k%len(rr)]);k+=1
            runs.append(run)
    old=max(runs,key=len);ends=[old[0],old[-1]]
    line=LineString(union.exterior.coords);cuts=[]
    for p in ends:
        pt=line.interpolate(line.project(Point(p)));cuts.append(tuple(round(v*2)/2 for v in pt.coords[0]))
    seam=min(arcs(union.exterior.coords,*cuts),key=lambda pp:LineString(pp).length);seam=[tuple(round(v,8) for v in p) for p in seam];seamline=LineString(seam)
    poly=z[qindex];pp=list(poly.exterior.coords);a,b=[min(pp,key=lambda q:math.dist(q,p)) for p in ends]
    options=arcs(pp,a,b);western=min(options,key=lambda v:LineString(v).hausdorff_distance(LineString(old)));other=options[1-options.index(western)]
    # Keep the opposite arc backwards, replacing only the western arc with the frozen seam.
    path=route(a,cuts[0],.5)+seam[1:]+route(cuts[1],b,.5)[1:]+list(reversed(other))[1:]
    proposed=Polygon(path).difference(union)
    assert proposed.is_valid and proposed.boundary.intersection(union.boundary).equals(seamline)
    z[qindex]=proposed;combined=rebuild([p.boundary for p in fixed+z],fixed+z)
    assert all(p.equals(q) for p,q in zip(fixed,combined))
    expected=adjacent(fixed)|{(a+11,b+11) for a,b in adjacent(bodies(raw))}|{(10,18)}
    assert adjacent(combined)==expected and shapely.coverage_is_valid(combined)
    save('data/zhejiang-anchored.json',{'paths':[svg_path(p) for p in combined],'seam':seam})
    print('Seam',seam,'angles',sum(len(acute_vertices(p)) for p in combined),flush=True)
def finish():
    a=load('data/zhejiang-anchored.json');initial=[geometry_from_path(p) for p in a['paths']];fixed=[geometry_from_path(r['path']) for r in freeze()['regions']];_,raw,_=source()
    result,report=soften(initial,fixed+bodies(raw),locked_count=11,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True)
    if any(acute_vertices(p) for p in result):
        result,fine=soften(result,fixed+bodies(raw),locked_count=11,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True,detail_steps=(.5,1,2,4,6,8));report['fine']=fine
    assert not any(acute_vertices(p) for p in result)
    save('data/zhejiang-finished.json',{'paths':[svg_path(p) for p in result],'report':report,'seam':a['seam']})
def compact():
    from compact_lobes import optimize
    from simplify_shared import objective,boundary,shared_routes
    a=load('data/zhejiang-finished.json');initial=[geometry_from_path(p) for p in a['paths']];f=freeze();fixed=[geometry_from_path(r['path']) for r in f['regions']];regions,raw,_=source();names=[r['name'] for r in f['regions']+regions]
    result,report=optimize(initial,fixed+bodies(raw),names,target_names=names[11:],objective_fn=objective,boundary_fn=boundary,limit=18,chain_routes=shared_routes,locked_count=11,expected_topology=topology_signature(initial))
    save('data/zhejiang-final.json',{'paths':[svg_path(p) for p in result],'report':report,'seam':a['seam']})
def emit():
    from simplify_shared import pair_stats
    a=load('data/zhejiang-final.json');polys=[geometry_from_path(p) for p in a['paths']];zr,raw,sha=source();refs=[{**r,'province':'江西'} for r in read_reference()['regions']]+zr;filtered=bodies(raw)
    from island_groups import fit_groups
    island_index=next(i for i,r in enumerate(refs) if r['name']=='舟山')
    polys[island_index],island_report=fit_groups(raw[island_index-11],unary_union([p for i,p in enumerate(polys) if i!=island_index]))
    regions=[{'id':r['id'],'name':r['name'],'province':r['province'],'variants':{'east':{'path':svg_path(p),'label':label_for(p,r['label'])}}} for r,p in zip(refs,polys)]
    for r in refs:r['label']=label_for(geometry_from_path(r['path']),r['label'])
    metrics=[{'name':r['name'],'turns':turns(p),'acuteAngles':len(acute_vertices(p)),'parts':len(polygon_parts(p)),'bodyIou':p.intersection(b).area/p.union(b).area,'fullSourceIou':p.intersection(o).area/p.union(o).area,'areaError':abs(p.area-b.area)/b.area} for r,p,b,o in zip(zr,polys[11:],filtered,raw)]
    metrics[island_index-11]['shapeBudget']='Schematic enlargement: exempt from body IoU and 15% area constraint'
    report={'version':'0.10.0','seam':a['seam'],'frozenJiangxiSha256':freeze()['sourceDataSha256'],'zhejiangSourceSha256':sha,'zhejiangRetrieved':'2026-09-08','islandPolicy':'Zhoushan uses three enlarged island groups; other Zhejiang cities retain their main body','islandGroups':island_report,'mainlandOmittedDetachedParts':sum(len(polygon_parts(p))-1 for i,p in enumerate(raw) if i!=island_index-11),'cities':metrics,'sharedPairs':pair_stats(polys,[r['name'] for r in refs]),'preIslandGroupingOptimization':a['report']}
    data={'version':'0.10.0','defaultVariant':'east','regions':regions,'variants':{'east':{'outline':svg_path(unary_union(polys))}}}
    (ROOT/'dist/east-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False)+';\nconst REFERENCE_MAP = '+json.dumps({'regions':refs},ensure_ascii=False)+';\n')
    save('dist/east-report.json',report)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1160 1020"><title>江西与浙江真实区划参考</title><rect width="1160" height="1020" fill="white"/><g transform="translate(40 140)">']
    for r in refs:svg.append('<path fill="#f5f7fa" stroke="#26364b" stroke-width="1.4" d="'+r['path']+'"/>')
    for r in refs:svg.append(f'<text x="{r["label"][0]}" y="{r["label"][1]}" text-anchor="middle" font-size="20">{r["name"]}</text>')
    svg.append('</g></svg>');(ROOT/'dist/east-reference.svg').write_text(''.join(svg));print('Final',metrics,flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['base','anchor','finish','compact','emit','all'],default='all');args=ap.parse_args();freeze()
    for name,fn in [('base',base),('anchor',anchor),('finish',finish),('compact',compact),('emit',emit)]:
        if args.stage in ('all',name):fn()
