"""A-8 regression suite for the v2 plugin-format fixes (籠A).

Each test targets a behavior that failed on the pre-fix expansion layer: member
definitions, saijiki marker classes, the new region keys and diagonal band,
unknown-key rejection, en repetition units, nested anchor repetition, and
fires_on longest-match. Plugin documents are inlined so the suite is hermetic.
"""

from __future__ import annotations

import re

import pytest

from inku_server.plugins.document_format import (
    PluginFormatError,
    expand_plugin_ddl,
    parse_plugin_document,
)

_HEADER = """---
namespace: Test
name: leaves
version: 0.1.0
authors: [tester]
languages: [ja, en]
license: MIT
description_ja: テスト
description_en: test
---
"""


def _doc(body: str):
    return parse_plugin_document(_HEADER + body)


def _entry(
    heading: str,
    ja_lines: str,
    en_lines: str,
    *,
    fires_ja: str = "語",
    fires_en: str = "word",
) -> str:
    return f"""
## 語: {heading}
surface_ja: {heading}
surface_en: {heading}
fires_on_ja: {fires_ja}
fires_on_en: {fires_en}
note_ja: n
note_en: n

### 展開 (ja)
{ja_lines}

### 展開 (en)
{en_lines}
"""


def _regions(ddl: str) -> list[tuple[float, float, float, float]]:
    return [
        tuple(float(v) for v in m.split(", "))
        for m in re.findall(r"(?:領域|region) \[([^\]]+)\]", ddl)
    ]


def _centers(ddl: str) -> list[tuple[float, float]]:
    return [((a + c) / 2, (b + d) / 2) for a, b, c, d in _regions(ddl)]


def _expand(doc, source: str, lang: str):
    return expand_plugin_ddl("", source_text=source, lang=lang, documents=[doc], seed_text=source)


# --------------------------------------------------------------------------- #
# A-1 saijiki marker classes                                                  #
# --------------------------------------------------------------------------- #
def test_a1_material_color_variation_lines_validate() -> None:
    doc = _doc(
        _entry(
            "若葉",
            "弧を 3〜5枚、{領域: 上半分} に散らす。\n鉛筆で、緑で。細かく震える。",
            "Scatter 3-5 arcs in {region: upper half}.\nIn pencil, in green. Fine trembling.",
        )
    )
    assert [e.heading for e in doc.entries] == ["若葉"]


def test_a1_missing_verbs_draw_and_fill_validate() -> None:
    doc = _doc(
        _entry(
            "描画",
            "弧を 3〜5枚、{領域: 中域} に散らす。\n緑で描く。",
            "Scatter 3-5 arcs in {region: middle}.\nFill in green.",
        )
    )
    assert doc.entries[0].heading == "描画"


# --------------------------------------------------------------------------- #
# A-2 member definitions                                                      #
# --------------------------------------------------------------------------- #
def test_a2_member_definition_is_inlined_per_member() -> None:
    doc = _doc(
        _entry(
            "若葉",
            "member 葉形: 弧を置き、前の弧に両端で触れる\n葉形を 3〜5枚、{領域: 上半分} に散らす。",
            "member leaf form: place an arc, then an arc touching the previous arc at both ends\n"
            "Scatter 3-5 leaf forms in {region: upper half}.",
        )
    )
    assert doc.entries[0].members["ja"] == {"葉形": "弧を置き、前の弧に両端で触れる"}
    result = _expand(doc, "語", "ja")
    # v1.94 輪1: 対 member は決定的転写され、member ごとに配置弧 + touching 弧の
    # instruction 対になる（テキストには残らない）。
    assert "葉形を" not in result.ddl
    assert "両端で触れる" not in result.ddl
    assert len(result.instructions) >= 6 and len(result.instructions) % 2 == 0
    touching = [i for i in result.instructions if i.get("relation")]
    assert len(touching) == len(result.instructions) // 2
    assert all(i["relation"]["type"] == "touching" for i in touching)


def test_a2_undefined_member_reference_is_rejected() -> None:
    with pytest.raises(PluginFormatError) as excinfo:
        _doc(
            _entry(
                "若葉",
                "葉形を 3〜5枚、{領域: 上半分} に散らす。",
                "Scatter 3-5 leaf forms in {region: upper half}.",
            )
        )
    assert any("undefined member" in r for r in excinfo.value.reasons)


# --------------------------------------------------------------------------- #
# A-3 region keys and diagonal band                                           #
# --------------------------------------------------------------------------- #
def test_a3_bottom_band_places_members_low() -> None:
    doc = _doc(
        _entry(
            "下草",
            "弧を 3〜4枚、{領域: 下端の帯} に散らす。",
            "Scatter 3-4 arcs in {region: bottom band}.",
        )
    )
    centers = _centers(_expand(doc, "語", "ja").ddl)
    assert centers, "expected member regions"
    # Members sit in the bottom band, not the default center (~0.5).
    assert all(cy > 0.7 for _cx, cy in centers)


