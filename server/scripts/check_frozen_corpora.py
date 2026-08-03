"""Run the frozen-corpus guard the way CI runs it, before pushing.

CI (`.github/workflows/reference-corpus.yml`) is the only automated check this
repository has, and it is the only one that regenerates the corpora on another
machine. The unit tests cannot stand in for it: `test_render_reference.py` and
`test_ddl_reference.py` compare frozen files with the manifest and never
re-render or re-expand anything, so a corpus can drift while the whole suite
stays green. That has happened three times -- the engine 10 platform drift, the
retired `contact` key, and the silverpoint rename -- and each time the red
arrived after the push instead of before it.

This script makes CI the backstop rather than the detector. Run it from
``server/`` before merging:

    uv run python scripts/check_frozen_corpora.py

**The generators write before their guard fires.** If this script reports drift,
the working tree already holds the new corpus. Decide which it is:

* the change was sanctioned (a rename the author ruled on, a new engine
  version) -> keep it, and run the generator a second time to confirm the run
  is clean and byte-identical;
* the change was not sanctioned -> ``git checkout -- server/reference/``.
"""
from __future__ import annotations

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


def main() -> int:
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
    print("if this was sanctioned, run the generator again -- the second run must be")
    print("clean and byte-identical. if it was not, restore it:")
    print("  git checkout -- server/reference/")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
