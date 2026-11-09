#!/usr/bin/env bash
# Build an iOS Simulator application (iPad) from this product checkout, signed as Xcode's "Sign to Run Locally"
# (ad hoc, no team): the Simulator's Keychain and the Files app's view of the app's Documents need the signed app and
# its application identifier (ios-app step 2, 2026-11-08).
# With --device, build for a connected iPad instead, signed automatically by the team in INKU_IOS_TEAM (the author's,
# never committed), copy the installed app's data aside, then install and launch it (ios-app step 6, 2026-11-09).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILD="$APPLE/build/iOS"
CONFIGURATION=Release
BUNDLE_ID=app.inku.ios
RUN_APP=false
DEVICE_NAME='iPad Pro 11-inch (M5)'
# --device: a connected physical device (its UDID or name; default: the only connected physical iPad).
PHYSICAL=false
PHYSICAL_DEVICE=''
# How long the launched application must stay alive before the run counts as started.
LAUNCH_SETTLE_SECONDS=10

usage() {
    printf 'usage: apple/scripts/build-ios.sh [Debug|Release] [--run [DEVICE_NAME] | --device [UDID_OR_NAME]]\n' >&2
    printf 'With --device, build for a connected physical iPad, signed by the team in INKU_IOS_TEAM (Xcode must be\n' >&2
    printf 'signed in to that team), copy the installed app'"'"'s Library/Application Support to\n' >&2
    printf 'apple/build/iOS/device-backups/, then install and launch it with devicectl.\n' >&2
    printf 'Default: Release application and release Rust archives, for the iOS Simulator, signed to run locally.\n' >&2
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
        --device)
            [[ "$PHYSICAL" == false && "$RUN_APP" == false ]] || { usage; exit 2; }
            PHYSICAL=true
            next="${arguments[index + 1]:-}"
            if [[ -n "$next" && "$next" != Debug && "$next" != Release && "$next" != -* ]]; then
                PHYSICAL_DEVICE="$next"
                index=$((index + 1))
            fi
            ;;
        *) usage; exit 2 ;;
    esac
    index=$((index + 1))
done
[[ "$PHYSICAL" == false || "$RUN_APP" == false ]] || { usage; exit 2; }
if [[ "$PHYSICAL" == true && -z "${INKU_IOS_TEAM:-}" ]]; then
    printf 'Set INKU_IOS_TEAM to the signing team ID (10 characters) for --device; it is not stored in the checkout.\n' >&2
    exit 2
