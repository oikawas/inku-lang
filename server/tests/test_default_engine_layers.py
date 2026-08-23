"""Stage 4-1 guards for ground and presence layer boundaries."""

from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import inku_server.renderer as renderer
from inku_server.schema import Score


PROFILE_DIGESTS = {
    "display": "c7efa2169b8b5ef541a821881edbf28f00f9e598657852df316240ef09d81cff",
    "editable": "45aeeffbad633a6b097657c81de3eabb47189efde91446889bc0c8c30e4d4504",
    "compat": "275d32fe71cefb86a756f7608056b61cf6bc91f5086fbc2c82d236cdbee056ce",
}


def _representative_score() -> Score:
    return Score.model_validate(
        {
            "canvas": {
                "aspect": "portrait",
                "ground": {
                    "material": "washi",
                    "tone": "warm",
                    "grain": "coarse",
                    "density": 0.31,
                    "opacity": 0.17,
                },
            },
            "background": "white",
            "presence": {
                "kind": "group_like",
                "intensity": "high",
                "center": [0.61, 0.43],
                "symmetry": "radial",
                "gaze_pressure": "medium",
                "contour_density": "high",
            },
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.12, 0.18],
                    "to": [0.88, 0.79],
                    "weight": "pencil",
                    "color": "blue",
                },
                {
                    "primitive": "circle",
                    "center": [0.35, 0.63],
                    "radius": 0.11,
                    "weight": "computer",
                    "color": "orange",
                    "filled": True,
                },
            ],
        }
    )


def test_t3_ground_and_presence_profiles_keep_the_pre_move_bytes() -> None:
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


def test_t4_t5_layers_have_one_way_dependencies() -> None:
    imports = _import_names("inku_server.render_engines.default.layers")
    forbidden = ("renderer", "surfaces", "marks")
    assert not any(
        name == item or name.endswith(f".{item}")
        for name in imports
        for item in forbidden
    )
