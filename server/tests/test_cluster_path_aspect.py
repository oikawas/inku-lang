"""engine 32: a cluster and a path keep their shape on any canvas.

engine 30 put a mark's own size on the short edge and engine 31 did it for the
ring and the region. The same distortion was still in the two arrangements that
carry 36.2% of the marks production expands: a cluster written as "scattered in
clumps" came out as a narrow vertical stripe on the pillar (1:5) and a wide band
on CinemaScope -- the band's own aspect moved by a factor of 8.8 across those
two papers -- and a `wave` swung 220px on the square canvas against 44px on the
pillar for the same description.

Two quantities live in these functions and only one of them is a shape:

  * across the path, the wave's swing and the jitter, and the cluster's band --
    these are the figure, and they go on the short side;
  * along the path, `margin + t * span`, and the cluster's centre -- these say
    how much of the paper the group uses and where it sits, and they stay
    proportional (R3, and `span` is [I-135] (3)-b, still unruled).

Every gate is stated against the square canvas, or as a ratio, never as an
absolute pixel count: what "the same shape" means here is "the number the square
canvas produces", and the amount at stake is the canvas aspect itself (0.2 on
the pillar), four orders of magnitude above the 1e-9 quantisation.

Which paper a gate runs on is not free. On a canvas taller than it is wide the
short side is x, so `scale_x` is exactly 1.0 and anything measured on x there is
green whatever the code does; on a wide canvas it is the other way round. The
aspects each gate takes are chosen for the axis it measures.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.render_engines.default import planning
from inku_server.render_engines.default.planning import (
    _anchor,
    _expand_arrangement,
    _resolve_performance_score,
)
from inku_server.renderer import render
from inku_server.schema import Score

# The quantisation leaves the derived ratios agreeing to about 1e-9; the
# anisotropy these gates catch is of the order of the canvas aspect itself.
TOLERANCE = 1e-6

ASPECTS = ("pillar", "vertical", "wide", "golden")
# Papers whose long side is y: `scale_y` is the factor under test there, and
# `scale_x` is 1.0. The wave's swing and the diagonal's y jitter are measured
# on these.
Y_LONG = ("pillar", "vertical")
# Papers whose long side is x. `top_to_bottom` spreads on x, so it is measured
# on these and nowhere else.
X_LONG = ("wide", "golden")

_BASE = {
    "primitive": "circle", "center": [0.5, 0.5], "radius": 0.01,
    "color": "black", "weight": "pen",
}
_ARR = {"count": 40, "layout": "scatter", "jitter": 0.0, "margin": 0.1}

CLUSTER = {**_BASE, "arrangement": {
    **_ARR, "count": 36, "cluster_count": 1, "density": "medium",
    "path": "none"}}
# Three clumps strung along a path: the only input that reaches the fifth call
# site, the `_path_pos` inside `_clustered_pos` that resolves a cluster's
# centre. A `path="none"` cluster takes its centre from `_scatter_pos` instead,
# and would leave that site untested.
#
# The path is a `diagonal` because that is the one that spreads on both axes.
# With a `wave` the centres move only on y, so on a paper whose long side is x
# the factor is 1.0 and wiring the canvas into that call changes nothing --
# measured: the perturbation reddened two of the four papers instead of four.
CLUSTER_ON_PATH = {**_BASE, "arrangement": {
    **_ARR, "count": 36, "cluster_count": 3, "density": "low",
    "path": "diagonal"}}
PATH_WAVE = {**_BASE, "arrangement": {**_ARR, "path": "wave"}}
PATH_DIAGONAL = {**_BASE, "arrangement": {**_ARR, "path": "diagonal"}}
PATH_TTB = {**_BASE, "arrangement": {**_ARR, "path": "top_to_bottom"}}
SCATTER = {**_BASE, "arrangement": {**_ARR, "count": 60, "path": "none"}}
HORIZONTAL = {**_BASE, "arrangement": {
    **_ARR, "count": 20, "layout": "horizontal", "path": "none"}}
VERTICAL = {**_BASE, "arrangement": {
    **_ARR, "count": 20, "layout": "vertical", "path": "none"}}

SUBJECTS = {
    "cluster": CLUSTER,
    "path-wave": PATH_WAVE,
    "path-diagonal": PATH_DIAGONAL,
    "path-top_to_bottom": PATH_TTB,
}

# Measured on the square canvas at engine 31 (commit 93025219), before a line of
# engine 32 was written, and asserted here unchanged. This is what "engine 32
# does not move the square canvas" means as a number: the short-side factors are
# exactly 1.0 there, so every one of these coordinates has to come back.
#
# Freezing the placement rather than the SVG is deliberate. An implementation
# that reaches the right shape by some constant of its own -- 0.9 on both axes,
# say -- passes a gate written as "with the rule switched off it draws the same
# bytes", because such an implementation never calls the helper the switch turns
# off. It cannot pass this one.
ENGINE_31_SQUARE_PLACEMENT = {
    "cluster": "ea1aacb45707f5d2",
    "path-wave": "b58eab876a36afff",
    "path-diagonal": "e0ffc8ed78ac8f76",
    "path-top_to_bottom": "ae4496fa16702415",
}


def _placed(
    instruction: dict, aspect: str, *, render_seed: int = 7
) -> tuple[object, list[tuple[float, float]]]:
    """Where the marks of one instruction land, normalized, on `aspect`.

    The two calls are the ones `render()` makes, in that order and with those
    arguments, so a gate here runs on the path a drawing takes rather than on a
    copy of it.
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
        points += [_anchor(member) for member in members]
    return canvas, points


