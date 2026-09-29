#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cairosvg
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "artwork/fixed-scale-generation.json").read_text())
CANVAS = tuple(CONFIG["canvasPixels"])
NORMALIZED = tuple(CONFIG["normalizedGeneratedPixels"])
INPUT_PPU = CONFIG["pixelsPerPageUnit"]
OUTPUT_PPU = CONFIG["generatedPixelsPerPageUnit"]


def path_points(path: str):
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path)]
    return list(zip(nums[::2], nums[1::2]))


def render_svg_window(svg_path: Path, bounds):
    text = svg_path.read_text()
    x, y, w, h = bounds
    text = re.sub(r'viewBox="[^"]+"', f'viewBox="{x} {y} {w} {h}"', text, count=1)
    data = cairosvg.svg2png(bytestring=text.encode(), output_width=CANVAS[0], output_height=CANVAS[1])
    from io import BytesIO
    return Image.open(BytesIO(data)).convert("RGBA")


def page_to_pixel(point, bounds, ppu=INPUT_PPU):
    return ((point[0] - bounds[0]) * ppu, (point[1] - bounds[1]) * ppu)


def paste_page_art(canvas, image_path, art_bounds, window_bounds):
    art = Image.open(image_path).convert("RGBA")
    target = (round(art_bounds[2] * INPUT_PPU), round(art_bounds[3] * INPUT_PPU))
    art = art.resize(target, Image.Resampling.LANCZOS)
    xy = page_to_pixel((art_bounds[0], art_bounds[1]), window_bounds)
    canvas.alpha_composite(art, (round(xy[0]), round(xy[1])))


def ownership_rect(plan, window):
    columns = sorted({w["column"] for w in plan["windows"]})
    rows = sorted({w["row"] for w in plan["windows"]})
    xcenters = {c: sum(w["worldBounds"][0] + w["worldBounds"][2] / 2 for w in plan["windows"] if w["column"] == c) / sum(1 for w in plan["windows"] if w["column"] == c) for c in columns}
    ycenters = {r: sum(w["worldBounds"][1] + w["worldBounds"][3] / 2 for w in plan["windows"] if w["row"] == r) / sum(1 for w in plan["windows"] if w["row"] == r) for r in rows}
    ci, ri = columns.index(window["column"]), rows.index(window["row"])
    wx, wy, ww, wh = window["worldBounds"]
    left = wx if ci == 0 else (xcenters[columns[ci - 1]] + xcenters[columns[ci]]) / 2
    right = wx + ww if ci == len(columns) - 1 else (xcenters[columns[ci]] + xcenters[columns[ci + 1]]) / 2
    top = wy if ri == 0 else (ycenters[rows[ri - 1]] + ycenters[rows[ri]]) / 2
    bottom = wy + wh if ri == len(rows) - 1 else (ycenters[rows[ri]] + ycenters[rows[ri + 1]]) / 2
    return left, top, right, bottom


def polygon_mask(path, bounds):
    im = Image.new("L", CANVAS, 0)
    pts = [page_to_pixel(p, bounds) for p in path_points(path)]
    ImageDraw.Draw(im).polygon(pts, fill=255)
    return im


def owned_mask(plan, window, visible):
    left, top, right, bottom = ownership_rect(plan, window)
    wb = window["worldBounds"]
    p0 = page_to_pixel((left, top), wb)
    p1 = page_to_pixel((right, bottom), wb)
    rect = Image.new("L", CANVAS, 0)
    ImageDraw.Draw(rect).rectangle((round(p0[0]), round(p0[1]), round(p1[0]), round(p1[1])), fill=255)
    return ImageChops.multiply(visible, rect)


def overlay_restored_window(canvas, restored_path, source_bounds, current_bounds):
    restored = Image.open(restored_path).convert("RGBA")
    restored = restored.resize(CANVAS, Image.Resampling.LANCZOS)
    dx = round((source_bounds[0] - current_bounds[0]) * INPUT_PPU)
    dy = round((source_bounds[1] - current_bounds[1]) * INPUT_PPU)
    canvas.alpha_composite(restored, (dx, dy))


