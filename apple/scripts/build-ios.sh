#!/usr/bin/env bash
# Build an unsigned iOS Simulator application (iPad) from this product checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILD="$APPLE/build/iOS"
CONFIGURATION=Release
BUNDLE_ID=app.inku.ios
RUN_APP=false
DEVICE_NAME='iPad Pro 11-inch (M5)'
# How long the launched application must stay alive before the run counts as started.
LAUNCH_SETTLE_SECONDS=10

usage() {
    printf 'usage: apple/scripts/build-ios.sh [Debug|Release] [--run [DEVICE_NAME]]\n' >&2
    printf 'Default: Release application and release Rust archives, for the iOS Simulator, unsigned.\n' >&2
    printf 'Set INKU_APPLE_PROFILE=debug to explicitly select debug Rust archives.\n' >&2
    printf 'With --run, boot the simulator device (default: %s) without opening Simulator.app,\n' "$DEVICE_NAME" >&2
    printf 'install and launch %s, and fail unless it is still running %s seconds later.\n' "$BUNDLE_ID" "$LAUNCH_SETTLE_SECONDS" >&2
}

configuration_selected=false
arguments=("$@")
index=0
while (( index < ${#arguments[@]} )); do
    argument="${arguments[index]}"
    case "$argument" in
        Debug|Release)
            [[ "$configuration_selected" == false ]] || { usage; exit 2; }
            CONFIGURATION="$argument"
            configuration_selected=true
            ;;
        --run)
            [[ "$RUN_APP" == false ]] || { usage; exit 2; }
            RUN_APP=true
            # An optional device name follows, unless the next word is the configuration.
            next="${arguments[index + 1]:-}"
            if [[ -n "$next" && "$next" != Debug && "$next" != Release && "$next" != -* ]]; then
                DEVICE_NAME="$next"
                index=$((index + 1))
            fi
            ;;
        *) usage; exit 2 ;;
    esac
    index=$((index + 1))
done
[[ "$(uname -s)" == Darwin ]] || { printf 'The iOS application build requires macOS and Xcode.\n' >&2; exit 2; }
for tool in python3 node uv xcodegen xcodebuild xcrun; do
    command -v "$tool" >/dev/null || { printf 'Missing build prerequisite: %s\n' "$tool" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
node --input-type=module -e 'import { stripTypeScriptTypes } from "node:module"; stripTypeScriptTypes("const value: number = 1;");'
xcrun --sdk iphonesimulator --show-sdk-path >/dev/null || { printf 'The iOS Simulator SDK is not installed in the selected Xcode.\n' >&2; exit 2; }

# The tracked build number is the floor; the local counter allocates a new number for every build
# (one counter for both platforms, so a Mac and an iOS build never share a number).
VERSION_FLOOR="$(tr -d '[:space:]' < "$APPLE/VERSION")"
BUILD_FLOOR="$(tr -d '[:space:]' < "$APPLE/BUILD_NUMBER")"
# CFBundleShortVersionString allows at most three numeric components.
[[ "$VERSION_FLOOR" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'apple/VERSION must have three numbers: %s\n' "$VERSION_FLOOR" >&2; exit 2; }
[[ "$BUILD_FLOOR" =~ ^[1-9][0-9]*$ ]] || { printf 'apple/BUILD_NUMBER must be a positive integer: %s\n' "$BUILD_FLOOR" >&2; exit 2; }
ALLOCATION="$(python3 "$APPLE/scripts/allocate-build-number.py" --floor "$BUILD_FLOOR" --version-floor "$VERSION_FLOOR")"
read -r MARKETING_VERSION BUILD_NUMBER <<< "$ALLOCATION"

# Normal builds use the reviewed, committed resource snapshot. Following a newer
# Server checkout is an explicit source operation, independent of a rebuild.
if [[ -n "${INKU_APPLE_REFERENCE_ROOT:-}" ]]; then
    python3 "$APPLE/scripts/export-server-resources.py" --source-root "$INKU_APPLE_REFERENCE_ROOT"
fi
uv sync --project "$ROOT/server" --frozen
python3 "$APPLE/scripts/prepare-meter-resources.py"
# The Web's registered 3D viewer is not committed here: copy it unchanged, then compare every file with the Web's.
python3 "$APPLE/scripts/sync-ddl3d-viewer.py"
# The iOS slices come only from `build-core.sh all`. Rebuild only when the artifact is not an `all`
# build, was built with another profile, or was built from different core sources.
core_status=0
"$APPLE/scripts/build-core.sh" --check-current all || core_status=$?
case "$core_status" in
    0) printf 'Not rebuilding the Rust core artifact.\n' ;;
    1) "$APPLE/scripts/build-core.sh" all ;;
    *) exit "$core_status" ;;
