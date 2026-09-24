#!/usr/bin/env python3
"""Publish accepted canonical rasters using workflow-declared paths and bounds."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / "dist/jiangxi-city-tiles.json"


def repository_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--region",
        action="append",
        required=True,
        metavar="WORKFLOW=CANONICAL_PNG",
        help="publish one accepted canonical raster through its workflow manifest",
    )
    args = parser.parse_args()

    requests = []
    for value in args.region:
        workflow_text, separator, image_text = value.partition("=")
        if not separator:
            parser.error("--region must be WORKFLOW=CANONICAL_PNG")
        workflow_path = repository_path(workflow_text)
        image_path = repository_path(image_text)
        if not workflow_path.is_file() or not image_path.is_file():
            parser.error(f"missing workflow or canonical image: {value}")
        requests.append((workflow_path, image_path))

    tiles = json.loads(TILES.read_text(encoding="utf-8"))
    published = {}

    for workflow_path, image_path in requests:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        region = workflow["region"]
        artifacts = workflow["artifacts"]
        plan = json.loads(repository_path(artifacts["fixedScalePlan"]).read_text(encoding="utf-8"))
        matches = [
            tile for tile in tiles
            if tile.get("id") == region["id"] and tile.get("layout") == region["layout"]
        ]
        if len(matches) != 1:
            raise ValueError(f"{region['id']}: expected exactly one tile record")
        tile = matches[0]
        if tile["path"] != plan["canonicalPath"]:
            raise ValueError(f"{region['id']}: page path differs from fixed-scale plan")

        image = Image.open(image_path).convert("RGBA")
        bx, by, bw, bh = plan["canonicalPathBounds"]
        ppu_x, ppu_y = image.width / bw, image.height / bh
        if abs(ppu_x - ppu_y) > 0.02:
            raise ValueError(f"{region['id']}: canonical raster is stretched")

        dist_path = repository_path(artifacts["finalImage"])
        if dist_path.suffix.lower() != ".webp":
            raise ValueError(f"{region['id']}: finalImage must be a WebP")
        dist_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(dist_path, "WEBP", quality=92, method=6, exact=True)

        tile["bounds"] = [bx, by, bw, bh]
        tile["image"] = str(dist_path.relative_to(ROOT / "dist"))
        tile["status"] = "accepted"
        tile["reviewNote"] = (
            f"Fixed-scale canonical {region['name']} raster published at exact balanced-layout bounds."
        )
        published[region["id"]] = {
            "image": str(dist_path.relative_to(ROOT)),
            "size": list(image.size),
            "pixelsPerPageUnit": [ppu_x, ppu_y],
        }

    TILES.write_text(json.dumps(tiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    preview_tiles = ROOT / "full-page-preview/jiangxi-city-tiles.json"
    if preview_tiles.parent.exists():
        shutil.copy2(TILES, preview_tiles)
    print(json.dumps({"assets": published}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
