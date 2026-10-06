#!/usr/bin/env bash
# Keep verified copies of the Skia prebuilt binaries and print SKIA_BINARIES_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="$ROOT/core/crates/inku-display/skia-binaries.sha256"
CACHE="${INKU_SKIA_BINARIES_DIR:-$HOME/Library/Application Support/inku/build-cache/skia-binaries}"
FEATURES=jpegd-jpege-pdf-svg-textlayout-webpd-webpe
RELEASES=https://github.com/rust-skia/skia-binaries/releases/download

usage() {
    cat <<'USAGE'
usage: scripts/skia-binaries.sh <rust-target>...

For each target, check the copy of its Skia prebuilt binaries in the cache against
core/crates/inku-display/skia-binaries.sha256, fetching it from GitHub only when it is
missing. Then print the SKIA_BINARIES_URL value that points skia-bindings at the cache:

  SKIA_BINARIES_URL="$(scripts/skia-binaries.sh aarch64-apple-darwin)" scripts/rust-toolchain.sh test --locked -p inku-display --features skia

Cache: ~/Library/Application Support/inku/build-cache/skia-binaries (INKU_SKIA_BINARIES_DIR).
A copy that does not match is refused and left in place for inspection.
USAGE
}

[[ $# -gt 0 && "$1" != -h && "$1" != --help ]] || { usage >&2; exit 2; }
[[ -f "$LIST" ]] || { printf 'missing digest list: %s\n' "$LIST" >&2; exit 2; }

digest() {
    shasum -a 256 "$1" | awk '{print $1}'
}

for target in "$@"; do
    line="$(awk -v suffix="-$target-$FEATURES.tar.gz" '!/^#/ && length($2) > length(suffix) && substr($2, length($2) - length(suffix) + 1) == suffix' "$LIST")"
    [[ -n "$line" && "$(printf '%s\n' "$line" | wc -l | tr -d ' ')" == 1 ]] || {
        printf 'no Skia binaries listed for %s in %s\n' "$target" "$LIST" >&2
        exit 2
    }
    expected="${line%% *}"
    name="${line##* }"
    file="$CACHE/$name"
    if [[ ! -f "$file" ]]; then
        mkdir -p "$(dirname "$file")"
        partial="$file.partial"
        printf 'fetching %s\n' "$RELEASES/$name" >&2
        curl --fail --location --silent --show-error --output "$partial" "$RELEASES/$name"
        actual="$(digest "$partial")"
        [[ "$actual" == "$expected" ]] || {
            printf 'refusing download %s: sha256 %s, expected %s\n' "$partial" "$actual" "$expected" >&2
            exit 1
        }
        mv "$partial" "$file"
    fi
    actual="$(digest "$file")"
    [[ "$actual" == "$expected" ]] || {
        printf 'refusing %s: sha256 %s, expected %s\n' "$file" "$actual" "$expected" >&2
        exit 1
    }
done

# skia-bindings fills in {tag} (its version) and {key}; a file:// URL is read as a path.
printf 'file://%s/{tag}/skia-binaries-{key}.tar.gz\n' "$CACHE"
