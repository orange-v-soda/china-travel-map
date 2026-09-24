#!/usr/bin/env python3
"""Merge accepted fixed-scale windows in page space using their editable masks."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import cairosvg
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--window", action="append", required=True, metavar="INDEX=IMAGE")
    args = parser.parse_args()

    sources: dict[int, Path] = {}
    for value in args.window:
        index_text, separator, image_text = value.partition("=")
        if not separator or not index_text.isdigit():
            parser.error("--window must be INDEX=IMAGE")
        sources[int(index_text)] = Path(image_text)

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    windows = {item["index"]: item for item in plan["windows"]}
    if set(sources) != set(plan["generationOrder"]):
        parser.error("one source is required for every planned generation window")

    first_index = plan["generationOrder"][0]
    first = Image.open(sources[first_index]).convert("RGBA")
    first_world = windows[first_index]["worldBounds"]
    ppu_x = first.width / first_world[2]
    ppu_y = first.height / first_world[3]
    bx, by, bw, bh = plan["canonicalPathBounds"]
    output_width, output_height = round(bw * ppu_x), round(bh * ppu_y)
    canvas = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))

    for index in plan["generationOrder"]:
        window = windows[index]
        source = Image.open(sources[index]).convert("RGBA")
        wx, wy, ww, wh = window["worldBounds"]
        expected = (round(ww * ppu_x), round(wh * ppu_y))
        if source.size != expected:
            source = source.resize(expected, Image.Resampling.LANCZOS)
        editable = Image.open(window["visibleMask"]).convert("L").resize(
            source.size, Image.Resampling.NEAREST
        ).point(lambda value: 255 if value >= 128 else 0)
        source.putalpha(editable)
        x = round((wx - bx) * ppu_x)
        y = round((wy - by) * ppu_y)
        canvas.alpha_composite(source, (x, y))

    final_mask_svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
      viewBox="{bx} {by} {bw} {bh}" width="{output_width}" height="{output_height}">
      <path d="{plan['canonicalPath']}" fill="#fff"/>
    </svg>'''
    mask_bytes = cairosvg.svg2png(
        bytestring=final_mask_svg.encode("utf-8"),
        output_width=output_width,
        output_height=output_height,
    )
    canvas.putalpha(Image.open(io.BytesIO(mask_bytes)).convert("L"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    print(json.dumps({
        "output": str(args.output),
        "size": [output_width, output_height],
        "pixelsPerPageUnit": [ppu_x, ppu_y],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
