#!/usr/bin/env bash
# Run this repository's Rust commands with the pinned rustup toolchain.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLCHAIN_FILE="$ROOT/core/rust-toolchain.toml"

usage() {
    cat <<'USAGE'
usage: scripts/rust-toolchain.sh <cargo arguments...>
       scripts/rust-toolchain.sh --batch <cargo arguments...> ::: <cargo arguments...>
       scripts/rust-toolchain.sh --wrapper-help

Run Cargo in this checkout's core/ with the pinned rustup toolchain.
--batch validates the toolchain once, then runs the selected commands in order.
The first failure stops the batch and its exit code is returned unchanged.
::: is reserved as a command separator only in batch mode; empty commands fail
before any Cargo command runs. Arguments are passed as-is, without shell eval.
Cargo --help is forwarded normally. No toolchains are installed automatically.

Examples:
  scripts/rust-toolchain.sh test -p inku-ddl --locked --offline --test score_lowering
  scripts/rust-toolchain.sh --batch fmt --all -- --check ::: test -p inku-ddl --locked --offline --test score_lowering

Overrides: INKU_RUSTUP_BIN, CARGO_HOME, RUSTUP_HOME (standard rustup locations).
USAGE
}

[[ $# -gt 0 ]] || { usage >&2; exit 2; }
if [[ "$1" == --wrapper-help ]]; then
    [[ $# -eq 1 ]] || { usage >&2; exit 2; }
    usage
    exit 0
fi

BATCH=false
if [[ "$1" == --batch ]]; then
    BATCH=true
    shift
    # Check every boundary up front; an invalid later group must not run an
    # earlier command that might write files.
    command_size=0
    for argument in "$@"; do
        if [[ "$argument" == ::: ]]; then
            [[ "$command_size" -gt 0 ]] || { usage >&2; exit 2; }
            command_size=0
        else
            command_size=$((command_size + 1))
        fi
    done
    [[ "$command_size" -gt 0 ]] || { usage >&2; exit 2; }
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
    if ! path="$("$RUSTUP_BIN" which --toolchain "$CHANNEL" "$tool" 2>/dev/null)"; then
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

CARGO_VERSION="$("$CARGO_BIN" --version | awk '{print $2; exit}')"
RUSTC_VERSION="$("$RUSTC_BIN" --version | awk '{print $2; exit}')"
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
if [[ "$BATCH" == true ]]; then
    command_args=()
    for argument in "$@"; do
        if [[ "$argument" == ::: ]]; then
            "$CARGO_BIN" "${command_args[@]}" || exit "$?"
            command_args=()
        else
            command_args+=("$argument")
        fi
    done
    exec "$CARGO_BIN" "${command_args[@]}"
fi
exec "$CARGO_BIN" "$@"
