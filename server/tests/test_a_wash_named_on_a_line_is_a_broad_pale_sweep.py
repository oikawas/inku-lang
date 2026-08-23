"""render engine 38: a wash named on a line is a broad pale sweep.

Contract `a-wash-named-on-a-line-is-a-broad-pale-sweep`. When a description says
`面: 薄墨` and Stage 2 attaches it to a line or an arc, the wash used to reach
nothing at all: `_with_surface_on_a_closed_shape` read every `面: ...` sentence
as a sentence about the shape before it and walked the surface back, dropping it
where there was no shape to walk back to. Measured on 3,458 production works on
2026-08-16, 987 hold a surface still sitting on an open shape and 567 of those
name 薄墨 -- and 490 of the 567 (86.4%) are dropped outright, 354 for having no
closed shape behind them and 136 because that shape already carried a surface.

The reading was wrong for the same reason it was wrong for 粒 and にじみ, which
engine 37 took out of it: a wash is how the ink was diluted, which is something
a line does. So `MARK_SURFACE_WORDS` gains the word, and the renderer performs
it -- the mark is drawn three times as broad at 0.35 of the opacity it would
otherwise have had. The author chose those two numbers on 2026-08-16 from a
contact sheet of four readings (`cli/out2/913-v2.13.26-a-wash-named-on-a-line/`).

T-169..T-177 are the contract's acceptance.

**T-169, T-170 and T-171 go through `coerce_score`.** The reference-corpus
generator imports `renderer` directly and never calls coerce, so a gate that
built its Score by hand would stay green while production dropped every one of
these requests before the renderer ever saw it.

**T-173, T-174 and T-175 compare against digests measured on the engine-37
tree** and frozen in the pre-implementation commit (2026-08-17, before a line of
this version was written). The corpus cannot supply them: it froze not one case
with a wash on an open shape, which is the hole this version exists to fill.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import pathlib
import re
from typing import Any

from inku_server import renderer
from inku_server.coerce import coerce_score
from inku_server.render_engines import current_render_engine
from inku_server.renderer import (
    WASH_MARK_OPACITY_GAIN,
    WASH_MARK_WIDTH_GAIN,
    _mark_width_px,
    _stroke_width_px,
)
from inku_server.schema import MARK_SURFACE_WORDS, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
RENDERER_SOURCE = SERVER_ROOT / "src" / "inku_server" / "renderer.py"
CORPUS_DIR = SERVER_ROOT / "reference" / f"render-engine-{current_render_engine().version}"

# A `d` made only of straight segments: the band the stroke engine lays down.
# The arc's first path is the invisible intent arc and carries an `A`, so this
# skips it rather than measuring the geometry instead of the ink.
BAND_D = re.compile(r'\sd="(M [-\d.LZM ]+)"')
TEXTURE_FILTER_REF = re.compile(r'filter="url\(#(texture-[a-z_]+)\)"')


def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _generator()


def _render_input(primitive: str, weight: str, texture: str | None = None) -> dict[str, Any]:
    """One corpus-shaped case, built by the generator's own helpers.

    Every field is stated the way the frozen corpus states it, so a digest
    measured here and a digest measured there are the same measurement.
    """
    surface = None
    if texture is not None:
        surface = copy.deepcopy(GENERATOR.BASE_SURFACE)
        surface["texture"] = texture
    return {
        "score": GENERATOR._score(
            GENERATOR._instruction(primitive, weight=weight, surface=surface)
        ),
        "render_seed": GENERATOR.DEFAULT_RENDER_SEED,
        "color_map": copy.deepcopy(GENERATOR.DEFAULT_COLOR_MAP),
        "catalog_id": None,
        "svg_profile": "editable",
        "wild": False,
    }


def _digest(primitive: str, weight: str, texture: str | None = None) -> str:
    return GENERATOR._normalized_digest(GENERATOR.render_case(_render_input(primitive, weight, texture)))


def _coerced_score(primitive: str, weight: str, texture: str) -> Score:
    """The Score production would hand the renderer, coerce included."""
    return coerce_score(Score.model_validate(_render_input(primitive, weight, texture)["score"]))


def _draw_coerced(primitive: str, weight: str, texture: str | None) -> str:
    render_input = _render_input(primitive, weight, texture)
    score = coerce_score(Score.model_validate(render_input["score"]))
    return renderer.render(
        score,
        color_map=render_input["color_map"],
        render_seed=render_input["render_seed"],
        svg_profile=render_input["svg_profile"],
    )


def _polygon_area(d: str) -> float:
    """The area a `M x y L x y ... Z` band encloses, subpaths summed."""
    total = 0.0
    for subpath in d.split("M "):
        numbers = [float(value) for value in re.findall(r"-?\d+\.?\d*", subpath)]
        points = list(zip(numbers[0::2], numbers[1::2]))
        if len(points) < 3:
            continue
        total += abs(
            sum(
                points[i][0] * points[(i + 1) % len(points)][1]
                - points[(i + 1) % len(points)][0] * points[i][1]
                for i in range(len(points))
            )
        ) / 2.0
    return total


def _ink(svg: str) -> tuple[float, float]:
    """How much ink the mark laid down, and at what opacity.

    Two shapes of answer, because a line has two drawing paths: every tool but
    `rotring` performs a band (a filled polygon), and `rotring` is an SVG
    `<line>` whose width and opacity come straight from `_stroke_attrs`. A test
    that measured only the first would be blind to exactly the half the
    prototype forgot to wire.
    """
    band = BAND_D.search(svg)
    if band is not None:
        opening = svg.rfind("<path", 0, band.start())
        element = svg[opening : svg.index(">", band.start()) + 1]
        opacity = re.search(r'fill-opacity="([\d.]+)"', element)
        return _polygon_area(band.group(1)), float(opacity.group(1)) if opacity else 1.0
    element = re.search(r"<line\b[^>]*>", svg)
    assert element is not None, "the mark is neither a band nor a line"
    x1, y1, x2, y2 = (
        float(re.search(rf'{key}="([-\d.]+)"', element.group(0)).group(1))
        for key in ("x1", "y1", "x2", "y2")
    )
    width = float(re.search(r'stroke-width="([\d.]+)"', element.group(0)).group(1))
    opacity = re.search(r'stroke-opacity="([\d.]+)"', element.group(0))
    return math.hypot(x2 - x1, y2 - y1) * width, float(opacity.group(1)) if opacity else 1.0


# The three drawing paths an open shape has. `brush_thin` and `rotring` are
# production's top two tools for this request (171 and 92 of 567, measured
# 2026-08-16) and they are also the two halves of a line: a band and an SVG
# `<line>`. The arc goes through `_render_arc_hand_stroke`, a third function
# again -- the one the prototype left unwired, which is why its 刷毛 reading and
# its 濃度 reading came out byte-identical.
WASH_PAIRS = (("line", "brush_thin"), ("line", "rotring"), ("arc", "pencil"))

# Measured on the engine-37 tree on 2026-08-17 and frozen in the
# pre-implementation commit, before a line of this version existed. Not
# regenerated by anything: a record this file rewrote when the code moved would
# be a record, not a gate.
ENGINE_37_DIGESTS = {
    ("square", "brush_thin", "wash"): "470338b7f8c19d1257a2f2ab4bf43f97",
    ("circle", "pencil", "wash"): "3c502eb9096c3348ed6e9a06494b3e6c",
    ("line", "brush_thin", "paper_grain"): "5968cccf65d93da10891cc4a4edbcffc",
    ("line", "brush_thin", "hatch"): "14715ee6f3e87ff514a0a1047262d5a2",
    ("arc", "pencil", "hatch"): "72d62c5a9c58d405b7153fd295bcc767",
    ("line", "chalk", "grain"): "6bc37a6684835c13b63edba8d74f642e",
    ("line", "brush_thin", None): "da6af2082c591f6936b0e7b8892d3e61",
    ("line", "rotring", None): "f5c06def4780521f0bf6be7f474bb00a",
    ("arc", "pencil", None): "ef50972e4e1cf6f092b1eb8f90ff082b",
    ("line", "brush_thick", None): "8600f4a5d60ef5abf1c4e3d133cafe5d",
}


# --- T-169: coerce leaves the wash where the sentence put it -----------------


def test_t169_coerce_keeps_a_wash_on_a_line_and_still_moves_the_rest() -> None:
    """T-169. The word decides, and 薄墨 is now one of the words that stays.

    Both halves are needed. Letting every surface stay on an open shape passes
    the first half and loses the repair ddl engine 15 exists for; the second
    half is what says the decision was made by the word and not by the shape.
    """
    assert "wash" in MARK_SURFACE_WORDS
    for primitive, weight in WASH_PAIRS:
        kept = _coerced_score(primitive, weight, "wash")
        mark = kept.instructions[0]
        assert mark.primitive == primitive, (primitive, weight)
        assert mark.surface is not None, (primitive, weight)
        assert mark.surface.texture == "wash", (primitive, weight)

    # The control: an interior word on the same Score, with no closed shape
    # behind it, is still dropped. 紙目 and 平行線 are the two the contract
    # leaves unruled, so they must not have been carried along.
    for texture in ("paper_grain", "hatch"):
        moved = _coerced_score("line", "brush_thin", texture)
        mark = moved.instructions[0]
        assert mark.surface is None or mark.surface.texture == "none", texture


# --- T-170: the mark comes out broader --------------------------------------


def test_t170_a_wash_line_is_drawn_three_times_as_broad() -> None:
    """T-170. Through coerce, on all three drawing paths.

    The area of the ink rather than the bytes of the `d`: a `d` that differs is
    satisfied by any change at all, including one that only moved the mark, so
    it cannot tell this version from the call site T-172 counts.

    The band's area is not exactly three times the plain one -- the stroke
    engine tapers the ends and the sheet cuts the run, and neither scales with
    the width -- so the drawn claim is a floor and the exact factor is asserted
    of `_mark_width_px`, which is where the number lives.
    """
    for primitive, weight in WASH_PAIRS:
        plain, _ = _ink(_draw_coerced(primitive, weight, None))
        washed, _ = _ink(_draw_coerced(primitive, weight, "wash"))
        assert washed > plain * 2.0, (primitive, weight, plain, washed)

    canvas = renderer.canvas_size_for_aspect("square")
    for primitive, weight in WASH_PAIRS:
        washed_score = _coerced_score(primitive, weight, "wash")
        mark = washed_score.instructions[0]
        assert _mark_width_px(mark, canvas) == (
            _stroke_width_px(mark.weight, canvas, mark.thinness) * WASH_MARK_WIDTH_GAIN
        ), (primitive, weight)


# --- T-171: the mark comes out paler ----------------------------------------


def test_t171_a_wash_mark_is_drawn_at_0_35_of_its_opacity() -> None:
    """T-171. Computed from the product's own constant, not from 0.35.

    Pinned to the exact factor rather than to an inequality: `<= 1.0` is
    satisfied by an implementation that pales nothing at all.
    """
    assert WASH_MARK_OPACITY_GAIN == 0.35
    for primitive, weight in WASH_PAIRS:
        _, plain = _ink(_draw_coerced(primitive, weight, None))
        _, washed = _ink(_draw_coerced(primitive, weight, "wash"))
        assert washed == round(plain * WASH_MARK_OPACITY_GAIN, 6), (
            primitive, weight, plain, washed,
        )
        assert washed < plain, (primitive, weight)


# --- T-172: nobody forgot a call site ---------------------------------------


# Every function that still asks `_stroke_width_px` directly. Two, and they are
# the entrances themselves -- which is the whole claim: a width asked for
# anywhere else is a width that cannot see that the mark was described.
WIDTH_ENTRANCES = ("_mark_width_px", "_nominal_mark_width_px")

# The seven call sites an open shape reaches, by the function that encloses
# them. Named rather than derived: a list built by walking the module is empty,
# and so green, exactly when the wiring has been undone.
OPEN_SHAPE_WIDTH_CALLERS = (
    "_amplitude_px",              # the wobble amplitude of a line or an arc
    "_stroke_attrs",              # rotring and every attrs-drawn mark
    "_material_outline_profile",  # the material tone beside the mark
    "_emit_layer",                # the material line group
    "_render_hand_stroke",        # a performed line
    "_render_arc_hand_stroke",    # a performed arc
)


def _enclosing_function(lines: list[str], index: int) -> str:
    for back in range(index, -1, -1):
        match = re.match(r"\s*def (\w+)", lines[back])
        if match:
            return match.group(1)
    return "<module>"


def test_t172_every_width_is_asked_of_the_one_entrance() -> None:
    """T-172. The prototype wired three call sites and drew the arc unchanged.

    Counted from the source rather than from a drawing, because the failure
    this measures is a call site nobody thought of -- and a drawing only shows
    the ones a test happened to draw. The drawn half is T-170, which covers the
    arc and the attrs path by name for the same reason.
    """
    lines = RENDERER_SOURCE.read_text(encoding="utf-8").splitlines()
    direct = [
        _enclosing_function(lines, index)
        for index, line in enumerate(lines)
        if "_stroke_width_px(" in line and not line.lstrip().startswith("def ")
    ]
    assert sorted(direct) == sorted(WIDTH_ENTRANCES), direct

    entrance_calls = [
        _enclosing_function(lines, index)
        for index, line in enumerate(lines)
        if re.search(r"_(?:mark|nominal_mark)_width_px\(", line)
        and not line.lstrip().startswith("def ")
        and _enclosing_function(lines, index) not in WIDTH_ENTRANCES
    ]
    for caller in OPEN_SHAPE_WIDTH_CALLERS:
        assert caller in entrance_calls, (caller, sorted(set(entrance_calls)))
    # Fifteen, counted 2026-08-17: exactly the fifteen call sites that asked
    # `_stroke_width_px` before this version, with `_material_outline_profile`'s
    # pair now split between the thinned entrance and the nominal one. The count
    # is here so that removing a call site is as visible as forgetting one.
    assert len(entrance_calls) == 15, sorted(entrance_calls)


# --- T-173: a closed shape does not move ------------------------------------


def test_t173_a_closed_shape_wash_is_untouched() -> None:
    """T-173. A closed shape's 薄墨 is its interior, drawn since engine 36.

    Both witnesses at once: two Scores measured on the engine-37 tree before
    this version was written, and the five wash cases the corpus already held,
    whose digests must be the ones engine 37 froze.
    """
    for key in (("square", "brush_thin", "wash"), ("circle", "pencil", "wash")):
        assert _digest(*key) == ENGINE_37_DIGESTS[key], key

    current = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))["cases"]
    previous = json.loads(
        (SERVER_ROOT / "reference" / "render-engine-37" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    frozen_wash = (
        "C-surface-wash-pen",
        "C-surface-wash-pencil",
        "C-display-surface-wash-pen",
        "E-wild-surface-wash-pen",
        "E-wild-surface-wash-pencil",
    )
    for case_id in frozen_wash:
        assert current[case_id]["digest"] == previous[case_id]["digest"], case_id


# --- T-174: the other surface words do not move -----------------------------


def test_t174_a_surface_word_that_is_not_a_wash_is_untouched() -> None:
    """T-174. The decision is made by the word, not by the shape being open.

    紙目 and 平行線 are two the contract leaves unruled, and 粒 belongs to engine
    37 -- all three must draw exactly what they drew the day before this one.
    """
    for key in (
        ("line", "brush_thin", "paper_grain"),
        ("line", "brush_thin", "hatch"),
        ("arc", "pencil", "hatch"),
        ("line", "chalk", "grain"),
    ):
        assert _digest(*key) == ENGINE_37_DIGESTS[key], key


# --- T-175: a mark that names no surface does not move ----------------------


def test_t175_a_mark_with_no_surface_is_untouched() -> None:
    """T-175. The control for the control.

    Without it an implementation that widened every open mark would satisfy
    T-170 and T-171 and be caught by nothing else this file draws.
    """
    for key in (
        ("line", "brush_thin", None),
        ("line", "rotring", None),
        ("arc", "pencil", None),
        ("line", "brush_thick", None),
    ):
        assert _digest(*key) == ENGINE_37_DIGESTS[key], key


# --- T-176: the widest pair, measured -------------------------------------


def test_t176_the_widest_tool_is_measured_and_reported() -> None:
    """T-176. `brush_thick` is the broadest tool, so it is the widest wash.

    **No ceiling is asserted.** `brush_thick` carries 32 of the 567 production
    requests and was not on the contact sheet the author ruled from, so whether
    a cap belongs here is unruled -- the number is reported and the relation is
    what is measured. The Score is built by hand rather than through coerce, so
    that a perturbation of the coerce half lands on T-169..T-171 and this one
    stays a statement about the renderer.
    """
    canvas = renderer.canvas_size_for_aspect("square")
    plain_score = Score.model_validate(_render_input("line", "brush_thick")["score"])
    wash_score = Score.model_validate(_render_input("line", "brush_thick", "wash")["score"])

    plain_area, _ = _ink(renderer.render(plain_score, render_seed=GENERATOR.DEFAULT_RENDER_SEED))
    wash_area, _ = _ink(renderer.render(wash_score, render_seed=GENERATOR.DEFAULT_RENDER_SEED))
    assert wash_area > plain_area

    nominal = _mark_width_px(wash_score.instructions[0], canvas)
    assert nominal == _stroke_width_px("brush_thick", canvas) * WASH_MARK_WIDTH_GAIN
    # Reported, not bounded: 24.0 px of a 1000 px canvas, against 8.0 plain.
    print(
        f"T-176 brush_thick wash band: nominal width {nominal:.3f}px "
        f"(plain {_stroke_width_px('brush_thick', canvas):.3f}px), "
        f"ink area {wash_area:.1f} against {plain_area:.1f}"
    )


# --- T-177: the corpus reaches the texture filters (ledger I-289) -----------


# Measured 2026-08-17 from the baked corpus. Engine 37's number for every one of
# these was zero, because the only `display` cases it held were `pen` and `pen`
# is not in `TEXTURE_SPECS`. `drypoint` is one and only one: it is excluded from
# the general branch by name at every write site and reaches the corpus solely
# through the burr it is drawn with, which is a different claim than "filtered".
FILTER_MARKER_COUNTS = {
    "C-filter-display-pencil": 107,
    "C-filter-display-crayon": 163,
    "C-filter-display-chalk": 94,
    "C-filter-display-brush_thick": 64,
    "C-filter-display-drypoint": 1,
}
GENERAL_BRANCH_TOOLS = ("pencil", "crayon", "chalk", "brush_thick")


def test_t177_the_corpus_traverses_the_texture_filter_branch() -> None:
    """T-177. Engine 37 baked 597 SVGs and not one carried a texture filter.

    Two halves fail for different reasons. The frozen manifest holds each digest
    even when the corpus omits an unchanged raw SVG; the live half redraws the
    same input. A generator that stops asking for `display` is therefore visible
    instead of leaving the frozen record standing as its own witness.

    **`drypoint` appears, and that is the measurement, not a leak.** The
    contract expected it absent because `ins.weight != "drypoint"` guards the
    general branch at every write site -- true, and the version's own reason for
    a case per tool. But `_render_hand_stroke` writes `url(#texture-drypoint)`
    for the raised burr, which is what a drypoint is. So the claim it witnesses
    is exact: one reference, and the general branch fired for it zero times.
    """
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    inputs = GENERATOR.build_inputs()
    live = {}
    for case_id, expected in FILTER_MARKER_COUNTS.items():
        frozen = manifest["cases"][case_id]
        assert inputs[case_id] == frozen["input"]
        svg = GENERATOR.render_case(inputs[case_id])
        assert GENERATOR._normalized_digest(svg) == frozen["digest"]
        live[case_id] = svg

        references = TEXTURE_FILTER_REF.findall(svg)
        assert len(references) == expected, (case_id, len(references))
        assert set(references) == {
            f"texture-{case_id.rsplit('-', 1)[1]}"
        }, (case_id, sorted(set(references)))

    carrying = sum(
        1 for svg in live.values() if TEXTURE_FILTER_REF.search(svg) is not None
    )
    assert carrying > 0, "the corpus reaches no texture filter at all, as in engine 37"

    for tool in GENERAL_BRANCH_TOOLS:
        assert FILTER_MARKER_COUNTS[f"C-filter-display-{tool}"] > 1, tool
    assert FILTER_MARKER_COUNTS["C-filter-display-drypoint"] == 1
