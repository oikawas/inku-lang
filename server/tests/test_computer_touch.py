"""Render engine 13 contracts for the computer touch."""

from __future__ import annotations

from typing import get_args
from xml.etree import ElementTree

from inku_server.renderer import render
from inku_server.saijiki import SAIJIKI
from inku_server.schema import Score, Weight
from inku_server.stroke_engine import GRAMMARS, synthesize_stroke


def _line_score(weight: str, *, count: int = 1) -> Score:
    instruction: dict = {
        "primitive": "line",
        "from": [0.2, 0.5],
        "to": [0.8, 0.5],
        "weight": weight,
    }
    if count > 1:
        instruction["arrangement"] = {
            "count": count,
            "layout": "vertical",
            "margin": 0.15,
        }
    return Score.model_validate({"instructions": [instruction]})


def test_computer_repeats_width_and_dash_across_render_seeds() -> None:
    computer_a = synthesize_stroke(
        (200.0, 500.0), (800.0, 500.0), 2.0, "computer", seed=472
    )
    computer_b = synthesize_stroke(
        (200.0, 500.0), (800.0, 500.0), 2.0, "computer", seed=93
    )
    assert [sample.width for sample in computer_a.samples] == [
        sample.width for sample in computer_b.samples
    ]
    assert len({sample.width for sample in computer_a.samples}) <= 4

    pencil_a = synthesize_stroke(
        (200.0, 500.0), (800.0, 500.0), 2.0, "pencil", seed=472
    )
    pencil_b = synthesize_stroke(
        (200.0, 500.0), (800.0, 500.0), 2.0, "pencil", seed=93
    )
    assert [sample.width for sample in pencil_a.samples] != [
        sample.width for sample in pencil_b.samples
    ]

    score = _line_score("computer", count=4)
    roots = [
        ElementTree.fromstring(render(score, render_seed=seed, svg_profile="editable"))
        for seed in (472, 93)
    ]
    dash_columns = [
        [
            node.attrib["stroke-dasharray"]
            for node in root.iter()
            if node.attrib.get("class") == "material-outline"
        ]
        for root in roots
    ]
    assert dash_columns[0] == dash_columns[1]


def test_computer_is_immune_to_wild_while_pencil_is_not() -> None:
    computer = _line_score("computer")
    assert render(computer, render_seed=77, wild=False) == render(
        computer, render_seed=77, wild=True
    )

    pencil = _line_score("pencil")
    assert render(pencil, render_seed=77, wild=False) != render(
        pencil, render_seed=77, wild=True
    )


def test_computer_material_layers_are_straight_and_share_one_dash() -> None:
    root = ElementTree.fromstring(
        render(_line_score("computer", count=4), render_seed=77)
    )
    material = [
        node for node in root.iter() if node.attrib.get("class") == "material-outline"
    ]
    assert len(material) == 8
    assert all(node.tag.endswith("line") for node in material)
    assert not any(node.tag.endswith("polyline") for node in material)
    assert {node.attrib["stroke-dasharray"] for node in material} == {
        "22.000000,9.000000"
    }
    assert {node.attrib["stroke-width"] for node in material} == {"0.900000"}
    assert {node.attrib["stroke-opacity"] for node in material} == {"0.576000"}
    assert all(node.attrib["y1"] == node.attrib["y2"] for node in material)
    assert not any(node.tag.endswith("circle") for node in root.iter())
    assert "texture-computer" not in ElementTree.tostring(root, encoding="unicode")


def test_touch_score_values_match_weight_and_stroke_grammars() -> None:
    touch = next(category for category in SAIJIKI if category.key == "tezawari")
    score_values = {word.score_value for word in touch.words}
    assert None not in score_values
    assert score_values == set(get_args(Weight)) == set(GRAMMARS)
