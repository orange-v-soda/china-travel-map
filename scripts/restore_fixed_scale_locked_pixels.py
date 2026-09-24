#!/usr/bin/env python3
"""Restore immutable context pixels after an image-generation window returns."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated", type=Path)
    parser.add_argument("context", type=Path)
    parser.add_argument("editable_mask", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    generated = Image.open(args.generated).convert("RGB")
    context = Image.open(args.context).convert("RGB")
    editable = Image.open(args.editable_mask).convert("L")
    if context.size != generated.size:
        context = context.resize(generated.size, Image.Resampling.LANCZOS)
    if editable.size != generated.size:
        editable = editable.resize(generated.size, Image.Resampling.NEAREST)
    editable = editable.point(
        lambda value: 255 if value >= 128 else 0
    )

    # White mask pixels come from the model; black pixels are copied verbatim
    # from the context, including accepted overlap and all out-of-target areas.
    restored = Image.composite(generated, context, editable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    restored.save(args.output)


if __name__ == "__main__":
    main()
