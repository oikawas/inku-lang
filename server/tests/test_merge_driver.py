"""Unit test for the web/BUILD_NUMBER merge driver (scripts/git/build-number-merge.sh).

The driver is what stops the shared build counter from conflicting on every
merge.  It runs non-interactively inside git, so it must always exit 0 and must
always leave a single number in %A -- there is no operator to fall back on.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "git" / "build-number-merge.sh"


def run_driver(tmp_path: Path, ours: str, base: str, theirs: str) -> tuple[int, str]:
    a = tmp_path / "A"
    o = tmp_path / "O"
    b = tmp_path / "B"
    a.write_text(ours)
    o.write_text(base)
    b.write_text(theirs)
    r = subprocess.run([str(DRIVER), str(a), str(o), str(b)], capture_output=True, text=True)
    return r.returncode, a.read_text()


def test_driver_is_executable():
    assert DRIVER.is_file(), f"missing driver: {DRIVER}"
    assert DRIVER.stat().st_mode & 0o111, "driver must be executable for git to run it"


@pytest.mark.parametrize(
    "ours,theirs,expected",
    [
        ("818\n", "817\n", "818\n"),  # ours is larger
        ("817\n", "818\n", "818\n"),  # theirs is larger
        ("817\n", "817\n", "817\n"),  # identical -- still resolves, still exits 0
        ("\n", "817\n", "817\n"),  # non-numeric ours counts as 0
    ],
)
def test_driver_keeps_the_larger_side(tmp_path, ours, theirs, expected):
    rc, result = run_driver(tmp_path, ours, "800\n", theirs)
    # git treats a non-zero exit as a conflict, so the driver must never fail.
    assert rc == 0
    assert result == expected
