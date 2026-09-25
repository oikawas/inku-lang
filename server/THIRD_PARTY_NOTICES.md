# Server distribution notices

The inku application code is licensed under the [repository MIT license](../LICENSE).
The container also carries independently licensed Python packages, native Rust
code, and Noto Serif JP. This document does not relicense those components.

Where an installed Python distribution supplies license files, they are
preserved alongside that package under
`/app/server/.venv/lib/python3.12/site-packages/*-dist-info/`.
For the MPL-2.0-covered `certifi 2026.2.25`, source is available from
https://pypi.org/project/certifi/2026.2.25/#files . For the MPL-2.0 and
MIT-covered `tqdm 4.67.3`, source is available from
https://pypi.org/project/tqdm/4.67.3/#files . These packages are not modified
by inku.
The Noto Serif JP copyright and SIL OFL 1.1 text are in
`src/inku_server/fonts/OFL.txt` beside the font.

The native binding uses UniFFI 0.32.0. The eight MPL-2.0 packages in
`core/Cargo.lock` are `uniffi`, `uniffi_bindgen`, `uniffi_core`,
`uniffi_internal_macros`, `uniffi_macros`, `uniffi_meta`, `uniffi_pipeline`,
and `uniffi_udl`. Their exact source archives are available from
`https://crates.io/api/v1/crates/<package>/0.32.0/download`, replacing
`<package>` with each listed name. The MPL-2.0 terms are available from
https://www.mozilla.org/en-US/MPL/2.0/ . The product does not modify these
upstream packages.

The container also contains `/app/licenses/RUST_THIRD_PARTY_NOTICES.txt`,
generated from the exact Cargo.lock registry sources during the native build.
It records each crate's license expression, source archive, and license files;
crates with no standalone license file are identified for release review.
The other current cases without a standalone license file are `cesu8 1.1.0`
(MIT or Apache-2.0, MIT selected), `jni-sys-macros 0.4.1` (MIT or Apache-2.0,
MIT selected), and `r-efi 6.0.0` (MIT or Apache-2.0 or LGPL-2.1-or-later,
MIT selected). Their exact source archives are linked in the generated bundle.

Before a public image release, review the actual native wheel and Python
environment against the locked dependencies and preserve any additional
third-party license and NOTICE files required by the components shipped.
