"""Area-compressed comparison; shared vertices and edge directions stay fixed."""
import json, hashlib
from pathlib import Path
import numpy as np
from scipy.linalg import null_space
from scipy.optimize import minimize, LinearConstraint
from shapely.geometry import Polygon, MultiPolygon, Point, LineString
from shapely.ops import unary_union, polygonize, nearest_points
from shapely.geometry.polygon import orient
from shapely import coverage_is_valid
from generate_map import ROOT,geometry_from_path,polygon_parts,label_for,adjacent
from soften_angles import acute_vertices

ALPHA=.75

def run():
    source=(ROOT/'dist/south-data.js').read_text();data=json.loads(source.split(' = ',1)[1].split(';\n')[0])
    original=[geometry_from_path(r['variants']['east']['path']) for r in data['regions']]
    # Polygonize the common network so both sides carry identical split vertices.
    faces=list(polygonize(unary_union([p.boundary for p in original])))
    owners=[max(range(len(original)),key=lambda i:p.intersection(original[i]).area) for p in faces]
    nodes=[];lookup={};rings=[]
    for p in faces:
        assert not p.interiors
        ring=[]
        for xy in list(orient(p,sign=1).exterior.coords)[:-1]:
            if xy not in lookup:lookup[xy]=len(nodes);nodes.append(xy)
            ring.append(lookup[xy])
        rings.append(np.array(ring))
    X=np.array(nodes)/100.;V=len(X);base=X.copy();areas=np.array([p.area/10000 for p in original]);partareas=np.array([p.area/10000 for p in faces])
    edges=sorted({tuple(sorted((int(a),int(b)))) for rr in rings for a,b in zip(rr,np.roll(rr,-1))});ea=np.array([a for a,b in edges]);eb=np.array([b for a,b in edges]);vectors=X[eb]-X[ea];length=np.linalg.norm(vectors,axis=1);unit=vectors/length[:,None]
    C=np.zeros((len(edges),2*V))
    for k,(a,b) in enumerate(edges):
        normal=np.array([-unit[k,1],unit[k,0]]);C[k,2*a:2*a+2]=-normal;C[k,2*b:2*b+2]=normal
    N=null_space(C);print('Network',V,'vertices',len(edges),'edges',N.shape[1],'degrees of freedom',flush=True)
    oi=np.array(owners);ra=np.concatenate(rings);rb=np.concatenate([np.roll(rr,-1) for rr in rings]);owneredge=np.concatenate([np.full(len(rr),i) for rr,i in zip(rings,owners)]);partedge=np.concatenate([np.full(len(rr),i) for i,rr in enumerate(rings)]);counts=np.bincount(owneredge,minlength=82)
    expected=adjacent(original);oldacute=sum(len(acute_vertices(p)) for p in original)
    def geometries(x):
        ff=[Polygon(np.round(x[rr]*100,8)) for rr in rings]
        pp=[MultiPolygon([p for p,j in zip(ff,owners) if i==j]) if owners.count(i)>1 else ff[owners.index(i)] for i in range(82)]
        return pp
    def valid(x,verbose=False):
        def fail(reason):
            if verbose:print("Rejected",reason,flush=True)
            return False
        if np.min(np.sum((x[eb]-x[ea])*unit,axis=1)-np.minimum(length*.25,.02))< -1e-7:return fail("edge length")
        pp=geometries(x)
        if any(not p.is_valid for p in pp) or not coverage_is_valid(pp):return fail("invalid coverage")
        if adjacent(pp)!=expected:return fail("adjacency")
        u=unary_union(pp)
        if len(polygon_parts(u))!=len(polygon_parts(unary_union(original))) or any(p.interiors for p in polygon_parts(u)):return fail("union components or holes")
        if sum(len(acute_vertices(p)) for p in pp)!=oldacute:return fail("acute angles")
        # Keep detached pieces detached and readable as islands.
        for i,p in enumerate(pp):
            for part in polygon_parts(p):
                if part.area==max(q.area for q in polygon_parts(p)):continue
                other=unary_union([q if j!=i else q.difference(part) for j,q in enumerate(pp)])
                if part.distance(other)<2.5-1e-6:return fail("island gap "+str(i))
        return True
    E=np.sum((N.reshape(V,2,-1)[eb]-N.reshape(V,2,-1)[ea])*unit[:,:,None],axis=1)
    # Supporting halfplanes keep nearby nonincident edges separated. Shared
    # endpoints remain free; disconnected components retain sea clearance.
    parent=list(range(V))
    def find(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for a,b in edges:parent[find(a)]=find(b)
    lines=[LineString([base[a],base[b]]) for a,b in edges]
    constraints=[row for row in E];lower=list(np.minimum(length*.25,.02)-length)
    nn=N.reshape(V,2,-1)
    for k,(a,b) in enumerate(edges):
        for j in range(k):
            c,d=edges[j]
            if len({a,b,c,d})<4:continue
            distance=lines[k].distance(lines[j])
            if distance<1e-8 or distance>.5:continue
            pa,pb=nearest_points(lines[k],lines[j]);normal=(np.array(pb.coords[0])-np.array(pa.coords[0]))/distance
            gap=.025 if find(a)!=find(c) else min(distance*.2,.02)
            # Direction and positive length fix the extremal endpoints, so one
            # inequality represents the entire pair of segments.
            u=max((a,b),key=lambda i:normal@base[i]);v=min((c,d),key=lambda i:normal@base[i])
            constraints.append(normal@(nn[v]-nn[u]));lower.append(gap-normal@(base[v]-base[u]))
    constraint=LinearConstraint(np.array(constraints),np.array(lower),np.inf)
    print('Linear constraints',len(lower),flush=True)
    z=np.zeros(N.shape[1]);trace=[]
    for alpha in [.95,.90,.85,.80,.75]:
        target=areas**alpha;target*=areas.sum()/target.sum();scale=np.sqrt(target/areas);ptarget=partareas*target[oi]/areas[oi]
        desired=(base[rb]-base[ra])*scale[owneredge,None];w=.3/(counts[owneredge]*areas[owneredge]);anchor=.005/V
        def loss(z):
            x=base+(N@z).reshape(-1,2);a=x[ra];b=x[rb];pa=np.bincount(partedge,weights=(a[:,0]*b[:,1]-a[:,1]*b[:,0])/2,minlength=len(rings))
            err=(pa-ptarget)/ptarget;weights=1/np.bincount(oi,minlength=82)[oi];f=np.sum(weights*err**2);g=np.zeros_like(x)
            coeff=(2*weights*err/ptarget)[partedge]/2
            np.add.at(g,ra,coeff[:,None]*np.column_stack((b[:,1],-b[:,0])));np.add.at(g,rb,coeff[:,None]*np.column_stack((-a[:,1],a[:,0])))
            delta=(b-a)-desired;f+=np.sum(w[:,None]*delta**2);dg=2*w[:,None]*delta;np.add.at(g,rb,dg);np.add.at(g,ra,-dg)
            diff=x-base;f+=anchor*np.sum(diff**2);g+=2*anchor*diff
            ll=np.sum((x[eb]-x[ea])*unit,axis=1);short=np.minimum(ll-np.minimum(length*.25,.02),0);f+=100*np.sum(short**2);gg=200*short[:,None]*unit;np.add.at(g,eb,gg);np.add.at(g,ea,-gg)
            return f,N.T@g.ravel()
        result=minimize(loss,z,jac=True,method='SLSQP',constraints=[constraint],options={'maxiter':400,'ftol':1e-9})
        step=1.
        while step>1/1024:
            candidate=z+step*(result.x-z);x=base+(N@candidate).reshape(-1,2)
            if valid(x,verbose=step==1):break
            step/=2
        if step<=1/1024:step=0;candidate=z
        z=candidate;pp=geometries(base+(N@z).reshape(-1,2));aa=[p.area for p in pp]
        trace.append({'alpha':alpha,'acceptedStep':step,'iterations':result.nit,'optimizerSuccess':bool(result.success),'message':str(result.message),'ratio':max(aa)/min(aa)})
        print(trace[-1],flush=True)
    x=base+(N@z).reshape(-1,2);assert valid(x);pp=geometries(x)
    def path(p):return ' '.join('M'+' L'.join(f'{a:.8f},{b:.8f}' for a,b in q.exterior.coords)+' Z' for q in polygon_parts(p))
    metrics=[]
    from shapely.affinity import translate,scale as rescale
    for i,(r,p,q) in enumerate(zip(data['regions'],pp,original)):
        moved=translate(p,xoff=q.centroid.x-p.centroid.x,yoff=q.centroid.y-p.centroid.y);normalized=rescale(moved,xfact=np.sqrt(q.area/p.area),yfact=np.sqrt(q.area/p.area),origin=q.centroid)
        metrics.append({'id':r['id'],'name':r['name'],'beforeArea':q.area,'afterArea':p.area,'areaFactor':p.area/q.area,'normalizedShapeIou':normalized.intersection(q).area/normalized.union(q).area,'centroidShift':p.centroid.distance(q.centroid),'parts':len(polygon_parts(p))})
        r['variants']['balanced']={'path':path(p),'label':label_for(max(polygon_parts(p),key=lambda p:p.area),r['variants']['east']['label'])}
    data['variants']['balanced']={'outline':path(unary_union(pp))};data['defaultVariant']='balanced';data['version']='0.15.0-experiment'
    report={'sourceSha256':hashlib.sha256(source.encode()).hexdigest(),'alpha':ALPHA,'beforeRatio':max(areas)/min(areas),'afterRatio':max(p.area for p in pp)/min(p.area for p in pp),'targetRatio':(max(areas)/min(areas))**ALPHA,'trace':trace,'cities':metrics,'vertices':V,'edges':len(edges),'adjacencies':len(expected),'acuteAngles':oldacute,'note':'Fixed edge directions, fixed shared vertex connectivity; soft area targets; no manual coordinates.'}
    (ROOT/'dist/balanced-data.js').write_text('const MAP_DATA = '+json.dumps(data,ensure_ascii=False)+';\n')
    (ROOT/'dist/balanced-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Final',report['beforeRatio'],report['afterRatio'],'shape min',min(m['normalizedShapeIou'] for m in metrics),flush=True)
if __name__=='__main__':run()
