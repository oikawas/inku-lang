"""Render engine 14: one drawing sits on one lattice.

The grid is the paper, not a property of what is drawn on it. Engine 13 sized
the step from the stroke's own length, so a short line and a long line landed on
different grids and the same line at two places fell out of phase. These checks
pin the step to the canvas alone.
"""

from __future__ import annotations

from xml.etree import ElementTree

from inku_server.renderer import render
from inku_server.schema import Score

RENDER_SEED = 12345

# One score, three sizes: a 120px line, an 840px line and a circle. If the step
# still followed the stroke, these three would each bring their own grid.
MIXED_INSTRUCTIONS = [
    {"primitive": "line", "from": [0.44, 0.30], "to": [0.56, 0.30], "weight": "computer"},
    {"primitive": "line", "from": [0.08, 0.70], "to": [0.92, 0.70], "weight": "computer"},
    {"primitive": "circle", "center": [0.50, 0.50], "radius": 0.14, "weight": "computer"},
]

# Master-grid rounding, not slack: the worst deviation measured on a square
# canvas is 0.0 px and on a pillar canvas 1.1e-13 px. Off the lattice the error
# is most of a cell.
LATTICE_TOLERANCE_PX = 1e-5


def _cells(instructions: list[dict], *, aspect: str = "square") -> list[dict[str, str]]:
    score = Score.model_validate(
        {"canvas": {"aspect": aspect}, "instructions": instructions}
    )
    root = ElementTree.fromstring(
        render(score, render_seed=RENDER_SEED, svg_profile="editable")
    )
    return [
        node.attrib for node in root.iter() if node.attrib.get("class") == "raster-bleed"
    ]


def _one_step(cells: list[dict[str, str]]) -> float:
    sides = {cell["width"] for cell in cells} | {cell["height"] for cell in cells}
    assert len(sides) == 1, sides
    return float(sides.pop())


def test_every_stroke_in_one_score_shares_one_lattice() -> None:
    cells = _cells(MIXED_INSTRUCTIONS)
    assert len(cells) == 97
    step = _one_step(cells)
    assert step == 18.000000

    for cell in cells:
        for centre in (float(cell["x"]) + step / 2, float(cell["y"]) + step / 2):
            assert abs(centre - round(centre / step) * step) < LATTICE_TOLERANCE_PX


def test_the_step_comes_from_the_canvas_not_from_the_stroke() -> None:
    # Short side 1000 -> 18.0; short side 200 (pillar is 1:5) -> 3.6.
    assert _one_step(_cells(MIXED_INSTRUCTIONS)) == 18.000000
    assert _one_step(_cells(MIXED_INSTRUCTIONS, aspect="pillar")) == 3.600000

    # Seven times the length, same lattice.
    short = [MIXED_INSTRUCTIONS[0]]
    long = [MIXED_INSTRUCTIONS[1]]
    assert _one_step(_cells(short)) == _one_step(_cells(long)) == 18.000000


# (instruction, weight, cell count). The counts come from the geometry: one cell
# per sample the rounding moved.
BLEED_CASES = (
    ({"primitive": "line", "from": [0.18, 0.50], "to": [0.82, 0.50]}, "computer", 29),
    ({"primitive": "circle", "center": [0.50, 0.50], "radius": 0.24}, "computer", 74),
    (
        {"primitive": "square", "position": [0.28, 0.28], "size": [0.44, 0.44]},
        "computer",
        84,
    ),
    (
        {
            "primitive": "arc",
            "center": [0.50, 0.50],
            "radius": 0.27,
            "angle_start": 15.0,
            "angle_end": 285.0,
        },
        "computer",
        60,
    ),
    (
        {"primitive": "polygon", "center": [0.50, 0.50], "radius": 0.25, "sides": 7},
        "computer",
        112,
    ),
    # The lattice belongs to the tool that quantizes. Nobody else gets cells.
    ({"primitive": "line", "from": [0.18, 0.50], "to": [0.82, 0.50]}, "pencil", 0),
    ({"primitive": "line", "from": [0.18, 0.50], "to": [0.82, 0.50]}, "rotring", 0),
)


def test_lattice_cell_counts_and_tone() -> None:
    for instruction, weight, expected in BLEED_CASES:
        cells = _cells([{**instruction, "weight": weight}])
        assert len(cells) == expected, (instruction["primitive"], weight)
        if not cells:
            continue
        assert _one_step(cells) == 18.000000

    line = _cells([{**BLEED_CASES[0][0], "weight": "computer"}])
    step = _one_step(line)
    head = [
        (
            round(float(cell["x"]) + step / 2, 6),
            round(float(cell["y"]) + step / 2, 6),
            cell["fill-opacity"],
        )
        for cell in line[:5]
    ]
    # Rows 4 and 5 share a centre: with the step no longer shrinking with the
    # stroke, consecutive samples can round into the same cell. They are drawn
    # twice rather than merged.
    assert head == [
        (216.000000, 522.000000, "0.400756"),
        (252.000000, 522.000000, "0.349177"),
        (288.000000, 540.000000, "0.229277"),
        (306.000000, 540.000000, "0.100432"),
        (306.000000, 540.000000, "0.450000"),
    ]

    tones = [float(cell["fill-opacity"]) for cell in line]
    assert min(tones) == 0.040347
    assert max(tones) == 0.450000
    assert round(sum(tones) / len(tones), 6) == 0.306994
