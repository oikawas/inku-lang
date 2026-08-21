"""Generate the frozen render-engine reference corpus.

Run from ``server/`` with the repository-standard uv cache environment.
Every render input is literal: no schema defaults, renderer color map, color
catalog, or coerce path supplies fixture values.
"""

from __future__ import annotations

from collections.abc import Iterator
import contextlib
import copy
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any, get_args

from inku_server import renderer
from inku_server.color_catalogs import COLOR_CATALOGS, render_color_map_for_catalog
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import GroundMaterial, Instruction, Score

REFERENCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "reference"
ENGINE = current_render_engine()
ENGINE_VERSION = ENGINE.version
OUTPUT_DIR = REFERENCE_ROOT / f"render-engine-{ENGINE_VERSION}"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

CORPUS_FORMAT_VERSION = "2"
SCHEMA_VERSION = "0.1.0"
FROZEN_AT = "2026-08-21"
REASON = (
    "Non-computer solid surfaces now keep a real base fill and use a deterministic "
    "standard SVG mottle filter in editable and display output. Compat keeps a "
    "filter-free flat vector base fill, and computer keeps its periodic scan. Engine 40 "
    "adds the four direct cases C-surface-solid-pen, C-display-surface-solid-pen, "
    "C-compat-surface-solid-pen, and C-display-surface-solid-computer."
)
SVG_PROFILE = "editable"
DEFAULT_RENDER_SEED = 12345

TOOLS = (
    "brush_thick", "brush_thin", "burin", "chalk", "computer", "crayon",
    "drypoint", "pen", "pencil", "rotring", "silverpoint",
)
PRIMITIVES = (
    "line", "circle", "ellipse", "triangle", "square", "polygon", "arc", "cloudform",
)
ABSTRACT_COLORS = (
    "white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple",
)

# Literal copies. Do not replace these with renderer or catalog imports.
DEFAULT_COLOR_MAP = {
    "white": "#ffffff", "black": "#111111", "blue": "#2c3e91",
    "red": "#a2342a", "green": "#2f6b3a", "gray": "#888888",
}
VIVID_MATERIAL_COLOR_MAP = {
    "white": "#f4f4f4", "black": "#1c1c1c", "blue": "#73c2fb",
    "red": "#f50087", "green": "#008f39", "gray": "#7d6f66",
}

BASE_INSTRUCTION: dict[str, Any] = {
    "primitive": "line", "from": [0.18, 0.50], "to": [0.82, 0.50],
    "center": None, "radius": None, "sides": None, "position": None,
    "size": None, "angle_start": None, "angle_end": None, "rotation": None,
    "filled": False, "style": "solid", "weight": "pen", "thinness": None,
    "mode": "additive",
    "carve_depth": None, "color": "black", "color_hint": None,
    "variation": None, "arrangement": None, "at": None, "relation": None,
    "surface": None,
}
BASE_SCORE: dict[str, Any] = {
    "version": "0.1.0",
    "canvas": {"aspect": "square", "ground": None},
    "background": "white",
    "presence": None,
    "instructions": [],
}
BASE_SURFACE: dict[str, Any] = {
    "texture": "stipple", "density": 0.55, "scale": 0.40, "opacity": 0.36,
    "bleed": 0.25, "direction": "diagonal_rising", "spacing_gradient": "none",
    "tone_steps": 3, "seed": 24680,
}
BASE_GROUND: dict[str, Any] = {
    "material": "plain", "tone": "off_white", "grain": "medium",
    "density": 0.45, "opacity": 0.16, "seed": 13579,
}
BASE_ARRANGEMENT: dict[str, Any] = {
    "count": 60, "layout": "scatter", "rows": None, "cols": None, "jitter": 0.12,
    "path": "none", "color_cycle": [], "margin": 0.1, "center": None,
    "radius": None, "density": "none", "cluster_count": None, "fade": "none",
    "preserve_space": False, "rhythm_spacing": "none",
}
# Group G's anchors. "edge" is the one under which the frame correction fires.
G_ANCHORS: dict[str, list[float]] = {
    "center": [0.5, 0.5], "corner": [0.2, 0.2], "edge": [0.85, 0.85],
}
GEOMETRY: dict[str, dict[str, Any]] = {
    "line": {"from": [0.18, 0.50], "to": [0.82, 0.50]},
    "circle": {"from": None, "to": None, "center": [0.50, 0.50], "radius": 0.24},
    "ellipse": {"from": None, "to": None, "center": [0.50, 0.50], "size": [0.48, 0.30]},
    "triangle": {"from": None, "to": None, "position": [0.28, 0.28], "size": [0.44, 0.44]},
    "square": {"from": None, "to": None, "position": [0.28, 0.28], "size": [0.44, 0.44]},
    "polygon": {"from": None, "to": None, "center": [0.50, 0.50], "radius": 0.25, "sides": 7},
    "arc": {"from": None, "to": None, "center": [0.50, 0.50], "radius": 0.27,
            "angle_start": 15.0, "angle_end": 285.0},
    "cloudform": {"from": None, "to": None, "center": [0.50, 0.50], "size": [0.48, 0.32]},
}

TAGS = ("path", "polyline", "polygon", "circle", "ellipse", "line", "rect", "g")
IDENTITY_FIELDS = ("corpus_format_version", "engine_version", "schema_version", "color_map_digest")


def _instruction(primitive: str, **changes: Any) -> dict[str, Any]:
    result = copy.deepcopy(BASE_INSTRUCTION)
    result.update(GEOMETRY[primitive])
    result["primitive"] = primitive
    result.update(changes)
    return result


def _score(
    instruction: dict[str, Any],
    *,
    aspect: str = "square",
    ground: dict[str, Any] | None = None,
    background: str = "white",
) -> dict[str, Any]:
    result = copy.deepcopy(BASE_SCORE)
    result["canvas"] = {"aspect": aspect, "ground": copy.deepcopy(ground)}
    result["background"] = background
    result["instructions"] = [copy.deepcopy(instruction)]
    return result


def _case(cases: dict[str, dict[str, Any]], case_id: str, instruction: dict[str, Any], *,
          aspect: str = "square", ground: dict[str, Any] | None = None,
          background: str = "white",
          render_seed: int = DEFAULT_RENDER_SEED,
          composition_seed: int | None = None,
          color_map: dict[str, str] = DEFAULT_COLOR_MAP,
          catalog_id: str | None = None,
          svg_profile: str = SVG_PROFILE,
          wild: bool = False) -> None:
    if case_id in cases:
        raise ValueError(f"duplicate case ID: {case_id}")
    cases[case_id] = {
        "score": _score(
            instruction, aspect=aspect, ground=ground, background=background
        ),
        "render_seed": render_seed,
        "color_map": copy.deepcopy(color_map),
        "catalog_id": catalog_id,
        "svg_profile": svg_profile,
        "wild": wild,
    }
    # Stated only where it is stated. Writing the key unconditionally would
    # move all 531 inputs the day the key was added, and the manifest would
    # report a corpus-wide change for a case nobody drew differently.
    if composition_seed is not None:
        cases[case_id]["composition_seed"] = composition_seed


