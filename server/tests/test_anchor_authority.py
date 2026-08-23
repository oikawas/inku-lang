"""engine 20: the position of an expanded group belongs to the description.

Until engine 19 each layout branch invented its own place. 77.8% of the marks
in production never consulted the declared coordinates, so moving every stated
coordinate down moved the ink by a median of 0.0000. These six tests hold the
two things engine 20 adds -- the group meets its anchor, and it stays inside
the frame -- against the four ways of getting it wrong that were measured
before the change was written (contract section 2.6):

  (1) not moving the group at all          -> T-1
  (2) moving it but never shrinking        -> T-2
  (3) clamping the overflow onto the frame -> T-3
  (4) shrinking the whole group uniformly  -> T-4

T-5 and T-6 are the other side: a description that states no arrangement, and
one whose anchor is where the group already was, must draw engine 19's picture.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

from inku_server.render_engines.default.planning import (
    FRAME_HI,
    FRAME_LO,
    _anchor,
    _expand_arrangement,
    _expand_arrangement_layout,
    _quantise_instructions,
)
from inku_server.render_engines.default.marks import _uses_material_outline
from inku_server.renderer import render
from inku_server.schema import Instruction, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_19_MANIFEST = SERVER_ROOT / "reference" / "render-engine-19" / "manifest.json"
RENDER_SEED = 12345

# The bounding box of every G case as engine 19 laid it out, measured on
# `fa7ff4e` before the post-stage existed. T-4 compares against these because
# engine 19's radial code no longer exists in this checkout and cannot be
# re-derived from it.
ENGINE_19_SPREAD: dict[str, tuple[float, float]] = {
    "G-cluster-center": (0.6140, 0.4410),
    "G-cluster-corner": (0.6845, 0.6947),
    "G-cluster-edge": (0.3513, 0.3556),
    "G-cluster-preserve-edge": (0.2727, 0.2820),
    "G-grid-center": (0.6094, 0.6038),
    "G-grid-corner": (0.6153, 0.6092),
    "G-grid-edge": (0.6038, 0.6149),
    "G-horizontal-nopath-center": (0.8000, 0.0000),
    "G-horizontal-nopath-corner": (0.8000, 0.0000),
    "G-horizontal-nopath-edge": (0.8000, 0.0000),
    "G-path-diagonal-edge": (0.8319, 0.8418),
    "G-path-hwave-edge": (0.8000, 0.4989),
    "G-path-top_to_bottom-edge": (0.2781, 0.8000),
    "G-path-wave-center": (0.8000, 0.5063),
    "G-path-wave-corner": (0.8000, 0.4968),
    "G-path-wave-edge": (0.8000, 0.4989),
    "G-radial-center-edge": (0.5878, 0.5939),
    "G-radial-nocenter-center": (0.5878, 0.5939),
    "G-radial-nocenter-corner": (0.5878, 0.5939),
    "G-radial-nocenter-edge": (0.5878, 0.5939),
    "G-scatter-center": (0.7733, 0.7816),
    "G-scatter-corner": (0.7899, 0.7806),
    "G-scatter-dense-edge": (0.7722, 0.7762),
    "G-scatter-edge": (0.7722, 0.7762),
    "G-scatter-fade-edge": (0.7722, 0.7762),
    "G-scatter-rhythm-edge": (0.7722, 0.7762),
    "G-scatter-small-center": (0.7351, 0.4929),
    "G-scatter-small-corner": (0.2914, 0.3729),
    "G-scatter-small-edge": (0.4121, 0.4903),
    "G-vertical-nopath-center": (0.0000, 0.8000),
    "G-vertical-nopath-corner": (0.0000, 0.8000),
    "G-vertical-nopath-edge": (0.0000, 0.8000),
}


def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# engine 23 added four G cases that differ from an existing one only by the
# composition seed they state, which no test in this file reads: the score, and
# so the instruction, is the same object. Engine 19's spread was measured before
# these ids existed, so the twin borrows its base case's measurement rather than
# claiming a number nobody took.
ENGINE_23_COMPOSITION_TWINS: dict[str, str] = {
    "G-composition-cluster-center": "G-cluster-center",
    "G-composition-grid-center": "G-grid-center",
    "G-composition-path-wave-edge": "G-path-wave-edge",
    "G-composition-scatter-edge": "G-scatter-edge",
}

# engine 24 added six G cases for the fading routes the corpus never walked.
# None of them can borrow the way the twins above do: each states a score of its
# own -- another tool, another layout, a surface, a colour cycle -- so no engine
# 19 measurement covers it and none is identical to a case that has one. They
# are named rather than matched by pattern, so a case dropping out of T-4 for
# some other reason is a failure instead of an absence. T-2 and T-3 above do
# reach them: the exclusion is from the historical comparison only.
ENGINE_24_FADE_CASES: frozenset[str] = frozenset({
    "G-fade-count2-edge",
    "G-fade-cycle-edge",
    "G-fade-directional-path-edge",
    "G-fade-radial-edge",
    "G-fade-rotring-edge",
    "G-fade-surface-edge",
})

# engine 25 added four G cases for the three size rules a circle cannot reach.
# Excluded from T-4 for the same reason as the six above and one more: these are
# the only G cases that are not circles at all, so engine 19 measured neither
# the case nor its shape. Named rather than matched, for the same reason.
ENGINE_25_SIZE_CASES: frozenset[str] = frozenset({
    "G-size-ellipse-edge",
    "G-size-line-edge",
    "G-size-square-edge",
    "G-size-triangle-edge",
})

# engine 26 added four more for the angle rule -- the two shapes it turns that
# the corpus had never carried, and the two groups that state their own angle.
# Excluded from T-4 on the same grounds: engine 19 measured no `arc` or
# `cloudform` group, and none of these four existed for it to measure.
ENGINE_26_ANGLE_CASES: frozenset[str] = frozenset({
    "G-angle-arc-edge",
    "G-angle-cloudform-edge",
    "G-angle-stated-30-edge",
    "G-angle-stated-zero-edge",
})


def _g_instructions() -> dict[str, Instruction]:
    """The corpus's own group G, so the gate and the frozen cases cannot drift."""
    inputs = _generator().build_inputs()
    return {
        case_id: Score.model_validate(case["score"]).instructions[0]
        for case_id, case in sorted(inputs.items())
        if case_id.startswith("G-")
    }


