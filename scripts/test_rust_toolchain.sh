#!/usr/bin/env bash
# Focused regression for the repository Rust entry point.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT/scripts/rust-toolchain.sh"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/inku-rust-toolchain-test.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

[[ -x "$RUNNER" ]] || {
    printf 'missing executable Rust toolchain guard: %s\n' "$RUNNER" >&2
    exit 1
}

FAKE_HOME="$TEST_DIR/cargo home"
RUSTUP_HOME="$TEST_DIR/rustup home"
TOOLCHAIN_BIN="$RUSTUP_HOME/toolchains/1.95.0-fake/bin"
BREW_BIN="$TEST_DIR/homebrew/bin"
LOG="$TEST_DIR/cargo.log"
VALIDATION_LOG="$TEST_DIR/validation.log"
BREW_MARKER="$TEST_DIR/homebrew-used"
mkdir -p "$FAKE_HOME/.cargo/bin" "$TOOLCHAIN_BIN" "$BREW_BIN"

cat > "$FAKE_HOME/.cargo/bin/rustup" <<'FAKE_RUSTUP'
#!/bin/sh
set -eu
[ "$1" = which ]
[ "$2" = --toolchain ]
[ "$3" = 1.95.0 ]
tool="$4"
printf 'which %s\n' "$tool" >> "$INKU_RUST_VALIDATION_LOG"
printf '%s/toolchains/1.95.0-fake/bin/%s\n' "$RUSTUP_HOME" "$tool"
FAKE_RUSTUP

cat > "$TOOLCHAIN_BIN/cargo" <<'FAKE_CARGO'
#!/bin/sh
set -eu
if [ "${1:-}" = --version ]; then
    printf 'cargo version\n' >> "$INKU_RUST_VALIDATION_LOG"
    printf 'cargo 1.95.0 (pinned-test)\n'
    exit 0
fi
{
    printf 'cargo=%s\n' "$0"
    printf 'rustc=%s\n' "$RUSTC"
    printf 'path_head=%s\n' "${PATH%%:*}"
    printf 'pwd=%s\n' "$PWD"
    printf 'args=%s\n' "$*"
    for arg do printf 'arg=<%s>\n' "$arg"; done
} >> "$INKU_RUST_GUARD_TEST_LOG"
if [ "${1:-}" = fail ]; then exit 37; fi
FAKE_CARGO

cat > "$TOOLCHAIN_BIN/rustc" <<'FAKE_RUSTC'
#!/bin/sh
set -eu
if [ "${1:-}" = --version ]; then
    printf 'rustc version\n' >> "$INKU_RUST_VALIDATION_LOG"
    printf 'rustc 1.95.0 (pinned-test)\n'
    exit 0
fi
exit 0
FAKE_RUSTC

cat > "$TOOLCHAIN_BIN/rustdoc" <<'FAKE_RUSTDOC'
#!/bin/sh
exit 0
FAKE_RUSTDOC

for tool in cargo rustc; do
    cat > "$BREW_BIN/$tool" <<'FAKE_HOMEBREW'
