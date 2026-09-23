#!/usr/bin/env python3
"""Build deterministic fixed-scale review inputs from a joint semantic SVG.

This does not invoke an image model. Every regional generation view uses the
same square page-space extent, so geographic scale cannot drift when a new
region is added. Regions with no semantic coverage remain the blank paper
color; accepted neighboring semantics appear wherever they enter the view.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
CANVAS_PX = 2048
WORLD_SPAN = 320.0
PX_PER_PAGE_UNIT = CANVAS_PX / WORLD_SPAN
PAPER = "#f5f1e7"
MASTER = ROOT / "dist/assets/joint-nanchang-jiujiang/nanchang-jiujiang-joint-semantic-v7.svg"
TILES = ROOT / "dist/jiangxi-city-tiles.json"


def path_bounds(path_text: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", path_text)]
    xs, ys = values[0::2], values[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def render_semantic(master_text: str, world: list[float], output: Path) -> None:
    x, y, width, height = world
    root = re.compile(r"<svg\b[^>]*>")
    replacement = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{x:.6f} {y:.6f} {width:.6f} {height:.6f}" '
        f'width="{CANVAS_PX}" height="{CANVAS_PX}">'
        f'<rect x="{x:.6f}" y="{y:.6f}" width="{width:.6f}" '
        f'height="{height:.6f}" fill="{PAPER}" data-role="blank-outside-semantic"/>'
    )
    review_svg = root.sub(replacement, master_text, count=1)
    cairosvg.svg2png(
        bytestring=review_svg.encode("utf-8"),
        write_to=str(output),
        output_width=CANVAS_PX,
        output_height=CANVAS_PX,
    )


def render_mask(path_text: str, world: list[float], output: Path) -> None:
    x, y, width, height = world
    mask_svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
      viewBox="{x:.6f} {y:.6f} {width:.6f} {height:.6f}"
      width="{CANVAS_PX}" height="{CANVAS_PX}">
      <rect x="{x:.6f}" y="{y:.6f}" width="{width:.6f}" height="{height:.6f}" fill="#000"/>
      <path d="{path_text}" fill="#fff"/>
    </svg>'''
    cairosvg.svg2png(
        bytestring=mask_svg.encode("utf-8"),
        write_to=str(output),
        output_width=CANVAS_PX,
        output_height=CANVAS_PX,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default="360100")
    args = parser.parse_args()

    tiles = json.loads(TILES.read_text())
    target = next(tile for tile in tiles if tile["id"] == args.target and tile["layout"] == "balanced")
    min_x, min_y, max_x, max_y = path_bounds(target["path"])
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    world = [center_x - WORLD_SPAN / 2, center_y - WORLD_SPAN / 2, WORLD_SPAN, WORLD_SPAN]

    name = "nanchang" if args.target == "360100" else args.target
    output_dir = ROOT / "artwork/generation-inputs" / name / "fixed-scale-review"
    output_dir.mkdir(parents=True, exist_ok=True)
    mask = output_dir / f"{name}-mask.png"
    semantic = output_dir / f"{name}-semantic-context.png"
    render_mask(target["path"], world, mask)
    render_semantic(MASTER.read_text(), world, semantic)

    target_pixel_bounds = [
        round((min_x - world[0]) * PX_PER_PAGE_UNIT, 2),
        round((min_y - world[1]) * PX_PER_PAGE_UNIT, 2),
        round((max_x - min_x) * PX_PER_PAGE_UNIT, 2),
        round((max_y - min_y) * PX_PER_PAGE_UNIT, 2),
    ]
    print(json.dumps({
        "target": args.target,
        "master": str(MASTER.relative_to(ROOT)),
        "canvasPx": [CANVAS_PX, CANVAS_PX],
        "worldSpan": WORLD_SPAN,
        "pxPerPageUnit": PX_PER_PAGE_UNIT,
        "worldBounds": world,
        "targetPixelBounds": target_pixel_bounds,
        "mask": str(mask.relative_to(ROOT)),
        "semanticContext": str(semantic.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
