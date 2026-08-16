"""render engine 37: a named sheet changes how the mark runs.

Contract `a-named-sheet-changes-how-the-mark-runs`. `Support` has carried the
sheet's two quantities since engine 19 and `synthesize_stroke` has accepted one
for just as long, but no caller passed it -- measured 2026-08-16, `git grep
'support='` returned nothing under `server/src`. So a work drew the same way on
washi and on canvas, and the ground it named reached the picture as backdrop
artwork only.

Two of the nine surface words are about the mark rather than about an interior.
粒 is the tool skipping on the sheet and にじみ is the ink spreading into it, and
a line has no interior to hold either, so coerce stops carrying them back to the
nearest closed shape and the renderer raises the sheet for that one instruction.

T-1..T-11 are the contract's acceptance. **T-5, T-6 and T-11 go through
`coerce_score`**: the reference-corpus generator imports `renderer` directly and
never calls coerce, so a gate that skipped it would stay green while production
dropped every one of these requests before the renderer saw it.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import re
from typing import Any, get_args

import pytest

from inku_server import renderer, stroke_engine
from inku_server.coerce import coerce_score
from inku_server.renderer import render
from inku_server.schema import CLOSED_SHAPES, MARK_SURFACE_WORDS, GroundMaterial, Score
from inku_server.stroke_engine import (
    DEFAULT_SUPPORT,
    GROUND_SUPPORT,
    MARK_SUPPORT_GAIN,
    SUPPORT_CAP,
    TOOL_SUPPORT_BIAS,
    support_for_ground,
    support_with_mark_word,
)

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_36_MANIFEST = SERVER_ROOT / "reference" / "render-engine-36" / "manifest.json"

SEED = 20260816
PATH_D = re.compile(r'\sd="([^"]*)"')
FILTER_REF = re.compile(r'filter="url\(')

# The seven the ground field carries that draw something. `plain` is the absence
# of a ground and is deliberately not one of them.
SHEETS = (
    "paper",
    "washi",
    "ink_wash",
    "charcoal_ground",
    "canvas",
    "drawing_paper",
    "mezzotint",
)

SURFACE: dict[str, Any] = {
    "texture": "grain",
    "density": 0.55,
    "scale": 0.40,
    "opacity": 0.36,
    "bleed": 0.25,
    "direction": "none",
    "spacing_gradient": "none",
    "tone_steps": 3,
    "seed": 24680,
}
GROUND: dict[str, Any] = {
    "material": "paper",
    "tone": "off_white",
    "grain": "medium",
    "density": 0.45,
    "opacity": 0.16,
    "seed": 13579,
}


def _score(
    weight: str = "brush_thick",
    *,
    material: str | None = None,
    texture: str | None = None,
    primitive: str = "line",
) -> Score:
    instruction: dict[str, Any] = {
        "primitive": primitive,
        "weight": weight,
        "color": "black",
    }
    if primitive == "line":
        instruction |= {"from": [0.18, 0.50], "to": [0.82, 0.50]}
    else:
        instruction |= {"center": [0.50, 0.50], "radius": 0.24}
    if texture is not None:
        surface = copy.deepcopy(SURFACE)
        surface["texture"] = texture
        instruction["surface"] = surface
    ground = None
    if material is not None:
        ground = copy.deepcopy(GROUND)
        ground["material"] = material
    return Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": {"aspect": "square", "ground": ground},
            "background": "white",
            "presence": None,
            "instructions": [instruction],
        }
    )


CONTENT_GROUP = re.compile(r'<g [^>]*clip-path="url\(#canvas-clip\)"')


def _marks(svg: str) -> list[str]:
    """Every path body of the marks, with the ground's own artwork left out.

    The ground draws itself into `layer_01_canvas_ground`, and that layer is
    different for every support by design. Counting it here would make "the
    sheet changed the mark" true for a version that changed only the backdrop --
    which is exactly the state this contract exists to end.
    """
    start = CONTENT_GROUP.search(svg)
    assert start is not None, "the drawing has no content group"
    return PATH_D.findall(svg[start.start() :])


def _draw(score: Score, **kwargs: Any) -> str:
    return render(score, render_seed=SEED, **kwargs)


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_render_reference", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- T-1: the table --------------------------------------------------------


def test_t1_every_ground_material_has_a_sheet() -> None:
    """T-1. The table is walked from the enum, and unknown is an error.

    A support that joins `GroundMaterial` and never joins the table would draw
    as plain paper, and nothing about the picture would say so. The table is
    built by walking `get_args(GroundMaterial)` for exactly that reason, so a
    hand-written list of names here would be a second copy free to drift.
    """
    materials = get_args(GroundMaterial)
    assert set(SHEETS) | {"plain"} == set(materials)
    for material in materials:
        assert material in GROUND_SUPPORT, material
        assert support_for_ground(material) is GROUND_SUPPORT[material]
    # The absence of a ground is the one constant sheet, not a sheet of its own.
    assert support_for_ground("plain") == DEFAULT_SUPPORT
    assert support_for_ground("paper") == DEFAULT_SUPPORT
    with pytest.raises(ValueError):
        support_for_ground("vellum")


# --- T-2: the sheet reaches the mark ---------------------------------------


def test_t2_a_different_sheet_draws_a_different_mark() -> None:
    """T-2. The same score and the same seed on seven sheets draw seven marks.

    Pairwise rather than one pair: measured against a single washi-vs-canvas
    comparison, giving `canvas` the paper's own numbers leaves that pair
    different and the gate green. Seven distinct bodies is what says each row of
    the table reached the drawing.
    """
    bodies = {material: _marks(_draw(_score(material=material))) for material in SHEETS}
    for material, marks in bodies.items():
        assert marks, material
    joined = {material: "".join(marks) for material, marks in bodies.items()}
    assert len(set(joined.values())) == len(SHEETS), sorted(
        material for material in SHEETS if list(joined.values()).count(joined[material]) > 1
    )


# --- T-3: a work that names no ground does not move -------------------------

ENGINE_36_UNGROUNDED = (
    "A-brush_thick-line",
    "A-brush_thick-circle",
    "A-chalk-arc",
    "A-pencil-circle",
)


def test_t3_a_work_that_names_no_ground_is_byte_identical_with_engine_36() -> None:
    """T-3. `DEFAULT_SUPPORT` is what a work naming no ground still meets.

    Measured against the frozen engine 36 record rather than against another
    call of today's renderer: comparing the tree with itself would pass on any
    tree. These four state no `ground` at all and are drawn with three tools the
    sheet reaches, so a sheet handed to an ungrounded work would move them.
    """
    generator = _generator()
    previous = json.loads(ENGINE_36_MANIFEST.read_text(encoding="utf-8"))["cases"]
    inputs = generator.build_inputs()
    for case_id in ENGINE_36_UNGROUNDED:
        assert inputs[case_id]["score"]["canvas"]["ground"] is None, case_id
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == previous[case_id]["digest"], case_id


# --- T-4: a tool that does not meet paper does not move ---------------------


def test_t4_the_drafting_pen_is_byte_identical_on_every_sheet() -> None:
    """T-4. `rotring` meets neither quantity, so no sheet can reach it.

    The control for T-2. Without it, "the sheet moves the mark" would be
    satisfied by a change that moved every mark, including the machines' -- and
    a plotter has no contact with paper at all.
    """
    assert TOOL_SUPPORT_BIAS["rotring"] == (0.00, 0.00)
    drawings = {material: _draw(_score("rotring", material=material)) for material in SHEETS}
    marks = {material: "".join(_marks(svg)) for material, svg in drawings.items()}
    assert len(set(marks.values())) == 1, sorted(marks)
    # And the same as the sheet a work naming no ground gets.
    assert set(marks.values()) == {"".join(_marks(_draw(_score("rotring"))))}


# --- T-5, T-6: the two mark words reach the mark ----------------------------


def _drawn_with_the_word_doing_nothing(score: Score, monkeypatch) -> list[str]:
    """The same Score, drawn with the mark word's gain turned off.

    **The control has to be this and not "the same line without a surface".**
    The performance seed is derived from the instruction's own dump, so adding a
    `surface` field re-rolls it and moves the mark for a reason that has nothing
    to do with the sheet -- measured 2026-08-16, and it is what made the first
    version of T-5 and T-6 green under every perturbation that unwired the
    renderer half. Holding the Score fixed and stopping the mechanism keeps the
    seed identical, so what is left in the difference is the sheet.
    """
    monkeypatch.setattr(stroke_engine, "MARK_SUPPORT_GAIN", 1.0)
    try:
        return _marks(_draw(score))
    finally:
        monkeypatch.undo()


def test_t5_grain_on_a_line_changes_that_line(monkeypatch) -> None:
    """T-5. 面: 粒 on a line is the sheet refusing the tool harder.

    Two halves, because the request crosses two layers and either one can drop
    it. **Through `coerce_score`** -- until ddl-engine 20 coerce moved this
    surface off the line before the renderer ever saw it, so a gate that built
    the Score by hand would measure a road production never travelled. **And
    against the mechanism stopped** -- see `_drawn_with_the_word_doing_nothing`.
    """
    with_word = coerce_score(_score("chalk", texture="grain"))
    line = with_word.instructions[0]
    assert line.surface is not None and line.surface.texture == "grain"
    # The word raises the quantity a refused tool meets, and nothing else.
    sheet = support_for_ground("paper")
    raised = support_with_mark_word(sheet, "grain")
    assert raised.tooth == min(SUPPORT_CAP, sheet.tooth * MARK_SUPPORT_GAIN) > sheet.tooth
    assert raised.absorb == sheet.absorb
    assert _marks(_draw(with_word)) != _drawn_with_the_word_doing_nothing(
        with_word, monkeypatch
    )


def test_t6_bleed_on_a_line_changes_that_line(monkeypatch) -> None:
    """T-6. 面: にじみ on a line is the sheet drinking more. Both halves, as T-5."""
    with_word = coerce_score(_score("brush_thick", texture="bleed"))
    line = with_word.instructions[0]
    assert line.surface is not None and line.surface.texture == "bleed"
    sheet = support_for_ground("paper")
    raised = support_with_mark_word(sheet, "bleed")
    assert raised.absorb == min(SUPPORT_CAP, sheet.absorb * MARK_SUPPORT_GAIN) > sheet.absorb
    assert raised.tooth == sheet.tooth
    assert _marks(_draw(with_word)) != _drawn_with_the_word_doing_nothing(
        with_word, monkeypatch
    )


# --- T-7: a closed shape is not worked twice --------------------------------


def test_t7_a_closed_shape_is_not_worked_by_its_own_surface_word() -> None:
    """T-7. A circle's 粒 is its interior, and it is said exactly once.

    **⚠ The contract asked for the contour to be byte-identical to the same
    circle carrying no surface, and that cannot be measured**: the performance
    seed is derived from the instruction's own dump, so adding a `surface` field
    re-rolls the seed and moves the contour for a reason that has nothing to do
    with the sheet (measured 2026-08-16: seed 14267649868722562617 without,
    6333770378296910734 with). That is behaviour older than this contract --
    ddl-engine 18 records folding `solid` out of the seed for the same reason.

    So the claim is put where it can be seen. The sheet an instruction meets is
    decided by `_instruction_support`, and a closed shape must come back with
    the sheet it was given; an open one must not. The drawing then shows the two
    halves of "exactly once": the circle draws an interior surface group and no
    raised sheet, the line raises the sheet and draws no interior.
    """
    assert "circle" in CLOSED_SHAPES
    circle = coerce_score(_score("chalk", texture="grain", primitive="circle"))
    line = coerce_score(_score("chalk", texture="grain"))
    assert circle.instructions[0].surface is not None
    assert line.instructions[0].surface is not None

    for material in SHEETS:
        sheet = support_for_ground(material)
        assert renderer._instruction_support(circle.instructions[0], sheet) == sheet, material
        raised = renderer._instruction_support(line.instructions[0], sheet)
        assert raised != sheet, material
        assert raised.tooth == min(SUPPORT_CAP, sheet.tooth * MARK_SUPPORT_GAIN), material

    # And in the drawing: the interior is drawn for the shape that has one, and
    # only for it.
    assert re.search(r'<g id="surface_[^"]*">', _draw(circle)) is not None
    assert re.search(r'<g id="surface_[^"]*">', _draw(line)) is None


# --- T-8: the ceiling binds --------------------------------------------------


def test_t8_the_ceiling_holds_the_ladder_at_three() -> None:
    """T-8. washi drinks at 2.2 and にじみ doubles it; the sheet stops at 3.0.

    Computed from the product's own constants, and pinned to the exact value
    rather than to an inequality: `<= 3.0` is satisfied by an implementation
    where the ceiling never binds at all, and then raising it would move
    nothing (memory: a clamped value is invisible where the other term binds).
    """
    washi = support_for_ground("washi")
    assert washi.absorb * MARK_SUPPORT_GAIN > SUPPORT_CAP
    capped = support_with_mark_word(washi, "bleed")
    assert capped.absorb == SUPPORT_CAP == 3.0
    assert capped.tooth == washi.tooth
    for material in SHEETS:
        sheet = support_for_ground(material)
        for word in sorted(MARK_SURFACE_WORDS):
            raised = support_with_mark_word(sheet, word)
            assert raised.absorb <= SUPPORT_CAP, (material, word)
            assert raised.tooth <= SUPPORT_CAP, (material, word)


# --- T-9: nobody forgot to hand it over -------------------------------------


def test_t9_every_synthesis_call_is_handed_the_sheet() -> None:
    """T-9. Eleven call sites, eleven hand-overs.

    The sheet travels by argument and not in a module variable, so the way it
    goes missing is a call site nobody edited. Counted from the source: a call
    that got the default would draw on plain paper and say nothing about it.
    """
    source = (SERVER_ROOT / "src" / "inku_server" / "renderer.py").read_text(
        encoding="utf-8"
    )
    call = re.compile(r"\bsynthesize_(?:stroke|along)\(")
    sites = 0
    handed = 0
    for match in call.finditer(source):
        sites += 1
        index = match.end()
        depth = 1
        while depth:
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
            index += 1
        if "support=" in source[match.end() : index - 1]:
            handed += 1
    assert sites == 11, sites
    assert handed == sites, (handed, sites)


# --- T-10: [I-264] is not made worse ----------------------------------------


def test_t10_the_sheet_adds_no_filter_reference() -> None:
    """T-10. Filter references are what [I-264] is decided by, and they do not move.

    Measured across four subjects and eighteen settings before this contract was
    written; this is the guard that keeps it true. The reason is structural: a
    filter is attached where the path is written out, from the tool's name, and
    the sheet rewrites widths and breaks upstream of that -- a break becomes a
    subpath inside the same `d`, not a second element.
    """
    counts = {}
    elements = {}
    for material in ("paper", "canvas"):
        svg = _draw(_score("chalk", material=material), svg_profile="display")
        counts[material] = len(FILTER_REF.findall(svg))
        elements[material] = len(re.findall(r"<(?:path|polyline|polygon)[ />]", svg))
    assert counts["paper"] > 0, "no filter was attached, so this gate saw nothing"
    assert counts["paper"] == counts["canvas"], counts
    assert elements["paper"] == elements["canvas"], elements


# --- T-11: coerce keeps the mark words and moves the rest -------------------


def test_t11_coerce_keeps_a_mark_word_on_a_line_and_moves_the_rest() -> None:
    """T-11. The word decides, and only the two mark words stay.

    Both halves are needed. An implementation that let every surface stay on an
    open shape satisfies the first half and loses the repair engine 15 exists
    for, and the second half is what says the decision was made by the word.
    """
    # Named here rather than read from the set. Walking `MARK_SURFACE_WORDS`
    # makes this loop empty the moment the set is emptied, and an empty loop is
    # green -- measured 2026-08-16, where emptying the set left this gate
    # passing while every request it guards was being dropped again. The set is
    # a decision, so the decision is what gets pinned; the wash contract
    # (render engine 39) adds its word here deliberately.
    assert set(MARK_SURFACE_WORDS) == {"grain", "bleed"}
    for word in ("grain", "bleed"):
        kept = coerce_score(_score("chalk", texture=word))
        line = kept.instructions[0]
        assert line.primitive == "line"
        assert line.surface is not None and line.surface.texture == word, word

    for word in ("wash", "hatch", "crosshatch", "stipple", "paper_grain", "aquatint"):
        assert word not in MARK_SURFACE_WORDS
        moved = coerce_score(_score("chalk", texture=word))
        line = moved.instructions[0]
        assert line.surface is None or line.surface.texture == "none", word
