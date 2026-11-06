#!/usr/bin/env bash
# Build the same Rust facade and generator from this product checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE="$ROOT/apple/Packages/InkuCore"
BUILD="$ROOT/apple/scripts/.build/core"
RUST_TARGET="$BUILD/rust"
MODE="${1:-macos}"
PROFILE="${INKU_APPLE_PROFILE:-release}"

usage() {
    printf 'usage: apple/scripts/build-core.sh [macos|all]\n' >&2
    printf 'macos: arm64 + x86_64; all: additionally iOS device + Universal simulator\n' >&2
    printf 'Set INKU_APPLE_PROFILE=debug for a development artifact.\n' >&2
}

[[ $# -le 1 && ( "$MODE" == macos || "$MODE" == all ) ]] || { usage; exit 2; }
[[ "$PROFILE" == release || "$PROFILE" == debug ]] || { usage; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { printf 'Apple builds require macOS and Xcode.\n' >&2; exit 2; }

CHANNEL="$(awk -F'"' '/^[[:space:]]*channel[[:space:]]*=/ { print $2; exit }' "$ROOT/core/rust-toolchain.toml")"
RUSTUP_BIN="${INKU_RUSTUP_BIN:-${CARGO_HOME:-$HOME/.cargo}/bin/rustup}"
TARGETS=(aarch64-apple-darwin x86_64-apple-darwin)
if [[ "$MODE" == all ]]; then
    TARGETS+=(aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios)
fi
INSTALLED="$("$RUSTUP_BIN" target list --toolchain "$CHANNEL" --installed)"
for target in "${TARGETS[@]}"; do
    if ! printf '%s\n' "$INSTALLED" | /usr/bin/grep -qx "$target"; then
        printf 'Missing Rust target. Install explicitly: %s target add --toolchain %s %s\n' "$RUSTUP_BIN" "$CHANNEL" "$target" >&2
        exit 2
    fi
done

# Some rustup macOS toolchains ship rust-objcopy with an rpath that does not
# reach the toolchain's libLLVM.dylib. Scope the lookup fix to this build and
# preserve any library paths supplied by the caller.
RUST_SYSROOT="$("$RUSTUP_BIN" run "$CHANNEL" rustc --print sysroot)"
if [[ -f "$RUST_SYSROOT/lib/libLLVM.dylib" ]]; then
    export INKU_RUST_DYLD_LIBRARY_PATH="$RUST_SYSROOT/lib"
fi

mkdir -p "$BUILD/generated" "$BUILD/headers" "$BUILD/macos" "$PACKAGE/Sources/InkuCoreBindings" "$PACKAGE/Artifacts"
copy_if_changed() {
    if [[ ! -f "$2" ]] || ! cmp -s "$1" "$2"; then
        cp "$1" "$2"
    fi
}
export CARGO_TARGET_DIR="$RUST_TARGET"
export MACOSX_DEPLOYMENT_TARGET=14.0
export IPHONEOS_DEPLOYMENT_TARGET=17.0
PROFILE_ARGS=()
if [[ "$PROFILE" == release ]]; then
    PROFILE_ARGS+=(--release)
fi
# Skia screen display (inku-display): skia-bindings reads the prebuilt binaries from
# copies checked against core/crates/inku-display/skia-binaries.sha256 on every build.
# The GPU windows' Skia (Graphite) is the archive scripts/skia-graphite-binaries.sh built,
# checked against core/crates/inku-display-gpu/skia-binaries.sha256.
SKIA_BINARIES_URL="$("$ROOT/scripts/skia-binaries.sh" --with-local "${TARGETS[@]}")"
export SKIA_BINARIES_URL
for target in "${TARGETS[@]}"; do
    "$ROOT/scripts/rust-toolchain.sh" build --locked -p inku-pipeline-uniffi --features display --lib --target "$target" "${PROFILE_ARGS[@]}"
done
# The zoomed windows' program on Apple silicon (inku-display-gpu). no-compile: a missing or
# different archive stops the build instead of compiling Skia here.
"$ROOT/scripts/rust-toolchain.sh" build --locked -p inku-display-gpu --features graphite,skia-safe/no-compile \
    --bin inku-display-gpu --target aarch64-apple-darwin "${PROFILE_ARGS[@]}"
mkdir -p "$BUILD/display-gpu"
copy_if_changed "$RUST_TARGET/aarch64-apple-darwin/$PROFILE/inku-display-gpu" "$BUILD/display-gpu/inku-display-gpu"

# The Cargo.lock-pinned 0.32.0 generator inspects this exact archive's metadata.
"$ROOT/scripts/rust-toolchain.sh" run --locked -p inku-pipeline-uniffi --features cli --bin uniffi-bindgen -- \
    generate "$RUST_TARGET/aarch64-apple-darwin/$PROFILE/libinku_pipeline_uniffi.a" \
    --language swift --crate inku_pipeline_uniffi --config "$ROOT/apple/scripts/uniffi-swift.toml" \
    --out-dir "$BUILD/generated" --no-format
copy_if_changed "$BUILD/generated/InkuCoreBindings.swift" "$PACKAGE/Sources/InkuCoreBindings/InkuCoreBindings.swift"
copy_if_changed "$BUILD/generated/InkuCoreFFI.h" "$BUILD/headers/InkuCoreFFI.h"
copy_if_changed "$BUILD/generated/InkuCoreFFI.modulemap" "$BUILD/headers/module.modulemap"

xcrun lipo -create \
    "$RUST_TARGET/aarch64-apple-darwin/$PROFILE/libinku_pipeline_uniffi.a" \
    "$RUST_TARGET/x86_64-apple-darwin/$PROFILE/libinku_pipeline_uniffi.a" \
    -output "$BUILD/macos/libinku_pipeline_uniffi.new.a"
copy_if_changed "$BUILD/macos/libinku_pipeline_uniffi.new.a" "$BUILD/macos/libinku_pipeline_uniffi.a"
rm "$BUILD/macos/libinku_pipeline_uniffi.new.a"
FRAMEWORK_ARGS=(-library "$BUILD/macos/libinku_pipeline_uniffi.a" -headers "$BUILD/headers")
if [[ "$MODE" == all ]]; then
    mkdir -p "$BUILD/ios-simulator"
    xcrun lipo -create \
        "$RUST_TARGET/aarch64-apple-ios-sim/$PROFILE/libinku_pipeline_uniffi.a" \
        "$RUST_TARGET/x86_64-apple-ios/$PROFILE/libinku_pipeline_uniffi.a" \
        -output "$BUILD/ios-simulator/libinku_pipeline_uniffi.new.a"
    copy_if_changed "$BUILD/ios-simulator/libinku_pipeline_uniffi.new.a" "$BUILD/ios-simulator/libinku_pipeline_uniffi.a"
    rm "$BUILD/ios-simulator/libinku_pipeline_uniffi.new.a"
    FRAMEWORK_ARGS+=(
        -library "$RUST_TARGET/aarch64-apple-ios/$PROFILE/libinku_pipeline_uniffi.a" -headers "$BUILD/headers"
        -library "$BUILD/ios-simulator/libinku_pipeline_uniffi.a" -headers "$BUILD/headers"
    )
fi

# Replace only the generated artifact after every selected archive has built.
OUTPUT="$BUILD/InkuCoreFFI.xcframework"
[[ ! -d "$OUTPUT" ]] || rm -rf "$OUTPUT"
xcodebuild -create-xcframework "${FRAMEWORK_ARGS[@]}" -output "$OUTPUT"
if [[ ! -d "$PACKAGE/Artifacts/InkuCoreFFI.xcframework" ]] || ! diff -qr "$OUTPUT" "$PACKAGE/Artifacts/InkuCoreFFI.xcframework" >/dev/null; then
    [[ ! -d "$PACKAGE/Artifacts/InkuCoreFFI.xcframework" ]] || rm -rf "$PACKAGE/Artifacts/InkuCoreFFI.xcframework"
    cp -R "$OUTPUT" "$PACKAGE/Artifacts/InkuCoreFFI.xcframework"
fi
python3 - "$ROOT" "$PACKAGE" "$RUST_TARGET" "$PROFILE" "$CHANNEL" "$MODE" "${TARGETS[@]}" <<'__INKU_CORE_MANIFEST__'
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib

root, package, rust_target = map(Path, sys.argv[1:4])
profile, channel, mode = sys.argv[4:7]
targets = sys.argv[7:]

def git(*args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

source = hashlib.sha256()
paths = git("ls-files", "-c", "-o", "--exclude-standard", "core").splitlines()
for name in sorted(set(paths)):
    path = root / name
    if path.is_file():
        source.update(name.encode() + b"\0")
        source.update(bytes.fromhex(file_digest(path)))
lock = tomllib.loads((root / "core/Cargo.lock").read_text())
generator = next(item["version"] for item in lock["package"] if item["name"] == "uniffi_bindgen")
if generator != "0.32.0":
    raise SystemExit("unexpected UniFFI generator version")
identity = {
    "schema": "inku.apple-rust-artifact.v1",
    "product_commit": git("rev-parse", "HEAD"),
    "core_dirty": bool(git("status", "--porcelain", "--", "core")),
    "core_source_sha256": source.hexdigest(),
    "rust_toolchain": channel,
    "features": ["display"],
    "uniffi_generator": generator,
    "profile": profile,
    "mode": mode,
    "minimum_macos": "14.0",
    "minimum_ios": "17.0",
    "archives": {
        target: file_digest(rust_target / target / profile / "libinku_pipeline_uniffi.a")
        for target in targets
    },
    "swift_binding_sha256": file_digest(package / "Sources/InkuCoreBindings/InkuCoreBindings.swift"),
    "display_gpu": {
        "target": "aarch64-apple-darwin",
        "features": ["graphite"],
        "sha256": file_digest(root / "apple/scripts/.build/core/display-gpu/inku-display-gpu"),
    },
}
manifest = package / "Artifacts/build-manifest.json"
content = json.dumps(identity, indent=2, sort_keys=True) + "\n"
if not manifest.is_file() or manifest.read_text() != content:
    manifest.write_text(content)
__INKU_CORE_MANIFEST__
printf 'Generated %s (%s, macOS 14 / iOS 17).\n' "$PACKAGE/Artifacts/InkuCoreFFI.xcframework" "$MODE"
