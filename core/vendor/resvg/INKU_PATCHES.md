# inku changes to resvg 0.48.1

This directory vendors the published `resvg 0.48.1` crate from
<https://crates.io/crates/resvg/0.48.1>, corresponding to upstream commit
`68b14c4c3bccdb60344c777406486b54c36ec1a4` in
<https://github.com/linebender/resvg>. The upstream MIT and Apache-2.0 licenses
are included unchanged. Cargo registry metadata and the upstream crate's
standalone lockfile are omitted; `core/Cargo.lock` pins dependencies.
The README's chart links point to the upstream commit because the published
crate does not include those images.

There are two local patches. The displacement patch (2026-10-31) is confined
to `src/filter/displacement_map.rs` and `apply_displacement_map` in
`src/filter/mod.rs`, and backports upstream's fix (resvg CHANGELOG, Unreleased
after 0.49.0, #1157: "`feDisplacementMap` no longer applies `scale` twice", and
the map is read with non-premultiplied colors). resvg 0.48.1 multiplied the
`scale` attribute in twice and read the map premultiplied, so with scale `s`
it moved a pixel by `s * s` times the premultiplied channel where Chrome and
Skia move it by `s` times the plain channel: a scale of 8 moved a square 32 px
in resvg 0.48.1 and 4 px in Chrome. The patch takes upstream's two changes as
they are. Every `feDisplacementMap` drawn by `inku-svg-raster` (Android's
thumbnails, exports and pictures for a model, and works outside the display
table) now moves pixels as the screens do; today's tools, whose displacement
scales are about 1.0 to 2.4, move theirs about that many times less than
before. The media of Saijiki v3 write the look resvg 0.48.1 gave them as a
specification displacement (`inku-render/src/media.rs`, `Displacement`), so
they must not be drawn by an unpatched resvg 0.48.1 (the Server's `resvg_py`).

The turbulence patch is confined to `src/filter/turbulence.rs` and its Rayon
dependency in `Cargo.toml`. It computes lattice coordinates and interpolation
weights once per axis and octave, then evaluates RGBA together. Gradient
vectors are stored contiguously in channel order instead of thousands of
small allocations. An eight-entry LRU cache reuses the seed-dependent lattice
and gradients across filters. At most 200,000 axis entries are retained during
a filter; larger tables use the original constant-memory pixel path.

Regions of at least 32,768 pixels and 65,536 pixel-octaves can use a single
lazy Rayon pool capped at four workers on macOS and two on other targets,
clamped to available CPU parallelism. Smaller regions stay sequential, and
pool construction failure falls back to the sequential path. Android always
executes prepared rows sequentially: the
shared row workers regressed representative Pixel 9 preview latency. Other
targets share the pool across concurrent renders, not per filter. Seed generation, per-channel floating-point operation order,
stitching (including coordinate-dependent wraps), octave accumulation,
clamping, and byte rounding retain upstream behavior. The patch adds no
unsafe code and does not lower raster resolution.

On macOS, the public pencil fixture at 4320 by 4320 pixels with nine
2048-side tiles had a warm mean region-render time of 3750.519 ms with two
workers and 3035.656 ms with four, about 19% shorter. Each policy was measured
for one initial cold iteration and two warm iterations; preparation time was
reported separately. The SHA-256 of all nine tiles' raw bytes in fixed
row-major tile order matched in all three iterations of both policies:
`500af047a9007eda3ac11690185c6ea242085a9ff6fdb42c01c71ad236acdb2e`.
This is a limited result for one public fixture and one fixed workload, not
evidence of optimal performance for all Macs or works, or lower app memory.

`inku-svg-raster` keeps the published resvg 0.48.1 as a test-only dependency.
Its `raster_equivalence` integration test compares every pixel with that
independent upstream renderer at preview resolution, including a full region
above the parallel threshold, stitched turbulence below that threshold, and
the zero-octave boundary. Its fixtures set every `feDisplacementMap` scale to
0 before both renders, since the displacement patch departs from 0.48.1 on
purpose; a separate test pins the displacement patch to the specification's
amount. When updating resvg, compare the
upstream algorithm and re-evaluate this patch instead of silently carrying it
onto a different implementation.

On Linux, run the focused comparison with
`scripts/rust-toolchain.sh test --locked --release -p inku-svg-raster --test raster_equivalence -- --nocapture`.
`INKU_RASTER_EQUIVALENCE_CASE` selects one named case; absent preserves the
five-case default and an unknown name fails. The macOS worker-policy check
selected only `parallel-full-region` and found zero changed pixels against
upstream. From the product checkout, reproduce that check and the fixed
pencil-only measurement with:

```sh
INKU_RASTER_EQUIVALENCE_CASE=parallel-full-region scripts/rust-toolchain.sh test --release --locked --offline -p inku-svg-raster --test raster_equivalence optimized_turbulence_preserves_upstream_images -- --exact --nocapture
scripts/rust-toolchain.sh run --release --locked --offline -p inku-svg-raster --example prepared-scene-profile -- ../server/reference/render-engine-41/C-filter-display-pencil.svg 3 --pencil-tiles-only
```

The `raster-profile` example measures parsing and rasterization separately and
emits raw-pixel SHA-256 digests; image comparisons run on Linux. Android's
`SvgRasterPerformanceTest` measures the packaged JNI path and Bitmap transfer
at preview resolution through the safe instrumentation runner.

The Server and the CLI draw their PNGs with this crate through the Python
wheel (`inku_render.svg_to_png`) and record `inku_render.raster_identity_json()`
beside them: this crate's version and `inku.N`, N being the count of local
patches above (`0.48.1+inku.2`). A new version or a new patch changes
`RASTER_IDENTITY` in `inku-render-python/src/lib.rs` in the same commit; its
test reads this file and the vendored `Cargo.toml`.
