"""Build the Fuzhou semantic guide in the project's balanced outline.

The balanced project geometry is authoritative. Real-world county-seat,
hydrology and elevation data are mapped into that silhouette through the same
east-to-balanced cells used by the page. The SVG contains no visible labels.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DIST = ROOT / "dist"
OUT = DIST / "assets" / "fuzhou"
SIZE = 1024
REGION_ID = "361000"
OUT.mkdir(parents=True, exist_ok=True)


def load_js_json(path: Path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text.split(" = ", 1)[1].rsplit(";", 1)[0])


def path_geometry(path_text: str):
    polygons = []
    for subpath in re.findall(r"M(.*?)(?=M|$)", path_text):
        values = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", subpath)]
        points = list(zip(values[0::2], values[1::2]))
        if len(points) >= 3:
            polygons.append(Polygon(points))
    return unary_union(polygons).buffer(0)


def area_path(geometry):
    if geometry.is_empty:
        return ""
    polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms) if isinstance(geometry, MultiPolygon) else []
    chunks = []
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            chunks.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in ring.coords) + " Z")
    return " ".join(chunks)


art = load_js_json(DIST / "jiangxi-art-data.js")
city = next(item for item in art["cities"] if item["id"] == REGION_ID)
east_outline = path_geometry(city["east"])
balanced = path_geometry(city["balanced"])
cells = [item for item in art["cells"] if item["id"] == REGION_ID]
cell_records = []
for cell in cells:
    matrix = cell["matrix"]
    cell_records.append((
        Polygon(cell["from"]),
        [matrix[0], matrix[2], matrix[1], matrix[3], matrix[4], matrix[5]],
    ))

projection = json.loads((DATA / "jiangxi-projection.json").read_text(encoding="utf-8"))


def geographic_to_east(lon, lat, z=None):
    if hasattr(lon, "__iter__"):
        points = [geographic_to_east(float(x), float(y)) for x, y in zip(lon, lat)]
        return [point[0] for point in points], [point[1] for point in points]
    x = math.radians(lon)
    y = -math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return (
        projection["dx"] + (x - projection["left"]) * projection["scale"],
        projection["dy"] + (y - projection["top"]) * projection["scale"],
    )


# Official municipal extent: 115°35′–117°18′ E, 26°29′–28°30′ N.
real_extent = box(115 + 35 / 60, 26 + 29 / 60, 117 + 18 / 60, 28 + 30 / 60)
projected_extent = transform(geographic_to_east, real_extent)
rminx, rminy, rmaxx, rmaxy = projected_extent.bounds
eminx, eminy, emaxx, emaxy = east_outline.bounds
fit_x = (emaxx - eminx) / (rmaxx - rminx)
fit_y = (emaxy - eminy) / (rmaxy - rminy)
fit_matrix = [fit_x, 0, 0, fit_y, eminx - rminx * fit_x, eminy - rminy * fit_y]


def warp_geometry(geometry):
    source = affinity.affine_transform(transform(geographic_to_east, geometry), fit_matrix)
    pieces = []
    for cell, matrix in cell_records:
        piece = source.intersection(cell.buffer(1e-7))
        if not piece.is_empty:
            pieces.append(affinity.affine_transform(piece, matrix))
    return unary_union(pieces) if pieces else Polygon()


def warp_point(lon, lat):
    x, y = geographic_to_east(lon, lat)
    x, y = fit_matrix[0] * x + fit_matrix[4], fit_matrix[3] * y + fit_matrix[5]
    point = Point(x, y)
    _, _, matrix = min(
        ((cell.distance(point), cell, matrix) for cell, matrix in cell_records),
        key=lambda item: item[0],
    )
    a, b, d, e, xoff, yoff = matrix
    return a * x + b * y + xoff, d * x + e * y + yoff


tile_x, tile_y, tile_x1, tile_y1 = balanced.bounds
tile_width, tile_height = tile_x1 - tile_x, tile_y1 - tile_y


def canvas_xy(x, y, z=None):
    if hasattr(x, "__iter__"):
        return (
            [(float(px) - tile_x) / tile_width * SIZE for px in x],
            [(float(py) - tile_y) / tile_height * SIZE for py in y],
        )
    return (x - tile_x) / tile_width * SIZE, (y - tile_y) / tile_height * SIZE


def canvas_geometry(geometry):
    return transform(canvas_xy, geometry)


balanced_canvas = canvas_geometry(balanced)
clip_path = area_path(balanced_canvas)
global_ppu = 2048 / 175
local_ppu = math.sqrt((SIZE / tile_width) * (SIZE / tile_height))
semantic_scale = local_ppu / global_ppu

defs = f'''<defs>
  <clipPath id="clip"><path d="{clip_path}" fill-rule="evenodd"/></clipPath>
  <linearGradient id="plain" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2e7c5"/><stop offset="1" stop-color="#d5d7a9"/></linearGradient>
  <pattern id="farmland" width="{14 * semantic_scale:.2f}" height="{14 * semantic_scale:.2f}" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">
    <path d="M0 0 V{14 * semantic_scale:.2f}" stroke="#bcae7d" stroke-width="{2 * semantic_scale:.2f}" opacity=".45"/>
  </pattern>
</defs>'''
layers = [f'<path d="{clip_path}" fill="url(#plain)" fill-rule="evenodd"/>']

# Elevation semantics: eastern Wuyi foothills and southern/western uplands,
# leaving the central Fu River basin visually open.
dem_npz = np.load(DATA / "jiangxi-dem.npz")
dem = dem_npz["elevation"]
origin_x, origin_y = dem_npz["tileOrigin"].tolist()
zoom = int(dem_npz["zoom"])


def elevation(lon, lat):
    world = 256 * (2 ** zoom)
    px = (lon + 180) / 360 * world - origin_x * 256
    py = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * world - origin_y * 256
    ix, iy = int(round(px)), int(round(py))
    return float(dem[iy, ix]) if 0 <= iy < dem.shape[0] and 0 <= ix < dem.shape[1] else 0


for lat in np.arange(real_extent.bounds[1] + .04, real_extent.bounds[3], .075):
    for lon in np.arange(real_extent.bounds[0] + .04, real_extent.bounds[2], .08):
        height = elevation(float(lon), float(lat))
        if height < 105:
            continue
        x, y = canvas_xy(*warp_point(float(lon), float(lat)))
        if not balanced_canvas.contains(Point(x, y)):
            continue
        size = min(18, 6.5 + (height - 105) / 42) * semantic_scale
        layers.append(f'<path d="M{x-size:.2f},{y+size*.48:.2f} Q{x-size*.30:.2f},{y-size*.80:.2f} {x:.2f},{y-size:.2f} Q{x+size*.42:.2f},{y-size*.30:.2f} {x+size:.2f},{y+size*.48:.2f} Z" fill="#70906c" opacity=".76"/>')
        layers.append(f'<path d="M{x-size*.20:.2f},{y-size*.72:.2f} Q{x+size*.15:.2f},{y-size*.12:.2f} {x+size:.2f},{y+size*.48:.2f} L{x:.2f},{y+size*.28:.2f} Z" fill="#4f755e" opacity=".70"/>')

# County-scale anchors. Coordinates are geographic inputs; only their warped
# density regions are visible in the text-free guide.
anchors = [
    (361002, "临川区", 116.358, 27.983, True),
    (361003, "东乡区", 116.603, 28.247, False),
    (361021, "南城县", 116.637, 27.555, False),
    (361022, "黎川县", 116.907, 27.282, False),
    (361023, "南丰县", 116.525, 27.218, False),
    (361024, "崇仁县", 116.061, 27.765, False),
    (361025, "乐安县", 115.838, 27.428, False),
    (361026, "宜黄县", 116.222, 27.546, False),
    (361027, "金溪县", 116.755, 27.919, False),
    (361028, "资溪县", 117.061, 27.706, False),
    (361030, "广昌县", 116.325, 26.837, False),
]
anchor_records = []
core_points, county_points = [], []
for adcode, name, lon, lat, core in anchors:
    canvas = list(canvas_xy(*warp_point(lon, lat)))
    point = Point(*canvas)
    (core_points if core else county_points).append(point)
    anchor_records.append({"adcode": adcode, "name": name, "coordinate": [lon, lat], "canvas": canvas})


def organic_zone(points, radius, xscale=1.0, yscale=1.0, merge=0):
    shapes = [affinity.scale(point.buffer(radius, resolution=32), xfact=xscale, yfact=yscale, origin=point) for point in points]
    zone = unary_union(shapes)
    if merge:
        zone = zone.buffer(merge, resolution=24).buffer(-merge * .55, resolution=24)
    return zone.intersection(balanced_canvas)


all_points = core_points + county_points
rural = organic_zone(all_points, 58 * semantic_scale, 1.32, .72, 8 * semantic_scale)
county = organic_zone(county_points, 20 * semantic_scale, 1.20, .70, 2 * semantic_scale)
metro = organic_zone(core_points, 31 * semantic_scale, 1.38, .78, 10 * semantic_scale)
layers.append(f'<path d="{area_path(rural)}" fill="#ddcea0" opacity=".44" fill-rule="evenodd"/>')
layers.append(f'<path d="{area_path(rural)}" fill="url(#farmland)" opacity=".48" fill-rule="evenodd"/>')
layers.append(f'<path d="{area_path(county)}" fill="#c8c3b7" opacity=".88" fill-rule="evenodd"/>')
layers.append(f'<path d="{area_path(metro)}" fill="#9da3a1" opacity=".94" fill-rule="evenodd"/>')

# Major-water-only topology. The primary Fu River is authored from its known
# south-to-north sequence (Guangchang–Nanfeng–Nancheng–Linchuan), with only two
# tributary cues. This avoids turning the full HydroRIVERS inventory into a
# visually dominant marsh/stream mesh.
river_specs = [
    ([(116.32, 26.78), (116.38, 26.92), (116.50, 27.18), (116.62, 27.55),
      (116.48, 27.78), (116.36, 27.98), (116.30, 28.26), (116.25, 28.50)], 4.2),
    ([(116.91, 27.30), (116.75, 27.57), (116.64, 27.78), (116.36, 27.98)], 2.5),
    ([(115.84, 27.43), (116.06, 27.76), (116.36, 27.98)], 2.2),
]
river_surfaces = []
for coordinates, width in river_specs:
    mapped = canvas_geometry(warp_geometry(LineString(coordinates))).intersection(balanced_canvas)
    if not mapped.is_empty:
        river_surfaces.append(mapped.buffer(width * semantic_scale / 2, cap_style=1, join_style=1))
water = unary_union(river_surfaces).buffer(0).intersection(balanced_canvas) if river_surfaces else Polygon()
layers.append(f'<path d="{area_path(water)}" fill="#a9c8c5" stroke="#7fa8a8" stroke-width="{.7 * semantic_scale:.2f}" fill-rule="evenodd"/>')
layers.append(f'<path d="{area_path(water)}" fill="#79a8b0" opacity=".82" fill-rule="evenodd"/>')


def landmark_marker(lon, lat):
    x, y = canvas_xy(*warp_point(lon, lat))
    radius = 7 * semantic_scale
    return f'''<g transform="translate({x:.2f} {y:.2f})" data-landmark="wenchangli">
      <circle r="{radius:.2f}" fill="#fff8df" stroke="#8f302f" stroke-width="{2 * semantic_scale:.2f}"/>
      <circle r="{2.6 * semantic_scale:.2f}" fill="#b63f38"/>
    </g>'''


# Wenchangli is the one emphasized landmark, placed within the Linchuan core.
layers.append(landmark_marker(116.356, 27.988))

guide = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">{defs}
<rect width="{SIZE}" height="{SIZE}" fill="#f5f1e7"/>
<g clip-path="url(#clip)" data-semantic="target-region">{"".join(layers)}</g></svg>'''
mask = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}"><rect width="{SIZE}" height="{SIZE}" fill="black"/><path d="{clip_path}" fill="white" fill-rule="evenodd"/></svg>'''

(OUT / "fuzhou-semantic.svg").write_text(guide, encoding="utf-8")
(OUT / "fuzhou-mask.svg").write_text(mask, encoding="utf-8")
(OUT / "manifest.json").write_text(json.dumps({
    "projectOutline": "main / JIANGXI_ART region 361000 / balanced",
    "warp": "main / JIANGXI_ART cells for city 361000",
    "textFree": True,
    "anchors": anchor_records,
    "settlementSemantics": {
        "regionalProfile": "Fu River basin with eastern Wuyi foothills and southern/western uplands",
        "wilderness": "untinted dry land, forest or mountains according to elevation",
        "rural": "compact Jiangnan paddy and citrus-growing belts around county seats",
        "countyTown": "compact gray-white county fabric only inside light-gray regions",
        "metropolitan": "continuous neutral-gray Fuzhou/Linchuan urban core",
    },
    "waterSemantics": {
        "topology": "unified-major-river-surface",
        "openWaterExpansionAllowed": False,
        "riverStrokeInsideLakeAllowed": False,
        "generation": "Blue is the maximum water extent; every non-blue pixel is dry land.",
    },
    "landmarks": [{
        "marker": "landmark-1",
        "name": "文昌里历史文化街区",
        "coordinate": [116.356, 27.988],
        "canvas": list(canvas_xy(*warp_point(116.356, 27.988))),
        "description": "A single compact traditional riverside street-and-courtyard cluster within the central urban area; no oversized gate, pagoda, or text.",
    }],
    "generationViewport": {
        "coordinateSystem": "balanced-page-space",
        "bounds": [tile_x, tile_y, tile_width, tile_height],
        "rasterSize": [SIZE, SIZE],
        "globalPixelsPerPageUnit": global_ppu,
        "localPixelsPerPageUnit": local_ppu,
        "semanticScale": semantic_scale,
        "neighborContext": "360100 / accepted Nanchang v6 artwork",
    },
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print({"cells": len(cells), "anchors": len(anchors), "outlineBounds": balanced.bounds})
