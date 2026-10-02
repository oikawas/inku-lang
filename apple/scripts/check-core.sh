#!/usr/bin/env bash
# Run the bounded owned-boundary fixture after build-core.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec xcrun swift run --package-path "$ROOT/apple/Packages/InkuCore" \
    --scratch-path "$ROOT/apple/scripts/.build/swift-core-check" InkuCoreCheck
