from __future__ import annotations

import re

from inku_server.ddl_expander import expand_intermediate_ddl


JA_TECHNIQUE_MARKERS = [
    "右半分の斜めの帯",
    "左下から右上へ三本",
    "波打つ軌跡に沿って七個",
    "左下の焦点から三つ",
    "右上の黄金比の位置",
    "左上の三分割の交点",
    "左下の白銀比の位置",
    "対位法の反行",
    "倍音列",
    "輪唱のずれ",
    "一点透視法",
    "前の線を切る",
    "前の線に沿って",
    "前の形に触れない",
    "画面全体へ三本",
    "右下の焦点から外へ",
    "右下の焦点から放射状に",
    "上から下への縦の帯",
    "上から下へ",
    "左から右への横の帯",
    "左から右へ",
    "上端寄りに",
    "上端寄りへ",
    "上端寄りの焦点",
    "右半分の焦点",
    "中央静止の周囲",
    "遠近法の奥行き",
    "素描の下線",
    "点描",
    "油絵の厚塗り",
    "水彩",
    "パッチワーク",
    "フレスコの下地",
    "水墨の濃淡",
]

EN_TECHNIQUE_MARKERS = [
    "diagonal band in the right half",
    "lower left to upper right",
    "undulating trace",
    "lower-left focus",
    "golden-ratio position",
    "rule-of-thirds point",
    "silver-ratio position",
    "contrapuntal contrary motion",
    "harmonic overtone series",
    "canon offset",
    "one-point perspective",
    "cutting the previous line",
    "along the previous line",
    "not touching the previous shape",
    "across the whole canvas",
    "outward from a lower-right focus",
    "radiating from a lower-right focus",
    "from top to bottom in a vertical band",
    "from top to bottom",
    "left to right in horizontal strata",
    "left to right",
    "near the upper edge",
    "toward the upper edge",
    "upper-edge focus",
    "right-half focus",
    "around a central stillness",
    "perspective depth",
    "drawing underlines",
    "pointillism",
    "oil impasto",
    "watercolor",
    "patchwork",
    "fresco ground",
    "ink-wash value",
]


def test_gray_background_survives_stage_15_in_both_wordings():
    """灰背景は Stage 1.5 を素通りする（契約 background-color-openness・段 2）。

    裏返す前の表明は「灰は白へ是正される」だった。`_avoid_gray_background` は
    現行の「埋める」と保存済み作品の「塗りつぶす」の両方を書き換えていたので、
    素通りの表明も両語形で立てる。
    """
    for ddl in ("背景を灰で埋める。黒い線を一本引く。", "背景を灰色で塗りつぶす。黒い線を一本引く。"):
        expanded = expand_intermediate_ddl(ddl)
        assert "背景を灰" in expanded
        assert "背景を白で埋める" not in expanded


def test_expand_intermediate_ddl_is_idempotent_after_expansion():
    ddl = "赤い小さな円を中央付近に五つ散らす。灰色の小さな円を右上の黄金比の位置に一点置く。半径は0.025。"

    assert expand_intermediate_ddl(ddl) == ddl


def test_expand_intermediate_ddl_en_keeps_gray_background():
    """英語側の分岐も `_avoid_gray_background` の中にあったので、同じ表明を英語でも裏返す。"""
    expanded = expand_intermediate_ddl(
        "Fill background with gray. Draw three black horizontal lines.",
        lang="en",
    )

    assert "Fill background with gray" in expanded
    assert "Fill background with white" not in expanded


def test_expand_intermediate_ddl_en_reframes_center():
    expanded = expand_intermediate_ddl(
        "Place a black circle at center. Draw three white lines near the center.",
        lang="en",
    )

    assert "center" not in expanded.lower()
    assert "focus" in expanded.lower()


def test_stage15_added_lines_and_arcs_always_name_a_touch():
    expanded = expand_intermediate_ddl(
        "青い鉛筆の円を中央に置く。黒い鉛筆の横線を三本引く。",
        context_text="静かな水面の反射と細い波",
    )
    touches = ("銀筆", "鉛筆", "ペン", "ロットリング", "クレヨン", "チョーク", "細筆", "太筆", "ビュラン", "ドライポイント")

    for sentence in expanded.split("。"):
        if "線" in sentence or "弧" in sentence:
            assert any(touch in sentence for touch in touches), sentence


def test_stage15_added_lines_and_arcs_always_name_a_touch_en():
    expanded = expand_intermediate_ddl(
        "Place a blue pencil circle at center. Draw three black pencil horizontal lines.",
        lang="en",
        context_text="quiet water reflections and fine waves",
    )
    touches = ("hair", "pencil", "pen", "rotring", "crayon", "chalk", "fine-brush", "thick-brush", "burin", "drypoint")

    for sentence in re.split(r"(?<=[.!?])\s+", expanded):
        lower = sentence.lower()
        if "line" in lower or "arc" in lower:
            assert any(touch in lower for touch in touches), sentence


