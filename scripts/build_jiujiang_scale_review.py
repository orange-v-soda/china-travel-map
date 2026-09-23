#!/usr/bin/env python3
"""Build Jiujiang mask/context at the accepted Nanchang geographic scale."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import cairosvg


ROOT = Path(__file__).resolve().parents[1]
CANVAS = 4096
PX_PER_PAGE_UNIT = 2048 / 175
WORLD_SPAN = CANVAS / PX_PER_PAGE_UNIT
PAPER = "#f5f1e7"
MASTER = ROOT / "dist/assets/joint-nanchang-jiujiang/nanchang-jiujiang-joint-semantic-v7.svg"
TILES = ROOT / "dist/jiangxi-city-tiles.json"
NANCHANG_ART = ROOT / "generated_images/exec-bed00718-7969-439e-b4bc-39331edefc73.png"
NANCHANG_VIEW = [293.453153465, 232.265967415, 175.0, 175.0]
OUT = ROOT / "artwork/generation-inputs/jiujiang/scale-review"


def bounds(path_text: str) -> tuple[float, float, float, float]:
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", path_text)]
    xs, ys = numbers[0::2], numbers[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def png_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render(svg: str, path: Path) -> None:
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(path),
        output_width=CANVAS,
        output_height=CANVAS,
    )


def main() -> None:
    tiles = json.loads(TILES.read_text())
    records = {tile["id"]: tile for tile in tiles if tile["layout"] == "balanced"}
    target = records["360400"]
    nanchang = records["360100"]

    min_x, min_y, max_x, max_y = bounds(target["path"])
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    world = [center_x - WORLD_SPAN / 2, center_y - WORLD_SPAN / 2, WORLD_SPAN, WORLD_SPAN]
    x, y, width, height = world

    OUT.mkdir(parents=True, exist_ok=True)
    mask_svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
      viewBox="{x:.9f} {y:.9f} {width:.9f} {height:.9f}" width="{CANVAS}" height="{CANVAS}">
      <rect x="{x:.9f}" y="{y:.9f}" width="{width:.9f}" height="{height:.9f}" fill="#000"/>
      <path d="{target['path']}" fill="#fff"/>
    </svg>'''
    render(mask_svg, OUT / "jiujiang-mask.png")

    master = MASTER.read_text()
    replacement = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{x:.9f} {y:.9f} {width:.9f} {height:.9f}" '
        f'width="{CANVAS}" height="{CANVAS}">'
        f'<rect x="{x:.9f}" y="{y:.9f}" width="{width:.9f}" height="{height:.9f}" '
        f'fill="{PAPER}" data-role="blank-outside-semantic"/>'
    )
    context = re.sub(r"<svg\b[^>]*>", replacement, master, count=1)
    vx, vy, vw, vh = NANCHANG_VIEW
    overlay = f'''
      <defs><clipPath id="accepted-nanchang-art" clipPathUnits="userSpaceOnUse">
        <path d="{nanchang['path']}"/>
      </clipPath></defs>
      <image x="{vx}" y="{vy}" width="{vw}" height="{vh}" preserveAspectRatio="none"
        clip-path="url(#accepted-nanchang-art)" href="{png_uri(NANCHANG_ART)}"
        data-role="accepted-neighbor-art"/>
    </svg>'''
    context = context.rsplit("</svg>", 1)[0] + overlay
    render(context, OUT / "jiujiang-context.png")

    print(json.dumps({
        "canvas": [CANVAS, CANVAS],
        "pxPerPageUnit": PX_PER_PAGE_UNIT,
        "worldBounds": world,
        "targetPixelSize": [
            round((max_x - min_x) * PX_PER_PAGE_UNIT, 2),
            round((max_y - min_y) * PX_PER_PAGE_UNIT, 2),
        ],
        "nanchangArt": str(NANCHANG_ART.relative_to(ROOT)),
        "outputs": [
            str((OUT / "jiujiang-mask.png").relative_to(ROOT)),
            str((OUT / "jiujiang-context.png").relative_to(ROOT)),
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