def _extent_px(
    instruction: dict, aspect: str, *, render_seed: int = 7
) -> tuple[float, float]:
    canvas, points = _placed(instruction, aspect, render_seed=render_seed)
    xs = [x * canvas.width for x, _ in points]
    ys = [y * canvas.height for _, y in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _bbox_aspect(instruction: dict, aspect: str) -> float:
    width, height = _extent_px(instruction, aspect)
    return width / height


def _placement_digest(instruction: dict, aspect: str) -> str:
    _, points = _placed(instruction, aspect)
    payload = json.dumps([[round(x, 9), round(y, 9)] for x, y in points])
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --- T-1 / T-2: the cluster's band --------------------------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_cluster_band_keeps_the_square_canvas_aspect(aspect: str):
    """T-1: one clump is the same shape on any paper.

    A single cluster is used so the measured box is the band itself; with
    several clumps the box would also carry the distance between them, which is
    a placement and is meant to follow the paper.
    """
    reference = _bbox_aspect(CLUSTER, "square")
    assert reference == pytest.approx(0.1977117, abs=1e-6)  # a narrow band
    assert _bbox_aspect(CLUSTER, aspect) == pytest.approx(reference, abs=TOLERANCE)


@pytest.mark.parametrize("aspect", ("square", "pillar", "wide"))
def test_cluster_band_still_scales_with_the_stated_density(aspect: str):
    """T-2: the band is drawn from the description's density, not from the edge.

    `low` gives a radius of 0.035 and `high` 0.085, so the band has to come out
    2.43 times the size in pixels. An implementation that drew every clump at
    some constant fraction of the short side would satisfy T-1 and fail here.
    """
    low = copy.deepcopy(CLUSTER)
    low["arrangement"]["density"] = "low"
    high = copy.deepcopy(CLUSTER)
    high["arrangement"]["density"] = "high"

    low_w, low_h = _extent_px(low, aspect)
    high_w, high_h = _extent_px(high, aspect)

    assert high_w / low_w == pytest.approx(0.085 / 0.035, abs=TOLERANCE)
    assert high_h / low_h == pytest.approx(0.085 / 0.035, abs=TOLERANCE)


# --- T-3 / T-4: the path's cross-axis spread ----------------------------


@pytest.mark.parametrize("aspect", Y_LONG)
def test_wave_swing_keeps_the_square_canvas_measure(aspect: str):
    """T-3, on y: the wave swings as far, in short-side units, as on the square.

    Read against the short side rather than as a pixel count, because that is
    what the description's 0.22 buys: 220px of a 1000px square and 44px of the
    pillar's 200px width, which is the same swing on paper of a different size.
    Only papers whose long side is y are taken -- on a wide canvas `scale_y` is
    1.0 and this passes however the code is written.
    """
    square = canvas_size_for_aspect("square")
    reference = _extent_px(PATH_WAVE, "square")[1] / square.unit

    canvas = canvas_size_for_aspect(aspect)
    assert _extent_px(PATH_WAVE, aspect)[1] / canvas.unit == pytest.approx(
        reference, abs=TOLERANCE
    )


@pytest.mark.parametrize("aspect", X_LONG)
def test_top_to_bottom_spread_keeps_the_square_canvas_measure(aspect: str):
    """T-3, on x: the other axis has its own factor and its own papers.

    `top_to_bottom` spreads on x, so the gate is on a canvas whose long side is
    x. A fix applied to `scale_y` alone leaves this one red, which is the point
    of measuring both axes on the papers where each one binds.
    """
    square = canvas_size_for_aspect("square")
    reference = _extent_px(PATH_TTB, "square")[0] / square.unit

    canvas = canvas_size_for_aspect(aspect)
    assert _extent_px(PATH_TTB, aspect)[0] / canvas.unit == pytest.approx(
        reference, abs=TOLERANCE
    )


@pytest.mark.parametrize("aspect", ("square", "pillar", "wide"))
def test_wave_swing_still_scales_with_the_stated_amplitude(
    monkeypatch, aspect: str
):
    """T-4: the swing is drawn from the amplitude, not from the short side.

    Doubling the amplitude has to double the swing in pixels on every paper. An
    implementation that had collapsed the amplitude into a constant multiple of
    the short side would satisfy T-3 -- every canvas would agree with the square
    one -- and fail here.

    The jitter is switched off for both runs so the measured extent is the
    amplitude alone; left on, it adds a term that does not double and the ratio
    would be 1.9-something for a correct implementation.
    """
    monkeypatch.setattr(planning, "_PATH_JITTER", 0.0)

    monkeypatch.setattr(planning, "_PATH_WAVE_AMPLITUDE", 0.22)
    narrow = _extent_px(PATH_WAVE, aspect)[1]
    monkeypatch.setattr(planning, "_PATH_WAVE_AMPLITUDE", 0.44)
    wide = _extent_px(PATH_WAVE, aspect)[1]

    assert wide / narrow == pytest.approx(2.0, abs=TOLERANCE)


# --- T-5: the clusters' centres stay proportional -----------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_cluster_centres_stay_proportional(monkeypatch, aspect: str):
    """T-5: where the clumps sit follows the paper, as it did before.

    The band is switched off by taking the density radius to zero, which
    collapses every member onto its cluster's centre and leaves the centres
    readable on their own. What is asserted is the arrangement of the centres
    relative to their own middle: `_fit_group_to_anchor` moves the group as a
    whole onto the declared anchor, so the absolute coordinates carry that
    translation and the offsets do not.

    The subject follows a path, so its centres come from the `_path_pos` call
    inside `_clustered_pos` -- the site that must NOT be given the canvas. With
    `path="none"` the centres come from `_scatter_pos` and an implementation
    that wired that site up would stay green here.
    """
    monkeypatch.setattr(planning, "_density_radius", lambda density, preserve: 0.0)

    def offsets(target: str) -> list[tuple[float, float]]:
        _, points = _placed(CLUSTER_ON_PATH, target)
        cx = sum(x for x, _ in points) / len(points)
        cy = sum(y for _, y in points) / len(points)
        return [(round(x - cx, 9), round(y - cy, 9)) for x, y in points]

    assert offsets(aspect) == offsets("square")


# --- T-6: the plain scatter is left alone -------------------------------


@pytest.mark.parametrize("aspect", ASPECTS)
def test_plain_scatter_still_follows_the_paper(aspect: str):
    """T-6: a uniform scatter is not a shape, and is not levelled.

    An affine map takes a uniform distribution to a uniform distribution, so
    scattering over the whole sheet already means the same thing on every
    sheet; putting it on the short side would confine it to a square patch. The
    group's box has to come out the square canvas's box times the paper's own
    aspect.
    """
    canvas = canvas_size_for_aspect(aspect)
    square_w, square_h = _extent_px(SCATTER, "square")
    width, height = _extent_px(SCATTER, aspect)

    assert width / height == pytest.approx(
        (square_w / square_h) * (canvas.width / canvas.height), abs=TOLERANCE
    )


# --- T-7: the square canvas is untouched --------------------------------


@pytest.mark.parametrize("name", sorted(SUBJECTS))
def test_square_placement_is_the_engine_31_placement(name: str):
    """T-7, at the placement: engine 32 moves nothing on a square canvas."""
    assert _placement_digest(SUBJECTS[name], "square") == (
        ENGINE_31_SQUARE_PLACEMENT[name]
    )


@pytest.mark.parametrize("name", sorted(SUBJECTS))
@pytest.mark.parametrize("render_seed", (7, 12345))
def test_square_canvas_svg_is_byte_identical_without_the_rule(
    monkeypatch, name: str, render_seed: int
):
    """T-7, at the drawing: the whole SVG, not only where the marks land.

    Compared against the rule switched off, which is what engine 31 did here.
    The factors are exactly 1.0 on a square canvas, so the two have to agree
    byte for byte -- and a multiplication by 1.0 is not always the identity in
    floating point, which is why this is asserted rather than assumed.
    """
    score_input = {
        "version": "0.1.0", "canvas": "square", "background": "white",
        "instructions": [copy.deepcopy(SUBJECTS[name])],
    }

    def draw() -> str:
        return render(
            Score.model_validate(copy.deepcopy(score_input)),
            render_seed=render_seed,
            composition_seed=render_seed,
            svg_profile="editable",
        )

    with_rule = draw()
    monkeypatch.setattr(planning, "_short_side_scales", lambda canvas: (1.0, 1.0))
    without_rule = draw()

    assert with_rule == without_rule


# --- T-9: how much paper a layout uses is not this contract's business ---


@pytest.mark.parametrize("aspect", X_LONG)
def test_horizontal_layout_still_covers_the_stated_span(aspect: str):
    """T-9: `horizontal` covers `span` of the width, as it did at engine 31.

    Whether a layout should use the paper's long direction is [I-135] (3)-b and
    unruled; this records that engine 32 did not settle it by accident.

    Only papers whose long side is x are taken, for the same reason the gates
    above choose their papers. On the pillar the short side IS the width, so a
    `span` moved onto the short side would cover 160px of the pillar instead
    of... 160px: the gate could not fail there, and it was measured passing
    under exactly that perturbation before these papers were narrowed.
    """
    canvas = canvas_size_for_aspect(aspect)
    assert _extent_px(HORIZONTAL, aspect)[0] == pytest.approx(
        0.8 * canvas.width, abs=1e-6
    )


@pytest.mark.parametrize("aspect", Y_LONG)
def test_vertical_layout_still_covers_the_stated_span(aspect: str):
    """T-9, the other layout: `vertical` covers `span` of the height."""
    canvas = canvas_size_for_aspect(aspect)
    assert _extent_px(VERTICAL, aspect)[1] == pytest.approx(
        0.8 * canvas.height, abs=1e-6
    )