def _placed(instruction: Instruction) -> list[tuple[float, float]]:
    return [_anchor(item) for item in _expand_arrangement(instruction, RENDER_SEED)]


def _laid_out(instruction: Instruction) -> list[tuple[float, float]]:
    """Where the layout branch alone would put the marks (engine 19's answer).

    Quantised like the real expansion (engine 21), so that comparing the two
    still measures what the fitting stage did rather than the rounding that
    both sides go through.
    """
    return [
        _anchor(item)
        for item in _quantise_instructions(
            _expand_arrangement_layout(instruction, RENDER_SEED)
        )
    ]


def _spread(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        max(x for x, _ in points) - min(x for x, _ in points),
        max(y for _, y in points) - min(y for _, y in points),
    )


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def _one_arrangement(anchor: list[float], **arrangement: object) -> Instruction:
    payload: dict[str, object] = {
        "count": 60, "layout": "scatter", "jitter": 0.12, "path": "none",
        "margin": 0.1,
    }
    payload.update(arrangement)
    return Instruction.model_validate(
        {
            "primitive": "circle", "center": anchor, "radius": 0.03,
            "weight": "pen", "arrangement": payload,
        }
    )


# T-1 --------------------------------------------------------------------
# Written on scatter and on vertical without a path, and on nothing else.
# `horizontal` keeps y straight from the declaration and clustering re-centres
# on it, so both already move 0.20 in engine 19: a T-1 written on those is
# green before the change and proves nothing (measured 0.2000 and 0.2143).
def test_moving_the_declared_coordinate_moves_the_group():
    for arrangement in ({}, {"layout": "vertical"}):
        high = _centroid(_placed(_one_arrangement([0.5, 0.3], **arrangement)))
        low = _centroid(_placed(_one_arrangement([0.5, 0.5], **arrangement)))
        assert low[1] - high[1] >= 0.15, arrangement

        # The same pair through the layout branch alone -- what engine 19 drew.
        # Without this the threshold above could be met by a branch that already
        # honoured the declaration, and the post-stage would go untested.
        was_high = _centroid(_laid_out(_one_arrangement([0.5, 0.3], **arrangement)))
        was_low = _centroid(_laid_out(_one_arrangement([0.5, 0.5], **arrangement)))
        assert was_low[1] - was_high[1] < 0.01, arrangement


