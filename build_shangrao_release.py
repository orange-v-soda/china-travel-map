from __future__ import annotations
import json,math,random,re,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter,ImageChops
R=Path(__file__).parent
A=json.loads((R/"minimal-shangrao-art.json").read_text())
if (R/"dist/jiangxi-art-data.js").exists():
 t=(R/"dist/jiangxi-art-data.js").read_text().strip()
 full=json.loads(t[len("const JIANGXI_ART = "):-1])
 city=next(x for x in full["cities"] if x["id"]=="361100")
 A={"cities":[city],"cells":[x for x in full["cells"] if x["id"]=="361100"],"features":full["features"],"landmarks":[x for x in full["landmarks"] if x["city"]=="361100"]}
G=json.loads((R/"data/shangrao-counties-source.geojson").read_text())
C=A["cities"][0]; P=C["balanced"]; PPU=7.1657142857142855
nums=lambda s:[float(x) for x in re.findall(r"-?\d+(?:\.\d+)?",s)]
pts=lambda s:list(zip(nums(s)[::2],nums(s)[1::2]))
def box(q):
 x=[p[0] for p in q];y=[p[1] for p in q];return min(x),min(y),max(x),max(y)
Q=pts(P); X0,Y0,X1,Y1=box(Q); W=round((X1-X0)*PPU);H=round((Y1-Y0)*PPU);S=PPU*2
def relevant(feature):
 q=pts(feature["path"])
 if not q:return False
 x0,y0,x1,y1=box(q)
 return x1>=X0-10 and x0<=X1+10 and y1>=Y0-10 and y0<=Y1+10
A["features"]=[f for f in A["features"] if relevant(f)]
def px(p):return ((p[0]-X0)*S,(p[1]-Y0)*S)
def rings(f):
 g=f["geometry"]; ps=g["coordinates"] if g["type"]=="MultiPolygon" else [g["coordinates"]]
 for p in ps: yield p[0]
allg=[tuple(v) for f in G["features"] for z in rings(f) for v in z]
gx0,gy0,gx1,gy1=box(allg); ex0,ey0,ex1,ey1=box(pts(C["east"]))
def tri(p,a,b,c):
 d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
 if abs(d)<1e-9:return False
 u=((b[1]-c[1])*(p[0]-c[0])+(c[0]-b[0])*(p[1]-c[1]))/d
 v=((c[1]-a[1])*(p[0]-c[0])+(a[0]-c[0])*(p[1]-c[1]))/d
 return u>=-1e-6 and v>=-1e-6 and u+v<=1.000001
def warp(lon,lat):
 p=(ex0+(lon-gx0)/(gx1-gx0)*(ex1-ex0),ey0+(gy1-lat)/(gy1-gy0)*(ey1-ey0))
 cs=[c for c in A["cells"] if tri(p,*c["from"])]
 if not cs:
  cs=sorted(A["cells"],key=lambda c:(p[0]-sum(v[0] for v in c["from"])/3)**2+(p[1]-sum(v[1] for v in c["from"])/3)**2)[:1]
 a,b,c,d,e,f=cs[0]["matrix"];return a*p[0]+c*p[1]+e,b*p[0]+d*p[1]+f
def lines(path):
 for s in re.split(r"(?=M)",path):
  q=pts(s)
  if len(q)>1:yield [px(p) for p in q]
def mountain(d,x,y,z):
 x,y=px((x,y));z*=S
 d.polygon([(x-z,y+z*.55),(x-z*.15,y-z),(x+z,y+z*.55)],fill=(82,125,85,190))
 d.polygon([(x-z*.15,y-z),(x+z*.12,y-z*.12),(x+z,y+z*.55)],fill=(58,96,69,190))
