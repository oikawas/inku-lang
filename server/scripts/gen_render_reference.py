"""Generate the frozen render-engine reference corpus.

Run from ``server/`` with the repository-standard uv cache environment.
Every render input is literal: no schema defaults, renderer color map, color
catalog, or coerce path supplies fixture values.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any

from inku_server.color_catalogs import COLOR_CATALOGS, render_color_map_for_catalog
from inku_server.render_engines import current_render_engine
from inku_server.renderer import render
from inku_server.schema import Score

REFERENCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "reference"
ENGINE = current_render_engine()
ENGINE_VERSION = ENGINE.version
OUTPUT_DIR = REFERENCE_ROOT / f"render-engine-{ENGINE_VERSION}"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

CORPUS_FORMAT_VERSION = "2"
SCHEMA_VERSION = "0.1.0"
FROZEN_AT = "2026-07-30"
REASON = (
    "Each work now receives a deterministic assignment from its named catalog "
    "palette before descriptions override it. ASCII hue hints match whole words, "
    "CJK hints retain substring matching, backgrounds use the same assignment, "
    "and sparse achromatic palettes cannot collapse black, gray, and white. The "
    "original 365 cases remain byte-identical because they carry only the literal "
    "six-key map; the new F group traverses all eleven catalogs, all nine abstract "
    "colors, hint boundaries, missing bands, brown, and non-white backgrounds."
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

    for material in ("plain", "paper", "washi", "ink_wash", "charcoal_ground", "mezzotint"):
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

    representatives = {
        "line-pencil": _instruction("line", weight="pencil"),
        "circle-crayon": _instruction("circle", weight="crayon"),
        "arc-brush-thick": _instruction("arc", weight="brush_thick"),
        "filled-square-rotring": _instruction("square", weight="rotring", filled=True),
    }
    for aspect in ("square", "wide", "pillar", "vertical"):
        for name, instruction in representatives.items():
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
        ("hint-missing-purple", "default", "black", "purple"),
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

    expected = {"A": 88, "B": 72, "C": 58, "D": 28, "E": 119, "F": 110}
    actual = {prefix: sum(case_id.startswith(f"{prefix}-") for case_id in cases) for prefix in expected}
    if actual != expected or len(cases) != 475:
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


def generate() -> None:
    existing = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else None
    inputs = build_inputs()

    rendered: dict[str, str] = {}
    cases: dict[str, dict[str, Any]] = {}
    for case_id, render_input in sorted(inputs.items()):
        svg = render(Score.model_validate(render_input["score"]),
                     color_map=render_input["color_map"],
                     catalog_id=render_input["catalog_id"],
                     render_seed=render_input["render_seed"],
                     svg_profile=render_input["svg_profile"], wild=render_input["wild"])
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Only the cases that moved get an SVG body. An unchanged case is already
    # frozen in the last version where it moved; copying it forward would make
    # the directory listing stop meaning "what this version changed".
    for case_id in frozen["changed_from_previous"]:
        (OUTPUT_DIR / f"{case_id}.svg").write_text(rendered[case_id], encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if existing is not None and existing.get("cases") != manifest["cases"]:
        before = tuple(existing.get(field) for field in IDENTITY_FIELDS)
        after = tuple(manifest.get(field) for field in IDENTITY_FIELDS)
        if before == after:
            raise SystemExit(
                "render corpus changed without an identity-field change; bump the appropriate "
                "version instead of rewriting a frozen corpus"
            )


if __name__ == "__main__":
    generate()
