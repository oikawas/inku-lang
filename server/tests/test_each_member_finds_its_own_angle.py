"""engine 26: each member of a group finds its own angle.

The other half of the pair engine 25 began. `Arrangement` is the declaration
"several of this shape"; it no more says "all of them at the same angle" than it
says "all of them the same size", and until here the expander answered it by
rewriting coordinates and nothing else, so the N members came out sharing one
angle. +/-25% and +/-12 degrees were ruled on together (author, 2026-08-08) and
the second amplitude arrives here.

This stage is narrower than either before it, and narrow by ruling rather than
by accident. It reaches 17.5% of production's groups and 18.2% of its expanded
marks, because five kinds of group are left exactly as they were. Three of the
five are what the ruling is about, and they carry the weight of these tests: a
`line`, where the angle is what the mark says (T-6); a group that states
`rotation`, where the description has already answered the question (T-4, T-5);
and a `circle`, where an angle cannot be seen at all and turning one would move
nothing but the performance seed (T-7). `grid` (T-8) and the machine tools
(T-3) carry over from engine 25.

T-4 is the one that costs something to get wrong. The exclusion is `is not
None` and not `if ins.rotation:`, because `rotation: 0` is an answer -- "do not
tilt these" -- and 141 groups in production give it. Under a truthy test those
141 alone would turn, silently, and every other test here would stay green.

The rest hold the change to its own quantity. The angle is drawn from the same
performance seed the size reads, so a composition seed still moves only where
the marks land (T-10, set as a pair because either half alone passes an
implementation that has dropped the angle to a constant); every consumer of
`rotation` turns the shape about `_anchor(ins)`, so no anchor moves (T-9); and
engine 25's sizes and engine 24's fade ceilings arrive untouched (T-11).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import statistics

import pytest

from inku_server import renderer
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS, HAND_GROUP_ROT

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SERVER_ROOT / "reference"
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

RENDER_SEED = 12345
COMPOSITION_SEED = 777

# The ruling (author, 2026-08-08): +/-12 degrees, one amplitude for every hand
# tool, stated as the pair "+/-25% and +/-12 degrees".
AMPLITUDE = 12.0

# What engine 25 froze, and what engine 26 does to it. The three that move are
# the ellipse, square and triangle groups engine 25 itself added: they are the
# only hand-tool groups in the corpus that are neither circles nor lines.
ENGINE_25_CASES = 545
ENGINE_25_G_CASES = 46
ENGINE_26_CASES = 549
MOVED_CASES = 3
UNCHANGED_CASES = 542
ADDED_CASES = 4

# The four cases engine 26 adds, in the two opposite roles.
TURNED_CASES = ("G-angle-arc-edge", "G-angle-cloudform-edge")
STATED_CASES = ("G-angle-stated-zero-edge", "G-angle-stated-30-edge")

# Same bound and same reason as engine 25's: an anchor rebuilt from `position`
# and `size`, or from a line's two ends, is recovered through two coordinates
# `_quantise_instructions` rounds independently.
ANCHOR_TOLERANCE = 2 * 10 ** -renderer.ARRANGEMENT_QUANTUM

# The five shapes the rule turns, in the order production ranks them: `arc` 377
# groups, `ellipse` 373, `square` 215, `triangle` 98, `cloudform` 64. `line` and
# `circle` are excluded by ruling and by visibility, so they are absent here on
# purpose and are watched by T-6 and T-7 instead.
TURNED_SHAPES = ("arc", "ellipse", "square", "triangle", "cloudform")

GEOMETRY: dict[str, dict] = {
    "arc": {"center": [0.5, 0.5], "radius": 0.06,
            "angle_start": 15.0, "angle_end": 285.0},
    "circle": {"center": [0.5, 0.5], "radius": 0.03},
    "cloudform": {"center": [0.5, 0.5], "size": [0.10, 0.06]},
    "ellipse": {"center": [0.5, 0.5], "size": [0.10, 0.06]},
    "line": {"from": [0.46, 0.48], "to": [0.54, 0.52]},
    "square": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
    "triangle": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
}


def _manifest(version: str) -> dict:
    path = REFERENCE_ROOT / f"render-engine-{version}" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_generator():
    """The bake's own module, so a replay goes through the call the bake makes."""
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _instruction(
    *,
    primitive: str = "ellipse",
    weight: str = "pen",
    rotation: float | None = None,
    **arrangement,
) -> Instruction:
    """One group. `ellipse` by default: it is the shape the rule turns that the
    corpus and production both carry most, and -- unlike `circle` -- an angle
    can be seen on it. A gate here that reached for a circle would measure
    nothing, which is the mistake engine 25's own gates made four times."""
    arr = {"count": 12, "layout": "scatter", "jitter": 0.12, "margin": 0.1}
    arr.update(arrangement)
    return Instruction.model_validate(
        {
            "primitive": primitive,
            "weight": weight,
            "rotation": rotation,
            "arrangement": arr,
            **GEOMETRY[primitive],
        }
    )


