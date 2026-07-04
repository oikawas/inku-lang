from __future__ import annotations

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


def test_expand_intermediate_ddl_selects_focused_layers():
    ddl = "背景を灰で塗りつぶす。赤い小さな円をランダムに十二個散らす。青い小さな円をランダムに八個散らす。白い細筆の細い線を水平に三本引く。"

    expanded = expand_intermediate_ddl(ddl)
    selected = [marker for marker in JA_TECHNIQUE_MARKERS if marker in expanded]

    assert "ランダム" not in expanded
    assert "背景を灰" not in expanded
    assert "背景を白で塗りつぶす" in expanded
    assert "画面全体に点々と十二個" in expanded
    assert "正五角形" not in expanded
    assert "中心から" not in expanded
    assert "中央へ" not in expanded
    assert len(selected) <= 3
    assert len(selected) < len(JA_TECHNIQUE_MARKERS)
    assert expanded.count("。") <= ddl.count("。") + 8
    assert expanded.count("小さな円") <= ddl.count("小さな円")
    assert any(word in expanded for word in ("小さな楕円", "短い線", "小さな四角", "細い弧"))
    assert any(word in expanded for word in ("右上がり", "右下がり", "回転した", "焦点"))


def test_expand_intermediate_ddl_is_idempotent_after_expansion():
    ddl = "赤い小さな円を中央付近に五つ散らす。灰色の小さな円を右上の黄金比の位置に一点置く。半径は0.025。"

    assert expand_intermediate_ddl(ddl) == ddl


def test_expand_intermediate_ddl_varies_by_input():
    first = expand_intermediate_ddl("中心に黒い四角を置く。白い横線を三本引く。")
    second = expand_intermediate_ddl("満天の星空に白い小さな円を画面全体に点々と六百十個散らす。")

    assert first != second
    assert "中心" not in first
    assert "中央" not in first
    assert "焦点に黒い四角を置く" in first
    assert any(marker in first for marker in ("遠近法の奥行き", "一点透視法", "パッチワーク", "水彩", "素描の下線", "点描"))
    assert any(marker in second for marker in ("左下の焦点から三つ", "波打つ軌跡に沿って七個", "左下から右上へ三本", "画面全体へ三本", "前の線に沿って"))


def test_expand_intermediate_ddl_uses_context_to_control_filter_amount():
    quiet = expand_intermediate_ddl(
        "黒い円を左上の焦点に一点置く。",
        context_text="余白の多い静かな一滴の墨",
    )
    dense = expand_intermediate_ddl(
        "白い小さな円を画面全体に点々と八十個散らす。",
        context_text="満天の星が複雑なリズムで重なる",
    )

    quiet_selected = [marker for marker in JA_TECHNIQUE_MARKERS if marker in quiet]
    dense_selected = [marker for marker in JA_TECHNIQUE_MARKERS if marker in dense]

    assert len(quiet_selected) == 0
    assert len(dense_selected) >= 2
    assert len(quiet_selected) < len(dense_selected)


def test_expand_intermediate_ddl_carries_atmospheric_context():
    expanded = expand_intermediate_ddl(
        "白い短い線を上から下へ九本散らす。",
        context_text="透明な膜と雨の反射が残るバス停",
    )

    assert "透明な膜" in expanded
    assert "薄い反射" in expanded


def test_expand_intermediate_ddl_carries_sensory_context_without_overloading():
    expanded = expand_intermediate_ddl(
        "緑の三角を三つ置く。赤い楕円を三つ置く。",
        context_text="柔らかな陽光と沈丁花の香り、桜の蕾が開花を待つ春の五感",
    )

    markers = ("柔らかな光", "香りの層", "開花を待つ蕾", "五感の気配")
    selected = [marker for marker in markers if marker in expanded]

    assert len(selected) >= 2
    assert expanded.count("。") <= 8


def test_expand_intermediate_ddl_does_not_add_true_circles_for_particles():
    expanded = expand_intermediate_ddl(
        "背景を黒で塗りつぶす。白い小さな四角を画面全体に点々と六百十個散らす。",
        context_text="満天の星空",
    )

    assert "小さな円" not in expanded
    assert any(word in expanded for word in ("小さな楕円", "短い線", "小さな四角"))
    assert any(word in expanded for word in ("右上がり", "右下がり", "回転した"))


