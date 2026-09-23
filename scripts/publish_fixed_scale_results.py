#!/usr/bin/env python3
"""Map fixed-scale raw generations back to exact project tiles and publish v5 assets."""
from __future__ import annotations

import io
import json
from pathlib import Path

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PAPER = "#f5f1e7"
TILES = ROOT / "dist/jiangxi-city-tiles.json"
REGIONS = {
    "360100": {
        "name": "nanchang",
        "source": ROOT / "generated_images/exec-bed00718-7969-439e-b4bc-39331edefc73.png",
        "world": [293.453153465, 232.265967415, 175.0, 175.0],
        "size": [1024, 1024],
        "mask": ROOT / "dist/assets/nanchang/nanchang-mask.svg",
    },
    "360400": {
        "name": "jiujiang",
        "source": ROOT / "generated_images/exec-b6c18eef-7ecf-4537-8ac8-456be758a124.png",
        "world": [146.070503105, 70.854843255, 350.0, 350.0],
        "size": [1024, 979],
        "mask": ROOT / "dist/assets/jiujiang/jiujiang-mask.svg",
    },
}


def map_to_tile(source: Image.Image, world: list[float], tile_bounds: list[float], size: list[int]) -> Image.Image:
    wx, wy, ww, wh = world
    tx, ty, tw, th = tile_bounds
    sw, sh = source.size
    ow, oh = size
    affine = (
        tw * sw / (ww * ow),
        0,
        (tx - wx) * sw / ww,
        0,
        th * sh / (wh * oh),
        (ty - wy) * sh / wh,
    )
    return source.transform(
        (ow, oh),
        Image.Transform.AFFINE,
        affine,
        resample=Image.Resampling.BICUBIC,
    )


def exact_mask(path: Path, size: list[int]) -> Image.Image:
    data = cairosvg.svg2png(url=str(path), output_width=size[0], output_height=size[1])
    return Image.open(io.BytesIO(data)).convert("L")


def main() -> None:
    tiles = json.loads(TILES.read_text())
    by_id = {tile["id"]: tile for tile in tiles if tile["layout"] == "balanced"}
    published = {}

    for region_id, record in REGIONS.items():
        tile = by_id[region_id]
        source = Image.open(record["source"]).convert("RGB")
        mapped = map_to_tile(source, record["world"], tile["bounds"], record["size"])
        mask = exact_mask(record["mask"], record["size"])
        final = Image.composite(mapped, Image.new("RGB", tuple(record["size"]), PAPER), mask)

        name = record["name"]
        review_path = ROOT / f"artwork/generated/{name}/{name}-fixed-scale-v5.png"
        dist_path = ROOT / f"dist/assets/{name}/{name}-art-final-v5.webp"
        preview_path = ROOT / f"full-page-preview/assets/{name}/{name}-art-final-v5.webp"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        final.save(review_path)
        for path in (dist_path, preview_path):
            path.parent.mkdir(parents=True, exist_ok=True)
            final.save(path, "WEBP", quality=88, method=6)
        published[region_id] = {"tile": tile, "image": final, "mask": mask, "dist": dist_path}

    min_x = min(item["tile"]["bounds"][0] for item in published.values()) - 4
    min_y = min(item["tile"]["bounds"][1] for item in published.values()) - 4
    max_x = max(item["tile"]["bounds"][0] + item["tile"]["bounds"][2] for item in published.values()) + 4
    max_y = max(item["tile"]["bounds"][1] + item["tile"]["bounds"][3] for item in published.values()) + 4
    scale = 6
    review = Image.new("RGB", (round((max_x - min_x) * scale), round((max_y - min_y) * scale)), PAPER)
    for region_id in ("360400", "360100"):
        item = published[region_id]
        x, y, width, height = item["tile"]["bounds"]
        review_size = (round(width * scale), round(height * scale))
        image = item["image"].resize(review_size, Image.Resampling.LANCZOS)
        mask = item["mask"].resize(review_size, Image.Resampling.LANCZOS)
        review.paste(image, (round((x - min_x) * scale), round((y - min_y) * scale)), mask)
    review_path = ROOT / "dist/nanchang-jiujiang-fixed-scale-v5-review.png"
    review.save(review_path)

    print(json.dumps({
        "assets": {region_id: str(item["dist"].relative_to(ROOT)) for region_id, item in published.items()},
        "review": str(review_path.relative_to(ROOT)),
        "sizes": {region_id: item["image"].size for region_id, item in published.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
