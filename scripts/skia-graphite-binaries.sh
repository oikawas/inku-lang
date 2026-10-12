#!/usr/bin/env bash
# Build the Skia binaries inku-display-gpu links, once, into the checked cache.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${INKU_BUILD_CACHE_DIR:-$HOME/Library/Application Support/inku/build-cache}"
CACHE="${INKU_SKIA_BINARIES_DIR:-$BASE/skia-binaries}"
WORK="$BASE/skia-graphite-build"
SDK="${INKU_SKIA_SDKROOT:-/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk}"
LIST="$ROOT/core/crates/inku-display-gpu/skia-binaries.sha256"
TARGET=aarch64-apple-darwin
TAG=0.153.3
# skia-bindings' key for skia-safe =0.153.3 with svg, webp, metal and graphite (and
# its default pdf and jpeg) on this target.
KEY=b7f043e0b1e2a850e702-aarch64-apple-darwin-graphite-jpegd-jpege-metal-pdf-svg-textlayout-webpd-webpe
NINJA_URL=https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-mac.zip
NINJA_SHA256=c99048673aa765960a99cf10c6ddb9f1fad506099ff0a0e137ad8960a88f321b

usage() {
    cat <<'USAGE'
usage: scripts/skia-graphite-binaries.sh

The published Skia prebuilt binaries for skia-safe 0.153.3 have no archive with
Graphite and Metal next to SVG and WebP, which the macOS app's GPU windows
(core/crates/inku-display-gpu) need. This builds Skia from the skia-bindings
crate's source for aarch64-apple-darwin, packs it like a published archive, puts
it into the cache scripts/skia-binaries.sh checks, and prints the digest line for
core/crates/inku-display-gpu/skia-binaries.sha256. Ordinary builds only read it.

Needs the macOS 26.5 SDK of the Command Line Tools: with Xcode 27's SDK, bindgen
writes a C++ library type Rust cannot compile (std::__hash_table's
__node_allocator). INKU_SKIA_SDKROOT names another SDK. ninja v1.13.2 is fetched
once and checked against its published SHA-256.

Cache: ~/Library/Application Support/inku/build-cache (INKU_BUILD_CACHE_DIR).
USAGE
}

[[ $# -eq 0 ]] || { usage >&2; [[ "$1" == -h || "$1" == --help ]] && exit 0; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { printf 'Building Skia for macOS requires macOS.\n' >&2; exit 2; }
[[ -d "$SDK" ]] || {
    printf 'missing SDK %s: install the Command Line Tools with the macOS 26.5 SDK, or set INKU_SKIA_SDKROOT\n' "$SDK" >&2
    exit 2
}

digest() {
    shasum -a 256 "$1" | awk '{print $1}'
}

NINJA_DIR="$WORK/ninja-v1.13.2"
NINJA="$NINJA_DIR/ninja"
if [[ ! -x "$NINJA" ]]; then
    mkdir -p "$NINJA_DIR"
    curl --fail --location --silent --show-error --output "$NINJA_DIR/ninja-mac.zip.partial" "$NINJA_URL"
    actual="$(digest "$NINJA_DIR/ninja-mac.zip.partial")"
    [[ "$actual" == "$NINJA_SHA256" ]] || {
        printf 'refusing %s: sha256 %s, expected %s\n' "$NINJA_URL" "$actual" "$NINJA_SHA256" >&2
        exit 1
    }
    mv "$NINJA_DIR/ninja-mac.zip.partial" "$NINJA_DIR/ninja-mac.zip"
    /usr/bin/unzip -o -q "$NINJA_DIR/ninja-mac.zip" -d "$NINJA_DIR"
fi

# A fresh target directory, so skia-bindings compiles Skia instead of reusing a build.
rm -rf "$WORK/target"
started=$SECONDS
env -u SKIA_BINARIES_URL FORCE_SKIA_BUILD=1 SKIA_NINJA_COMMAND="$NINJA" SDKROOT="$SDK" \
    MACOSX_DEPLOYMENT_TARGET=14.0 CARGO_TARGET_DIR="$WORK/target" \
    "$ROOT/scripts/rust-toolchain.sh" build --locked -p inku-display-gpu --features graphite \
    --lib --target "$TARGET" --release

OUT=""
for candidate in "$WORK/target/$TARGET/release/build"/skia-bindings-*/out/skia; do
    [[ -f "$candidate/bindings.rs" ]] && OUT="$candidate"
done
[[ -n "$OUT" ]] || { printf 'skia-bindings left no output in %s\n' "$WORK/target" >&2; exit 1; }
SOURCE="$("$ROOT/scripts/rust-toolchain.sh" metadata --format-version 1 --locked --offline --all-features \
    | python3 -c 'import json, sys; print(next(p["manifest_path"] for p in json.load(sys.stdin)["packages"] if p["name"] == "skia-bindings" and p["version"] == "0.153.3"))')"
SKIA_LICENSE="$(dirname "$SOURCE")/skia/LICENSE"

ARCHIVE="$CACHE/$TAG/skia-binaries-$KEY.tar.gz"
mkdir -p "$(dirname "$ARCHIVE")"
# The same members as a published archive, in a fixed order with fixed metadata.
python3 - "$OUT" "$SKIA_LICENSE" "$TAG" "$KEY" "$ARCHIVE" <<'__INKU_SKIA_ARCHIVE__'
import gzip
import io
import sys
import tarfile
from pathlib import Path

out, license_path, tag, key, archive = sys.argv[1:6]
files = {name: (Path(out) / name).read_bytes() for name in [
    "bindings.rs", "libskia-bindings.a", "libskia.a", "libskparagraph.a", "libskresources.a",
    "libskshaper.a", "libskunicode_core.a", "libskunicode_icu.a", "libsvg.a"]}
files["LICENSE_SKIA"] = Path(license_path).read_bytes()
files["key.txt"] = key.encode()
files["tag.txt"] = tag.encode()
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
    directory = tarfile.TarInfo("skia-binaries")
    directory.type, directory.mode, directory.mtime = tarfile.DIRTYPE, 0o755, 0
    tar.addfile(directory)
    for name in sorted(files):
        info = tarfile.TarInfo(f"skia-binaries/{name}")
        info.size, info.mode, info.mtime = len(files[name]), 0o644, 0
        tar.addfile(info, io.BytesIO(files[name]))
partial = Path(archive + ".partial")
with partial.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as stream:
    stream.write(buffer.getvalue())
partial.replace(archive)
__INKU_SKIA_ARCHIVE__

line="$(digest "$ARCHIVE")  $TAG/skia-binaries-$KEY.tar.gz"
printf 'Built %s in %ds.\n' "$ARCHIVE" "$((SECONDS - started))" >&2
if /usr/bin/grep -qxF "$line" "$LIST" 2>/dev/null; then
    printf 'It matches %s.\n' "$LIST" >&2
else
    printf 'Put this line into %s (replacing the old one):\n' "$LIST" >&2
fi
printf '%s\n' "$line"