def _expand(instruction: Instruction, *, placement=None, performance=RENDER_SEED):
    """The product call, with both seeds stated."""
    return renderer._expand_arrangement(
        instruction,
        RENDER_SEED if placement is None else placement,
        None,
        performance_seed=performance,
    )


def _withhold_rotations(monkeypatch) -> None:
    """Draw as engine 25 did: the group expands, and every member shares an angle.

    Engine 26 is engine 25 plus this one step, so neutralising it is how a test
    reads engine 25's answer out of the engine that is installed -- the same
    device engine 25's gates used to read engine 24's, and engine 24's to read
    engine 23's.
    """
    monkeypatch.setattr(
        renderer, "_apply_member_rotations", lambda items, arr, member_seed: items
    )


def _draw(instruction: Instruction, **kwargs) -> str:
    # `editable` keeps one group per mark and is the profile the corpus bakes.
    kwargs.setdefault("render_seed", RENDER_SEED)
    return render(
        Score.model_validate({"instructions": [instruction.model_dump(by_alias=True)]}),
        svg_profile="editable",
        **kwargs,
    )


def _assert_unchanged_from_engine_25(monkeypatch, instruction: Instruction) -> None:
    """This group is drawn byte for byte as engine 25 drew it.

    Paired with its own control every time it is used: a claim that a drawing
    did not move is worth nothing unless something in the same test shows that
    the step being withheld moves a drawing at all.
    """
    engine_26 = _draw(instruction)
    control_26 = _draw(_instruction(count=instruction.arrangement.count))
    _withhold_rotations(monkeypatch)
    assert _draw(instruction) == engine_26
    assert _draw(_instruction(count=instruction.arrangement.count)) != control_26


def _members_through_render(monkeypatch, instruction: Instruction, **kwargs):
    """The members as they leave the expander, on the product's own render path.

    `_expand_arrangement` can be called directly, and most tests here do -- but
    which seed reaches it is decided by `render`, one call further out. A gate
    that only ever calls the expander states both seeds by hand and so cannot
    see the caller stop passing one, or start passing the other.
    """
    captured: list[list[Instruction]] = []
    original = renderer._apply_member_rotations

    def spy(items, arr, member_seed):
        turned = original(items, arr, member_seed)
        captured.append(turned)
        return turned

    monkeypatch.setattr(renderer, "_apply_member_rotations", spy)
    _draw(instruction, **kwargs)
    assert len(captured) == 1
    return captured[0]


def _anchors(items: list[Instruction]) -> list[float]:
    """Every member's anchor, flattened: `pytest.approx` compares numbers."""
    return [value for item in items for value in renderer._anchor(item)]


def _extents(items: list[Instruction]) -> list[float]:
    """One size number per member, in the field that member's own rule scales."""
    return [
        item.radius if item.radius is not None else item.size[0]
        for item in items
    ]


def _fade_levels(items: list[Instruction]) -> list[str]:
    return [
        match.group(0) if (match := re.search(r"fade_level=[\d.]+", item.color_hint or "")) else ""
        for item in items
    ]


# T-1 ---------------------------------------------------------------------
def test_the_members_of_a_group_differ_in_angle():
    """Measured on the drawing, not on the instructions: the claim is that the
    marks come out at different angles, and `rotation` is only how they get
    there. An ellipse, because a circle prints no `rotate(` however it is
    turned -- which is exactly why the rule leaves circles alone."""
    svg = _draw(_instruction(count=12))
    angles = [float(value) for value in re.findall(r"rotate\((-?[\d.]+)", svg)]

    assert len(angles) == 12
    assert len(set(angles)) == 12
    assert statistics.pstdev(angles) > 1.0


