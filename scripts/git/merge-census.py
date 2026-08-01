#!/usr/bin/env python3
"""Replay the last N merges on main and report which files actually conflicted.

Ground truth for the merge-conflict rate: for every merge commit, re-run the
merge of its two parents from their merge-base and record git's own verdict.
`git merge-tree` honours .gitattributes and configured merge drivers (verified
2026-08-01), so this measures the same thing an interactive `git merge` would.

Usage: merge-census.py [N]   (default 80)
"""
import collections
import subprocess
import sys


def git(*args: str) -> tuple[str, int]:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout, r.returncode


def main() -> int:
    n = sys.argv[1] if len(sys.argv) > 1 else "80"
    merges = git("log", "--merges", "--format=%H %P", f"-{n}", "main")[0].strip().split("\n")
    conflicts: collections.Counter[str] = collections.Counter()
    replayed = conflicted = 0
    for line in merges:
        parts = line.split()
        if len(parts) != 3:
            continue  # skip octopus merges
        _, p1, p2 = parts
        base = git("merge-base", p1, p2)[0].strip()
        if not base:
            continue
        out, rc = git("merge-tree", "--write-tree", "--name-only", "--merge-base", base, p1, p2)
        replayed += 1
        if rc == 0:
            continue
        conflicted += 1
        # First line is the tree oid; "Auto-merging ..." lines are informational.
        for path in out.split("\n")[1:]:
            path = path.strip()
            if path and not path.startswith(("Auto-merging", "CONFLICT")):
                conflicts[path] += 1
    print(f"replayed={replayed} conflicted={conflicted}")
    for path, count in conflicts.most_common():
        print(f"{count}\t{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
