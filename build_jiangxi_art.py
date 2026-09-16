"""Build a measured geographic guide and exact, shared-edge artwork placement.
Does not edit any accepted map path. Run with --cache /path/to/downloads.
"""
import json,math,hashlib,argparse
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon,Point,shape,mapping,box
from shapely.ops import unary_union,polygonize,transform
from shapely.geometry.polygon import orient
from generate_map import geometry_from_path,polygon_parts
ROOT=Path(__file__).parent
C=json.loads((ROOT/'data/jiangxi-projection.json').read_text())
BOUNDS=[130,145,500,625]
def project(x,y,z=None):
 x=np.asarray(x);y=np.asarray(y)
 return C['dx']+(np.radians(x)-C['left'])*C['scale'],C['dy']+(-np.log(np.tan(np.pi/4+np.radians(y)/2))-C['top'])*C['scale']
def path(g):
 return ' '.join('M'+' L'.join(f'{x:.6f},{y:.6f}'for x,y in ring.coords)+' Z'for p in polygon_parts(g)for ring in [p.exterior,*p.interiors])
def triangles(a,b):
 # Prefer well-shaped ears valid in both layouts, avoiding elongated texture cells.
 ids=list(range(len(a)));out=[]
 while len(ids)>3:
  candidates=[];removed=False
  for j in range(len(ids)):
   v=[ids[j-1],ids[j],ids[(j+1)%len(ids)]]
   aa=np.array([a[i]for i in v]);bb=np.array([b[i]for i in v])
   ca=np.linalg.det(np.array([aa[1]-aa[0],aa[2]-aa[0]]));cb=np.linalg.det(np.array([bb[1]-bb[0],bb[2]-bb[0]]))
   if abs(ca)<1e-7 and abs(cb)<1e-6:ids.pop(j);removed=True;break
   if ca<=1e-7 or cb<=1e-7:continue
   pa,pb=Polygon(aa),Polygon(bb)
   if any(pa.covers(Point(a[k])) or pb.covers(Point(b[k])) for k in ids if k not in v):continue
   candidates.append((min(pa.area/pa.length**2,pb.area/pb.length**2),j,v))
  if removed:continue
  if not candidates:raise ValueError('No common triangulation ear')
  _,j,v=max(candidates);out.append(v);ids.pop(j)
 out.append(ids)
 return out

