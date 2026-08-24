"""Public schema and coercion contracts for the one-sided thinness axis."""

from __future__ import annotations

from typing import get_args

from inku_server import composer
from inku_server.coerce import coerce_score
from inku_server.schema import Score, Thinness


def _score(thinness: str | None) -> Score:
    instruction = {
        "primitive": "line",
        "from": [0.1, 0.5],
        "to": [0.9, 0.5],
        "weight": "pencil",
    }
    if thinness is not None:
        instruction["thinness"] = thinness
    return Score.model_validate({"instructions": [instruction]})


def test_thinness_has_only_the_two_narrowing_values() -> None:
    assert get_args(Thinness) == ("fine", "extra_fine")


def test_saved_scores_preserve_each_thinness_value() -> None:
    assert _score("fine").instructions[0].thinness == "fine"
    assert _score("extra_fine").instructions[0].thinness == "extra_fine"
    assert _score(None).instructions[0].thinness is None


def test_stage_two_schema_places_thinness_before_surface() -> None:
    properties = composer._score_tool_schema()["properties"]["instructions"]["items"][
        "properties"
    ]
    assert list(properties).index("thinness") + 1 == list(properties).index("surface")
    assert properties["thinness"]["anyOf"][0]["enum"] == ["fine", "extra_fine"]


def test_coercion_keeps_a_supplied_thinness() -> None:
    score = coerce_score(_score("extra_fine"), ddl="an extra fine pencil line")
    assert score.instructions[0].thinness == "extra_fine"
