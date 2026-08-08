"""engine 25: each member of a group gets its own size.

`Arrangement` is the declaration "several of this shape". It never says "all of
them the same size" -- and yet until here the expander answered it by rewriting
coordinates and nothing else, so the N members came out congruent. That
congruence was the engine's own addition, the largest signature it was putting
on drawings nobody had asked it for: in production 2,559 of 2,757 works carry
an expanded group, the expander lays down 178,694 marks, and the coefficient of
variation of the sizes inside a group is 0.0000.

These fourteen tests hold a change that takes a property out rather than
putting one in. The sizes differ and the amplitude is the one that was ruled on
(T-1, T-2); the groups that keep their exact repetition keep it, by ruling for
`grid`, by having nobody to differ from at `count == 1`, and by tool grammar
for the machines (T-3, T-4, T-10); the four size rules each preserve the anchor
they are measured from, so the placement sees the group engine 24 placed
(T-5, T-9), and stage A's fade ceilings, measured from those same anchors,
arrive unchanged (T-8).

The other half is which seed the size is drawn from. Engine 23 split placement
off onto the composition seed and declared that this is what a composition seed
moves; a size fed from the expander's own seed would have followed it and
undone the split on the day it was made. T-6 and T-7 are set as a pair, because
either alone passes for an implementation that has dropped the size to a
constant.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import statistics

import pytest

from inku_server import renderer
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Instruction, Score
from inku_server.stroke_engine import GRAMMARS, HAND_GROUP_SIZE

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SERVER_ROOT / "reference"
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

RENDER_SEED = 12345
COMPOSITION_SEED = 777

# The ruling (author, 2026-08-08): +/-25%, one amplitude for every hand tool.
AMPLITUDE = 0.25

# What engine 24 froze, and what engine 25 does to it.
ENGINE_24_CASES = 541
ENGINE_25_CASES = 545
MOVED_CASES = 37
UNCHANGED_CASES = 504

# An anchor that is rebuilt from two fields -- a bbox from `position` and
# `size`, a line from its two ends -- is recovered through two coordinates that
# `_quantise_instructions` rounds independently, so it lands within one step of
# the nine-decimal grid rather than on the same float. Measured: 1.0e-9 for
# `square` and `triangle`, 5.0e-10 for `line`, exactly 0 for the primitives
# anchored on `center`. That is 1e-6 px on a 1000px canvas, three decimals under
# what the SVG prints. What the two rules here would move if they were wrong is
# half the growth of the shape -- about 1e-2 -- seven orders of magnitude above
# this bound.
ANCHOR_TOLERANCE = 2 * 10 ** -renderer.ARRANGEMENT_QUANTUM


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
    primitive: str = "circle",
    weight: str = "pen",
    **arrangement,
) -> Instruction:
    arr = {"count": 12, "layout": "scatter", "jitter": 0.12, "margin": 0.1}
    arr.update(arrangement)
    geometry: dict = {
        "circle": {"center": [0.5, 0.5], "radius": 0.03},
        "ellipse": {"center": [0.5, 0.5], "size": [0.10, 0.06]},
        "square": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
        "triangle": {"position": [0.46, 0.46], "size": [0.08, 0.08]},
        "line": {"from": [0.46, 0.48], "to": [0.54, 0.52]},
    }[primitive]
    return Instruction.model_validate(
        {"primitive": primitive, "weight": weight, "arrangement": arr, **geometry}
    )


def _expand(instruction: Instruction, *, placement=None, performance=RENDER_SEED):
    """The product call, with both seeds stated."""
    return renderer._expand_arrangement(
        instruction,
        RENDER_SEED if placement is None else placement,
        None,
        performance_seed=performance,
    )


def _withhold_sizes(monkeypatch) -> None:
    """Draw as engine 24 did: the group expands, and every member is congruent.

    Engine 25 is engine 24 plus this one step, so neutralising it is how a test
    reads engine 24's answer out of the engine that is installed -- the same
    device engine 24's own gates used to read engine 23's.
    """
    monkeypatch.setattr(
        renderer, "_apply_member_sizes", lambda items, arr, size_seed: items
    )


def _members_through_render(monkeypatch, instruction: Instruction, **kwargs):
    """The members as they leave the expander, on the product's own render path.

    `_expand_arrangement` can be called directly, and the tests above do -- but
    which seed reaches it is decided by `render`, one call further out. A gate
    that only ever calls the expander itself states both seeds by hand and so
    cannot see the caller stop passing one.
    """
    captured: list[list[Instruction]] = []
    original = renderer._apply_member_sizes

    def spy(items, arr, size_seed):
        sized = original(items, arr, size_seed)
        captured.append(sized)
        return sized

    monkeypatch.setattr(renderer, "_apply_member_sizes", spy)
    _draw(instruction, **kwargs)
    assert len(captured) == 1
    return captured[0]


def _draw(instruction: Instruction, **kwargs) -> str:
    # `editable` keeps one group per mark and is the profile the corpus bakes.
    kwargs.setdefault("render_seed", RENDER_SEED)
    return render(
        Score.model_validate({"instructions": [instruction.model_dump(by_alias=True)]}),
        svg_profile="editable",
        **kwargs,
    )


def _anchors(items: list[Instruction]) -> list[float]:
    """Every member's anchor, flattened: `pytest.approx` compares numbers."""
    return [value for item in items for value in renderer._anchor(item)]