def _case_unit(cases: dict[str, dict[str, Any]], case_id: str,
               instructions: list[dict[str, Any]], *,
               render_seed: int = DEFAULT_RENDER_SEED,
               composition_seed: int | None = None) -> None:
    """A case whose score holds more than one instruction.

    Every other case here draws a single instruction, which is all a corpus of
    one-mark subjects needs. A composite is a claim about a span, so it cannot
    be stated with one.
    """
    if case_id in cases:
        raise ValueError(f"duplicate case ID: {case_id}")
    score = copy.deepcopy(BASE_SCORE)
    score["canvas"] = {"aspect": "square", "ground": None}
    score["background"] = "white"
    score["instructions"] = [copy.deepcopy(item) for item in instructions]
    cases[case_id] = {
        "score": score,
        "render_seed": render_seed,
        "color_map": copy.deepcopy(DEFAULT_COLOR_MAP),
        "catalog_id": None,
        "svg_profile": SVG_PROFILE,
        "wild": False,
    }
    if composition_seed is not None:
        cases[case_id]["composition_seed"] = composition_seed


def build_inputs() -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}

    for tool in TOOLS:
        for primitive in PRIMITIVES:
            _case(cases, f"A-{tool}-{primitive}", _instruction(primitive, weight=tool))

    dimensions = {"line": ["position_x", "position_y"], "circle": ["radius"], "arc": ["radius"]}
    for quality in ("white", "perlin", "pink", "wave"):
        for amplitude in ("fine", "medium", "broad"):
            for primitive in ("line", "circle", "arc"):
                for tool in ("pencil", "brush_thick"):
                    variation = {
                        "amplitude": amplitude, "frequency": "medium", "quality": quality,
                        "dimensions": dimensions[primitive],
                    }
                    _case(cases, f"B-{quality}-{amplitude}-{primitive}-{tool}",
                          _instruction(primitive, weight=tool, variation=variation))

    for primitive in ("circle", "ellipse", "triangle", "square", "polygon"):
        for tool in ("pencil", "crayon", "brush_thick"):
            _case(cases, f"C-fill-{primitive}-{tool}",
                  _instruction(primitive, weight=tool, filled=True))

    # Engine 22 branches a fill on coverage, and the engine-21 corpus could not
    # tell that rule from a hand-written list of tool names: it carried zero
    # filled instructions with a thinness modifier, no filled computer and no
    # filled silverpoint, so three of the acceptance gates had nothing to run on
    # (run 857 §2). The crayon pair is the deciding one -- same tool, thinness
    # alone, coverage 0.333 to 0.117, one on each side of the threshold. Do not
    # substitute crayon+fine: its coverage is 0.200, exactly on the line. The
    # brush_thick pair is the control for it: thinness moves the coverage
    # (0.667 to 0.233) without moving the branch.
    _case(cases, "C-fill-circle-computer",
          _instruction("circle", weight="computer", filled=True))
    _case(cases, "C-fill-circle-silverpoint",
          _instruction("circle", weight="silverpoint", filled=True))
    _case(cases, "C-fill-circle-crayon-extra_fine",
          _instruction("circle", weight="crayon", filled=True, thinness="extra_fine"))
    _case(cases, "C-fill-circle-brush_thick-extra_fine",
          _instruction("circle", weight="brush_thick", filled=True,
                       thinness="extra_fine"))
    # chalk is the one tool carrying ToolGrammar.fill_contrast ("give chalk more
    # contrast than crayon", author 2026-08-07), and the corpus held no filled
    # chalk at all -- so the whole of that ruling would have been recorded
    # nowhere. The pair is deliberate: the contrast belongs to the TOOL, so it
    # has to survive the tool crossing the branch, which chalk does on thinness
    # alone (coverage 0.250 to 0.088).
    _case(cases, "C-fill-circle-chalk",
          _instruction("circle", weight="chalk", filled=True))
    _case(cases, "C-fill-circle-chalk-extra_fine",
          _instruction("circle", weight="chalk", filled=True, thinness="extra_fine"))

    for texture in ("stipple", "hatch", "crosshatch", "aquatint", "grain", "wash", "bleed", "paper_grain"):
        for tool in ("pen", "pencil"):
            surface = copy.deepcopy(BASE_SURFACE)
            surface["texture"] = texture
            _case(cases, f"C-surface-{texture}-{tool}",
                  _instruction("square", weight=tool, filled=False, surface=surface))

    # Tiny fills. Everything below the measured boundary is placed as one dab
    # rather than scanned; above it the interior is still filled with strokes.
    # The boundary is a short side of 2.9%-3.2% of the canvas, measured across
    # five tools and six seeds, so 1% is safely below and 3.4% safely above.
    _case(cases, "C-tinyfill-circle-pen",
          _instruction("circle", weight="pen", radius=0.005, filled=True))
    _case(cases, "C-tinyfill-circle-rotring",
          _instruction("circle", weight="rotring", radius=0.005, filled=True))
    _case(cases, "C-tinyfill-square-brush_thick",
          _instruction("square", weight="brush_thick", position=[0.495, 0.495],
                       size=[0.01, 0.01], filled=True))
    _case(cases, "C-tinyfill-boundary-pen",
          _instruction("circle", weight="pen", radius=0.017, filled=True))

    # The thinness axis. Three tools spanning the width table (0.5 / 2.0 / 8.0)
    # times the two thinness values, plus one case that states the default
    # explicitly: naming the default must draw exactly what omitting it draws.
    for tool in ("silverpoint", "pen", "brush_thick"):
        for thinness in ("fine", "extra_fine"):
            _case(cases, f"C-thinness-{thinness}-{tool}",
                  _instruction("line", weight=tool, thinness=thinness))
    _case(cases, "C-thinness-default-pen",
          _instruction("line", weight="pen", thinness=None))

    # The corpus is 100% `editable`, but production renders `display`. Every
    # display-only branch of the surface layer was therefore never executed once
    # in 350 cases. These four run the profile the author actually looks at.
    for texture in ("wash", "bleed", "grain", "hatch"):
        surface = copy.deepcopy(BASE_SURFACE)
        surface["texture"] = texture
        _case(cases, f"C-display-surface-{texture}-pen",
              _instruction("square", weight="pen", filled=False, surface=surface),
              svg_profile="display")

    # Engine 40: the three profiles must each carry their actual solid boundary,
    # and the periodic grammar must stay on the computer's scan path. This is
    # the smallest set that distinguishes editable/display mottle, compat's
    # filter-free fallback, and the machine control without a tool/shape matrix.
    for case_id, tool, svg_profile in (
        ("C-surface-solid-pen", "pen", SVG_PROFILE),
        ("C-display-surface-solid-pen", "pen", "display"),
        ("C-compat-surface-solid-pen", "pen", "compat"),
        ("C-display-surface-solid-computer", "computer", "display"),
    ):
        solid = copy.deepcopy(BASE_SURFACE)
        solid["texture"] = "solid"
        _case(
            cases,
            case_id,
            _instruction("square", weight=tool, filled=True, surface=solid),
            svg_profile=svg_profile,
        )

    # Read from the enum rather than listed here: a support added to the schema
    # and not to this list would be a value the frozen record never holds, and
    # the version that added it would freeze with an empty diff that reads as
    # "nothing moved".
    for material in get_args(GroundMaterial):
        ground = copy.deepcopy(BASE_GROUND)
        ground["material"] = material
        _case(cases, f"C-ground-{material}", _instruction("line", weight="pen"), ground=ground)

    for field, value in (("density", 0.85), ("opacity", 0.42)):
        ground = copy.deepcopy(BASE_GROUND)
        ground["material"] = "paper"
        ground[field] = value
        _case(cases, f"C-ground-field-{field}", _instruction("line", weight="pen"), ground=ground)

    # The only path that reaches the derived ground seed: every other ground case
    # above pins `seed`, so engine 14's corpus never called `_texture_seed` once.
    for suffix, changes in (
        ("paper", {}),
        ("washi", {"material": "washi"}),
        ("coarse", {"grain": "coarse"}),
        ("paper-opacity", {"opacity": 0.42}),
    ):
        ground = copy.deepcopy(BASE_GROUND)
        ground.update({"material": "paper", "grain": "medium", "seed": None})
        ground.update(changes)
        _case(cases, f"C-groundseed-auto-{suffix}", _instruction("line", weight="pen"), ground=ground)

    # Engine 37. Every ground case above is drawn with `pen`, whose meeting with
    # the sheet is (0.15, 0.15) -- the sheet moves those marks, but barely, so a
    # corpus holding only them would freeze a version that reads as "nothing
    # happened". These carry the two tools the two quantities actually reach:
    # `brush_thick` is drunk by the sheet (1.00, 0.15) and `chalk` is refused by
    # it (0.10, 1.30). The instruction and the seed are the same across the row;
    # only the sheet changes, so the record says what the sheet did and nothing
    # else. `plain` is the control -- the sheet a work that names no ground gets.
    for tool in ("brush_thick", "chalk"):
        for material in ("plain", "washi", "canvas"):
            ground = copy.deepcopy(BASE_GROUND)
            ground["material"] = material
            _case(cases, f"C-sheet-{material}-{tool}",
                  _instruction("line", weight=tool), ground=ground)

    # The mark words. 粒 and にじみ on a `line` are not an interior, so they raise
    # the sheet's own two quantities for that one instruction rather than being
    # moved back to a closed shape. **These three do not reach that decision:**
    # this generator imports `renderer` directly and never calls `coerce_score`,
    # so the surface arrives here already sitting on the line. What they measure
    # is the renderer's half. The coerce half is measured by T-11.
    for word, tool in (("grain", "chalk"), ("bleed", "brush_thick")):
        ground = copy.deepcopy(BASE_GROUND)
        ground["material"] = "paper"
        surface = copy.deepcopy(BASE_SURFACE)
        surface["texture"] = word
        _case(cases, f"C-sheet-line-{word}",
              _instruction("line", weight=tool, surface=surface), ground=ground)

    # The one combination where the ceiling binds: washi drinks at 2.2 and にじみ
    # doubles it to 4.4, past the end of the ladder the author accepted. Without
    # a case here the cap could be raised to any number and the corpus would not
    # notice.
    cap_ground = copy.deepcopy(BASE_GROUND)
    cap_ground["material"] = "washi"
    cap_surface = copy.deepcopy(BASE_SURFACE)
    cap_surface["texture"] = "bleed"
    _case(cases, "C-sheet-cap",
          _instruction("line", weight="brush_thick", surface=cap_surface), ground=cap_ground)

    # Engine 38. 薄墨 on an open shape is a broad pale sweep. Not one case in
    # the 597 above carries a wash on a line or an arc -- the three open-shape
    # surfaces here are engine 37's 粒 and にじみ -- so freezing without these
    # would record a version whose change the record never traverses.
    # `brush_thin` and `rotring` are production's top two tools for this
    # request (171 and 92 of 567 measured 2026-08-16), and they are the two
    # halves of the drawing path: a `rotring` line is an SVG `<line>` drawn
    # from `_stroke_attrs`, every other tool is a performed band. The arc goes
    # through `_render_arc_hand_stroke`, a different function again -- the one
    # the prototype forgot, which is why its 刷毛 and its 濃度 came out equal.
    for primitive, tool in (
        ("line", "brush_thin"), ("line", "rotring"), ("arc", "pencil"),
    ):
        wash = copy.deepcopy(BASE_SURFACE)
        wash["texture"] = "wash"
        _case(cases, f"C-wash-{primitive}-{tool}",
              _instruction(primitive, weight=tool, surface=wash))

    # The control. A closed shape's 薄墨 is its interior, drawn by the surface
    # layer since engine 36, and this version must not reach it: without a
    # frozen closed case beside the open ones, dropping the closed-shape
    # exclusion would move nothing the corpus records.
    closed_wash = copy.deepcopy(BASE_SURFACE)
    closed_wash["texture"] = "wash"
    _case(cases, "C-wash-closed-control",
          _instruction("square", weight="brush_thin", surface=closed_wash))

    # Engine 38, second half (ledger I-289). The texture filters are written
    # only under the `display` profile, and every `display` case above is drawn
    # with `pen` -- which is not in `TEXTURE_FILTER_WEIGHTS`. Measured
    # 2026-08-17 on engine 37: of 597 baked SVGs, the number carrying
    # `filter="url(#texture-` is **zero**. These carry the four tools the
    # branch actually fires for. `drypoint` is the fifth key of
    # `TEXTURE_SPECS` and is excluded by name at every write site, so it is
    # here as the witness for that exclusion: a list of four would make "and
    # drypoint does not appear" a claim with nobody to test it.
    for tool in ("pencil", "crayon", "chalk", "brush_thick", "drypoint"):
        filter_surface = copy.deepcopy(BASE_SURFACE)
        filter_surface["texture"] = "hatch"
        _case(cases, f"C-filter-display-{tool}",
              _instruction("square", weight=tool, filled=False, surface=filter_surface),
              svg_profile="display")

    representatives = {
        "line-pencil": _instruction("line", weight="pencil"),
        "circle-crayon": _instruction("circle", weight="crayon"),
        "arc-brush-thick": _instruction("arc", weight="brush_thick"),
        "filled-square-rotring": _instruction("square", weight="rotring", filled=True),
        # A 1.6:1 ellipse is the case the corpus never had: on a non-square
        # canvas the old rule turned it upright, so the record could not tell a
        # widened mark from a preserved one.
        "ellipse-pen": _instruction("ellipse", weight="pen"),
    }
    for aspect in ("square", "wide", "pillar", "vertical"):
        for name, instruction in representatives.items():
            _case(cases, f"D-canvas-{aspect}-{name}", instruction, aspect=aspect)

    # Engine 31: the layer that arranges marks, on all four aspects. The corpus
    # could not see this rule at all before -- of 553 cases the five carrying a
    # `radial` were every one of them square, and not one case carried an
    # `at.region`. The square column is the control: on a square canvas the two
    # arithmetics are the same, so those four must not move.
    arrangement_region = [0.6, 0.18, 0.82, 0.4]  # a square box, 0.22 x 0.22
    ring = copy.deepcopy(BASE_ARRANGEMENT)
    ring.update({"count": 12, "layout": "radial", "radius": 0.3,
                 "center": [0.5, 0.5], "jitter": 0.0})
    region_grid = copy.deepcopy(BASE_ARRANGEMENT)
    region_grid.update({"count": 12, "layout": "grid", "jitter": 0.0})
    region_scatter = copy.deepcopy(BASE_ARRANGEMENT)
    region_scatter.update({"count": 12, "layout": "scatter", "jitter": 0.0})
    arrangements = {
        # The ring the ruling is about: round marks were sitting on a ring the
        # canvas had flattened to its own aspect.
        "radial": _instruction("circle", radius=0.02, weight="brush_thick",
                               arrangement=ring),
        # A region resolved for a single mark -- the site every region
        # instruction goes through, whatever its layout.
        "region-single": _instruction("circle", radius=0.012,
                                      at={"region": arrangement_region}),
        # The grid reads the region a second time, in its own branch. A fix
        # applied only to the first site leaves `region-single` unchanged and
        # this one stretched.
        "region-grid": _instruction("circle", radius=0.012, arrangement=region_grid,
                                    at={"region": arrangement_region}),
        # A layout for which the region is only an anchor: nothing is confined
        # to the box, but the anchor still moves. Kept so the record shows it.
        "region-scatter": _instruction("circle", radius=0.012,
                                       arrangement=region_scatter,
                                       at={"region": arrangement_region}),
    }
    for aspect in ("square", "wide", "pillar", "vertical"):
        for name, instruction in arrangements.items():
            _case(cases, f"D-canvas-{aspect}-{name}", instruction, aspect=aspect)

    # Engine 32: the cluster and the path, the two remaining arrangements whose
    # own shape the canvas was stretching, and together 36.2% of the marks
    # production expands. The corpus could not see either: `G-cluster-*` and
    # `G-path-*` are ten cases and every one of them is square, so not one
    # non-square cluster or path existed anywhere in the record.
    #
    # Each subject is drawn on the square canvas and on the papers whose long
    # side is the axis it spreads on. That pairing is the whole point: a
    # `top_to_bottom` spreads on x, so on the pillar its factor is exactly 1.0
    # and the case would be frozen without being able to fail. The square
    # column is the control -- the arithmetic is the identity there, so those
    # four must draw what engine 31 drew.
    cluster_group = copy.deepcopy(BASE_ARRANGEMENT)
    cluster_group.update({"count": 36, "layout": "scatter", "cluster_count": 3,
                          "density": "medium", "path": "none", "jitter": 0.0})
    wave_group = copy.deepcopy(BASE_ARRANGEMENT)
    wave_group.update({"count": 40, "layout": "scatter", "path": "wave",
                       "jitter": 0.0})
    diagonal_group = copy.deepcopy(BASE_ARRANGEMENT)
    diagonal_group.update({"count": 40, "layout": "scatter", "path": "diagonal",
                           "jitter": 0.0})
    top_to_bottom_group = copy.deepcopy(BASE_ARRANGEMENT)
    top_to_bottom_group.update({"count": 40, "layout": "scatter",
                                "path": "top_to_bottom", "jitter": 0.0})
    spreads = {
        # Clumps: the band is rotated, so it spreads on both axes and every
        # non-square paper can see it.
        "cluster": (_instruction("circle", radius=0.012, weight="pen",
                                 arrangement=cluster_group),
                    ("square", "pillar", "vertical", "wide")),
        # The wave swings on y.
        "path-wave": (_instruction("circle", radius=0.012, weight="pen",
                                   arrangement=wave_group),
                      ("square", "pillar", "vertical")),
        # The diagonal jitters on both.
        "path-diagonal": (_instruction("circle", radius=0.012, weight="pen",
                                       arrangement=diagonal_group),
                          ("square", "pillar", "vertical", "wide")),
        # This one spreads on x, so it is drawn on the wide canvas only.
        "path-top_to_bottom": (_instruction("circle", radius=0.012, weight="pen",
                                            arrangement=top_to_bottom_group),
                               ("square", "wide")),
    }
    for name, (instruction, aspects) in spreads.items():
        for aspect in aspects:
            _case(cases, f"D-canvas-{aspect}-{name}", instruction, aspect=aspect)

    for style in ("solid", "dashed", "dotted", "dash_dot"):
        _case(cases, f"D-style-{style}", _instruction("arc", weight="pen", style=style))

    for seed in (1, 12345, 98765):
        _case(cases, f"D-seed-{seed}", _instruction("arc", weight="drypoint"), render_seed=seed)

    _case(cases, "D-size-tiny-filled-circle",
          _instruction("circle", weight="pencil", radius=0.003, filled=True))
    _case(cases, "D-size-large-filled-polygon",
          _instruction("polygon", weight="brush_thick", radius=0.47, sides=8, filled=True))
    _case(cases, "D-color-vivid-material-green-circle",
          _instruction("circle", weight="pen", color="green"), color_map=VIVID_MATERIAL_COLOR_MAP)

    for seed in (2**63 + 1, 2**64 - 1):
        _case(cases, f"D-unsigned-seed-{seed}",
              _instruction("arc", weight="drypoint"), render_seed=seed)

    # E: the unleashed performance. Paired with A (every tool x primitive), the
    # C fills and the C surfaces, because those are the paths the toggle reaches
    # for the first time in engine 14.
    for tool in TOOLS:
        for primitive in PRIMITIVES:
            _case(cases, f"E-wild-{tool}-{primitive}",
                  _instruction(primitive, weight=tool), wild=True)

    for primitive in ("circle", "ellipse", "triangle", "square", "polygon"):
        for tool in ("pencil", "crayon", "brush_thick"):
            _case(cases, f"E-wild-fill-{primitive}-{tool}",
                  _instruction(primitive, weight=tool, filled=True), wild=True)

    for texture in ("stipple", "hatch", "crosshatch", "aquatint", "grain", "wash", "bleed", "paper_grain"):
        for tool in ("pen", "pencil"):
            surface = copy.deepcopy(BASE_SURFACE)
            surface["texture"] = texture
            _case(cases, f"E-wild-surface-{texture}-{tool}",
                  _instruction("square", weight=tool, filled=False, surface=surface),
                  wild=True)

    # F: deterministic catalog assignment. The first 99 cases cross every
    # catalog with every abstract color. The remaining cases pin description
    # matching and the background path that the original corpus never reached.
    catalog_maps: dict[str, dict[str, str]] = {}
    for catalog in COLOR_CATALOGS:
        catalog_id = str(catalog["id"])
        catalog_map = render_color_map_for_catalog(catalog_id)
        if catalog_map is None:
            raise AssertionError(f"missing reference catalog: {catalog_id}")
        catalog_maps[catalog_id] = catalog_map
        for color in ABSTRACT_COLORS:
            _case(
                cases,
                f"F-catalog-{catalog_id}-{color}",
                _instruction("line", weight="pen", color=color),
                color_map=catalog_map,
                catalog_id=catalog_id,
            )

    for suffix, catalog_id, color, hint in (
        ("hint-deep-blue", "ink_season", "black", "deep blue wash"),
        ("hint-vertical", "ink_season", "black", "vertical trace"),
        ("hint-restored", "default", "gray", "restored edge"),
        ("hint-sakura", "ink_season", "black", "桜色の薄い層"),
        ("hint-missing-purple-sea-stone", "sea_stone", "black", "purple"),
        ("hint-brown", "fresco_study", "black", "umber earth"),
    ):
        _case(
            cases,
            f"F-{suffix}",
            _instruction("line", weight="pen", color=color, color_hint=hint),
            color_map=catalog_maps[catalog_id],
            catalog_id=catalog_id,
        )

    for suffix, catalog_id, background in (
        ("black", "default", "black"),
        ("blue", "ink_season", "blue"),
        ("gray", "fresco_study", "gray"),
        ("red", "vivid_material", "red"),
        ("green", "dye_earth", "green"),
    ):
        _case(
            cases,
            f"F-background-{suffix}",
            _instruction("line", weight="pen", color="black"),
            background=background,
            color_map=catalog_maps[catalog_id],
            catalog_id=catalog_id,
        )

    # G: placement authority. A-F never state an `arrangement`, so none of the
    # 493 reaches `_expand_arrangement` -- engine 20 could be deleted whole and
    # they would all stay green. Every G case carries one, and inside an anchor
    # triplet the declared centre is the only thing that differs.
    def _g(case_id: str, anchor: str, *, composition_seed: int | None = None,
           weight: str = "pen", radius: float = 0.03,
           surface: dict[str, Any] | None = None, **changes: Any) -> None:
        arrangement = copy.deepcopy(BASE_ARRANGEMENT)
        arrangement.update(changes)
        _case(cases, case_id,
              _instruction("circle", weight=weight, center=list(G_ANCHORS[anchor]),
                           radius=radius, arrangement=arrangement, surface=surface),
              composition_seed=composition_seed)

    # The largest route (40.9% of the expanded marks in production).
    for anchor in G_ANCHORS:
        _g(f"G-scatter-{anchor}", anchor)
        _g(f"G-scatter-small-{anchor}", anchor, count=5)

    # Clusters (27.1%). preserve_space raises the centre margin to 0.20.
    for anchor in G_ANCHORS:
        _g(f"G-cluster-{anchor}", anchor, cluster_count=3)
    _g("G-cluster-preserve-edge", "edge", cluster_count=3, preserve_space=True)

    # Paths (9.1%). The cross axis was written as a literal 0.5 until engine 20.
    for path in ("wave", "diagonal", "top_to_bottom"):
        _g(f"G-path-{path}-edge", "edge", layout="vertical", path=path)
    _g("G-path-wave-center", "center", layout="vertical", path="wave")
    _g("G-path-wave-corner", "corner", layout="vertical", path="wave")
    _g("G-path-hwave-edge", "edge", layout="horizontal", path="wave")

    # vertical / horizontal without a path: one axis already kept the
    # declaration, so the centre pair here is a control that must not move.
    for anchor in G_ANCHORS:
        _g(f"G-vertical-nopath-{anchor}", anchor, layout="vertical")
        _g(f"G-horizontal-nopath-{anchor}", anchor, layout="horizontal")

    # radial: stage 2's target. Without `center` the ring used to turn around
    # the middle of the canvas; the centre anchor is the control that stays.
    for anchor in G_ANCHORS:
        _g(f"G-radial-nocenter-{anchor}", anchor, layout="radial", count=12)
    _g("G-radial-center-edge", "edge", layout="radial", count=12, center=[0.3, 0.3])

    # The smallest route (0.7%), and the only one that tiles a region.
    for anchor in G_ANCHORS:
        _g(f"G-grid-{anchor}", anchor, layout="grid", count=16, rows=4, cols=4)

    # Density, fade and rhythm ride along the same anchor as the scatter cases:
    # they change how a group is drawn, never who decides where it is.
    _g("G-scatter-dense-edge", "edge", density="high")
    _g("G-scatter-fade-edge", "edge", fade="outward")
    _g("G-scatter-rhythm-edge", "edge", rhythm_spacing="loose")

    # engine 23: the four cases that state a composition seed. Each is the twin
    # of a case above with the same score and the same performance seed, so the
    # pair is the whole claim -- placement follows the composition seed, and
    # nothing else in the drawing does. The layouts are taken from the 22 of
    # group G whose expansion actually moves when the seed moves; `radial` and
    # the pathless `vertical` / `horizontal` are excluded because their
    # coordinates are the same for every seed, so a twin there would be
    # identical to its base and prove nothing.
    # engine 24: the fade reaches every member. Until here the corpus walked one
    # fading route -- `G-scatter-fade-edge`, the plainest one there is: outward,
    # scatter, a hand tool, no cycle, no surface. The six below are the routes
    # the change actually turns on, and none of them existed in any version.
    #
    # The surface case states `seed: None` on purpose. Every other surface case
    # in this corpus states 24680, which returns from `_surface_seed` before the
    # instruction dump is hashed -- so none of them can see a hint written onto
    # the members, which is the one thing this case is here to watch.
    FADE_SURFACE: dict[str, Any] = {
        "texture": "wash", "density": 0.55, "scale": 0.40, "opacity": 0.36,
        "bleed": 0.25, "direction": "diagonal_rising", "spacing_gradient": "none",
        "tone_steps": 3, "seed": None,
    }
    _g("G-fade-directional-path-edge", "edge", fade="directional",
       layout="vertical", path="top_to_bottom", count=20)
    _g("G-fade-cycle-edge", "edge", fade="outward",
       color_cycle=["red", "blue", "green"])
    _g("G-fade-surface-edge", "edge", fade="outward", count=12,
       radius=0.06, surface=FADE_SURFACE)
    _g("G-fade-rotring-edge", "edge", fade="outward", weight="rotring")
    _g("G-fade-radial-edge", "edge", fade="outward", layout="radial", count=12)
    _g("G-fade-count2-edge", "edge", fade="outward", count=2)

    # engine 25: every member of a group gets its own size. All 42 G cases
    # above are circles, so `radius x k` was the only one of the four size
    # rules the corpus could reach -- and in production a circle is 14.3% of
    # the expanded marks against a line's 43.8%. These four walk the other
    # three: the same factor on both components of `size`, the `position`
    # correction that keeps a bbox centred on its anchor while it grows, and
    # the scaling of a line about its own midpoint rather than about one end.
    # All four sit on the `edge` anchor, where the frame correction fires.
    def _g_shape(case_id: str, primitive: str, geometry: dict[str, Any],
                 **changes: Any) -> None:
        arrangement = copy.deepcopy(BASE_ARRANGEMENT)
        arrangement.update(changes)
        _case(cases, case_id,
              _instruction(primitive, weight="pen", arrangement=arrangement,
                           **geometry))

    _g_shape("G-size-line-edge", "line",
             {"from": [0.81, 0.83], "to": [0.89, 0.87]}, count=12)
    _g_shape("G-size-square-edge", "square",
             {"position": [0.81, 0.81], "size": [0.08, 0.08]}, count=12)
    _g_shape("G-size-triangle-edge", "triangle",
             {"position": [0.81, 0.81], "size": [0.08, 0.08]}, count=12)
    _g_shape("G-size-ellipse-edge", "ellipse",
             {"center": [0.85, 0.85], "size": [0.10, 0.06]}, count=12)

    # engine 26: every member of a group gets its own angle. Four more, because
    # otherwise the corpus barely sees the rule. Of the 46 groups above, 42 are
    # circles -- which the rule leaves alone, an angle being invisible on one --
    # one is a line and one is a grid, both excluded by the ruling, so only the
    # three shapes engine 25 added turn. `arc` is the largest target there is in
    # production (377 groups against `ellipse`'s 373) and the corpus holds not
    # one; `cloudform` (64) likewise.
    #
    # The other two state `rotation` themselves and are here to be identical.
    # The ruling excludes a group that names its own angle, and `rotation: 0` is
    # such a group: it says "do not tilt these", which is an answer and not a
    # missing one. 141 groups in production give it, and they are the only ones
    # a truthy test would silently turn -- so this pair is the corpus's only
    # sight of the difference between `is not None` and `if ins.rotation:`.
    _g_shape("G-angle-arc-edge", "arc",
             {"center": [0.85, 0.85], "radius": 0.06,
              "angle_start": 15.0, "angle_end": 285.0}, count=12)
    _g_shape("G-angle-cloudform-edge", "cloudform",
             {"center": [0.85, 0.85], "size": [0.10, 0.06]}, count=12)
    _g_shape("G-angle-stated-zero-edge", "ellipse",
             {"center": [0.85, 0.85], "size": [0.10, 0.06], "rotation": 0.0},
             count=12)
    _g_shape("G-angle-stated-30-edge", "ellipse",
             {"center": [0.85, 0.85], "size": [0.10, 0.06], "rotation": 30.0},
             count=12)

    G_COMPOSITION_SEED = 777
    _g("G-composition-scatter-edge", "edge", composition_seed=G_COMPOSITION_SEED)
    _g("G-composition-grid-center", "center", composition_seed=G_COMPOSITION_SEED,
       layout="grid", count=16, rows=4, cols=4)
    _g("G-composition-cluster-center", "center", composition_seed=G_COMPOSITION_SEED,
       cluster_count=3)
    _g("G-composition-path-wave-edge", "edge", composition_seed=G_COMPOSITION_SEED,
       layout="vertical", path="wave")

    # C gained 6 in engine 22: a filled computer and a filled silverpoint, which
    # the corpus had never carried, the crayon / brush_thick thinness pair that
    # tells a coverage rule from a list of tool names, and the chalk pair that
    # carries the one tool-level fill contrast across the branch.
    # G gained 4 in engine 23: the twins that state a composition seed, which is
    # the only way the corpus reaches the placement seed at all.
    # G gained 6 in engine 24: the fading routes the corpus had never walked.
    # G gained 4 in engine 25: the three size rules a circle cannot reach.
    # G gained 4 in engine 26: the two shapes the angle rule turns that the
    # corpus had never carried, and the two groups that state their own angle.
    # D gained 4 in engine 30: one representative, drawn on all four aspects.
    # Until then no case put a mark wider than it is tall on a canvas taller
    # than it is wide, so nothing in the record could tell a mark that kept its
    # proportion from one the canvas had stretched.
    # D gained 16 in engine 31: four arrangement subjects on all four aspects.
    # The corpus held five `radial` cases, all square, and no `at.region` at
    # all, so both rules the ruling states would have gone into the record
    # unrecorded.
    # D gained 13 in engine 32: a cluster and three paths, each on the square
    # canvas and on the papers whose long side is the axis it spreads on. Nine
    # of the thirteen draw something engine 31 could not; the four square ones
    # are the control and must not move.
    # H is new in engine 33: the composite unit. Every case above draws one
    # instruction, so the corpus could not state a span at all -- freezing the
    # version without these would record a vocabulary the record never speaks.
    # The head repeats the whole span; the member follows its own head rather
    # than the previous copy, which is the entire claim. `plain` is the control:
    # the same two instructions with no span, which is the picture engine 32
    # drew, and it must not move.
    HEAD: dict[str, Any] = {
        "center": [0.50, 0.50], "radius": 0.08,
        "angle_start": 220.0, "angle_end": 320.0,
    }
    MEMBER: dict[str, Any] = {
        "center": [0.50, 0.50], "radius": 0.08,
        "angle_start": 40.0, "angle_end": 140.0,
        "relation": {"type": "touching", "gap": "medium"},
    }

    def _pair(case_id: str, **changes: Any) -> None:
        arrangement = copy.deepcopy(BASE_ARRANGEMENT)
        arrangement.update({"count": 3, "layout": "scatter", "margin": 0.15})
        arrangement.update(changes)
        _case_unit(
            cases, case_id,
            [_instruction("arc", weight="pen", arrangement=arrangement, **HEAD),
             _instruction("arc", weight="pen", **MEMBER)],
        )

    _pair("H-pair-scatter-plain")
    _pair("H-pair-scatter-unit", group_size=2)
    _pair("H-pair-radial-unit", group_size=2, count=6, layout="radial",
          center=[0.5, 0.5], radius=0.3)
    _pair("H-pair-cycle-unit", group_size=2, count=4,
          color_cycle=["red", "blue"])

    # C gained two with `canvas` and `drawing_paper`. The count stays written
    # out by hand on purpose: the ground cases are read from the enum now, so
    # this line is what makes adding a support a deliberate re-bake instead of a
    # corpus that quietly grew.
    # Engine 37 gained nine more to C: six that change nothing but the sheet
    # under two tools the sheet actually reaches, two that put a mark word on a
    # line, and one where the ceiling binds.
    # Engine 38 gained nine more to C: four that put 薄墨 on an open shape --
    # the two drawing paths a line has plus an arc, and a closed control -- and
    # five that reach the texture filters, which no `display` case in the
    # corpus could reach while all four of them were `pen`.
    expected = {"A": 88, "B": 72, "C": 84, "D": 61, "E": 119, "F": 128,
                "G": 50, "H": 4}
    actual = {prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases) for prefix in expected}
    if actual != expected or len(cases) != 606:
        raise AssertionError(f"case count mismatch: {actual}, total={len(cases)}")
    return cases


