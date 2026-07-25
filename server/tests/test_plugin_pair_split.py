"""v1.94 展開層の対分離・en 形容詞つき反復・fires_on stray 緩和の回帰。

対分離: relation literal を含む member 定義は、対の各要素が同一 region を持つ
独立文へ分割される。これにより Stage 2 は member ごとに「配置弧 + touching 弧」
の 2 instruction を書け、Build 590 の明示 region 数上限とも整合する。
"""

import re

import pytest

from inku_server.plugins.document_format import (
    PluginFormatError,
    expand_plugin_ddl,
    validate_plugin_document,
)


def _doc(range_ja: str = "3〜3枚", range_en: str = "3-3 blades", extra: str = "") -> str:
    return f"""---
namespace: Test
name: pairleaf
version: 0.1.0
authors: [test]
languages: [ja, en]
license: MIT
description_ja: 対分離検査用。
description_en: Pair-split test word.
---

## 語: 対葉
surface_ja: 対葉
surface_en: pair leaf
fires_on_ja: 対葉
fires_on_en: pair leaf

### 展開 ja
member 葉形: 弧を置き、前の弧に両端で触れる(膨らみは細く)
葉形を {range_ja}、{{領域: 中域}} に散らす
{extra}
### 展開 en
member blade: place an arc, then an arc touching the previous arc at both ends
Scatter {range_en} in {{region: middle}}
"""


def _sentences(ddl: str, lang: str) -> list[str]:
    if lang == "ja":
        return [s for s in re.split(r"(?<=。)", ddl) if s.strip()]
    return [s for s in re.split(r"(?<=[.!?])\s+", ddl) if s.strip()]


def test_pair_member_transcribes_place_and_touching_ja() -> None:
    doc = validate_plugin_document(_doc())
    res = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    # v1.94 輪1: 対 member はテキストではなく決定的 instruction として転写される
    assert "領域 [" not in res.ddl and "触れる" not in res.ddl
    assert len(res.instructions) == 6  # 3 member × (配置 + touching)
    for k in range(0, 6, 2):
        place, touch = res.instructions[k], res.instructions[k + 1]
        assert place["primitive"] == "arc" and "at" in place and "relation" not in place
        assert touch["relation"] == {"type": "touching"}
        assert place["center"] == touch["center"]  # 対は同一 member region 由来
        # 掃引は劣弧（180°未満）で、対ごとに揺れる
        assert (place["angle_end"] - place["angle_start"]) < 180
    spans = {i["angle_end"] - i["angle_start"] for i in res.instructions}
    assert len(spans) > 1  # 固定スタンプ化していない


def test_pair_member_deterministic() -> None:
    doc = validate_plugin_document(_doc())
    a = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    b = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    assert a.instructions == b.instructions


def test_pair_member_transcribes_en_with_adjective_range() -> None:
    doc = validate_plugin_document(_doc(range_en="3-3 tall blades"))
    res = expand_plugin_ddl("Place Test.対葉.", source_text="Place Test.対葉.", lang="en", documents=[doc])
    assert len(res.instructions) == 6
    assert sum(1 for i in res.instructions if i.get("relation")) == 3


def test_style_line_applies_weight_and_color_to_pair() -> None:
    doc = validate_plugin_document(_doc(extra="ロットリングで、赤で。"))
    res = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    assert "ロットリング" not in res.ddl  # 様式行は消費される
    assert all(i.get("weight") == "rotring" and i.get("color") == "red" for i in res.instructions)


def test_mixed_style_line_applies_head_and_keeps_motion_text() -> None:
    # 「鉛筆で、緑で。細かく震える。」— 行頭の様式文だけ消費し、運動句は残す
    doc = validate_plugin_document(_doc(extra="鉛筆で、緑で。細かく震える。"))
    res = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    assert all(i.get("weight") == "pencil" and i.get("color") == "green" for i in res.instructions)
    assert "鉛筆" not in res.ddl and "緑" not in res.ddl
    assert "細かく震える" in res.ddl


def test_non_style_line_after_pair_stays_in_text() -> None:
    doc = validate_plugin_document(_doc(extra="中心から線を下へ引く。"))
    res = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    assert "線を下へ引く" in res.ddl
    assert all("weight" not in i for i in res.instructions)


def test_adjective_range_singular_keeps_adjective() -> None:
    # member を参照しない通常反復行でも形容詞つき範囲が展開され、単数形に形容詞が残る
    text = _doc().replace("Scatter 3-3 blades in {region: middle}", "Scatter 1-1 tall arcs in {region: middle}")
    text = text.replace("member blade: place an arc, then an arc touching the previous arc at both ends\n", "")
    doc = validate_plugin_document(text)
    res = expand_plugin_ddl("Place Test.対葉.", source_text="Place Test.対葉.", lang="en", documents=[doc])
    assert "one tall arc" in res.ddl


def test_pair_budget_counts_both_arcs() -> None:
    # 25 member × 2 = 50 > 48 はロード拒否、24 × 2 = 48 は通過
    with pytest.raises(PluginFormatError) as exc:
        validate_plugin_document(_doc(range_ja="25〜25枚", range_en="25-25 blades"))
    assert "budget" in str(exc.value)
    validate_plugin_document(_doc(range_ja="24〜24枚", range_en="24-24 blades"))


def test_stray_reference_removes_sentence_not_expansion() -> None:
    doc = validate_plugin_document(_doc())
    ddl = "赤い円を置く。Foo.謎を通す。対葉を散らす。"
    res = expand_plugin_ddl(ddl, source_text="対葉を散らす", lang="ja", documents=[doc])
    assert [p["plugin_term"] for p in res.provenance] == ["Test.対葉"]
    assert "Foo." not in res.ddl
    assert "赤い円を置く。" in res.ddl  # 無関係な文は保持
    assert any("stray non-core reference removed" in w for w in res.warnings)
    assert len(res.instructions) == 6  # 展開（決定的転写）は生きている


def test_all_stray_falls_back_to_core_approximation() -> None:
    doc = validate_plugin_document(_doc())
    res = expand_plugin_ddl("Foo.謎を通す。", source_text="無関係", lang="ja", documents=[doc])
    assert res.provenance == ()
    assert "Foo." not in res.ddl
    assert any("expansion was dropped" in w for w in res.warnings)
