"""engine 31: the arrangement layer keeps its shape on any canvas.

engine 30 put a mark's own size on the short edge, so a circle stays a circle
whatever the canvas is. What arranges those marks was still anisotropic: a
`radial` ring drawn on the pillar (1:5) came out with an aspect of 0.19 -- round
dots sitting on a flattened ring -- and an `at.region` written as a square box
came out as tall or as wide as the canvas.

Every gate here is stated as "the same number the square canvas produces", never
as an absolute: the ring's own aspect is 0.99 and not 1.00 (`_rhythm_t` includes
both ends, so twelve points divide the circle into eleven steps and the ends do
not fall symmetrically), and the grid box's is 1.125 and not 1.00 (twelve cells
tile as 4x3). Writing the round numbers would fail a correct implementation.

R1 -- putting `arrangement.margin` on the short edge -- was refused (author,
2026-08-12), so the layouts that spread to the frame are deliberately untested
here: filling the canvas is what those layouts mean.
"""

from __future__ import annotations

import copy

import pytest

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server import renderer
from inku_server.renderer import (
    _anchor,
    _expand_arrangement,
    _region_in_short_side_units,
    _resolve_performance_score,
    render,
)
from inku_server.schema import Score

# Quantisation leaves the derived ratios agreeing to about 1e-8; the anisotropy
# these gates are here to catch is of the order of the canvas aspect itself
# (0.2 on the pillar), so this is four orders of magnitude of headroom.
TOLERANCE = 1e-6

ASPECTS = ("pillar", "vertical", "wide", "golden")
REGION = [0.6, 0.18, 0.82, 0.4]  # a square box: 0.22 x 0.22

RING = {
    "primitive": "circle", "center": [0.5, 0.5], "radius": 0.02,
    "color": "black", "weight": "brush_thick",
    "arrangement": {"count": 12, "layout": "radial", "radius": 0.3,
                    "center": [0.5, 0.5]},
}
REGION_SINGLE = {
    "primitive": "circle", "center": [0.5, 0.5], "radius": 0.012,
    "color": "black", "weight": "pen", "at": {"region": REGION},
}
REGION_GRID = {
    **REGION_SINGLE,
    "arrangement": {"count": 12, "layout": "grid", "jitter": 0.0},
}


def _placed_px(
    instruction: dict, aspect: str, *, render_seed: int = 7
) -> list[tuple[float, float]]:
    """Where the marks of one instruction land, in pixels, on `aspect`.

    The two calls are the ones `render()` makes (renderer.py, the resolve and
    the expansion), in that order and with those arguments, so a gate here runs
    on the same path a drawing does rather than on a copy of it.
    """
    canvas = canvas_size_for_aspect(aspect)
    score = Score.model_validate(
        {"version": "0.1.0", "canvas": aspect, "background": "white",
         "instructions": [copy.deepcopy(instruction)]}
    )
    resolved = _resolve_performance_score(score, render_seed, canvas)
    points: list[tuple[float, float]] = []
    for ins in resolved.instructions:
        members = (
            _expand_arrangement(
                ins, render_seed, canvas, performance_seed=render_seed
            )
            if ins.arrangement
            else [ins]
        )
        for member in members:
            ax, ay = _anchor(member)
            points.append((ax * canvas.width, ay * canvas.height))
    return points


