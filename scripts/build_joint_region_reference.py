#!/usr/bin/env python3
"""Compose regional semantic SVGs in project coordinates for one-pass generation."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SIZE = 1536
REGIONS = {
    "jiujiang": {
        "semantic": ROOT / "dist/assets/jiujiang/jiujiang-semantic.svg",
        "mask": ROOT / "dist/assets/jiujiang/jiujiang-mask.svg",
        "path": "360400",
    },
    "nanchang": {
        "semantic": ROOT / "dist/assets/nanchang/nanchang-semantic.svg",
        "mask": ROOT / "dist/assets/nanchang/nanchang-mask.svg",
        "path": "360100",
    },
}


def load_art():
    text = (ROOT / "dist/jiangxi-art-data.js").read_text()
    return json.loads(text.split(" = ", 1)[1].rsplit(";", 1)[0])


def path_bounds(path: str):
    values = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path)]
    xs, ys = values[0::2], values[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def render(path: Path) -> Image.Image:
    data = cairosvg.svg2png(url=str(path), output_width=1024, output_height=1024)
    return Image.open(io.BytesIO(data)).convert("RGBA")


art = load_art()
cities = {city["id"]: city for city in art["cities"]}
for region in REGIONS.values():
    region["bounds"] = path_bounds(cities[region["path"]]["balanced"])

minx = min(r["bounds"][0] for r in REGIONS.values())
miny = min(r["bounds"][1] for r in REGIONS.values())
maxx = max(r["bounds"][2] for r in REGIONS.values())
maxy = max(r["bounds"][3] for r in REGIONS.values())
span = max(maxx - minx, maxy - miny) * 1.12
cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
world = [cx - span / 2, cy - span / 2, cx + span / 2, cy + span / 2]
joint_scale = SIZE / span

canvas = Image.new("RGBA", (SIZE, SIZE), "#f5f1e7")
union_mask = Image.new("L", (SIZE, SIZE), 0)
placements = {}

for name, region in REGIONS.items():
    bx0, by0, bx1, by1 = region["bounds"]
    local_scale = min((1024 - 112) / (bx1 - bx0), (1024 - 112) / (by1 - by0))
    local_ox = (1024 - (bx1 - bx0) * local_scale) / 2
    local_oy = (1024 - (by1 - by0) * local_scale) / 2
    resize_scale = joint_scale / local_scale
    width = round(1024 * resize_scale)
    height = round(1024 * resize_scale)
    x = round((bx0 - local_ox / local_scale - world[0]) * joint_scale)
    y = round((by0 - local_oy / local_scale - world[1]) * joint_scale)

    semantic = render(region["semantic"]).resize((width, height), Image.Resampling.LANCZOS)
    mask = render(region["mask"]).convert("L").resize((width, height), Image.Resampling.LANCZOS)
    canvas.paste(semantic, (x, y), mask)
    union_mask.paste(Image.new("L", (width, height), 255), (x, y), mask)
    placements[name] = {"x": x, "y": y, "width": width, "height": height, "bounds": region["bounds"]}

out = ROOT / "dist/assets/joint-nanchang-jiujiang"
out.mkdir(parents=True, exist_ok=True)
canvas.convert("RGB").save(out / "joint-semantic.png")
union_mask.save(out / "joint-mask.png")
(out / "joint-layout.json").write_text(json.dumps({
    "size": SIZE,
    "worldBounds": world,
    "worldScale": joint_scale,
    "regions": placements,
}, indent=2) + "\n")
print({"worldBounds": world, "placements": placements})
