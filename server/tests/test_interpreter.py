"""Stage 1 interpreter tests.

出力は自由文なので完全一致はせず、
- Saijiki かたち語彙を 1 つ以上含む
- 感情語彙が漏れていない
- 長さが妥当な範囲

を検査する。
"""

from __future__ import annotations

import os

import pytest

from inku_server.interpreter import interpret

FORMS = ["円", "楕円", "三角", "四角", "線", "弧"]
EMOTION_WORDS = ["美しい", "美しく", "激しい", "激しく", "素敵", "きれい"]


def _backend_available() -> bool:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY"))


requires_llm = pytest.mark.skipif(
    not _backend_available(),
    reason="no LLM backend configured",
)


@requires_llm
@pytest.mark.parametrize(
    "source",
    [
        "山の向こうに月が昇る",
        "静かな水面に落ちる一滴",
        "激しい嵐の中で",
        "冬の朝、窓ガラスの結晶",
        "夜空に三日月と星",
    ],
)
def test_interpret_produces_saijiki(source: str):
    ddl = interpret(source)

    assert ddl, f"empty output for source: {source}"
    assert 5 < len(ddl) < 500, f"suspicious length {len(ddl)}: {ddl}"

    assert any(w in ddl for w in FORMS), (
        f"no form vocabulary in output\n  source: {source}\n  ddl: {ddl}"
    )

    leaked = [w for w in EMOTION_WORDS if w in ddl]
    assert not leaked, (
        f"emotion words leaked: {leaked}\n  source: {source}\n  ddl: {ddl}"
    )
