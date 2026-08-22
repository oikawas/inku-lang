"""Stage 3 guards for palette and SVG document boundaries."""

from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import inku_server.renderer as renderer
from inku_server.schema import Score


PROFILE_DIGESTS = {
    "display": "64f6f634dfa4952324442406569b727d6d904b7ad50911fd61dafe50143a21e4",
    "editable": "3c9e5a29c875ad854f7f9cfb124b9910dd8c46ed64819a529fd0e2f8e89f62d8",
    "compat": "86f1f51eece7d1d394015f8f33c75700ca48253214dc5d017a4aafee52f996bb",
}

COLOR_MAP = {
    "palette:ink": "#17253f",
    "palette:clay": "#b45a32",
    "palette:leaf": "#49765b",
    "palette:light": "#eee9dc",
    "palette:dark": "#171512",
}


def _representative_score() -> Score:
    return Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.13, 0.22],
                    "to": [0.87, 0.78],
                    "weight": "pencil",
                    "color": "red",
                    "color_hint": "deep blue wash",
                },
                {
                    "primitive": "circle",
                    "center": [0.68, 0.34],
                    "radius": 0.12,
                    "weight": "computer",
                    "color": "orange",
                    "color_hint": "brown earth",
                    "filled": True,
                },
            ],
        }
    )


def test_t3_color_and_document_profiles_keep_the_pre_move_bytes() -> None:
    score = _representative_score()

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(
            score,
            color_map=COLOR_MAP,
            catalog_id="stage3-characterization",
            svg_profile=profile,
            render_seed=31415,
        )
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


def test_t1_renderer_and_planning_use_the_canonical_palette_objects() -> None:
    palette = importlib.import_module("inku_server.render_engines.default.palette")
    planning = importlib.import_module("inku_server.render_engines.default.planning")
    names = (
        "COLOR_MAP",
        "HUE_HINTS",
        "_hex_to_rgb",
        "_hue_from_hex",
        "_oklch_from_hex",
        "_work_color_choice",
        "_work_color_assignment",
        "_hint_hues",
        "_resolve_color",
        "_render_effect_hint",
        "_norm_label",
    )

    for name in names:
        assert getattr(renderer, name) is getattr(palette, name)
    assert planning._render_effect_hint is palette._render_effect_hint
    assert planning._norm_label is palette._norm_label


def test_t2_renderer_reexports_the_canonical_document_objects() -> None:
    document = importlib.import_module("inku_server.render_engines.default.document")
    names = (
        "SVG_PROFILES",
        "_score_canvas_aspect",
        "_score_canvas_ground",
        "build_texture_metadata",
        "_normalize_svg_profile",
        "_safe_svg_id",
        "_instruction_svg_id",
        "_mark_svg_id",
        "_inject_svg_document_metadata",
        "_new_svg_drawing",
        "_build_root_groups",
        "_attach_root_groups",
        "_inject_extra_defs",
    )

    for name in names:
        assert getattr(renderer, name) is getattr(document, name)


def _import_names(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    names.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    return names


def test_t4_new_modules_have_one_way_dependencies_and_no_general_context() -> None:
    palette_imports = _import_names("inku_server.render_engines.default.palette")
    document_imports = _import_names("inku_server.render_engines.default.document")
    planning_imports = _import_names("inku_server.render_engines.default.planning")

    for imports in (palette_imports, document_imports, planning_imports):
        assert not any(name == "renderer" or name.endswith(".renderer") for name in imports)
    assert not any(name == "planning" or name.endswith(".planning") for name in palette_imports)

    default_package = Path(renderer.__file__).with_name("render_engines") / "default"
    production = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(default_package.glob("*.py"))
    )
    assert "class RenderContext" not in production
    assert "class RenderSession" not in production