# The frame the contract states, written out here instead of imported. T-2 used
# to read FRAME_LO/FRAME_HI from the renderer, which let the bound itself drift:
# widening it to 0.005/0.995 left T-2 green and reddened only the frozen G
# digest, and a digest is rebaked whenever the corpus is regenerated. The bound
# is part of what engine 20 promises, so the test has to say it.
CONTRACT_FRAME_LO = 0.02
CONTRACT_FRAME_HI = 0.98


def test_the_frame_is_the_one_the_contract_states():
    assert (FRAME_LO, FRAME_HI) == (CONTRACT_FRAME_LO, CONTRACT_FRAME_HI)


# T-2 --------------------------------------------------------------------
# Moving the group without shrinking it puts marks outside the frame in 25 of
# the 36 G cases (measured). Every case is checked, not only the edge scatter,
# because that is where the count of 25 comes from. It was 23 of 32 until
# engine 23 added the four composition twins: two of the cases they copy
# overflow, so they carry that over.
def test_no_placed_mark_leaves_the_frame():
    outside = {
        case_id: [
            (x, y)
            for x, y in _placed(instruction)
            if not (CONTRACT_FRAME_LO - 1e-9 <= x <= CONTRACT_FRAME_HI + 1e-9)
            or not (CONTRACT_FRAME_LO - 1e-9 <= y <= CONTRACT_FRAME_HI + 1e-9)
        ]
        for case_id, instruction in _g_instructions().items()
    }
    assert {case_id: marks for case_id, marks in outside.items() if marks} == {}

    # Not vacuous. Engine 19 never overflowed, because it never went to the
    # anchor in the first place; the overflow is created by the move. So the
    # control is the move without the shrink, which is the implementation this
    # test exists to reject. It leaves marks outside in 39 of the 50 cases
    # (35 of 46 before engine 26 added its four, 31 of 42 before engine 25
    # added its four, 25 of 36 before engine 24 added its six).
    shifted_out = 0
    for instruction in _g_instructions().values():
        points = _laid_out(instruction)
        cx, cy = _centroid(points)
        ax, ay = _anchor(instruction)
        if any(
            not (CONTRACT_FRAME_LO <= x - cx + ax <= CONTRACT_FRAME_HI)
            or not (CONTRACT_FRAME_LO <= y - cy + ay <= CONTRACT_FRAME_HI)
            for x, y in points
        ):
            shifted_out += 1
    assert shifted_out == 39


# T-3 --------------------------------------------------------------------
# Restricted to the scatter edge case. Clamping the overflow onto the frame
# piles 8 marks onto shared coordinates there. It cannot be written for every
# layout: radial's first and last mark share a point by construction, so four G
# cases carry a pile-up in engine 19 already and an unconditional form of this
# test would fail a correct implementation.
def test_the_frame_correction_does_not_stack_marks_on_the_edge():
    points = _placed(_one_arrangement([0.85, 0.85]))
    rounded = [(round(x, 6), round(y, 6)) for x, y in points]
    assert len(rounded) == len(set(rounded))
    assert len(points) == 60


# T-4 --------------------------------------------------------------------
# The threshold is 0.5 and not 0.3. A uniform similarity shrink -- the obvious
# alternative to shrinking each side on its own -- leaves a worst spread ratio
# of 0.315, which passes at 0.3 and proves nothing. R5's worst is 0.660.
def test_the_frame_correction_does_not_collapse_a_group():
    ratios: dict[str, float] = {}
    instructions = _g_instructions()
    unmeasured = (
        ENGINE_24_FADE_CASES | ENGINE_25_SIZE_CASES | ENGINE_26_ANGLE_CASES
    ) & set(instructions)
    assert len(unmeasured) == 14
    for case_id, instruction in instructions.items():
        if case_id in unmeasured:
            continue
        width, height = _spread(_placed(instruction))
        base_id = ENGINE_23_COMPOSITION_TWINS.get(case_id, case_id)
        assert instructions[base_id] == instruction, case_id
        was_width, was_height = ENGINE_19_SPREAD[base_id]
        ratios[case_id] = min(
            width / was_width if was_width else 1.0,
            height / was_height if was_height else 1.0,
        )
    worst = min(ratios.values())
    assert worst >= 0.5, sorted(ratios.items(), key=lambda item: item[1])[:3]
    # Not vacuous: something really is being shrunk, so a change that stopped
    # correcting overflow altogether would not slip past this test as "green".
    assert worst <= 0.75, worst


