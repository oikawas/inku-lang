"""Stage 1 interpreter tests.

出力は自由文なので完全一致はしない:
- Saijiki かたち語彙を 1 つ以上含む
- 感情語彙が漏れていない
- 長さが妥当な範囲

`leaked` (prompt 内例と入力同一) と `novel` (prompt 外) を分離し、
memorize と汎化 を切り分けて測る。
"""

from __future__ import annotations

import os

import pytest

from inku_server.interpreter import interpret

FORMS = ["円", "楕円", "三角", "四角", "線", "弧"]
EMOTION_WORDS = [
    "美しい",
    "美しく",
    "激しい",
    "激しく",
    "素敵",
    "きれい",
    "儚い",
]

# prompt 内 few-shot に登場する入力 (memorize 経路で通りやすい)
LEAKED_SOURCES = [
    "山の向こうに月が昇る",
    "激しい嵐の中で",
    "静かな水面に落ちる一滴",
    "冬の朝、窓ガラスの結晶",
]

# prompt 外 (汎化を測る)
NOVEL_SOURCES = [
    "夜空に三日月と星",
    "朝霧の山",
    "雪原の一本の木",
    "桜の花びら舞い散る",
    "滝の音",
    "一本の赤い糸",
    "三本の竹",
    "空に浮かぶ雲",
    "秋の夕暮れ",
    "音のない部屋",
    "時の流れ",
]


def _backend_available() -> bool:
    backend = os.getenv("INKU_LLM_BACKEND", "anthropic").lower()
    if backend == "openai":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY"))


requires_llm = pytest.mark.skipif(
    not _backend_available(),
    reason="no LLM backend configured",
)


def _assert_valid_ddl(source: str, ddl: str) -> None:
    assert ddl, f"empty output for source: {source}"
    assert 5 < len(ddl) < 500, f"suspicious length {len(ddl)}: {ddl}"

    assert any(w in ddl for w in FORMS), (
        f"no form vocabulary in output\n  source: {source}\n  ddl: {ddl}"
    )

    leaked = [w for w in EMOTION_WORDS if w in ddl]
    assert not leaked, (
        f"emotion words leaked: {leaked}\n  source: {source}\n  ddl: {ddl}"
    )


@requires_llm
@pytest.mark.parametrize("source", LEAKED_SOURCES, ids=lambda s: f"leaked:{s}")
def test_interpret_leaked(source: str):
    _assert_valid_ddl(source, interpret(source))


@requires_llm
@pytest.mark.parametrize("source", NOVEL_SOURCES, ids=lambda s: f"novel:{s}")
def test_interpret_novel(source: str):
    _assert_valid_ddl(source, interpret(source))
