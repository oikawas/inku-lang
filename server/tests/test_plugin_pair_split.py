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


def test_pair_member_splits_into_place_and_touching_ja() -> None:
    doc = validate_plugin_document(_doc())
    res = expand_plugin_ddl("Test.対葉を置く。", source_text="Test.対葉を置く。", lang="ja", documents=[doc])
    region_sents = [s for s in _sentences(res.ddl, "ja") if "領域 [" in s]
    assert len(region_sents) == 6  # 3 member × (配置 + touching)
    touching = [s for s in region_sents if "前の弧に両端で触れる" in s]
    placing = [s for s in region_sents if "前の弧に両端で触れる" not in s]
    assert len(touching) == 3 and len(placing) == 3
    # 対の 2 文は同一 region を共有する
    regions = [re.search(r"領域 \[[^\]]+\]", s).group(0) for s in region_sents]
    assert regions[0] == regions[1] and regions[2] == regions[3] and regions[4] == regions[5]


def test_pair_member_splits_en_with_adjective_range() -> None:
    doc = validate_plugin_document(_doc(range_en="3-3 tall blades"))
    res = expand_plugin_ddl("Place Test.対葉.", source_text="Place Test.対葉.", lang="en", documents=[doc])
    region_sents = [s for s in _sentences(res.ddl, "en") if "region [" in s]
    assert len(region_sents) == 6
    assert sum("touching the previous arc" in s for s in region_sents) == 3
    # 分割後の touching 文が "then" を引きずらない
    assert not any(s.lower().startswith("then ") for s in region_sents)


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
    assert "領域 [" in res.ddl  # 展開は生きている


def test_all_stray_falls_back_to_core_approximation() -> None:
    doc = validate_plugin_document(_doc())
    res = expand_plugin_ddl("Foo.謎を通す。", source_text="無関係", lang="ja", documents=[doc])
    assert res.provenance == ()
    assert "Foo." not in res.ddl
    assert any("expansion was dropped" in w for w in res.warnings)
