#!/usr/bin/env bash
# Build an unsigned local Universal application from this product checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILD="$APPLE/build/macOS"
CONFIGURATION=Release
INSTALL_APP=false
STOP_EXISTING=true

usage() {
    printf 'usage: apple/scripts/build-macos.sh [Debug|Release] [--install] [--keep-running]\n' >&2
    printf 'Default: Release application and release Rust archives.\n' >&2
    printf 'Set INKU_APPLE_PROFILE=debug to explicitly select debug Rust archives.\n' >&2
    printf 'Existing Inku instances owned by this user are force-stopped before building.\n' >&2
    printf 'With --keep-running, they are left running (not allowed with --install).\n' >&2
    printf 'With --install, update the fixed ~/Applications/Inku.app.\n' >&2
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
        --keep-running) STOP_EXISTING=false ;;
        *) usage; exit 2 ;;
    esac
done
[[ "$INSTALL_APP" == false || "$STOP_EXISTING" == true ]] || { usage; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { printf 'The macOS application build requires macOS and Xcode.\n' >&2; exit 2; }
for tool in python3 node uv xcodegen xcodebuild xcrun; do
    command -v "$tool" >/dev/null || { printf 'Missing build prerequisite: %s\n' "$tool" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
node --input-type=module -e 'import { stripTypeScriptTypes } from "node:module"; stripTypeScriptTypes("const value: number = 1;");'

# The bundle version comes only from these files, as android/VERSION does for Android.
MARKETING_VERSION="$(tr -d '[:space:]' < "$APPLE/VERSION")"
BUILD_NUMBER="$(tr -d '[:space:]' < "$APPLE/BUILD_NUMBER")"
# CFBundleShortVersionString allows at most three numeric components.
[[ "$MARKETING_VERSION" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || { printf 'apple/VERSION must be 1 to 3 numbers: %s\n' "$MARKETING_VERSION" >&2; exit 2; }
[[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]] || { printf 'apple/BUILD_NUMBER must be a positive integer: %s\n' "$BUILD_NUMBER" >&2; exit 2; }

mkdir -p "$BUILD"
if [[ "$STOP_EXISTING" == true ]]; then
    python3 "$APPLE/scripts/stop-existing-macos.py" --report "$BUILD/stop-existing.json"
fi
xcrun swift -module-cache-path "$BUILD/IconModuleCache" "$APPLE/scripts/prepare-macos-icon.swift"
# Normal builds use the reviewed, committed resource snapshot. Following a newer
# Server checkout is an explicit source operation, independent of a rebuild.
if [[ -n "${INKU_APPLE_REFERENCE_ROOT:-}" ]]; then
    python3 "$APPLE/scripts/export-server-resources.py" --source-root "$INKU_APPLE_REFERENCE_ROOT"
fi
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
    "MARKETING_VERSION=$MARKETING_VERSION" \
    "CURRENT_PROJECT_VERSION=$BUILD_NUMBER" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY= \
    build

APP="$BUILD/DerivedData/Build/Products/$CONFIGURATION/Inku.app"
# A successful build for only the active architecture is insufficient here.
for architecture in arm64 x86_64; do
    xcrun lipo "$APP/Contents/MacOS/Inku" -verify_arch "$architecture"
done
for pair in "CFBundleShortVersionString=$MARKETING_VERSION" "CFBundleVersion=$BUILD_NUMBER"; do
    actual="$(/usr/libexec/PlistBuddy -c "Print :${pair%%=*}" "$APP/Contents/Info.plist")"
    [[ "$actual" == "${pair#*=}" ]] || { printf 'Built %s is %s, expected %s\n' "${pair%%=*}" "$actual" "${pair#*=}" >&2; exit 1; }
done
printf 'Built unsigned Universal application %s (%s): %s\n' "$MARKETING_VERSION" "$BUILD_NUMBER" "$APP"
if [[ "$INSTALL_APP" == true ]]; then
    python3 "$APPLE/scripts/install-macos.py" --app "$APP"
fi
