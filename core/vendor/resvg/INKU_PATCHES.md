# inku changes to resvg 0.48.1

This directory vendors the published `resvg 0.48.1` crate from
<https://crates.io/crates/resvg/0.48.1>, corresponding to upstream commit
`68b14c4c3bccdb60344c777406486b54c36ec1a4` in
<https://github.com/linebender/resvg>. The upstream MIT and Apache-2.0 licenses
are included unchanged. Cargo registry metadata and the upstream crate's
standalone lockfile are omitted; `core/Cargo.lock` pins dependencies.
The README's chart links point to the upstream commit because the published
crate does not include those images.

The local patch is confined to `src/filter/turbulence.rs` and its Rayon
dependency in `Cargo.toml`. It computes lattice coordinates and interpolation
weights once per axis and octave, then evaluates RGBA together. Gradient
vectors are stored contiguously in channel order instead of thousands of
small allocations. An eight-entry LRU cache reuses the seed-dependent lattice
and gradients across filters. At most 200,000 axis entries are retained during
a filter; larger tables use the original constant-memory pixel path.

Regions of at least 32,768 pixels and 65,536 pixel-octaves can use a single
lazy Rayon pool capped at two workers and available CPU parallelism. Smaller
regions stay sequential, and pool construction failure falls back to the
sequential path. Android always executes prepared rows sequentially: the
shared row workers regressed representative Pixel 9 preview latency. Other
targets share the pool across concurrent renders, not per filter. Seed generation, per-channel floating-point operation order,
stitching (including coordinate-dependent wraps), octave accumulation,
clamping, and byte rounding retain upstream behavior. The patch adds no
unsafe code and does not lower raster resolution.

`inku-svg-raster` keeps the published resvg 0.48.1 as a test-only dependency.
Its `raster_equivalence` integration test compares every pixel with that
independent upstream renderer at preview resolution, including a full region
above the parallel threshold, stitched turbulence below that threshold, and
the zero-octave boundary. When updating resvg, compare the
upstream algorithm and re-evaluate this patch instead of silently carrying it
onto a different implementation.

On Linux, run the focused comparison with
`scripts/rust-toolchain.sh test --locked --release -p inku-svg-raster --test raster_equivalence -- --nocapture`.
The `raster-profile` example measures parsing and rasterization separately and
emits raw-pixel SHA-256 digests; image comparisons run on Linux. Android's
`SvgRasterPerformanceTest` measures the packaged JNI path and Bitmap transfer
at preview resolution through the safe instrumentation runner.
