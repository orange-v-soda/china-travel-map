"""Map real Jiujiang geography into the project's accepted balanced outline.

The project's existing per-triangle east->balanced warp is authoritative for
the final silhouette. Real hydrology, DEM samples, and county-seat anchors are
mapped through those same triangles. The generated guide is only a visual
reference; the mask restores exact geometry after image generation. Construction
anchors are never published or composited into the final artwork.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import transform, unary_union


HERE = Path(__file__).resolve().parent
if (HERE / "dist" / "jiangxi-art-data.js").exists():
    # Repository-root installation.
    WORK = HERE
    DATA = WORK / "data"
    PROJECT = WORK / "dist"
    COUNTIES = DATA / "jiujiang-counties-source.geojson"
    OUT = PROJECT / "assets" / "jiujiang"
else:
    # Standalone workspace prototype.
    WORK = HERE.parents[1]
    DATA = WORK / "local-data"
    PROJECT = WORK / "project-main"
    COUNTIES = WORK / "jiujiang-counties.geojson"
    OUT = HERE
SIZE = 1024
MARGIN = 56
OUT.mkdir(parents=True, exist_ok=True)


def load_geojson(path: Path):
    return json.loads(path.read_text())


def load_js_json(path: Path):
    text = path.read_text()
    return json.loads(text.split(" = ", 1)[1].rsplit(";", 1)[0])


def path_geometry(path_text: str):
    polygons = []
    for subpath in re.findall(r"M(.*?)(?=M|$)", path_text):
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", subpath)]
        pts = list(zip(nums[0::2], nums[1::2]))
        if len(pts) >= 3:
            polygons.append(Polygon(pts))
    return unary_union(polygons)


art = load_js_json(PROJECT / "jiangxi-art-data.js")
city_record = next(c for c in art["cities"] if c["id"] == "360400")
east_outline = path_geometry(city_record["east"])
balanced = path_geometry(city_record["balanced"])
cells = [c for c in art["cells"] if c["id"] == "360400"]
cell_records = []
for cell in cells:
    source = Polygon(cell["from"])
    matrix = cell["matrix"]
    shapely_matrix = [matrix[0], matrix[2], matrix[1], matrix[3], matrix[4], matrix[5]]
    cell_records.append((source, shapely_matrix))

projection = json.loads((DATA / "jiangxi-projection.json").read_text())
county_fc = load_geojson(COUNTIES)
county_union = unary_union([shape(f["geometry"]) for f in county_fc["features"]])


def geographic_to_east(lon, lat, z=None):
    if hasattr(lon, "__iter__"):
        xs, ys = [], []
        for x, y in zip(lon, lat):
            px, py = geographic_to_east(float(x), float(y))
            xs.append(px)
            ys.append(py)
        return xs, ys
    x = math.radians(lon)
    y = -math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return projection["dx"] + (x - projection["left"]) * projection["scale"], projection["dy"] + (y - projection["top"]) * projection["scale"]


# First fit the complete real Jiujiang extent into the project's schematic
# east-outline box. This retains county-seat relative positions while ensuring
# every anchor lies inside the project's accepted city footprint.
real_projected = transform(geographic_to_east, county_union)
rminx, rminy, rmaxx, rmaxy = real_projected.bounds
eminx, eminy, emaxx, emaxy = east_outline.bounds
fit_x = (emaxx - eminx) / (rmaxx - rminx)
fit_y = (emaxy - eminy) / (rmaxy - rminy)
fit_matrix = [fit_x, 0, 0, fit_y, eminx - rminx * fit_x, eminy - rminy * fit_y]


def warp_geometry(geom):
    east = affinity.affine_transform(transform(geographic_to_east, geom), fit_matrix)
    pieces = []
    for source, matrix in cell_records:
        piece = east.intersection(source.buffer(1e-7))
        if not piece.is_empty:
            pieces.append(affinity.affine_transform(piece, matrix))
    return unary_union(pieces) if pieces else Polygon()


def warp_point(lon, lat):
    x, y = geographic_to_east(lon, lat)
    x, y = fit_matrix[0] * x + fit_matrix[4], fit_matrix[3] * y + fit_matrix[5]
    point = Point(x, y)
    candidates = [(source.distance(point), source, matrix) for source, matrix in cell_records]
    _, _, matrix = min(candidates, key=lambda item: item[0])
    a, b, d, e, xoff, yoff = matrix
    return a * x + b * y + xoff, d * x + e * y + yoff


minx, miny, maxx, maxy = balanced.bounds
scale = min((SIZE - 2 * MARGIN) / (maxx - minx), (SIZE - 2 * MARGIN) / (maxy - miny))
offset_x = (SIZE - (maxx - minx) * scale) / 2
offset_y = (SIZE - (maxy - miny) * scale) / 2


def canvas_xy(x, y, z=None):
    if hasattr(x, "__iter__"):
        return [offset_x + (float(px) - minx) * scale for px in x], [offset_y + (float(py) - miny) * scale for py in y]
    return offset_x + (x - minx) * scale, offset_y + (y - miny) * scale


def canvas_geometry(geom):
    return transform(canvas_xy, geom)


balanced_canvas = canvas_geometry(balanced)


def ring_path(coords):
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in coords) + " Z"


def area_path(geom):
    if geom.is_empty:
        return ""
    parts = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
    return " ".join(ring_path(poly.exterior.coords) + " " + " ".join(ring_path(r.coords) for r in poly.interiors) for poly in parts)


def line_path(geom):
    if geom.is_empty:
        return ""
    parts = [geom] if isinstance(geom, LineString) else list(geom.geoms) if isinstance(geom, MultiLineString) else []
    return " ".join("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in line.coords) for line in parts)


clip_path = area_path(balanced_canvas)
defs = f'''<defs>
  <clipPath id="clip"><path d="{clip_path}" fill-rule="evenodd"/></clipPath>
  <linearGradient id="plain" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2e7c5"/><stop offset="1" stop-color="#d5d7a9"/></linearGradient>
  <pattern id="farmland" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">
    <path d="M0 0 V14" stroke="#bcae7d" stroke-width="2" opacity=".45"/>
  </pattern>
</defs>'''

base = [f'<path d="{clip_path}" fill="url(#plain)" fill-rule="evenodd"/>']

# DEM-tied hill and mountain marks.
dem_npz = np.load(DATA / "jiangxi-dem.npz")
dem = dem_npz["elevation"]
tile_x, tile_y = dem_npz["tileOrigin"].tolist()
zoom = int(dem_npz["zoom"])


def elevation(lon, lat):
    world = 256 * (2 ** zoom)
    px = (lon + 180) / 360 * world - tile_x * 256
    py = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * world - tile_y * 256
    ix, iy = int(round(px)), int(round(py))
    return float(dem[iy, ix]) if 0 <= iy < dem.shape[0] and 0 <= ix < dem.shape[1] else 0


for lat in np.arange(county_union.bounds[1] + .025, county_union.bounds[3], .045):
    for lon in np.arange(county_union.bounds[0] + .025, county_union.bounds[2], .052):
        if not county_union.contains(Point(float(lon), float(lat))):
            continue
        elev = elevation(float(lon), float(lat))
        if elev < 58:
            continue
        x, y = canvas_xy(*warp_point(float(lon), float(lat)))
        size = min(18, 7 + (elev - 58) / 35)
        base.append(f'<path d="M{x-size:.2f},{y+size*.48:.2f} Q{x-size*.30:.2f},{y-size*.80:.2f} {x:.2f},{y-size:.2f} Q{x+size*.42:.2f},{y-size*.30:.2f} {x+size:.2f},{y+size*.48:.2f} Z" fill="#70906c" opacity=".76"/>')
        base.append(f'<path d="M{x-size*.20:.2f},{y-size*.72:.2f} Q{x+size*.15:.2f},{y-size*.12:.2f} {x+size:.2f},{y+size*.48:.2f} L{x:.2f},{y+size*.28:.2f} Z" fill="#4f755e" opacity=".70"/>')

# Lakes mapped through the project's exact triangle warp.
for feature in load_geojson(DATA / "jiangxi-lakes.geojson")["features"]:
    mapped = canvas_geometry(warp_geometry(shape(feature["geometry"])))
    if not mapped.is_empty:
        d = area_path(mapped)
        # Water is a positional constraint, not a request to expand the whole
        # surrounding wetland into open water. Keep it pale and subordinate.
        base.append(f'<path d="{d}" fill="#a9c8c5" stroke="#7fa8a8" stroke-width="0.8" fill-rule="evenodd"/>')

# Rivers mapped through the same warp. They are included in the guide only.
river_draws = []
for feature in load_geojson(DATA / "jiangxi-hydrorivers.geojson")["features"]:
    upland = float(feature.get("properties", {}).get("UPLAND_SKM", 0) or 0)
    if upland < 220:
        continue
    mapped = canvas_geometry(warp_geometry(shape(feature["geometry"])))
    if mapped.is_empty:
        continue
    width = max(1.0, min(5.8, .45 + math.log10(max(upland, 1)) * 1.05))
    river_draws.append((width, line_path(mapped)))


# Settlement semantics are continuous density regions, not miniature buildings.
# Their shape, palette, and texture describe the settlement hierarchy to the
# image model while county centers remain recorded as geographic metadata.
anchors = []
core_points = []
county_points = []
for feature in county_fc["features"]:
    props = feature["properties"]
    lon, lat = props["center"]
    adcode = int(props["adcode"])
    core = adcode in {360402, 360403, 360404}
    point = list(canvas_xy(*warp_point(lon, lat)))
    (core_points if core else county_points).append(Point(*point))
    anchors.append({"adcode": adcode, "name": props["name"], "coordinate": [lon, lat], "canvas": point})


def organic_zone(points, radius, xscale=1.0, yscale=1.0, merge=0):
    shapes = [affinity.scale(point.buffer(radius, resolution=32), xfact=xscale, yfact=yscale, origin=point) for point in points]
    zone = unary_union(shapes)
    if merge:
        zone = zone.buffer(merge, resolution=24).buffer(-merge * .55, resolution=24)
    return zone.intersection(balanced_canvas)


all_points = core_points + county_points
rural_zone = organic_zone(all_points, 55, 1.25, .72, 9)
county_zone = organic_zone(county_points, 21, 1.20, .70, 2)
metro_zone = organic_zone(core_points, 27, 1.20, .76, 12)

# Draw broad, low-density farmland first, then progressively darker urban areas.
base.append(f'<path d="{area_path(rural_zone)}" fill="#ddcea0" opacity=".42" fill-rule="evenodd"/>')
base.append(f'<path d="{area_path(rural_zone)}" fill="url(#farmland)" opacity=".46" fill-rule="evenodd"/>')
base.append(f'<path d="{area_path(county_zone)}" fill="#c8c3b7" stroke="#9f9b91" stroke-width="1.4" opacity=".76" fill-rule="evenodd"/>')
base.append(f'<path d="{area_path(metro_zone)}" fill="#9da3a1" stroke="#747c7b" stroke-width="1.8" opacity=".84" fill-rule="evenodd"/>')

# Keep the constrained river network legible above settlement-density regions.
for width, d in sorted(river_draws):
    base.append(f'<path d="{d}" fill="none" stroke="#eef3ec" stroke-width="{width+1.0:.2f}" stroke-linecap="round" stroke-linejoin="round" opacity=".72"/>')
    base.append(f'<path d="{d}" fill="none" stroke="#6f9fa7" stroke-width="{width:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')


def landmark_marker(lon, lat):
    x, y = canvas_xy(*warp_point(lon, lat))
    return f'''<g transform="translate({x:.2f} {y:.2f})">
      <circle r="7" fill="#fff8df" stroke="#8f302f" stroke-width="2"/>
      <circle r="2.6" fill="#b63f38"/>
      <path d="M0 -11 V-7 M0 7 V11 M-11 0 H-7 M7 0 H11" stroke="#8f302f" stroke-width="1.5" stroke-linecap="round"/>
    </g>'''


# One relatively independent map region keeps at most one landmark: Mount Lu.
base.append(landmark_marker(115.9667, 29.5450))

outline = f'<path d="{clip_path}" fill="none" stroke="#4e675d" stroke-width="5" stroke-linejoin="round" fill-rule="evenodd"/>'

guide = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">{defs}
<rect width="{SIZE}" height="{SIZE}" fill="#f5f1e7"/>
<g clip-path="url(#clip)">{"".join(base)}</g>{outline}</svg>'''
mask_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}"><rect width="{SIZE}" height="{SIZE}" fill="black"/><path d="{clip_path}" fill="white" fill-rule="evenodd"/></svg>'''

(OUT / "jiujiang-semantic.svg").write_text(guide)
(OUT / "jiujiang-mask.svg").write_text(mask_svg)
(OUT / "manifest.json").write_text(json.dumps({
    "projectOutline": "main / MAP_DATA region 360400 / balanced",
    "warp": "main / JIANGXI_ART cells for city 360400",
    "textFree": True,
    "anchors": anchors,
    "settlementSemantics": {
        "regionalProfile": "south bank of the Yangtze / northwest Poyang Lake / Mount Lu and western Jiujiang hills",
        "wilderness": {"visual": "untinted base", "generation": "forested western hills, Mount Lu highland, lake wetlands, or open terrain according to elevation and hydrology"},
        "rural": {"visual": "light ochre farmland texture", "generation": "Jiangnan paddy fields, lake-edge dikes, water-linked villages, and compact farm plots"},
        "countyTown": {"visual": "warm light-gray compact region", "generation": "compact northern Jiangxi county town with gray-white fabric, tiled roofs, and river- or lake-oriented streets"},
        "metropolitan": {"visual": "medium cool-gray continuous region", "generation": "dense gray-white Jiujiang urban fabric on the south bank of the Yangtze; semantic gray does not prescribe roof color"},
    },
    "waterSemantics": {
        "openWaterExpansionAllowed": False,
        "wetlandDefaultRendering": "land-dominant",
        "generation": "Blue water shapes are the maximum open-water extent. Render adjacent wetlands primarily as fields, meadow, reed strips, dikes, bars, and tree belts; reject continuous marsh expansion.",
    },
    "landmarks": [
        {"marker": "landmark-1", "name": "Mount Lu", "coordinate": [115.9667, 29.5450], "canvas": list(canvas_xy(*warp_point(115.9667, 29.5450))), "description": "Mount Lu highland south of Jiujiang's urban core and west of Poyang Lake; render as the single emphasized natural landmark, integrated into the mountain mass rather than as a building."},
    ],
}, ensure_ascii=False, indent=2) + "\n")
print({"cells": len(cells), "anchors": len(anchors), "outlineBounds": balanced.bounds})