# T-2 ---------------------------------------------------------------------
def test_the_amplitude_is_the_one_that_was_ruled_on():
    """Two claims, and both are needed. Nothing leaves +/-12 degrees, and the
    ends are reached -- a rule that turned every member by a degree would keep
    the first claim perfectly.

    200 members rather than 12: the draw is a hash, so a dozen samples land
    where they land. At 200 the extremes come within 0.2 of the ends."""
    items = _expand(_instruction(count=200))
    angles = [item.rotation for item in items]

    assert min(angles) >= -AMPLITUDE and max(angles) <= AMPLITUDE
    assert min(angles) < -AMPLITUDE + 0.5
    assert max(angles) > AMPLITUDE - 0.5
    assert HAND_GROUP_ROT == AMPLITUDE


# T-3 ---------------------------------------------------------------------
@pytest.mark.parametrize("weight", ["rotring", "computer"])
def test_the_machine_tools_keep_their_exact_angle(weight, monkeypatch):
    """Exact repetition is the machine's signature, not a defect to sand off.
    Pinned in the grammar by a `group_rot` of zero, the way `group_hand` and
    `fill_hand` are, rather than derived from anything.

    The pair with T-1: the same group, the same count, the same layout, and the
    only difference is the tool."""
    assert GRAMMARS[weight].group_rot == 0.0

    items = _expand(_instruction(weight=weight, count=12))
    assert {item.rotation for item in items} == {None}

    _assert_unchanged_from_engine_25(monkeypatch, _instruction(weight=weight, count=12))


# T-4 ---------------------------------------------------------------------
def test_a_group_that_states_a_zero_angle_is_untouched(monkeypatch):
    """The one test that separates `is not None` from `if ins.rotation:`.

    `rotation: 0` is an answer and not a missing one: the description said "do
    not tilt these". 2,135 groups in production state an angle and 141 of them
    state zero, and under a truthy test those 141 -- and only those 141 -- would
    turn. Every other gate in this file stays green while that happens, which is
    why the case is written out here and added to the corpus as well."""
    stated = _instruction(rotation=0.0, count=12)
    assert stated.rotation is not None and not stated.rotation

    items = _expand(stated)
    assert {item.rotation for item in items} == {0.0}

    _assert_unchanged_from_engine_25(monkeypatch, stated)


# T-5 ---------------------------------------------------------------------
def test_a_group_that_states_an_angle_is_untouched(monkeypatch):
    """The ruling itself (author, 2026-08-08): start where the description has
    not already spoken. A member that drifted off a stated 30 degrees would be
    the engine overruling the score."""
    stated = _instruction(rotation=30.0, count=12)

    items = _expand(stated)
    assert {item.rotation for item in items} == {30.0}

    _assert_unchanged_from_engine_25(monkeypatch, stated)


# T-6 ---------------------------------------------------------------------
def test_a_line_group_is_untouched(monkeypatch):
    """The ruling (author, 2026-08-08): on a line the angle is what the mark
    says. Tilting the blades tips the grass over, so a line's angle belongs to
    the description in a way an ellipse's does not."""
    items = _expand(_instruction(primitive="line", count=12))
    assert {item.rotation for item in items} == {None}

    _assert_unchanged_from_engine_25(monkeypatch, _instruction(primitive="line", count=12))


# T-7 ---------------------------------------------------------------------
def test_a_circle_group_is_untouched(monkeypatch):
    """A circle looks the same at every angle, so turning one changes no pixel.
    What it would change is the performance seed, which hashes the whole
    instruction dump -- the worse half of both outcomes, and the reason the
    sample sheets excluded circles too."""
    items = _expand(_instruction(primitive="circle", count=12))
    assert {item.rotation for item in items} == {None}

    _assert_unchanged_from_engine_25(
        monkeypatch, _instruction(primitive="circle", count=12)
    )


# T-8 ---------------------------------------------------------------------
def test_a_grid_is_untouched(monkeypatch):
    """A grid is the tiling whose point is that the cells match (author ruling,
    2026-08-08). Carried over from engine 25 unchanged."""
    grid = _instruction(layout="grid", count=16, rows=4, cols=4)
    items = _expand(grid)
    assert {item.rotation for item in items} == {None}

    _assert_unchanged_from_engine_25(monkeypatch, grid)


