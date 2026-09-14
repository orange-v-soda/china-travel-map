"""Add Hong Kong, Macao and Shanghai to the unbalanced geographic baseline."""
import json,hashlib,math
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union, nearest_points
from generate_map import ROOT,geometry_from_path,polygon_parts,octilinear,svg_path,label_for,adjacent
from build_east import source,save
from simplify_boundaries import clean,alternatives,turns
from soften_angles import acute_vertices

def svg_path(p):
    return ' '.join('M'+' L'.join(f'{float(x)!r},{float(y)!r}' for x,y in ring.coords)+' Z' for part in polygon_parts(p) for ring in [part.exterior,*part.interiors])

def score(p):return len(acute_vertices(p)),turns(p)
def fit(raw):
    real=Polygon(max(polygon_parts(raw),key=lambda g:g.area).exterior)
    def okay(p):return p.is_valid and p.area>0 and p.intersection(real).area/p.union(real).area>=.75 and abs(p.area-real.area)/real.area<=.15
    for tolerance in [6,4,2,1,.5,.25,.1]:
        initial=octilinear([real.simplify(tolerance,preserve_topology=True)],grid=.125)[0]
        if okay(initial):break
    else:raise ValueError('No initial shape fit')
    p=initial;accepted=0
    while True:
        rr=clean(list(p.exterior.coords))[:-1];best=None;current=score(p)
        def candidates():
            for i in range(len(rr)):
                q=rr[i:]+rr[:i]
                for span in range(len(q)-2,1,-1):
                    for route in alternatives(q[0],q[span]):
                        out=clean(route+q[span+1:]+[q[0]])
                        if len(out)>=4:yield Polygon(out)
        for candidate in candidates():
            if not okay(candidate):continue
            ss=score(candidate)
            if ss<current:
                best=(ss,candidate);break
        if best is None:break
        p=best[1];accepted+=1
    print('Fit',real.area,score(initial),'->',score(p),'steps',accepted,flush=True)
    return p,{'tolerance':tolerance,'accepted':accepted,'initialTurns':turns(initial),'turns':turns(p),'iou':p.intersection(real).area/p.union(real).area,'areaError':abs(p.area-real.area)/real.area}

def attach(p,donor,real,minimum_iou=.75,minimum_contact=3):
    from shapely.affinity import translate
    # The smallest rigid displacement aligning parallel supports creates a shared
    # seam without adding a neck or extra corners.
    choices=[]
    for a,b in zip(p.exterior.coords,list(p.exterior.coords)[1:]):
        dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy);nx=-dy/length;ny=dx/length
        for part in polygon_parts(donor):
            for c,d in zip(part.exterior.coords,list(part.exterior.coords)[1:]):
                if abs(dx*(d[1]-c[1])-dy*(d[0]-c[0]))>1e-7:continue
                shift=(c[0]-a[0])*nx+(c[1]-a[1])*ny
                if abs(shift)>20:continue
                xx=round(shift*nx,8);yy=round(shift*ny,8);q=translate(p,xoff=xx,yoff=yy)
                if q.intersection(donor).area>1e-6 or q.boundary.intersection(donor.boundary).length<minimum_contact:continue
                iou=q.intersection(real).area/q.union(real).area
                if iou>=minimum_iou:choices.append((xx*xx+yy*yy,-iou,xx,yy,q))
    assert choices,'No shape-preserving contact found'
    chosen=min(choices,key=lambda x:x[:4]);return chosen[-1],[chosen[2],chosen[3]]

