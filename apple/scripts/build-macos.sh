#!/usr/bin/env bash
# Build an unsigned local Universal application from this product checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILD="$APPLE/build/macOS"
CONFIGURATION="${1:-Release}"

usage() {
    printf 'usage: apple/scripts/build-macos.sh [Debug|Release]\n' >&2
    printf 'Default: Release application and release Rust archives.\n' >&2
    printf 'Set INKU_APPLE_PROFILE=debug to explicitly select debug Rust archives.\n' >&2
}

[[ $# -le 1 && ( "$CONFIGURATION" == Debug || "$CONFIGURATION" == Release ) ]] || { usage; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { printf 'The macOS application build requires macOS and Xcode.\n' >&2; exit 2; }
for tool in python3 xcodegen xcodebuild xcrun; do
    command -v "$tool" >/dev/null || { printf 'Missing build prerequisite: %s\n' "$tool" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'

python3 "$APPLE/scripts/export-server-resources.py"
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
xcrun lipo -verify_arch arm64 x86_64 "$APP/Contents/MacOS/Inku"
printf 'Built unsigned Universal application: %s\n' "$APP"