# T-9 ---------------------------------------------------------------------
@pytest.mark.parametrize("primitive", TURNED_SHAPES)
def test_the_placement_does_not_move(primitive, monkeypatch):
    """Where engine 25 needed three coordinate corrections, this needs none:
    every consumer of `rotation` turns the shape about `_anchor(ins)` already,
    so a member spins around the point the group was laid out on.

    Structural or not, it is measured. Not byte-identity of the SVG -- the
    tremor of the pen is drawn along the turned outline and is meant to move --
    but the anchors, which is what the placement reads.

    Each of the five shapes the rule turns, not one standing in for the rest:
    engine 25's own gates measured five layouts with a circle each and four
    perturbations walked straight through them."""
    instruction = _instruction(primitive=primitive, count=12)
    engine_26 = _expand(instruction)
    _withhold_rotations(monkeypatch)
    engine_25 = _expand(instruction)

    assert _anchors(engine_26) == pytest.approx(_anchors(engine_25), abs=ANCHOR_TOLERANCE)
    # Not vacuous: the angles really did move, on this shape, in this call.
    assert [item.rotation for item in engine_26] != [item.rotation for item in engine_25]


# T-10 --------------------------------------------------------------------
def test_the_composition_seed_does_not_reach_the_angle(monkeypatch):
    """Engine 23 declared what a composition seed moves: where the marks land.
    An angle drawn from the expander's own placement seed would follow it and
    undo that split.

    Both directions, in one function but as two separate assertions, because
    either alone passes an implementation that has dropped the angle to a
    constant. Through `render`, because that is where the two seeds are told
    apart -- called directly, this test would be stating the seeds itself."""
    instruction = _instruction(count=24)
    here = _members_through_render(
        monkeypatch, instruction, composition_seed=COMPOSITION_SEED
    )
    other_placement = _members_through_render(
        monkeypatch, instruction, composition_seed=COMPOSITION_SEED + 1
    )
    other_performance = _members_through_render(
        monkeypatch,
        instruction,
        composition_seed=COMPOSITION_SEED,
        render_seed=RENDER_SEED + 1,
    )

    # The composition seed moves the placement and nothing else.
    assert [item.rotation for item in here] == [
        item.rotation for item in other_placement
    ]
    assert [renderer._anchor(item) for item in here] != [
        renderer._anchor(item) for item in other_placement
    ]
    # The performance seed moves the angle.
    assert [item.rotation for item in here] != [
        item.rotation for item in other_performance
    ]
    assert len({item.rotation for item in here}) == 24


# T-11 --------------------------------------------------------------------
@pytest.mark.parametrize("primitive", TURNED_SHAPES)
def test_the_earlier_stages_do_not_move(primitive, monkeypatch):
    """Only the angle moved. Engine 25's sizes and engine 24's fade ceilings
    are read out of the same call and have to arrive as they were.

    They can only stay put if the two rules are blind to each other, which they
    are: the size rule reads `radius` / `size` / the endpoints and the angle
    rule reads `rotation`. Mixing the angle draw into the size coefficient is
    the perturbation this exists to catch, and nothing else in the file would
    notice it."""
    instruction = _instruction(primitive=primitive, count=12, fade="outward")
    engine_26 = _expand(instruction)
    _withhold_rotations(monkeypatch)
    engine_25 = _expand(instruction)

    assert _extents(engine_26) == _extents(engine_25)
    assert _fade_levels(engine_26) == _fade_levels(engine_25)
    # The premise: both quantities are actually present on this shape.
    assert len(set(_extents(engine_26))) == 12
    assert all(level for level in _fade_levels(engine_26))
    # Not vacuous: the angles moved in the very call the sizes did not.
    assert [item.rotation for item in engine_26] != [item.rotation for item in engine_25]