def _extent(item: Instruction) -> float:
    """One number per member, in the unit its own rule scales.

    Not a rendered width: the claim is about the dimension the description
    states, and the four primitives state it in three different fields.
    """
    if item.primitive == "line":
        assert item.from_ and item.to
        return math.hypot(item.to[0] - item.from_[0], item.to[1] - item.from_[1])
    if item.radius is not None:
        return item.radius
    assert item.size is not None
    return item.size[0]


# T-1 --------------------------------------------------------------------
def test_the_members_of_a_group_differ_in_size():
    """The congruence was the engine's addition; this is it being taken out.

    T-3 is the other half: on its own this passes for an implementation that
    varies the size of the machine tools too.
    """
    members = _expand(_instruction(count=24))
    radii = [item.radius for item in members]
    assert len(radii) == 24
    # Near the member count, not merely "more than one": a rule that gave the
    # group two sizes would satisfy the weaker claim.
    assert len(set(radii)) == 24
    assert statistics.pstdev(radii) / statistics.fmean(radii) > 0.10


# T-2 --------------------------------------------------------------------
def test_the_amplitude_is_the_one_that_was_ruled_on():
    """0.75x..1.25x, and the ends are reached rather than merely respected."""
    base = _instruction(count=400).radius
    factors = sorted(item.radius / base for item in _expand(_instruction(count=400)))

    assert factors[0] >= 1 - AMPLITUDE
    assert factors[-1] <= 1 + AMPLITUDE
    # A rule that halved the amplitude would still sit inside the bound above.
    assert factors[0] == pytest.approx(1 - AMPLITUDE, abs=2e-3)
    assert factors[-1] == pytest.approx(1 + AMPLITUDE, abs=2e-3)
    assert statistics.fmean(factors) == pytest.approx(1.0, abs=0.02)


# T-3 --------------------------------------------------------------------
def test_the_machine_tools_repeat_exactly():
    """Exact repetition is the machine's signature, not a defect to sand off.

    The corpus can only measure `rotring`: `G-fade-rotring-edge` is the one
    machine group among its 42, and it carries no `computer` group at all, so
    that half is built here. Read against engine 24's frozen digest through the
    bake's own call, which fails without a rebake.
    """
    assert GRAMMARS["rotring"].group_hand == 0.0
    assert GRAMMARS["computer"].group_hand == 0.0

    generator = _load_generator()
    engine_24 = _manifest("24")["cases"]["G-fade-rotring-edge"]
    assert (
        generator._normalized_digest(generator.render_case(engine_24["input"]))
        == engine_24["digest"]
    )
    assert _manifest("25")["cases"]["G-fade-rotring-edge"]["digest"] == engine_24["digest"]

    for weight in ("rotring", "computer"):
        members = _expand(_instruction(weight=weight, count=12))
        assert len({item.radius for item in members}) == 1


def test_the_machine_group_is_byte_identical(monkeypatch):
    """The whole drawing, not only the stated radius: a machine group has to
    come out of engine 25 as the bytes engine 24 wrote."""
    computer = _instruction(weight="computer", count=12)
    engine_25 = _draw(computer)
    _withhold_sizes(monkeypatch)
    assert engine_25 == _draw(computer)