def _normalized_digest(svg: str) -> str:
    normalized = re.sub(r"\d+\.\d+", lambda match: f"{round(float(match.group(0)), 6):.6f}", svg)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _color_map_digest(inputs: dict[str, dict[str, Any]]) -> str:
    payload = {
        case_id: {
            "catalog_id": render_input["catalog_id"],
            "color_map": render_input["color_map"],
        }
        for case_id, render_input in sorted(inputs.items())
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:32]


def _previous_manifest() -> dict[str, Any] | None:
    """The frozen manifest of the highest engine version below the current one.

    Version directories are the record of how many times the layer changed, so
    "previous" is the largest integer under the current one that was actually
    frozen, not `current - 1`.
    """
    current = int(ENGINE_VERSION)
    candidates: list[tuple[int, pathlib.Path]] = []
    for path in REFERENCE_ROOT.glob("render-engine-*/manifest.json"):
        suffix = path.parent.name.rsplit("-", 1)[-1]
        if suffix.isdigit() and int(suffix) < current:
            candidates.append((int(suffix), path))
    if not candidates:
        return None
    return json.loads(max(candidates)[1].read_text())


def _source_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REFERENCE_ROOT.parent.parent,
                          check=True, capture_output=True, text=True).stdout.strip()


def render_case(render_input: dict[str, Any]) -> str:
    """Draw one case from its stated input, and only from that.

    Named so the tests that replay a case go through the same call the bake
    does. A test that copies the argument list instead stays green when this
    one stops forwarding a key, which is how a corpus can hold an input field
    that never reaches the renderer.
    """
    return render(Score.model_validate(render_input["score"]),
                  color_map=render_input["color_map"],
                  catalog_id=render_input["catalog_id"],
                  render_seed=render_input["render_seed"],
                  composition_seed=render_input.get("composition_seed"),
                  svg_profile=render_input["svg_profile"], wild=render_input["wild"])