esac
xcodegen generate --use-cache --spec "$APPLE/project.yml" --project "$APPLE" --project-root "$APPLE"

mkdir -p "$BUILD"
xcodebuild \
    -project "$APPLE/Inku.xcodeproj" \
    -scheme InkuIOS \
    -configuration "$CONFIGURATION" \
    -destination 'generic/platform=iOS Simulator' \
    -derivedDataPath "$BUILD/DerivedData" \
    -clonedSourcePackagesDirPath "$BUILD/SourcePackages" \
    "MARKETING_VERSION=$MARKETING_VERSION" \
    "CURRENT_PROJECT_VERSION=$BUILD_NUMBER" \
    "INKU_ALLOCATED_BUILD_NUMBER=$BUILD_NUMBER" \
    "INKU_ALLOCATED_VERSION=$MARKETING_VERSION" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGN_IDENTITY= \
    build

APP="$BUILD/DerivedData/Build/Products/$CONFIGURATION-iphonesimulator/Inku.app"
[[ -d "$APP" ]] || { printf 'The build produced no application at %s\n' "$APP" >&2; exit 1; }
# An iOS bundle is flat: Info.plist sits at the bundle root.
for pair in "CFBundleShortVersionString=$MARKETING_VERSION" "CFBundleVersion=$BUILD_NUMBER" "CFBundleIdentifier=$BUNDLE_ID"; do
    actual="$(/usr/libexec/PlistBuddy -c "Print :${pair%%=*}" "$APP/Info.plist")"
    [[ "$actual" == "${pair#*=}" ]] || { printf 'Built %s is %s, expected %s\n' "${pair%%=*}" "$actual" "${pair#*=}" >&2; exit 1; }
done
# The app carries the copy, file for file (the package declares it only when the copy exists).
python3 "$APPLE/scripts/sync-ddl3d-viewer.py" --check --app "$APP"

if [[ "$RUN_APP" == true ]]; then
    # Pick the named device among the available ones, preferring one that is already booted.
    read -r DEVICE_UDID DEVICE_STATE < <(xcrun simctl list devices available -j | python3 -c '
import json, sys
name = sys.argv[1]
matches = [device for devices in json.load(sys.stdin)["devices"].values() for device in devices
           if device.get("name") == name and device.get("isAvailable", True)]
matches.sort(key=lambda device: device.get("state") != "Booted")
if matches:
    print(matches[0]["udid"], matches[0]["state"])
' "$DEVICE_NAME") || true
    [[ -n "${DEVICE_UDID:-}" ]] || { printf 'No available simulator device named %s (see xcrun simctl list devices available)\n' "$DEVICE_NAME" >&2; exit 1; }
    # simctl boots the device headless; Simulator.app is never opened here.
    if [[ "$DEVICE_STATE" != Booted ]]; then
        xcrun simctl boot "$DEVICE_UDID" || { printf 'Could not boot %s (%s); the build itself succeeded: %s\n' "$DEVICE_NAME" "$DEVICE_UDID" "$APP" >&2; exit 1; }
    fi
    xcrun simctl bootstatus "$DEVICE_UDID"
    xcrun simctl install "$DEVICE_UDID" "$APP"
    xcrun simctl launch --terminate-running-process "$DEVICE_UDID" "$BUNDLE_ID"
    sleep "$LAUNCH_SETTLE_SECONDS"
    # launchctl lists the application's job with its process id while it runs ("-" once it has exited).
    job="$(xcrun simctl spawn "$DEVICE_UDID" launchctl list | awk -v id="UIKitApplication:$BUNDLE_ID[" 'index($3, id) == 1 { print; exit }')"
    if [[ -z "$job" || ! "$job" =~ ^[0-9]+[[:space:]] ]]; then
        printf '%s is not running on %s (%s) %s seconds after launch: %s\n' \
            "$BUNDLE_ID" "$DEVICE_NAME" "$DEVICE_UDID" "$LAUNCH_SETTLE_SECONDS" "${job:-no launchctl job}" >&2
        exit 1
    fi
    printf '%s is running on %s (%s): %s\n' "$BUNDLE_ID" "$DEVICE_NAME" "$DEVICE_UDID" "$job"
fi
printf 'Built unsigned iOS Simulator application %s (%s): %s\n' "$MARKETING_VERSION" "$BUILD_NUMBER" "$APP"
