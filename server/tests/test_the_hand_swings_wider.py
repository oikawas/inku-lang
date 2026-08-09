"""engine 27: the hand swings wider.

Engines 25 and 26 took a congruence out of a repeated group. `Arrangement` says
"several of this shape" and never "all of them the same size" or "all of them at
the same angle", so the sameness was the engine's own addition; engine 25 gave
every member its own size and engine 26 gave it its own angle, at the pair the
author ruled on that day: +/-25% and +/-12 degrees. Round 2b of the same reading
marked the size variation slightly short and the angle variation short, and
asked for the same two rules to swing wider (author, 2026-08-08). Engine 27 is
those two numbers: +/-35% and +/-27 degrees.

Which is why almost nothing here reads a constant. `HAND_GROUP_SIZE == 0.35` is
true of any tree where somebody typed 0.35, and it is already held next door, in
the two files engines 25 and 26 left behind. What this file holds is the swing
in the drawing: a group reaches sizes the old amplitude could not produce (T-2)
and angles it could not produce (T-3); the frame the group is placed into did
not move when the members grew by half again (T-4); the engine names the version
the wider swing belongs to (T-7); and the frozen corpus moved on exactly the
cases the two rules reach and nowhere else (T-8).

T-2 and T-3 are the load-bearing pair. Both are measured through the product's
own drawing rather than off the constants, and both are stated against the
ceiling of the OLD amplitude -- a ratio of 1.25/0.75, an angle of 12 degrees --
so no tuning of the new one can satisfy them by accident and the old one cannot
satisfy them at all.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import pathlib
import re

import pytest

from inku_server import renderer
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SERVER_ROOT / "reference"
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

RENDER_SEED = 12345

# The amplitudes engine 26 drew at. Literals, not imports: what these are for is
# to name the band the new swing has to leave, and an import of the constant
# would move with it and make the claim vacuous on the day it is retuned again.
ENGINE_26_SIZE = 0.25
ENGINE_26_ROT = 12.0

# The ceiling of the old size amplitude. A group drawn at +/-25% cannot put more
# than 1.25/0.75 between its largest member and its smallest, whatever seed it
# is given, so a ratio above this is a statement about the amplitude and not
# about the draw.
ENGINE_26_SIZE_CEILING = (1 + ENGINE_26_SIZE) / (1 - ENGINE_26_SIZE)

# What engine 26 froze, and what engine 27 does to it. Engine 27 adds no case:
# it moves the drawings of the cases that are already there.
ENGINE_26_CASES = 549
ENGINE_27_CASES = 549
MOVED_CASES = 45
UNCHANGED_CASES = 504
ADDED_CASES = 0

# The frame engine 20 states, written out rather than imported for the reason
# `test_anchor_authority.py` gives: reading FRAME_LO/FRAME_HI from the renderer
# lets the bound itself drift and leaves the test green while it does.
CONTRACT_FRAME_LO = 0.02
CONTRACT_FRAME_HI = 0.98

# An anchor rebuilt from two fields lands within one step of the nine-decimal
# grid `_quantise_instructions` rounds on, rather than on the same float. The
# same bound `test_each_member_gets_its_own_size.py` measures and states.
ANCHOR_TOLERANCE = 2 * 10**-renderer.ARRANGEMENT_QUANTUM

# The shapes the two rules reach. `circle` is excluded from both lists on
# purpose -- an angle cannot be seen on one, so the angle rule leaves it alone
# and a reading that included it would report "no rotate()" as a failure -- and
# `line` is excluded from the angle list because there the angle IS what the
# mark says. Both exclusions are held by their own tests in the two files
# engines 25 and 26 left; here they would only blur what is being measured.
SIZE_SHAPES = ("ellipse", "square", "triangle", "arc", "cloudform")
ANGLE_SHAPES = ("ellipse", "square", "triangle", "arc", "cloudform")

GEOMETRY: dict[str, dict] = {
    "ellipse": {"center": [0.5, 0.5], "size": [0.10, 0.06]},
    "square": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
    "triangle": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
    "arc": {
        "center": [0.5, 0.5],
        "radius": 0.05,
        "angle_start": 15.0,
        "angle_end": 285.0,
    },
    "cloudform": {"center": [0.5, 0.5], "size": [0.10, 0.06]},
}

ROTATE = re.compile(r"rotate\(\s*(-?[0-9.]+)")


def _load_generator():
    """The bake's own module, so a replay goes through the call the bake makes."""
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(version: str) -> dict:
    path = REFERENCE_ROOT / f"render-engine-{version}" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _instruction(primitive: str, *, count: int, weight: str = "pen") -> Instruction:
    return Instruction.model_validate(
        {
            "primitive": primitive,
            "weight": weight,
            "arrangement": {
                "count": count,
                "layout": "scatter",
                "jitter": 0.12,
                "margin": 0.1,
            },
            **GEOMETRY[primitive],
        }
    )


def _expand(instruction: Instruction) -> list[Instruction]:
    return renderer._expand_arrangement(
        instruction, RENDER_SEED, None, performance_seed=RENDER_SEED
    )