def test_engine_25s_own_drawings_replay_unchanged():
    """The other half of T-11, and the half the comparison above cannot reach.

    Withholding the angle step shows that the angle step wrote no size -- but
    both sides of that comparison run the same size rule, so a change to the
    size rule itself is invisible to it, and mixing the angle draw into the
    size coefficient would pass it perfectly.

    So this replays engine 25's own frozen cases through the installed product
    and holds them to the digest engine 25 recorded. Live rendering against a
    frozen record, not manifest against manifest: two frozen files agree with
    each other whatever the renderer is doing today.
    """
    generator = _load_generator()
    previous = _manifest("25")["cases"]
    current = _manifest("26")["cases"]

    replayed = [
        case_id
        for case_id in previous
        if case_id.startswith("G-")
        and previous[case_id]["digest"] == current[case_id]["digest"]
    ]
    assert len(replayed) == ENGINE_25_G_CASES - MOVED_CASES

    # The premise: these are groups whose members really do carry engine 25's
    # per-member sizes, so a change to that rule has somewhere to show.
    sized = [
        case_id
        for case_id in replayed
        if (instruction := previous[case_id]["input"]["score"]["instructions"][0])
        and instruction["arrangement"]["layout"] != "grid"
        and instruction["arrangement"]["count"] > 1
        and GRAMMARS[instruction["weight"]].group_hand > 0.0
    ]
    assert len(sized) == 38

    for case_id in replayed:
        svg = generator.render_case(previous[case_id]["input"])
        assert generator._normalized_digest(svg) == previous[case_id]["digest"], case_id


# T-12 --------------------------------------------------------------------
def test_the_engine_names_itself_26_or_later():
    """`>=`, not `==`. Engine 25's contract had to make engine 24's gates
    relax this exact assertion, because an equality here turns red on the day
    the next stage lands and says nothing about this one."""
    assert int(current_render_engine().version) >= 26


# T-13 --------------------------------------------------------------------
def test_the_added_corpus_cases_discriminate():
    """The four cases engine 26 adds have to be able to fail, and they are
    measured through the corpus rather than through a score built here: a case
    can only be quietly replaced by a different one in the generator, and a
    test that assembles its own input would never see that happen. Engine 25's
    equivalent gate made that mistake and its perturbation walked past.

    The two turning cases have to be `arc` and `cloudform` -- the corpus
    already reaches the rule through three other shapes, so a fourth ellipse
    would discriminate perfectly and cover nothing -- and they have to change
    when the amplitude is withheld. The two stating cases have to do the
    reverse, and still read the angle they state."""
    generator = _load_generator()
    inputs = generator.build_inputs()
    manifest = _manifest(current_render_engine().version)

    for case_id in TURNED_CASES + STATED_CASES:
        assert case_id in manifest["cases"], case_id

    assert {
        inputs[case_id]["score"]["instructions"][0]["primitive"]
        for case_id in TURNED_CASES
    } == {"arc", "cloudform"}

    for case_id in TURNED_CASES:
        drawn = generator._normalized_digest(generator.render_case(inputs[case_id]))
        with generator._member_rotations_withheld():
            assert generator._normalized_digest(
                generator.render_case(inputs[case_id])
            ) != drawn, case_id

    for case_id in STATED_CASES:
        stated = inputs[case_id]
        drawn = generator._normalized_digest(generator.render_case(stated))
        with generator._member_rotations_withheld():
            assert generator._normalized_digest(
                generator.render_case(stated)
            ) == drawn, case_id
        dropped = generator.copy.deepcopy(stated)
        dropped["score"]["instructions"][0]["rotation"] = None
        assert generator._normalized_digest(
            generator.render_case(dropped)
        ) != drawn, case_id


# T-14 --------------------------------------------------------------------
def test_three_cases_of_the_frozen_corpus_moved():
    """The reach of the stage, read off the two bakes.

    A regenerated record and not a property, so this is not on its own a reason
    to believe anything: break the product and it moves too. It is here because
    the count is the one number the contract predicted before the work started
    -- three of 545 -- and a bake that moved 37 or 300 would mean the exclusions
    are not what they are supposed to be."""
    previous = _manifest("25")["cases"]
    current = _manifest("26")["cases"]

    assert len(previous) == ENGINE_25_CASES
    assert len(current) == ENGINE_26_CASES

    shared = set(previous) & set(current)
    moved = {case_id for case_id in shared if previous[case_id]["digest"] != current[case_id]["digest"]}
    assert len(moved) == MOVED_CASES
    assert len(shared) - len(moved) == UNCHANGED_CASES
    assert len(set(current) - set(previous)) == ADDED_CASES
    # Every one of the three is a hand-tool group that is neither a circle nor
    # a line -- which is to say, the three engine 25 added.
    assert moved == {"G-size-ellipse-edge", "G-size-square-edge", "G-size-triangle-edge"}
