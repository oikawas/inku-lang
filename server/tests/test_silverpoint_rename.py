"""Public compatibility contracts for the hair-to-silverpoint rename."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from inku_server.schema import Score, Weight


def _score(weight: str) -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5], "weight": weight}
            ]
        }
    )


def test_the_weight_enum_replaced_the_name_rather_than_adding_one() -> None:
    weights = get_args(Weight)
    assert "silverpoint" in weights
    assert "hair" not in weights
    assert len(weights) == 11


def test_saved_hair_scores_replay_as_silverpoint() -> None:
    assert _score("hair").instructions[0].weight == "silverpoint"
    assert _score("hair").instructions[0].weight != Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5]}]}
    ).instructions[0].weight


def test_only_the_compatibility_spelling_is_replaced() -> None:
    for spelling in ("Hair", "hairs", "silver-point", "silver point", "metalpoint"):
        with pytest.raises(ValidationError):
            _score(spelling)


def test_silverpoint_keeps_its_rust_render_properties() -> None:
    import inku_render

    reference = json.loads(inku_render.renderer_reference_json())
    silverpoint = next(
        item
        for item in reference["weight_properties"]["weights"]
        if item["weight"] == "silverpoint"
    )
    assert silverpoint == {
        "weight": "silverpoint",
        "stroke_width": 0.5,
        "stroke_opacity": 0.72,
        "stroke_dasharray": None,
        "stroke_linecap": "butt",
        "texture_filter": False,
    }