def build():
 random.seed(361100); size=(W*2,H*2)
 im=Image.new("RGBA",size,(239,232,205,255)); mask=Image.new("L",size);ImageDraw.Draw(mask).polygon([px(p) for p in Q],fill=255)
 wash=Image.new("RGBA",size);wd=ImageDraw.Draw(wash,"RGBA")
 for _ in range(100): 
  x=random.uniform(size[0]*.35,size[0]);y=random.uniform(0,size[1]);r=random.uniform(20,95)
  wd.ellipse((x-r,y-r*.6,x+r,y+r*.6),fill=(64,114,76,random.randint(12,35)))
 im=Image.alpha_composite(im,wash.filter(ImageFilter.GaussianBlur(20)))
 art=Image.new("RGBA",size);d=ImageDraw.Draw(art,"RGBA")
 for _ in range(150):
  nx,ny=random.random(),random.random()
  if nx<.42 and ny>.55 and random.random()<.72:continue
  mountain(d,X0+(X1-X0)*(.25+.72*nx),Y0+(Y1-Y0)*(.04+.9*ny),random.uniform(1.1,2.5))
 for f in A["features"]:
  if f.get("kind")=="lake":
   for q in lines(f["path"]):
    if len(q)>2:d.polygon(q,fill=(75,143,165,225))
 for f in A["features"]:
  if f.get("kind")=="river":
   for q in lines(f["path"]):d.line(q,fill=(65,130,153,225),width=max(1,int(float(f.get("width",.5))*S*1.2)),joint="curve")
 anchors=[]
 for f in G["features"]:
  p=f["properties"];co=p.get("center") or p.get("centroid")
  if not co:continue
  q=warp(*co);anchors.append({"adcode":p.get("adcode"),"name":p.get("name"),"coordinate":co,"page":q})
  x,y=px(q);r=(3 if p.get("adcode") in (361102,361104) else 1.8)*S
  d.ellipse((x-r,y-r*.7,x+r,y+r*.7),fill=(120,119,112,185))
  for a in (0,math.pi/3,-math.pi/3):
   dx,dy=math.cos(a)*r*1.5,math.sin(a)*r*1.5;d.line((x-dx,y-dy,x+dx,y+dy),fill=(241,233,210,210),width=max(1,int(S*.25)))
 wy=next(x for x in A["landmarks"] if x["number"]==12)["point"];wx,wy=px(wy)
 for i in range(12):
  x=wx+(i%4-1.5)*1.8*S;y=wy+(i//4-1)*1.6*S
  d.rectangle((x-.5*S,y,x+.5*S,y+.6*S),fill=(243,238,222,245));d.polygon((x-.7*S,y,x,y-.7*S,x+.7*S,y),fill=(50,54,51,240))
 sx,sy=px(next(x for x in A["landmarks"] if x["number"]==11)["point"])
 for dx,h,z in [(-2.4,6.5,1.2),(0,9,1.35),(2.4,5.7,1.0),(4,4.5,.8)]:
  x=sx+dx*S;d.polygon((x-z*S,sy+3*S,x-.45*z*S,sy-h*S,x+.3*z*S,sy-(h+1)*S,x+z*S,sy+3*S),fill=(189,184,168,245))
 art.putalpha(ImageChops.multiply(art.getchannel("A"),mask));im=Image.alpha_composite(im,art);im.putalpha(mask);im=im.resize((W,H),Image.Resampling.LANCZOS)
 out=R/"dist/assets/shangrao";out.mkdir(parents=True,exist_ok=True);img=out/"shangrao-art-final-v1.webp";im.save(img,"WEBP",quality=84,method=6)
 water=[]
 for f in A["features"]:
  if f.get("kind")=="lake":water.append(f'<path d="{f["path"]}" fill="#5ba8c1"/>')
  elif f.get("kind")=="river" and float(f.get("width",0))>=.42:water.append(f'<path d="{f["path"]}" fill="none" stroke="#4d91a8" stroke-width="{max(.45,float(f.get("width",.5))):.3f}"/>')
 dens="".join(f'<ellipse cx="{a["page"][0]:.4f}" cy="{a["page"][1]:.4f}" rx="2" ry="1.4"/>' for a in anchors)
 sem=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0} {Y0} {X1-X0} {Y1-Y0}"><defs><clipPath id="region"><path d="{P}"/></clipPath></defs><g clip-path="url(#region)"><path d="{P}" fill="#dfe3bd"/><g id="wilderness"><path d="M520 232C560 218 600 245 606 294V366C573 345 543 335 520 311Z" fill="#74a078"/></g><g id="rural-farmland"><path d="M418 285C450 270 492 286 522 316L511 386C475 374 444 353 420 333Z" fill="#d2be82"/></g><g id="unified-water-surface">{''.join(water)}</g><g id="settlement-density" fill="#8f8d87">{dens}</g><g id="landmark-markers" fill="#c94b3f"><circle cx="576.7396" cy="280.7165" r="3.2"/><circle cx="555.7773" cy="243.9074" r="3.2"/></g></g></svg>'''
 (out/"shangrao-semantic.svg").write_text(sem);(out/"shangrao-mask.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0} {Y0} {X1-X0} {Y1-Y0}"><path d="{P}" fill="#fff"/></svg>\n')
 joint=sem.replace(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{X0} {Y0} {X1-X0} {Y1-Y0}">','<svg xmlns="http://www.w3.org/2000/svg" viewBox="130 145 500 625"><g id="accepted-neighbor-context"></g><g id="join-owned-semantics"></g>')
 jo=R/"dist/assets/joint-nanchang-jiujiang-fuzhou-shangrao";jo.mkdir(parents=True,exist_ok=True);(jo/"nanchang-jiujiang-fuzhou-shangrao-joint-semantic-v9.svg").write_text(joint)
 span=175.;margin=15.;over=48.
 def origins(lo,hi):
  n=max(1,math.ceil((hi-lo+2*margin-over)/(span-over)));return [(lo+hi-span)/2] if n==1 else [lo-margin+(hi+margin-span-(lo-margin))*i/(n-1) for i in range(n)]
 wins=[]
 for row,y in enumerate(origins(Y0,Y1)):
  for col,x in enumerate(origins(X0,X1)):
   i=len(wins)+1;stem=f"shangrao-{i:02d}";base=f"artwork/generation-inputs/shangrao/fixed-scale-tiles/{stem}"
   wins.append({"index":i,"row":row,"column":col,"worldBounds":[x,y,span,span],"canvasPixels":[2048,2048],"pixelsPerPageUnit":2048/175,"context":base+"-context.png","visibleMask":base+"-mask.png","editMask":base+"-edit-mask.png","lockedAcceptedRegions":[],"postGenerationRule":"restore every black-mask pixel from context before compositing"})
 plan={"schemaVersion":1,"region":"361100","layout":"balanced","canonicalPath":P,"canonicalPathBounds":[X0,Y0,X1-X0,Y1-Y0],"fixedScaleConfig":"artwork/fixed-scale-generation.json","windowCount":len(wins),"generationOrder":[w["index"] for w in wins],"windows":wins,"neighborArt":[{"region":"360400","image":"dist/assets/jiujiang/jiujiang-art-final-v7.webp"},{"region":"361000","image":"dist/assets/fuzhou/fuzhou-art-final-v1.webp"}],"acceptedWindows":[],"publishRule":"composite in balanced page coordinates; crop to canonicalPathBounds; never stretch"}
 pp=R/"artwork/generation-inputs/shangrao/fixed-scale-tiles/shangrao-plan.json";pp.parent.mkdir(parents=True,exist_ok=True);pp.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n")
 man={"projectOutline":"main / JIANGXI_ART region 361100 / balanced","warp":"JIANGXI_ART cells 361100","textFree":True,"anchors":anchors,"settlementSemantics":{"regionalProfile":"Poyang Lake eastern shore / Xin River valley / Wuyuan-Huaiyu-Sanqingshan ranges","wilderness":{"visual":"untinted base","generation":"wooded ranges and dry valleys"},"rural":{"visual":"light ochre farmland","generation":"lake-shore and Xin River fields"},"countyTown":{"visual":"warm light-gray","generation":"compact modern county towns"},"metropolitan":{"visual":"cool-gray continuous","generation":"Shangrao Xin River urban corridor"}},"waterSemantics":{"topology":"unified-lake-and-river-surface","riverStrokeInsideLakeAllowed":False,"openWaterExpansionAllowed":False,"wetlandDefaultRendering":"land-dominant"},"landmarks":[{"marker":"landmark-1","name":"三清山","coordinate":[118.067,28.917],"page":[576.739563,280.716545]},{"marker":"landmark-2","name":"婺源村落","coordinate":[117.85,29.25],"page":[555.777312,243.907413]}],"generationViewport":{"coordinateSystem":"balanced-page-space","canonicalBounds":[X0,Y0,X1-X0,Y1-Y0],"windowCount":len(wins),"pixelsPerPageUnit":2048/175}}
 (out/"manifest.json").write_text(json.dumps(man,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"image":str(img),"bytes":img.stat().st_size,"plan":str(pp),"windows":len(wins)}))
if __name__=="__main__":build()