# T-5 --------------------------------------------------------------------
# The 32 cases of A-F that render engine 22 was authorised to move: the fill
# layer. Every one of them states `filled` and no arrangement, and the branch
# they moved into is gated in `test_fill_underlay_and_branch.py`. They are
# listed rather than matched by pattern so that a case moving for some OTHER
# reason still fails this test -- a pattern would quietly absorb it.
ENGINE_22_FILL_CASES = frozenset({
    "C-fill-circle-brush_thick", "C-fill-circle-crayon", "C-fill-circle-pencil",
    "C-fill-ellipse-brush_thick", "C-fill-ellipse-crayon", "C-fill-ellipse-pencil",
    "C-fill-polygon-brush_thick", "C-fill-polygon-crayon", "C-fill-polygon-pencil",
    "C-fill-square-brush_thick", "C-fill-square-crayon", "C-fill-square-pencil",
    "C-fill-triangle-brush_thick", "C-fill-triangle-crayon", "C-fill-triangle-pencil",
    "C-tinyfill-boundary-pen", "D-size-large-filled-polygon",
    "E-wild-fill-circle-brush_thick", "E-wild-fill-circle-crayon",
    "E-wild-fill-circle-pencil", "E-wild-fill-ellipse-brush_thick",
    "E-wild-fill-ellipse-crayon", "E-wild-fill-ellipse-pencil",
    "E-wild-fill-polygon-brush_thick", "E-wild-fill-polygon-crayon",
    "E-wild-fill-polygon-pencil", "E-wild-fill-square-brush_thick",
    "E-wild-fill-square-crayon", "E-wild-fill-square-pencil",
    "E-wild-fill-triangle-brush_thick", "E-wild-fill-triangle-crayon",
    "E-wild-fill-triangle-pencil",
})

# The 14 that moved for a DIFFERENT reason, and so are listed apart from the
# fill cases rather than folded in with them. "For chalk, raise the amount of
# skipping on the line side" (author, 2026-08-07) is not a fill ruling: it
# raises how hard the sheet refuses that one tool, which reaches every chalk
# stroke in the corpus, filled or not. Every one of them is chalk, and no other
# tool moved -- that is what makes this an authorised exception rather than a
# leak. The amount is gated in `test_fill_underlay_and_branch.py` (T-22).
ENGINE_22_CHALK_CASES = frozenset({
    "A-chalk-arc", "A-chalk-circle", "A-chalk-cloudform", "A-chalk-ellipse",
    "A-chalk-line", "A-chalk-square", "A-chalk-triangle",
    "E-wild-chalk-arc", "E-wild-chalk-circle", "E-wild-chalk-cloudform",
    "E-wild-chalk-ellipse", "E-wild-chalk-line", "E-wild-chalk-square",
    "E-wild-chalk-triangle",
})


# The 3 that render engine 30 was authorised to move, listed for the same reason
# the two sets above are: a case moving for any OTHER reason must still fail.
# Engine 30 stopped turning `size` into pixels through `width` and `height`
# separately, so a mark keeps the proportion its description gave it on every
# canvas. On a square canvas the two rules are the same arithmetic, which is why
# only the non-square members of `D-canvas-*` are here -- and only the ones
# drawn from `size`: the corpus's other non-square cases state `radius` or two
# endpoints, and engine 30 does not reach either.
ENGINE_30_ASPECT_CASES = frozenset({
    "D-canvas-pillar-filled-square-rotring",
    "D-canvas-vertical-filled-square-rotring",
    "D-canvas-wide-filled-square-rotring",
})


