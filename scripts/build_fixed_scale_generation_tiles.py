#!/usr/bin/env python3
"""Build fixed-size, fixed-scale generation windows for a balanced city path.

Every output window is 2048 px square and covers the same 175 x 175 units in
balanced page space. Large regions therefore use multiple overlapping windows
instead of changing scale. Masks are always rendered directly from the current
balanced path used by the page; legacy 1024-space masks are never reused.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import re
from pathlib import Path

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "artwork/fixed-scale-generation.json"
ART_DATA = ROOT / "dist/jiangxi-art-data.js"
TILE_MANIFEST = ROOT / "dist/jiangxi-city-tiles.json"
WORKFLOW_DIR = ROOT / "artwork/workflows"


def load_workflows() -> dict[str, dict]:
    workflows = {}
    for path in WORKFLOW_DIR.glob("*.json"):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        region = workflow.get("region", {})
        region_id = region.get("id")
        if region_id:
            workflows[region_id] = workflow
    return workflows


def load_art_data() -> dict:
    text = ART_DATA.read_text(encoding="utf-8").strip()
    prefix = "const JIANGXI_ART = "
    if not text.startswith(prefix) or not text.endswith(";"):
        raise ValueError(f"unexpected data wrapper: {ART_DATA}")
    return json.loads(text[len(prefix):-1])


def path_bounds(path_text: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", path_text)]
    xs, ys = values[0::2], values[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def axis_origins(low: float, high: float, span: float, margin: float, overlap: float) -> list[float]:
    covered_low = low - margin
    covered_high = high + margin
    required = covered_high - covered_low
    if required <= span:
        return [(low + high - span) / 2]
    count = math.ceil((required - overlap) / (span - overlap))
    count = max(2, count)
    last = covered_high - span
    step = (last - covered_low) / (count - 1)
    return [covered_low + index * step for index in range(count)]


def data_uri(path: Path) -> str:
    media_type = "image/webp" if path.suffix.lower() == ".webp" else "image/png"
    return f"data:{media_type};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render_png(svg: str, output: Path, size: int) -> None:
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(output),
        output_width=size,
        output_height=size,
    )


def intersection(a: list[float], b: list[float]) -> list[float] | None:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return None
    return [left, top, right - left, bottom - top]


def owned_overlap(previous: list[float], current: list[float], fraction: float) -> list[float] | None:
    """Return the current window's immutable share of an earlier overlap."""
    overlap = intersection(previous, current)
    if overlap is None:
        return None
    ox, oy, ow, oh = overlap
    px, py, pw, ph = previous
    cx, cy, cw, ch = current
    delta_x = (cx + cw / 2) - (px + pw / 2)
    delta_y = (cy + ch / 2) - (py + ph / 2)
    if abs(delta_x) >= abs(delta_y):
        owned_width = ow * fraction
        return [ox, oy, owned_width, oh] if delta_x >= 0 else [ox + ow - owned_width, oy, owned_width, oh]
    owned_height = oh * fraction
    return [ox, oy, ow, owned_height] if delta_y >= 0 else [ox, oy + oh - owned_height, ow, owned_height]