FADE_CASES = (
    "G-fade-directional-path-edge",
    "G-fade-cycle-edge",
    "G-fade-surface-edge",
    "G-fade-rotring-edge",
    "G-fade-radial-edge",
    "G-fade-count2-edge",
)


def _assert_fade_cases_discriminate(inputs: dict[str, dict[str, Any]]) -> None:
    """Every fading case added here has to notice `fade` before it is written.

    A case that draws the same picture with and without the declaration records
    that nothing broke and nothing else; the corpus would then hold six cases
    that cannot fail. Checked at bake time, on the bake's own call.
    """
    for case_id in FADE_CASES:
        stated = inputs[case_id]
        withheld = copy.deepcopy(stated)
        withheld["score"]["instructions"][0]["arrangement"]["fade"] = "none"
        if _normalized_digest(render_case(stated)) == _normalized_digest(render_case(withheld)):
            raise AssertionError(f"{case_id}: the drawing does not read `fade`")


# The two that must come out with no ceiling at all, and stay that way.
DEGENERATE_FADE_CASES = ("G-fade-radial-edge", "G-fade-count2-edge")


def _assert_fade_reaches_every_member(inputs: dict[str, dict[str, Any]]) -> None:
    """At least one drawn fading group carries more than one ceiling.

    The check above cannot ask this. Dropping the declaration takes the whole
    group's fade away, and engine 23 already drew that difference with a single
    constant for the whole group -- so an implementation that carries no
    per-member ceiling at all still passes it. The corpus is asked directly
    instead: some drawn group has to hold distinct per-member levels, or `fade`
    is pinned only where the rule declines to fire.

    And the two degenerate groups have to hold none: a ring is equidistant from
    its own centre and so is a pair, and ranking them would draw a gradient
    nobody stated. Author ruling A on ledger I-166, 2026-08-09; the engine's
    behaviour is not changed, only asked about.
    """
    def levels(case_id: str) -> list[float | None]:
        render_input = inputs[case_id]
        instruction = Instruction.model_validate(
            render_input["score"]["instructions"][0]
        )
        performance_seed = render_input["render_seed"]
        # The placement seed is the composition seed's when the case states one:
        # read with "is it stated", never with a falsy test, because 0 is a seed
        # a caller can legitimately give.
        placement_seed = render_input.get("composition_seed")
        if placement_seed is None:
            placement_seed = performance_seed
        return [
            renderer._fade_level_from_hint(item.color_hint)
            for item in renderer._expand_arrangement(
                instruction, placement_seed, performance_seed=performance_seed
            )
        ]

    ramped = [
        case_id
        for case_id in FADE_CASES
        if len({level for level in levels(case_id) if level is not None}) > 1
    ]
    if not ramped:
        raise AssertionError(
            "no drawn fading group carries a per-member ceiling; the corpus "
            "pins `fade` only where the rule declines to fire"
        )
    for case_id in DEGENERATE_FADE_CASES:
        if any(level is not None for level in levels(case_id)):
            raise AssertionError(f"{case_id}: a group that cannot fade was ramped")


