"""I-143: a repeated composite stays one unit in the Score and performance."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from inku_server import renderer
from inku_server.limits import DEFAULT_LIMITS, Limits, limits_as_dict
from inku_server.coerce import enforce_hard_ceiling
from inku_server.plugins.document_format import (
    expand_plugin_ddl,
    validate_plugin_document,
)
from inku_server.schema import Score


def _pair_plugin(count: int = 3) -> str:
    return f"""---
namespace: Test
name: composite
version: 0.1.0
authors: [test]
languages: [ja, en]
license: MIT
description_ja: 複合反復の検査。
description_en: Composite repetition fixture.
---

## 語: 対葉
surface_ja: 対葉
surface_en: pair leaf
fires_on_ja: 対葉
fires_on_en: pair leaf

### 展開 ja
member 葉形: 弧を置き、前の弧に両端で触れる
葉形を {count}〜{count}枚、{{領域: 中域}} に散らす
### 展開 en
member blade: place an arc, then an arc touching the previous arc at both ends
Scatter {count}-{count} blades in {{region: middle}}
"""


def _composite_score(*, group_size: int | None = 2) -> Score:
    arrangement: dict[str, object] = {"count": 3, "layout": "scatter"}
    if group_size is not None:
        arrangement["group_size"] = group_size
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.08,
                    "angle_start": 220,
                    "angle_end": 320,
                    "weight": "computer",
                    "arrangement": arrangement,
                    "at": {"region": [0.25, 0.25, 0.75, 0.75]},
                },
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.08,
                    "angle_start": 40,
                    "angle_end": 140,
                    "weight": "computer",
                    "relation": {"type": "touching"},
                },
            ]
        }
    )


def test_t1_composite_span_is_structural_and_rejects_invalid_scores() -> None:
    assert _composite_score().instructions[0].arrangement.group_size == 2  # type: ignore[union-attr]
    assert _composite_score(group_size=None).instructions[0].arrangement.group_size == 1  # type: ignore[union-attr]

    invalid = _composite_score().model_dump(by_alias=True)
    invalid["instructions"] = invalid["instructions"][:1]
    with pytest.raises(ValidationError, match="group_size"):
        Score.model_validate(invalid)

    invalid = _composite_score().model_dump(by_alias=True)
    invalid["instructions"][1]["arrangement"] = {"count": 2, "layout": "scatter"}
    with pytest.raises(ValidationError, match="nested arrangement"):
        Score.model_validate(invalid)

    invalid = _composite_score().model_dump(by_alias=True)
    invalid["instructions"][0]["relation"] = {"type": "touching"}
    with pytest.raises(ValidationError, match="head cannot relate"):
        Score.model_validate(invalid)

    invalid = _composite_score().model_dump(by_alias=True)
    invalid["instructions"][1]["mode"] = "carve"
    with pytest.raises(ValidationError, match="share one mode"):
        Score.model_validate(invalid)

    invalid = _composite_score().model_dump(by_alias=True)
    invalid["instructions"][1]["relation"] = {"type": "between"}
    with pytest.raises(ValidationError, match="two prior instructions"):
        Score.model_validate(invalid)


def test_t2_pair_member_is_two_instructions_with_one_composite_arrangement() -> None:
    document = validate_plugin_document(_pair_plugin())
    result = expand_plugin_ddl(
        "Test.対葉を置く。",
        source_text="Test.対葉を置く。",
        lang="ja",
        documents=[document],
    )

    assert len(result.instructions) == 6
    assert len(result.score_instructions) == 2
    arrangement = result.score_instructions[0]["arrangement"]
    assert arrangement["count"] == 3
    assert arrangement["group_size"] == 2
    assert result.score_instructions[1]["relation"] == {"type": "touching"}


def test_t3_composite_expands_before_each_local_touching_relation() -> None:
    score = _composite_score()
    resolved = renderer._resolve_performance_score(
        score,
        performance_seed=17,
        composition_seed=23,
        canvas=renderer.canvas_size_for_aspect("square"),
    )

    assert len(resolved.instructions) == 6
    for index in range(0, 6, 2):
        first = renderer._canvas_endpoint_geometry(
            resolved.instructions[index], 17, index
        )
        second = renderer._canvas_endpoint_geometry(
            resolved.instructions[index + 1], 17, index + 1
        )
        assert first is not None and second is not None
        assert second[0] == pytest.approx(first[0])
        assert second[1] == pytest.approx(first[1])

    svg = renderer.render(
        score,
        render_seed=17,
        composition_seed=23,
        svg_profile="editable",
    )
    assert len(re.findall(r'id="mark_\d{3}_000_arc"', svg)) == 6


def test_t4_whole_work_budget_counts_every_member_of_a_composite() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "arrangement": {"count": 100, "layout": "vertical"},
                },
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.08,
                    "angle_start": 220,
                    "angle_end": 320,
                    "arrangement": {
                        "count": 300,
                        "layout": "scatter",
                        "group_size": 2,
                    },
                },
                {
                    "primitive": "arc",
                    "center": [0.5, 0.5],
                    "radius": 0.08,
                    "angle_start": 40,
                    "angle_end": 140,
                    "relation": {"type": "touching"},
                },
            ]
        }
    )

    limited = enforce_hard_ceiling(score)
    group = limited.instructions[1].arrangement
    assert group is not None
    assert 100 + group.count * group.group_size <= 400

    limits = Limits(
        **{**limits_as_dict(DEFAULT_LIMITS), "max_instructions": 2}
    )
    limited = enforce_hard_ceiling(score, limits)
    assert len(limited.instructions) == 1


def test_t5_explicit_single_member_group_is_byte_identical_to_the_default() -> None:
    default = _composite_score(group_size=None)
    explicit = _composite_score(group_size=1)
    assert renderer.render(default, render_seed=17, composition_seed=23) == renderer.render(
        explicit, render_seed=17, composition_seed=23
    )
