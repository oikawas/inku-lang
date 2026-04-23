"""Stage 2 composer integration tests.

LLM backend は `INKU_LLM_BACKEND` で切替 (anthropic | openai)。

厳密比較軸:
- primitive / color / weight / style / variation: 完全一致
- 座標・サイズ・半径: ±0.05 tolerance (0-1 比率上 5%)
- variation.dimensions: 集合一致 (順序不問)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from inku_server.composer import compose
from inku_server.schema import Instruction, Score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "stage2"

NUMERIC_TOL = 0.05


def _cases() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


def _backend_available() -> bool:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY"))


requires_api_key = pytest.mark.skipif(
    not _backend_available(),
    reason="no LLM backend configured (set ANTHROPIC_API_KEY or INKU_LLM_BACKEND=openai)",
)


def _approx_equal(a, b, tol: float = NUMERIC_TOL) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(
            _approx_equal(x, y, tol) for x, y in zip(a, b)
        )
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


def _diff_instruction(a: Instruction, e: Instruction) -> list[str]:
    errs: list[str] = []
    for field in ("primitive", "color", "weight", "style"):
        av, ev = getattr(a, field), getattr(e, field)
        if av != ev:
            errs.append(f"{field}: {av!r} vs {ev!r}")

    for field in ("center", "radius", "from_", "to", "position", "size"):
        av, ev = getattr(a, field), getattr(e, field)
        if av is None and ev is None:
            continue
        if not _approx_equal(av, ev):
            label = "from" if field == "from_" else field
            errs.append(f"{label}: {av} vs {ev}")

    va, ev_var = a.variation, e.variation
    if (va is None) != (ev_var is None):
        errs.append(f"variation: {va} vs {ev_var}")
    elif va is not None and ev_var is not None:
        if va.amplitude != ev_var.amplitude:
            errs.append(f"variation.amplitude: {va.amplitude} vs {ev_var.amplitude}")
        if va.quality != ev_var.quality:
            errs.append(f"variation.quality: {va.quality} vs {ev_var.quality}")
        if set(va.dimensions) != set(ev_var.dimensions):
            errs.append(
                f"variation.dimensions: {va.dimensions} vs {ev_var.dimensions}"
            )

    return errs


@requires_api_key
@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_compose_fixture(case_dir: Path):
    ddl = (case_dir / "input.txt").read_text(encoding="utf-8").strip()
    expected = Score.model_validate_json((case_dir / "expected.json").read_text())

    actual = compose(ddl)

    if len(actual.instructions) != len(expected.instructions):
        raise AssertionError(
            f"{case_dir.name}: instruction count "
            f"{len(actual.instructions)} vs {len(expected.instructions)}"
        )

    all_errors: list[str] = []
    for i, (a, e) in enumerate(zip(actual.instructions, expected.instructions)):
        errs = _diff_instruction(a, e)
        if errs:
            all_errors.append(f"  [{i}] " + "; ".join(errs))

    if all_errors:
        raise AssertionError(
            f"\n{case_dir.name} ({len(all_errors)} instruction(s) with diffs):\n"
            + "\n".join(all_errors)
        )


def test_submit_tool_schema_is_valid():
    from inku_server.composer import _submit_tool

    tool = _submit_tool()
    assert tool["name"] == "submit_score"
    assert "input_schema" in tool
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert "instructions" in schema["properties"]
