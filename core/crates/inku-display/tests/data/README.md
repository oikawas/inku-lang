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

`linear-gradient-wash` and `linear-gradient-field` are the two linear gradients the
core writes (the ink-wash ground's bands, and the computer fill with
`color-interpolation="sRGB"`), drawn large and without noise (2026-10-12). Chrome
154.0.8037.99 made their pictures the same way. Without their gradient fills they do
not match Chrome, so the test sees the gradients.

`dash-offset` is the dashes the canvas ground writes (`stroke-dasharray` with
`stroke-dashoffset`, I-723), drawn large and dark (2026-10-17). Chrome 155.0.8059.80
made its picture the same way. Without its offsets it does not match Chrome, so the
test sees them.

`user-space-gradient` is the painting knife's thinning: linear gradients with
`gradientUnits="userSpaceOnUse"`, numeric endpoints and one colour fading in opacity.
`round-join` is the round join used by etching lines and the media's ridges, with
thick strokes and acute corners. Both are large, dark, noise-free synthetic pictures
(2026-11-01). Chrome 156.0.8078.74 made their pictures the same way as C1, each at
200 × 200 pixels. Removing `gradientUnits` restores objectBoundingBox; removing
`stroke-linejoin` restores miter. Neither control matches Chrome under the same
yardstick. The Skia/Chrome C2 comparison keeps both pictures unchanged.

The CPU/Graphite comparison at 1x and in a 4x window uses `user-space-gradient` and
`round-join-gentle`. The latter keeps the same stroke width and round caps and joins,
with 90-degree corners. Along steep lines (about 74 degrees), CPU and Graphite edge
coverage differs at 1x regardless of join shape: miter differs in 0.725% of pixels,
and thin round lines in 0.60-0.64%, above the 0.5% yardstick (I-726). This is why
Graphite uses the gentler picture. It is compared only with the CPU and has no
Chrome reference image. The original acute picture and its Chrome reference remain
in C2.

## `public-requests.json` (C6)

The 17 public DDL texts of stage 1 (with where each was taken from) and the exact
compile and render inputs the macOS app built for them: the shared macro definitions,
locks, compiler options and clip policy once, and each work's host options (canvas and
palette) and render options. The C6 test draws them again with the current core.
The plugin calls in `p02` and `p03` use the current braced notation; their
historical `public/` SVG and Chrome images remain the original stage 1 captures.
