# SVG-controlled city tiles

The accepted SVG path is authoritative, not the outline invented by ImageGen.
Generate each city for its final layout directly. The job records the exact path,
path SHA-256, bounds, canvas aspect ratio and valid visible neighbors.

`node scripts/city-svg-pipeline.cjs prepare 360100 balanced` creates the actual
generation context and silhouette. Use these as references with unchanged framing.
`node scripts/city-svg-pipeline.cjs finalize 360100 balanced INPUT.png` creates
a self-contained clipped SVG and transparent PNG. It rejects stale geometry and
changed aspect ratios and checks for visible pixels outside the mask.

Containment is deterministic. River centerlines, landmark alignment and full
interior paint coverage still require review. Generated transparency and model
drawn outlines must not be mistaken for exact masks. A tile with uncovered interior
or shifted geography must not be accepted merely because outside pixels are zero.

Only accepted entries in `dist/jiangxi-city-tiles.json` render as city artwork.
Entries include id, layout, path, pathSha256, bounds, image and status. Runtime
requires an exact path and layout match and applies that city's original clip.
Each legacy triangle is also confined to its own city's path. Export embeds every
image and preserves the same clips. Existing whole-province art remains legacy
until replacements pass content review; rejected Nanchang variants are not live.

Nanchang balanced trial: 0 visible pixels outside mask, 0 uncovered fully interior pixels at 1536 x 1536. Shape is unchanged. ImageGen needed a second fill pass because its own outline omitted 3.56% of the SVG interior. The final candidate is not in the accepted manifest.
