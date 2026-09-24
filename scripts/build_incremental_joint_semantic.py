#!/usr/bin/env python3
"""Build one incremental semantic SVG with joins that own shared borders.

Regional semantic SVGs seed accepted interiors.  Their page-space features are
then dissolved inside an editable collar around every accepted join.  The join,
not either region, owns water and settlement geometry at the common boundary.
Future regions append to semantic-joint-state.json and rebuild the same master.
"""
from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import cairosvg
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "artwork/semantic-joint-state.json"
TILES_PATH = ROOT / "dist/jiangxi-city-tiles.json"
STATE = json.loads(STATE_PATH.read_text(encoding="utf-8"))
MASTER_PATH = ROOT / STATE["masterSvg"]
OUT = MASTER_PATH.parent
MASTER_NAME = MASTER_PATH.name
RENDER_SCALE = int(STATE.get("renderScale", 8))

FILL_CLASS = {
    "#ddcea0": "rural",
    "#c8c3b7": "county",
    "#9da3a1": "metro",
    "#a9c8c5": "water",
    "#79a8b0": "river",
}


def svg_uri(path: Path) -> str:
    # The joint master owns one continuous ground surface.  Regional SVG
    # backgrounds use local gradients/canvases and would otherwise expose a
    # rectangular color seam even when every feature is continuous.
    source = path.read_text()
    source = source.replace(
        '<rect width="1024" height="1024" fill="#f5f1e7"/>',
        '<rect width="1024" height="1024" fill="none"/>',
        1,
    )
    source = re.sub(
        r'(<path\s+d="[^"]+"\s+)fill="url\(#plain\)"',
        r'\1fill="none"',
        source,
        count=1,
    )
    data = base64.b64encode(source.encode()).decode("ascii")
    return f"data:image/svg+xml;base64,{data}"


def rings_from_path(path_text: str):
    """Read the straight-sided area paths emitted by the regional builders."""
    rings = []
    for part in re.findall(r"M(.*?)(?=M|$)", path_text):
        if "Q" in part or "C" in part or "A" in part:
            continue
        nums = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", part)]
        points = list(zip(nums[0::2], nums[1::2]))
        if len(points) >= 3:
            polygon = Polygon(points)
            if polygon.is_valid and polygon.area > 0:
                rings.append(polygon)
    return unary_union(rings).buffer(0) if rings else Polygon()


def path_geometry(path_text: str):
    return rings_from_path(path_text)


def area_path(geometry):
    if geometry.is_empty:
        return ""
    polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms) if isinstance(geometry, MultiPolygon) else []
    chunks = []
    for polygon in polygons:
        rings = [polygon.exterior, *polygon.interiors]
        chunks.extend(
            "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in ring.coords) + " Z"
            for ring in rings
        )
    return " ".join(chunks)


def local_to_page(geometry, bounds):
    x, y, width, height = bounds
    geometry = affinity.scale(geometry, xfact=width / 1024, yfact=height / 1024, origin=(0, 0))
    return affinity.translate(geometry, xoff=x, yoff=y)


def extract_features(svg_path: Path, bounds):
    result = {name: [] for name in FILL_CLASS.values()}
    root = ET.fromstring(svg_path.read_text())
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        semantic_class = FILL_CLASS.get(element.attrib.get("fill", "").lower())
        if not semantic_class:
            continue
        geometry = rings_from_path(element.attrib.get("d", ""))
        if not geometry.is_empty:
            result[semantic_class].append(local_to_page(geometry, bounds))
    return {key: unary_union(value).buffer(0) if value else Polygon() for key, value in result.items()}


def close_feature(geometry, amount):
    if geometry.is_empty or amount <= 0:
        return geometry
    return geometry.buffer(amount, join_style=1).buffer(-amount, join_style=1).buffer(0)


state = STATE
tiles = json.loads(TILES_PATH.read_text())
tile_by_id = {
    tile["id"]: tile for tile in tiles
    if tile["layout"] == "balanced" and tile["id"] in state["regions"]
}

outlines = {region_id: path_geometry(tile_by_id[region_id]["path"]) for region_id in state["acceptedOrder"]}
features = {
    region_id: extract_features(ROOT / state["regions"][region_id]["semanticSvg"], tile_by_id[region_id]["bounds"])
    for region_id in state["acceptedOrder"]
}
accepted_union = unary_union(list(outlines.values())).buffer(0)
min_x, min_y, max_x, max_y = accepted_union.bounds
padding = 2
view = [min_x - padding, min_y - padding, max_x - min_x + padding * 2, max_y - min_y + padding * 2]

