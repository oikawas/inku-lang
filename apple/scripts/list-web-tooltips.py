#!/usr/bin/env python3
"""List every Web tooltip site, the way the macOS tooltip parity table counts them.

A site is each `<Tooltip` (its `text=`) and each `title=` in a `.svelte` file under `web/src`, in file order.
This is the same rule the table's header names (originally 173 sites at Build1162). The macOS check
(`InkuAppCheck --tooltips-leftovers-only`) counts the same sites per component and compares them with the
table, so a tooltip added to the Web fails the check until the table has a row for it.

  python3 apple/scripts/list-web-tooltips.py                 # every site in the working tree
  python3 apple/scripts/list-web-tooltips.py --rev 7a0f01800 # every site at a commit
  python3 apple/scripts/list-web-tooltips.py --compare       # per-component counts: table rows vs Web sites
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "apple/Sources/InkuAppCheck/TooltipParityTable.swift"
SITE = re.compile(r"<Tooltip\b|\btitle=")
KEY = re.compile(r"t\(\)\.([A-Za-z0-9_]+)")


def sources(rev: str | None) -> list[tuple[str, str]]:
    """Return (path under the repository, text) for every .svelte file under web/src."""
    if rev is None:
        paths = sorted((ROOT / "web/src").rglob("*.svelte"))
        return [(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")) for path in paths]
    names = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", rev, "web/src"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    result = []
    for name in sorted(n for n in names if n.endswith(".svelte")):
        text = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{rev}:{name}"], check=True, capture_output=True, text=True,
        ).stdout
        result.append((name, text))
    return result


def attribute(text: str, start: int) -> str:
    """The `text=` / `title=` value that follows a site, as written (a `{...}` expression or a quoted string)."""
    match = re.compile(r"(?:text|title)=").search(text, start)
    if match is None or match.start() - start > 400:
        return ""
    index = match.end()
    if index >= len(text):
        return ""
    opener = text[index]
    if opener in "\"'":
        end = text.find(opener, index + 1)
        return text[index:end + 1]
    if opener != "{":
        return ""
    depth = 0
    for cursor in range(index, min(len(text), index + 600)):
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth == 0:
                return text[index:cursor + 1]
    return text[index:index + 120]


def sites(rev: str | None) -> list[dict[str, object]]:
    found = []
    for path, text in sources(rev):
        component = Path(path).name
        for match in SITE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            value = attribute(text, match.start())
            found.append({
                "component": component,
                "line": line,
                "kind": "Tooltip" if match.group().startswith("<") else "title",
                "keys": KEY.findall(value),
                "value": " ".join(value.split()),
            })
    return found


def table_counts() -> Counter[str]:
    rows = re.findall(r'web: "([^":]+):', TABLE.read_text(encoding="utf-8"))
    return Counter(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", help="read web/src at this commit instead of the working tree")
    parser.add_argument("--compare", action="store_true", help="compare per-component counts with the table")
    args = parser.parse_args()
    found = sites(args.rev)
    if args.compare:
        web = Counter(str(site["component"]) for site in found)
        table = table_counts()
        differing = sorted(name for name in set(web) | set(table) if web[name] != table[name])
        for name in differing:
            print(f"{name}: table {table[name]}, web {web[name]}")
        print(f"total: table {sum(table.values())}, web {sum(web.values())}")
        return 1 if differing else 0
    for site in found:
        keys = ",".join(site["keys"]) or "-"
        print(f"{site['component']}:{site['line']}\t{site['kind']}\t{keys}\t{site['value'][:160]}")
    print(f"{len(found)} sites", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
