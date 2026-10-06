# Skia and its third-party code (skia-bindings 0.153.3)

The Skia prebuilt binaries that `skia-bindings` 0.153.3 links carry only
`LICENSE_SKIA`. The texts here are for what is compiled into them, copied unmodified
from the Skia source of that release: `rust-skia/skia` tag `m153-0.101.2`
(`skia-bindings` `[package.metadata] skia`) and the `third_party/externals`
revisions its `DEPS` pins. `skia-LICENSE` is identical to the binaries' `LICENSE_SKIA`.

Each library was found by its symbols in the built `libskia*.a` archives
(macOS arm64, features svg and webp, 2026-10-06); FreeType and Brotli are not in them.

| File | Library | Version | DEPS revision |
|---|---|---|---|
| `skia-LICENSE` | Skia | m153 | rust-skia/skia `m153-0.101.2` |
| `expat-COPYING` | Expat | 2.7.4 | `6154446fccefbf3ca644894f598969113b0c7bcd` |
| `harfbuzz-COPYING`, `harfbuzz-ms-use-COPYING` | HarfBuzz | 13.1.0 | `9cb1fee51069b206effb4736e443b038d230789d` |
| `icu-LICENSE` | ICU | 78.2 | `d578f2e8b7bd5938e21cfb6bf15c079e0aa5b738` |
| `libpng-LICENSE` | libpng | 1.6.56 | `d5515b5b8be3901aac04e5bd8bd5c89f287bcd33` |
| `zlib-LICENSE` | zlib (Chromium) | 1.3.0.1 | `646b7f569718921d7d4b5b8e22572ff6c76f2596` |
| `libjpeg-turbo-LICENSE.md`, `libjpeg-turbo-README.ijg` | libjpeg-turbo | 3.1.0 | `e14cbfaa85529d47f9f55b0f104a579c1061f9ad` |
| `libwebp-COPYING`, `libwebp-PATENTS` | libwebp | 1.4.0 | `845d5476a866141ba35ac133f856fa62f0b7445f` |
| `wuffs-LICENSE` | Wuffs | 0.3.3 (`wuffs-v0.3.c`) | `e3f919ccfe3ef542cfc983a82146070258fb57f8` |

HarfBuzz builds `hb-ot-shaper-use.cc`, whose table is generated in part from the
Microsoft data under `src/ms-use`, so that MIT text is included. The other
`COPYING` files under HarfBuzz belong to its tests, which are not built.

`../rust-skia-0.153.3-LICENSE` is the rust-skia repository's `LICENSE` at tag
`0.153.3`; the `skia-safe`, `skia-bindings` and `skia-svg-macros` crate archives
have no license file.

Android's prebuilt binaries (GPU) combine other parts; count them again there.
