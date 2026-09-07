"""Build geographic SVG and browser data from the GeoAtlas Jiangxi snapshot.

Usage: python generate_reference.py /path/to/360000_full.json
Without an argument, download the named source. No external Python packages.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.request import urlopen
from xml.sax.saxutils import escape

SOURCE='https://geo.datav.aliyun.com/areas_v3/bound/360000_full.json'
ROOT=Path(__file__).parent

def generate(raw):
    features=json.loads(raw)['features']
    def project(p):return (math.radians(p[0]),-math.log(math.tan(math.pi/4+math.radians(p[1])/2)))
    def polygons(f):
        c=f['geometry']['coordinates']
        return c if f['geometry']['type']=='MultiPolygon' else [c]
    allpoints=[project(p) for f in features for poly in polygons(f) for ring in poly for p in ring]
    left=min(p[0] for p in allpoints);right=max(p[0] for p in allpoints)
    top=min(p[1] for p in allpoints);bottom=max(p[1] for p in allpoints)
    scale=min(512/(right-left),608/(bottom-top))
    dx=124+(512-(right-left)*scale)/2;dy=152+(608-(bottom-top)*scale)/2
    def xy(p):
        x,y=project(p);return [round(dx+(x-left)*scale,2),round(dy+(y-top)*scale,2)]
    regions=[]
    for f in features:
        p=f['properties'];paths=[]
        for poly in polygons(f):
            for ring in poly:
                coords=[xy(c) for c in ring]
                paths.append(' '.join(('M' if i==0 else 'L')+f'{x},{y}' for i,(x,y) in enumerate(coords))+' Z')
        regions.append({'id':str(p['adcode']),'name':p['name'].removesuffix('市'),'path':' '.join(paths),'label':xy(p.get('centroid',p['center']))})
    info={'source':SOURCE,'retrieved':'2026-09-07','sha256':hashlib.sha256(raw).hexdigest(),'projection':'Spherical Mercator; uniform fit, no independent x/y scaling','regions':regions}
    (ROOT/'dist/reference-data.js').write_text('const REFERENCE_MAP = '+json.dumps(info,ensure_ascii=False,separators=(',',':'))+';\n')
    paths='\n'.join(f'<path data-city="{r["id"]}" d="{r["path"]}"/>' for r in regions)
    labels='\n'.join(f'<text x="{r["label"][0]}" y="{r["label"][1]}">{escape(r["name"])}</text>' for r in regions)
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 860" width="760" height="860" role="img" aria-labelledby="title desc">
<title id="title">江西省真实区划参考图</title><desc id="desc">根据阿里云 DataV.GeoAtlas 边界数据投影生成，保留源数据轮廓，供抽象地图对照。非官方标准地图。</desc>
<metadata>Source: {SOURCE}; retrieved 2026-09-07; SHA256 {info['sha256']}</metadata>
<rect width="760" height="860" fill="white"/>
<g font-family="sans-serif" fill="#17263b"><text x="64" y="76" font-size="34" font-weight="700">江西</text><text x="65" y="101" font-size="12" fill="#68768a">真实区划 / GEOGRAPHIC REFERENCE</text></g>
<g fill="#f6f8fc" stroke="#26364b" stroke-width="1.4" stroke-linejoin="round" fill-rule="evenodd">{paths}</g>
<g font-family="sans-serif" font-size="21" font-weight="600" fill="#17263b" text-anchor="middle" dominant-baseline="central" paint-order="stroke" stroke="white" stroke-width="3" stroke-linejoin="round">{labels}</g>
<path d="M680 142V114M673 122L680 114L687 122" fill="none" stroke="#17263b" stroke-width="1.5"/><text x="680" y="105" text-anchor="middle" font-size="12" font-family="sans-serif">N</text>
<path d="M64 795H696" stroke="#dfe5ec"/><text x="64" y="822" font-size="12" fill="#68768a" font-family="sans-serif">数据：DataV.GeoAtlas · 参考示意，非官方标准地图</text>
</svg>'''
    (ROOT/'dist/jiangxi-reference.svg').write_text(svg)
    print('Built geographic reference SVG:',len(regions),'cities; SHA256',info['sha256'])

if __name__=='__main__':
    raw=Path(sys.argv[1]).read_bytes() if len(sys.argv)>1 else urlopen(SOURCE,timeout=30).read()
    generate(raw)
