"""Structural checks for the frozen render-engine reference corpus."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re

from inku_server.master_grid import MASTER_GRID_DECIMALS
from inku_server.render_engines import current_render_engine
from inku_server.schema import (
    Arrangement,
    CanvasGroundSpec,
    Instruction,
    Score,
    SurfaceSpec,
)

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_VERSION = current_render_engine().version
CORPUS_DIR = SERVER_ROOT / "reference" / f"render-engine-{ENGINE_VERSION}"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
# Attribution claims belong to a version. Reading them from a later manifest
# silently changes what the claim describes.
ENGINE_18_MANIFEST = SERVER_ROOT / "reference" / "render-engine-18" / "manifest.json"
ENGINE_19_MANIFEST = SERVER_ROOT / "reference" / "render-engine-19" / "manifest.json"
ENGINE_32_MANIFEST = SERVER_ROOT / "reference" / "render-engine-32" / "manifest.json"
ENGINE_33_MANIFEST = SERVER_ROOT / "reference" / "render-engine-33" / "manifest.json"
ENGINE_34_MANIFEST = SERVER_ROOT / "reference" / "render-engine-34" / "manifest.json"
ENGINE_35_MANIFEST = SERVER_ROOT / "reference" / "render-engine-35" / "manifest.json"
ENGINE_36_MANIFEST = SERVER_ROOT / "reference" / "render-engine-36" / "manifest.json"
ENGINE_37_MANIFEST = SERVER_ROOT / "reference" / "render-engine-37" / "manifest.json"
ENGINE_38_MANIFEST = SERVER_ROOT / "reference" / "render-engine-38" / "manifest.json"
ENGINE_39_MANIFEST = SERVER_ROOT / "reference" / "render-engine-39" / "manifest.json"
ENGINE_40_MANIFEST = SERVER_ROOT / "reference" / "render-engine-40" / "manifest.json"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_render_reference", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_render_reference_case_counts() -> None:
    cases = _manifest()["cases"]
    # Engine 18 replaced the catalog data without touching the original 365
    # cases. Group F is now 13 catalogs x 9 abstract colors, six hint cases, and
    # five non-white backgrounds. Engine 20 added group G: the 32 cases that
    # state an `arrangement`, which is the only way to reach placement at all.
    # Engine 22 added six to C: the corpus carried no filled `computer` and no
    # filled `silverpoint`, and no filled instruction with a thinness modifier
    # at all -- so a coverage rule and a list of tool names cut it identically
    # -- and no filled `chalk`, which is the one tool carrying a fill contrast
    # of its own.
    # Engine 23 added four to G: the twins that state a composition seed, which
    # is the only way the corpus reaches the placement seed at all.
    # Engine 24 added six more to G: the corpus stated a fade on one case only,
    # the plainest one, so none of the routes the per-member fade travels --
    # a colour cycle, a derived surface seed, a machine tool, and the two
    # degenerate groups that must not fade -- was walked by it.
    # Engine 25 added four more to G: all 42 groups above are circles, so
    # `radius x k` was the only one of the four member-size rules the corpus
    # could reach -- and a circle is 14.3% of the expanded marks in production
    # against a line's 43.8%.
    # Engine 26 added four more to G: two shapes the angle rule turns that the
    # corpus had never carried (`arc`, the largest target in production at 377
    # groups, and `cloudform`), and two groups that state their own angle, `0`
    # and `30` -- the only sight the corpus has of `is not None` against a
    # truthy test.
    # Engine 30 added four to D: one representative, `ellipse-pen`, drawn on all
    # four aspects. Every `size` in D until then stated its two extents the same,
    # so no case in the corpus could tell a mark that kept the proportion its
    # description gave it from one the canvas had stretched -- and on the pillar
    # engine 29 drew a mark written 1.6:1 wide as 0.32, upright.
    # Engine 31 added sixteen to D: four arrangement subjects -- a ring, a
    # region resolved for one mark, a grid over a region, and a group whose
    # region is only its anchor -- on all four aspects. Of the 553 cases above,
    # the five carrying a `radial` were every one of them square and not one
    # carried an `at.region`, so the corpus could not see either half of the
    # rule that keeps an arrangement's shape off the canvas aspect.
    # Engine 32 added thirteen to D: a cluster and three paths, each on the
    # square canvas and on the papers whose long side is the axis it spreads
    # on. The ten cluster and path cases the corpus already held are every one
    # of them square, so the two arrangements that carry 36.2% of production's
    # expanded marks had no non-square case anywhere in the record.
    # Engine 33 opened group H: the composite unit. Every case above it draws a
    # score of exactly one instruction, so a span -- one repeated unit made of
    # more than one mark -- could not be stated in this corpus at all. Three
    # state a span and `H-pair-scatter-plain` is the control: the same two
    # instructions with no span, which is the picture engine 32 drew.
    # Engine 34 added two to C: `canvas` and `drawing_paper`, the two supports
    # the ground field gained. The ground cases are read from `GroundMaterial`
    # now rather than listed in the generator, so a support that joins the enum
    # and is never baked cannot happen; what can happen is a support joining
    # without anyone deciding to re-freeze, and this count is what stops it.
    # Engine 37 added nine to C. Every one of the nineteen ground cases above is
    # drawn with `pen`, whose meeting with the sheet is (0.15, 0.15), and the
    # arrival probability that carries it is `rate * bias / (n - 4)` -- so small
    # for a pen that four of the seven supports produced no arrival at all and
    # left their case byte-identical. Six of the nine change nothing but the
    # sheet under `brush_thick` (drunk) and `chalk` (refused), two put a mark
    # word on a line, and one is the combination where the ceiling binds.
    # Engine 38 added nine to C, in two groups that must stay countable apart.
    # Four put wash on an open shape: the two drawing paths a line has
    # (`brush_thin` performs a band, `rotring` is an SVG `<line>` written from
    # `_stroke_attrs`), an arc, which is a third function again, and a closed
    # control. Not one of the 597 cases above carried a wash on an open shape,
    # so without them this version's change would not be in the record at all.
    # Five reach the texture filters, which are written only under `display` --
    # and all four `display` cases above are `pen`, which is not a filtered
    # tool, so of 597 baked SVGs the number carrying `filter="url(#texture-`
    # was zero. `drypoint` is the fifth: it is excluded from the general branch
    # by name and writes its burr filter instead, and without its own case that
    # exclusion would be a claim with nobody to test it.
    # Engine 40 adds four profile-boundary cases: editable/display/compat
    # non-computer solid and a display computer control.
    assert len(cases) == 610
    assert {
        prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases)
        for prefix in ("A", "B", "C", "D", "E", "F", "G", "H")
    } == {"A": 88, "B": 72, "C": 88, "D": 61, "E": 119, "F": 128, "G": 50, "H": 4}


def test_render_reference_inputs_are_fully_explicit() -> None:
    generator = _generator()
    instruction_fields = set(generator.BASE_INSTRUCTION)
    score_fields = set(generator.BASE_SCORE)
    assert instruction_fields == {
        field.alias or name for name, field in Instruction.model_fields.items()
    } - {"note"}
    assert score_fields == set(Score.model_fields)
    assert set(generator.BASE_SURFACE) == set(SurfaceSpec.model_fields)
    assert set(generator.BASE_GROUND) == set(CanvasGroundSpec.model_fields)
    # Every field is stated except the span, which is stated only where a case
    # states one: writing `group_size: 1` into the base would move all 582
    # inputs frozen before engine 33 for a span none of them has.
    assert set(generator.BASE_ARRANGEMENT) == set(Arrangement.model_fields) - {
        "group_size"
    }
    for case_id, case in generator.build_inputs().items():
        score = case["score"]
        assert set(score) == score_fields
        # Every instruction, not the first: engine 33's composite cases are the
        # first scores here to hold more than one, and a member stated with
        # fewer fields than its head would be an input this corpus never froze.
        for instruction in score["instructions"]:
            assert set(instruction) == instruction_fields
        if case_id.startswith("F-"):
            assert case["catalog_id"] is not None
            assert any(key.startswith("palette:") for key in case["color_map"])
        else:
            assert case["catalog_id"] is None
            assert set(case["color_map"]) == set(generator.DEFAULT_COLOR_MAP)
        assert case["svg_profile"] in ("editable", "display", "compat")
        assert isinstance(case["render_seed"], int)
        assert isinstance(case["wild"], bool)


def test_render_reference_keeps_the_display_profile_covered() -> None:
    """Keep a counted set of cases on the production-default `display` profile.

    Through Engine 15 the corpus was entirely `editable`, so none of the filter
    or clip paths seen by the author ran. Engine 38 added five cases. Reaching
    `display` is distinct from writing a filter: the first four cases use `pen`,
    which is absent from `TEXTURE_SPECS`. Of 597 frozen SVGs, none contained
    `filter="url(#texture-` in the 2026-08-17 I-289 measurement. This list measures
    only the profile; T-177 separately proves that filters are emitted.
    """
    cases = _generator().build_inputs()
    display = sorted(
        case_id for case_id, case in cases.items() if case["svg_profile"] == "display"
    )
    assert display == [
        "C-display-surface-bleed-pen",
        "C-display-surface-grain-pen",
        "C-display-surface-hatch-pen",
        "C-display-surface-solid-computer",
        "C-display-surface-solid-pen",
        "C-display-surface-wash-pen",
        "C-filter-display-brush_thick",
        "C-filter-display-chalk",
        "C-filter-display-crayon",
        "C-filter-display-drypoint",
        "C-filter-display-pencil",
    ]


def test_engine_18_moves_only_the_catalog_dependent_cases() -> None:
    """The unchanged side states that six-key legacy rendering did not move.

    This is an Engine 18 claim, so it reads the Engine 18 manifest.
    """
    manifest = json.loads(ENGINE_18_MANIFEST.read_text(encoding="utf-8"))
    changed = set(manifest["changed_from_previous"])
    original = {
        case_id for case_id in manifest["cases"] if not case_id.startswith("F-")
    }
    palette = {
        case_id for case_id in manifest["cases"] if case_id.startswith("F-")
    }

    assert len(original) == 365
    assert len(palette) == 128
    # 27 cases the three new catalogs brought, one for the relocated purple
    # case, and 42 whose hex moved because their catalog's data was replaced.
    # The other 58 F cases held still: engine 18 changes data, not the chain.
    assert len(changed) == 70
    assert changed <= palette
    assert not (changed & original)


def test_engine_19_moves_the_tools_the_sheet_meets_and_no_others() -> None:
    """Attribute the 227 cases moved by Engine 19.

    Ground resistance is a tool property, so the moved/unchanged boundary follows
    tools. If any machine-only case moved, resistance became a whole-work effect.
    This is an Engine 19 claim and reads that manifest; reading the current one
    would silently replace it with Engine 20's set of 32 moved cases.
    """
    manifest = json.loads(ENGINE_19_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "19"
    changed = set(manifest["changed_from_previous"])
    assert len(changed) == 227

    inputs = _generator().build_inputs()

    def tools(case_id: str) -> set[str]:
        return {
            instruction.get("weight")
            for instruction in inputs[case_id]["score"].get("instructions", [])
        }

    machines_only = {
        case_id
        for case_id in manifest["cases"]
        if tools(case_id) and tools(case_id) <= {"rotring", "computer"}
    }
    assert machines_only, "機械だけのケースが無ければ、下の主張は恒真である"
    assert not (changed & machines_only)

    # Arrival is sparse, so some hand-tool cases remain unchanged (72 of 86 brush
    # cases move). Use complete control groups: all 16 brush_thin-only cases and
    # all 30 crayon-only cases. A missing member would make the machine claim weak.
    for group, expected in (({"brush_thin"}, 16), ({"crayon"}, 30)):
        only = {
            case_id
            for case_id in manifest["cases"]
            if tools(case_id) and tools(case_id) <= group
        }
        assert len(only) == expected, (group, len(only))
        assert only <= changed, sorted(only - changed)


ENGINE_32_NEW_CASES = {
    f"D-canvas-{aspect}-{subject}"
    for subject, aspects in (
        ("cluster", ("square", "pillar", "vertical", "wide")),
        ("path-wave", ("square", "pillar", "vertical")),
        ("path-diagonal", ("square", "pillar", "vertical", "wide")),
        ("path-top_to_bottom", ("square", "wide")),
    )
    for aspect in aspects
}


def test_engine_32_moves_only_its_own_new_cluster_and_path_cases() -> None:
    """Engine 32 moved only the thirteen cases it added.

    Engine 32 is an identity on square canvases, so all 569 existing cases should
    remain byte-identical. A non-empty diff proves nothing because every new ID is
    counted as changed (`case_id not in before`). The manifest cannot distinguish
    nine moving cases from four controls; perturbation supplies that power. This
    check only proves that the moved set equals the thirteen new cases.

    It reads the Engine 32 manifest so Engine 33 cannot silently replace the claim.
    """
    manifest = json.loads(ENGINE_32_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "32"
    assert set(manifest["changed_from_previous"]) == ENGINE_32_NEW_CASES
    assert len(ENGINE_32_NEW_CASES) == 13


def test_engine_33_moves_only_its_own_composite_cases() -> None:
    """Engine 33 moved only the four composite cases it added.

    This version added vocabulary, so the existing 582 cases must stay identical.
    `group_size=1` is omitted from serialization, leaving every prior input intact.
    New IDs always count as changed, so perturbation supplies discrimination.

    Version agreement is checked here so the manifest records the running engine.
    """
    manifest = json.loads(ENGINE_33_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "33"
    assert set(manifest["changed_from_previous"]) == {
        "H-pair-cycle-unit",
        "H-pair-radial-unit",
        "H-pair-scatter-plain",
        "H-pair-scatter-unit",
    }
    previous = json.loads(ENGINE_32_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id.startswith("H-"):
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 582


# Thirteen ground cases: two new IDs and eleven existing cases with material.
# `C-ground-plain` is excluded because asking for no ground is not a ground.
ENGINE_34_GROUND_CASES = {
    "C-ground-canvas",
    "C-ground-charcoal_ground",
    "C-ground-drawing_paper",
    "C-ground-field-density",
    "C-ground-field-opacity",
    "C-ground-ink_wash",
    "C-ground-mezzotint",
    "C-ground-paper",
    "C-ground-washi",
    "C-groundseed-auto-coarse",
    "C-groundseed-auto-paper",
    "C-groundseed-auto-paper-opacity",
    "C-groundseed-auto-washi",
}


def test_engine_34_moves_only_the_ground_cases() -> None:
    """Engine 34 moved only the thirteen cases that carry a ground.

    It replaced profile-specific ground construction with `<pattern>`, so the 575
    cases without a ground must remain byte-identical. Any movement there reaches
    outside the ground layer.

    `C-ground-plain` must not be changed because a `plain` Score emits no ground
    layer. New IDs always count as changed, leaving the other eleven cases and the
    575 unchanged cases as the discriminating evidence.

    The yardstick is Engine 34's frozen manifest; Engine 35 checks version agreement.
    """
    manifest = json.loads(ENGINE_34_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "34"
    assert set(manifest["changed_from_previous"]) == ENGINE_34_GROUND_CASES
    assert "C-ground-plain" not in ENGINE_34_GROUND_CASES
    previous = json.loads(ENGINE_33_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_34_GROUND_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 575


# Nine hatch/crosshatch cases, counted by
# `input.score.instructions[].surface.texture`, not by case name. Name matching
# mixes three ground cases into wash and makes six wash cases look like eight.
# All nine use `square` and `spacing_gradient=none` (measured 2026-08-15).
ENGINE_35_HATCH_CASES = {
    "C-display-surface-hatch-pen",
    "C-surface-hatch-pen",
    "C-surface-hatch-pencil",
    "E-wild-surface-hatch-pen",
    "E-wild-surface-hatch-pencil",
    "C-surface-crosshatch-pen",
    "C-surface-crosshatch-pencil",
    "E-wild-surface-crosshatch-pen",
    "E-wild-surface-crosshatch-pencil",
}
# The six wash cases. **Counted from
# `input.score.instructions[].surface.texture`, not from the case name** -- by
# name, `C-ground-ink_wash`, `C-ground-washi` and `C-groundseed-auto-washi` mix
# in and six look like eight. Engines 33 / 34 / 35 all hold the same six, and
# these are the six engine 36 moves. **Two tests use this set from opposite
# sides** -- engine 35 from the side that left them alone, engine 36 from the
# side that moved them.
ENGINE_36_WASH_CASES = {
    "C-display-surface-wash-pen",
    "C-surface-wash-pen",
    "C-surface-wash-pencil",
    "E-wild-surface-wash-pen",
    "E-wild-surface-wash-pencil",
    "G-fade-surface-edge",
}


def test_engine_35_moves_only_the_hatch_cases() -> None:
    """Engine 35 moved only the nine cases that carry hatch or crosshatch.

    It is the version that clipped the lines at the contour, so **the 579 cases
    whose surface texture is neither hatch nor crosshatch are right to be
    byte-identical**. If even one of them moved, the clipping reached into
    another branch (touching `_scanline_segments` drags the wash and the fills
    along with it).

    No case id here is new. **So all nine carry discriminating power** -- unlike
    the ground version (engine 34), this one can be measured from the changed
    side as well.

    ⚠ Engine 36 exists now, so the yardstick moved from the current manifest to
    engine 35's frozen manifest (the same shape as the engine 33 and 34 tests).
    Version agreement is watched by the engine 36 test.
    """
    manifest = json.loads(ENGINE_35_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "35"
    assert set(manifest["changed_from_previous"]) == ENGINE_35_HATCH_CASES
    previous = json.loads(ENGINE_34_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_35_HATCH_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 579


def test_engine_35_hatch_cases_match_the_current_renderer() -> None:
    """Redraw the nine moved cases with the live renderer, not frozen records.

    The preceding checks compare manifests and render no byte. Seven hatch-breaking
    perturbations (P-1 through P-7) left all of them green: they inspect a record
    that can be rebaked, not the renderer. This check proves that the nine cases
    still match the current engine.

    Rendering goes through the generator's own call so its argument contract cannot
    change while this test remains green on a copied old invocation.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_35_HATCH_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == (
            manifest["cases"][case_id]["digest"]
        ), case_id
        checked += 1
    assert checked == 9


