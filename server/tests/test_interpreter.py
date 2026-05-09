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

from inku_server.interpreter import _build_system_prompt, _sanitize_placement_words, interpret

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
    backend = os.getenv("INKU_LLM_BACKEND", "").lower()
    model = os.getenv("OPENAI_MODEL_STAGE1", "")
    return backend == "openai" and bool(os.getenv("NVIDIA_API_KEY")) and "/" in model


requires_llm = pytest.mark.skipif(
    not _backend_available(),
    reason="NVIDIA NIM test backend is not configured",
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


def test_quantity_prompt_uses_dynamic_range():
    prompt = _build_system_prompt("満天の星空に砂のような点を埋め尽くす")

    assert "数量レンジ" in prompt
    assert "700〜1000" in prompt
    assert "固定値に丸めてはいけない" in prompt
    assert "必ず配置ガイダンスを与える" in prompt
    assert "正規化DDLに「ランダム」という語を出力してはいけない" in prompt
    assert "どこに" in prompt
    assert "どの方向へ" in prompt
    assert "どんな軌跡で" in prompt
    assert "二十個程度" not in prompt
    assert "六百十個" in prompt
    assert "八百九十個" in prompt
    assert "画面全体に点々と六百十個" in prompt
    assert "画面全体に細かく八百九十個" in prompt
    assert "背景色と主描画色を同じにしてはいけない" in prompt
    assert "人・顔・動物を具象化しない" in prompt
    assert "感情語・場所語を物体化しない" in prompt
    assert "物体化しない語も削除しない" in prompt
    assert "縦線+小楕円" in prompt
    assert "ランダムに六百十個" not in prompt
    assert "ランダムに八百九十個" not in prompt


def test_quantity_prompt_en_uses_dynamic_range():
    prompt = _build_system_prompt("a sky full of stars and sand-like dots", lang="en")

    assert "Count Ranges" in prompt
    assert "700–1000" in prompt
    assert "one fixed number" in prompt
    assert "always provide placement guidance" in prompt
    assert 'Do not output the word "random"' in prompt
    assert "where, in which direction, or along what trace" in prompt
    assert "about twenty" not in prompt
    assert "six hundred ten" in prompt
    assert "eight hundred ninety" in prompt
    assert "dotted across the whole canvas" in prompt
    assert "finely across the whole canvas" in prompt
    assert "same foreground and background color" in prompt
    assert "do not objectify emotion or place words" in prompt
    assert "do not delete non-objectified words" in prompt
    assert "six hundred ten small white circles randomly" not in prompt
    assert "eight hundred ninety small gray circles randomly" not in prompt


def test_sanitize_placement_words_removes_random_terms():
    assert _sanitize_placement_words("赤い円をランダムに五つ散らす。") == "赤い円を画面全体に点々と五つ散らす。"
    assert "random" not in _sanitize_placement_words(
        "Scatter five red circles randomly. Radius 0.04."
    ).lower()


def test_contrast_prompt_selects_invisible_examples():
    prompt = _build_system_prompt("白い背景に白い線を引く")
    assert "背景色と主描画色を同じにしてはいけない" in prompt
    assert "面積の少ない方" in prompt
    assert "背景を灰で塗りつぶす" in prompt
    assert "出力してはいけない" in prompt
    assert "白い背景に白い線" in prompt
    assert "黒い横線" in prompt
    assert "青い短い線" in _build_system_prompt("白い雪を白い背景に散らす")


def test_contrast_prompt_en_selects_invisible_examples():
    prompt = _build_system_prompt("white lines on a white background", lang="en")
    assert "same foreground and background color" in prompt
    assert "smaller visual area" in prompt
    assert "Fill background with gray" in prompt
    assert "Do not output" in prompt
    assert "White lines on a white background" in prompt
    assert "black horizontal line" in prompt
    assert "short blue lines" in _build_system_prompt("white snow on a white background", lang="en")


def test_touch_choice_prompt_selects_material_variations():
    prompt = _build_system_prompt("乾いた壁に残った粉の跡")

    assert "てざわり選択" in prompt
    assert "毎回ペンに寄せない" in prompt
    assert "粉、粉っぽい、かすれ" in prompt
    assert "チョーク" in prompt
    assert "クレヨン" in prompt
    assert "ロットリング" in prompt
    assert "チョークの横線" in prompt


def test_touch_choice_prompt_en_selects_material_variations():
    prompt = _build_system_prompt("a dry powder trace left on a wall", lang="en")

    assert "Touch Choice" in prompt
    assert "Do not default everything to pen" in prompt
    assert "powder, dusty" in prompt
    assert "chalk" in prompt
    assert "crayon" in prompt
    assert "rotring" in prompt
    assert "chalk horizontal lines" in prompt
