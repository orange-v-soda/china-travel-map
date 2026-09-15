"""Authored geographic illustration, not satellite imagery or measured land cover.
All layers share one geographic projection and one affine placement; the accepted
city polygon clips every layer. No administrative geometry is modified.
"""
import json,math,hashlib
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,LineString,Point
from shapely.affinity import scale,translate
from generate_map import geometry_from_path,polygon_parts
ROOT=Path(__file__).parent
C=json.loads((ROOT/'data/jiangxi-projection.json').read_text())
def xy(p):
 x=math.radians(p[0]);y=-math.log(math.tan(math.pi/4+math.radians(p[1])/2))
 return C['dx']+(x-C['left'])*C['scale'],C['dy']+(y-C['top'])*C['scale']
def path(g):
 return ' '.join('M'+' L'.join(f'{x:.4f},{y:.4f}' for x,y in ring.coords)+' Z' for p in polygon_parts(g) for ring in [p.exterior,*p.interiors])
def run():
 source=(ROOT/'dist/jiangsu-balanced-data.js').read_text();data=json.loads(source.split(' = ',1)[1].split(';\n')[0]);city=next(r for r in data['regions'] if r['id']=='360100')
 spec=json.loads((ROOT/'data/nanchang-landscape-sketch.json').read_text());reference=json.loads(source.split('const SOURCE_REFERENCE = ',1)[1].rstrip(';\n'));real=geometry_from_path(next(r for r in reference['regions'] if r['id']=='360100')['path'])
 xmin,ymin,xmax,ymax=real.bounds;variants={}
 for name,v in city['variants'].items():
  clip=geometry_from_path(v['path']);a,b,c,d=clip.bounds
  def mapped(g):return translate(scale(g,xfact=(c-a)/(xmax-xmin),yfact=(d-b)/(ymax-ymin),origin=(xmin,ymin)),xoff=a-xmin,yoff=b-ymin)
  layers=[{'kind':'plain','fill':'#c9d5ad','path':v['path']}]
  for f in spec['features']:
   g=Polygon([xy(p) for p in f['coordinates']]) if f['type']=='area' else LineString([xy(p) for p in f['coordinates']]).buffer(f['width']/2,quad_segs=4)
   g=mapped(g).intersection(clip)
   if g.is_empty:continue
   assert g.is_valid and g.difference(clip).area<1e-6
   layers.append({'kind':f['kind'],'name':f['name'],'fill':f['fill'],'path':path(g)})
   if f['kind']=='mountain':
    for amount,color in [(1.7,'#759473'),(3.4,'#5f8267'),(5.1,'#4c705b')]:
     p=g.buffer(-amount).simplify(.5)
     if not p.is_empty:layers.append({'kind':'relief','fill':color,'path':path(p)})
   if f['kind']=='urban':
    # Sparse abstract blocks: density texture, not a real street network.
    l,t,r,bt=g.bounds
    for xx in np.arange(l,r,2.7):
     for yy in np.arange(t,bt,2.7):
      q=Polygon([(xx,yy),(xx+1.8,yy),(xx+1.8,yy+1.1),(xx,yy+1.1)]).intersection(g.buffer(-.5))
      if q.area>.5:layers.append({'kind':'blocks','fill':'#aea896','path':path(q)})
  landmark=mapped(Point(xy(spec['landmark']['coordinate'])))
  assert clip.contains(landmark)
  label=[(a+c)/2,b+(d-b)*.83];assert clip.contains(Point(label))
  variants[name]={'clip':v['path'],'layers':layers,'landmark':[landmark.x,landmark.y],'label':label}
 out={'cityId':'360100','title':'南昌山水概括','provenance':'Authored schematic geographic features; no DEM, satellite imagery or measured urban extent.','variants':variants}
 (ROOT/'dist/nanchang-landscape-data.js').write_text('const NANCHANG_LANDSCAPE = '+json.dumps(out,ensure_ascii=False)+';\n')
 report={'mapSha256':hashlib.sha256(source.encode()).hexdigest(),'sketchSha256':hashlib.sha256((ROOT/'data/nanchang-landscape-sketch.json').read_bytes()).hexdigest(),'geometryUnchanged':True,'placement':'One affine transform from reference bounds to accepted city bounds, followed by polygon clipping. Not a topology-preserving full boundary warp.','limitations':['Authored approximate positions and extents','Relief bands are decorative, not elevation contours','River width exaggerated for overview readability','No cross-city river continuity claimed','Only Nanchang has landscape content'],'layers':{k:len(v['layers']) for k,v in variants.items()}}
 (ROOT/'dist/nanchang-landscape-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report)
if __name__=='__main__':run()
