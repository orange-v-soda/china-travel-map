#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text())


def write_json(path, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def overlap(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return None if x1 <= x0 or y1 <= y0 else [x0, y0, x1 - x0, y1 - y0]


def finalize_plan(region, version):
    path = f"artwork/generation-inputs/{region}/fixed-scale-tiles/{region}-plan.json"
    plan = read_json(path)
    for current in plan["windows"]:
        locked = []
        for previous in plan["windows"]:
            if previous["index"] >= current["index"]:
                continue
            box = overlap(previous["worldBounds"], current["worldBounds"])
            if not box:
                continue
            px = [
                round((box[0] - current["worldBounds"][0]) * 2048 / 175),
                round((box[1] - current["worldBounds"][1]) * 2048 / 175),
                round(box[2] * 2048 / 175),
                round(box[3] * 2048 / 175),
            ]
            locked.append({
                "sourceWindow": previous["index"],
                "sourceImage": f"artwork/generated/{region}/{region}-fixed-scale-window-{previous['index']:02d}-{version}-restored.png",
                "worldBounds": box,
                "pixelBoundsInCurrent": px,
            })
        current["lockedAcceptedRegions"] = locked
    plan["acceptedWindows"] = [
        {"index": w["index"], "image": f"artwork/generated/{region}/{region}-fixed-scale-window-{w['index']:02d}-{version}-restored.png"}
        for w in plan["windows"]
    ]
    plan["generationProtocol"] = {
        "inputCount": 2,
        "input1": "fixed-scale context containing semantic target plus immutable accepted artwork",
        "input2": "strict binary edit mask; white editable, black immutable",
        "normalizedResultPixels": [1254, 1254],
        "restoreBlackMaskPixels": True,
    }
    write_json(path, plan)


def prefix_svg(path, region):
    text = (ROOT / path).read_text()
    body = re.sub(r"^.*?<svg[^>]*>", "", text, count=1, flags=re.S)
    body = re.sub(r"</svg>\s*$", "", body, count=1, flags=re.S)
    ids = set(re.findall(r'id="([^"]+)"', body))
    for old in sorted(ids, key=len, reverse=True):
        new = f"r{region}-{old}"
        body = body.replace(f'id="{old}"', f'id="{new}"')
        body = body.replace(f'url(#{old})', f'url(#{new})')
        body = body.replace(f'href="#{old}"', f'href="#{new}"')
        body = body.replace(f'xlink:href="#{old}"', f'xlink:href="#{new}"')
    return f'<g data-region="{region}">{body}</g>'


def build_joint():
    parts = [
        prefix_svg("dist/assets/nanchang/nanchang-semantic.svg", "360100"),
        prefix_svg("dist/assets/jiujiang/jiujiang-semantic.svg", "360400"),
        prefix_svg("dist/assets/shangrao/shangrao-semantic.svg", "361100"),
        prefix_svg("dist/assets/jingdezhen/jingdezhen-semantic.svg", "360200"),
    ]
    rel = "dist/assets/joint-nanchang-jiujiang-shangrao-jingdezhen/nanchang-jiujiang-shangrao-jingdezhen-joint-semantic-v11.svg"
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="130 145 500 625">' + "".join(parts) + "</svg>\n")
    return rel


def build_workflows(joint):
    shared_rules = {
        "semanticSvgPrecedesGeneration": True,
        "finalPageLoadsRasterOnly": True,
        "targetGenerationMode": "fixed-scale-two-image-edit",
        "globalScaleBaseline": {"region": "360100", "rasterSize": [2048, 2048], "pageBounds": [293.453153465, 232.265967415, 175.0, 175.0], "pixelsPerPageUnit": 11.702857142857143},
        "normalizedGeneratedPixels": [1254, 1254],
        "rasterStretchOnPublishAllowed": False,
        "acceptedOverlapLockedInLaterWindows": True,
        "restoreLockedPixelsAfterGeneration": True,
        "editMaskSemantics": "white-only-edit-black-immutable",
        "modelVisibleAdministrativeOutline": False,
        "publishBounds": "canonical-path-bounds",
    }
    stages = ["lock-project-outline", "map-real-geography", "draw-semantic-svg", "build-global-scale-context", "tile-at-fixed-global-scale", "generate-raster-windows-from-svg-and-mask", "restore-immutable-pixels", "merge-windows-in-page-space", "apply-final-safety-clip-and-clean", "publish-raster-only"]
    sh = {
        "schemaVersion": 4,
        "region": {"id": "361100", "name": "上饶", "slug": "shangrao", "layout": "balanced"},
        "sequence": 3,
        "acceptedReferenceRegions": ["360100", "360400"],
        "excludedReferenceRegions": ["361000"],
        "stages": stages,
        "artifacts": {"semanticSvg": "dist/assets/shangrao/shangrao-semantic.svg", "jointSemanticSvg": joint, "fixedScalePlan": "artwork/generation-inputs/shangrao/fixed-scale-tiles/shangrao-plan.json", "maskSvg": "dist/assets/shangrao/shangrao-mask.svg", "finalImage": "dist/assets/shangrao/shangrao-art-final-v3.webp", "tileManifest": "dist/jiangxi-city-tiles.json"},
        "rules": shared_rules,
    }
    jz = {
        "schemaVersion": 4,
        "region": {"id": "360200", "name": "景德镇", "slug": "jingdezhen", "layout": "balanced"},
        "sequence": 4,
        "acceptedReferenceRegions": ["360100", "360400", "361100"],
        "excludedReferenceRegions": ["361000"],
        "stages": stages,
        "artifacts": {"semanticSvg": "dist/assets/jingdezhen/jingdezhen-semantic.svg", "jointSemanticSvg": joint, "fixedScalePlan": "artwork/generation-inputs/jingdezhen/fixed-scale-tiles/jingdezhen-plan.json", "maskSvg": "dist/assets/jingdezhen/jingdezhen-mask.svg", "finalImage": "dist/assets/jingdezhen/jingdezhen-art-final-v2.webp", "tileManifest": "dist/jiangxi-city-tiles.json"},
        "rules": shared_rules,
    }
    write_json("artwork/workflows/shangrao.json", sh)
    write_json("artwork/workflows/jingdezhen.json", jz)


def build_manifests():
    old = read_json("dist/assets/shangrao/manifest.json")
    old.update({
        "version": "v3",
        "generationMode": "fixed-scale-two-image-edit",
        "acceptedReferenceRegions": ["360100", "360400"],
        "excludedReferenceRegions": ["361000"],
        "canvasPixels": [2048, 2048],
        "normalizedGeneratedPixels": [1254, 1254],
        "worldSpan": [175.0, 175.0],
        "windowCount": 4,
        "finalImage": "shangrao-art-final-v3.webp",
        "finalSha256": sha("dist/assets/shangrao/shangrao-art-final-v3.webp"),
    })
    write_json("dist/assets/shangrao/manifest.json", old)
    jz = {
        "version": "v2",
        "projectOutline": "main / JIANGXI_ART region 360200 / balanced",
        "textFree": True,
        "generationMode": "fixed-scale-two-image-edit",
        "acceptedReferenceRegions": ["360100", "360400", "361100"],
        "excludedReferenceRegions": ["361000"],
        "canvasPixels": [2048, 2048],
        "normalizedGeneratedPixels": [1254, 1254],
        "worldSpan": [175.0, 175.0],
        "windowCount": 1,
        "anchors": [
            {"adcode": 360202, "name": "昌江区", "page": [488.82014231, 255.41441870]},
            {"adcode": 360203, "name": "珠山区", "page": [490.77149507, 254.98244038]},
            {"adcode": 360222, "name": "浮梁县", "page": [491.04727364, 249.32664521]},
            {"adcode": 360281, "name": "乐平市", "page": [482.34748026, 285.97911551]},
        ],
        "landmarks": [{"name": "御窑厂", "page": [493.6634, 239.0348], "rule": "single restrained historic ceramic kiln landmark"}],
        "finalImage": "jingdezhen-art-final-v2.webp",
        "finalSha256": sha("dist/assets/jingdezhen/jingdezhen-art-final-v2.webp"),
    }
    write_json("dist/assets/jingdezhen/manifest.json", jz)


def build_tiles():
    tiles = read_json("dist/jiangxi-city-tiles.json")
    tiles = [t for t in tiles if t["id"] != "361000"]
    by_id = {t["id"]: t for t in tiles}
    by_id["361100"].update({"image": "assets/shangrao/shangrao-art-final-v3.webp", "status": "accepted", "reviewNote": "Strict four-window fixed-scale two-image generation; only Nanchang and Jiujiang were accepted references; immutable pixels restored after every window."})
    jz_plan = read_json("artwork/generation-inputs/jingdezhen/fixed-scale-tiles/jingdezhen-plan.json")
    by_id["360200"] = {"id": "360200", "layout": "balanced", "path": jz_plan["canonicalPath"], "pathSha256": jz_plan["canonicalPathSha256"], "bounds": jz_plan["canonicalPathBounds"], "image": "assets/jingdezhen/jingdezhen-art-final-v2.webp", "status": "accepted", "reviewNote": "Strict fixed-scale two-image generation using Nanchang, Jiujiang and newly accepted Shangrao as immutable context; Fuzhou excluded."}
    order = ["360100", "360400", "361100", "360200"]
    write_json("dist/jiangxi-city-tiles.json", [by_id[i] for i in order])
    preview = []
    for item in [by_id[i] for i in order]:
        p = dict(item)
        p["image"] = "../dist/" + item["image"]
        preview.append(p)
    write_json("full-page-preview/jiangxi-city-tiles.json", preview)


def build_state(joint):
    state = {
        "schemaVersion": 2,
        "coordinateSystem": "balanced-page-space",
        "masterSvg": joint,
        "renderScale": 8,
        "acceptedOrder": ["360100", "360400", "361100", "360200"],
        "excludedFromAcceptedBaseline": ["361000"],
        "regions": {
            "360100": {"name": "南昌", "semanticSvg": "dist/assets/nanchang/nanchang-semantic.svg", "status": "accepted-reference"},
            "360400": {"name": "九江", "semanticSvg": "dist/assets/jiujiang/jiujiang-semantic.svg", "status": "accepted-reference"},
            "361100": {"name": "上饶", "semanticSvg": "dist/assets/shangrao/shangrao-semantic.svg", "status": "accepted-after-fixed-scale-regeneration"},
            "360200": {"name": "景德镇", "semanticSvg": "dist/assets/jingdezhen/jingdezhen-semantic.svg", "status": "accepted-after-shangrao"},
        },
        "rules": {"acceptedInteriorIsImmutable": True, "regionalGenerationInput": "fixed-175-page-unit-window-context-plus-binary-edit-mask", "restoreBlackMaskPixelsAfterGeneration": True, "fuzhouMayNotBeUsedAsReference": True},
    }
    write_json("artwork/semantic-joint-state.json", state)
    accepted = read_json("artwork/accepted-generation.json")
    accepted["jointSemantic"] = {"path": joint, "sha256": sha(joint)}
    accepted["acceptedOrder"] = ["360100", "360400", "361100", "360200"]
    accepted["excludedFromAcceptedBaseline"] = ["361000"]
    accepted["regions"].pop("361000", None)
    accepted["regions"]["361100"] = {"name": "上饶", "version": "v3", "plan": "artwork/generation-inputs/shangrao/fixed-scale-tiles/shangrao-plan.json", "planSha256": sha("artwork/generation-inputs/shangrao/fixed-scale-tiles/shangrao-plan.json"), "promptFiles": ["artwork/prompts/base.md", "artwork/prompts/shangrao-west.md", "artwork/prompts/shangrao-northeast.md", "artwork/prompts/shangrao-southeast.md", "artwork/prompts/shangrao-fixed-v3.md"], "finalImage": "dist/assets/shangrao/shangrao-art-final-v3.webp", "finalSha256": sha("dist/assets/shangrao/shangrao-art-final-v3.webp"), "generationMode": "fixed-scale-two-image-edit"}
    accepted["regions"]["360200"] = {"name": "景德镇", "version": "v2", "plan": "artwork/generation-inputs/jingdezhen/fixed-scale-tiles/jingdezhen-plan.json", "planSha256": sha("artwork/generation-inputs/jingdezhen/fixed-scale-tiles/jingdezhen-plan.json"), "promptFiles": ["artwork/prompts/base.md", "artwork/prompts/jingdezhen-fixed-v2.md"], "finalImage": "dist/assets/jingdezhen/jingdezhen-art-final-v2.webp", "finalSha256": sha("dist/assets/jingdezhen/jingdezhen-art-final-v2.webp"), "generationMode": "fixed-scale-two-image-edit"}
    accepted["regions"] = {k: accepted["regions"][k] for k in ["360100", "360400", "361100", "360200"]}
    write_json("artwork/accepted-generation.json", accepted)


def update_page():
    app = ROOT / "dist/landscape-app.js"
    text = app.read_text().replace("南昌、九江、抚州与上饶", "南昌、九江、上饶与景德镇")
    app.write_text(text)
    index = ROOT / "dist/index.html"
    text = re.sub(r"landscape-app\.js\?v=\d+", "landscape-app.js?v=8", index.read_text())
    index.write_text(text)
    (ROOT / "docs/GITHUB-PAGES-SYNC.md").write_text("""# GitHub Pages publication

GitHub Pages publishes `main` from `dist/`. The accepted fixed-scale sequence is Nanchang v6, Jiujiang v7, Shangrao v3, then Jingdezhen v2. Fuzhou is excluded from the accepted baseline and from all generation references.

Every regenerated region uses a 175 × 175 page-unit window rendered to a 2048 × 2048 semantic context plus a same-size strict binary edit mask. Model results are normalized to 1254 × 1254, all black-mask pixels are deterministically restored, multi-window regions are merged in balanced page coordinates, and the final raster is cropped to canonical path bounds without stretching.

Keep `dist/index.html`, `landscape-app.js`, `jiangxi-city-tiles.json`, manifests and every referenced image in the same commit. Versioned image names and the script query string must change together to avoid stale Pages/CDN assets.
""")


def main():
    finalize_plan("shangrao", "v3")
    finalize_plan("jingdezhen", "v2")
    joint = build_joint()
    build_workflows(joint)
    build_manifests()
    build_tiles()
    build_state(joint)
    update_page()
    print(json.dumps({"joint": joint, "jointSha256": sha(joint), "shangrao": sha("dist/assets/shangrao/shangrao-art-final-v3.webp"), "jingdezhen": sha("dist/assets/jingdezhen/jingdezhen-art-final-v2.webp")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
