#!/usr/bin/env python3
"""Apply the page-authoritative SVG mask and remove generated guide outlines."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("mask", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--guide-width", type=int, default=7)
    args = parser.parse_args()

    image = Image.open(args.source).convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    mask = Image.open(args.mask).convert("L").resize((1024, 1024), Image.Resampling.NEAREST)
    mask_arr = np.asarray(mask) >= 128
    if args.guide_width <= 0:
        inner = mask_arr.copy()
    else:
        kernel = args.guide_width * 2 + 1
        inner = np.asarray(mask.filter(ImageFilter.MinFilter(kernel))) >= 128

    rgba = np.asarray(image).copy()
    known = inner.copy()
    target = mask_arr.copy()
    # Propagate real interior paint through the narrow guide-line band.  This
    # removes the visible SVG outline without synthesising or moving geography.
    while np.any(target & ~known):
        sums = np.zeros_like(rgba[:, :, :3], dtype=np.uint32)
        counts = np.zeros(mask_arr.shape, dtype=np.uint16)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted_known = np.roll(known, (dy, dx), axis=(0, 1))
            shifted_rgb = np.roll(rgba[:, :, :3], (dy, dx), axis=(0, 1))
            sums += shifted_rgb * shifted_known[:, :, None]
            counts += shifted_known
        grow = target & ~known & (counts > 0)
        rgba[grow, :3] = (sums[grow] / counts[grow, None]).astype(np.uint8)
        known |= grow
    rgba[:, :, 3] = np.where(mask_arr, 255, 0).astype(np.uint8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(args.output)


if __name__ == "__main__":
    main()
