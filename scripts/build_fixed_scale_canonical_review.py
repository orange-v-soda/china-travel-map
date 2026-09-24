#!/usr/bin/env python3
"""Place canonical regional rasters together in balanced page coordinates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--region", action="append", required=True, metavar="PLAN=IMAGE")
    parser.add_argument("--margin", type=float, default=8.0)
    args = parser.parse_args()

    regions = []
    ppu = None
    for value in args.region:
        plan_text, separator, image_text = value.partition("=")
        if not separator:
            parser.error("--region must be PLAN=IMAGE")
        plan = json.loads(Path(plan_text).read_text(encoding="utf-8"))
        image = Image.open(image_text).convert("RGBA")
        bounds = plan["canonicalPathBounds"]
        region_ppu = image.width / bounds[2]
        if ppu is None:
            ppu = region_ppu
        elif abs(region_ppu - ppu) > 0.01:
            raise ValueError("regional rasters do not share one fixed pixel scale")
        regions.append((bounds, image))

    min_x = min(bounds[0] for bounds, _ in regions) - args.margin
    min_y = min(bounds[1] for bounds, _ in regions) - args.margin
    max_x = max(bounds[0] + bounds[2] for bounds, _ in regions) + args.margin
    max_y = max(bounds[1] + bounds[3] for bounds, _ in regions) + args.margin
    canvas = Image.new(
        "RGB",
        (round((max_x - min_x) * ppu), round((max_y - min_y) * ppu)),
        "#f5f1e7",
    )
    for bounds, image in regions:
        x, y, width, height = bounds
        expected = (round(width * ppu), round(height * ppu))
        if image.size != expected:
            image = image.resize(expected, Image.Resampling.LANCZOS)
        canvas.paste(
            image,
            (round((x - min_x) * ppu), round((y - min_y) * ppu)),
            image,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(json.dumps({"output": str(args.output), "size": list(canvas.size), "ppu": ppu}))


if __name__ == "__main__":
    main()