def test_engine_35_left_the_wash_cases_alone() -> None:
    """Engine 35 left the six wash cases alone. **This is a claim about history.**

    Engine 35 clipped lines at the contour, and what it clipped was hatch and
    crosshatch only. Had the same clipping reached the wash, it would not hide
    among the 579 -- this single test would catch it.

    ⚠ **This test used to draw as well** -- "the wash the current tree draws is
    the wash of engine 34". Engine 36 moved the wash, so the drawing half was
    taken over by `test_engine_36_wash_cases_match_the_current_renderer`.
    **It was pointed elsewhere rather than deleted**, because engine 35's own
    claim stays true (a frozen record does not move whatever later versions do).
    The name went from `leaves` to `left` for the same reason -- left in the
    present tense, it reads as a test about the current tree.
    """
    manifest = json.loads(ENGINE_35_MANIFEST.read_text(encoding="utf-8"))
    previous = json.loads(ENGINE_34_MANIFEST.read_text(encoding="utf-8"))["cases"]
    checked = 0
    for case_id in sorted(ENGINE_36_WASH_CASES):
        assert case_id in manifest["cases"], case_id
        assert manifest["cases"][case_id]["digest"] == previous[case_id]["digest"], case_id
        checked += 1
    assert checked == 6
    assert not ENGINE_36_WASH_CASES & ENGINE_35_HATCH_CASES


