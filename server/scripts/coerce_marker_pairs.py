"""Print, per coerce marker system, how many words each language declares.

This is a report, not a gate. The rule is that a judgement is declared in both
``ja.py`` and ``en.py``, but the two sides are not translations of each other:
Japanese carries 五感 where English carries both `sense` and `presence`, and
nothing says the counts should match. Forcing them to match would mean inventing
words, which changes what coerce reacts to.

What the table is for is the opposite question -- which judgements are lopsided
enough that one language probably lost something. Ledger I-317 (count how often
each system fires) is what will say whether a gap matters.

    uv run python scripts/coerce_marker_pairs.py            # every system
    uv run python scripts/coerce_marker_pairs.py --lopsided # only the uneven ones
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LANGUAGE_SUPPORT = Path(__file__).resolve().parents[1] / "src" / "inku_server" / "language_support"


def _strings(node: ast.AST) -> list[str]:
    return [s.value for s in ast.walk(node)
            if isinstance(s, ast.Constant) and isinstance(s.value, str) and s.value]


def systems() -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for lang in ("ja", "en"):
        tree = ast.parse((LANGUAGE_SUPPORT / f"{lang}.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "COERCE_MARKERS" for t in node.targets):
                continue
            for key, value in zip(node.value.keys, node.value.values):
                out.setdefault(key.value, {})[lang] = _strings(value)
    return out


def main(argv: list[str]) -> int:
    only_lopsided = "--lopsided" in argv
    table = systems()
    print(f"{'system':40} {'ja':>4} {'en':>4}  {'':2}")
    shown = 0
    for name, languages in table.items():
        ja = len(languages.get("ja", []))
        en = len(languages.get("en", []))
        flag = ""
        if not ja or not en:
            flag = "one language only"
        elif max(ja, en) >= 3 * max(1, min(ja, en)):
            flag = "3x or more apart"
        if only_lopsided and not flag:
            continue
        shown += 1
        print(f"{name:40} {ja:>4} {en:>4}  {flag}")
    total_ja = sum(len(v.get("ja", [])) for v in table.values())
    total_en = sum(len(v.get("en", [])) for v in table.values())
    distinct = len({w for v in table.values() for words in v.values() for w in words})
    print(f"\n{len(table)} systems ({shown} shown), {total_ja} ja entries, {total_en} en entries, "
          f"{distinct} distinct words")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
