"""`scripts/bump.py --scan-build` must read every face of the counter (I-196).

`web/BUILD_NUMBER` is one counter shared by three faces: the refs, the working
copy of every worktree, and the deployment host.  The scan used to read the
first face and tell the reader, in one parenthesis, to go and check the third by
hand -- and a scan that covers two faces prints the same shape of answer as one
that covers all three, so a forgotten face looks exactly like a complete scan.

These tests give the script a scratch repository, a linked worktree and an `ssh`
of their own, then move the number on one face at a time: each face that stops
being read stops moving the answer, which is what makes a dropped face visible.
They never run against the real tree -- its build number is shared, so a stray
increment would not be a local mistake.

They are skipped, not failed, when a source file is absent: the deployment host
carries only `server/` and `web/src` (the partial-tree failure mode of I-059).
"""

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCRIPT = "scripts/bump.py"

# Enough of the tree for the script to run: it stamps six files and refuses to
# start when a pattern stopped matching.
STAMPED = (
    "web/APP_VERSION",
    "web/BUILD_NUMBER",
    "PROJECT_CONTEXT.ja.md",
    "PROJECT_CONTEXT.md",
    "docs/spec/render-engine-history.ja.md",
    "docs/spec/render-engine-history.md",
)

SEED = 100
HOST = "ddl-server@example.invalid"
REPO = "inku-lang-test"

# The two lines the script reads the deployment target out of, in the shape the
# untracked deploy script writes them.
DEPLOY_SH = f"""#!/usr/bin/env bash
REMOTE_HOST="${{INKU_REMOTE_HOST:-{HOST}}}"
REMOTE_REPO="${{INKU_REMOTE_REPO:-{REPO}}}"
"""

FAKE_SSH = """#!/bin/sh
printf '%s\\n' "$*" >> "$SSH_LOG"
if [ -n "$SSH_FAIL" ]; then
  echo "kex_exchange_identification: connection closed" >&2
  exit 255
fi
echo "$SSH_NUMBER"
"""


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd: pathlib.Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(
        cwd,
        "-c", "user.email=bump-test@example.invalid",
        "-c", "user.name=bump test",
        "-c", "commit.gpgsign=false",
        "commit", "-q", "-m", message, "--no-verify",
    )


