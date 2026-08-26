"""Direct acceptance for I-403 stated surface delivery and fill deduplication."""

from __future__ import annotations

import pytest

from inku_server.coerce import coerce_score
from inku_server.schema import Score


def _circle(**changes: object) -> dict[str, object]:
    circle: dict[str, object] = {
        "primitive": "circle",
        "center": [0.5, 0.5],
        "radius": 0.16,
        "color": "black",
    }
    circle.update(changes)
    return circle


def _coerced(
    instructions: list[dict[str, object]],
    *,
    ddl: str,
    lang: str,
) -> tuple[Score, dict[str, int]]:
    report: dict[str, int] = {}
    score = coerce_score(
        Score.model_validate({"instructions": instructions}),
        ddl=ddl,
        lang=lang,
        branch_report=report,
    )
    return score, report


def test_english_flat_surface_reaches_the_one_closed_shape() -> None:
    score, report = _coerced(
        [_circle(surface={"texture": "none"})],
        ddl="Figure: one black circle. Surface: flat.",
        lang="en",
    )

    assert len(score.instructions) == 1
    circle = score.instructions[0]
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert circle.filled is True
    assert report["with_stated_surface_fidelity"] == 1
    assert report["with_fill_as_a_surface_word"] == 1


def test_japanese_fill_equivalent_circles_become_one_instruction() -> None:
    score, report = _coerced(
        [
            _circle(surface={"texture": "solid"}),
            _circle(filled=True),
        ],
        ddl="図形: 黒い円を一つ。面: 塗り。",
        lang="ja",
    )

    assert len(score.instructions) == 1
    circle = score.instructions[0]
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert circle.filled is True
    assert report["with_structural_duplicate_repair"] == 1
    assert report["with_stated_surface_fidelity"] == 0


@pytest.mark.parametrize(
    ("ddl", "instructions"),
    [
        ("Figure: one black circle.", [_circle(surface={"texture": "none"})]),
        ("Figure: one black circle. Surface: empty.", [_circle(surface={"texture": "none"})]),
        (
            "Figure: one black circle. Surface: flat. Surface: hatch.",
            [_circle(surface={"texture": "none"})],
        ),
        ("Surface: flat.", [{"primitive": "line"}]),
        (
            "Figure: two black circles. Surface: flat.",
            [_circle(), _circle(center=[0.7, 0.5])],
        ),
    ],
)
def test_stated_surface_does_not_guess_when_the_contract_is_ambiguous(
    ddl: str,
    instructions: list[dict[str, object]],
) -> None:
    score, report = _coerced(instructions, ddl=ddl, lang="en")

    assert len(score.instructions) == len(instructions)
    assert report["with_stated_surface_fidelity"] == 0


def test_matching_surface_is_a_noop_and_preserves_its_other_fields() -> None:
    expected_surface = {
        "texture": "hatch",
        "density": 0.61,
        "scale": 0.27,
        "opacity": 0.44,
        "direction": "vertical",
    }
    score, report = _coerced(
        [_circle(surface=expected_surface)],
        ddl="Figure: one black circle. Surface: hatch.",
        lang="en",
    )

    circle = score.instructions[0]
    assert circle.surface is not None
    assert circle.surface.model_dump(exclude_defaults=True) == expected_surface
    assert report["with_stated_surface_fidelity"] == 0


@pytest.mark.parametrize(
    "difference",
    [
        {"center": [0.7, 0.5]},
        {"style": "dotted"},
        {"color": "red"},
        {"weight": "pencil"},
        {"arrangement": {"count": 2, "layout": "scatter"}},
        {"relation": {"type": "touching"}},
        {"surface": {"texture": "none", "density": 0.7}},
    ],
)
def test_fill_equivalence_does_not_hide_a_meaningful_difference(
    difference: dict[str, object],
) -> None:
    legacy_fill = _circle(filled=True)
    legacy_fill.update(difference)
    score, _report = _coerced(
        [_circle(surface={"texture": "solid"}), legacy_fill],
        ddl="図形: 黒い円を二つ。",
        lang="ja",
    )

    assert len(score.instructions) == 2


@pytest.mark.parametrize("disabled", [False, True])
def test_delivery_and_fill_deduplication_apply_on_both_exits(
    monkeypatch: pytest.MonkeyPatch,
    disabled: bool,
) -> None:
    if disabled:
        monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    else:
        monkeypatch.delenv("INKU_COERCE_DISABLE", raising=False)

    score, report = _coerced(
        [
            _circle(surface={"texture": "solid"}),
            _circle(filled=True),
        ],
        ddl="図形: 黒い円を一つ。面: 塗り。",
        lang="ja",
    )

    assert len(score.instructions) == 1
    circle = score.instructions[0]
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert circle.filled is True
    assert report["with_structural_duplicate_repair"] == 1
    assert report["with_stated_surface_fidelity"] == 0


def test_stated_surface_repair_is_a_fixed_point() -> None:
    first, _first_report = _coerced(
        [_circle(surface={"texture": "none"})],
        ddl="Figure: one black circle. Surface: flat.",
        lang="en",
    )
    second_report: dict[str, int] = {}
    second = coerce_score(
        first,
        ddl="Figure: one black circle. Surface: flat.",
        lang="en",
        branch_report=second_report,
    )

    assert second.model_dump() == first.model_dump()
    assert second_report["with_stated_surface_fidelity"] == 0
    assert second_report["with_fill_as_a_surface_word"] == 0
