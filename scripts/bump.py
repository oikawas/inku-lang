#!/usr/bin/env python3
"""Stamp the application version and build number everywhere they are recorded.

One bump touches four places, and v2.9.24 shipped with one of them missed (the
project-context target line, in both languages).  This script writes all of them
from one pair of values so a miss is not possible, and
server/tests/test_version_consistency.py fails if they ever disagree again.

    python3 scripts/bump.py --version v2.9.25 --scan-build          # report only
    python3 scripts/bump.py --version v2.9.25 --build 822 --write
    python3 scripts/bump.py --show

Nothing is written without --write.  The default used to be the other way
round, and --scan-build -- which reads like "print the next number" -- stamped
six files on a checkout where the number was only being looked up (ledger
I-195).  A flag that has to be remembered is not a guard, so the writing is now
the flag and the looking is the default.

The build number is a *shared* counter: other branches may already have taken
the next value.  --scan-build reads every local ref and picks max+1, which is
the part that is easy to get wrong by hand.  It cannot see the deployment host,
so check `ssh pentala cat .../web/BUILD_NUMBER` as well before you take one.

This script does not touch APP_VERSION inside +page.svelte, because the UI now
reads web/APP_VERSION through the vite define.  It also does not touch
server/pyproject.toml, which carries the released distribution version and moves
only when a release is tagged.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APP_VERSION_FILE = ROOT / "web" / "APP_VERSION"
BUILD_NUMBER_FILE = ROOT / "web" / "BUILD_NUMBER"

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


def scan_build_numbers() -> tuple[int, dict[str, int]]:
    """Return max+1 across every local ref, with the per-ref values it saw."""
    refs = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
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
        digits = "".join(ch for ch in blob.stdout if ch.isdigit())
        if digits:
            seen[ref] = int(digits)
    if not seen:
        raise SystemExit("no branch carries web/BUILD_NUMBER")
    return max(seen.values()) + 1, seen


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
                        help="choose the build number as max+1 across every local ref")
    parser.add_argument("--show", action="store_true", help="print current values and exit")
    parser.add_argument("--write", action="store_true",
                        help="stamp the files; without it nothing on disk changes")
    args = parser.parse_args()

    version, build = read_current()

    if args.show:
        print(f"APP_VERSION  {version}")
        print(f"BUILD_NUMBER {build}")
        return 0

    if args.scan_build:
        nxt, seen = scan_build_numbers()
        for ref, value in sorted(seen.items(), key=lambda kv: -kv[1]):
            print(f"  {value:>6}  {ref}", file=sys.stderr)
        print(f"next build number: {nxt} "
              f"(local refs only -- also check the deployment host)", file=sys.stderr)
        build = str(nxt)
    elif args.build:
        build = args.build

    if args.version:
        version = args.version

    if not args.version and not args.build and not args.scan_build:
        parser.error("give --version and/or --build (or --scan-build), or --show")

    changes = apply(version, build, write=args.write)
    if not changes:
        print("nothing to change")
        return 0
    for line in changes:
        print(("wrote " if args.write else "would write ") + line)
    if not args.write:
        print(f"nothing was written ({len(changes)} file(s) would change) -- add --write to stamp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