SIZE_CASES = (
    "G-size-line-edge",
    "G-size-square-edge",
    "G-size-triangle-edge",
    "G-size-ellipse-edge",
)


@contextlib.contextmanager
def _member_sizes_withheld() -> Iterator[None]:
    """Draw as engine 24 did: the group expands, and every member is congruent."""
    original = renderer._apply_member_sizes
    renderer._apply_member_sizes = lambda items, arr, member_seed: items
    try:
        yield
    finally:
        renderer._apply_member_sizes = original


def _assert_size_cases_discriminate(inputs: dict[str, dict[str, Any]]) -> None:
    """Every case added here has to notice the per-member size, two ways.

    Withholding the amplitude has to change the drawing, or the case records
    that nothing broke and nothing else. And the four have to walk four
    different rules: the corpus already held 42 groups that were circles to
    the last one, so a fifth circle would discriminate perfectly and cover
    nothing. Checked at bake time, on the bake's own call.
    """
    primitives = {
        inputs[case_id]["score"]["instructions"][0]["primitive"]
        for case_id in SIZE_CASES
    }
    if primitives != {"line", "square", "triangle", "ellipse"}:
        raise AssertionError(f"the added cases do not cover the four rules: {sorted(primitives)}")
    for case_id in SIZE_CASES:
        stated = inputs[case_id]
        drawn = _normalized_digest(render_case(stated))
        with _member_sizes_withheld():
            withheld = _normalized_digest(render_case(stated))
        if drawn == withheld:
            raise AssertionError(f"{case_id}: the drawing does not read the member size")


