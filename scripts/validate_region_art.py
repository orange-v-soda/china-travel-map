#!/usr/bin/env python3
"""Validate the repository's SVG-first regional artwork contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXPECTED_STAGES_V3 = [
    "lock-project-outline",
    "map-real-geography",
    "draw-semantic-svg",
    "build-global-scale-context",
    "tile-at-fixed-global-scale",
    "generate-raster-windows-from-svg",
    "merge-windows-in-page-space",
    "apply-final-safety-clip-and-clean",
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

    schema_version = data.get("schemaVersion")
    if schema_version != 3:
        fail(errors, "schemaVersion must be 3; legacy regional workflows are unsupported")
    if data.get("stages") != EXPECTED_STAGES_V3:
        fail(errors, "workflow stages must use the current fixed-scale SVG-first order")

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
    elif (repo / final_image).is_file() and (repo / final_image).stat().st_size > 600_000:
        fail(errors, "finalImage exceeds the safe static-deployment upload size (600 KB)")

    limit = data.get("rules", {}).get("maxLandmarksPerIndependentArea")
    for area in data.get("independentAreas", []):
        landmarks = area.get("landmarks", [])
        if not isinstance(limit, int) or len(landmarks) > limit:
            fail(errors, f"area {area.get('id')} exceeds landmark limit {limit}")
        for landmark in landmarks:
            if not landmark.get("placementRule"):
                fail(errors, f"landmark {landmark.get('name')} lacks a placementRule")
            if not landmark.get("description"):
                fail(errors, f"landmark {landmark.get('name')} lacks a generation description")

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
    if rules.get("settlementEncoding") != "density-regions":
        fail(errors, "settlements must use density-regions instead of building glyphs")
    if rules.get("settlementClasses") != ["metropolitan", "county-town", "rural-farmland", "wilderness"]:
        fail(errors, "settlementClasses must define the fixed four-level hierarchy")
    if rules.get("landmarkEncoding") != "marker-plus-manifest-description":
        fail(errors, "landmarks must use markers in SVG and descriptions in metadata")
    if rules.get("regionalProfileRequired") is not True:
        fail(errors, "regionalProfileRequired must be true")
    if rules.get("waterEncoding") != "subordinate-major-network":
        fail(errors, "water must be encoded as a subordinate major network")
    if rules.get("urbanPalette") != "neutral-gray-density":
        fail(errors, "urban density regions must use a neutral gray palette")
    marker_radius = rules.get("landmarkMarkerMaxRadius")
    if not isinstance(marker_radius, (int, float)) or marker_radius > 7:
        fail(errors, "landmark markers must use a maximum radius of 7")
    if rules.get("openWaterExpansionAllowed") is not False:
        fail(errors, "open water expansion beyond semantic water shapes must be forbidden")
    if rules.get("wetlandDefaultRendering") != "non-water-is-dry-land":
        fail(errors, "every non-blue semantic region must render as dry land")
    if rules.get("waterQaRequiredBeforePublish") is not True:
        fail(errors, "water QA must be required before publishing")
    if rules.get("hydrologyTopology") != "unified-water-surface":
        fail(errors, "the workflow requires one unified water surface")
    if rules.get("riverStrokeInsideLakeAllowed") is not False:
        fail(errors, "river strokes inside lakes are forbidden")
    if rules.get("modelVisibleAdministrativeOutline") is not False:
        fail(errors, "model-visible administrative outlines are forbidden")
    if rules.get("generationMaskRole") != "final-safety-clip-only":
        fail(errors, "masks may only define editing and final safety clipping")
    if rules.get("targetGenerationMode") != "fresh-from-semantic":
        fail(errors, "targets must be generated fresh from the semantic guide")
    baseline = rules.get("globalScaleBaseline", {})
    if not isinstance(baseline.get("pixelsPerPageUnit"), (int, float)):
        fail(errors, "the workflow requires a numeric global pixel scale")
    if rules.get("semanticDrawingMode") != "crop-from-incremental-joint-master":
        fail(errors, "generation semantics must derive from the incremental joint master")
    joint_state = rules.get("jointSemanticState")
    if not joint_state or not (repo / joint_state).is_file():
        fail(errors, "the workflow requires an existing joint semantic state file")
    joint_svg = artifacts.get("jointSemanticSvg")
    if not joint_svg or not (repo / joint_svg).is_file():
        fail(errors, "the workflow requires an existing joint semantic SVG")
    elif "<g id=\"join-owned-semantics\">" not in (repo / joint_svg).read_text(encoding="utf-8"):
        fail(errors, "joint semantic SVG must contain a join-owned semantic layer")

    fixed_config = rules.get("fixedScaleConfig")
    if not fixed_config or not (repo / fixed_config).is_file():
        fail(errors, "the workflow requires an existing fixed-scale config")
    else:
        fixed = json.loads((repo / fixed_config).read_text(encoding="utf-8"))
        canvas = fixed.get("canvasPixels")
        span = fixed.get("worldSpan")
        ppu = fixed.get("pixelsPerPageUnit")
        if canvas != [2048, 2048] or span != [175.0, 175.0]:
            fail(errors, "fixed-scale config must use 2048 px over 175 page units")
        elif not isinstance(ppu, (int, float)) or abs(ppu - canvas[0] / span[0]) > 1e-12:
            fail(errors, "fixed-scale config has an inconsistent pixel density")
    plan = artifacts.get("fixedScalePlan")
    if not plan or not (repo / plan).is_file():
        fail(errors, "the workflow requires a generated fixed-scale window plan")
    if rules.get("canvasCoordinateSource") != "canonical-balanced-path":
        fail(errors, "masks must derive from the page's canonical balanced path")
    if rules.get("multipleGenerationWindowsAllowed") is not True:
        fail(errors, "the workflow must allow multiple fixed-scale windows")
    if rules.get("rasterStretchOnPublishAllowed") is not False:
        fail(errors, "raster stretching during publication is forbidden")
    if rules.get("acceptedOverlapLockedInLaterWindows") is not True:
        fail(errors, "accepted overlap must be locked in later windows")
    if rules.get("restoreLockedPixelsAfterGeneration") is not True:
        fail(errors, "locked pixels must be restored after generation")

    accepted_path = repo / "artwork/accepted-generation.json"
    if not accepted_path.is_file():
        fail(errors, "accepted generation manifest is missing")
    else:
        accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
        region_id = data.get("region", {}).get("id")
        record = accepted.get("regions", {}).get(region_id)
        if not record:
            fail(errors, f"accepted generation manifest has no record for {region_id}")
        else:
            if record.get("finalImage") != final_image:
                fail(errors, "workflow and accepted manifest disagree on finalImage")
            if record.get("plan") != artifacts.get("fixedScalePlan"):
                fail(errors, "workflow and accepted manifest disagree on fixedScalePlan")
            for prompt in record.get("promptFiles", []):
                if not (repo / prompt).is_file():
                    fail(errors, f"accepted prompt file does not exist: {prompt}")
            for path_key, hash_key in (("finalImage", "finalSha256"), ("plan", "planSha256")):
                path = repo / record[path_key]
                if path.is_file():
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != record.get(hash_key):
                        fail(errors, f"accepted checksum mismatch: {record[path_key]}")
    if rules.get("guideOutlineRemovalRequired") is not True:
        fail(errors, "the generated guide outline must be removed before publishing")
    if rules.get("adjacentGenerationMode") != "neighbor-collar-independent":
        fail(errors, "regions must use independent generation with an optional neighbor collar")
    adjacent = rules.get("adjacentRegions", [])
    if adjacent:
        fraction = rules.get("neighborContextMaximumFraction")
        if not isinstance(fraction, (int, float)) or fraction > .25:
            fail(errors, "neighbor context may occupy at most one quarter of the reference")
        if rules.get("independentRasterRequired") is not True:
            fail(errors, "each region must publish an independent raster")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {data['region']['name']} follows the SVG-first artwork workflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