# T-4 --------------------------------------------------------------------
def test_grid_repeats_exactly(monkeypatch):
    """An even tiling is the one arrangement whose point is that the cells
    match (author ruling, 2026-08-08)."""
    generator = _load_generator()
    engine_24 = _manifest("24")["cases"]
    engine_25 = _manifest("25")["cases"]
    grids = sorted(
        case_id
        for case_id, case in engine_24.items()
        if case_id.startswith("G-")
        and case["input"]["score"]["instructions"][0]["arrangement"]["layout"] == "grid"
    )
    assert len(grids) == 4
    for case_id in grids:
        assert engine_25[case_id]["digest"] == engine_24[case_id]["digest"], case_id
        assert (
            generator._normalized_digest(
                generator.render_case(engine_24[case_id]["input"])
            )
            == engine_24[case_id]["digest"]
        ), case_id

    tiling = _instruction(layout="grid", count=16, rows=4, cols=4)
    drawn = _draw(tiling)
    _withhold_sizes(monkeypatch)
    assert drawn == _draw(tiling)


# T-5 --------------------------------------------------------------------
# One primitive per layout rather than a circle five times. A circle has no
# `position` and no endpoints, so a circle-only reading of this cannot see the
# bbox correction or the midpoint pivot come out -- measured: both perturbations
# left the five green when they were all circles.
@pytest.mark.parametrize(
    "changes",
    [
        {"layout": "scatter", "primitive": "circle"},
        {"layout": "vertical", "path": "wave", "primitive": "square"},
        {"layout": "horizontal", "primitive": "line"},
        {"layout": "radial", "count": 12, "primitive": "ellipse"},
        {"cluster_count": 3, "primitive": "triangle"},
    ],
)
def test_the_placement_does_not_move(changes, monkeypatch):
    """`_fit_group_to_anchor` reads the anchors of the members and nothing
    else, so a size rule that moved one would hand the placement a different
    group. Measured after the fit, which is where the group finally is.

    Not a byte comparison: the hand does move, and by design -- `radius`,
    `size`, `from` and `to` are all inside `_SEED_INSTRUCTION_FIELDS`, so a
    member that changed size is performed with its own tremor.
    """
    instruction = _instruction(**changes)
    engine_25 = _expand(instruction)
    sized = [_extent(item) for item in engine_25]

    _withhold_sizes(monkeypatch)
    engine_24 = _expand(instruction)

    assert _anchors(engine_25) == pytest.approx(
        _anchors(engine_24), abs=ANCHOR_TOLERANCE
    )
    # Otherwise the equality above is the equality of two identical runs.
    assert sized != [_extent(item) for item in engine_24]


# T-6 --------------------------------------------------------------------
def test_the_composition_seed_does_not_reach_the_size(monkeypatch):
    """Engine 23 declared what a composition seed moves: where the marks land.

    The expander's own seed is built from the placement seed, so a size drawn
    from it would follow the composition seed and undo that split. T-7 is the
    other half.

    Through `render`, because that is where the two seeds are told apart.
    """
    instruction = _instruction(count=24)
    here = _members_through_render(
        monkeypatch, instruction, composition_seed=COMPOSITION_SEED
    )
    there = _members_through_render(
        monkeypatch, instruction, composition_seed=COMPOSITION_SEED + 1
    )

    assert [item.radius for item in here] == [item.radius for item in there]
    # The premise: these two placements really are different placements.
    assert [renderer._anchor(item) for item in here] != [
        renderer._anchor(item) for item in there
    ]


# T-7 --------------------------------------------------------------------
def test_the_performance_seed_does_reach_the_size(monkeypatch):
    """The reverse of T-6. Without it, an implementation that dropped the size
    to a constant passes T-6 perfectly.

    Through `render` and with the composition seed held still, so that what is
    varied is the performance seed alone. Called directly instead, this passes
    whether or not `render` ever hands the expander a performance seed -- the
    test would be stating it itself.
    """
    instruction = _instruction(count=24)
    here = [
        item.radius
        for item in _members_through_render(
            monkeypatch, instruction, composition_seed=COMPOSITION_SEED
        )
    ]
    there = [
        item.radius
        for item in _members_through_render(
            monkeypatch,
            instruction,
            composition_seed=COMPOSITION_SEED,
            render_seed=RENDER_SEED + 1,
        )
    ]

    assert here != there
    assert len(set(here)) == 24 and len(set(there)) == 24