# The two the angle rule turns, and the two it has to leave alone.
ANGLE_CASES = ("G-angle-arc-edge", "G-angle-cloudform-edge")
STATED_ANGLE_CASES = ("G-angle-stated-zero-edge", "G-angle-stated-30-edge")


@contextlib.contextmanager
def _member_rotations_withheld() -> Iterator[None]:
    """Draw as engine 25 did: the group expands, and every member shares an angle."""
    original = renderer._apply_member_rotations
    renderer._apply_member_rotations = lambda items, arr, member_seed: items
    try:
        yield
    finally:
        renderer._apply_member_rotations = original


def _assert_angle_cases_discriminate(inputs: dict[str, dict[str, Any]]) -> None:
    """The four added here have to notice the angle, in the two opposite ways.

    The turning pair has to change when the amplitude is withheld, and it has
    to be `arc` and `cloudform`: the corpus can already reach the rule through
    the three shapes engine 25 added, so a fourth ellipse would discriminate
    perfectly and cover nothing new.

    The stating pair has to do the reverse -- withholding the amplitude must
    not move them, because a group that names its own angle is excluded -- and
    still has to read `rotation` itself, or the pair records that nothing broke
    and nothing else. Dropping the stated angle turns the exclusion off, which
    is the only thing that separates `rotation: 0` from an unstated angle:
    neither draws a rotate() of its own. Checked at bake time, on the bake's
    own call.
    """
    primitives = {
        inputs[case_id]["score"]["instructions"][0]["primitive"]
        for case_id in ANGLE_CASES
    }
    if primitives != {"arc", "cloudform"}:
        raise AssertionError(f"the added cases do not reach the missing shapes: {sorted(primitives)}")
    for case_id in ANGLE_CASES:
        stated = inputs[case_id]
        drawn = _normalized_digest(render_case(stated))
        with _member_rotations_withheld():
            withheld = _normalized_digest(render_case(stated))
        if drawn == withheld:
            raise AssertionError(f"{case_id}: the drawing does not read the member angle")
    for case_id in STATED_ANGLE_CASES:
        stated = inputs[case_id]
        drawn = _normalized_digest(render_case(stated))
        with _member_rotations_withheld():
            if _normalized_digest(render_case(stated)) != drawn:
                raise AssertionError(f"{case_id}: a group that states its angle was turned")
        dropped = copy.deepcopy(stated)
        dropped["score"]["instructions"][0]["rotation"] = None
        if _normalized_digest(render_case(dropped)) == drawn:
            raise AssertionError(f"{case_id}: the drawing does not read `rotation`")


