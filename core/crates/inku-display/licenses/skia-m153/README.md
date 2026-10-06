# Skia and its third-party code (skia-bindings 0.153.3)

The Skia prebuilt binaries that `skia-bindings` 0.153.3 links carry only
`LICENSE_SKIA`. The texts here are for what is compiled into them, copied unmodified
from the Skia source of that release: `rust-skia/skia` tag `m153-0.101.2`
(`skia-bindings` `[package.metadata] skia`) and the `third_party/externals`
revisions its `DEPS` pins. `skia-LICENSE` is identical to the binaries' `LICENSE_SKIA`.

The platform inventory is in `../native-libraries.json`, read by
`scripts/skia_notices.py` in the product root. The common nine libraries were
found by their symbols in the macOS arm64 archives (features svg and webp,
2026-10-06). Android's aarch64 ganesh/vulkan archives also contain FreeType and
Vulkan Memory Allocator. No Brotli or SPIRV-Cross symbols were found in those
Android archives. The application still renders on CPU surfaces.

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
| `freetype-*` | FreeType | 2.14.2 | `264b5fbf5b912b39f98d038bf75d39be0a73f21b` |
| `vulkanmemoryallocator-LICENSE.txt` | Vulkan Memory Allocator | 3.4.0 | `eb744ea7a2b17040121b4bbb4d6f9e8a77e3cae7` |

The texts are as published, except that the link to `README.ijg` in
`libjpeg-turbo-LICENSE.md` points to `libjpeg-turbo-README.ijg`, the name that file has here.

HarfBuzz builds `hb-ot-shaper-use.cc`, whose table is generated in part from the
Microsoft data under `src/ms-use`, so that MIT text is included. The other
`COPYING` files under HarfBuzz belong to its tests, which are not built.

`../rust-skia-0.153.3-LICENSE` is the rust-skia repository's `LICENSE` at tag
`0.153.3`; the `skia-safe`, `skia-bindings` and `skia-svg-macros` crate archives
have no license file.

FreeType's FTL option is selected. Its `LICENSE.TXT`, `docs/FTL.TXT`, BDF and PCF
READMEs are copied unchanged. The additional license comment blocks from
`src/base/fthash.c`, `src/autofit/ft-hb-ft.c` and `src/gzip/zlib.h` retain the MIT
and zlib copyright notices of those compiled sources.

`android-ndk-r29-LLVM-NOTICE` is the complete, unchanged `NOTICE` from
`toolchains/llvm/prebuilt/darwin-x86_64/` in Android NDK `29.0.14206865`.
The Android JNI library statically links libc++ and libc++abi. This conservative
collection also contains notices for LLVM toolchain components not shipped in
the application; it is not evidence that all those components are linked.
