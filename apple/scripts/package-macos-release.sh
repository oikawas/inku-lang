#!/usr/bin/env bash
# Build, Developer ID sign, notarize and package the macOS application as a .dmg.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLE="$ROOT/apple"
BUILT_APP="$APPLE/build/macOS/DerivedData/Build/Products/Release/Inku.app"
ENTITLEMENTS="$APPLE/Configuration/Inku.entitlements"
BUNDLE_ID=app.inku.macos
IDENTITY="${INKU_MACOS_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${INKU_MACOS_NOTARY_PROFILE:-}"
NOTARIZE=true
BUILD_APP=true
ALLOW_DIRTY=false

usage() {
    cat >&2 <<'USAGE'
usage: apple/scripts/package-macos-release.sh --identity NAME
           (--notary-profile PROFILE | --skip-notarization) [--skip-build] [--allow-dirty]

Builds the Release Universal app without stopping running Inku instances, signs
it inside out with Hardened Runtime and a Developer ID Application identity,
makes a signed .dmg with an Applications link, notarizes and staples it, checks
Gatekeeper, and records the SHA-256 in apple/build/release/Inku-<version>-<build>/.

--identity          codesign identity (or INKU_MACOS_SIGN_IDENTITY)
--notary-profile    notarytool keychain profile (or INKU_MACOS_NOTARY_PROFILE)
--skip-notarization stop after signing the .dmg; Gatekeeper then rejects it
--skip-build        sign the app from the last apple/scripts/build-macos.sh Release
--allow-dirty       package a checkout with uncommitted changes (not for release)
Neither the identity nor the profile is stored in the repository.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --identity) [[ $# -ge 2 ]] || { usage; exit 2; }; IDENTITY="$2"; shift 2 ;;
        --notary-profile) [[ $# -ge 2 ]] || { usage; exit 2; }; NOTARY_PROFILE="$2"; shift 2 ;;
        --skip-notarization) NOTARIZE=false; shift ;;
        --skip-build) BUILD_APP=false; shift ;;
        --allow-dirty) ALLOW_DIRTY=true; shift ;;
        *) usage; exit 2 ;;
    esac
done
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail 'Packaging the macOS application requires macOS and Xcode.'
[[ "$IDENTITY" == "Developer ID Application: "* ]] || { usage; fail 'A Developer ID Application identity is required.'; }
if [[ "$NOTARIZE" == true && -z "$NOTARY_PROFILE" ]]; then usage; fail 'Pass --notary-profile or --skip-notarization.'; fi
/usr/bin/security find-identity -v -p codesigning | /usr/bin/grep -qF "\"$IDENTITY\"" \
    || fail 'The signing identity is not a valid code signing identity in the keychain.'
DIRTY="$(git -C "$ROOT" status --porcelain)"
[[ -z "$DIRTY" || "$ALLOW_DIRTY" == true ]] || fail 'The checkout has uncommitted changes; commit them or pass --allow-dirty.'

VERSION="$(tr -d '[:space:]' < "$APPLE/VERSION")"
BUILD_NUMBER="$(tr -d '[:space:]' < "$APPLE/BUILD_NUMBER")"
if [[ "$BUILD_APP" == true ]]; then
    # The release uses release Rust archives and the committed resource snapshot.
    env -u INKU_APPLE_REFERENCE_ROOT INKU_APPLE_PROFILE=release "$APPLE/scripts/build-macos.sh" Release --keep-running
fi
[[ -d "$BUILT_APP" ]] || fail "No Release build at $BUILT_APP"
python3 "$APPLE/scripts/build-macos-notices.py" --check
cmp -s "$APPLE/Sources/InkuUI/Resources/third-party-notices.json" \
    "$BUILT_APP/Contents/Resources/InkuApple_InkuUI.bundle/Contents/Resources/third-party-notices.json" \
    || fail 'The built app carries different third-party notices; rebuild it.'

