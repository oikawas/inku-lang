# inku-display test data

All of it comes from public sources in this repository; no saved user work is here.

## `public/` (C1, C4)

`p00`, `p02`, `p07` and `p11` are four of the 17 public works of Skia display stage 1
(2026-10-06). The core of product `d9cd41978e26ce6d1cbce0c68e95ad5eecdea7a9` drew them
from the DDL in `public-requests.json`, through the macOS app's compile and render
boundary. Together they write every compatibility case:

| Work | Case |
|---|---|
| `p00` | `use` and `pattern` with SVG2 `href`, an alpha mask with white content |
| `p02` | `stitchTiles="stitch"` (Skia does not read it; it matches anyway) |
| `p07` | the paper ground's ellipses with a default-unit radial gradient |
| `p11` | seeds that Blink and Skia read as different integers |

`*-chrome.png` is how Chrome drew each SVG, made once and kept: Chrome 154.0.8037.98,
`--headless=new --disable-gpu --force-device-scale-factor=1`, the SVG as an `<img>`
at its own size on a white page. Do not redraw them with Skia.

## `compat/` (C2)

One small SVG per rewrite (`pattern-href`, `use-href`, `ellipse-gradient`, `seed`,
`alpha-mask-white`) and the control `alpha-mask-gray`, with Chrome's pictures made
the same way. The seed `253038826` is one of `p11`'s: Blink reads it as 253038816,
Skia as 253038832. Seeds above 2^31 drew the same noise either way.

## `public-requests.json` (C6)

The 17 public DDL texts of stage 1 (with where each was taken from) and the exact
compile and render inputs the macOS app built for them: the shared macro definitions,
locks, compiler options and clip policy once, and each work's host options (canvas and
palette) and render options. The C6 test draws them again with the current core.
