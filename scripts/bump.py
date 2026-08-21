#!/usr/bin/env python3
"""Stamp the application version and build number everywhere they are recorded.

One bump touches four places, and v2.9.24 shipped with one of them missed (the
project-context target line, in both languages).  This script writes all of them
from one pair of values so a miss is not possible, and
server/tests/test_version_consistency.py fails if they ever disagree again.

    python3 scripts/bump.py --version v2.9.25 --scan-build          # report only
    python3 scripts/bump.py --scan-build --local                    # no ssh
    python3 scripts/bump.py --version v2.9.25 --build 822 --write
    python3 scripts/bump.py --build 822 --check                     # exit 2 on drift
    python3 scripts/bump.py --show

Nothing is written without --write.  The default used to be the other way
round, and --scan-build -- which reads like "print the next number" -- stamped
six files on a checkout where the number was only being looked up (ledger
I-195).  A flag that has to be remembered is not a guard, so the writing is now
the flag and the looking is the default.

The build number is a *shared* counter: other branches may already have taken
the next value.  --scan-build picks max+1 across all three faces the number
lives on -- every ref, every worktree's working copy (where a number taken but
not yet committed only shows up), and the deployment host -- because a scan that
covers two of them reads exactly like a scan that covers all three (ledger
I-196).  --local drops the host face, which is the only one that needs ssh; the
scan stops rather than reporting a number it knows is short a face.

This script does not touch APP_VERSION inside +page.svelte, because the UI now
reads web/APP_VERSION through the vite define.  It also does not touch
server/pyproject.toml, which carries the released distribution version and moves
only when a release is tagged.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APP_VERSION_FILE = ROOT / "web" / "APP_VERSION"
BUILD_NUMBER_FILE = ROOT / "web" / "BUILD_NUMBER"

# Where the deployment target is written down.  The deploy script is untracked
# and lives in the main working tree only, so the lookup walks the worktrees
# rather than assuming this checkout is the one that has it.
DEPLOY_SCRIPT = Path("no-git-sync") / "scripts" / "deploy.sh"
DEPLOY_DEFAULTS = (
    ("INKU_REMOTE_HOST", r'^REMOTE_HOST="\$\{INKU_REMOTE_HOST:-([^}"]+)\}"'),
    ("INKU_REMOTE_REPO", r'^REMOTE_REPO="\$\{INKU_REMOTE_REPO:-([^}"]+)\}"'),
)

# (path, pattern, replacement template).  Each pattern must match exactly once;
# a pattern that stops matching is a failure, not something to skip silently.
DOC_RULES: list[tuple[Path, str, str]] = [
    (
        ROOT / "PROJECT_CONTEXT.ja.md",
        r"\*\*対象バージョン: [^\n]*\*\*",
        "**対象バージョン: {version} / Build {build}**",
    ),
    (
        ROOT / "PROJECT_CONTEXT.md",
        r"\*\*Target version: [^\n]*\*\*",
        "**Target version: {version} / Build {build}**",
    ),
    (
        ROOT / "docs" / "spec" / "render-engine-history.ja.md",
        r"(\| `APP_VERSION` \| アプリの版 \| )[^|]*(\|)",
        r"\g<1>{version} \g<2>",
    ),
    (
        ROOT / "docs" / "spec" / "render-engine-history.ja.md",
        r"(\| `web/BUILD_NUMBER` \| ビルド通し番号 \| )[^|]*(\|)",
        r"\g<1>{build} \g<2>",
    ),
    (
        ROOT / "docs" / "spec" / "render-engine-history.md",
        r"(\| `APP_VERSION` \| the application version \| )[^|]*(\|)",
        r"\g<1>{version} \g<2>",
    ),
    (
        ROOT / "docs" / "spec" / "render-engine-history.md",
        r"(\| `web/BUILD_NUMBER` \| build serial \| )[^|]*(\|)",
        r"\g<1>{build} \g<2>",
    ),
]


def read_current() -> tuple[str, str]:
    return (
        APP_VERSION_FILE.read_text(encoding="utf-8").strip(),
        BUILD_NUMBER_FILE.read_text(encoding="utf-8").strip(),
    )


def _number(text: str) -> int | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def worktree_paths() -> list[Path]:
    """Every working tree of this repository, main one first."""
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [Path(line[len("worktree "):]) for line in listing.splitlines()
            if line.startswith("worktree ")]


def scan_refs() -> dict[str, int]:
    """web/BUILD_NUMBER as every ref carries it -- local branches and remotes."""
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/", "refs/remotes/"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    seen: dict[str, int] = {}
    for ref in refs:
        blob = subprocess.run(
            ["git", "show", f"{ref}:web/BUILD_NUMBER"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if blob.returncode != 0:
            continue
        value = _number(blob.stdout)
        if value is not None:
            seen[ref] = value
    return seen


def scan_worktrees(paths: list[Path]) -> dict[str, int]:
    """The number on disk in each working tree.

    A number taken in a worktree but not yet committed exists nowhere else, so
    dropping this face makes the scan hand out a value someone already holds.
    """
    seen: dict[str, int] = {}
    for path in paths:
        number_file = path / "web" / "BUILD_NUMBER"
        if not number_file.is_file():
            continue
        value = _number(number_file.read_text(encoding="utf-8"))
        if value is not None:
            seen[f"{path} (working tree)"] = value
    return seen


def deploy_target(paths: list[Path]) -> tuple[str, str]:
    """(host, repo) for the deployment host, from the environment or deploy.sh.

    The defaults live in the untracked deploy script so that this file -- which
    is public -- does not carry the deployment target.  A deploy script whose
    shape changed fails here rather than falling back to a guess.
    """
    from_env = {name: os.environ.get(name) for name, _ in DEPLOY_DEFAULTS}
    if all(from_env.values()):
        return from_env["INKU_REMOTE_HOST"], from_env["INKU_REMOTE_REPO"]

    for path in paths:
        script = path / DEPLOY_SCRIPT
        if not script.is_file():
            continue
        text = script.read_text(encoding="utf-8")
        found: list[str] = []
        for name, pattern in DEPLOY_DEFAULTS:
            match = re.search(pattern, text, re.MULTILINE)
            if match is None:
                raise LookupError(
                    f"{script}: no default for {name}; the script's shape changed, "
                    f"so set {name} in the environment or fix scripts/bump.py"
                )
            found.append(os.environ.get(name) or match.group(1))
        return found[0], found[1]

    raise LookupError(
        f"the deployment target is unknown: no worktree has {DEPLOY_SCRIPT} and "
        f"INKU_REMOTE_HOST / INKU_REMOTE_REPO are not both set"
    )


def scan_host(host: str, repo: str) -> dict[str, int]:
    """The number the deployment host is serving.

    A failure raises: the host is shared, and a scan that quietly skipped it
    would report the same shape of answer as one that reached it.
    """
    probe = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host,
         f"cat {repo}/web/BUILD_NUMBER"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise LookupError(
            f"{host}: {(probe.stderr.strip() or 'ssh failed').splitlines()[-1]}"
        )
    value = _number(probe.stdout)
    if value is None:
        raise LookupError(f"{host}: {repo}/web/BUILD_NUMBER holds no number")
    return {f"{host}:{repo}/web/BUILD_NUMBER": value}


def scan_build_numbers(*, local: bool) -> tuple[int, dict[str, int], list[str]]:
    """Return max+1 across the faces the counter lives on, and which were read.

    `local` drops the deployment host -- the one face that needs ssh -- and the
    caller has to say so in what it prints.
    """
    paths = worktree_paths()
    refs = scan_refs()
    trees = scan_worktrees(paths)
    seen = {**refs, **trees}
    scanned = [f"{len(refs)} refs", f"{len(trees)} worktrees"]

    if local:
        scanned.append("no deployment host (--local)")
    else:
        try:
            host, repo = deploy_target(paths)
            seen.update(scan_host(host, repo))
        except LookupError as exc:
            raise SystemExit(
                f"the deployment host was not scanned: {exc}\n"
                f"it carries the same counter, so no number is reported; "
                f"pass --local to take one from the refs and worktrees alone"
            ) from exc
        scanned.append(host)

    if not seen:
        raise SystemExit("nothing carries web/BUILD_NUMBER")
    return max(seen.values()) + 1, seen, scanned


def apply(version: str, build: str, *, write: bool) -> list[str]:
    """Report every file that would change, and change them only if `write`.

    The keyword has no default on purpose: a caller that forgets it gets a
    TypeError rather than a silent stamping.
    """
    changes: list[str] = []

    for path, value in ((APP_VERSION_FILE, version), (BUILD_NUMBER_FILE, build)):
        before = path.read_text(encoding="utf-8").strip()
        if before != value:
            changes.append(f"{path.relative_to(ROOT)}: {before} -> {value}")
            if write:
                path.write_text(value + "\n", encoding="utf-8")

    for path, pattern, template in DOC_RULES:
        text = path.read_text(encoding="utf-8")
        replacement = template.format(version=version, build=build)
        new_text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise SystemExit(
                f"{path.relative_to(ROOT)}: pattern did not match exactly once "
                f"({count}); the document shape changed, fix scripts/bump.py"
            )
        if new_text != text:
            changes.append(f"{path.relative_to(ROOT)}: {pattern[:40]}...")
            if write:
                path.write_text(new_text, encoding="utf-8")

    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="application version, e.g. v2.9.25")
    parser.add_argument("--build", help="build number, e.g. 822")
    parser.add_argument("--scan-build", action="store_true",
                        help="choose the build number as max+1 across every ref, every "
                             "worktree's working copy and the deployment host")
    parser.add_argument("--local", action="store_true",
                        help="do not ssh to the deployment host; the number then comes "
                             "from the refs and worktrees only")
    parser.add_argument("--verbose", action="store_true",
                        help="print every build-number source scanned by --scan-build")
    parser.add_argument("--show", action="store_true", help="print current values and exit")
    parser.add_argument("--write", action="store_true",
                        help="stamp the files; without it nothing on disk changes")
    parser.add_argument("--check", action="store_true",
                        help="write nothing and exit 2 if any stamped file is out of date")
    args = parser.parse_args()

    # A flag that quietly does nothing is how the caller comes to believe the
    # host was scanned when nothing scanned anything (ledger I-196).
    if args.local and not args.scan_build:
        parser.error("--local narrows --scan-build; it means nothing on its own")
    if args.check and args.write:
        parser.error("--check and --write are mutually exclusive")

    version, build = read_current()

    if args.show:
        print(f"APP_VERSION  {version}")
        print(f"BUILD_NUMBER {build}")
        return 0

    if args.scan_build:
        nxt, seen, scanned = scan_build_numbers(local=args.local)
        current = nxt - 1
        owners = sorted(source for source, value in seen.items() if value == current)
        owner_summary = ", ".join(owners[:2])
        if len(owners) > 2:
            owner_summary += f", +{len(owners) - 2} more"
        if args.verbose:
            for source, value in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {value:>6}  {source}", file=sys.stderr)
        print(
            f"next build number: {nxt} (current max: {current}; "
            f"owner{'s' if len(owners) != 1 else ''}: {owner_summary}; "
            f"scanned {len(seen)} faces: {', '.join(scanned)})",
            file=sys.stderr,
        )
        build = str(nxt)
    elif args.build:
        build = args.build

    if args.version:
        version = args.version

    if not args.version and not args.build and not args.scan_build:
        parser.error("give --version and/or --build (or --scan-build), or --show")

    changes = apply(version, build, write=args.write)
    if not changes:
        print("version markers are current" if args.check else "nothing to change")
        return 0
    for line in changes:
        print(("wrote " if args.write else "would write ") + line)
    if args.check:
        print(
            f"version markers are out of date ({len(changes)} file(s)); "
            "stamp them before running expensive checks",
            file=sys.stderr,
        )
        return 2
    if not args.write:
        print(f"nothing was written ({len(changes)} file(s) would change) -- add --write to stamp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