plist() { /usr/libexec/PlistBuddy -c "Print :$2" "$1/Contents/Info.plist" 2>/dev/null; }
[[ "$(plist "$BUILT_APP" CFBundleShortVersionString)" == "$VERSION" \
    && "$(plist "$BUILT_APP" CFBundleVersion)" == "$BUILD_NUMBER" ]] || fail 'The built app version differs from apple/VERSION and apple/BUILD_NUMBER.'
[[ "$(plist "$BUILT_APP" CFBundleIdentifier)" == "$BUNDLE_ID" ]] || fail "The release bundle identifier must be $BUNDLE_ID."
# The author's review database path is installed only into the unsigned local app.
! plist "$BUILT_APP" InkuDatabasePath >/dev/null || fail 'The release app must not name a database path.'

OUT="$APPLE/build/release/Inku-$VERSION-$BUILD_NUMBER"
APP="$OUT/Inku.app"
DMG="$OUT/Inku-macOS-$VERSION.dmg"
rm -rf "$OUT"
mkdir -p "$OUT"
/usr/bin/ditto "$BUILT_APP" "$APP"

# Sign nested code before its container: standalone Mach-O files, or the
# innermost enclosing bundle, deepest first. The main executable is the app's.
NESTED=()
while IFS= read -r -d '' file; do
    [[ "$file" != "$APP/Contents/MacOS/Inku" ]] || continue
    /usr/bin/file -b "$file" | /usr/bin/grep -q 'Mach-O' || continue
    target="$file"
    directory="$(dirname "$file")"
    while [[ "$directory" != "$APP" ]]; do
        case "$directory" in
            *.framework|*.bundle|*.plugin|*.xpc|*.appex|*.app) target="$directory"; break ;;
        esac
        directory="$(dirname "$directory")"
    done
    NESTED+=("$target")
