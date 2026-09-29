#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ORDER = ["360100", "360400", "361100", "360200"]


def load(path):
    return json.loads((ROOT / path).read_text())


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def require(ok, message, errors):
    if not ok:
        errors.append(message)


def validate_region(slug, region, version, expected_refs, errors):
    plan_path = f"artwork/generation-inputs/{slug}/fixed-scale-tiles/{slug}-plan.json"
    plan = load(plan_path)
    require(plan["region"] == region, f"{slug}: wrong region", errors)
    require(all(w["canvasPixels"] == [2048, 2048] for w in plan["windows"]), f"{slug}: non-2048 context", errors)
    require(all(w["worldBounds"][2:] == [175.0, 175.0] for w in plan["windows"]), f"{slug}: non-175 window", errors)
    refs = [x["region"] for x in plan["neighborArt"]]
    require(refs == expected_refs, f"{slug}: reference order {refs} != {expected_refs}", errors)
    require("361000" not in refs, f"{slug}: Fuzhou used as reference", errors)
    require(plan["generationProtocol"]["inputCount"] == 2, f"{slug}: not a two-image edit", errors)
    require(plan["generationProtocol"]["restoreBlackMaskPixels"] is True, f"{slug}: restoration disabled", errors)
    for window in plan["windows"]:
        idx = window["index"]
        context_path = ROOT / window["context"]
        visible_path = ROOT / window["visibleMask"]
        edit_path = ROOT / window["editMask"]
        restored_path = ROOT / f"artwork/generated/{slug}/{slug}-fixed-scale-window-{idx:02d}-{version}-restored.png"
        for p in (context_path, visible_path, edit_path, restored_path):
            require(p.is_file(), f"{slug}: missing {p.relative_to(ROOT)}", errors)
        if not all(p.is_file() for p in (context_path, edit_path, restored_path)):
            continue
        context = Image.open(context_path).convert("RGBA").resize((1254, 1254), Image.Resampling.LANCZOS)
        edit = Image.open(edit_path).convert("L").resize((1254, 1254), Image.Resampling.NEAREST)
        restored = Image.open(restored_path).convert("RGBA")
        require(restored.size == (1254, 1254), f"{slug}: restored window {idx} is not 1254 square", errors)
        immutable = ImageChops.invert(edit)
        delta = ImageChops.difference(context, restored)
        locked_delta = ImageChops.multiply(delta, Image.merge("RGBA", (immutable, immutable, immutable, immutable)))
        require(locked_delta.getbbox() is None, f"{slug}: window {idx} changed black-mask pixels", errors)
    final = ROOT / f"dist/assets/{slug}/{slug}-art-final-{version}.webp"
    require(final.is_file(), f"{slug}: final image missing", errors)
    if final.is_file():
        expected_size = (round(plan["canonicalPathBounds"][2] * 7.1657142857142855), round(plan["canonicalPathBounds"][3] * 7.1657142857142855))
        require(Image.open(final).size == expected_size, f"{slug}: final image was stretched", errors)
    accepted = load("artwork/accepted-generation.json")["regions"][region]
    require(accepted["version"] == version, f"{slug}: accepted version mismatch", errors)
    require(accepted["planSha256"] == digest(plan_path), f"{slug}: plan checksum mismatch", errors)
    require(accepted["finalSha256"] == digest(f"dist/assets/{slug}/{slug}-art-final-{version}.webp"), f"{slug}: final checksum mismatch", errors)


def main():
    errors = []
    fixed = load("artwork/fixed-scale-generation.json")
    require(fixed["canvasPixels"] == [2048, 2048], "global canvas must be 2048 square", errors)
    require(fixed["normalizedGeneratedPixels"] == [1254, 1254], "normalized output must be 1254 square", errors)
    require(fixed["worldSpan"] == [175.0, 175.0], "world span must be 175 square", errors)
    accepted = load("artwork/accepted-generation.json")
    require(accepted["acceptedOrder"] == EXPECTED_ORDER, "accepted order is wrong", errors)
    require(accepted.get("excludedFromAcceptedBaseline") == ["361000"], "Fuzhou exclusion missing", errors)
    require("361000" not in accepted["regions"], "Fuzhou remains accepted", errors)
    tiles = load("dist/jiangxi-city-tiles.json")
    require([x["id"] for x in tiles] == EXPECTED_ORDER, "published raster order is wrong", errors)
    validate_region("shangrao", "361100", "v3", ["360100", "360400"], errors)
    validate_region("jingdezhen", "360200", "v2", ["360100", "360400", "361100"], errors)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("OK: strict fixed-scale sequence Nanchang -> Jiujiang -> Shangrao v3 -> Jingdezhen v2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
