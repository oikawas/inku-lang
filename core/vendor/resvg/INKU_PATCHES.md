# inku changes to resvg 0.48.1

This directory vendors the published `resvg 0.48.1` crate from
<https://crates.io/crates/resvg/0.48.1>, corresponding to upstream commit
`68b14c4c3bccdb60344c777406486b54c36ec1a4` in
<https://github.com/linebender/resvg>. The upstream MIT and Apache-2.0 licenses
are included unchanged. Cargo registry metadata and the upstream crate's
standalone lockfile are omitted; `core/Cargo.lock` pins dependencies.
The README's chart links point to the upstream commit because the published
crate does not include those images.

The local patch is confined to `src/filter/turbulence.rs`. It computes the
lattice coordinates and interpolation weights once per pixel and octave,
then evaluates RGBA together. Gradient vectors are stored contiguously in
channel order instead of thousands of small allocations. Seed generation,
per-channel floating-point operation order, stitching, octave accumulation,
clamping, and byte rounding retain the upstream behavior. It adds no threads
or unsafe code and does not lower the raster resolution.

`inku-svg-raster` keeps the published resvg 0.48.1 as a test-only dependency.
Its `raster_equivalence` integration test compares every pixel with that
independent upstream renderer at preview resolution, including stitched
turbulence and the zero-octave boundary. When updating resvg, compare the
upstream algorithm and re-evaluate this patch instead of silently carrying it
onto a different implementation.

On Linux, run the focused comparison with
`scripts/rust-toolchain.sh test --locked --release -p inku-svg-raster --test raster_equivalence -- --nocapture`.
The `raster-profile` example measures parsing and rasterization separately and
emits raw-pixel SHA-256 digests; image comparisons run on Linux. Android's
`SvgRasterPerformanceTest` measures the packaged JNI path and Bitmap transfer
at preview resolution through the safe instrumentation runner.