done < <(find "$APP/Contents" -type f -print0)
if [[ ${#NESTED[@]} -gt 0 ]]; then
    while IFS= read -r target; do
        codesign --force --options runtime --timestamp --sign "$IDENTITY" "$target"
    done < <(printf '%s\n' "${NESTED[@]}" | awk -F/ '{ print NF "\t" $0 }' | sort -u | sort -t$'\t' -k1,1nr | cut -f2-)
fi
codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$APP"
printf 'Signed %d nested code item(s) and the application.\n' "${#NESTED[@]}"

codesign --verify --deep --strict --verbose=2 "$APP"
DETAILS="$(codesign -d --verbose=4 "$APP" 2>&1)"
printf '%s\n' "$DETAILS" | /usr/bin/grep -qE '^CodeDirectory .* flags=0x[0-9a-f]+\(([a-z-]+,)*runtime[,)]' \
    || fail 'Signed app lacks the Hardened Runtime flag.'
for expected in "Identifier=$BUNDLE_ID" 'Authority=Developer ID Application: ' 'Timestamp='; do
    printf '%s\n' "$DETAILS" | /usr/bin/grep -qF "$expected" || fail "Signed app lacks $expected"
done
TEAM_ID="$(printf '%s\n' "$DETAILS" | sed -n 's/^TeamIdentifier=//p')"
[[ -n "$TEAM_ID" && "$TEAM_ID" != "not set" ]] || fail 'Signed app has no Team ID.'
codesign -d --entitlements :- "$APP" > "$OUT/entitlements.plist" 2>/dev/null
[[ "$(plutil -convert json -o - "$OUT/entitlements.plist")" == "$(plutil -convert json -o - "$ENTITLEMENTS")" ]] \
    || fail 'Signed entitlements differ from apple/Configuration/Inku.entitlements.'

STAGE="$OUT/dmg-root"
mkdir "$STAGE"
/usr/bin/ditto "$APP" "$STAGE/Inku.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "Inku $VERSION" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"
rm -rf "$STAGE"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"
codesign --verify --strict --verbose=2 "$DMG"

SUBMISSION_ID=""
if [[ "$NOTARIZE" == true ]]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait --output-format json \
        > "$OUT/notary-submit.json"
    SUBMISSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$OUT/notary-submit.json")"
    STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$OUT/notary-submit.json")"
    xcrun notarytool log "$SUBMISSION_ID" --keychain-profile "$NOTARY_PROFILE" "$OUT/notary-log.json" || true
    [[ "$STATUS" == Accepted ]] || fail "Notarization $SUBMISSION_ID ended as $STATUS; see $OUT/notary-log.json"
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
fi

# Gatekeeper sees the app as a user does: inside the mounted .dmg.
MOUNT="$(mktemp -d "${TMPDIR:-/tmp}/inku-release.XXXXXX")"
hdiutil attach -quiet -nobrowse -readonly -noautoopen -mountpoint "$MOUNT" "$DMG"
trap 'hdiutil detach -quiet "$MOUNT" 2>/dev/null || true; rmdir "$MOUNT" 2>/dev/null || true' EXIT
[[ -L "$MOUNT/Applications" && "$(readlink "$MOUNT/Applications")" == /Applications ]] || fail 'The .dmg lacks its Applications link.'
codesign --verify --deep --strict --verbose=2 "$MOUNT/Inku.app"
GATEKEEPER_APP="$(spctl -a -vvv -t exec "$MOUNT/Inku.app" 2>&1 || true)"
GATEKEEPER_DMG="$(spctl -a -t open --context context:primary-signature -vvv "$DMG" 2>&1 || true)"
printf '%s\n%s\n' "$GATEKEEPER_APP" "$GATEKEEPER_DMG" | tee "$OUT/gatekeeper.txt"
if [[ "$NOTARIZE" == true ]]; then
    for result in "$GATEKEEPER_APP" "$GATEKEEPER_DMG"; do
        printf '%s\n' "$result" | /usr/bin/grep -q 'source=Notarized Developer ID' || fail 'Gatekeeper did not accept the notarized release.'
    done
else
    printf 'Notarization skipped: Gatekeeper is expected to reject this .dmg.\n'
fi

SHA256="$(shasum -a 256 "$DMG" | cut -d' ' -f1)"
printf '%s  %s\n' "$SHA256" "$(basename "$DMG")" > "$DMG.sha256"
# The Release attachment carries the same notices the app shows under About inku.
NOTICES="$OUT/Inku-macOS-$VERSION-THIRD-PARTY-NOTICES.txt"
python3 "$APPLE/scripts/build-macos-notices.py" --text "$NOTICES"
python3 - "$ROOT" "$OUT/release.json" "$DMG" "$SHA256" "$VERSION" "$BUILD_NUMBER" "$TEAM_ID" "$NOTARIZE" "$SUBMISSION_ID" "${DIRTY:+dirty}" "$NOTICES" <<'__INKU_RELEASE_RECORD__'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root, output, dmg = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sha256, version, build, team, notarized, submission, dirty = sys.argv[4:11]
notices = Path(sys.argv[11])
reference = json.loads((root / "apple/Sources/InkuUI/Resources/ui-reference.json").read_text())
core = json.loads((root / "apple/Packages/InkuCore/Artifacts/build-manifest.json").read_text())
record = {
    "schema": "inku.macos-release.v1",
    "version": version, "build": build,
    "server_reference": {"version": reference["version"], "build": reference["build"]},
    "product_commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
    "checkout_dirty": dirty == "dirty",
    "rust_archives": core["archives"],
    "dmg": dmg.name, "bytes": dmg.stat().st_size, "sha256": sha256,
    "team_id": team, "notarized": notarized == "true", "notary_submission_id": submission or None,
    "notices": notices.name, "notices_sha256": hashlib.sha256(notices.read_bytes()).hexdigest(),
}
output.write_text(json.dumps(record, indent=2) + "\n")
__INKU_RELEASE_RECORD__
printf 'Packaged %s (%s, build %s)\nSHA-256 %s\n' "$DMG" "$VERSION" "$BUILD_NUMBER" "$SHA256"
