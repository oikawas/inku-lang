#!/usr/bin/env bash
# Keep verified copies of the Skia prebuilt binaries and print SKIA_BINARIES_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="$ROOT/core/crates/inku-display/skia-binaries.sha256"
# Archives no release publishes, built here by scripts/skia-graphite-binaries.sh.
LOCAL_LIST="$ROOT/core/crates/inku-display-gpu/skia-binaries.sha256"
CACHE="${INKU_SKIA_BINARIES_DIR:-$HOME/Library/Application Support/inku/build-cache/skia-binaries}"
RELEASES=https://github.com/rust-skia/skia-binaries/releases/download

usage() {
    cat <<'USAGE'
usage: scripts/skia-binaries.sh [--with-local] <rust-target>...

For each target, check the copy of its Skia prebuilt binaries in the cache against
core/crates/inku-display/skia-binaries.sha256, fetching it from GitHub only when it is
missing. Then print the SKIA_BINARIES_URL value that points skia-bindings at the cache:

  SKIA_BINARIES_URL="$(scripts/skia-binaries.sh aarch64-apple-darwin)" scripts/rust-toolchain.sh test --locked -p inku-display --features skia

Archives listed in core/crates/inku-display-gpu/skia-binaries.sha256 (Skia with
Graphite for the macOS GPU windows) are never fetched: scripts/skia-graphite-binaries.sh
builds them. A present one is always checked; --with-local also requires each of them.

Cache: ~/Library/Application Support/inku/build-cache/skia-binaries (INKU_SKIA_BINARIES_DIR).
A copy that does not match is refused and left in place for inspection.
USAGE
}

REQUIRE_LOCAL=false
if [[ "${1:-}" == --with-local ]]; then
    REQUIRE_LOCAL=true
    shift
fi
[[ $# -gt 0 && "$1" != -h && "$1" != --help ]] || { usage >&2; exit 2; }
for list in "$LIST" "$LOCAL_LIST"; do
    [[ -f "$list" ]] || { printf 'missing digest list: %s\n' "$list" >&2; exit 2; }
done

digest() {
    shasum -a 256 "$1" | awk '{print $1}'
}

for target in "$@"; do
    # The digest list owns each target's complete feature key, including Android's.
    line="$(awk -v marker="-$target-" '!/^#/ && NF == 2 && index($2, marker) && $2 ~ /[.]tar[.]gz$/ { print }' "$LIST")"
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
    while IFS= read -r line; do
        expected="${line%% *}"
        file="$CACHE/${line##* }"
        if [[ ! -f "$file" ]]; then
            [[ "$REQUIRE_LOCAL" == false ]] || {
                printf 'missing %s: build it with scripts/skia-graphite-binaries.sh\n' "$file" >&2
                exit 1
            }
            continue
        fi
        actual="$(digest "$file")"
        [[ "$actual" == "$expected" ]] || {
            printf 'refusing %s: sha256 %s, expected %s (rebuilt? update %s)\n' "$file" "$actual" "$expected" "$LOCAL_LIST" >&2
            exit 1
        }
    done < <(awk -v marker="-$target-" '!/^#/ && NF == 2 && index($2, marker) && $2 ~ /[.]tar[.]gz$/ { print }' "$LOCAL_LIST")
done

# skia-bindings fills in {tag} (its version) and {key}; a file:// URL is read as a path.
printf 'file://%s/{tag}/skia-binaries-{key}.tar.gz\n' "$CACHE"