def build_inputs(region, through):
    plan_path = ROOT / f"artwork/generation-inputs/{region}/fixed-scale-tiles/{region}-plan.json"
    plan = json.loads(plan_path.read_text())
    semantic = ROOT / f"dist/assets/{region}/{region}-semantic.svg"
    outdir = plan_path.parent
    refs = {
        "nanchang": (ROOT.parent / "reference/nanchang-art-final-v6.webp", [328.68328868, 272.59962157, 104.53972957, 94.33269169]),
        "jiujiang": (ROOT.parent / "reference/jiujiang-art-final-v7.webp", [191.86382596, 186.49296086, 258.41335429, 118.72376479]),
        "shangrao": (ROOT / "artwork/generated/shangrao/shangrao-fixed-scale-canonical-v3.png", [417.81560560, 222.47860546, 186.97455521, 180.96645628]),
    }
    version = "v3" if region == "shangrao" else "v2"
    for window in plan["windows"]:
        if window["index"] > through:
            continue
        bounds = window["worldBounds"]
        context = Image.new("RGBA", CANVAS, (242, 239, 226, 255))
        context.alpha_composite(render_svg_window(semantic, bounds))
        for item in plan.get("neighborArt", []):
            slug = {"360100": "nanchang", "360400": "jiujiang", "361100": "shangrao"}.get(item["region"])
            if slug and refs[slug][0].exists():
                paste_page_art(context, refs[slug][0], refs[slug][1], bounds)
        for previous in plan["windows"]:
            if previous["index"] >= window["index"]:
                break
            restored = ROOT / f"artwork/generated/{region}/{region}-fixed-scale-window-{previous['index']:02d}-{version}-restored.png"
            if restored.exists():
                overlay_restored_window(context, restored, previous["worldBounds"], bounds)
        visible = polygon_mask(plan["canonicalPath"], bounds)
        edit = owned_mask(plan, window, visible)
        stem = f"{region}-{window['index']:02d}"
        context.save(outdir / f"{stem}-context.png")
        visible.save(outdir / f"{stem}-mask.png")
        edit.save(outdir / f"{stem}-edit-mask.png")
        print(json.dumps({"window": window["index"], "context": str(outdir / f"{stem}-context.png"), "editablePixels": sum(1 for p in edit.getdata() if p)}))


def restore(region, index, generated):
    base = ROOT / f"artwork/generation-inputs/{region}/fixed-scale-tiles/{region}-{index:02d}"
    context = Image.open(str(base) + "-context.png").convert("RGBA").resize(NORMALIZED, Image.Resampling.LANCZOS)
    mask = Image.open(str(base) + "-edit-mask.png").convert("L").resize(NORMALIZED, Image.Resampling.NEAREST)
    result = Image.open(generated).convert("RGBA").resize(NORMALIZED, Image.Resampling.LANCZOS)
    restored = Image.composite(result, context, mask)
    outdir = ROOT / f"artwork/generated/{region}"
    outdir.mkdir(parents=True, exist_ok=True)
    version = "v3" if region == "shangrao" else "v2"
    out = outdir / f"{region}-fixed-scale-window-{index:02d}-{version}-restored.png"
    restored.save(out)
    print(out)


def merge(region):
    plan = json.loads((ROOT / f"artwork/generation-inputs/{region}/fixed-scale-tiles/{region}-plan.json").read_text())
    version = "v3" if region == "shangrao" else "v2"
    x, y, w, h = plan["canonicalPathBounds"]
    size = (round(w * OUTPUT_PPU), round(h * OUTPUT_PPU))
    merged = Image.new("RGBA", size, (0, 0, 0, 0))
    for window in plan["windows"]:
        idx = window["index"]
        restored = Image.open(ROOT / f"artwork/generated/{region}/{region}-fixed-scale-window-{idx:02d}-{version}-restored.png").convert("RGBA")
        mask = Image.open(ROOT / f"artwork/generation-inputs/{region}/fixed-scale-tiles/{region}-{idx:02d}-edit-mask.png").convert("L").resize(NORMALIZED, Image.Resampling.NEAREST)
        restored.putalpha(ImageChops.multiply(restored.getchannel("A"), mask))
        dx = round((window["worldBounds"][0] - x) * OUTPUT_PPU)
        dy = round((window["worldBounds"][1] - y) * OUTPUT_PPU)
        merged.alpha_composite(restored, (dx, dy))
    final_mask = Image.new("L", size, 0)
    pts = [((px - x) * OUTPUT_PPU, (py - y) * OUTPUT_PPU) for px, py in path_points(plan["canonicalPath"])]
    ImageDraw.Draw(final_mask).polygon(pts, fill=255)
    merged.putalpha(final_mask)
    outdir = ROOT / f"dist/assets/{region}"
    outdir.mkdir(parents=True, exist_ok=True)
    canonical = ROOT / f"artwork/generated/{region}/{region}-fixed-scale-canonical-{version}.png"
    merged.save(canonical)
    final = outdir / f"{region}-art-final-{version}.webp"
    merged.save(final, "WEBP", quality=88, method=6)
    print(json.dumps({"canonical": str(canonical), "final": str(final), "size": size}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-inputs"); b.add_argument("region"); b.add_argument("--through", type=int, required=True)
    r = sub.add_parser("restore"); r.add_argument("region"); r.add_argument("index", type=int); r.add_argument("generated")
    m = sub.add_parser("merge"); m.add_argument("region")
    a = p.parse_args()
    if a.cmd == "build-inputs": build_inputs(a.region, a.through)
    elif a.cmd == "restore": restore(a.region, a.index, a.generated)
    else: merge(a.region)


if __name__ == "__main__":
    main()
