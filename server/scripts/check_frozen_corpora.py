"""Run a full frozen-corpus update at an explicit migration checkpoint.

This is not a normal pre-push or version-bump check. Use it only when an
overall migration has reached its explicit full-update checkpoint. Ordinary
changes select focused validation from their risk; an engine version alone does
not require a corpus update or a current-version reference directory.

Run from ``server/`` only with the explicit acknowledgement:

    uv run python scripts/check_frozen_corpora.py --full-update
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

SERVER_DIR = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_DIR.parent
REFERENCE = "server/reference/"
GENERATORS = ("scripts/gen_render_reference.py", "scripts/gen_ddl_reference.py")


def _run_generator(script: str) -> int:
    print(f"$ uv run python {script}", flush=True)
    completed = subprocess.run([sys.executable, script], cwd=SERVER_DIR)
    return completed.returncode


def _dirty_paths() -> list[str]:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", REFERENCE],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    return [line for line in status.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full-update",
        action="store_true",
        help="regenerate both corpora at an explicitly approved migration checkpoint",
    )
    args = parser.parse_args(argv)
    if not args.full_update:
        parser.error("--full-update is required; this is not a routine version-bump check")
    before = _dirty_paths()
    if before:
        print("server/reference/ is already dirty before the run; commit or restore it first:")
        for line in before:
            print(f"  {line}")
        return 2

    guards_fired = [script for script in GENERATORS if _run_generator(script) != 0]
    after = _dirty_paths()

    if not after and not guards_fired:
        # This bakes and compares on one machine, so it cannot speak for CI.
        # Until engine 21 it claimed it could, and said so for the two days CI
        # was red over a macOS/Linux libm difference (ledger I-111).
        print(f"frozen corpora are byte-identical on this machine ({sys.platform}).")
        return 0

    print()
    print("the frozen corpora moved:")
    for line in after:
        print(f"  {line}")
    if guards_fired:
        print(f"identity guard fired in: {', '.join(guards_fired)}")
    print()
    print("resolve the cause before repeating this explicit full update.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
