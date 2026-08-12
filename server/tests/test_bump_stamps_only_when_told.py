"""`scripts/bump.py` must not write unless it is told to (ledger I-195).

`--scan-build` reads like "print the next build number", and running it alone
stamped six files -- web/BUILD_NUMBER, both project-context files and both
version-marker tables -- on a checkout where the number was only being looked
up.  Nothing failed and nothing warned; the write was silent and looked
correct.  The default is now read-only and `--write` does the stamping.

These tests run the script against a scratch copy of the tree, never the real
one.  If the guard regresses, the damage stays in tmp_path instead of moving
the repository's own build number -- which is a shared counter, so a stray
increment is not a local mistake.

They are skipped, not failed, when a source file is absent: the deployment host
carries only `server/` and `web/src` (the same partial-tree failure mode ledger
item I-059 records).
"""

import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPT = "scripts/bump.py"

# The six files one stamping touches, in the script's own order.
STAMPED = (
    "web/APP_VERSION",
    "web/BUILD_NUMBER",
    "PROJECT_CONTEXT.ja.md",
    "PROJECT_CONTEXT.md",
    "docs/spec/render-engine-history.ja.md",
    "docs/spec/render-engine-history.md",
)


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway copy of the stamped files, with one commit so refs exist."""
    for rel in (SCRIPT, *STAMPED):
        src = ROOT / rel
        if not src.exists():
            pytest.skip(f"{rel} is absent (partial tree)")
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # --scan-build reads web/BUILD_NUMBER out of every local ref, so the copy
    # needs a repository of its own rather than the caller's.
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(
        tmp_path,
        "-c", "user.email=bump-test@example.invalid",
        "-c", "user.name=bump test",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", "seed", "--no-verify",
    )
    return tmp_path


def _run(tree: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tree / SCRIPT), *args],
        cwd=tree, capture_output=True, text=True,
    )


def _snapshot(tree: pathlib.Path) -> dict[str, bytes]:
    return {rel: (tree / rel).read_bytes() for rel in STAMPED}


def _changed(before: dict[str, bytes], tree: pathlib.Path) -> list[str]:
    return [rel for rel, blob in before.items() if (tree / rel).read_bytes() != blob]


def test_scan_build_alone_reports_the_next_number_and_writes_nothing(tree):
    before = _snapshot(tree)
    result = _run(tree, "--scan-build")

    assert result.returncode == 0, result.stderr
    assert "next build number" in result.stderr
    assert _changed(before, tree) == []


def test_a_version_and_a_build_without_write_change_nothing(tree):
    before = _snapshot(tree)
    result = _run(tree, "--version", "v9.9.9", "--build", "4242")

    assert result.returncode == 0, result.stderr
    assert _changed(before, tree) == []
    # The report has to say the writing did not happen, and how to make it.
    assert "would write" in result.stdout
    assert "--write" in result.stdout


def test_the_report_and_the_write_describe_the_same_files(tree):
    reported = _run(tree, "--version", "v9.9.9", "--build", "4242")
    would = [line for line in reported.stdout.splitlines() if line.startswith("would write ")]

    before = _snapshot(tree)
    stamped = _run(tree, "--version", "v9.9.9", "--build", "4242", "--write")
    wrote = [line for line in stamped.stdout.splitlines() if line.startswith("wrote ")]

    assert stamped.returncode == 0, stamped.stderr
    # A report that is not the eventual write is worse than no report: it is the
    # reason one would trust the read-only run in the first place.
    assert len(would) == len(wrote) >= len(STAMPED)
    assert sorted(_changed(before, tree)) == sorted(STAMPED)
    assert (tree / "web/APP_VERSION").read_text(encoding="utf-8").strip() == "v9.9.9"
    assert (tree / "web/BUILD_NUMBER").read_text(encoding="utf-8").strip() == "4242"
    assert "**対象バージョン: v9.9.9 / Build 4242**" in (
        tree / "PROJECT_CONTEXT.ja.md").read_text(encoding="utf-8")
    assert "**Target version: v9.9.9 / Build 4242**" in (
        tree / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")


def test_show_writes_nothing(tree):
    before = _snapshot(tree)
    result = _run(tree, "--show")

    assert result.returncode == 0, result.stderr
    assert "BUILD_NUMBER" in result.stdout
    assert _changed(before, tree) == []


def test_dry_run_is_gone_and_fails_loudly(tree):
    """The old read-only flag was removed rather than kept as a synonym.

    An old command line must not quietly mean something else; it must stop.
    """
    before = _snapshot(tree)
    result = _run(tree, "--scan-build", "--dry-run")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert _changed(before, tree) == []
