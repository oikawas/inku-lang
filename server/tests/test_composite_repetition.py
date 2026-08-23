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
from inku_server.plugins.system import canvas_aspect
from inku_server.render_engines.default import planning


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
    resolved = planning._resolve_performance_score(
        score,
        performance_seed=17,
        composition_seed=23,
        canvas=canvas_aspect.canvas_size_for_aspect("square"),
    )

    assert len(resolved.instructions) == 6
    for index in range(0, 6, 2):
        first = planning._canvas_endpoint_geometry(
            resolved.instructions[index], 17, index
        )
        second = planning._canvas_endpoint_geometry(
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


def test_t8_the_api_merges_the_compact_score_form_not_the_public_expansion() -> None:
    """The one line where the compact form enters the Score.

    Nothing else observed it. Reverting the route to the public expansion left
    the whole server suite green (3,170 passed) while production lost the
    composite entirely, so the claim is asserted where it is made.
    """
    # Importing the app is what creates the schema for the test database.
    from inku_server.api import app as _app  # noqa: F401
    from inku_server.api_core.routers import render as render_routes

    document = validate_plugin_document(_pair_plugin())

    def fake_expand(ddl, **kwargs):
        return expand_plugin_ddl(
            ddl,
            source_text=kwargs.get("source_text", ddl),
            lang=kwargs.get("lang", "ja"),
            documents=[document],
        )

    def fake_compose(ddl, **kwargs):
        return Score.model_validate({"instructions": []}), 1, 2

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", fake_expand)
        patch.setattr(
            render_routes, "expand_intermediate_for_lang", lambda ddl, **kwargs: ddl
        )
        patch.setattr(render_routes, "compose", fake_compose)
        patch.setattr(render_routes, "coerce_score", lambda score, **kwargs: score)
        response = render_routes.api_compose(
            render_routes.ComposeRequest(
                ddl="Test.対葉を置く。",
                description="Test.対葉を置く。",
                instruction_lang="ja",
            ),
            {"id": "test-user"},
        )

    # Stage 2 handed back nothing, so the route writes its one fallback mark and
    # the plugin's own instructions follow it.
    instructions = response.score.instructions
    merged = instructions[1:]
    assert len(merged) == 2, (
        "the route merged the public expansion (6 instructions); the compact "
        "Score form is what carries the composite"
    )
    arrangement = merged[0].arrangement
    assert arrangement is not None
    assert arrangement.count == 3
    assert arrangement.group_size == 2
    assert merged[1].relation is not None


def test_t9_a_span_the_ceiling_cannot_hold_leaves_marks_not_a_blank_work() -> None:
    """A span longer than the whole instruction ceiling used to empty the work.

    The ceiling still refuses to cut a span in half. When no span fits at all it
    dissolves the claim instead of the marks, and says so in the notes -- the
    limits are settings, so no caller can predict the drop.
    """
    score = _composite_score()
    limits = Limits(**{**limits_as_dict(DEFAULT_LIMITS), "max_instructions": 1})
    notes: list[str] = []

    limited = enforce_hard_ceiling(score, limits, notes)

    assert len(limited.instructions) == 1
    head = limited.instructions[0].arrangement
    assert head is not None and head.group_size == 1
    # I-154: the line handed back to the caller leads with the setting that
    # bound. The sentence inside the Score is unchanged -- moving those bytes
    # would redraw every frozen corpus.
    assert notes == ["max_instructions: instruction list capped at 1; 1 dropped"]
