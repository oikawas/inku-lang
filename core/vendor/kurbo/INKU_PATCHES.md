# inku changes to kurbo 0.13.1

This directory vendors the published `kurbo 0.13.1` crate from
<https://crates.io/crates/kurbo/0.13.1>. The upstream MIT and Apache-2.0
licenses are included unchanged. Cargo registry metadata, `Cargo.toml.orig`
and the upstream crate's standalone lockfile are omitted; `core/Cargo.lock`
pins dependencies. `core/Cargo.toml` puts it in place of the crates.io kurbo
with `[patch.crates-io]`, so usvg, svgtypes and inku-render all use it.

## Why (I-733, 2026-11-07)

Upstream kurbo calls `f64::sin`, `hypot`, `atan2` and the other float methods
of std when its `std` feature is on, and libm through its `FloatFuncs` trait
only without std. Those std methods call the host's C library (Apple libm,
bionic, glibc), whose answers differ in the last bit between hosts: measured
between macOS and the Linux of 5173, 4% of `sin`'s and 10% of `hypot`'s
answers differed, and the Compat SVG of three works of 29 differed, where the
Compat clip (`inku-render/src/compat_clip.rs`) strokes outlines with
`kurbo::stroke` and turns ellipses into paths with `kurbo::Ellipse`. usvg
asks for kurbo's default features, which include `std`, and every host build
of the core contains usvg, so a feature setting alone cannot turn libm on.

## The change

- Every `feature = "std"` test in `src/` reads `feature = "inku-host-std"`,
  a feature nobody enables. kurbo therefore always builds as `no_std` and
  computes with libm through `FloatFuncs`, whatever asks for `std`.
- `Cargo.toml`: `default = ["libm"]`, `std = ["libm"]` (kept so svgtypes'
  `kurbo/std` and usvg's default features resolve), `inku-host-std = []`.
  `std` no longer turns on `polycool/std` and `euclid?/std`; polycool then
  computes with libm too.
- `BezPath::to_svg` (`src/svg.rs`), which upstream has only with std, is
  kept without std and writes the same text. `BezPath::write_to`, which needs
  `std::io`, is gone; nothing in the core calls it.

How to check after an upgrade: build kurbo with
`scripts/rust-toolchain.sh rustc -p kurbo --lib -- -D unused_imports`. If
anything in kurbo's dependency graph brought std's float methods back, they
would win over `FloatFuncs` and its imports would become unused.
