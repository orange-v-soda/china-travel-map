"""Build a coordinate-anchored, text-free SVG illustration of Nanchang.

Administrative geometry and settlement anchors come from the Nanchang county
GeoJSON. Rivers, lakes, urban extents and elevation come from the existing
Jiangxi project data. The output is deliberately semantic rather than a street
map, but every major mark is tied to geographic coordinates.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "local-data"
OUT = Path(__file__).resolve().parent
COUNTIES = ROOT / "nanchang-counties.geojson"
W = H = 1200
MARGIN = 54


def load_geojson(path: Path):
    return json.loads(path.read_text())


county_fc = load_geojson(COUNTIES)
county_features = county_fc["features"]
county_geoms = [shape(f["geometry"]) for f in county_features]
city = unary_union(county_geoms)
minx, miny, maxx, maxy = city.bounds
mid_lat = (miny + maxy) / 2
cos_lat = math.cos(math.radians(mid_lat))
map_w = (maxx - minx) * cos_lat
map_h = maxy - miny
scale = min((W - 2 * MARGIN) / map_w, (H - 2 * MARGIN) / map_h)
ox = (W - map_w * scale) / 2
oy = (H - map_h * scale) / 2


def xy(lon, lat, z=None):
    if hasattr(lon, "__iter__"):
        return [ox + (float(x) - minx) * cos_lat * scale for x in lon], [oy + (maxy - float(y)) * scale for y in lat]
    return ox + (lon - minx) * cos_lat * scale, oy + (maxy - lat) * scale


def projected(geom):
    return transform(xy, geom)


def ring_path(coords):
    pts = list(coords)
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"


def area_path(geom):
    if geom.is_empty:
        return ""
    parts = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
    chunks = []
    for poly in parts:
        chunks.append(ring_path(poly.exterior.coords))
        chunks.extend(ring_path(r.coords) for r in poly.interiors)
    return " ".join(chunks)


def line_path(geom):
    if geom.is_empty:
        return ""
    parts = [geom] if isinstance(geom, LineString) else list(geom.geoms) if isinstance(geom, MultiLineString) else []
    return " ".join("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in line.coords) for line in parts)


city_svg = projected(city)
county_svg = [projected(g) for g in county_geoms]


def dem_elevation(lon, lat):
    dem_data = dem_elevation.data
    zoom = dem_elevation.zoom
    tx, ty = dem_elevation.origin
    world = 256 * (2 ** zoom)
    px = (lon + 180) / 360 * world - tx * 256
    rad = math.radians(lat)
    py = (1 - math.asinh(math.tan(rad)) / math.pi) / 2 * world - ty * 256
    ix, iy = int(round(px)), int(round(py))
    if 0 <= iy < dem_data.shape[0] and 0 <= ix < dem_data.shape[1]:
        return float(dem_data[iy, ix])
    return 0.0


dem_npz = np.load(DATA / "jiangxi-dem.npz")
dem_elevation.data = dem_npz["elevation"]
dem_elevation.origin = dem_npz["tileOrigin"].tolist()
dem_elevation.zoom = int(dem_npz["zoom"])


def svg_el(tag, attrs, body=""):
    attr = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"<{tag} {attr}>{body}</{tag}>" if body else f"<{tag} {attr}/>"


defs = f"""
<defs>
  <clipPath id="city-clip"><path d="{area_path(city_svg)}" fill-rule="evenodd"/></clipPath>
  <filter id="soft-shadow" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#405147" flood-opacity=".22"/>
  </filter>
  <linearGradient id="plain" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#dce3bd"/><stop offset="1" stop-color="#d5d7a9"/>
  </linearGradient>