def test_expand_intermediate_ddl_en_does_not_read_crescent_as_scent():
    expanded = expand_intermediate_ddl(
        "A single white crescent waits in an off-center dark field.",
        lang="en",
    )

    assert "scent layer" not in expanded.lower()
    assert "five-sense presence" not in expanded.lower()


def test_expand_intermediate_ddl_composition_seed_default_is_backward_compatible():
    ddl = "青い線を三本引く。"
    context = "リズムのある水面に反復する音が広がる"

    assert expand_intermediate_ddl(ddl, context_text=context, composition_seed=None) == expand_intermediate_ddl(ddl, context_text=context)


def test_nature_plugin_expands_only_explicit_namespace():
    ddl = "青い線を左から右へ五本並べる。Nature.風を 通す。"
    expanded = expand_intermediate_ddl(ddl)
    plain = expand_intermediate_ddl("青い線を左から右へ五本並べる。風を通す。")

    assert "Nature." not in expanded
    assert "全体の反復配置を左から右への横の帯に沿わせる" in expanded
    assert "ゆっくり揺れる" in expanded
    assert "全体の反復配置" not in plain


def test_nature_uneri_plugin_is_deterministic():
    ddl = "黒い線を三本引く。Nature.うねり。"

    first = expand_intermediate_ddl(ddl)
    second = expand_intermediate_ddl(ddl)

    assert first == second
    assert "波打つ軌跡" in first
    assert "揺らぎは大きくゆっくり" in first


def test_nature_plugin_can_be_disabled():
    ddl = "黒い線を三本引く。Nature.無風。"

    disabled = expand_intermediate_ddl(ddl, enable_plugins=False)

    assert "Nature.無風" in disabled
    assert "全体の揺らぎをなし" not in disabled


def test_nature_plugin_expands_in_english():
    ddl = "Draw five blue lines left to right. Nature.undulation."

    expanded = expand_intermediate_ddl(ddl, lang="en")

    assert "Nature." not in expanded
    assert "Set repeated placement along an undulating trace" in expanded
    assert "Broad slow swaying" in expanded


def test_numeric_regions_are_already_structurally_expanded_in_japanese():
    ddl = (
        "黒い鉛筆の細い弧を一枚、領域 [0.20, 0.30, 0.40, 0.50] に置く。"
        "黒い鉛筆の細い弧を一枚、領域 [0.55, 0.30, 0.75, 0.50] に置く。"
    )

    expanded = expand_intermediate_ddl(ddl, lang="ja", context_text="双弧を描く")

    assert expanded == ddl
    assert "楕円" not in expanded


def test_numeric_regions_are_already_structurally_expanded_in_english():
    ddl = (
        "Place one thin black pencil arc in region [0.20, 0.30, 0.40, 0.50]. "
        "Place one thin black pencil arc in region [0.55, 0.30, 0.75, 0.50]."
    )

    expanded = expand_intermediate_ddl(ddl, lang="en", context_text="draw twin arcs")

    assert expanded == ddl
    assert "ellipse" not in expanded.lower()


# ── Stage 1.5 adds nothing of its own (v2.11.0) ──────────────────────────────
# The candidate pool that used to append structural, musical and painterly
# sentences here was staffage: it wrote lines no description asked for. It was
# governed by the staffage level, and folding that axis away took the pool with
# it. These assert the property that replaced it -- for the very inputs that
# used to draw the most candidates, the expansion is the focus reframing alone.


def test_expand_intermediate_ddl_appends_nothing_for_a_dense_context() -> None:
    ddl = "白い小さな円を画面全体に点々と八十個散らす。"
    expanded = expand_intermediate_ddl(ddl, context_text="満天の星が複雑なリズムで重なる")

    assert not [marker for marker in JA_TECHNIQUE_MARKERS if marker in expanded]
    assert len(re.findall(r"。", expanded)) == len(re.findall(r"。", ddl))


def test_expand_intermediate_ddl_context_cannot_add_a_sentence() -> None:
    """The context used to decide how many candidates were appended.

    Two contexts that used to produce different amounts now produce the same
    expansion, because neither produces any. The DDL is the whole contract.
    """
    ddl = "黒い円を左上の焦点に一点置く。"
    quiet = expand_intermediate_ddl(ddl, context_text="余白の多い静かな一滴の墨")
    dense = expand_intermediate_ddl(ddl, context_text="満天の星が複雑なリズムで重なる")

    assert quiet == dense
    assert not [marker for marker in JA_TECHNIQUE_MARKERS if marker in quiet]


def test_expand_intermediate_ddl_en_appends_nothing_either() -> None:
    ddl = "Place one black square near the center. Draw three white horizontal lines."
    expanded = expand_intermediate_ddl(ddl, lang="en", context_text="a jazz club, swing and syncopation")

    assert not [marker for marker in EN_TECHNIQUE_MARKERS if marker in expanded]
    assert expanded.count(".") == ddl.count(".")
