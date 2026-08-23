"""Stage 4-2 guards for the default engine surface domain boundary."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
from pathlib import Path
from types import MappingProxyType

import inku_server.renderer as renderer
from inku_server.schema import Score


PROFILE_DIGESTS = {
    "display": "1701fbe038a4c15a5726588b5db0201e9d239682e43cd548db044d00ea190a70",
    "editable": "f72034f3a0d2a2a21d89b10255f6b742e75766e6e1e5449b4654df95f6ed0d42",
    "compat": "4f5820c96416c2949e5998523b55f0002514c1197e9e18679f8f63b1505c4c17",
}


def _representative_score() -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "square",
                    "position": [0.08, 0.12],
                    "size": [0.28, 0.24],
                    "weight": "pen",
                    "color": "blue",
                    "filled": False,
                    "surface": {
                        "texture": "grain",
                        "density": 0.44,
                        "scale": 0.37,
                        "opacity": 0.41,
                        "seed": 101,
                    },
                },
                {
                    "primitive": "circle",
                    "center": [0.68, 0.24],
                    "radius": 0.14,
                    "weight": "brush_thick",
                    "color": "red",
                    "filled": False,
                    "surface": {
                        "texture": "wash",
                        "density": 0.38,
                        "scale": 0.52,
                        "opacity": 0.33,
                        "seed": 202,
                    },
                },
                {
                    "primitive": "triangle",
                    "position": [0.10, 0.58],
                    "size": [0.30, 0.25],
                    "weight": "rotring",
                    "color": "green",
                    "filled": False,
                    "surface": {
                        "texture": "crosshatch",
                        "density": 0.47,
                        "scale": 0.45,
                        "opacity": 0.36,
                        "direction": "diagonal_falling",
                        "seed": 303,
                    },
                },
                {
                    "primitive": "cloudform",
                    "center": [0.69, 0.70],
                    "size": [0.27, 0.22],
                    "weight": "chalk",
                    "color": "purple",
                    "filled": False,
                    "surface": {
                        "texture": "bleed",
                        "density": 0.42,
                        "scale": 0.48,
                        "opacity": 0.31,
                        "bleed": 0.27,
                        "seed": 404,
                    },
                },
            ]
        }
    )


def test_t3_surface_profiles_keep_the_pre_move_bytes() -> None:
    score = _representative_score()

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(score, svg_profile=profile, render_seed=24680)
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


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


def test_t4_t5_surfaces_have_one_way_dependencies() -> None:
    engine = importlib.import_module("inku_server.render_engines.default.engine")
    surfaces = importlib.import_module("inku_server.render_engines.default.surfaces")
    imports = _import_names("inku_server.render_engines.default.surfaces")
    forbidden = ("renderer", "layers", "marks")
    assert not any(
        name == item or name.endswith(f".{item}")
        for name in imports
        for item in forbidden
    )
    assert dataclasses.is_dataclass(surfaces.SurfaceMarkStyle)
    assert surfaces.SurfaceMarkStyle.__dataclass_params__.frozen
    assert tuple(field.name for field in dataclasses.fields(surfaces.SurfaceMarkStyle)) == (
        "mark_width_px",
        "weight_style",
        "texture_filter_weights",
    )
    assert isinstance(engine._SURFACE_MARK_STYLE.weight_style, MappingProxyType)
    assert isinstance(engine._SURFACE_MARK_STYLE.texture_filter_weights, frozenset)