joint_layers = {name: [] for name in FILL_CLASS.values()}
join_metadata = []
join_collars = []
ownership_collars = []
for join in state["joins"]:
    left_id, right_id = join["regions"]
    common_border = outlines[left_id].boundary.intersection(outlines[right_id].boundary)
    if common_border.is_empty:
        # Tolerate sub-pixel discrepancies in future project outlines.
        common_border = outlines[left_id].boundary.intersection(outlines[right_id].boundary.buffer(0.03))
    collar = common_border.buffer(join["collarWidthPageUnits"], cap_style=2, join_style=2).intersection(accepted_union)
    if collar.is_empty:
        raise RuntimeError(f"No common border found for {left_id} and {right_id}")
    join_collars.append(collar)
    ownership_collars.append(
        common_border.buffer(join.get("ownershipWidthPageUnits", 3.0), cap_style=2, join_style=2).intersection(accepted_union)
    )

    for semantic_class in joint_layers:
        combined = unary_union([
            features[left_id][semantic_class],
            features[right_id][semantic_class],
        ]).intersection(collar)
        # A feature clipped by either old regional SVG must not retain the
        # administrative edge as a semantic edge.  Continue only the portion
        # that actually reaches the common border, then dissolve it with the
        # opposite side.  Features away from the border remain unchanged.
        continuation = join.get("boundaryContinuationPageUnits", {}).get(semantic_class, 0)
        if continuation > 0:
            touching = combined.intersection(common_border.buffer(0.35))
            if not touching.is_empty:
                combined = unary_union([combined, touching.buffer(continuation, resolution=24)])
        amount = join["featureClosingPageUnits"].get(semantic_class, 0)
        joint_layers[semantic_class].append(close_feature(combined, amount).intersection(collar))

    manual_water = [Polygon(points) for points in join.get("sharedWater", [])]
    if manual_water:
        joint_layers["water"].append(unary_union(manual_water).intersection(accepted_union))
    join_metadata.append({
        "regions": join["regions"],
        "borderLength": round(common_border.length, 3),
        "collarArea": round(collar.area, 3),
    })

joint = {
    key: unary_union(value).buffer(0).intersection(accepted_union) if value else Polygon()
    for key, value in joint_layers.items()
}
joint_collar = unary_union(join_collars).buffer(0)
ownership_collar = unary_union(ownership_collars).buffer(0)
# The dark river cue cannot pass through a manually or automatically joined
# open-water body.  A small inset keeps pale lake water visually uninterrupted.
joint["river"] = joint["river"].difference(joint["water"].buffer(0.18)).buffer(0)

defs = [
    '<linearGradient id="joint-plain" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2e7c5"/><stop offset="1" stop-color="#d5d7a9"/></linearGradient>',
    '<pattern id="joint-farmland" width="1.8" height="1.8" patternUnits="userSpaceOnUse" patternTransform="rotate(18)"><path d="M0 0 V1.8" stroke="#bcae7d" stroke-width="0.25" opacity=".45"/></pattern>',
]
images = []
for region_id in state["acceptedOrder"]:
    tile = tile_by_id[region_id]
    x, y, width, height = tile["bounds"]
    clip_id = f"region-{region_id}"
    accepted_interior = outlines[region_id].difference(ownership_collar).buffer(0)
    defs.append(f'<clipPath id="{clip_id}" clipPathUnits="userSpaceOnUse"><path d="{area_path(accepted_interior)}" fill-rule="evenodd"/></clipPath>')
    images.append(
        f'<image data-region="{region_id}" x="{x}" y="{y}" width="{width}" height="{height}" '
        f'preserveAspectRatio="none" clip-path="url(#{clip_id})" href="{svg_uri(ROOT / state["regions"][region_id]["semanticSvg"])}"/>'
    )

overlay = [
    f'<path data-class="rural" d="{area_path(joint["rural"])}" fill="#ddcea0" opacity=".68" fill-rule="evenodd"/>',
    f'<path data-class="rural-texture" d="{area_path(joint["rural"])}" fill="url(#joint-farmland)" opacity=".52" fill-rule="evenodd"/>',
    f'<path data-class="county" d="{area_path(joint["county"])}" fill="#c8c3b7" opacity=".96" fill-rule="evenodd"/>',
    f'<path data-class="metro" d="{area_path(joint["metro"])}" fill="#9da3a1" opacity=".98" fill-rule="evenodd"/>',
    f'<path data-class="water" d="{area_path(joint["water"])}" fill="#a9c8c5" stroke="#7fa8a8" stroke-width=".1" fill-rule="evenodd"/>',
    f'<path data-class="river" d="{area_path(joint["river"])}" fill="#79a8b0" opacity=".92" fill-rule="evenodd"/>',
]

x, y, width, height = view
metadata = json.dumps({
    "source": "artwork/semantic-joint-state.json",
    "acceptedOrder": state["acceptedOrder"],
    "joins": join_metadata,
    "rule": "accepted interiors plus join-owned shared semantics",
}, ensure_ascii=False)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.3f} {y:.3f} {width:.3f} {height:.3f}" width="{round(width * RENDER_SCALE)}" height="{round(height * RENDER_SCALE)}">
<metadata>{metadata}</metadata>
<defs>{''.join(defs)}</defs>
<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" height="{height:.3f}" fill="#f5f1e7"/>
<path d="{area_path(accepted_union)}" fill="url(#joint-plain)" fill-rule="evenodd"/>
<g id="accepted-regional-interiors">{''.join(images)}</g>
<g id="join-owned-semantics">{''.join(overlay)}</g>
</svg>'''

OUT.mkdir(parents=True, exist_ok=True)
svg_path = OUT / MASTER_NAME
png_path = svg_path.with_suffix(".png")
manifest_path = svg_path.with_suffix(".json")
svg_path.write_text(svg)
cairosvg.svg2png(
    bytestring=svg.encode(),
    write_to=str(png_path),
    output_width=round(width * RENDER_SCALE),
    output_height=round(height * RENDER_SCALE),
)
manifest_path.write_text(json.dumps({
    "masterSvg": str(svg_path.relative_to(ROOT)),
    "previewPng": str(png_path.relative_to(ROOT)),
    "coordinateSystem": state["coordinateSystem"],
    "acceptedOrder": state["acceptedOrder"],
    "joins": join_metadata,
    "regionalExportRule": "crop master in page coordinates; include an external neighbor collar for generation",
}, ensure_ascii=False, indent=2) + "\n")
print({"svg": str(svg_path), "png": str(png_path), "joins": join_metadata, "viewBox": view})