def test_a3_diagonal_band_descends_left_to_right() -> None:
    doc = _doc(
        _entry(
            "落葉",
            "弧を 6〜8枚、{領域: 左上から右下への斜めの帯} に散らす。",
            "Scatter 6-8 arcs in {region: diagonal band, upper-left to lower-right}.",
        )
    )
    centers = sorted(_centers(_expand(doc, "語", "ja").ddl))
    assert len(centers) >= 6
    ys = [cy for _cx, cy in centers]
    # Sorted by x, y is non-decreasing: a descending diagonal, not a rectangle.
    assert all(b >= a - 0.02 for a, b in zip(ys, ys[1:]))
    assert ys[-1] - ys[0] > 0.3


# --------------------------------------------------------------------------- #
# A-4 unknown region key is rejected at load, not silently defaulted          #
# --------------------------------------------------------------------------- #
def test_a4_unknown_region_key_rejected() -> None:
    with pytest.raises(PluginFormatError) as excinfo:
        _doc(
            _entry(
                "若葉",
                "弧を 3〜5枚、{領域: 存在しない帯} に散らす。",
                "Scatter 3-5 arcs in {region: nowhere band}.",
            )
        )
    assert any("unknown region key" in r for r in excinfo.value.reasons)


# --------------------------------------------------------------------------- #
# A-5 en repetition units and unit-preserving singular                        #
# --------------------------------------------------------------------------- #
def test_a5_en_units_expand_members() -> None:
    doc = _doc(
        _entry(
            "若葉",
            "弧を 3〜5枚、{領域: 上半分} に散らす。",
            "Scatter 3-5 arcs in {region: upper half}.",
        )
    )
    # Before the fix, en 'arcs' matched no unit and produced zero members.
    en = _expand(doc, "word", "en").ddl
    assert en.count("Place member") >= 3
    assert "one arc" in en  # unit-preserving singular


def test_a5_ja_singular_preserves_unit() -> None:
    doc = _doc(
        _entry(
            "竹",
            "線を 2〜3本、{領域: 中域} に並べる。",
            "Arrange 2-3 lines in {region: middle}.",
        )
    )
    ja = _expand(doc, "語", "ja").ddl
    assert "一本" in ja
    assert "一枚" not in ja


# --------------------------------------------------------------------------- #
# A-6 nested anchor repetition (spots x members)                              #
# --------------------------------------------------------------------------- #
def test_a6_nested_anchor_repetition_makes_multiple_columns() -> None:
    doc = _doc(
        _entry(
            "下草",
            "anchor 根元 を {領域: 下端の帯} に 2〜2箇所 置く。\n"
            "各根元から 弧を 2〜2本、上へ並べる。",
            "anchor roots in {region: bottom band}, at 2-2 spots.\n"
            "From each root, arrange 2-2 arcs upward.",
        )
    )
    centers = _centers(_expand(doc, "語", "ja").ddl)
    # 2 spots x 2 members = 4 member instructions in two distinct x-columns.
    assert len(centers) == 4
    columns = sorted({round(cx, 1) for cx, _cy in centers})
    assert len(columns) == 2


# --------------------------------------------------------------------------- #
# A-7 fires_on longest match                                                  #
# --------------------------------------------------------------------------- #
def _overlap_doc():
    return _doc(
        _entry("下草", "弧を {領域: 中域} に置く。", "Place an arc in {region: middle}.", fires_ja="草", fires_en="grass")
        + _entry("枯草", "弧を {領域: 中域} に置く。", "Place an arc in {region: middle}.", fires_ja="枯草", fires_en="withered grass")
    )


def test_a7_longest_match_suppresses_substring_fire() -> None:
    doc = _overlap_doc()
    fired = [p["plugin_term"] for p in _expand(doc, "枯草", "ja").provenance]
    assert fired == ["Test.枯草"]


def test_a7_different_positions_both_fire() -> None:
    doc = _overlap_doc()
    fired = {p["plugin_term"] for p in _expand(doc, "草、枯草", "ja").provenance}
    assert fired == {"Test.下草", "Test.枯草"}


# --------------------------------------------------------------------------- #
# A-8 ja/en placement equivalence (guards the 枯葉 lower-corner regression)   #
# --------------------------------------------------------------------------- #
def test_a8_ja_en_lower_corner_placement_equivalent() -> None:
    doc = _doc(
        _entry(
            "枯葉",
            "雲形を 2〜4個、{領域: 下の隅} に置く。",
            "Place 2-4 cloudforms in {region: lower corner}.",
        )
    )
    ja = _centers(_expand(doc, "語", "ja").ddl)
    en = _centers(_expand(doc, "word", "en").ddl)
    assert ja and en
    # Neither language falls back to the center band; both sit in the lower corner.
    for cx, cy in ja + en:
        assert cx > 0.55 and cy > 0.55