def test_a_score_without_an_arrangement_is_engine_19():
    """The cases of A-F state no arrangement and must be byte-identical.

    They are also the reason group G exists: no case in the frozen corpus
    reaches `_expand_arrangement` at all, so all of engine 20 could be deleted
    and this test alone would still pass.

    Engine 22 rebuilt the fill layer, so the 32 filled cases of A-F are no
    longer engine 19 and are excluded by name, and it raised how hard the sheet
    refuses chalk, which excludes 14 more.

    Engine 28 is a larger exception and is stated as a rule rather than a list.
    The material layer no longer draws itself on the ideal geometry, and the
    wobble is measured in stroke widths -- so every case drawn with a tool that
    has a material layer moved, which is 401 of the 493. What is left is the 92
    the change cannot reach: `burin`, `drypoint`, `silverpoint`, `rotring` and
    `computer` have no material layer at all, and no case here has a variation.

    Engine 30 is a third exception, of three cases: it stopped scaling `size`
    by `width` and `height` separately, so the three non-square canvases in the
    corpus that draw a mark from `size` moved. All three are drafting-pen fills,
    which is why they survived the engine 22 and 28 exceptions to be caught here.

    **The claim is thinner than it was**: 447 cases carried "a score with no
    arrangement is untouched by everything the layout work added", 92 carried it
    after engine 28, and 89 carry it now. The layout work is still what is being
    tested -- none of engine 20's expander runs on these -- but the byte-identity
    evidence for it is a fifth of what it was. That is worth a ledger entry, not
    a silent edit.
    """
    generator = _generator()
    frozen = json.loads(ENGINE_19_MANIFEST.read_text(encoding="utf-8"))["cases"]
    assert len(frozen) == 493
    assert ENGINE_22_FILL_CASES <= set(frozen)
    assert ENGINE_22_CHALK_CASES <= set(frozen)
    assert ENGINE_30_ASPECT_CASES <= set(frozen)
    assert not (ENGINE_22_FILL_CASES & ENGINE_22_CHALK_CASES)
    assert not (ENGINE_30_ASPECT_CASES & ENGINE_22_CHALK_CASES)
    # 除外の理由が名前と一致していること。塗りでない case が塗りの札で
    # 抜けたり、chalk でない case が chalk の札で抜けたりしない。
    assert all("fill" in case_id for case_id in ENGINE_22_FILL_CASES)
    assert all("chalk" in case_id for case_id in ENGINE_22_CHALK_CASES)
    # 比の札で抜けるのは、正方形でないキャンバスの case だけ。比は case 名の
    # 3 番目の区切りにある ("D-canvas-pillar-filled-square-rotring" の pillar)。
    assert all(case_id.startswith("D-canvas-") for case_id in ENGINE_30_ASPECT_CASES)
    assert all(
        case_id.split("-")[2] != "square" for case_id in ENGINE_30_ASPECT_CASES
    )
    checked = 0
    for case_id, case in frozen.items():
        render_input = case["input"]
        assert render_input["score"]["instructions"][0]["arrangement"] is None
        if case_id in ENGINE_22_FILL_CASES or case_id in ENGINE_22_CHALK_CASES:
            continue
        if case_id in ENGINE_30_ASPECT_CASES:
            continue
        if _uses_material_outline(render_input["score"]["instructions"][0]["weight"]):
            continue
        svg = render(
            Score.model_validate(render_input["score"]),
            color_map=render_input["color_map"],
            catalog_id=render_input["catalog_id"],
            render_seed=render_input["render_seed"],
            svg_profile=render_input["svg_profile"],
            wild=render_input["wild"],
        )
        assert generator._normalized_digest(svg) == case["digest"], case_id
        checked += 1
    assert checked == 89


# T-6 --------------------------------------------------------------------
def test_a_group_already_on_its_anchor_is_left_alone():
    """An anchor the group already meets must not move the picture.

    The two `-nopath-center` cases are the whole of it: those branches keep one
    axis from the declaration, and with the anchor at the middle the other axis
    already averages there too. Their edge siblings are the control -- if they
    held still as well, this would only be saying that the post-stage does
    nothing.
    """
    instructions = _g_instructions()
    for layout in ("vertical", "horizontal"):
        still = instructions[f"G-{layout}-nopath-center"]
        assert _placed(still) == _laid_out(still)

        moved = instructions[f"G-{layout}-nopath-edge"]
        assert _placed(moved) != _laid_out(moved)


def test_a_grid_keeps_the_region_the_description_gave_it():
    """`at.region` is a stated position, and the post-stage must not overrule it.

    A grid is the one branch that reads `at` itself, so for those instructions
    `at` survives performance resolution instead of being folded into the
    anchor. Fitting the tiles onto the shape's own centre would move the group
    out of the region the description asked for.
    """
    instruction = Instruction.model_validate(
        {
            "primitive": "circle", "center": [0.5, 0.5], "radius": 0.01,
            "at": {"region": [0.1, 0.2, 0.5, 0.8]},
            "arrangement": {"count": 4, "layout": "grid", "rows": 2, "cols": 2,
                            "jitter": 0.0},
        }
    )
    points = _placed(instruction)
    assert len(points) == 4
    assert all(0.1 <= x <= 0.5 and 0.2 <= y <= 0.8 for x, y in points)
    assert points == _laid_out(instruction)
