#!/usr/bin/env bash
# Build an unsigned local Universal application from this product checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILD="$APPLE/build/macOS"
CONFIGURATION=Release
INSTALL_APP=false

usage() {
    printf 'usage: apple/scripts/build-macos.sh [Debug|Release] [--install]\n' >&2
    printf 'Default: Release application and release Rust archives.\n' >&2
    printf 'Set INKU_APPLE_PROFILE=debug to explicitly select debug Rust archives.\n' >&2
    printf 'With --install, update the fixed ~/Applications/Inku.app after quitting it.\n' >&2
}

configuration_selected=false
for argument in "$@"; do
    case "$argument" in
        Debug|Release)
            [[ "$configuration_selected" == false ]] || { usage; exit 2; }
            CONFIGURATION="$argument"
            configuration_selected=true
            ;;
        --install) INSTALL_APP=true ;;
        *) usage; exit 2 ;;
    esac
done
[[ "$(uname -s)" == Darwin ]] || { printf 'The macOS application build requires macOS and Xcode.\n' >&2; exit 2; }
for tool in python3 node uv xcodegen xcodebuild xcrun; do
    command -v "$tool" >/dev/null || { printf 'Missing build prerequisite: %s\n' "$tool" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
node --input-type=module -e 'import { stripTypeScriptTypes } from "node:module"; stripTypeScriptTypes("const value: number = 1;");'

mkdir -p "$BUILD"
xcrun swift -module-cache-path "$BUILD/IconModuleCache" "$APPLE/scripts/prepare-macos-icon.swift"
python3 "$APPLE/scripts/export-server-resources.py"
uv sync --project "$ROOT/server" --frozen
python3 "$APPLE/scripts/prepare-meter-resources.py"
"$APPLE/scripts/build-core.sh" macos
xcodegen generate --spec "$APPLE/project.yml" --project "$APPLE" --project-root "$APPLE"

mkdir -p "$BUILD"
xcodebuild \
    -project "$APPLE/Inku.xcodeproj" \
    -scheme InkuMac \
    -configuration "$CONFIGURATION" \
    -destination 'generic/platform=macOS' \
    -derivedDataPath "$BUILD/DerivedData" \
    -clonedSourcePackagesDirPath "$BUILD/SourcePackages" \
    'ARCHS=arm64 x86_64' \
    ONLY_ACTIVE_ARCH=NO \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY= \
    build

APP="$BUILD/DerivedData/Build/Products/$CONFIGURATION/Inku.app"
# A successful build for only the active architecture is insufficient here.
for architecture in arm64 x86_64; do
    xcrun lipo "$APP/Contents/MacOS/Inku" -verify_arch "$architecture"
done
printf 'Built unsigned Universal application: %s\n' "$APP"
if [[ "$INSTALL_APP" == true ]]; then
    python3 "$APPLE/scripts/install-macos.py" --app "$APP"
fi