#!/bin/sh
printf 'Homebrew Rust was invoked\n' > "$INKU_RUST_GUARD_BREW_MARKER"
exit 90
FAKE_HOMEBREW
done
chmod +x "$FAKE_HOME/.cargo/bin/rustup" "$TOOLCHAIN_BIN"/* "$BREW_BIN"/*

CARGO_HOME="$FAKE_HOME/.cargo" \
RUSTUP_HOME="$RUSTUP_HOME" \
INKU_RUSTUP_BIN="$FAKE_HOME/.cargo/bin/rustup" \
INKU_RUST_GUARD_TEST_LOG="$LOG" \
INKU_RUST_VALIDATION_LOG="$VALIDATION_LOG" \
INKU_RUST_GUARD_BREW_MARKER="$BREW_MARKER" \
RUSTC="$BREW_BIN/rustc" \
PATH="$BREW_BIN:/usr/bin:/bin" \
    "$RUNNER" check --workspace --locked

[[ ! -e "$BREW_MARKER" ]] || {
    printf 'guard invoked Homebrew Rust\n' >&2
    exit 1
}
grep -Fx "cargo=$TOOLCHAIN_BIN/cargo" "$LOG" >/dev/null
grep -Fx "rustc=$TOOLCHAIN_BIN/rustc" "$LOG" >/dev/null
grep -Fx "path_head=$TOOLCHAIN_BIN" "$LOG" >/dev/null
grep -Fx "pwd=$ROOT/core" "$LOG" >/dev/null
grep -Fx 'args=check --workspace --locked' "$LOG" >/dev/null

BAD_RUSTUP="$TEST_DIR/bad-rustup"
cat > "$BAD_RUSTUP" <<FAKE_BAD_RUSTUP
#!/bin/sh
printf '%s/%s\n' '$BREW_BIN' "\$4"
FAKE_BAD_RUSTUP
chmod +x "$BAD_RUSTUP"

set +e
CARGO_HOME="$FAKE_HOME/.cargo" RUSTUP_HOME="$RUSTUP_HOME" INKU_RUSTUP_BIN="$BAD_RUSTUP" \
PATH="$BREW_BIN:/usr/bin:/bin" "$RUNNER" check > "$TEST_DIR/rejected.txt" 2>&1
REJECTED_STATUS=$?
set -e
[[ "$REJECTED_STATUS" == 2 ]] || {
    printf 'untrusted Rust path must be rejected with exit 2\n' >&2
    exit 1
}
grep -F 'refusing Rust tool outside rustup toolchains' "$TEST_DIR/rejected.txt" >/dev/null

run_wrapper() {
    CARGO_HOME="$FAKE_HOME/.cargo" RUSTUP_HOME="$RUSTUP_HOME" \
    INKU_RUSTUP_BIN="$FAKE_HOME/.cargo/bin/rustup" \
    INKU_RUST_GUARD_TEST_LOG="$LOG" INKU_RUST_VALIDATION_LOG="$VALIDATION_LOG" \
    PATH="$BREW_BIN:/usr/bin:/bin" "$RUNNER" "$@"
}

# Wrapper help does not require Rust; Cargo help still goes through the guard.
INKU_RUSTUP_BIN="$TEST_DIR/missing" "$RUNNER" --wrapper-help > "$TEST_DIR/help.txt"
grep -F -- '--batch' "$TEST_DIR/help.txt" >/dev/null
: > "$LOG"
run_wrapper --help
grep -Fx 'args=--help' "$LOG" >/dev/null

# One validation for multiple commands, with exact argument boundaries retained.
: > "$LOG"
: > "$VALIDATION_LOG"
run_wrapper --batch fmt --all ::: test -p example -- 'a filter with spaces' ''
[[ "$(wc -l < "$VALIDATION_LOG" | tr -d ' ')" == 5 ]]
grep '^args=' "$LOG" > "$TEST_DIR/actual-order.txt"
printf '%s\n' 'args=fmt --all' 'args=test -p example -- a filter with spaces ' > "$TEST_DIR/expected-order.txt"
cmp "$TEST_DIR/expected-order.txt" "$TEST_DIR/actual-order.txt"
grep -Fx 'arg=<a filter with spaces>' "$LOG" >/dev/null
grep -Fx 'arg=<>' "$LOG" >/dev/null

# Preserve the first failing exit code and never execute later commands.
: > "$LOG"
status=0
run_wrapper --batch check ::: fail ::: never-run || status=$?
[[ "$status" == 37 ]]
[[ "$(grep -c '^args=' "$LOG")" == 2 ]]
! grep -F 'never-run' "$LOG"
status=0
run_wrapper fail || status=$?
[[ "$status" == 37 ]]

# Validate the complete batch before any Cargo side effects.
for malformed in empty leading trailing consecutive; do
    : > "$LOG"
    case "$malformed" in
        empty) set -- --batch ;;
        leading) set -- --batch ::: check ;;
        trailing) set -- --batch check ::: ;;
        consecutive) set -- --batch check ::: ::: test ;;
    esac
    status=0
    run_wrapper "$@" > "$TEST_DIR/invalid.txt" 2>&1 || status=$?
    [[ "$status" == 2 && ! -s "$LOG" ]]
done

# A separator remains a literal argument outside explicit batch mode.
: > "$LOG"
run_wrapper test -- :::
grep -Fx 'arg=<:::>' "$LOG" >/dev/null

printf 'rust-toolchain guard regression: PASS\n'