# T-8 --------------------------------------------------------------------
@pytest.mark.parametrize("fade,changes", [
    ("outward", {"layout": "scatter", "count": 12}),
    ("directional", {"layout": "vertical", "path": "top_to_bottom", "count": 20}),
    ("outward", {"cluster_count": 3, "count": 12}),
    ("outward", {"layout": "scatter", "count": 12,
                 "color_cycle": ["red", "blue", "green"]}),
])
def test_stage_a_fade_levels_do_not_move(fade, changes, monkeypatch):
    """Stage A measures the ramp from the anchors and the member count, and
    stage B moves neither, so the ceilings engine 24 wrote arrive intact.

    The order inside `_finish_expanded_group` is what makes this true, and it
    is the order a later change is most likely to disturb.
    """
    instruction = _instruction(fade=fade, **changes)
    levels = [
        renderer._fade_level_from_hint(item.color_hint)
        for item in renderer._expand_arrangement_layout(
            instruction, RENDER_SEED, None, performance_seed=RENDER_SEED
        )
    ]
    assert all(level is not None for level in levels)

    _withhold_sizes(monkeypatch)
    assert levels == [
        renderer._fade_level_from_hint(item.color_hint)
        for item in renderer._expand_arrangement_layout(
            instruction, RENDER_SEED, None, performance_seed=RENDER_SEED
        )
    ]


# T-9 --------------------------------------------------------------------
@pytest.mark.parametrize(
    "primitive", ["circle", "ellipse", "square", "triangle", "line"]
)
def test_every_size_rule_preserves_its_anchor(primitive, monkeypatch):
    """Four rules, four anchors. A circle keeps its centre; a bbox has to pull
    its corner back by half the growth or its middle walks away; a line has to
    grow about its own midpoint rather than about one end.

    Measured on all five primitives because the corpus holds circles only: 42
    of its 42 groups, so `radius x k` was the only rule it could ever see.
    """
    instruction = _instruction(primitive=primitive, count=12)
    engine_25 = _expand(instruction)

    _withhold_sizes(monkeypatch)
    engine_24 = _expand(instruction)

    assert _anchors(engine_25) == pytest.approx(
        _anchors(engine_24), abs=ANCHOR_TOLERANCE
    )
    assert [_extent(item) for item in engine_25] != [
        _extent(item) for item in engine_24
    ]


def test_the_corpus_walks_every_size_rule(monkeypatch):
    """The same claim on the corpus's own cases, not only on scores built here.

    All 42 groups engine 24 froze are circles, so `radius x k` is the only rule
    the corpus could reach and the other three would go unwatched by every
    frozen record. This is what the four cases added in engine 25 are for, and
    it is what stops them being quietly replaced by four more circles.
    """
    generator = _load_generator()
    instructions = {
        case_id: Instruction.model_validate(
            render_input["score"]["instructions"][0]
        )
        for case_id, render_input in generator.build_inputs().items()
        if case_id.startswith("G-")
    }
    assert len(instructions) == 46
    shaped = {
        case_id: instruction
        for case_id, instruction in instructions.items()
        if instruction.primitive != "circle"
    }
    assert {item.primitive for item in shaped.values()} == {
        "line", "square", "triangle", "ellipse"
    }

    seed = generator.DEFAULT_RENDER_SEED
    engine_25 = {
        case_id: renderer._expand_arrangement(
            instruction, seed, None, performance_seed=seed
        )
        for case_id, instruction in shaped.items()
    }
    _withhold_sizes(monkeypatch)
    for case_id, instruction in shaped.items():
        engine_24 = renderer._expand_arrangement(
            instruction, seed, None, performance_seed=seed
        )
        assert _anchors(engine_25[case_id]) == pytest.approx(
            _anchors(engine_24), abs=ANCHOR_TOLERANCE
        ), case_id
        assert [_extent(item) for item in engine_25[case_id]] != [
            _extent(item) for item in engine_24
        ], case_id


def test_a_scaled_member_keeps_its_aspect_ratio():
    """`k` is a similarity factor. Stretching one axis is a second axis of
    variation that was not ruled on -- and for `square` it would stop being a
    square."""
    for primitive in ("ellipse", "square", "triangle"):
        instruction = _instruction(primitive=primitive, count=12)
        stated = instruction.size
        assert stated is not None
        # Held on the same nine-decimal grid the expansion is quantised on:
        # the two components are scaled by one `k` and then rounded apart.
        # Stretching one axis by the amplitude would be 1e-1 here.
        ratios = [item.size[0] / item.size[1] for item in _expand(instruction)]
        stated_ratio = stated[0] / stated[1]
        assert ratios == pytest.approx([stated_ratio] * len(ratios), abs=1e-6), primitive


