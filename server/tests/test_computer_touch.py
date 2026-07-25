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


def _bleed_cells(score: Score, *, render_seed: int = 12345) -> list[dict[str, str]]:
    root = ElementTree.fromstring(
        render(score, render_seed=render_seed, svg_profile="editable")
    )
    return [
        node.attrib
        for node in root.iter()
        if node.attrib.get("class") == "raster-bleed"
    ]


def _shape_score(instruction: dict) -> Score:
    return Score.model_validate({"instructions": [instruction]})


# The counts come from the geometry, not from the material code: one cell per
# sample the rounding moved. Endpoints are pinned to the intention and polygon
# corners are anchored, so those samples carry no residual and emit no cell —
# which is why a line gives 39 cells for 41 samples and a square 76 for 80.
BLEED_COUNTS = (
    ({"primitive": "line", "from": [0.08, 0.5], "to": [0.92, 0.5]}, 39),
    ({"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2}, 62),
    ({"primitive": "square", "position": [0.3, 0.3], "size": [0.4, 0.4]}, 76),
    (
        {
            "primitive": "arc",
            "center": [0.5, 0.5],
            "radius": 0.27,
            "angle_start": 15,
            "angle_end": 285,
        },
        60,
    ),
)


def test_computer_bleeds_one_lattice_cell_per_rounded_sample() -> None:
    for instruction, expected in BLEED_COUNTS:
        cells = _bleed_cells(_shape_score({**instruction, "weight": "computer"}))
        assert len(cells) == expected, instruction["primitive"]

    for weight in ("pencil", "rotring"):
        assert (
            _bleed_cells(
                _shape_score(
                    {
                        "primitive": "line",
                        "from": [0.08, 0.5],
                        "to": [0.92, 0.5],
                        "weight": weight,
                    }
                )
            )
            == []
        )


def test_computer_bleed_cells_sit_on_the_lattice_with_graded_tone() -> None:
    cells = _bleed_cells(
        _shape_score(
            {
                "primitive": "line",
                "from": [0.08, 0.5],
                "to": [0.92, 0.5],
                "weight": "computer",
            }
        )
    )
    step = float(cells[0]["width"])
    assert step == 15.120000
    assert {cell["height"] for cell in cells} == {cells[0]["width"]}

    centres = [
        (float(cell["x"]) + step / 2, float(cell["y"]) + step / 2) for cell in cells
    ]
    # Every cell is the lattice point the ink was rounded into, never the
    # intended position: each centre is an exact multiple of the step.
    for cx, cy in centres:
        assert abs(cx / step - round(cx / step)) < 1e-9
        assert abs(cy / step - round(cy / step)) < 1e-9

    head = [
        (round(cx, 6), round(cy, 6), cell["fill-opacity"])
        for (cx, cy), cell in zip(centres[:5], cells[:5])
    ]
    assert head == [
        (105.840000, 514.080000, "0.283154"),
        (151.200000, 529.200000, "0.140918"),
        (181.440000, 544.320000, "0.235045"),
        (196.560000, 544.320000, "0.450000"),
        (211.680000, 544.320000, "0.359455"),
    ]

    # The tone is the size of the discarded residual, so it is graded, and the
    # ceiling is reached only where the rounding moved half a cell.
    tones = [float(cell["fill-opacity"]) for cell in cells]
    assert min(tones) == 0.029548
    assert max(tones) == 0.450000
    assert round(sum(tones) / len(tones), 6) == 0.276556


def test_computer_has_no_material_outline_layer() -> None:
    root = ElementTree.fromstring(
        render(_line_score("computer", count=4), render_seed=77)
    )
    assert not [
        node for node in root.iter() if node.attrib.get("class") == "material-outline"
    ]
    assert not any(node.tag.endswith("circle") for node in root.iter())
    assert "texture-computer" not in ElementTree.tostring(root, encoding="unicode")

    # The hand tools keep theirs: removing the computer's ruled layer must not
    # reach into `_MATERIAL_OUTLINE_SPECS` for anyone else.
    pencil = ElementTree.fromstring(render(_line_score("pencil"), render_seed=77))
    assert [
        node for node in pencil.iter() if node.attrib.get("class") == "material-outline"
    ]


def test_touch_score_values_match_weight_and_stroke_grammars() -> None:
    touch = next(category for category in SAIJIKI if category.key == "tezawari")
    score_values = {word.score_value for word in touch.words}
    assert None not in score_values
    assert score_values == set(get_args(Weight)) == set(GRAMMARS)