</defs>
"""

layers = []
layers.append(svg_el("path", {"d": area_path(city_svg), "fill": "url(#plain)", "fill-rule": "evenodd"}))

# County-level tonal fields keep the administrative structure legible without labels.
county_fills = ["#d8ddb5", "#dfe0b9", "#d5d9ad", "#daddb3", "#d7dab0", "#dfe1b9", "#d9d9aa", "#d5d7ad", "#dfddb0"]
for geom, fill in zip(county_svg, county_fills):
    layers.append(svg_el("path", {"d": area_path(geom), "fill": fill, "fill-rule": "evenodd", "opacity": ".72"}))

# Measured urban extents, subdued so settlement symbols remain dominant.
urban_fc = load_geojson(DATA / "jiangxi-urban_areas.geojson")
for f in urban_fc["features"]:
    g = shape(f["geometry"]).intersection(city)
    if not g.is_empty:
        layers.append(svg_el("path", {"d": area_path(projected(g)), "fill": "#c9b8a1", "opacity": ".30", "fill-rule": "evenodd"}))

# Elevation-tied ridge glyphs: sparse marks, not invented continuous terrain.
ridge_marks = []
for lat in np.arange(miny + .025, maxy, .042):
    for lon in np.arange(minx + .025, maxx, .050):
        p = Point(float(lon), float(lat))
        if not city.contains(p):
            continue
        elev = dem_elevation(float(lon), float(lat))
        if elev < 55:
            continue
        x, y = xy(float(lon), float(lat))
        size = min(16.0, 5.5 + max(0, elev - 55) / 38)
        back = f"M{x-size:.2f},{y+size*.48:.2f} Q{x-size*.30:.2f},{y-size*.80:.2f} {x:.2f},{y-size:.2f} Q{x+size*.40:.2f},{y-size*.34:.2f} {x+size:.2f},{y+size*.48:.2f} Z"
        front = f"M{x-size*.20:.2f},{y-size*.73:.2f} Q{x+size*.15:.2f},{y-size*.15:.2f} {x+size:.2f},{y+size*.48:.2f} L{x:.2f},{y+size*.30:.2f} Z"
        ridge_marks.append(svg_el("path", {"d": back, "fill": "#6f8e68", "opacity": ".80"}))
        ridge_marks.append(svg_el("path", {"d": front, "fill": "#4f745c", "opacity": ".72"}))
layers.extend(ridge_marks)

# Real lakes and wetlands.
lake_fc = load_geojson(DATA / "jiangxi-lakes.geojson")
for f in lake_fc["features"]:
    g = shape(f["geometry"]).intersection(city)
    if not g.is_empty:
        layers.append(svg_el("path", {"d": area_path(projected(g)), "fill": "#77b5c2", "stroke": "#5b98aa", "stroke-width": "1", "fill-rule": "evenodd"}))

# Real river centerlines, filtered by upstream area and drawn in flow hierarchy.
river_fc = load_geojson(DATA / "jiangxi-hydrorivers.geojson")
rivers = []
for f in river_fc["features"]:
    props = f.get("properties", {})
    upland = float(props.get("UPLAND_SKM", 0) or 0)
    if upland < 120:
        continue
    g = shape(f["geometry"]).intersection(city)
    if g.is_empty:
        continue
    width = max(1.0, min(7.5, .65 + math.log10(max(upland, 1)) * 1.30))
    rivers.append((width, projected(g)))
river_draws = [(width, line_path(g)) for width, g in sorted(rivers, key=lambda item: item[0])]
for width, d in river_draws:
    layers.append(svg_el("path", {"d": d, "fill": "none", "stroke": "#eff7f4", "stroke-width": f"{width+2.1:.2f}", "stroke-linecap": "round", "stroke-linejoin": "round", "opacity": ".78"}))
for width, d in river_draws:
    layers.append(svg_el("path", {"d": d, "fill": "none", "stroke": "#579bad", "stroke-width": f"{width:.2f}", "stroke-linecap": "round", "stroke-linejoin": "round"}))


def settlement_cluster(lon, lat, scale_factor, seed, core=False):
    rng = random.Random(seed)
    x, y = xy(lon, lat)
    pieces = []
    radius = 20 * scale_factor
    pieces.append(svg_el("ellipse", {"cx": f"{x:.2f}", "cy": f"{y+2:.2f}", "rx": f"{radius:.2f}", "ry": f"{radius*.58:.2f}", "fill": "#d9c6aa", "opacity": ".72"}))
    count = 13 if core else 11
    for i in range(count):
        dx = rng.uniform(-radius*.72, radius*.72)
        dy = rng.uniform(-radius*.38, radius*.38)
        bw = rng.uniform(4.2, 7.4) * scale_factor
        bh = rng.uniform(5.5, 11.0) * scale_factor
        tone = rng.choice(["#b9785d", "#c88a65", "#9e7867", "#d09a70"])
        pieces.append(svg_el("rect", {"x": f"{x+dx-bw/2:.2f}", "y": f"{y+dy-bh:.2f}", "width": f"{bw:.2f}", "height": f"{bh:.2f}", "rx": "1.1", "fill": tone, "stroke": "#f4ebd8", "stroke-width": ".8"}))
    return f'<g filter="url(#soft-shadow)">{"".join(pieces)}</g>'


# Every county-level unit gets an explicit settlement anchor at its published center.
for f in county_features:
    props = f["properties"]
    lon, lat = props["center"]
    adcode = int(props["adcode"])
    core = adcode in {360102, 360103, 360104, 360111, 360112, 360113}
    factor = 0.96 if core else 1.42
    layers.append(settlement_cluster(lon, lat, factor, adcode, core=core))

# Two coordinate-anchored landmarks, deliberately smaller than settlement clusters.
def pavilion(lon, lat):
    x, y = xy(lon, lat)
    return f'''<g transform="translate({x:.2f} {y:.2f})" filter="url(#soft-shadow)">
      <path d="M-10 0 L0 -6 L10 0 L7 2 L-7 2 Z M-7 -5 L0 -10 L7 -5 L5 -3 L-5 -3 Z" fill="#a94e38" stroke="#f2d9b5" stroke-width="1"/>
      <path d="M-5 2 V10 H5 V2 M-2 2 V10 M2 2 V10" fill="#c88958" stroke="#6e4f3d" stroke-width="1.1"/>
    </g>'''


def ferris_wheel(lon, lat):
    x, y = xy(lon, lat)
    return f'''<g transform="translate({x:.2f} {y:.2f})" fill="none" stroke="#8b6f60" stroke-width="1.2" opacity=".92">
      <circle r="9" fill="#edf0dc"/><circle r="1.6" fill="#b46d56"/>
      <path d="M0 -9 V9 M-9 0 H9 M-6.4 -6.4 L6.4 6.4 M6.4 -6.4 L-6.4 6.4 M-6 13 L0 1 L6 13"/>
    </g>'''


layers.append(pavilion(115.885, 28.684))
layers.append(ferris_wheel(115.80, 28.61))

# County boundaries and prefecture outline sit above all art.
for geom in county_svg:
    layers.append(svg_el("path", {"d": area_path(geom), "fill": "none", "stroke": "#eee8d5", "stroke-width": "1.35", "stroke-linejoin": "round", "opacity": ".95"}))
layers.append(svg_el("path", {"d": area_path(city_svg), "fill": "none", "stroke": "#4f675d", "stroke-width": "4.2", "stroke-linejoin": "round", "fill-rule": "evenodd"}))

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
{defs}
<rect width="{W}" height="{H}" fill="#f5f1e6"/>
<g clip-path="url(#city-clip)">{"".join(layers)}</g>
</svg>
'''
(OUT / "nanchang-semantic.svg").write_text(svg)

manifest = {
    "title": "Nanchang semantic SVG prototype",
    "textFree": True,
    "countyUnitCount": len(county_features),
    "settlementAnchors": [
        {"adcode": f["properties"]["adcode"], "name": f["properties"]["name"], "coordinate": f["properties"]["center"]}
        for f in county_features
    ],
    "landmarks": [
        {"name": "Tengwang Pavilion", "coordinate": [115.885, 28.684]},
        {"name": "Star of Nanchang", "coordinate": [115.80, 28.61]},
    ],
    "sources": {
        "countyGeometry": "DataV GeoAtlas 360100_full.json snapshot",
        "hydrology": "repository Jiangxi HydroRIVERS and Natural Earth lake snapshots",
        "urban": "repository Natural Earth urban-area snapshot",
        "terrain": "repository DEM tile mosaic",
    },
}
(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(f"wrote {OUT / 'nanchang-semantic.svg'}")
