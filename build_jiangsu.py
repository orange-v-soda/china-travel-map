"""Extend the accepted eastern map with Jiangsu on the same shared network."""
import json,hashlib,math,argparse
import shapely
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union,linemerge
from generate_map import ROOT,geometry_from_path,svg_path,polygon_parts,octilinear,topology_signature,validate_step,adjacent,route,label_for
from build_east import source,bodies as largest_bodies,arcs,save,load
from build_special import svg_path
from simplify_boundaries import simplify,rebuild,turns,clean,rotations
from soften_angles import soften,acute_vertices

def filled_holes(polys):
    main=largest_bodies(polys)
    omitted=unary_union([p.difference(q) for p,q in zip(polys,main)])
    return [[h for h in p.interiors if (Polygon(h).area<20 and Polygon(h).area/p.area<.001) or Polygon(h).intersection(omitted).area/Polygon(h).area>.999] for p in main]

def bodies(polys):
    holes=filled_holes(polys)
    return [Polygon(p.exterior,[h for h in p.interiors if not any(Polygon(h).equals(Polygon(q)) for q in removed)]) for p,removed in zip(largest_bodies(polys),holes)]

def inputs():
    raw=(ROOT/'dist/special-data.js').read_bytes();s=raw.decode();data=json.loads(s.split(' = ',1)[1].split(';\n')[0]);refs=json.loads(s.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions']
    fixed=[geometry_from_path(r['variants']['east']['path']) for r in data['regions']]
    return data,refs,fixed,hashlib.sha256(raw).hexdigest()
def retained_old_sources(refs,fixed):
    result=[]
    for r,f in zip(refs,fixed):
        parts=sorted(polygon_parts(geometry_from_path(r['path'])),key=lambda p:-p.area)
        result.append(unary_union(parts[:1]+[p for p in parts[1:] if p.intersection(f).area/p.area>.5]))
    return result
def js_source():
    regions,raw,sha=source('jiangsu-source.geojson','江苏')
    return regions,raw,sha
def base():
    regions,raw,_=js_source();real=bodies(raw)
    print('Source',[(r['name'],len(polygon_parts(p)),[round(q.area,1) for q in sorted(polygon_parts(p),key=lambda g:-g.area)[:4]]) for r,p in zip(regions,raw)],flush=True)
    for tolerance in (6,4,2,1,.5):
        initial=octilinear(shapely.coverage_simplify(real,tolerance),grid=.5)
        if validate_step(initial,topology_signature(real)) is None and all(p.intersection(q).area/p.union(q).area>=.82 for p,q in zip(initial,real)):break
    else:raise ValueError('No initial fit meets topology and reserved shape budget')
    print('Initial coverage tolerance',tolerance,flush=True)
    result,report=simplify(initial,real,18,minimum_iou=.82,first_improvement=True,checkpoint_path=ROOT/"data/jiangsu-base-checkpoint.json")
    report['initialCoverageTolerance']=tolerance
    save('data/jiangsu-base.json',{'paths':[svg_path(p) for p in result],'report':report})
    print('Base',[(r['name'],turns(p)) for r,p in zip(regions,result)],flush=True)
def anchor_geometry(current,real,fixed,fixed_union,old_boundary,regions):
    current=list(current)
    # Shared junctions are preserved by the first shortening stage.
    network=linemerge(unary_union([p.boundary for p in current]));nodes={}
    for g in network.geoms:
        for p in [g.coords[0],g.coords[-1]]:nodes[p]=nodes.get(p,0)+1
    gd_outline=unary_union(current).boundary
    junctions=[p for p,n in nodes.items() if n>=3 and gd_outline.distance(Point(p))<1e-6]
    interfaces=[];mapping={}
    for frozen_part,source_boundary in old_boundary:
      for i,p in enumerate(real):
        pp=list(p.exterior.coords)[:-1];near=[source_boundary.distance(Point(v))<=1 for v in pp];runs=[]
        # Bridge only tiny source discrepancies inside an otherwise shared arc.
        for start in range(len(pp)):
            if near[start] or not near[start-1]:continue
            gap=[];k=start
            while not near[k%len(pp)] and len(gap)<len(pp):gap.append(k%len(pp));k+=1
            path=[pp[start-1]]+[pp[j] for j in gap]+[pp[k%len(pp)]]
            if LineString(path).length<=6 and all(source_boundary.distance(Point(pp[j]))<=2 for j in gap):
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
            else:
                rr=list(current[i].exterior.coords);edge=min(range(len(rr)-1),key=lambda k:LineString(rr[k:k+2]).distance(Point(pt)));a,b=rr[edge:edge+2];q=LineString([a,b]).interpolate(LineString([a,b]).project(Point(pt)))
                if abs(a[0]-b[0])<1e-7:node=(a[0],max(min(a[1],b[1]),min(max(a[1],b[1]),round(q.y*2)/2)))
                else:
                    x=max(min(a[0],b[0]),min(max(a[0],b[0]),round(q.x*2)/2));node=(x,a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
                if node not in rr:rr.insert(edge+1,node);current[i]=Polygon(rr)
            cut=frozen_part.boundary.interpolate(frozen_part.boundary.project(Point(pt)))
            cut=tuple(cut.coords[0]);rr=list(frozen_part.exterior.coords);a,b=min(zip(rr,rr[1:]),key=lambda ab:LineString(ab).distance(Point(cut)))
            if abs(a[0]-b[0])<1e-7:cut=(a[0],max(min(a[1],b[1]),min(max(a[1],b[1]),round(cut[1]*2)/2)))
            else:
                x=max(min(a[0],b[0]),min(max(a[0],b[0]),round(cut[0]*2)/2));cut=(x,a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
            if node in mapping:assert math.dist(mapping[node],cut)<1e-6,('endpoint collision',regions[i]['name'])
            mapping[node]=cut;ends.append(node)
        interfaces.append((i,original,ends,frozen_part))
    moved=[]
    for p in current:
        pp=list(p.exterior.coords);out=[]
        for a,b in zip(pp,pp[1:]):out.extend(route(mapping.get(a,a),mapping.get(b,b),.125)[:-1])
        moved.append(Polygon(out))
    seams=[]
    for i,original,ends,frozen_part in interfaces:
        cuts=[mapping[e] for e in ends]
        choices=arcs(frozen_part.exterior.coords,*cuts);seam=min(choices,key=lambda v:LineString(v).hausdorff_distance(LineString(original)));seam=[tuple(round(x,8) for x in p) for p in seam]
        choices=arcs(moved[i].exterior.coords,*cuts);other=max(choices,key=lambda v:LineString(v).hausdorff_distance(LineString(original)))
        g=Polygon(seam+list(reversed(other))[1:]).difference(unary_union(fixed));assert g.is_valid
        moved[i]=g;seams.append({'city':regions[i]['name'],'path':seam})
    combined=rebuild([p.boundary for p in fixed+moved],fixed+moved)
    assert all(p.equals(q) for p,q in zip(fixed,combined))
    assert shapely.coverage_is_valid(combined)
    assert topology_signature(combined[len(fixed):])==topology_signature(real)
    return combined,seams

def anchor(base_path="data/jiangsu-base.json",output_path="data/jiangsu-anchored.json"):
    from itertools import combinations
    data,refs,fixed,_=inputs();regions,raw,_=js_source();real=bodies(raw)
    fixed_union=max(polygon_parts(unary_union(fixed)),key=lambda p:p.area)
    retained=retained_old_sources(refs,fixed)
    source_parts=polygon_parts(unary_union([geometry_from_path(r['path']) for r in refs]))
    frozen_parts=polygon_parts(unary_union(fixed))
    old_boundary=[(max(frozen_parts,key=lambda q:p.intersection(q).area),p.boundary) for p in source_parts if p.area>100]
    base_data=load(base_path);current=[geometry_from_path(p) for p in base_data['paths']]
    def fit(p,q):return (p.intersection(q).area/p.union(q).area,abs(p.area-q.area)/q.area)
    def bad(polys):return [i for i,(p,q) in enumerate(zip(polys[len(fixed):],real)) if fit(p,q)[0]<.75 or fit(p,q)[1]>.15]
    expected_adj=adjacent(fixed)|{(i+len(fixed),j+len(fixed)) for i,j in adjacent(real)}
    for i,r in enumerate(refs):
        boundary=retained[i].boundary.buffer(.05)
        for j,p in enumerate(real):
            if p.boundary.intersection(boundary).length>3:expected_adj.add((i,len(fixed)+j))
    combined,seams=anchor_geometry(current,real,fixed,fixed_union,old_boundary,regions);repairs=[]
    assert adjacent(combined)==expected_adj
    if bad(combined):
        initial=octilinear(shapely.coverage_simplify(real,base_data.get('report',{}).get('initialCoverageTolerance',4)),grid=.5)
        def network(polys):return sorted([LineString(clean(g.coords)) for g in linemerge(unary_union([p.boundary for p in polys])).geoms],key=lambda g:tuple(g.coords))
        def endpoints(g):return tuple(sorted((tuple(g.coords[0]),tuple(g.coords[-1]))))
        original=network(initial);chains=network(current)
        references=[min((g for g in original if endpoints(g)==endpoints(c)),key=lambda g:c.hausdorff_distance(g)) for c in chains]
        assert len({g.wkb_hex for g in references})==len(chains)
        references=[g if g.coords[0]==c.coords[0] else LineString(list(g.coords)[::-1]) for g,c in zip(references,chains)]
        expected_rotation=rotations(chains)
        assert rotations(references)==expected_rotation
        targets=bad(combined);eligible=[k for k,g in enumerate(chains) if any(g.intersection(current[i].boundary).length>1e-7 for i in targets) and not g.equals(references[k])]
        before=[{'city':regions[i]['name'],'iou':fit(combined[len(fixed)+i],real[i])[0],'areaError':fit(combined[len(fixed)+i],real[i])[1]} for i in targets]
        print('Restoring source detail for',before,'candidate chains',len(eligible),flush=True)
        found=False
        for count in range(1,len(eligible)+1):
            for subset in combinations(eligible,count):
                proposed=[references[k] if k in subset else g for k,g in enumerate(chains)]
                if rotations(proposed)!=expected_rotation:continue
                try:
                    restored=rebuild(proposed,initial)
                    if validate_step(restored,topology_signature(real)):continue
                    candidate,candidate_seams=anchor_geometry(restored,real,fixed,fixed_union,old_boundary,regions)
                    if bad(candidate) or adjacent(candidate)!=expected_adj:continue
                except (AssertionError,shapely.errors.GEOSException,ValueError):continue
                combined,seams=candidate,candidate_seams;repairs=[{'before':before,'restoredChains':[{'endpoints':endpoints(chains[k]),'original':list(references[k].coords)} for k in subset]}];found=True;break
            if found:break
        assert found,'Source-detail restoration could not meet anchored shape budget'
    assert not bad(combined)
    save(output_path,{'paths':[svg_path(p) for p in combined],'seams':seams,'sourceDetailRestoration':repairs})
    print('Anchored',[(r['name'],round(fit(p,q)[0],3),turns(p)) for r,p,q in zip(regions,combined[len(fixed):],real)],flush=True)
    print('Cross pairs',[(data['regions'][a]['name'],regions[b-len(fixed)]['name']) for a,b in sorted(adjacent(combined)) if a<len(fixed)<=b],flush=True)
def finish():
    d,refs,fixed,_=inputs();r,raw,_=js_source();a=load('data/jiangsu-anchored.json');initial=[geometry_from_path(p) for p in a['paths']]
    result,report=soften(initial,fixed+bodies(raw),locked_count=85,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True,checkpoint_path=ROOT/"data/jiangsu-priority-angle-checkpoint.json",acute_first=True)
    if any(acute_vertices(p) for p in result[85:]):
        result,fine=soften(result,fixed+bodies(raw),locked_count=85,expected_topology=topology_signature(initial),split_rings=True,first_improvement=True,detail_steps=(.5,1,2,4,6,8),checkpoint_path=ROOT/"data/jiangsu-priority-fine-checkpoint.json",acute_first=True);report['fine']=fine
    save('data/jiangsu-finished.json',{'paths':[svg_path(p) for p in result],'report':report,'seams':a['seams']})
    print('Finished',[(rr['name'],turns(p),len(acute_vertices(p))) for rr,p in zip(r,result[85:])],flush=True)
def compact():
    from compact_lobes import optimize
    from simplify_shared import objective,boundary,shared_routes
    d,refs,fixed,_=inputs();r,raw,_=js_source();a=load('data/jiangsu-finished.json');initial=[geometry_from_path(p) for p in a['paths']]
    allowed=[v["point"] for p in initial for v in acute_vertices(p)]
    names=[rr['name'] for rr in refs+r]
    def angle_objective(polys):return (sum(len(acute_vertices(p)) for p in polys),*objective(polys))
    result,report=optimize(initial,fixed+bodies(raw),names,target_names=names[85:],objective_fn=angle_objective,boundary_fn=boundary,limit=18,chain_routes=shared_routes,locked_count=85,expected_topology=topology_signature(initial),allowed_acute_points=allowed,checkpoint_path=ROOT/"data/jiangsu-priority-compact-checkpoint.json",first_improvement=True)
    assert all(unary_union(fixed).boundary.distance(Point(v["point"]))<1e-7 for p in result[85:] for v in acute_vertices(p)),"Unresolved movable acute angle"
    report["inheritedAcutePoints"]=[v["point"] for p in result for v in acute_vertices(p)]
    save('data/jiangsu-final.json',{'paths':[svg_path(p) for p in result],'report':report,'seams':a['seams']})
def emit():
    from island_groups import fit_detached_island
    from simplify_shared import pair_stats
    from xml.sax.saxutils import escape
    data,old_refs,fixed,fixed_sha=inputs();regions,raw,source_sha=js_source();refs=old_refs+regions
    a=load('data/jiangsu-final.json');polys=[geometry_from_path(p) for p in a['paths']];mainland=list(polys[85:]);islands=[]
    for i,p in enumerate(raw):
        parts=sorted(polygon_parts(p),key=lambda g:-g.area)
        for part in parts[1:2]:
            if part.area<100:continue
            island,meta=fit_detached_island(part,unary_union(polys));polys[85+i]=unary_union([polys[85+i],island]);islands.append({'city':regions[i]['name'],**meta,'path':svg_path(island)})
    out=[]
    for i,(r,p) in enumerate(zip(refs,polys)):out.append({'id':r['id'],'name':r['name'],'province':r['province'],**({'fullName':r['fullName'],'administrativeType':r['administrativeType']} if 'fullName' in r else {}),'variants':{'east':{'path':svg_path(p),'label':label_for(max(polygon_parts(p),key=lambda g:g.area),data['regions'][i]['variants']['east']['label'] if i<85 else r['label'])}}})
    for r in refs:r['label']=label_for(geometry_from_path(r['path']),r['label'])
    metrics=[{'name':r['name'],'turns':turns(p),'mainlandTurns':turns(q),'parts':len(polygon_parts(p)),'acuteAngles':acute_vertices(p),'mainlandIou':q.intersection(real).area/q.union(real).area,'mainlandAreaError':abs(q.area-real.area)/real.area,'fullSourceIou':p.intersection(original).area/p.union(original).area} for r,p,q,real,original in zip(regions,polys[85:],mainland,bodies(raw),raw)]
    final_seams=[]
    for name in dict.fromkeys(item['city'] for item in a['seams']):
        i=next(i for i,r in enumerate(refs) if r['name']==name)
        shared=polys[i].boundary.intersection(unary_union(fixed).boundary)
        shared=linemerge(shared) if shared.geom_type=='MultiLineString' else shared
        for line in ([shared] if shared.geom_type=='LineString' else shared.geoms):
            if line.geom_type=='LineString':final_seams.append({'city':name,'path':list(line.coords)})
    assert unary_union([LineString(x['path']) for x in final_seams]).equals(unary_union([LineString(x['path']) for x in a['seams']]))
    preparation={'sourceMinorParts':sum(len(polygon_parts(p))-1 for p in raw),'omittedParts':sum(len(polygon_parts(p))-1 for p in raw)-len(islands),'retainedIslandRule':{'maximumPerCity':1,'minimumArea':100},'filledHoles':[{'name':r['name'],'area':Polygon(h).area} for r,holes in zip(regions,filled_holes(raw)) for h in holes],'omittedEnclaveHoleCoverage':.999,'initialCoverageTolerance':load('data/jiangsu-base.json')['report']['initialCoverageTolerance'],'sourceDetailRestoration':load('data/jiangsu-anchored.json')['sourceDetailRestoration'],'preAnchorMinimumIou':.82,'sourceArcGapBridge':{'maximumLength':6,'maximumDistance':2}}
    report={'version':'0.17.0','frozenEastSha256':fixed_sha,'jiangsuSourceSha256':source_sha,'retrieved':'2026-09-11','preparation':preparation,'cities':metrics,'seams':final_seams,'initialSeams':a['seams'],'islands':islands,'sharedPairs':pair_stats(polys,[r['name'] for r in refs]),'optimization':a['report'],'inheritedAcutePoints':a['report']['inheritedAcutePoints']}
    result={'version':'0.17.0','defaultVariant':'east','regions':out,'variants':{'east':{'outline':svg_path(unary_union(polys))}}}
    (ROOT/'dist/jiangsu-data.js').write_text('const MAP_DATA = '+json.dumps(result,ensure_ascii=False)+';\nconst REFERENCE_MAP = '+json.dumps({'regions':refs},ensure_ascii=False)+';\n')
    save('dist/jiangsu-report.json',report)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1660 2040"><title>七省与香港、澳门、上海真实区划参考</title><rect width="1660" height="2040" fill="white"/><g transform="translate(500 690)">']
    for r in refs:svg.append('<path fill-rule="evenodd" fill="#f5f7fa" stroke="#26364b" stroke-width="1.4" d="'+r['path']+'"/>')
    for r in refs:svg.append(f'<text x="{r["label"][0]}" y="{r["label"][1]}" text-anchor="middle" font-size="20">{escape(r["name"])}</text>')
    svg.append('</g></svg>');(ROOT/'dist/jiangsu-reference.svg').write_text(''.join(svg))
    print('Delivery',metrics,'islands',islands,flush=True)
def balance():
    from build_balanced import run
    run('dist/jiangsu-data.js','jiangsu-balanced',minimum_median_fraction=.25,alphas=[.75],max_iterations=800,version='0.17.0')

if __name__=='__main__':
    import fcntl,os
    generation_lock=(ROOT/'data/jiangsu-generation.lock').open('a+')
    try:fcntl.flock(generation_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Jiangsu generation is already running; wait for its saved stage output')
    generation_lock.seek(0);generation_lock.truncate();generation_lock.write(str(os.getpid()));generation_lock.flush()
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['base','anchor','finish','compact','emit','balance','all'],default='all');args=ap.parse_args()
    for name in ['base','anchor','finish','compact','emit','balance']:
        if args.stage in (name,'all'):globals()[name]()