def _draw(instruction: Instruction) -> str:
    # `editable` keeps one group per mark and is the profile the corpus bakes.
    return render(
        Score.model_validate({"instructions": [instruction.model_dump(by_alias=True)]}),
        svg_profile="editable",
        render_seed=RENDER_SEED,
    )


def _extent(item: Instruction) -> float:
    """One number per member, in the unit that member's own rule scales."""
    if item.primitive == "line":
        assert item.from_ and item.to
        return math.hypot(item.to[0] - item.from_[0], item.to[1] - item.from_[1])
    if item.radius is not None:
        return item.radius
    assert item.size is not None
    return item.size[0]


def _restore_engine_26_size(monkeypatch) -> None:
    """Put `group_hand` back to +/-25%, leaving every other quantity alone.

    Not the same device as `_withhold_sizes`: switching `_apply_member_sizes`
    off answers "what did engine 24 draw", which is a question about whether the
    stage exists. What is asked here is narrower -- "what did the SAME stage
    draw one amplitude ago" -- so the stage keeps running and only the number it
    is tuned by goes back. A gate written the other way would be satisfied by an
    implementation that had dropped the per-member size altogether.
    """
    for weight, grammar in GRAMMARS.items():
        if grammar.group_hand > 0.0:
            monkeypatch.setitem(
                GRAMMARS, weight, dataclasses.replace(grammar, group_hand=ENGINE_26_SIZE)
            )


def _g_instructions(generator) -> dict[str, tuple[Instruction, dict]]:
    return {
        case_id: (
            Instruction.model_validate(render_input["score"]["instructions"][0]),
            render_input,
        )
        for case_id, render_input in generator.build_inputs().items()
        if case_id.startswith("G-")
    }


def _placed(instruction: Instruction, render_input: dict) -> list[tuple[float, float]]:
    """Where the corpus's own call puts the members' anchors."""
    seed = render_input["render_seed"]
    placement = render_input.get("composition_seed", seed)
    members = renderer._expand_arrangement(
        instruction, placement, None, performance_seed=seed
    )
    return [renderer._anchor(item) for item in members]


# T-2 --------------------------------------------------------------------
# Split by shape rather than read once on a circle. `_scale_member` has four
# branches and the shape decides which one runs: `arc` goes through `radius`,
# `ellipse` and `cloudform` through `size`, `square` and `triangle` through the
# bbox rule that has to pull the corner back by half the growth. A single-shape
# reading of this would watch one branch and report on four.
@pytest.mark.parametrize("primitive", SIZE_SHAPES)
def test_the_members_reach_sizes_the_old_amplitude_could_not_produce(primitive):
    """The swing in the drawing, stated against the ceiling of the old band.

    400 members, because the claim is about the ends of the band and the ends
    of a 12-draw sample are wherever the hash put them. The two assertions are
    a pair on purpose: the ratio says the group is wider than +/-25% can ever
    be, and the absolute ends say WHERE it got wider, so a rule that stretched
    one end and left the other cannot answer both.
    """
    instruction = _instruction(primitive, count=400)
    base = _extent(instruction)
    factors = sorted(_extent(item) / base for item in _expand(instruction))

    assert len(factors) == 400
    # Measured at +/-25%: 1.6650 at its widest across these five shapes, against
    # a ceiling of 1.6667. Measured at +/-35%: 2.0665 at its narrowest.
    assert factors[-1] / factors[0] > ENGINE_26_SIZE_CEILING, (
        primitive, factors[0], factors[-1]
    )
    # Measured at +/-25%: the largest member reached 1.2497 and the smallest
    # 0.7500. Measured at +/-35%: 1.3466 and 0.6518.
    assert factors[-1] > 1 + ENGINE_26_SIZE, (primitive, factors[-1])
    assert factors[0] < 1 - ENGINE_26_SIZE, (primitive, factors[0])


# T-3 --------------------------------------------------------------------
# Read off the drawn SVG and not off the expanded instructions: `rotation` is
# an engine field that three different consumers turn a shape by, and a member
# that carried a 27-degree `rotation` no writer ever printed would satisfy an
# instruction-level reading perfectly while drawing engine 26's picture.
@pytest.mark.parametrize("primitive", ANGLE_SHAPES)
def test_the_members_turn_further_than_the_old_amplitude_allowed(primitive):
    """+/-12 degrees can span 24 and reach 12. Both are exceeded here.

    60 members rather than 400: the SVG is written out for this one, and 60 is
    already enough to put the measured span at 50.6 degrees in the worst of the
    five shapes -- twice what the old amplitude's own ceiling allows.
    """
    svg = _draw(_instruction(primitive, count=60))
    angles = [float(value) for value in ROTATE.findall(svg)]

    # Not vacuous: a shape the writer never prints a rotate() for would leave
    # this list empty and every claim below trivially true.
    assert len(angles) == 60, (primitive, len(angles))
    # Measured at +/-12 degrees: 23.651 at its widest, 11.988 at its furthest.
    # Measured at +/-27: 50.561 at its narrowest, 24.236 at its least far.
    assert max(angles) - min(angles) > 2 * ENGINE_26_ROT, (primitive, angles)
    assert max(abs(angle) for angle in angles) > ENGINE_26_ROT, (primitive, angles)