# T-10 -------------------------------------------------------------------
@pytest.mark.parametrize("layout", ["scatter", "vertical", "radial", "horizontal"])
def test_a_group_of_one_is_byte_identical(layout, monkeypatch):
    """A member of one has nobody to differ from, so the drawing is engine
    24's to the byte.

    Built here rather than replayed from the corpus: not one of the corpus's 42
    groups states `count == 1`, so a corpus-only reading of this would be
    vacuously true and the perturbation that varies a lone member would find
    nothing to break.
    """
    assert all(
        case["input"]["score"]["instructions"][0]["arrangement"]["count"] > 1
        for case in _manifest("24")["cases"].values()
        if case["input"]["score"]["instructions"][0].get("arrangement")
    )

    alone = _instruction(count=1, layout=layout)
    engine_25 = _draw(alone)
    _withhold_sizes(monkeypatch)
    assert engine_25 == _draw(alone)


# T-11 -------------------------------------------------------------------
def test_the_engine_names_itself_25_or_later():
    """`>=`, not `==`. Engine 24 wrote the equality and it went red the moment
    engine 25 arrived, which is a statement that is only ever true for one
    round; what this change adds is true of every version after it.
    """
    assert int(current_render_engine().version) >= 25
    assert HAND_GROUP_SIZE == AMPLITUDE
    assert all(
        GRAMMARS[weight].group_hand == AMPLITUDE
        for weight in GRAMMARS
        if weight not in ("rotring", "computer")
    )


# T-12 -------------------------------------------------------------------
def test_the_added_corpus_cases_discriminate():
    """The four added cases have to fail when the change is undone, and they
    have to walk four different rules.

    Both clauses are load-bearing and neither replaces the other. Four fresh
    circles would discriminate perfectly and add no coverage at all, because
    all 42 groups the corpus already held were circles.
    """
    generator = _load_generator()
    inputs = generator.build_inputs()
    assert len(generator.SIZE_CASES) == 4
    generator._assert_size_cases_discriminate(inputs)

    manifest = _manifest(current_render_engine().version)
    primitives = set()
    for case_id in generator.SIZE_CASES:
        assert case_id in manifest["cases"], case_id
        instruction = manifest["cases"][case_id]["input"]["score"]["instructions"][0]
        assert instruction["arrangement"]["count"] > 1, case_id
        primitives.add(instruction["primitive"])
        # The contract's own reading: a case that draws the same picture with
        # one member as with twelve is recording the frame and nothing else.
        lone = generator.copy.deepcopy(manifest["cases"][case_id]["input"])
        lone["score"]["instructions"][0]["arrangement"]["count"] = 1
        assert generator._normalized_digest(
            generator.render_case(manifest["cases"][case_id]["input"])
        ) != generator._normalized_digest(generator.render_case(lone)), case_id
    assert primitives == {"line", "square", "triangle", "ellipse"}


# T-13 -------------------------------------------------------------------
def test_thirty_seven_cases_of_the_frozen_corpus_moved():
    """A regenerated record, not a property: on its own it is not evidence that
    the change is right. It says what the corpus could see -- every group that
    expands with a hand tool and is not a grid, and nothing else."""
    previous = _manifest("24")
    current = _manifest("25")
    assert len(previous["cases"]) == ENGINE_24_CASES
    assert len(current["cases"]) == ENGINE_25_CASES

    moved = sorted(
        case_id
        for case_id, case in previous["cases"].items()
        if current["cases"][case_id]["digest"] != case["digest"]
    )
    assert len(moved) == MOVED_CASES
    assert len(previous["cases"]) - len(moved) == UNCHANGED_CASES
    assert all(case_id.startswith("G-") for case_id in moved)

    added = set(current["cases"]) - set(previous["cases"])
    assert sorted(current["changed_from_previous"]) == sorted(added | set(moved))


# T-14 -------------------------------------------------------------------
def test_a_score_with_no_arrangement_is_byte_identical(monkeypatch):
    """453 of the 541 cases engine 24 froze state no arrangement at all, and
    not one of them may move: this change lives inside the expander, and a
    single instruction never enters it."""
    previous = _manifest("24")["cases"]
    current = _manifest("25")["cases"]
    plain = [
        case_id
        for case_id, case in previous.items()
        if case["input"]["score"]["instructions"][0].get("arrangement") is None
    ]
    assert len(plain) >= 450
    for case_id in plain:
        assert current[case_id]["digest"] == previous[case_id]["digest"], case_id

    single = Score.model_validate(
        {
            "instructions": [
                {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.24},
                {"primitive": "line", "from": [0.18, 0.5], "to": [0.82, 0.5]},
            ]
        }
    )
    engine_25 = render(single, render_seed=RENDER_SEED, svg_profile="editable")
    _withhold_sizes(monkeypatch)
    assert engine_25 == render(single, render_seed=RENDER_SEED, svg_profile="editable")
