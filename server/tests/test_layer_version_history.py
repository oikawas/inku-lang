from __future__ import annotations

import ast
import re
from pathlib import Path


LAYER_VERSIONS = Path(__file__).parents[1] / "src" / "inku_server" / "layer_versions.py"


def test_ddl_engine_history_has_no_gap() -> None:
    source = LAYER_VERSIONS.read_text()
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "DDL_ENGINE_VERSION" for target in node.targets)
    )
    current = int(ast.literal_eval(assignment.value))
    history = source[: sum(len(line) for line in source.splitlines(keepends=True)[: assignment.lineno - 1])]
    documented = [int(version) for version in re.findall(r"^# (\d+) \(", history, flags=re.MULTILINE)]

    # SPEC §2.1 records each new version only in the changelog, so the comment
    # history stops where that rule began. What it keeps must stay gapless and
    # must never claim a version beyond the current one.
    assert documented == list(range(documented[0], 4, -1))
    assert documented[0] <= current