def test_expand_intermediate_ddl_abstracts_presence_without_body_symbols():
    expanded = expand_intermediate_ddl(
        "青い横線を下端に三十本並べる。",
        context_text="川岸で人と熊が並んで待っている",
    )

    assert any(marker in expanded for marker in ("存在の重心", "輪郭の密度"))
    assert "縦線" not in expanded
    assert "小さな楕円" not in expanded


def test_expand_intermediate_ddl_does_not_invent_gaze_for_city_context():
    expanded = expand_intermediate_ddl(
        "夜のガラス越しに、街のネオンが涙のように滲んでいる。",
    )

    assert "視線の切片" not in expanded
    assert "余白の切片" in expanded


def test_expand_intermediate_ddl_en_selects_focused_layers():
    ddl = "Scatter five small red circles randomly. Draw three thin white horizontal lines."

    expanded = expand_intermediate_ddl(ddl, lang="en")
    selected = [marker for marker in EN_TECHNIQUE_MARKERS if marker in expanded]

    assert "random" not in expanded.lower()
    assert "dotted across the whole canvas" in expanded
    assert "regular pentagon" not in expanded
    assert "from center" not in expanded
    assert "toward the center" not in expanded
    assert len(selected) <= 2
    assert len(selected) < len(EN_TECHNIQUE_MARKERS)
    assert "rising to the right" in expanded


def test_expand_intermediate_ddl_en_avoids_gray_background():
    expanded = expand_intermediate_ddl(
        "Fill background with gray. Draw three black horizontal lines.",
        lang="en",
    )

    assert "background with gray" not in expanded.lower()
    assert "Fill background with white." in expanded


def test_expand_intermediate_ddl_en_reframes_center():
    expanded = expand_intermediate_ddl(
        "Place a black circle at center. Draw three white lines near the center.",
        lang="en",
    )

    assert "center" not in expanded.lower()
    assert "focus" in expanded.lower()


def test_expand_intermediate_ddl_en_does_not_read_crescent_as_scent():
    expanded = expand_intermediate_ddl(
        "A single white crescent waits in an off-center dark field.",
        lang="en",
    )

    assert "scent layer" not in expanded.lower()
    assert "five-sense presence" not in expanded.lower()


def test_expand_intermediate_ddl_emits_relation_phrases_for_stage2_copy():
    expanded = expand_intermediate_ddl(
        "白い小さな円を画面全体に点々と八十個散らす。",
        context_text="満天の星が複雑なリズムで重なる",
    )

    assert any(phrase in expanded for phrase in ("前の線に沿って", "前の線を切る", "前の形に触れない"))


def test_line_music_profile_does_not_default_to_diagonal_band():
    outputs = [
        expand_intermediate_ddl("青い線を三本引く。", context_text="リズムのある水面"),
        expand_intermediate_ddl("黒い線を左から右へ五本並べる。", context_text="反復する音"),
    ]

    joined = "\n".join(outputs)
    assert "右半分の斜めの帯" not in joined
    assert any(phrase in joined for phrase in ("上から下への縦の帯", "左から右への横の帯", "画面全体へ", "上端寄り", "倍音列", "右下の焦点"))


def test_expand_intermediate_ddl_composition_family_rewrites_diagonal_bias():
    outputs = [
        expand_intermediate_ddl("赤い小さな円を画面全体に点々と二十個散らす。", context_text="満天の星"),
        expand_intermediate_ddl("青い線を三本引く。", context_text="リズムのある水面"),
        expand_intermediate_ddl("白い四角を三つ置く。", context_text="静かな部屋と余白"),
    ]

    joined = "\n".join(outputs)
    assert any(phrase in joined for phrase in ("上から下への縦の帯", "左から右への横の帯", "画面全体へ", "上端寄り"))



def test_expand_intermediate_ddl_vary_seed_default_is_backward_compatible():
    ddl = "青い線を三本引く。"
    context = "リズムのある水面に反復する音が広がる"

    assert expand_intermediate_ddl(ddl, context_text=context, vary_seed=None) == expand_intermediate_ddl(ddl, context_text=context)


def test_expand_intermediate_ddl_vary_seed_is_deterministic_and_diverse():
    ddl = "青い線を三本引く。"
    context = "リズムのある水面に反復する音が広がる"

    first = expand_intermediate_ddl(ddl, context_text=context, vary_seed=3)
    second = expand_intermediate_ddl(ddl, context_text=context, vary_seed=3)
    variants = {expand_intermediate_ddl(ddl, context_text=context, vary_seed=seed) for seed in range(10)}

    assert first == second
    assert len(variants) >= 3
