"""Render engine 30: a mark keeps the shape the description gave it.

Engine 29 turned `size` into pixels anisotropically -- `size[0] * canvas.width`
and `size[1] * canvas.height` -- so the same description drew a different shape
on every aspect. A square written `size [0.3, 0.3]` came out 1.61:1 on the
golden canvas and 0.20:1 on the pillar, and worst of all an ellipse written
`size [0.4, 0.2]` (wide, 2:1) came out 0.40 on the pillar: upright, the reverse
of what the description said. Engine 30 puts both extents on the short edge, so
the aspect decides where a mark sits and no longer what shape it is.

The cases here are synthetic. Everything is measured from the ink the renderer
actually wrote -- the coordinates in `points` and `d` inside the content layer --
rather than from the helper under test, so a helper that returned the right
numbers while the drawing went elsewhere would not pass.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest

from inku_server.renderer import render
from inku_server.schema import Score

RENDER_SEED = 12345
SVG_NS = "{http://www.w3.org/2000/svg}"
ASPECTS = ("square", "golden", "pillar", "wide")

# The hand is what keeps these ratios off their nominal value: a 1:1 square
# measures 0.976, because the tremor is not symmetric and the grid a tool
# quantises onto is a share of the short edge rather than of the mark. Neither
# is noise-free across aspects, so the floor was measured rather than assumed:
# over the six marks below the widest spread on a correct engine 30 is 0.0030
# (clamped-square), and the smallest defect the perturbations produce is 0.0956
# (one site of `_representative_size_px` put back). 0.02 sits between the two,
# an order of magnitude under what engine 29 itself did (a square written 1:1
# came out 1.61 on the golden canvas).
RATIO_TOLERANCE = 0.02

# A texture and a tremor, because three of the four functions that turned `size`
# into pixels are unreachable without them: `_shape_bbox` and `_surface_contour`
# return early when `surface` is None, and `_representative_size_px` is only
# read to scale a variation. Measured with a counting wrapper over one run of
# the four aspects: 12 / 16 / 16 / 16 calls. Drawn plain, this score would walk
# `_render_instruction` alone and a revert in the other three would pass.
SURFACE = {"texture": "stipple", "density": 0.5, "scale": 0.4, "opacity": 0.3}
VARIATION = {
    "amplitude": "broad",
    "frequency": "medium",
    "quality": "perlin",
    "dimensions": ["position_x", "position_y"],
}

# Four primitives because all four read `size`, and the twelve multiplications
# engine 29 had were spread over four functions. A single primitive walks only
# part of that.
#
# The fifth entry is not a fifth primitive but a fifth reading of the same one.
# `_representative_size_px` reaches the paper through one term only -- the
# amplitude clamp, `min(amplitude * stroke_width, 0.40 * representative)` -- and
# on the four marks above the stroke-width term is what binds, so the whole
# function could go back to width/height and nothing would move. A small figure
# drawn with a thick tool is where the clamp is the smaller of the two
# (measured, square canvas: 16.00 px of amplitude against a 11.31 px clamp),
# and that is the safety valve the representative size exists to feed.
SHAPES: dict[str, dict] = {
    "square": {"primitive": "square", "position": [0.35, 0.35], "size": [0.3, 0.3]},
    "ellipse": {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.4, 0.2]},
    "triangle": {"primitive": "triangle", "position": [0.35, 0.35], "size": [0.3, 0.3]},
    "cloudform": {"primitive": "cloudform", "center": [0.5, 0.5], "size": [0.4, 0.25]},
    "clamped-ellipse": {
        "primitive": "ellipse",
        "center": [0.25, 0.75],
        "size": [0.08, 0.04],
        "weight": "brush_thick",
    },
    # Unequal extents, and the wider one first, because `_representative_size_px`
    # reduces square, triangle and cloudform to `min(w, h) / 2`. A mark whose two
    # extents are written the same survives that reduction unchanged -- engine
    # 29's `min(s * width, s * height)` is `s * unit`, exactly what engine 30
    # computes -- and so does one written taller than it is wide. Only a mark
    # written wider than it is tall separates the two rules there, and 4:1
    # separates them by the full factor the pillar allows: on that canvas the
    # representative size is 4 px under engine 30 and 16 under engine 29.
    "clamped-square": {
        "primitive": "square",
        "position": [0.70, 0.20],
        "size": [0.16, 0.04],
        "weight": "brush_thick",
    },
}

# `position` would raise: an ellipse is anchored on its centre.
SCORE_ORDER = (
    "square",
    "ellipse",
    "triangle",
    "cloudform",
    "clamped-ellipse",
    "clamped-square",
)

_NUMBER = re.compile(r"-?\d+\.?\d*(?:e-?\d+)?")


def _drawn_points(node) -> list[tuple[float, float]]:
    """The coordinate pairs one element put on the paper."""
    pairs: list[tuple[float, float]] = []
    for attr in ("points", "d"):
        raw = node.attrib.get(attr)
        if not raw:
            continue
        numbers = [float(value) for value in _NUMBER.findall(raw)]
        pairs.extend(zip(numbers[0::2], numbers[1::2]))
    return pairs


def _render(instructions: list[dict], aspect: str, **shared) -> ElementTree.Element:
    score = Score.model_validate(
        {
            "canvas": {"aspect": aspect},
            "instructions": [
                {"weight": "pen", **item, **shared} for item in instructions
            ],
        }
    )
    return ElementTree.fromstring(
        render(score, render_seed=RENDER_SEED, svg_profile="editable")
    )


def _instruction_groups(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        node
        for node in root.iter(f"{SVG_NS}g")
        if node.attrib.get("id", "").startswith("instruction_")
    ]


def _extent(node: ElementTree.Element) -> tuple[float, float]:
    """Width and height of the ink under one node, in px."""
    points = [pair for child in node.iter() for pair in _drawn_points(child)]
    assert points, ElementTree.tostring(node)[:200]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _canvas_px(root: ElementTree.Element) -> tuple[float, float]:
    return float(root.attrib["width"]), float(root.attrib["height"])


def _shape_ratios(aspect: str) -> dict[str, float]:
    """Width / height of each mark in one score drawn on one canvas."""
    root = _render(
        [SHAPES[name] for name in SCORE_ORDER],
        aspect,
        surface=SURFACE,
        variation=VARIATION,
    )
    groups = _instruction_groups(root)
    assert len(groups) == len(SCORE_ORDER), [g.attrib["id"] for g in groups]
    ratios = {}
    for name, group in zip(SCORE_ORDER, groups):
        width, height = _extent(group)
        ratios[name] = width / height
    return ratios


def _grain_counts(aspect: str) -> dict[str, int]:
    """How many stipple dabs each mark carries on one canvas."""
    root = _render(
        [SHAPES[name] for name in SCORE_ORDER],
        aspect,
        surface=SURFACE,
        variation=VARIATION,
    )
    counts = {}
    for name, group in zip(SCORE_ORDER, _instruction_groups(root)):
        counts[name] = len(
            [
                node
                for node in group.iter()
                if node.attrib.get("class", "").startswith("surface-stroke-v1")
            ]
        )
    return counts


# --- T-1: the mark keeps its shape --------------------------------------- #


@pytest.mark.parametrize("primitive", SCORE_ORDER)
def test_the_mark_keeps_its_shape_on_any_canvas(primitive: str) -> None:
    """One description, four aspects, one shape.

    Written against the square canvas rather than against a constant: what the
    description asked for is a proportion, and a rule that scaled every mark by
    some other constant would still be wrong in the same way engine 29 was.
    """
    ratios = {aspect: _shape_ratios(aspect)[primitive] for aspect in ASPECTS}
    reference = ratios["square"]
    for aspect in ASPECTS:
        assert ratios[aspect] == pytest.approx(reference, abs=RATIO_TOLERANCE), ratios


@pytest.mark.parametrize("primitive", SCORE_ORDER)
def test_the_mark_carries_the_same_texture_on_any_canvas(primitive: str) -> None:
    """The other way `_shape_bbox` reaches the paper.

    How many grains a surface lays down is a share of the mark's own area,
    `(w * h) / (unit * unit * 0.18)`, so under engine 30 both terms scale with
    the short edge and the count is the same on every canvas. Engine 29's bbox
    grew or shrank with the aspect, and on the pillar it hit the 1.8 ceiling.
    Held apart from the ratio checks because grains are scattered inside the
    contour: adding or dropping a few moves the count but not the extent, and a
    shape-ratio reading cannot see it.
    """
    counts = {aspect: _grain_counts(aspect)[primitive] for aspect in ASPECTS}
    assert len(set(counts.values())) == 1, counts


# --- T-2: the description's orientation survives -------------------------- #


def test_a_wide_ellipse_is_still_wide_on_a_pillar() -> None:
    """The reverse pair T-1 cannot see.

    T-1 compares a ratio against the same ratio, so it says nothing about which
    way round the mark is. This does: `size [0.4, 0.2]` is 2:1 wide, and on the
    pillar canvas engine 29 drew it 0.40 -- upright, the reverse of what the
    description said.
    """
    pillar = _shape_ratios("pillar")["ellipse"]
    assert pillar > 1.0, pillar
    assert pillar == pytest.approx(
        _shape_ratios("square")["ellipse"], abs=RATIO_TOLERANCE
    )


def test_the_mark_lands_on_the_paper_it_was_given() -> None:
    """Which edge, not just which proportion.

    Following the long edge preserves proportion and orientation exactly as
    well as following the short one -- measured, a rule built on
    `max(width, height)` still draws this ellipse 2.01 wide on the pillar -- so
    neither T-1 nor the check above separates the two. What separates them is
    scale: the pillar is 200 px across, and a mark 0.4 of the long edge is 400
    px wide, half of it off the paper on either side. Read as containment
    rather than as a formula, because 'both extents times the short edge' is
    the implementation and this is what it is for.
    """
    for aspect in ASPECTS:
        root = _render(
            [SHAPES["ellipse"]], aspect, surface=SURFACE, variation=VARIATION
        )
        canvas_width, canvas_height = _canvas_px(root)
        points = [
            pair
            for node in _instruction_groups(root)[0].iter()
            for pair in _drawn_points(node)
        ]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        assert 0.0 <= min(xs) and max(xs) <= canvas_width, (aspect, min(xs), max(xs))
        assert 0.0 <= min(ys) and max(ys) <= canvas_height, (aspect, min(ys), max(ys))


# --- T-3: placement still spreads with the aspect ------------------------- #


@pytest.mark.parametrize("aspect", ASPECTS)
def test_where_a_mark_sits_still_follows_the_whole_canvas(aspect: str) -> None:
    """The binding T-1 would let go of.

    Sizes follow the short edge; coordinates do not. A line drawn from x=0.1 to
    x=0.9 spans four fifths of the canvas whatever its shape -- 800 px on the
    square, 160 on the pillar, 1880 on the wide. Put `_px` on the short edge too
    and the drawing stops spreading into the canvas it was given.
    """
    root = _render([{"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}], aspect)
    canvas_width, _ = _canvas_px(root)
    width, _ = _extent(_instruction_groups(root)[0])
    assert width == pytest.approx(0.80 * canvas_width, abs=0.5), (aspect, width)
