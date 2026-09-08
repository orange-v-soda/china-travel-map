"""Build one geographic reference from adjacent province-level GeoAtlas snapshots.

Default experiment: Jiangxi (360000) + Zhejiang (330000).  Their prefecture
features are projected together into one canvas so the provincial border is
part of the same shared line network used by the octilinear pipeline.

Usage:
  python generate_reference.py
  python generate_reference.py /path/to/360000_full.json /path/to/330000_full.json

No external Python packages are required for this reference-data step.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.request import urlopen
from xml.sax.saxutils import escape

ROOT=Path(__file__).parent
PROVINCES=[
    {"adcode":"360000","name":"江西","abbr":"赣"},
    {"adcode":"330000","name":"浙江","abbr":"浙"},
]
SOURCE_TEMPLATE="https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json"
CANVAS={"width":1120,"height":860,"mapLeft":124,"mapTop":152,"mapWidth":872,"mapHeight":608}


def read_raw_sources(paths):
    if paths and len(paths)!=len(PROVINCES):
        raise SystemExit(f"expected {len(PROVINCES)} local GeoJSON files, got {len(paths)}")
    rows=[]
    for i,province in enumerate(PROVINCES):
        url=SOURCE_TEMPLATE.format(adcode=province["adcode"])
        raw=Path(paths[i]).read_bytes() if paths else urlopen(url,timeout=30).read()
        rows.append((province,url,raw))
    return rows


def generate(source_rows):
    source_digest=hashlib.sha256()
    features=[]
    sources=[]
    for province,url,raw in source_rows:
        source_digest.update(province["adcode"].encode())
        source_digest.update(raw)
        payload=json.loads(raw)
        sources.append({
            "province":province["name"],"adcode":province["adcode"],"url":url,
            "sha256":hashlib.sha256(raw).hexdigest(),
        })
        for feature in payload["features"]:
            feature["_province"]=province
            features.append(feature)

    def project(p):
        return (math.radians(p[0]),-math.log(math.tan(math.pi/4+math.radians(p[1])/2)))

    def polygons(feature):
        coords=feature["geometry"]["coordinates"]
        return coords if feature["geometry"]["type"]=="MultiPolygon" else [coords]

    allpoints=[project(p) for f in features for poly in polygons(f) for ring in poly for p in ring]
    left=min(p[0] for p in allpoints);right=max(p[0] for p in allpoints)
    top=min(p[1] for p in allpoints);bottom=max(p[1] for p in allpoints)
    scale=min(CANVAS["mapWidth"]/(right-left),CANVAS["mapHeight"]/(bottom-top))
    dx=CANVAS["mapLeft"]+(CANVAS["mapWidth"]-(right-left)*scale)/2
    dy=CANVAS["mapTop"]+(CANVAS["mapHeight"]-(bottom-top)*scale)/2

    def xy(p):
        x,y=project(p)
        return [round(dx+(x-left)*scale,2),round(dy+(y-top)*scale,2)]

    regions=[]
    for f in features:
        props=f["properties"];province=f["_province"];paths=[]
        for poly in polygons(f):
            for ring in poly:
                coords=[xy(c) for c in ring]
                paths.append(" ".join(("M" if i==0 else "L")+f"{x},{y}" for i,(x,y) in enumerate(coords))+" Z")
        regions.append({
            "id":str(props["adcode"]),
            "name":props["name"].removesuffix("市"),
            "province":province["name"],
            "provinceAdcode":province["adcode"],
            "path":" ".join(paths),
            "label":xy(props.get("centroid",props["center"])),
        })

    short_name="赣浙"
    info={
        "title":"江西 + 浙江",
        "shortName":short_name,
        "provinceNames":[p["name"] for p in PROVINCES],
        "retrieved":"2026-09-08",
        "sha256":source_digest.hexdigest(),
        "projection":"Spherical Mercator; one shared projection and scale for all provinces",
        "canvas":CANVAS,
        "sources":sources,
        "regions":regions,
    }
    (ROOT/"dist/reference-data.js").write_text(
        "const REFERENCE_MAP = "+json.dumps(info,ensure_ascii=False,separators=(",",":"))+";\n"
    )

    paths="\n".join(f'<path data-city="{r["id"]}" d="{r["path"]}"/>' for r in regions)
    labels="\n".join(
        f'<text x="{r["label"][0]}" y="{r["label"][1]}">{escape(r["name"])}</text>' for r in regions
    )
    w=CANVAS["width"];h=CANVAS["height"];right_note=w-64;north_x=w-80
    source_text=" + ".join(p["province"] for p in sources)
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="title desc">
<title id="title">赣浙真实区划联合参考图</title><desc id="desc">江西与浙江的地级市边界使用同一投影和比例尺生成，省界作为同一共享边界网络的一部分。非官方标准地图。</desc>
<metadata>Sources: {source_text}; combined SHA256 {info["sha256"]}</metadata>
<rect width="{w}" height="{h}" fill="white"/>
<g font-family="sans-serif" fill="#17263b"><text x="64" y="76" font-size="34" font-weight="700">赣浙</text><text x="65" y="101" font-size="12" fill="#68768a">联合真实区划 / GEOGRAPHIC REFERENCE</text></g>
<g fill="#f6f8fc" stroke="#26364b" stroke-width="1.4" stroke-linejoin="round" fill-rule="evenodd">{paths}</g>
<g font-family="sans-serif" font-size="18" font-weight="600" fill="#17263b" text-anchor="middle" dominant-baseline="central" paint-order="stroke" stroke="white" stroke-width="3" stroke-linejoin="round">{labels}</g>
<path d="M{north_x} 142V114M{north_x-7} 122L{north_x} 114L{north_x+7} 122" fill="none" stroke="#17263b" stroke-width="1.5"/><text x="{north_x}" y="105" text-anchor="middle" font-size="12" font-family="sans-serif">N</text>
<path d="M64 795H{right_note}" stroke="#dfe5ec"/><text x="64" y="822" font-size="12" fill="#68768a" font-family="sans-serif">数据：DataV.GeoAtlas · 江西 + 浙江联合参考 · 非官方标准地图</text>
</svg>'''
    (ROOT/"dist/region-reference.svg").write_text(svg)
    print("Built joint geographic reference:",len(regions),"prefecture regions;",", ".join(info["provinceNames"]),"SHA256",info["sha256"])


if __name__=="__main__":
    generate(read_raw_sources(sys.argv[1:]))
