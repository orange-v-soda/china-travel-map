# GitHub Pages publication

GitHub Pages publishes `main` from `dist/`. The accepted fixed-scale sequence is Nanchang v6, Jiujiang v7, Shangrao v3, then Jingdezhen v2. Fuzhou is excluded from the accepted baseline and from all generation references.

Every regenerated region uses a 175 × 175 page-unit window rendered to a 2048 × 2048 semantic context plus a same-size strict binary edit mask. Model results are normalized to 1254 × 1254, all black-mask pixels are deterministically restored, multi-window regions are merged in balanced page coordinates, and the final raster is cropped to canonical path bounds without stretching.

Keep `dist/index.html`, `landscape-app.js`, `jiangxi-city-tiles.json`, manifests and every referenced image in the same commit. Versioned image names and the script query string must change together to avoid stale Pages/CDN assets.