def _write_output_directory(
    output_dir: pathlib.Path,
    manifest: dict[str, Any],
    rendered: dict[str, str],
    changed: list[str],
) -> None:
    """Write one complete corpus directory without publishing it."""
    output_dir.mkdir()
    for case_id in changed:
        (output_dir / f"{case_id}.svg").write_text(rendered[case_id], encoding="utf-8")
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _publish_output_directory(
    manifest: dict[str, Any],
    rendered: dict[str, str],
    changed: list[str],
    *,
    output_dir: pathlib.Path = OUTPUT_DIR,
) -> None:
    """Stage a complete corpus, then publish it without modifying in place."""
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    backup = parent / f".{output_dir.name}.previous"

    # A process can be killed between the two directory renames. In that case
    # the previous corpus remains whole under the fixed backup name, so the next
    # run can restore it before doing any work.
    if backup.exists():
        if output_dir.exists():
            shutil.rmtree(backup)
        else:
            backup.rename(output_dir)

    staging = pathlib.Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent))
    try:
        staging.rmdir()
        _write_output_directory(staging, manifest, rendered, changed)
        if not output_dir.exists():
            staging.rename(output_dir)
            return

        output_dir.rename(backup)
        try:
            staging.rename(output_dir)
        except BaseException:
            backup.rename(output_dir)
            raise
        shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def generate() -> None:
    existing = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else None
    inputs = build_inputs()
    _assert_fade_cases_discriminate(inputs)
    _assert_fade_reaches_every_member(inputs)
    _assert_size_cases_discriminate(inputs)
    _assert_angle_cases_discriminate(inputs)

    rendered: dict[str, str] = {}
    cases: dict[str, dict[str, Any]] = {}
    for case_id, render_input in sorted(inputs.items()):
        svg = render_case(render_input)
        rendered[case_id] = svg
        cases[case_id] = {
            "input": render_input,
            "digest": _normalized_digest(svg),
            "bytes": len(svg.encode()),
            "counts": {tag: len(re.findall(rf"<{tag}(?:[ />])", svg)) for tag in TAGS},
            "classes": sorted(set(re.findall(r'class="([^"]+)"', svg))),
        }

    if existing is None:
        previous = _previous_manifest()
        if previous is None:
            changed = sorted(cases)
        else:
            before = previous["cases"]
            changed = sorted(
                case_id for case_id, case in cases.items()
                if case_id not in before or before[case_id]["digest"] != case["digest"]
            )
        frozen = {
            "frozen_at": FROZEN_AT, "commit": _source_commit(), "reason": REASON,
            "changed_from_previous": changed,
        }
    else:
        frozen = {key: existing[key] for key in ("frozen_at", "commit", "reason", "changed_from_previous")}

    manifest = {
        "corpus_format_version": CORPUS_FORMAT_VERSION, "layer": "render-engine",
        "engine_id": ENGINE.id, "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "color_map_digest": _color_map_digest(inputs),
        **frozen, "cases": cases,
    }
    if existing is not None and existing.get("cases") != manifest["cases"]:
        before = tuple(existing.get(field) for field in IDENTITY_FIELDS)
        after = tuple(manifest.get(field) for field in IDENTITY_FIELDS)
        if before == after:
            raise SystemExit(
                "render corpus changed without an identity-field change; bump the appropriate "
                "version instead of rewriting a frozen corpus"
            )

    # Only the cases that moved get an SVG body. An unchanged case is already
    # frozen in the last version where it moved; copying it forward would make
    # the directory listing stop meaning "what this version changed".
    _publish_output_directory(manifest, rendered, frozen["changed_from_previous"])


if __name__ == "__main__":
    generate()