def main(cache):
 src=(ROOT/'dist/jiangsu-balanced-data.js').read_text();data=json.loads(src.split(' = ',1)[1].split(';\n')[0]);regions=data['regions'];allbase=[geometry_from_path(r['variants']['east']['path'])for r in regions]
 faces=list(polygonize(unary_union([p.boundary for p in allbase])))
 selected=[i for i,r in enumerate(regions)if r['id'].startswith('36')]
 union=unary_union([allbase[i]for i in selected]);cells=[];shared={};citypaths=[]
 for i in selected:
  r=regions[i];basefaces=[p for p in faces if p.representative_point().within(allbase[i])];target=polygon_parts(geometry_from_path(r['variants']['balanced']['path']))
  assert len(basefaces)==len(target)
  citypaths.append({'id':r['id'],'name':r['name'],'east':r['variants']['east']['path'],'balanced':r['variants']['balanced']['path']})
  mapped=[]
  for p,q in zip(basefaces,target):
   a=np.asarray(orient(p,sign=1).exterior.coords)[:-1];b=np.asarray(q.exterior.coords)[:-1];assert len(a)==len(b),(r['name'],len(a),len(b))
   for av,bv in zip(a,b):
    key=tuple(av);assert key not in shared or np.linalg.norm(shared[key]-bv)<1e-6
    shared[key]=bv
   for ix in triangles(a,b):
    at=a[ix];bt=b[ix];m=np.linalg.solve(np.c_[at,np.ones(3)],bt)
    # SVG matrix(a b c d e f)
    matrix=[m[0,0],m[0,1],m[1,0],m[1,1],m[2,0],m[2,1]]
    assert np.linalg.det(m[:2,:])>0
    cells.append({'id':r['id'],'from':at.tolist(),'to':bt.tolist(),'matrix':matrix,'clip':path(Polygon(bt).buffer(.12,join_style=2))});mapped.append(Polygon(bt))
  assert unary_union(mapped).symmetric_difference(geometry_from_path(r['variants']['balanced']['path'])).area<1e-4
  assert abs(sum(p.area for p in mapped)-unary_union(mapped).area)<1e-5
 print('Mesh verified:',len(cells),'triangles',flush=True)
 outdir=ROOT/'dist/assets/jiangxi';outdir.mkdir(parents=True,exist_ok=True)
 # Snapshot clipped public vector sources; coordinates remain lon/lat.
 geobox=box(113.3,24.3,118.7,30.3);snap={};counts={}
 for key in ['lakes','urban_areas','populated_places','hydrorivers']:
  sourcefile=cache/(key+'.json') if cache else ROOT/f'data/jiangxi-{key}.geojson'
  raw=json.loads(sourcefile.read_text());features=[]
  for f in raw['features']:
   g=shape(f['geometry'])
   if g.intersects(geobox):
    if key=='hydrorivers' and f['properties'].get('UPLAND_SKM',0)<80:continue
    features.append(f)
  snap[key]=features;counts[key]=len(features)
  (ROOT/f'data/jiangxi-{key}.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False))
 # DEM mosaic in exact source Mercator coordinates, no painted relief invented here.
 from PIL import Image
 if cache:
  dem=np.zeros((6*256,5*256),dtype=np.float32)
  for tx in range(208,213):
   for ty in range(105,111):
    rgb=np.array(Image.open(cache/f'dem-8-{tx}-{ty}.png')).astype(float)
    dem[(ty-105)*256:(ty-104)*256,(tx-208)*256:(tx-207)*256]=rgb[:,:,0]*256+rgb[:,:,1]+rgb[:,:,2]/256-32768
  np.savez_compressed(ROOT/'data/jiangxi-dem.npz',elevation=dem,tileOrigin=[208,105],zoom=8)
 else:
  dem=np.load(ROOT/'data/jiangxi-dem.npz')['elevation']
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.colors import LinearSegmentedColormap,LightSource
 from matplotlib.patches import PathPatch
 from matplotlib.path import Path as MPath
 def patch(g,**kw):
  verts=[];codes=[]
  for p in polygon_parts(g):
   for ring in [p.exterior,*p.interiors]:
    rr=list(ring.coords);verts.extend(rr);codes.extend([1]+[2]*(len(rr)-2)+[79])
  return PathPatch(MPath(verts,codes),**kw)
 fig=plt.figure(figsize=(8,10),dpi=192);ax=fig.add_axes([0,0,1,1]);x,y,w,h=BOUNDS;ax.set_xlim(x,x+w);ax.set_ylim(y+h,y);ax.axis('off');fig.patch.set_facecolor('#faf8f0');ax.set_facecolor('#faf8f0')
 clip=patch(union,facecolor='none',edgecolor='none');ax.add_patch(clip)
 cmap=LinearSegmentedColormap.from_list('elevation',['#dce6b6','#c8d7a3','#a2bb83','#6f986b','#456f56','#9c9a75'])
 terrain=LightSource(315,50).shade(dem,cmap,vert_exag=1.3,dx=530,dy=530,vmin=0,vmax=1800,blend_mode='soft')
 def tilecoord(xx,yy):return C['dx']+((xx/256*2*np.pi-np.pi)-C['left'])*C['scale'],C['dy']+((yy/256*2*np.pi-np.pi)-C['top'])*C['scale']
 l,t=tilecoord(208,105);rr,bb=tilecoord(213,111)
 im=ax.imshow(terrain,extent=[l,rr,bb,t],origin='upper',interpolation='bilinear');im.set_clip_path(clip)
 vector=[]
 for f in snap['urban_areas']:
  g=transform(project,shape(f['geometry'])).intersection(union)
  if not g.is_empty:
   pa=patch(g,facecolor='#ad8262',edgecolor='none',alpha=.9);ax.add_patch(pa);vector.append({'kind':'urban','path':path(g)})
 for f in snap['hydrorivers']:
  g=transform(project,shape(f['geometry'])).intersection(union)
  if g.is_empty:continue
  flow=float(f['properties'].get('DIS_AV_CMS',1));width=max(.22,min(1.8,.19+np.log10(max(1,flow))*.33))
  for line in (list(g.geoms)if hasattr(g,'geoms')else[g]):
   if line.geom_type!='LineString':continue
   xx,yy=line.xy;ax.plot(xx,yy,color='#438ca6',linewidth=width*.6,zorder=3)
   vector.append({'kind':'river','path':'M'+' L'.join(f'{xx:.3f},{yy:.3f}'for xx,yy in line.coords),'width':width,'flow':flow})
 for f in snap['lakes']:
  g=transform(project,shape(f['geometry'])).intersection(union)
  if not g.is_empty:
   ax.add_patch(patch(g,facecolor='#78bdd0',edgecolor='#529ab0',linewidth=.3,zorder=4));vector.append({'kind':'lake','path':path(g),'name':f['properties'].get('name')})
 # Settlements from source points; symbols intentionally exaggerated, not urban footprints.
 for f in snap['populated_places']:
  p=Point(*project(*shape(f['geometry']).coords[0]));
  if union.contains(p):ax.scatter([p.x],[p.y],s=8,c='#b77b59',edgecolors='#faf3dc',linewidths=.4,zorder=5)
 # Save the clean guide before reference-only locator numbers.
 fig.savefig(outdir/'geographic-guide.png',dpi=192)
 landmarks=[
 ('Tengwang Pavilion','滕王阁',115.881,28.681,'360100','red-pillared multi-tier pavilion on the Gan east bank'),
 ('Imperial kilns','景德镇御窑',117.207,29.294,'360200','low red brick barrel-vault kilns and white porcelain vessels'),
 ('Wugong Shan','武功山',114.173,27.458,'360300','golden-green alpine meadow ridge'),
 ('Lushan','庐山',115.983,29.567,'360400','steep forested massif west of Poyang Lake, waterfall'),
 ('Fairy Lake','仙女湖',114.818,27.770,'360500','small forested reservoir with islands'),
 ('Longhu Shan','龙虎山',116.958,28.114,'360600','red sandstone cliffs along a winding river'),
 ('Ganzhou old town','赣州古城',114.948,25.866,'360700','city wall and small pontoon bridge at river confluence'),
 ('Jinggangshan','井冈山',114.167,26.570,'360800','layered forested mountain ridges and small historical house'),
 ('Mingyue Shan','明月山',114.29,27.59,'360900','high wooded mountain ridge'),
 ('Wenchangli','文昌里',116.37,27.99,'361000','white-walled dark-tile historic street by Fu river'),
 ('Sanqing Shan','三清山',118.067,28.917,'361100','slender pale granite pillars and pines'),
 ('Wuyuan villages','婺源',117.85,29.25,'361100','white walls black roofs in fields and foothills')]
 locators=[]
 for num,(en,cn,lon,lat,cid,desc) in enumerate(landmarks,1):
  p=Point(*project(lon,lat));g=allbase[next(i for i,r in enumerate(regions)if r['id']==cid)];old=p
  if not g.buffer(-5).contains(p):p=shapely.ops.nearest_points(g.buffer(-5),p)[0]
  locators.append({'number':num,'name':cn,'en':en,'coordinate':[lon,lat],'point':[p.x,p.y],'city':cid,'schematicShift':p.distance(old),'depiction':desc})
  ax.scatter([p.x],[p.y],s=78,c='#a74b36',edgecolors='white',linewidths=1,zorder=8)
  ax.text(p.x,p.y,str(num),ha='center',va='center',color='white',fontsize=6.5,fontweight='bold',zorder=9)
 for i in selected:
  ax.add_patch(patch(allbase[i],facecolor='none',edgecolor='#6c7668',linewidth=.5,alpha=.7,zorder=7))
 fig.savefig(outdir/'generation-guide.png',dpi=192);plt.close(fig)
 payload={'bounds':BOUNDS,'cities':citypaths,'cells':cells,'features':vector,'landmarks':locators,'images':{'art':'assets/jiangxi/artwork.png','geography':'assets/jiangxi/geographic-guide.png'}}
 (ROOT/'dist/jiangxi-art-data.js').write_text('const JIANGXI_ART = '+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n')
 report={'mapSha256':hashlib.sha256(src.encode()).hexdigest(),'geometryUnchanged':True,'cityCount':11,'triangles':len(cells),'positiveJacobian':True,'exactTargetCoverage':True,'counts':counts,'bounds':BOUNDS,'mapping':'Original shared Mercator projection for geographic features; joint-valid per-city triangulation maps one continuous texture into the accepted balanced outlines. Shared edges have identical endpoint maps.','limitations':['Geographic features approximate after administrative simplification; source features outside accepted province silhouette clipped.','Artwork interprets measured relief and rivers; generated details are not measurements.','Natural Earth urban extents are historical and generalized, not current built-up boundaries.','Landmark anchors are approximate, enlarged illustrative symbols; shifts into simplified city masks recorded.'],'landmarks':locators}
 (ROOT/'dist/jiangxi-art-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(counts,flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path);main(ap.parse_args().cache)
