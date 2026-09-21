#!/usr/bin/env python3
"""Validate the repository's SVG-first regional artwork contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED_STAGES = [
    "lock-project-outline",
    "map-real-geography",
    "draw-semantic-svg",
    "generate-raster-from-svg",
    "apply-exact-mask-and-clean",
    "publish-raster-only",
]


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    workflow_path = args.workflow if args.workflow.is_absolute() else repo / args.workflow
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if data.get("schemaVersion") != 1:
        fail(errors, "schemaVersion must be 1")
    if data.get("stages") != EXPECTED_STAGES:
        fail(errors, "workflow stages must use the fixed SVG-first order")

    artifacts = data.get("artifacts", {})
    required = ("semanticSvg", "maskSvg", "manifest", "finalImage", "tileManifest")
    for key in required:
        value = artifacts.get(key)
        if not value:
            fail(errors, f"missing artifact entry: {key}")
        elif not (repo / value).is_file():
            fail(errors, f"artifact does not exist: {value}")

    for key in ("semanticSvg", "maskSvg"):
        value = artifacts.get(key)
        if value and (repo / value).is_file():
            text = (repo / value).read_text(encoding="utf-8")
            if "<svg" not in text or "</svg>" not in text:
                fail(errors, f"{key} is not a complete SVG: {value}")

    final_image = artifacts.get("finalImage", "")
    if Path(final_image).suffix.lower() not in {".png", ".webp"}:
        fail(errors, "finalImage must be PNG or WebP")

    limit = data.get("rules", {}).get("maxLandmarksPerIndependentArea")
    for area in data.get("independentAreas", []):
        landmarks = area.get("landmarks", [])
        if not isinstance(limit, int) or len(landmarks) > limit:
            fail(errors, f"area {area.get('id')} exceeds landmark limit {limit}")
        for landmark in landmarks:
            if not landmark.get("placementRule"):
                fail(errors, f"landmark {landmark.get('name')} lacks a placementRule")

    for value in data.get("forbiddenPublicArtifacts", []):
        if (repo / value).exists():
            fail(errors, f"construction overlay must not be published: {value}")

    tile_path = artifacts.get("tileManifest")
    if tile_path and (repo / tile_path).is_file():
        tiles = json.loads((repo / tile_path).read_text(encoding="utf-8"))
        region = data.get("region", {})
        matches = [
            tile for tile in tiles
            if tile.get("id") == region.get("id")
            and tile.get("layout") == region.get("layout")
            and tile.get("status") == "accepted"
        ]
        expected_image = final_image.removeprefix("dist/")
        if len(matches) != 1:
            fail(errors, "tile manifest must contain exactly one accepted region/layout entry")
        elif matches[0].get("image") != expected_image:
            fail(errors, f"page must load only the final raster: {expected_image}")

    rules = data.get("rules", {})
    if rules.get("semanticSvgPrecedesGeneration") is not True:
        fail(errors, "semanticSvgPrecedesGeneration must be true")
    if rules.get("finalPageLoadsRasterOnly") is not True:
        fail(errors, "finalPageLoadsRasterOnly must be true")
    if rules.get("constructionGuidesVisibleInFinal") is not False:
        fail(errors, "constructionGuidesVisibleInFinal must be false")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {data['region']['name']} follows the SVG-first artwork workflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