def test_engine_36_moves_only_the_wash_cases() -> None:
    """Engine 36 moved only the six cases whose surface texture is `wash`.

    The version moved the sweep's width and its opacity and nothing else, so
    **the 582 cases that carry no wash are right to be byte-identical**. If even
    one of them moved, the hand reached outside the wash branch (touching
    `_scanline_segments` drags the fills and the hatch along with it).

    No case id here is new. **So all six carry discriminating power.**

    Version agreement is watched here too. If `default.py` and the manifest
    drift apart, the corpus is a record of some implementation other than the
    one that runs.
    """
    # Read by name, not through `_manifest()`. An attribution is a claim about
    # one version, and reading the current manifest would swap the subject of
    # the claim the day the next version froze -- which is what happened here
    # when engine 37 arrived and this line still said "36".
    manifest = json.loads(ENGINE_36_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "36"
    assert set(manifest["changed_from_previous"]) == ENGINE_36_WASH_CASES
    previous = json.loads(ENGINE_35_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_36_WASH_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 582


def test_engine_36_wash_cases_match_the_current_renderer() -> None:
    """Redraw the six that moved with the live renderer, not the frozen record.

    **⚠ The test above compares manifest against manifest and redraws not one
    byte.** That was measured during the engine 35 cycle -- perturbations that
    move the wash's opacity left the manifest-to-manifest comparison green.
    **That one is a record that gets rebaked, not a test of the renderer.**
    This is where "the six of this version are what the current tree draws"
    gets measured.

    The drawing goes through bake's own call. Copying the arguments out would
    leave this test green in the old calling convention on the day the
    generator stops sending a key.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_36_WASH_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == (
            manifest["cases"][case_id]["digest"]
        ), case_id
        checked += 1
    assert checked == 6


ENGINE_37_SHEET_CASES = frozenset(
    {
        # New: the sheet under the two tools that reach the two quantities.
        "C-sheet-plain-brush_thick",
        "C-sheet-washi-brush_thick",
        "C-sheet-canvas-brush_thick",
        "C-sheet-plain-chalk",
        "C-sheet-washi-chalk",
        "C-sheet-canvas-chalk",
        # New: a mark word on a line, and the pair the ceiling binds.
        "C-sheet-line-grain",
        "C-sheet-line-bleed",
        "C-sheet-cap",
        # Carried over and moved: the three ground cases whose pen crossed the
        # arrival threshold. The other sixteen ground cases did not move.
        "C-ground-washi",
        "C-ground-ink_wash",
        "C-groundseed-auto-washi",
    }
)


def test_engine_37_moves_only_the_sheet_cases() -> None:
    """Engine 37 moved the twelve the sheet reaches and nothing else.

    Nine are new and three are carried over. **The three are the measurement,
    not a gap**: every ground case in this corpus is drawn with `pen`, whose
    meeting with the sheet is (0.15, 0.15), and the arrival probability that
    carries the sheet is `rate * bias / (n - 4)`. At a pen's bias that number is
    around 0.005, so an arrival is rare -- only `washi` and `ink_wash`, the two
    supports that drink more than paper does, pushed it far enough for a centre
    to land at all. The four that refuse harder (`charcoal_ground`, `canvas`,
    `drawing_paper`, `mezzotint`) left their pen case byte-identical, which is
    exactly why the nine new cases are drawn with `brush_thick` and `chalk`.

    Everything outside the ground is right to be byte-identical: a work that
    names no ground keeps `DEFAULT_SUPPORT`, and `paper` restates it.

    This reads the Engine 37 manifest. Reading the current manifest silently
    replaced the claim with the Engine 38 diff when that version was frozen.
    """
    manifest = json.loads(ENGINE_37_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "37"
    assert set(manifest["changed_from_previous"]) == ENGINE_37_SHEET_CASES
    previous = json.loads(ENGINE_36_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_37_SHEET_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 585


def test_engine_37_sheet_cases_match_the_current_renderer() -> None:
    """Redraw the twelve that moved with the live renderer, not the frozen record.

    **⚠ The test above compares manifest against manifest and redraws not one
    byte**, the same way engines 35 and 36 found out. This is where "the twelve
    of this version are what the current tree draws" gets measured, and it is
    the only place in this file that traverses the sheet at all: the other live
    redraws here (group G, group F, engine 32, 35 and 36) hold no case that
    names a ground.

    The drawing goes through bake's own call so a key the generator stops
    forwarding is seen here instead of being copied into this test too.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_37_SHEET_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == (
            manifest["cases"][case_id]["digest"]
        ), case_id
        checked += 1
    assert checked == 12


ENGINE_38_WASH_CASES = frozenset(
    {
        # New: wash on the three drawing paths an open shape has.
        "C-wash-line-brush_thin",
        "C-wash-line-rotring",
        "C-wash-arc-pencil",
        # New: the control the closed-shape exclusion is measured by.
        "C-wash-closed-control",
    }
)
ENGINE_38_FILTER_CASES = frozenset(
    {
        "C-filter-display-pencil",
        "C-filter-display-crayon",
        "C-filter-display-chalk",
        "C-filter-display-brush_thick",
        "C-filter-display-drypoint",
    }
)


def test_engine_38_moves_only_its_own_new_cases() -> None:
    """Engine 38 moved the nine it added and not one case that was here.

    **Byte-identity of the other 597 is the claim, not a gap.** The version
    widens and pales a mark whose surface says wash, and wash sat on an open shape in
    exactly zero of the cases frozen before it -- the three open-shape surfaces
    in the corpus are Engine 37's grain and bleed, which this version decides by
    word and leaves alone. So a diff of anything but the nine would be this
    version reaching a mark nobody described that way.

    Every new ID counts in `changed_from_previous` through the generator's
    `case_id not in before` rule. This check only proves that the moved set equals
    the nine new cases; perturbation proves what those cases actually exercise.
    """
    manifest = json.loads(ENGINE_38_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "38"
    assert set(manifest["changed_from_previous"]) == (
        ENGINE_38_WASH_CASES | ENGINE_38_FILTER_CASES
    )
    assert len(ENGINE_38_WASH_CASES) == 4
    assert len(ENGINE_38_FILTER_CASES) == 5
    previous = json.loads(ENGINE_37_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_38_WASH_CASES or case_id in ENGINE_38_FILTER_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 597


def test_engine_38_new_cases_match_the_current_renderer() -> None:
    """Redraw the nine with the live renderer, not the frozen record.

    **⚠ The test above compares manifest against manifest and redraws not one
    byte**, the same way engines 35, 36 and 37 found out. This is the only
    place that traverses wash on an open shape at all: of the other live
    redraws in this file, group G, group F and engine 32 hold no surface on an
    open shape, and engines 35, 36 and 37 hold no wash on one.

    The drawing goes through bake's own call so a key the generator stops
    forwarding is seen here instead of being copied into this test too.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_38_WASH_CASES | ENGINE_38_FILTER_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == (
            manifest["cases"][case_id]["digest"]
        ), case_id
        checked += 1
    assert checked == 9


ENGINE_39_GRAIN_CASES = frozenset(
    {
        "C-display-surface-grain-pen",
        "C-surface-grain-pen",
        "C-surface-grain-pencil",
        "E-wild-surface-grain-pen",
        "E-wild-surface-grain-pencil",
    }
)


def test_engine_39_moves_only_the_grain_cases() -> None:
    """Engine 39 moves exactly the five grain serialisations and preserves 601 cases."""
    manifest = json.loads(ENGINE_39_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "39"
    assert set(manifest["changed_from_previous"]) == ENGINE_39_GRAIN_CASES
    previous = json.loads(ENGINE_38_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_39_GRAIN_CASES:
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 601


def test_engine_39_grain_cases_match_the_current_renderer() -> None:
    """The five changed records are regenerated through the bake's own call."""
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_39_GRAIN_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == manifest["cases"][case_id]["digest"], case_id
        checked += 1
    assert checked == 5


ENGINE_40_SOLID_PROFILE_CASES = frozenset(
    {
        "C-surface-solid-pen",
        "C-display-surface-solid-pen",
        "C-compat-surface-solid-pen",
        "C-display-surface-solid-computer",
    }
)


def test_engine_40_moves_only_the_solid_profile_cases() -> None:
    """Engine 40 adds four solid-profile cases and preserves all 606 prior cases."""
    manifest = json.loads(ENGINE_40_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "40"
    assert set(manifest["changed_from_previous"]) == ENGINE_40_SOLID_PROFILE_CASES
    previous = json.loads(ENGINE_39_MANIFEST.read_text(encoding="utf-8"))["cases"]
    carried = 0
    for case_id, case in manifest["cases"].items():
        if case_id in ENGINE_40_SOLID_PROFILE_CASES:
            assert case_id not in previous, case_id
            continue
        assert case_id in previous, case_id
        assert case["digest"] == previous[case_id]["digest"], case_id
        carried += 1
    assert carried == 606


def test_engine_37_records_a_sheet_the_paper_and_the_canvas_do_not_share() -> None:
    """The six paired cases must not be six copies of one drawing.

    A record where the sheet changed and the digest did not would be a version
    that says it moved the mark and did not, which is the state engine 34 froze
    without noticing: its two new supports were `pen` cases and the pen never
    reached them.
    """
    cases = _manifest()["cases"]
    for tool in ("brush_thick", "chalk"):
        digests = {
            material: cases[f"C-sheet-{material}-{tool}"]["digest"]
            for material in ("plain", "washi", "canvas")
        }
        assert len(set(digests.values())) == 3, (tool, digests)


def test_engine_35_hatch_cases_keep_the_pitch_they_had() -> None:
    """None of the nine moved cases changed hatch spacing.

    Author ruling 3 keeps line-making regular when clipped inside a shape. Spacing
    is exposed as a `hatch-spacing-*` class, so the corpus can verify it separately
    from digest movement. `C-surface-hatch-pen` was already 21.250 at `189fedc7`.
    """
    manifest = _manifest()
    previous = json.loads(ENGINE_34_MANIFEST.read_text(encoding="utf-8"))["cases"]
    for case_id in sorted(ENGINE_35_HATCH_CASES):
        now = {
            value
            for entry in manifest["cases"][case_id]["classes"]
            for value in re.findall(r"hatch-spacing-[0-9.]+", entry)
        }
        before = {
            value
            for entry in previous[case_id]["classes"]
            for value in re.findall(r"hatch-spacing-[0-9.]+", entry)
        }
        assert now and now == before, (case_id, sorted(before), sorted(now))
    assert "hatch-spacing-21.250" in {
        value
        for entry in manifest["cases"]["C-surface-hatch-pen"]["classes"]
        for value in re.findall(r"hatch-spacing-[0-9.]+", entry)
    }


def test_engine_32_cases_match_the_current_renderer() -> None:
    """Redraw the thirteen new cases with the live renderer, not frozen records.

    Other checks compare frozen SVGs with manifests and stay green if `_path_pos`
    or `_clustered_pos` breaks. The live group-G check also uses only square cases
    and reaches none of Engine 32's rules. This is the sole live non-square route.

    Rendering goes through the generator's own call so its argument contract cannot
    change while this test remains green on a copied old invocation.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id in sorted(ENGINE_32_NEW_CASES):
        svg = generator.render_case(inputs[case_id])
        assert generator._normalized_digest(svg) == (
            manifest["cases"][case_id]["digest"]
        ), case_id
        checked += 1
    assert checked == 13


def test_engine_18_palette_cases_cover_the_resolution_chain() -> None:
    generator = _generator()
    inputs = generator.build_inputs()
    cases = _manifest()["cases"]
    catalog_cases = {
        case_id: case
        for case_id, case in inputs.items()
        if case_id.startswith("F-catalog-")
    }

    assert {case["catalog_id"] for case in catalog_cases.values()} == {
        str(catalog["id"]) for catalog in generator.COLOR_CATALOGS
    }
    assert {
        case["score"]["instructions"][0]["color"]
        for case in catalog_cases.values()
    } == set(generator.ABSTRACT_COLORS)

    assert cases["F-hint-deep-blue"]["digest"] != cases[
        "F-catalog-ink_season-black"
    ]["digest"]
    assert cases["F-hint-vertical"]["digest"] == cases[
        "F-catalog-ink_season-black"
    ]["digest"]
    assert cases["F-hint-restored"]["digest"] == cases[
        "F-catalog-default-gray"
    ]["digest"]
    # ink_season's red band holds two colors; the work assignment picks Madder.
    assert "#8c2d1d" in _resolve_svg("F-hint-sakura").read_text()
    # The empty-band witness moved to sea_stone: engine 18's default catalog has
    # a purple, and sea_stone's purple is the one band left empty by ruling. The
    # stand-in is Night Sea, which is also this catalog's blue.
    assert "#191970" in _resolve_svg(
        "F-hint-missing-purple-sea-stone"
    ).read_text()
    assert "#b06a2f" in _resolve_svg("F-hint-brown").read_text()
    assert all(
        inputs[case_id]["score"]["background"] != "white"
        for case_id in inputs
        if case_id.startswith("F-background-")
    )


def test_engine_18_palette_cases_match_the_current_renderer() -> None:
    """Group F must traverse the live resolver, not only frozen SVG files."""
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    for case_id, render_input in inputs.items():
        if not case_id.startswith("F-"):
            continue
        svg = generator.render_case(render_input)
        assert generator._normalized_digest(svg) == manifest["cases"][case_id]["digest"]


def test_group_g_matches_the_current_renderer() -> None:
    """Group G must traverse the live placement stage, not only frozen files.

    Nothing else in this file re-renders anything: the other tests compare
    frozen SVG with the frozen manifest, so a change to `_expand_arrangement`
    leaves them all green. Group G is the only corpus group that reaches
    placement at all, and this is the only test that runs it.
    """
    generator = _generator()
    manifest = _manifest()
    inputs = generator.build_inputs()
    checked = 0
    for case_id, render_input in inputs.items():
        if not case_id.startswith("G-"):
            continue
        # Through the bake's own call, so that a key the generator stops
        # forwarding is seen here instead of being copied into this test too.
        svg = generator.render_case(render_input)
        assert generator._normalized_digest(svg) == manifest["cases"][case_id]["digest"], case_id
        checked += 1
    assert checked == 50


def test_render_reference_discriminator_cases() -> None:
    cases = _manifest()["cases"]
    square = cases["D-canvas-square-arc-brush-thick"]
    pillar = cases["D-canvas-pillar-arc-brush-thick"]
    assert square["digest"] != pillar["digest"]

    ordinary = cases["D-seed-12345"]
    for seed in (2**63 + 1, 2**64 - 1):
        high = cases[f"D-unsigned-seed-{seed}"]
        assert high["input"]["render_seed"] > 2**63
        assert high["digest"] != ordinary["digest"]

    # Engine 16 stage 2 made the tiny case explicitly a dab; Engine 15 could only
    # show that it was not scan-filled because the area-fill fallback had no class.
    # Keep this paired with the scan behavior above the boundary.
    tiny = cases["D-size-tiny-filled-circle"]
    assert not any("fill-stroke-v1" in name for name in tiny["classes"])
    assert "fill-dab-v1" in tiny["classes"]
    boundary = cases["C-tinyfill-boundary-pen"]
    # Engine 22 moved pen at coverage 0.167 to the texture branch. This boundary
    # checks only that it is area-filled rather than dabbed, so either branch is valid.
    assert any(
        name.startswith(("fill-stroke-v1", "fill-texture-v1"))
        for name in boundary["classes"]
    )
    assert "fill-dab-v1" not in boundary["classes"]
    # The machine extreme remains an area fill at every size and emits no class.
    assert cases["C-tinyfill-circle-rotring"]["classes"] == []

    # Engine 16 stage 1: the production-default display profile reaches brushwork.
    display = cases["C-display-surface-wash-pen"]
    assert any("surface-stroke-v1" in name.split() for name in display["classes"])

    # Engine 16 stage 3: thinness changes the drawing, but silverpoint is already
    # at the width floor. It still enters the performance seed, so the hand changes.
    thin = {
        key: cases[f"C-thinness-{key}"]
        for key in (
            "default-pen", "fine-pen", "extra_fine-pen",
            "fine-silverpoint", "extra_fine-silverpoint",
        )
    }
    assert len({case["digest"] for case in thin.values()}) == 5


def _resolve_svg(case_id: str) -> pathlib.Path:
    """Find a case body by walking back to the last version that moved it.

    An unchanged case has no SVG in the current version directory; the prior body
    remains current. Being able to follow that chain is the point of SPEC §15.7.
    """
    reference_root = MANIFEST_PATH.parent.parent
    versions = sorted(
        (int(path.name.rsplit("-", 1)[-1]), path)
        for path in reference_root.glob("render-engine-*")
        if path.name.rsplit("-", 1)[-1].isdigit()
        and int(path.name.rsplit("-", 1)[-1]) <= int(ENGINE_VERSION)
    )
    for _, directory in reversed(versions):
        candidate = directory / f"{case_id}.svg"
        if candidate.exists():
            return candidate
    raise AssertionError(f"no frozen SVG for {case_id} in any version up to {ENGINE_VERSION}")


def test_render_reference_svg_files_match_manifest() -> None:
    manifest = _manifest()
    generator = _generator()
    for case_id, case in manifest["cases"].items():
        svg = _resolve_svg(case_id).read_text(encoding="utf-8")
        assert len(svg.encode("utf-8")) == case["bytes"]
        assert generator._normalized_digest(svg) == case["digest"]


def test_corpus_bodies_match_the_changed_case_set() -> None:
    """Unchanged cases have no body; the prior version's body remains current.

    This makes files in a version directory mean exactly what that version moved.
    Copying every case into every version would erase that meaning.
    """
    manifest = _manifest()
    changed = set(manifest["changed_from_previous"])
    bodies = {path.stem for path in MANIFEST_PATH.parent.glob("*.svg")}
    assert bodies == changed
    unchanged = set(manifest["cases"]) - changed
    if not unchanged:
        assert ENGINE_VERSION == "41"
        assert changed == set(manifest["cases"])
        return
    for case_id in unchanged:
        assert _resolve_svg(case_id).parent != MANIFEST_PATH.parent


def test_every_corpus_number_uses_at_most_master_grid_precision() -> None:
    """Engine 41 may compact zeroes but never exceeds the six-decimal grid."""
    off_grid = []
    checked = 0
    files = sorted(CORPUS_DIR.glob("*.svg"))
    for path in files:
        for name, value in re.findall(r'([\w:-]+)="([^"]*)"', path.read_text()):
            if name in ("class", "id", "version"):
                continue
            for decimals in re.findall(r"\d+\.(\d+)", value):
                checked += 1
                if not 1 <= len(decimals) <= MASTER_GRID_DECIMALS:
                    off_grid.append((path.name, name, decimals))
    assert len(files) == len(_manifest()["changed_from_previous"])
    assert checked > 2_400, checked
    assert off_grid == []