def main() -> None:
    workflows = load_workflows()
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=sorted(workflows))
    parser.add_argument(
        "--neighbor-art",
        action="append",
        default=[],
        metavar="REGION_ID=IMAGE",
        help="accepted neighboring raster to place inside its canonical balanced path",
    )
    parser.add_argument(
        "--accepted-window",
        action="append",
        default=[],
        metavar="INDEX=IMAGE",
        help="accepted earlier full-window result to lock into later overlapping windows",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    workflow = workflows[args.target]
    name = workflow["region"]["slug"]
    joint_svg = ROOT / workflow["artifacts"]["jointSemanticSvg"]

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    size = int(config["canvasPixels"][0])
    span_x, span_y = map(float, config["worldSpan"])
    margin = float(config["outerMarginPageUnits"])
    overlap = float(config["minimumWindowOverlapPageUnits"])
    locked_fraction = float(config["lockedOverlapFraction"])
    expected_ppu = float(config["pixelsPerPageUnit"])
    if config["canvasPixels"] != [size, size] or span_x != span_y:
        raise ValueError("fixed-scale workflow requires a square canvas and square world span")
    actual_ppu = size / span_x
    if not math.isclose(actual_ppu, expected_ppu, rel_tol=0, abs_tol=1e-12):
        raise ValueError("pixelsPerPageUnit does not match canvasPixels/worldSpan")

    art = load_art_data()
    canonical = {city["id"]: city["balanced"] for city in art["cities"]}
    tiles = json.loads(TILE_MANIFEST.read_text(encoding="utf-8"))
    published = {
        tile["id"]: tile for tile in tiles
        if tile.get("layout") == "balanced" and tile.get("status") == "accepted"
    }
    target_path = canonical[args.target]
    if args.target in published and published[args.target]["path"] != target_path:
        raise ValueError(f"tile manifest path for {args.target} is not the page's balanced path")

    neighbors: list[tuple[str, Path]] = []
    for value in args.neighbor_art:
        region_id, separator, image_text = value.partition("=")
        if not separator or region_id not in canonical:
            parser.error("--neighbor-art must be REGION_ID=IMAGE with a known Jiangxi region")
        image_path = Path(image_text)
        if not image_path.is_absolute():
            image_path = ROOT / image_path
        if not image_path.is_file():
            parser.error(f"neighbor art does not exist: {image_path}")
        neighbors.append((region_id, image_path))

    accepted_windows: dict[int, Path] = {}
    for value in args.accepted_window:
        index_text, separator, image_text = value.partition("=")
        if not separator or not index_text.isdigit():
            parser.error("--accepted-window must be INDEX=IMAGE")
        image_path = Path(image_text)
        if not image_path.is_absolute():
            image_path = ROOT / image_path
        if not image_path.is_file():
            parser.error(f"accepted window does not exist: {image_path}")
        accepted_windows[int(index_text)] = image_path

    min_x, min_y, max_x, max_y = path_bounds(target_path)
    x_origins = axis_origins(min_x, max_x, span_x, margin, overlap)
    y_origins = axis_origins(min_y, max_y, span_y, margin, overlap)
    master = joint_svg.read_text(encoding="utf-8")
    output_dir = args.output_dir or (
        ROOT / "artwork/generation-inputs" / name / "fixed-scale-tiles"
    )
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    window_geometries = []
    for row, y in enumerate(y_origins):
        for column, x in enumerate(x_origins):
            window_geometries.append({
                "index": len(window_geometries) + 1,
                "row": row,
                "column": column,
                "worldBounds": [x, y, span_x, span_y],
            })

    unknown = sorted(set(accepted_windows) - {window["index"] for window in window_geometries})
    if unknown:
        parser.error(f"accepted window indices are outside this plan: {unknown}")

    windows = []
    for geometry in window_geometries:
            index = geometry["index"]
            row = geometry["row"]
            column = geometry["column"]
            x, y, _, _ = geometry["worldBounds"]
            root = (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="{x:.9f} {y:.9f} {span_x:.9f} {span_y:.9f}" '
                f'width="{size}" height="{size}">'
                f'<rect x="{x:.9f}" y="{y:.9f}" width="{span_x:.9f}" height="{span_y:.9f}" '
                f'fill="#f5f1e7" data-role="blank-outside-semantic"/>'
            )
            context_svg = re.sub(r"<svg\b[^>]*>", root, master, count=1).rsplit("</svg>", 1)[0]
            if neighbors:
                context_svg += "<defs>"
                for region_id, _ in neighbors:
                    context_svg += (
                        f'<clipPath id="neighbor-{region_id}" clipPathUnits="userSpaceOnUse">'
                        f'<path d="{canonical[region_id]}"/></clipPath>'
                    )
                context_svg += "</defs>"
                for region_id, image_path in neighbors:
                    bx0, by0, bx1, by1 = path_bounds(canonical[region_id])
                    bx, by, bw, bh = bx0, by0, bx1 - bx0, by1 - by0
                    context_svg += (
                        f'<image x="{bx}" y="{by}" width="{bw}" height="{bh}" preserveAspectRatio="none" '
                        f'clip-path="url(#neighbor-{region_id})" href="{data_uri(image_path)}" '
                        f'data-role="accepted-neighbor-art"/>'
                    )

            locked_regions = []
            for previous in window_geometries:
                previous_index = previous["index"]
                if previous_index >= index or previous_index not in accepted_windows:
                    continue
                lock = owned_overlap(previous["worldBounds"], geometry["worldBounds"], locked_fraction)
                if lock is None:
                    continue
                lx, ly, lw, lh = lock
                clip_id = f"accepted-window-{previous_index}-lock-{index}"
                target_clip_id = f"target-region-{index}-{previous_index}"
                context_svg += (
                    f'<defs><clipPath id="{clip_id}" clipPathUnits="userSpaceOnUse">'
                    f'<rect x="{lx:.9f}" y="{ly:.9f}" width="{lw:.9f}" height="{lh:.9f}"/>'
                    f'</clipPath><clipPath id="{target_clip_id}" clipPathUnits="userSpaceOnUse">'
                    f'<path d="{target_path}"/></clipPath></defs>'
                    f'<g clip-path="url(#{target_clip_id})"><image '
                    f'x="{previous["worldBounds"][0]:.9f}" y="{previous["worldBounds"][1]:.9f}" '
                    f'width="{previous["worldBounds"][2]:.9f}" height="{previous["worldBounds"][3]:.9f}" '
                    f'preserveAspectRatio="none" clip-path="url(#{clip_id})" '
                    f'href="{data_uri(accepted_windows[previous_index])}" '
                    f'data-role="immutable-accepted-window"/></g>'
                )
                locked_regions.append({
                    "sourceWindow": previous_index,
                    "sourceImage": str(accepted_windows[previous_index].relative_to(ROOT)),
                    "worldBounds": lock,
                    "pixelBoundsInCurrent": [
                        round((lx - x) * actual_ppu),
                        round((ly - y) * actual_ppu),
                        round(lw * actual_ppu),
                        round(lh * actual_ppu),
                    ],
                })
            context_svg += "</svg>"

            locked_mask_shapes = "".join(
                f'<rect x="{lock["worldBounds"][0]:.9f}" y="{lock["worldBounds"][1]:.9f}" '
                f'width="{lock["worldBounds"][2]:.9f}" height="{lock["worldBounds"][3]:.9f}" fill="#000"/>'
                for lock in locked_regions
            )
            mask_svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
              viewBox="{x:.9f} {y:.9f} {span_x:.9f} {span_y:.9f}"
              width="{size}" height="{size}">
              <rect x="{x:.9f}" y="{y:.9f}" width="{span_x:.9f}" height="{span_y:.9f}" fill="#000"/>
              <path d="{target_path}" fill="#fff"/>
              {locked_mask_shapes}
            </svg>'''

            stem = f"{name}-{index:02d}"
            context_path = output_dir / f"{stem}-context.png"
            visible_mask_path = output_dir / f"{stem}-mask.png"
            edit_mask_path = output_dir / f"{stem}-edit-mask.png"
            render_png(context_svg, context_path, size)
            mask_bytes = cairosvg.svg2png(
                bytestring=mask_svg.encode("utf-8"), output_width=size, output_height=size
            )
            editable = Image.open(io.BytesIO(mask_bytes)).convert("L").point(
                lambda value: 255 if value >= 128 else 0
            )
            editable.save(visible_mask_path)
            api_mask = Image.new("RGBA", (size, size), (0, 0, 0, 255))
            api_mask.putalpha(Image.eval(editable, lambda value: 255 - value))
            api_mask.save(edit_mask_path)

            windows.append({
                "index": index,
                "row": row,
                "column": column,
                "worldBounds": [x, y, span_x, span_y],
                "canvasPixels": [size, size],
                "pixelsPerPageUnit": actual_ppu,
                "context": str(context_path.relative_to(ROOT)),
                "visibleMask": str(visible_mask_path.relative_to(ROOT)),
                "editMask": str(edit_mask_path.relative_to(ROOT)),
                "lockedAcceptedRegions": locked_regions,
                "postGenerationRule": "restore every black-mask pixel from context before compositing",
            })

    plan = {
        "schemaVersion": 1,
        "region": args.target,
        "layout": "balanced",
        "canonicalPath": target_path,
        "canonicalPathBounds": [min_x, min_y, max_x - min_x, max_y - min_y],
        "fixedScaleConfig": str(CONFIG_PATH.relative_to(ROOT)),
        "windowCount": len(windows),
        "generationOrder": [window["index"] for window in windows],
        "windows": windows,
        "neighborArt": [
            {"region": region_id, "image": str(image_path.relative_to(ROOT))}
            for region_id, image_path in neighbors
        ],
        "acceptedWindows": [
            {"index": index, "image": str(image_path.relative_to(ROOT))}
            for index, image_path in sorted(accepted_windows.items())
        ],
        "publishRule": "composite in balanced page coordinates; crop to canonicalPathBounds; never stretch",
    }
    plan_path = output_dir / f"{name}-plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"plan": str(plan_path.relative_to(ROOT)), "windowCount": len(windows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