fi
[[ "$(uname -s)" == Darwin ]] || { printf 'The iOS application build requires macOS and Xcode.\n' >&2; exit 2; }
for tool in python3 node uv xcodegen xcodebuild xcrun; do
    command -v "$tool" >/dev/null || { printf 'Missing build prerequisite: %s\n' "$tool" >&2; exit 2; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
node --input-type=module -e 'import { stripTypeScriptTypes } from "node:module"; stripTypeScriptTypes("const value: number = 1;");'
if [[ "$PHYSICAL" == true ]]; then
    xcrun --sdk iphoneos --show-sdk-path >/dev/null || { printf 'The iOS SDK is not installed in the selected Xcode.\n' >&2; exit 2; }
    # Pick the device before building: a missing or ambiguous device stops here, not after the long build.
    DEVICE_LIST="$(mktemp)"
    trap 'rm -f "$DEVICE_LIST"' EXIT
    xcrun devicectl list devices --json-output "$DEVICE_LIST" >/dev/null 2>&1 || true
    PHYSICAL_UDID="$(python3 -c '
import json, sys
wanted = sys.argv[1]
devices = json.load(open(sys.argv[2]))["result"]["devices"]
physical = [d for d in devices if d.get("hardwareProperties", {}).get("reality") == "physical"
            and d.get("connectionProperties", {}).get("pairingState") == "paired"]
if wanted:
    found = [d for d in physical if wanted in (d.get("hardwareProperties", {}).get("udid"), d.get("deviceProperties", {}).get("name"))]
else:
    found = [d for d in physical if d.get("hardwareProperties", {}).get("deviceType") == "iPad"]
if len(found) == 1:
    print(found[0]["hardwareProperties"]["udid"])
' "$PHYSICAL_DEVICE" "$DEVICE_LIST")" || true
    [[ -n "$PHYSICAL_UDID" ]] || {
        printf 'No single paired physical device matches %s (see xcrun devicectl list devices).\n' "${PHYSICAL_DEVICE:-"an iPad"}" >&2
        exit 1
    }
else
    xcrun --sdk iphonesimulator --show-sdk-path >/dev/null || { printf 'The iOS Simulator SDK is not installed in the selected Xcode.\n' >&2; exit 2; }
fi

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
if [[ "$PHYSICAL" == true ]]; then
    # Automatic signing: Xcode makes or reuses the team's development profile for app.inku.ios.
    DESTINATION='generic/platform=iOS'
    SIGNING=(-allowProvisioningUpdates CODE_SIGN_STYLE=Automatic "DEVELOPMENT_TEAM=$INKU_IOS_TEAM")
    PRODUCTS="$CONFIGURATION-iphoneos"
else
    DESTINATION='generic/platform=iOS Simulator'
    SIGNING=(CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM=)
    PRODUCTS="$CONFIGURATION-iphonesimulator"
fi
xcodebuild \
    -project "$APPLE/Inku.xcodeproj" \
    -scheme InkuIOS \
    -configuration "$CONFIGURATION" \
    -destination "$DESTINATION" \
    -derivedDataPath "$BUILD/DerivedData" \
    -clonedSourcePackagesDirPath "$BUILD/SourcePackages" \
    "MARKETING_VERSION=$MARKETING_VERSION" \
    "CURRENT_PROJECT_VERSION=$BUILD_NUMBER" \
    "INKU_ALLOCATED_BUILD_NUMBER=$BUILD_NUMBER" \
    "INKU_ALLOCATED_VERSION=$MARKETING_VERSION" \
    "${SIGNING[@]}" \
    build

APP="$BUILD/DerivedData/Build/Products/$PRODUCTS/Inku.app"
[[ -d "$APP" ]] || { printf 'The build produced no application at %s\n' "$APP" >&2; exit 1; }
# An iOS bundle is flat: Info.plist sits at the bundle root.
for pair in "CFBundleShortVersionString=$MARKETING_VERSION" "CFBundleVersion=$BUILD_NUMBER" "CFBundleIdentifier=$BUNDLE_ID"; do
    actual="$(/usr/libexec/PlistBuddy -c "Print :${pair%%=*}" "$APP/Info.plist")"
    [[ "$actual" == "${pair#*=}" ]] || { printf 'Built %s is %s, expected %s\n' "${pair%%=*}" "$actual" "${pair#*=}" >&2; exit 1; }
done
# The app carries the copy, file for file (the package declares it only when the copy exists).
python3 "$APPLE/scripts/sync-ddl3d-viewer.py" --check --app "$APP"

if [[ "$PHYSICAL" == true ]]; then
    # The installed app's works and settings are copied aside first: installing can migrate its database at the
    # next start, and the app starts right after the install (ios-app plan step 6).
    # An app that has not stored anything yet (it never got past its first screen) has no Application Support.
    # The listings are read whole first: `devicectl … | grep -q` fails under pipefail when grep stops reading early.
    installed="$(xcrun devicectl device info apps --device "$PHYSICAL_UDID" --bundle-id "$BUNDLE_ID" 2>/dev/null || true)"
    library=''
    if grep -q "$BUNDLE_ID" <<< "$installed"; then
        library="$(xcrun devicectl device info files --device "$PHYSICAL_UDID" --domain-type appDataContainer \
            --domain-identifier "$BUNDLE_ID" --subdirectory Library --no-recurse 2>/dev/null || true)"
    fi
    if grep -q '^Application Support ' <<< "$library"; then
        BACKUP="$BUILD/device-backups/$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$BACKUP"
        xcrun devicectl device copy from --device "$PHYSICAL_UDID" --domain-type appDataContainer \
            --domain-identifier "$BUNDLE_ID" --source "Library/Application Support" --destination "$BACKUP" \
            || { printf 'Could not copy the installed app data from %s; nothing was installed.\n' "$PHYSICAL_UDID" >&2; exit 1; }
        printf 'Copied the installed app data to %s\n' "$BACKUP"
    fi
    xcrun devicectl device install app --device "$PHYSICAL_UDID" "$APP"
    xcrun devicectl device process launch --device "$PHYSICAL_UDID" --terminate-existing "$BUNDLE_ID"
    sleep "$LAUNCH_SETTLE_SECONDS"
    processes="$(xcrun devicectl device info processes --device "$PHYSICAL_UDID" 2>/dev/null || true)"
    grep -q '/Inku.app/' <<< "$processes" || {
        printf '%s is not running on %s %s seconds after launch.\n' "$BUNDLE_ID" "$PHYSICAL_UDID" "$LAUNCH_SETTLE_SECONDS" >&2
        exit 1
    }
    printf 'Built, installed and launched iOS application %s (%s) on %s: %s\n' "$MARKETING_VERSION" "$BUILD_NUMBER" "$PHYSICAL_UDID" "$APP"
    exit 0
fi

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
printf 'Built iOS Simulator application %s (%s), signed to run locally: %s\n' "$MARKETING_VERSION" "$BUILD_NUMBER" "$APP"
