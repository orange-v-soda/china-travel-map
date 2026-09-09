"""Extend the accepted eastern map with Hunan on the same shared network."""
import json,hashlib,math,argparse
import shapely
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union,linemerge
from generate_map import ROOT,geometry_from_path,svg_path,polygon_parts,octilinear,topology_signature,validate_step,adjacent,route,label_for
from build_east import source,bodies as largest_bodies,arcs,save,load
from simplify_boundaries import simplify,rebuild,turns,clean
from soften_angles import soften,acute_vertices

def bodies(polys):
    result=[]
    for p in largest_bodies(polys):
        holes=[r for r in p.interiors if not (Polygon(r).area<20 and Polygon(r).area/p.area<.001)]
        result.append(Polygon(p.exterior,holes))
    return result

def inputs():
    raw=(ROOT/'dist/southeast-data.js').read_bytes();s=raw.decode();data=json.loads(s.split(' = ',1)[1].split(';\n')[0]);refs=json.loads(s.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions']
    fixed=[geometry_from_path(r['variants']['east']['path']) for r in data['regions']]
    return data,refs,fixed,hashlib.sha256(raw).hexdigest()
def hn_source():
    regions,raw,sha=source('hunan-source.geojson','湖南')
    for r in regions:
        if r['id']=='433100':r.update(name='湘西',fullName='湘西土家族苗族自治州',administrativeType='自治州')
    return regions,raw,sha
def base():
    regions,raw,_=hn_source();real=bodies(raw)
    print('Source',[(r['name'],len(polygon_parts(p)),[round(q.area,1) for q in sorted(polygon_parts(p),key=lambda g:-g.area)[:4]]) for r,p in zip(regions,raw)],flush=True)
    initial=octilinear(shapely.coverage_simplify(real,6),grid=.5)
    assert validate_step(initial,topology_signature(real)) is None
    result,report=simplify(initial,real,18)
    save('data/hunan-base.json',{'paths':[svg_path(p) for p in result],'report':report})
    print('Base',[(r['name'],turns(p)) for r,p in zip(regions,result)],flush=True)
def anchor():
    data,refs,fixed,_=inputs();fixed_union=max(polygon_parts(unary_union(fixed)),key=lambda p:p.area)
    old_union=unary_union(bodies([geometry_from_path(r['path']) for r in refs]));old_boundary=old_union.boundary
    regions,raw,_=hn_source();real=bodies(raw);current=[geometry_from_path(p) for p in load('data/hunan-base.json')['paths']]
    # Shared junctions are preserved by the first shortening stage.
    network=linemerge(unary_union([p.boundary for p in current]));nodes={}
    for g in network.geoms:
        for p in [g.coords[0],g.coords[-1]]:nodes[p]=nodes.get(p,0)+1
    hn_outline=unary_union(current).boundary
    junctions=[p for p,n in nodes.items() if n>=3 and hn_outline.distance(Point(p))<1e-6]
    interfaces=[];mapping={}
    for i,p in enumerate(real):
        pp=list(p.exterior.coords)[:-1];near=[old_boundary.distance(Point(v))<=1 for v in pp];runs=[]
        # Bridge only tiny source discrepancies inside an otherwise shared arc.
        for start in range(len(pp)):
            if near[start] or not near[start-1]:continue
            gap=[];k=start
            while not near[k%len(pp)] and len(gap)<len(pp):gap.append(k%len(pp));k+=1
            path=[pp[start-1]]+[pp[j] for j in gap]+[pp[k%len(pp)]]
            if LineString(path).length<=6 and all(old_boundary.distance(Point(pp[j]))<=2 for j in gap):
                for j in gap:near[j]=True
        for j in range(len(pp)):
            if near[j] and not near[j-1]:
                run=[];k=j
                while near[k%len(pp)] and len(run)<len(pp):run.append(pp[k%len(pp)]);k+=1
                if len(run)>4:runs.append(run)
        if not runs:continue
        original=max(runs,key=lambda run:LineString(run).length)
        ends=[]
        for pt in [original[0],original[-1]]:
            j=min(junctions,key=lambda q:math.dist(q,pt))
            if math.dist(j,pt)<20:node=j
            else:node=min(list(current[i].exterior.coords),key=lambda q:math.dist(q,pt))
            cut=fixed_union.boundary.interpolate(fixed_union.boundary.project(Point(pt)))
            cut=tuple(round(v*2)/2 for v in cut.coords[0]);mapping[node]=cut;ends.append(node)
        interfaces.append((i,original,ends))
    print('Interface nodes',mapping,flush=True)
    moved=[]
    for p in current:
        pp=list(p.exterior.coords);out=[]
        for a,b in zip(pp,pp[1:]):out.extend(route(mapping.get(a,a),mapping.get(b,b),.5)[:-1])
        moved.append(Polygon(out))
    seams=[]
    for i,original,ends in interfaces:
        cuts=[mapping[e] for e in ends]
        choices=arcs(fixed_union.exterior.coords,*cuts);seam=min(choices,key=lambda v:LineString(v).hausdorff_distance(LineString(original)));seam=[tuple(round(x,8) for x in p) for p in seam]
        choices=arcs(moved[i].exterior.coords,*cuts);other=max(choices,key=lambda v:LineString(v).hausdorff_distance(LineString(original)))
        g=Polygon(seam+list(reversed(other))[1:]).difference(unary_union(fixed));assert g.is_valid
        moved[i]=g;seams.append({'city':regions[i]['name'],'path':seam})
    combined=rebuild([p.boundary for p in fixed+moved],fixed+moved)
    print('Anchored',[(r['name'],round(p.area),round(p.intersection(q).area/p.union(q).area,3),turns(p)) for r,p,q in zip(regions,combined[31:],real)],flush=True)
    assert all(p.equals(q) for p,q in zip(fixed,combined))
    assert shapely.coverage_is_valid(combined)
    assert topology_signature(combined[31:])==topology_signature(real)
    save('data/hunan-anchored.json',{'paths':[svg_path(p) for p in combined],'seams':seams})
    print('Cross pairs',[(data['regions'][a]['name'],regions[b-31]['name']) for a,b in sorted(adjacent(combined)) if a<31<=b],flush=True)
def finish():
    d,refs,fixed,_=inputs();r,raw,_=hn_source();a=load('data/hunan-anchored.json');initial=[geometry_from_path(p) for p in a['paths']]
    result,report=soften(initial,fixed+bodies(raw),locked_count=31,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True)
    if any(acute_vertices(p) for p in result[31:]):
        result,fine=soften(result,fixed+bodies(raw),locked_count=31,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True,detail_steps=(.5,1,2,4,6,8));report['fine']=fine
    save('data/hunan-finished.json',{'paths':[svg_path(p) for p in result],'report':report,'seams':a['seams']})
    print('Finished',[(rr['name'],turns(p),len(acute_vertices(p))) for rr,p in zip(r,result[31:])],flush=True)
def compact():
    from compact_lobes import optimize
    from simplify_shared import objective,boundary,shared_routes
    d,refs,fixed,_=inputs();r,raw,_=hn_source();a=load('data/hunan-finished.json');initial=[geometry_from_path(p) for p in a['paths']]
    allowed=[v["point"] for p in initial for v in acute_vertices(p)]
    assert all(unary_union(fixed).boundary.distance(Point(v))<1e-7 for p in initial[31:] for v in [x["point"] for x in acute_vertices(p)])
    names=[rr['name'] for rr in refs+r]
    result,report=optimize(initial,fixed+bodies(raw),names,target_names=names[31:],objective_fn=objective,boundary_fn=boundary,limit=18,chain_routes=shared_routes,locked_count=31,expected_topology=topology_signature(initial),allowed_acute_points=allowed,checkpoint_path=ROOT/"data/hunan-compact-checkpoint.json",first_improvement=True)
    report["inheritedAcutePoints"]=allowed
    save('data/hunan-final.json',{'paths':[svg_path(p) for p in result],'report':report,'seams':a['seams']})
def emit():
    from island_groups import fit_detached_island
    from simplify_shared import pair_stats
    from xml.sax.saxutils import escape
    data,old_refs,fixed,fixed_sha=inputs();regions,raw,source_sha=hn_source();refs=old_refs+regions
    a=load('data/hunan-final.json');polys=[geometry_from_path(p) for p in a['paths']];mainland=list(polys[31:]);islands=[]
    for i,p in enumerate(raw):
        parts=sorted(polygon_parts(p),key=lambda g:-g.area)
        for part in parts[1:]:
            if part.area<100 or part.area/p.area<.05:continue
            island,meta=fit_detached_island(part,unary_union(polys));polys[31+i]=unary_union([polys[31+i],island]);islands.append({'city':regions[i]['name'],**meta,'path':svg_path(island)})
    out=[]
    for i,(r,p) in enumerate(zip(refs,polys)):out.append({'id':r['id'],'name':r['name'],'province':r['province'],**({'fullName':r['fullName'],'administrativeType':r['administrativeType']} if 'fullName' in r else {}),'variants':{'east':{'path':svg_path(p),'label':label_for(max(polygon_parts(p),key=lambda g:g.area),data['regions'][i]['variants']['east']['label'] if i<31 else r['label'])}}})
    for r in refs:r['label']=label_for(geometry_from_path(r['path']),r['label'])
    metrics=[{'name':r['name'],'turns':turns(p),'parts':len(polygon_parts(p)),'acuteAngles':acute_vertices(p),'mainlandIou':q.intersection(real).area/q.union(real).area,'mainlandAreaError':abs(q.area-real.area)/real.area,'fullSourceIou':p.intersection(original).area/p.union(original).area} for r,p,q,real,original in zip(regions,polys[31:],mainland,bodies(raw),raw)]
    final_seams=[]
    for item in a['seams']:
        i=next(i for i,r in enumerate(refs) if r['name']==item['city'])
        shared=polys[i].boundary.intersection(unary_union(fixed).boundary)
        shared=linemerge(shared) if shared.geom_type=='MultiLineString' else shared
        assert shared.geom_type=='LineString'
        final_seams.append({'city':item['city'],'path':list(shared.coords)})
    assert unary_union([LineString(x['path']) for x in final_seams]).equals(unary_union([LineString(x['path']) for x in a['seams']]))
    preparation={'omittedParts' :sum(len(polygon_parts(p))-1 for p in raw),'filledHoles':[{'name':r['name'],'area':Polygon(h).area} for r,p in zip(regions,largest_bodies(raw)) for h in p.interiors if Polygon(h).area<20 and Polygon(h).area/p.area<.001],'sourceArcGapBridge':{'maximumLength':6,'maximumDistance':2}}
    report={'version':'0.12.0','frozenEastSha256':fixed_sha,'hunanSourceSha256':source_sha,'retrieved':'2026-09-09','preparation':preparation,'cities':metrics,'seams':final_seams,'initialSeams':a['seams'],'islands':islands,'sharedPairs':pair_stats(polys,[r['name'] for r in refs]),'optimization':a['report'],'inheritedAcutePoints':a['report']['inheritedAcutePoints']}
    result={'version':'0.12.0','defaultVariant':'east','regions':out,'variants':{'east':{'outline':svg_path(unary_union(polys))}}}
    (ROOT/'dist/atlas-data.js').write_text('const MAP_DATA = '+json.dumps(result,ensure_ascii=False)+';\nconst REFERENCE_MAP = '+json.dumps({'regions':refs},ensure_ascii=False)+';\n')
    save('dist/hunan-report.json',report)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1660 1160"><title>江西、浙江、福建与湖南真实区划参考</title><rect width="1660" height="1160" fill="white"/><g transform="translate(500 140)">']
    for r in refs:svg.append('<path fill-rule="evenodd" fill="#f5f7fa" stroke="#26364b" stroke-width="1.4" d="'+r['path']+'"/>')
    for r in refs:svg.append(f'<text x="{r["label"][0]}" y="{r["label"][1]}" text-anchor="middle" font-size="20">{escape(r["name"])}</text>')
    svg.append('</g></svg>');(ROOT/'dist/atlas-reference.svg').write_text(''.join(svg))
    print('Delivery',metrics,'islands',islands,flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['base','anchor','finish','compact','emit','all'],default='all');args=ap.parse_args()
    for name in ['base','anchor','finish','compact','emit']:
        if args.stage in (name,'all'):globals()[name]()