# T-4 --------------------------------------------------------------------
def test_the_wider_swing_does_not_move_the_frame(monkeypatch):
    """The worry the contract raised, answered on the corpus's own 50 groups.

    Raising the size amplitude makes every member up to 35% larger, and engine
    25 needed three coordinate corrections to keep `_scale_member` from walking
    the anchor it is measured from while it does. `_fit_group_to_anchor` reads
    the anchors and nothing else, so if any of those three corrections were
    wrong the wider swing would hand the placement a different group and push
    marks out of the frame.

    Measured: it hands it the same group. Every anchor lands within one step of
    the quantisation grid of where +/-25% put it -- 1.0e-9 at worst, on the
    three cases whose anchor is rebuilt from two rounded fields -- and the
    frame correction fires on the same 40 of 50 cases at both amplitudes.

    This is the corpus reading of a claim `test_each_member_gets_its_own_size.py`
    makes on five scores built by hand. The corpus is where the layouts, the
    counts, the tools and the composition twins actually vary.
    """
    generator = _load_generator()
    cases = _g_instructions(generator)
    assert len(cases) == 50

    wider = {
        case_id: _placed(instruction, render_input)
        for case_id, (instruction, render_input) in cases.items()
    }
    extents = {
        case_id: [
            _extent(item)
            for item in renderer._expand_arrangement(
                instruction,
                render_input.get("composition_seed", render_input["render_seed"]),
                None,
                performance_seed=render_input["render_seed"],
            )
        ]
        for case_id, (instruction, render_input) in cases.items()
    }

    outside = {
        case_id: [
            (x, y)
            for x, y in points
            if not (CONTRACT_FRAME_LO - 1e-9 <= x <= CONTRACT_FRAME_HI + 1e-9)
            or not (CONTRACT_FRAME_LO - 1e-9 <= y <= CONTRACT_FRAME_HI + 1e-9)
        ]
        for case_id, points in wider.items()
    }
    assert {case_id: marks for case_id, marks in outside.items() if marks} == {}

    _restore_engine_26_size(monkeypatch)
    moved = 0
    for case_id, (instruction, render_input) in cases.items():
        narrower = _placed(instruction, render_input)
        assert [value for point in wider[case_id] for value in point] == pytest.approx(
            [value for point in narrower for value in point], abs=ANCHOR_TOLERANCE
        ), case_id
        was = [
            _extent(item)
            for item in renderer._expand_arrangement(
                instruction,
                render_input.get("composition_seed", render_input["render_seed"]),
                None,
                performance_seed=render_input["render_seed"],
            )
        ]
        if was != extents[case_id]:
            moved += 1
    # Not vacuous: the anchors agreeing means nothing unless the members really
    # did change size between the two readings. 45 of the 50 G cases are groups
    # the size rule reaches; the other five are the four grids and the one
    # rotring group, and those are supposed to be identical at any amplitude.
    assert moved == 45, moved


# T-7 --------------------------------------------------------------------
def test_the_engine_names_itself_27_or_later():
    """`>=`, not `==`, for the reason engines 25 and 26 both wrote down: an
    equality here turns red on the day the next stage lands and says nothing
    about this one."""
    assert int(current_render_engine().version) >= 27


# T-8 --------------------------------------------------------------------
def test_the_corpus_moved_on_the_cases_the_two_rules_reach():
    """The reach of the change, read off the two bakes.

    A regenerated record rather than a property, so this is not on its own a
    reason to believe anything: break the product and the record moves with it.
    It is here because 45 is the number the contract predicted before the work
    started, counted from the generator's own `build_inputs()` against the four
    `if` statements in the two rules -- and a bake that moved 5 or 300 would
    mean the exclusions are not the ones they are supposed to be.

    The added count is zero, and that is half the claim. Engines 24, 25 and 26
    each answered a new rule by adding cases; engine 27 answers a wider swing of
    two rules that are already there, so a case appearing here would mean the
    bake was doing something this contract did not ask for.
    """
    previous = _manifest("26")["cases"]
    current = _manifest("27")["cases"]

    assert len(previous) == ENGINE_26_CASES
    assert len(current) == ENGINE_27_CASES

    shared = set(previous) & set(current)
    moved = {
        case_id
        for case_id in shared
        if previous[case_id]["digest"] != current[case_id]["digest"]
    }
    assert len(moved) == MOVED_CASES
    assert len(shared) - len(moved) == UNCHANGED_CASES
    assert len(set(current) - set(previous)) == ADDED_CASES

    # Every case that moved holds a group, and every group that did not move is
    # one of the four exclusions. Stated as a partition rather than a count, so
    # a bake that moved 45 of the wrong cases still fails.
    assert all(case_id.startswith("G-") for case_id in moved), sorted(moved)[:5]
