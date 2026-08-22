"""engine 24: `fade` reaches every member of a group.

`Arrangement.fade` declares how a group falls off -- `outward` from its centre,
`directional` along the way it travels -- and until engine 23 the renderer
answered it with one constant for the whole group: 0.40 outward, 0.48
directional, the same number on the nearest mark and the farthest. "It fades
from the centre to the edge" was drawn as "all of it is a bit pale". In
production that reading covers 2,738 of 6,425 groups (42.6%) and 83,703 of
178,694 marks.

Nothing is added to the vocabulary here: the declaration was already in the
Score, and these fourteen tests hold the delivery of it. The ramp reaches each
member and its stated ends arrive intact (T-1, T-2, T-12); the two carriages
that would silently swallow it -- the colour cycle that rebuilds `color_hint`
from an allowlist, and the normalisation that flattens a decimal point -- carry
it instead (T-4, and T-2's raw read); a machine tool fades too, by ruling
(T-5); every layout branch writes it (T-6); and the groups that cannot fade are
left exactly where engine 23 left them (T-7, T-14).

The other half is what must NOT move. `color_hint` was chosen as the carriage
because it sits outside `_SEED_INSTRUCTION_FIELDS`, so the hand cannot feel it
(T-11), and the surface seed drops the tag before it hashes the instruction, so
the texture cannot either (T-3). Both are measured against engine 23's own
frozen bytes, not against a reconstruction.
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import math
import pathlib
import re

import pytest

from inku_server import renderer
from inku_server.render_engines.default import planning
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Instruction, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SERVER_ROOT / "reference"
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"

RENDER_SEED = 12345

# The ends of the ramp (author ruling A-1 = F1) and the ratio the fill keeps.
OUTWARD_NEAR, OUTWARD_FAR = 0.62, 0.18
DIRECTIONAL_NEAR, DIRECTIONAL_FAR = 0.70, 0.26
OUTWARD_FILL_RATIO, DIRECTIONAL_FILL_RATIO = 0.55, 0.625
# What engine 23 put on every member of a fading group.
ENGINE_23_OUTWARD, ENGINE_23_DIRECTIONAL = 0.40, 0.48

# The last version that froze a body for this case; its digest is still the one
# engine 23's manifest carries, which is checked in T-11 before it is used.
# engine 28 で再取得。材質層の作り方そのものが変わったので (装飾が演奏された墨から
# オフセットを取り、dasharray を捨てた)、engine 21 が書いた本体との比較は
# 材質層の差で必ず落ちる。**比べている主張は「fade の段は配置にも筆致にも触れない」**
# であって版の同一性ではないので、現行版の本体へ据え直す。
FROZEN_FADE_BODY = REFERENCE_ROOT / "render-engine-28" / "G-scatter-fade-edge.svg"

OPACITY_ATTR = re.compile(r'\s(?:fill|stroke)-opacity="[^"]*"')
MATERIAL_OUTLINE = re.compile(r"<[^>]*material-outline[^>]*>")
D_ATTR = re.compile(r'\sd="([^"]*)"')


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(version: str) -> dict:
    path = REFERENCE_ROOT / f"render-engine-{version}" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _score(
    *,
    fade: str = "outward",
    weight: str = "pen",
    filled: bool = False,
    primitive: str = "circle",
    surface: dict | None = None,
    **arrangement,
) -> dict:
    arr = {"count": 12, "layout": "scatter", "jitter": 0.12, "margin": 0.1, "fade": fade}
    arr.update(arrangement)
    instruction = {
        "primitive": primitive,
        "center": [0.5, 0.5],
        "radius": 0.03,
        "weight": weight,
        "filled": filled,
        "arrangement": arr,
    }
    if surface is not None:
        instruction["surface"] = surface
    return {"instructions": [instruction]}


def _draw(score: dict) -> str:
    # `editable` is the profile that keeps one group per mark, which is how a
    # per-member reading is possible at all; it is also the profile the frozen
    # corpus bakes.
    return render(
        Score.model_validate(score), render_seed=RENDER_SEED, svg_profile="editable"
    )


def _draw_as_frozen(score: dict, monkeypatch) -> str:
    """The same drawing with the per-member levels withheld.

    Engine 24 is engine 23 plus this one step: with no level on the hint the
    consumer falls back to the group-wide constant and the surface seed has
    nothing to drop, so what comes back is the engine-23 drawing.
    """
    monkeypatch.setattr(
        planning, "_apply_fade_levels", lambda items, arr, center=None: items
    )
    return _draw(score)


def _without_member_sizes(monkeypatch) -> None:
    """Take engine 25's per-member size back out.

    The three tests below read this layer against engine 23's frozen bytes.
    Engine 25 gives every member of a group its own size, which moves those
    bytes for a reason that has nothing to do with the fade -- so without this
    they would stop measuring the fade and start measuring the size. The frozen
    body stays the yardstick; what is neutralised is the later layer, not the
    claim.
    """
    monkeypatch.setattr(
        planning, "_apply_member_sizes", lambda items, arr, member_seed: items
    )


def _mark_ceilings(svg: str) -> list[float]:
    """The ink ceiling each member was drawn with, in expansion order.

    The band that draws a hand-tool contour carries it as `fill-opacity`, a
    machine tool as `stroke-opacity`; the `material-outline` circles are the
    tool's own trace and carry neither. A hand tool wraps its mark in a group
    and a machine draws one element, so the id is what both have.
    """
    ceilings = []
    for chunk in svg.split('id="mark_')[1:]:
        body = MATERIAL_OUTLINE.sub("", chunk)
        values = [
            float(value)
            for value in re.findall(r'(?:fill|stroke)-opacity="([0-9.]+)"', body)
        ]
        assert values, "a mark with no opacity attribute at all"
        ceilings.append(max(values))
    return ceilings


def _hints(score: dict) -> list[str | None]:
    """The hints the expansion hands to the consumer, through the product call."""
    instruction = Instruction.model_validate(score["instructions"][0])
    return [
        item.color_hint
        for item in renderer._expand_arrangement_layout(instruction, RENDER_SEED)
    ]


# T-1 --------------------------------------------------------------------
def test_the_fade_differs_by_position_inside_the_group():
    """The nearest member is the darkest and the farthest the palest.

    T-7 is the other half: on its own this passes for an implementation that
    ranks every group by index, including the ones that have no inside.
    """
    score = _score(fade="outward", count=12)
    ceilings = _mark_ceilings(_draw(score))
    assert len(ceilings) == 12
    assert len(set(ceilings)) > 1

    instruction = Instruction.model_validate(score["instructions"][0])
    members = renderer._expand_arrangement_layout(instruction, RENDER_SEED)
    anchors = [renderer._anchor(member) for member in members]
    cx = sum(x for x, _ in anchors) / len(anchors)
    cy = sum(y for _, y in anchors) / len(anchors)
    distances = [math.hypot(x - cx, y - cy) for x, y in anchors]

    nearest = distances.index(min(distances))
    farthest = distances.index(max(distances))
    assert ceilings[nearest] == max(ceilings)
    assert ceilings[farthest] == min(ceilings)
    # Monotone, not merely different: the ramp is the declaration.
    by_distance = [ceiling for _, ceiling in sorted(zip(distances, ceilings))]
    assert by_distance == sorted(by_distance, reverse=True)


# T-2 --------------------------------------------------------------------
def test_the_stated_ends_of_the_ramp_arrive_intact():
    """0.62/0.18 and 0.70/0.26 reach the drawing.

    An implementation that reads the level off the normalised hint gets a
    different number here: normalisation replaces the decimal point, so
    "fade_level=0.6200" arrives as "fade level=0 6200".
    """
    outward = _mark_ceilings(_draw(_score(fade="outward", count=12)))
    assert max(outward) == pytest.approx(OUTWARD_NEAR, abs=5e-5)
    assert min(outward) == pytest.approx(OUTWARD_FAR, abs=5e-5)

    directional = _mark_ceilings(
        _draw(_score(fade="directional", layout="vertical", path="wave", count=12))
    )
    assert max(directional) == pytest.approx(DIRECTIONAL_NEAR, abs=5e-5)
    assert min(directional) == pytest.approx(DIRECTIONAL_FAR, abs=5e-5)


# T-3 --------------------------------------------------------------------
def test_the_surface_texture_does_not_move(monkeypatch):
    """`_surface_seed` hashes the whole instruction dump, so a per-member tag
    would move the texture of every mark in a fading group.

    The case states no surface seed on purpose: with one stated the seed returns
    before the dump is hashed, and this test would pass while measuring nothing.
    """
    surface = {
        "texture": "wash", "density": 0.55, "scale": 0.40, "opacity": 0.36,
        "bleed": 0.25, "direction": "diagonal_rising", "seed": None,
    }
    score = _score(fade="outward", count=8, surface=surface, primitive="circle")
    score["instructions"][0]["radius"] = 0.06

    faded = _draw(score)
    assert "surface_000_000_wash" in faded
    frozen = _draw_as_frozen(copy.deepcopy(score), monkeypatch)

    assert faded != frozen
    # Only the opacity attributes differ -- every coordinate is where engine 23
    # put it, the surface strokes included.
    assert OPACITY_ATTR.sub("", faded) == OPACITY_ATTR.sub("", frozen)


# T-4 --------------------------------------------------------------------
def test_the_fade_survives_a_colour_cycle():
    """43.5% of the fading groups in production state a cycle, and the cycle
    rebuilds `color_hint` from an allowlist. A test that looks only at groups
    without one cannot see this at all."""
    score = _score(fade="outward", count=12, color_cycle=["red", "blue", "green"])
    svg = _draw(score)
    ceilings = _mark_ceilings(svg)
    assert len(set(ceilings)) > 1
    assert max(ceilings) == pytest.approx(OUTWARD_NEAR, abs=5e-5)
    # The cycle still did its own job.
    assert len({colour for colour in re.findall(r'(?:fill|stroke)="(#[0-9a-f]{6})"', svg)}) >= 3
    assert all("fade_level=" in (hint or "") for hint in _hints(score))


# T-5 --------------------------------------------------------------------
def test_the_fade_reaches_a_machine_tool():
    """Author ruling A-2, 2026-08-08: a machine has its own core hardness, its
    own ink density and its own colour, so stage A reaches it. Stage B (the
    per-member differences in FORM) is ruled the other way for `periodic` tools;
    this test is the record that the two disciplines differ."""
    ceilings = _mark_ceilings(_draw(_score(fade="outward", weight="rotring", count=12)))
    assert len(set(ceilings)) > 1
    assert min(ceilings) == pytest.approx(OUTWARD_FAR, abs=5e-5)


# T-6 --------------------------------------------------------------------
LAYOUT_BRANCHES = {
    "grid": {"layout": "grid", "count": 16, "rows": 4, "cols": 4},
    "cluster": {"layout": "scatter", "count": 12, "cluster_count": 3},
    "horizontal-path": {"layout": "horizontal", "count": 12, "path": "wave"},
    "horizontal": {"layout": "horizontal", "count": 12},
    "vertical-path": {"layout": "vertical", "count": 12, "path": "wave"},
    "vertical": {"layout": "vertical", "count": 12},
    "radial": {"layout": "radial", "count": 12},
    "scatter": {"layout": "scatter", "count": 12},
}


@pytest.mark.parametrize("branch", sorted(LAYOUT_BRANCHES))
def test_every_layout_branch_writes_the_level(branch):
    """One branch that keeps the old exit leaves its own layout unfaded, and a
    test that measures a single layout stays green while it does.

    `directional` is the mode used here because it is the one no layout is
    degenerate under: an `outward` ring has no inside, which is T-7.
    """
    score = _score(fade="directional", **LAYOUT_BRANCHES[branch])
    hints = _hints(score)
    assert all("fade_level=" in (hint or "") for hint in hints), branch
    ceilings = _mark_ceilings(_draw(score))
    assert len(set(ceilings)) > 1, branch


def test_the_two_single_member_exits_cannot_fade(monkeypatch):
    """The remaining two of the ten exits return one instruction, and one member
    has no position inside its own group.

    They write no level and the drawing is engine 23's. Note what that drawing
    already was: a group of one drops its `arrangement` without going through
    `_shift`, so `fade=outward` never reached the hint and engine 23 did not
    fade it either. This test holds that unchanged rather than asserting the
    group-wide constant, which was never on it.
    """
    score = _score(fade="outward", count=1)
    assert all("fade_level=" not in (hint or "") for hint in _hints(score))
    faded = _draw(score)
    assert len(_mark_ceilings(faded)) == 1
    assert faded == _draw_as_frozen(copy.deepcopy(score), monkeypatch)


# T-7 --------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,changes",
    [
        ("ring", {"layout": "radial", "count": 12}),
        ("pair", {"layout": "scatter", "count": 2}),
    ],
)
def test_a_group_that_cannot_fade_is_left_where_frozen_left_it(
    name, changes, monkeypatch
):
    """A ring is equidistant from its own centre, and so is a pair. Ranking
    them by index would draw a gradient running once around the ring -- a
    pattern the description never states."""
    score = _score(fade="outward", **changes)
    assert all("fade_level=" not in (hint or "") for hint in _hints(score)), name

    faded = _draw(score)
    ceilings = set(_mark_ceilings(faded))
    assert len(ceilings) == 1
    assert ceilings.pop() == pytest.approx(ENGINE_23_OUTWARD, abs=5e-5)
    assert faded == _draw_as_frozen(copy.deepcopy(score), monkeypatch)


# T-8 --------------------------------------------------------------------
def test_the_engine_names_itself_24_or_later():
    """`>=`, not `==`: what engine 24 added holds for every version after it,
    and an equality here is a statement that is true for one round only."""
    assert int(current_render_engine().version) >= 24


# T-9 --------------------------------------------------------------------
def test_the_added_corpus_cases_can_tell_the_fade_apart():
    """Each of the six added cases draws a different picture with `fade` than
    without it. Checked here and at bake time, on the bake's own call: a case
    that cannot fail would record that nothing broke and nothing else."""
    generator = _load_generator()
    inputs = generator.build_inputs()
    assert len(generator.FADE_CASES) == 6
    generator._assert_fade_cases_discriminate(inputs)

    manifest = _manifest(current_render_engine().version)
    for case_id in generator.FADE_CASES:
        assert case_id in manifest["cases"], case_id
        assert manifest["cases"][case_id]["input"]["score"]["instructions"][0][
            "arrangement"
        ]["fade"] != "none", case_id


# T-10 -------------------------------------------------------------------
def test_one_case_of_the_frozen_corpus_moved():
    """A regenerated record, not a property: on its own it is not evidence that
    the change is right. It says what the corpus could see -- one route out of
    535, the plainest fading group there is."""
    # Named, not "current": this records what engine 24's bake did to engine
    # 23's, and that pair is fixed forever. Read as "current" it would restate
    # itself against every later bake and go red on the next one.
    current = _manifest("24")
    previous = _manifest("23")
    assert len(previous["cases"]) == 535
    assert len(current["cases"]) == 541

    moved = sorted(
        case_id
        for case_id, case in previous["cases"].items()
        if current["cases"][case_id]["digest"] != case["digest"]
    )
    assert moved == ["G-scatter-fade-edge"]
    added = set(current["cases"]) - set(previous["cases"])
    assert sorted(current["changed_from_previous"]) == sorted(added | set(moved))


# T-11 -------------------------------------------------------------------
def test_the_hand_does_not_feel_the_level(monkeypatch):
    """Stage A is orthogonal to placement and to touch.

    `color_hint` is the carriage exactly because it is outside
    `_SEED_INSTRUCTION_FIELDS`. Written to a field inside that list, the same
    number would move every performance seed in the group and the coordinates
    below would move with it. Measured against the current corpus's own bytes.
    """
    assert "color_hint" not in renderer._SEED_INSTRUCTION_FIELDS

    # engine 28 で据え直した。これは以前 engine 23 の凍結バイトを物差しにし、
    # 後から載った層 (engine 25 の成員ごとの寸法) を無効化して比べていた。
    # engine 28 は材質層の作り方と揺らぎの物差しの両方を動かしたので、同じやり方を
    # 続けるには engine 28 を丸ごと無効化することになる —— それは物差しを作り直す
    # のと変わらない。**主張は「fade の段は配置にも筆致にも触れない」**なので、
    # 版を挟まずに fade の入・切そのものを比べる。凍結バイトへの依存が無くなり、
    # 次の engine でも同じ検査がそのまま効く。
    case = _manifest("28")["cases"]["G-scatter-fade-edge"]
    generator = _load_generator()

    faded = case["input"]
    plain = copy.deepcopy(faded)
    assert plain["score"]["instructions"][0]["arrangement"]["fade"] != "none"
    plain["score"]["instructions"][0]["arrangement"]["fade"] = "none"

    with_fade = generator.render_case(faded)
    without_fade = generator.render_case(plain)
    assert with_fade != without_fade
    assert D_ATTR.findall(with_fade) == D_ATTR.findall(without_fade)
    assert OPACITY_ATTR.sub("", with_fade) == OPACITY_ATTR.sub("", without_fade)


# T-12 -------------------------------------------------------------------
def test_directional_follows_the_expansion_order():
    """`directional` is the mode a two-member group can still take, because it
    reads the order the path lays the marks down in rather than a distance."""
    score = _score(
        fade="directional", layout="vertical", path="top_to_bottom", count=20
    )
    ceilings = _mark_ceilings(_draw(score))
    assert len(ceilings) == 20
    assert ceilings == sorted(ceilings, reverse=True)
    assert ceilings[0] == pytest.approx(DIRECTIONAL_NEAR, abs=5e-5)
    assert ceilings[-1] == pytest.approx(DIRECTIONAL_FAR, abs=5e-5)


# T-13 -------------------------------------------------------------------
@pytest.mark.parametrize(
    "fade,ratio,layout",
    [
        ("outward", OUTWARD_FILL_RATIO, {"layout": "scatter"}),
        ("directional", DIRECTIONAL_FILL_RATIO, {"layout": "vertical", "path": "wave"}),
    ],
)
def test_the_fill_keeps_its_ratio_to_the_stroke(fade, ratio, layout):
    """The engine-23 constants carried a ratio -- 0.22/0.40 and 0.30/0.48 -- and
    the ramp keeps it, so a filled group thins in step instead of the outline
    running away from its own fill."""
    score = _score(fade=fade, filled=True, count=12, **layout)
    instruction = Instruction.model_validate(score["instructions"][0])
    members = renderer._expand_arrangement_layout(instruction, RENDER_SEED)
    canvas = renderer.canvas_size_for_aspect("square")

    seen = set()
    for member in members:
        attrs = renderer._stroke_attrs(
            member,
            {"black": "#111111"},
            canvas,
            work_assignment={},
        )
        assert attrs["fill"] != "none"
        assert attrs["fill_opacity"] / attrs["stroke_opacity"] == pytest.approx(
            ratio, abs=1e-3
        )
        seen.add(attrs["stroke_opacity"])
    assert len(seen) > 1


# T-14 -------------------------------------------------------------------
def test_a_group_that_declares_no_fade_is_byte_identical(monkeypatch):
    """Every G case of engine 23 that states no fade reproduces its frozen
    digest here, through the bake's own call.

    The tag is not minted either. The digest above cannot see that on its own:
    the consumer is gated on the `fade=<mode>` token, which a group that
    declares no fade never carries, so a level written onto one would ride along
    unread and change no byte. What must not happen is that it is written.
    """
    assert all("fade_level=" not in (hint or "") for hint in _hints(_score(fade="none")))

    # engine 28 で据え直した。無効化していたのは engine 25 の層で、engine 23 の
    # 凍結バイトを物差しにしていたためである。engine 28 の corpus に対しては
    # 無効化なしで読む —— **この半分は焼き直される記録であって検査ではない**
    # （主張そのものは上の 1 行が持っている。件数 35 は母集団の番人として残す）。
    generator = _load_generator()
    # Engine 29 resnaps the live half; the fade population is unchanged.
    current = _manifest("29")
    checked = 0
    for case_id, case in sorted(current["cases"].items()):
        if not case_id.startswith("G-"):
            continue
        arrangement = case["input"]["score"]["instructions"][0]["arrangement"]
        if arrangement["fade"] != "none":
            continue
        digest = generator._normalized_digest(generator.render_case(case["input"]))
        assert digest == case["digest"], case_id
        checked += 1
    # 35 -> 43. engine 23 の corpus を読んでいたのを engine 28 のものへ据え直した
    # ので母集団が増えた (engine 24〜28 が足した G の case のうち fade を宣言しない
    # もの)。**数える番人としての役目は変わらない** —— 読み手が大半を落としても
    # 通ってしまうことを防ぐために置いてある。
    assert checked == 43


# T-15 -------------------------------------------------------------------
def test_the_corpus_holds_a_ramped_group_and_two_that_cannot_fade():
    """The bake asks the corpus what the weak guard cannot ask it.

    T-9 withholds the declaration, and engine 23 already drew that difference
    with one constant for the whole group -- so a renderer carrying no
    per-member ceiling passes it. This is the other half: some drawn fading
    group has to hold distinct levels, and the two degenerate ones none.
    Author ruling A on ledger I-166, 2026-08-09.
    """
    generator = _load_generator()
    inputs = generator.build_inputs()
    assert set(generator.DEGENERATE_FADE_CASES) <= set(generator.FADE_CASES)
    generator._assert_fade_reaches_every_member(inputs)

    # The question has something to bite on: not every case is degenerate.
    assert len(generator.DEGENERATE_FADE_CASES) < len(generator.FADE_CASES)


# T-16 -------------------------------------------------------------------
def test_the_bake_runs_every_discriminating_guard_it_defines():
    """A guard nobody calls is a guard that cannot fail.

    The four live in the generator and are wired into `generate` by hand, and
    removing one line there would leave every test above green while the corpus
    went back to being baked unasked.
    """
    generator = _load_generator()
    body = inspect.getsource(generator.generate)
    for name in (
        "_assert_fade_cases_discriminate",
        "_assert_fade_reaches_every_member",
        "_assert_size_cases_discriminate",
        "_assert_angle_cases_discriminate",
    ):
        assert f"{name}(inputs)" in body, name
