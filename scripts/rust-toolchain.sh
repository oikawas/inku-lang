#!/usr/bin/env bash
# Run this repository's Rust commands with the pinned rustup toolchain.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLCHAIN_FILE="$ROOT/core/rust-toolchain.toml"

if [[ $# -eq 0 ]]; then
    printf 'usage: scripts/rust-toolchain.sh <cargo arguments...>\n' >&2
    exit 2
fi

[[ -f "$TOOLCHAIN_FILE" ]] || {
    printf 'missing Rust toolchain contract: %s\n' "$TOOLCHAIN_FILE" >&2
    exit 2
}

CHANNEL="$(awk -F'"' '/^[[:space:]]*channel[[:space:]]*=/ { print $2; exit }' "$TOOLCHAIN_FILE")"
[[ -n "$CHANNEL" ]] || {
    printf 'missing Rust channel in %s\n' "$TOOLCHAIN_FILE" >&2
    exit 2
}

RUSTUP_BIN="${INKU_RUSTUP_BIN:-${CARGO_HOME:-$HOME/.cargo}/bin/rustup}"
RUSTUP_TOOLCHAINS="${RUSTUP_HOME:-$HOME/.rustup}/toolchains"
[[ -x "$RUSTUP_BIN" ]] || {
    printf 'missing rustup executable: %s\n' "$RUSTUP_BIN" >&2
    printf 'install rustup and toolchain %s; Homebrew Rust is not accepted\n' "$CHANNEL" >&2
    exit 2
}

resolve_tool() {
    local tool="$1" path
    if ! path="$($RUSTUP_BIN which --toolchain "$CHANNEL" "$tool" 2>/dev/null)"; then
        printf 'rustup toolchain %s does not provide %s\n' "$CHANNEL" "$tool" >&2
        exit 2
    fi
    case "$path" in
        "$RUSTUP_TOOLCHAINS"/*/bin/"$tool") ;;
        *)
            printf 'refusing Rust tool outside rustup toolchains: %s\n' "$path" >&2
            exit 2 ;;
    esac
    [[ -x "$path" ]] || {
        printf 'Rust tool is not executable: %s\n' "$path" >&2
        exit 2
    }
    printf '%s\n' "$path"
}

CARGO_BIN="$(resolve_tool cargo)"
RUSTC_BIN="$(resolve_tool rustc)"
RUSTDOC_BIN="$(resolve_tool rustdoc)"

CARGO_VERSION="$($CARGO_BIN --version | awk '{print $2; exit}')"
RUSTC_VERSION="$($RUSTC_BIN --version | awk '{print $2; exit}')"
if [[ "$CARGO_VERSION" != "$CHANNEL" || "$RUSTC_VERSION" != "$CHANNEL" ]]; then
    printf 'refusing Rust version mismatch: required=%s cargo=%s rustc=%s\n' \
        "$CHANNEL" "$CARGO_VERSION" "$RUSTC_VERSION" >&2
    exit 2
fi

TOOLCHAIN_BIN="$(dirname "$CARGO_BIN")"
export PATH="$TOOLCHAIN_BIN:$PATH"
export CARGO="$CARGO_BIN"
export RUSTC="$RUSTC_BIN"
export RUSTDOC="$RUSTDOC_BIN"
export RUSTUP_TOOLCHAIN="$CHANNEL"

cd "$ROOT/core"
exec "$CARGO_BIN" "$@"
