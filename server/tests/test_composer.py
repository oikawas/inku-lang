"""Stage 2 composer integration tests.

ANTHROPIC_API_KEY 有のときのみ実行 (実 API を叩く)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from inku_server.composer import compose
from inku_server.schema import Score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "stage2"


def _cases() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


requires_api_key = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires ANTHROPIC_API_KEY",
)


@requires_api_key
@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_compose_fixture(case_dir: Path):
    ddl = (case_dir / "input.txt").read_text(encoding="utf-8").strip()
    expected = Score.model_validate_json((case_dir / "expected.json").read_text())

    actual = compose(ddl)

    assert len(actual.instructions) == len(expected.instructions), (
        f"instruction count mismatch for {case_dir.name}: "
        f"expected {len(expected.instructions)}, got {len(actual.instructions)}"
    )
    for i, (a, e) in enumerate(zip(actual.instructions, expected.instructions)):
        assert a.primitive == e.primitive, (
            f"primitive mismatch in {case_dir.name}[{i}]: "
            f"expected {e.primitive}, got {a.primitive}"
        )


def test_submit_tool_schema_is_valid():
    from inku_server.composer import _submit_tool

    tool = _submit_tool()
    assert tool["name"] == "submit_score"
    assert "input_schema" in tool
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert "instructions" in schema["properties"]
