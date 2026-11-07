# inku changes to svgtypes 0.16.1

This directory vendors the published `svgtypes 0.16.1` crate from
<https://crates.io/crates/svgtypes/0.16.1>. The upstream MIT and Apache-2.0
licenses are included unchanged. Cargo registry metadata, `Cargo.toml.orig`
and the upstream crate's standalone lockfile are omitted; `core/Cargo.lock`
pins dependencies. `core/Cargo.toml` puts it in place of the crates.io
svgtypes with `[patch.crates-io]`.

## Why (I-733, 2026-11-07)

svgtypes is `no_std` and, with its `std` feature, called the float methods of
std that a std kurbo brought into scope: `cos`, `sin` and `tan` for a
transform's `rotate`, `skewX` and `skewY`, and `round` for colors. Those call
the host's C library, whose answers differ between hosts in the last bit.
With the vendored kurbo always `no_std` (see `../kurbo/INKU_PATCHES.md`), those
methods are not in scope at all.

## The change

- `src/color.rs` and `src/transform.rs` import `kurbo::common::FloatFuncs`
  whatever the features (their `feature = "std"` test reads
  `feature = "inku-host-std"`, a feature nobody enables), so svgtypes computes
  with kurbo's libm functions.
- `Cargo.toml` declares `inku-host-std = []`. The other features are as
  upstream.
