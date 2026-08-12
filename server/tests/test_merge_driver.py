"""Unit test for the web/BUILD_NUMBER merge driver (scripts/git/build-number-merge.sh).

The driver is what stops the shared build counter from conflicting on every
merge.  It runs non-interactively inside git, so it must always exit 0 and must
always leave a single number in %A -- there is no operator to fall back on.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "git" / "build-number-merge.sh"
SETUP = REPO_ROOT / "scripts" / "git" / "setup.sh"

# The development server carries only what the two services need, so `scripts/`
# is not there (ledger I-059). Skip on the DIRECTORY, never on the driver file:
# a rename would otherwise turn this suite into a silent skip instead of a red.
git_scripts_only = pytest.mark.skipif(
    not DRIVER.parent.is_dir(), reason="scripts/git/ is absent from this checkout"
)


def run_driver(tmp_path: Path, ours: str, base: str, theirs: str) -> tuple[int, str]:
    a = tmp_path / "A"
    o = tmp_path / "O"
    b = tmp_path / "B"
    a.write_text(ours)
    o.write_text(base)
    b.write_text(theirs)
    r = subprocess.run([str(DRIVER), str(a), str(o), str(b)], capture_output=True, text=True)
    return r.returncode, a.read_text()


@git_scripts_only
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
@git_scripts_only
def test_driver_keeps_the_larger_side(tmp_path, ours, theirs, expected):
    rc, result = run_driver(tmp_path, ours, "800\n", theirs)
    # git treats a non-zero exit as a conflict, so the driver must never fail.
    assert rc == 0
    assert result == expected


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


@pytest.mark.parametrize("target", ["test", "test-server", "test-cli", "test-web"])
@git_scripts_only
def test_make_test_entry_points_apply_repository_git_setup(target):
    result = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines().count("./scripts/git/setup.sh") == 1


@git_scripts_only
def test_setup_repairs_an_unconfigured_clone_before_merge(tmp_path):
    repo = tmp_path / "clone"
    repo.mkdir()
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "config", "user.email", "test@example.invalid")

    (repo / "scripts" / "git").mkdir(parents=True)
    (repo / "web").mkdir()
    shutil.copy2(DRIVER, repo / "scripts" / "git" / DRIVER.name)
    shutil.copy2(SETUP, repo / "scripts" / "git" / SETUP.name)
    shutil.copy2(REPO_ROOT / "Makefile", repo / "Makefile")
    (repo / ".gitattributes").write_text("web/BUILD_NUMBER merge=buildnumber\n")
    (repo / "web" / "BUILD_NUMBER").write_text("900\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-qm", "base")

    run_git(repo, "branch", "-M", "main")
    run_git(repo, "switch", "-qc", "other")
    (repo / "web" / "BUILD_NUMBER").write_text("901\n")
    run_git(repo, "commit", "-qam", "other build")
    run_git(repo, "switch", "-q", "main")
    (repo / "web" / "BUILD_NUMBER").write_text("902\n")
    run_git(repo, "commit", "-qam", "main build")

    subprocess.run(
        ["make", "git-setup"], cwd=repo, capture_output=True, text=True, check=True
    )
    configured = run_git(repo, "config", "--get", "merge.buildnumber.driver")
    assert str(repo / "scripts" / "git" / DRIVER.name) in configured.stdout

    run_git(repo, "merge", "--no-edit", "other")
    assert (repo / "web" / "BUILD_NUMBER").read_text() == "902\n"