def run():
    text=(ROOT/'dist/south-data.js').read_text();data=json.loads(text.split(' = ',1)[1].split(';\n')[0]);refs=json.loads(text.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions'];old=[geometry_from_path(r['variants']['east']['path']) for r in data['regions']]
    regs=[];new=[];full=[];reports=[]
    for name,province,kind,donor in [('hongkong','香港','特别行政区','深圳'),('macau','澳门','特别行政区','珠海'),('shanghai','上海','直辖市','嘉兴')]:
        rr,raw,sha=source(name+'-source.geojson',province);r=rr[0];r.update(name=province,province=province,fullName=province+('特别行政区' if kind=='特别行政区' else '市'),administrativeType=kind)
        p,report=fit(raw[0]);donor_poly=old[next(i for i,t in enumerate(data['regions']) if t['name']==donor)]
        if province=='澳门':
            p,report['translation']=attach(p,donor_poly,max(polygon_parts(raw[0]),key=lambda g:g.area),minimum_iou=0,minimum_contact=1);report['placement']='coastal adjacency illustration'
        elif p.distance(donor_poly)>1e-7:p,report['translation']=attach(p,donor_poly,max(polygon_parts(raw[0]),key=lambda g:g.area))
        regs.append(r);new.append(p);full.append(raw[0]);reports.append({'name':province,'sourceSha256':sha,'sourceFile':name+'-source.geojson','donor':donor,**report})
    carved=list(old)
    for p,r in zip(new,reports):
        idx=next(i for i,region in enumerate(data['regions']) if region['name']==r['donor']);g=carved[idx].difference(p);assert len(polygon_parts(g))==len(polygon_parts(carved[idx])) and g.is_valid
        r['carvedArea']=carved[idx].area-g.area;carved[idx]=g
    from simplify_boundaries import rebuild
    combined=rebuild([p.boundary for p in carved+new],carved+new)
    assert shapely.coverage_is_valid(combined)
    print('Combined',[(r['name'],turns(p),acute_vertices(p)) for r,p in zip(data['regions']+regs,combined) if r['name'] in ['深圳','珠海','嘉兴','香港','澳门','上海']],flush=True)
    print('New adj',[( (data['regions']+regs)[i]['name'],(data['regions']+regs)[j]['name']) for i,j in sorted(adjacent(combined)) if j>=82],flush=True)
    save('data/special-initial.json',{'paths':[svg_path(p) for p in combined],'regions':regs,'reports':reports})

def emit():
    from island_groups import fit_detached_island
    from shapely.affinity import translate
    from xml.sax.saxutils import escape
    a=json.loads((ROOT/'data/special-initial.json').read_text());polys=[geometry_from_path(p) for p in a['paths']]
    oldtext=(ROOT/'dist/south-data.js').read_text();old=json.loads(oldtext.split(' = ',1)[1].split(';\n')[0]);oldrefs=json.loads(oldtext.split('const REFERENCE_MAP = ',1)[1].rstrip(';\n'))['regions'];refs=oldrefs+a['regions']
    _,raw,_=source('shanghai-source.geojson','上海');parts=sorted(polygon_parts(raw[0]),key=lambda p:-p.area);islands=[]
    for k,part in enumerate([parts[1],unary_union(parts[2:4])]):
        if k==0:
            g,fitreport=fit(part);found=False
            for _,dx,dy in sorted((dx*dx+dy*dy,dx,dy) for dx in range(-24,25) for dy in range(-24,25) if dx*dx+dy*dy<=24**2):
                candidate=translate(g,xoff=dx,yoff=dy)
                if candidate.distance(unary_union(polys))>=2.5:
                    island=candidate;meta={'translation':[dx,dy],'sourceArea':part.area,'displayArea':island.area,'minimumGap':2.5,'fit':fitreport};found=True;break
            assert found,'Cannot place main Shanghai island'
        else:
            island,meta=fit_detached_island(part,unary_union(polys));meta['sourceGroupParts']=2
        polys[-1]=unary_union([polys[-1],island]);islands.append({'city':'上海',**meta,'path':svg_path(island)})
    assert shapely.coverage_is_valid(polys)
    expected=adjacent([geometry_from_path(r['variants']['east']['path']) for r in old['regions']])
    for j,name in enumerate(['深圳','珠海','嘉兴']):expected.add((next(i for i,r in enumerate(old['regions']) if r['name']==name),82+j))
    assert adjacent(polys)==expected
    assert not any(p.interiors for p in polygon_parts(unary_union(polys)))
    assert sum(len(acute_vertices(p)) for p in polys)==6
    regions=[]
    for r,p in zip(refs,polys):
        item={k:r[k] for k in ['id','name','province','fullName','administrativeType'] if k in r}
        item['variants']={'east':{'path':svg_path(p),'label':label_for(max(polygon_parts(p),key=lambda p:p.area),r['label'])}};regions.append(item)
    for i in range(82):
        if regions[i]['name'] not in ['深圳','珠海']:regions[i]['variants']['east']['label']=old['regions'][i]['variants']['east']['label']
    data={'version':'0.16.0-base','defaultVariant':'east','regions':regions,'variants':{'east':{'outline':svg_path(unary_union(polys))}}}
    (ROOT/'dist/special-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False)+';\nconst REFERENCE_MAP = '+json.dumps({'regions':refs},ensure_ascii=False)+';\n')
    report={'version':'0.16.0','retrieved':'2026-09-11','baseSha256':hashlib.sha256(oldtext.encode()).hexdigest(),'sourceReports':a['reports'],'islands':islands,'regions':[],'adjacencies':len(expected),'acuteAngles':6}
    for r,p in zip(refs,polys):
        report['regions'].append({'name':r['name'],'area':p.area,'turns':turns(p),'parts':len(polygon_parts(p)),'acuteAngles':len(acute_vertices(p))})
    for j,name in enumerate(['hongkong','macau','shanghai']):
        _,src,_=source(name+'-source.geojson');real=max(polygon_parts(src[0]),key=lambda p:p.area);main=max(polygon_parts(polys[82+j]),key=lambda p:p.area)
        report['sourceReports'][j].update(finalMainlandIou=main.intersection(real).area/main.union(real).area,finalMainlandAreaError=abs(main.area-real.area)/real.area,sourceParts=len(polygon_parts(src[0])),retainedParts=len(polygon_parts(polys[82+j])))
    save('dist/special-report.json',report)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1660 1880"><title>六省与香港、澳门、上海真实区划参考</title><rect width="1660" height="1880" fill="white"/><g transform="translate(500 530)">']
    for r in refs:svg.append('<path fill-rule="evenodd" fill="#f5f7fa" stroke="#26364b" stroke-width="1.4" d="'+r['path']+'"/>')
    for r in refs:svg.append(f'<text x="{r["label"][0]}" y="{r["label"][1]}" text-anchor="middle" font-size="20">{escape(r["name"])}</text>')
    svg.append('</g></svg>');(ROOT/'dist/special-reference.svg').write_text(''.join(svg));print('Emitted',report['sourceReports'],flush=True)

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['base','emit','balance','all'],default='all');args=ap.parse_args()
    if args.stage in ('base','all'):run()
    if args.stage in ('emit','all'):emit()


    if args.stage in ('balance','all'):
        from build_balanced import run as balance
        balance('dist/special-data.js','special-balanced',minimum_median_fraction=.25,alphas=[.75],max_iterations=800)