def _extent(points: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _bbox_aspect(points: list[tuple[float, float]]) -> float:
    width, height = _extent(points)
    return width / height


def _landing_spread_px(
    instruction: dict, aspect: str, seeds: range
) -> list[tuple[float, float]]:
    """Where one mark can land inside its region, sampled across seeds.

    One score cannot answer this: repeating the same instruction inside a score
    draws one mark, not many. The region is walked by drawing the same
    instruction again under a different performance seed.
    """
    points: list[tuple[float, float]] = []
    for seed in seeds:
        points += _placed_px(instruction, aspect, render_seed=seed)
    return points


# --- T-1 / T-2: the ring (R2) -------------------------------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_radial_ring_keeps_the_square_canvas_aspect(aspect: str):
    """T-1: the ring is as round on any canvas as it is on the square one."""
    reference = _bbox_aspect(_placed_px(RING, "square"))
    assert reference == pytest.approx(0.9898214, abs=1e-6)  # not 1.00
    assert _bbox_aspect(_placed_px(RING, aspect)) == pytest.approx(
        reference, abs=TOLERANCE
    )


@pytest.mark.parametrize("aspect", ("square", "pillar", "wide"))
def test_radial_radius_still_scales_with_the_stated_radius(aspect: str):
    """T-2: the ring is drawn from the stated radius, not from the short edge.

    Doubling `arrangement.radius` has to double the ring in pixels. An
    implementation that drew the ring at some constant fraction of the short
    edge would pass T-1 and fail here.
    """
    small = copy.deepcopy(RING)
    small["arrangement"]["radius"] = 0.15
    large = copy.deepcopy(RING)
    large["arrangement"]["radius"] = 0.30

    small_w, small_h = _extent(_placed_px(small, aspect))
    large_w, large_h = _extent(_placed_px(large, aspect))

    assert large_w / small_w == pytest.approx(2.0, abs=TOLERANCE)
    assert large_h / small_h == pytest.approx(2.0, abs=TOLERANCE)


# --- T-3 / T-4 / T-5: the region (R3) -----------------------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_single_mark_region_keeps_the_square_canvas_aspect(aspect: str):
    """T-3: `_resolve_at_region` -- where one mark can fall keeps its shape."""
    seeds = range(1, 25)
    reference = _bbox_aspect(_landing_spread_px(REGION_SINGLE, "square", seeds))
    assert _bbox_aspect(
        _landing_spread_px(REGION_SINGLE, aspect, seeds)
    ) == pytest.approx(reference, abs=TOLERANCE)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_grid_region_keeps_the_square_canvas_aspect(aspect: str):
    """T-4: the grid branch reads the region too.

    This is a separate site from T-3's: a fix applied only to
    `_resolve_at_region` leaves the grid stretched and T-3 green.
    """
    reference = _bbox_aspect(_placed_px(REGION_GRID, "square"))
    assert reference == pytest.approx(1.125, abs=1e-6)  # 12 cells tile 4x3
    assert _bbox_aspect(_placed_px(REGION_GRID, aspect)) == pytest.approx(
        reference, abs=TOLERANCE
    )


@pytest.mark.parametrize("aspect", ("square", "pillar", "wide"))
def test_region_extent_still_scales_with_the_stated_region(aspect: str):
    """T-5: the region is drawn from what the description stated.

    Same centre, twice the width, so the box has to come out twice as wide in
    pixels. An implementation that drew every region at a fixed fraction of the
    short edge would pass T-3 and T-4 and fail here.
    """
    seeds = range(1, 25)
    narrow = copy.deepcopy(REGION_SINGLE)
    wide = copy.deepcopy(REGION_SINGLE)
    wide["at"] = {"region": [0.49, 0.18, 0.93, 0.4]}  # centre 0.71, width x2

    narrow_w, _ = _extent(_landing_spread_px(narrow, aspect, seeds))
    wide_w, _ = _extent(_landing_spread_px(wide, aspect, seeds))

    assert wide_w / narrow_w == pytest.approx(2.0, abs=TOLERANCE)


# --- T-6: the centre stays proportional ---------------------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_region_centre_stays_proportional(aspect: str):
    """T-6: "upper right" is the upper right of every canvas.

    The ruling puts the region's extent on the short edge and leaves its centre
    alone. A region with no extent has nowhere to land but its centre, so this
    reads the centre directly.
    """
    canvas = canvas_size_for_aspect(aspect)
    centred = copy.deepcopy(REGION_SINGLE)
    centred["at"] = {"region": [0.71, 0.29, 0.71, 0.29]}

    (x_px, y_px), = _placed_px(centred, aspect, render_seed=5)
    assert (x_px / canvas.width, y_px / canvas.height) == (0.71, 0.29)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_grid_region_centre_stays_proportional(aspect: str):
    """T-6 at the grid site: the tiling is centred where the region is."""
    canvas = canvas_size_for_aspect(aspect)
    points = _placed_px(REGION_GRID, aspect)
    xs = [point[0] / canvas.width for point in points]
    ys = [point[1] / canvas.height for point in points]

    assert (min(xs) + max(xs)) / 2 == pytest.approx(0.71, abs=1e-9)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(0.29, abs=1e-9)


# --- T-7: the square canvas is untouched --------------------------------


@pytest.mark.parametrize(
    "region",
    ([0.6, 0.18, 0.82, 0.4], [0.0, 0.0, 1.0, 1.0], [0.31, 0.07, 0.93, 0.55]),
)
def test_square_canvas_returns_the_region_unchanged(region: list[float]):
    """T-7, at the arithmetic: a square canvas must be exactly the identity.

    Not approximately. Centre +/- half-extent does not round-trip in floating
    point even when the factor is 1.0 -- for [0.6, 0.18, 0.82, 0.4] it moves y0
    by 2.78e-17 -- which is enough to cross a rounding boundary downstream and
    move a frozen square case.
    """
    square = canvas_size_for_aspect("square")
    assert _region_in_short_side_units(region, square) == tuple(region)


def test_square_canvas_svg_is_byte_identical_without_the_rule(monkeypatch):
    """T-7, at the drawing: engine 31 changes nothing on a square canvas.

    The comparison is against the rule switched off, which is what the previous
    engine did on this path -- the short-side factors are exactly 1.0 on a
    square canvas, so the two have to agree byte for byte. The score below runs
    all three sites the ruling touches: the ring, the single region mark and
    the grid over a region.
    """
    score_input = {
        "version": "0.1.0", "canvas": "square", "background": "white",
        "instructions": [
            copy.deepcopy(RING),
            copy.deepcopy(REGION_SINGLE),
            copy.deepcopy(REGION_GRID),
        ],
    }

    def draw() -> str:
        return render(
            Score.model_validate(copy.deepcopy(score_input)),
            render_seed=7,
            composition_seed=7,
            svg_profile="display",
        )

    with_rule = draw()
    monkeypatch.setattr(
        renderer,
        "_region_in_short_side_units",
        lambda region, canvas: tuple(region),
    )
    without_rule = draw()

    assert with_rule == without_rule