class Tree:
    """A scratch repository plus the seams the scan reaches out through."""

    def __init__(self, root: pathlib.Path, ssh_log: pathlib.Path):
        self.root = root
        self.ssh_log = ssh_log

    def number(self, value: int, *, at: pathlib.Path | None = None) -> None:
        (at or self.root).joinpath("web/BUILD_NUMBER").write_text(
            f"{value}\n", encoding="utf-8")

    def run(self, *args: str, ssh_number: int = SEED, ssh_fail: bool = False,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        environment = dict(os.environ)
        # The caller's own deployment target must not decide what these tests
        # measure; only what a case sets explicitly does.
        environment.pop("INKU_REMOTE_HOST", None)
        environment.pop("INKU_REMOTE_REPO", None)
        environment.update({
            "PATH": f"{self.root.parent / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "SSH_LOG": str(self.ssh_log),
            "SSH_NUMBER": str(ssh_number),
            **({"SSH_FAIL": "1"} if ssh_fail else {}),
            **(env or {}),
        })
        return subprocess.run(
            [sys.executable, str(self.root / SCRIPT), *args],
            cwd=self.root, capture_output=True, text=True, env=environment,
        )

    def ssh_calls(self) -> list[str]:
        return self.ssh_log.read_text(encoding="utf-8").splitlines() if (
            self.ssh_log.exists()) else []

    def snapshot(self) -> dict[str, bytes]:
        return {rel: (self.root / rel).read_bytes() for rel in STAMPED}

    def changed(self, before: dict[str, bytes]) -> list[str]:
        return [rel for rel, blob in before.items()
                if (self.root / rel).read_bytes() != blob]


@pytest.fixture
def tree(tmp_path: pathlib.Path) -> Tree:
    root = tmp_path / "repo"
    for rel in (SCRIPT, *STAMPED):
        src = ROOT / rel
        if not src.exists():
            pytest.skip(f"{rel} is absent (partial tree)")
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    _git(root, "init", "-q")
    (root / "web/BUILD_NUMBER").write_text(f"{SEED}\n", encoding="utf-8")
    # As in the real tree: untracked, so a later `git add -A` in a test does not
    # commit it and a checkout back does not delete it.
    (root / ".gitignore").write_text("no-git-sync/\n", encoding="utf-8")
    _commit(root, "seed")

    # The deployment target lives in the untracked deploy script, so the scan
    # has to find it the same way it does in the real tree.
    deploy = root / "no-git-sync/scripts/deploy.sh"
    deploy.parent.mkdir(parents=True, exist_ok=True)
    deploy.write_text(DEPLOY_SH, encoding="utf-8")

    ssh = tmp_path / "bin/ssh"
    ssh.parent.mkdir(parents=True, exist_ok=True)
    ssh.write_text(FAKE_SSH, encoding="utf-8")
    ssh.chmod(0o755)

    return Tree(root, tmp_path / "ssh.log")


def _next_number(result: subprocess.CompletedProcess) -> int:
    line = [ln for ln in result.stderr.splitlines() if ln.startswith("next build number:")]
    assert line, result.stderr
    return int(line[0].split(":")[1].split("(")[0].strip())


def test_a_number_on_another_branch_moves_the_next_one(tree: Tree):
    head = _git(tree.root, "rev-parse", "--abbrev-ref", "HEAD")
    _git(tree.root, "checkout", "-q", "-b", "rival")
    tree.number(SEED + 5)
    _commit(tree.root, "rival takes one")
    _git(tree.root, "checkout", "-q", head)

    result = tree.run("--scan-build")

    assert result.returncode == 0, result.stderr
    assert _next_number(result) == SEED + 6


def test_a_number_on_a_remote_ref_moves_the_next_one(tree: Tree, tmp_path):
    """A number taken in another clone and pushed is already spoken for."""
    remote = tmp_path / "remote.git"
    _git(tree.root, "init", "-q", "--bare", str(remote))
    head = _git(tree.root, "rev-parse", "--abbrev-ref", "HEAD")
    _git(tree.root, "checkout", "-q", "-b", "pushed")
    tree.number(SEED + 7)
    _commit(tree.root, "another clone takes one")
    _git(tree.root, "remote", "add", "origin", str(remote))
    _git(tree.root, "push", "-q", "origin", "pushed")
    _git(tree.root, "checkout", "-q", head)
    # Only the remote-tracking ref carries it now.
    _git(tree.root, "branch", "-q", "-D", "pushed")

    result = tree.run("--scan-build")

    assert result.returncode == 0, result.stderr
    assert _next_number(result) == SEED + 8


def test_a_number_taken_in_a_worktree_but_not_committed_moves_the_next_one(tree: Tree, tmp_path):
    """The face no ref can show: a stamped, uncommitted working copy."""
    linked = tmp_path / "linked"
    _git(tree.root, "worktree", "add", "-q", "--detach", str(linked), "HEAD")
    tree.number(SEED + 9, at=linked)

    concise = tree.run("--scan-build")
    verbose = tree.run("--scan-build", "--verbose")

    assert concise.returncode == 0, concise.stderr
    assert verbose.returncode == 0, verbose.stderr
    assert _next_number(concise) == _next_number(verbose) == SEED + 10
    assert "\n  " not in concise.stderr
    assert "scanned 4 faces" in concise.stderr
    assert any("linked" in line and "working tree" in line
               for line in verbose.stderr.splitlines())


def test_the_deployment_host_moves_the_next_one(tree: Tree):
    result = tree.run("--scan-build", ssh_number=SEED + 20)

    assert result.returncode == 0, result.stderr
    assert _next_number(result) == SEED + 21


def test_the_host_and_path_come_from_the_deploy_script(tree: Tree):
    result = tree.run("--scan-build")

    assert result.returncode == 0, result.stderr
    calls = tree.ssh_calls()
    assert len(calls) == 1, calls
    assert HOST in calls[0]
    assert f"{REPO}/web/BUILD_NUMBER" in calls[0]


def test_the_environment_overrides_the_deploy_script(tree: Tree):
    result = tree.run("--scan-build", env={
        "INKU_REMOTE_HOST": "someone@elsewhere.invalid",
        "INKU_REMOTE_REPO": "other-repo",
    })

    assert result.returncode == 0, result.stderr
    calls = tree.ssh_calls()
    assert len(calls) == 1, calls
    assert "someone@elsewhere.invalid" in calls[0]
    assert "other-repo/web/BUILD_NUMBER" in calls[0]
    assert HOST not in calls[0]


def test_one_environment_variable_mixes_with_the_script(tree: Tree):
    """Each half of the target is looked up on its own, not as a pair."""
    result = tree.run("--scan-build", env={"INKU_REMOTE_REPO": "other-repo"})

    assert result.returncode == 0, result.stderr
    calls = tree.ssh_calls()
    assert len(calls) == 1, calls
    assert HOST in calls[0]
    assert "other-repo/web/BUILD_NUMBER" in calls[0]


def test_an_unreachable_host_stops_the_scan(tree: Tree):
    """No number at all beats a number that is short one face."""
    before = tree.snapshot()
    result = tree.run("--scan-build", ssh_fail=True)

    assert result.returncode != 0
    assert "next build number" not in result.stderr
    assert "--local" in result.stderr
    assert tree.changed(before) == []


def test_an_unknown_deployment_target_stops_the_scan(tree: Tree):
    """The defaults are read from a file that may not be in this checkout."""
    (tree.root / "no-git-sync/scripts/deploy.sh").unlink()

    result = tree.run("--scan-build")

    assert result.returncode != 0
    assert "next build number" not in result.stderr
    assert "--local" in result.stderr
    assert tree.ssh_calls() == []


def test_local_skips_the_host_and_says_which_face_went_unread(tree: Tree):
    result = tree.run("--scan-build", "--local", ssh_number=SEED + 30)

    assert result.returncode == 0, result.stderr
    assert tree.ssh_calls() == []
    # The host's number is higher, and dropping the face has to be visible in
    # the same line that hands out the number.
    assert _next_number(result) == SEED + 1
    assert "--local" in result.stderr


def test_the_scan_names_every_face_it_read(tree: Tree):
    result = tree.run("--scan-build")

    scanned = [ln for ln in result.stderr.splitlines() if ln.startswith("next build number:")][0]
    assert "refs" in scanned
    assert "worktrees" in scanned
    assert HOST in scanned


def test_scanning_three_faces_still_writes_nothing(tree: Tree):
    """The read-only default of I-195 survives the wider scan."""
    before = tree.snapshot()
    result = tree.run("--scan-build")

    assert result.returncode == 0, result.stderr
    assert tree.changed(before) == []
    assert "--write" in result.stdout


def test_local_alone_is_refused(tree: Tree):
    """A narrowing flag that silently does nothing teaches the wrong lesson."""
    result = tree.run("--local")

    assert result.returncode == 2
    assert "--local" in result.stderr
    assert tree.ssh_calls() == []
