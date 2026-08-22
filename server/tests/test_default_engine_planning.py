"""Stage 2 guards for the default-engine performance planning module."""

from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import inku_server.renderer as renderer
from inku_server.schema import Score


REPRESENTATIVE_DIGESTS = {
    "arrangement": "ca1346db46b630b1011b977cdf467e55323e4b266718e9437b3935b8c87c0d57",
    "composite_relation": "e7e28a9142662d2d0fc8afe3b479f7483812219089e28bb38d3c0b9b01919580",
}


def _representative_scores() -> dict[str, Score]:
    return {
        "arrangement": Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "square",
                        "position": [0.41, 0.43],
                        "size": [0.16, 0.12],
                        "weight": "pencil",
                        "color": "blue",
                        "arrangement": {
                            "count": 7,
                            "layout": "radial",
                            "radius": 0.27,
                            "center": [0.54, 0.46],
                            "fade": "outward",
                            "color_cycle": ["blue", "red"],
                        },
                    }
                ]
            }
        ),
        "composite_relation": Score.model_validate(
            {
                "instructions": [
                    {
                        "primitive": "arc",
                        "center": [0.5, 0.5],
                        "radius": 0.08,
                        "angle_start": 220,
                        "angle_end": 320,
                        "weight": "computer",
                        "arrangement": {
                            "count": 3,
                            "layout": "scatter",
                            "group_size": 2,
                        },
                        "at": {"region": [0.25, 0.25, 0.75, 0.75]},
                    },
                    {
                        "primitive": "arc",
                        "center": [0.5, 0.5],
                        "radius": 0.08,
                        "angle_start": 40,
                        "angle_end": 140,
                        "weight": "computer",
                        "relation": {"type": "touching"},
                    },
                ]
            }
        ),
    }


def test_t2_representative_planning_cases_keep_the_pre_move_bytes() -> None:
    for name, score in _representative_scores().items():
        svg = renderer.render(
            score, svg_profile="editable", render_seed=17, composition_seed=23
        )
        assert hashlib.sha256(svg.encode()).hexdigest() == REPRESENTATIVE_DIGESTS[name]


def test_t1_renderer_reexports_the_canonical_planning_objects() -> None:
    planning = importlib.import_module("inku_server.render_engines.default.planning")
    names = (
        "FRAME_LO",
        "FRAME_HI",
        "_PATH_WAVE_AMPLITUDE",
        "_PATH_JITTER",
        "_PATH_SPREAD",
        "_FADE_FILL_RATIO",
        "ARRANGEMENT_QUANTUM",
        "_anchor",
        "_resolve_performance_score",
        "_expand_arrangement_layout",
        "_expand_arrangement",
        "_apply_member_sizes",
        "_apply_member_rotations",
        "_quantise_instructions",
    )

    for name in names:
        assert getattr(renderer, name) is getattr(planning, name)


def test_t3_reference_generators_patch_the_canonical_planning_module() -> None:
    server_root = Path(__file__).resolve().parents[1]
    render_source = (server_root / "scripts/gen_render_reference.py").read_text()
    android_source = (server_root / "scripts/gen_android_reference.py").read_text()

    assert "planning._apply_member_sizes =" in render_source
    assert "planning._apply_member_rotations =" in render_source
    assert "setattr(planning, name," in android_source


def test_t4_planning_does_not_import_renderer_or_svgwrite() -> None:
    planning = importlib.import_module("inku_server.render_engines.default.planning")
    source = Path(planning.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert not any(name == "svgwrite" or name.endswith(".svgwrite") for name in imports)
    assert not any(name == "renderer" or name.endswith(".renderer") for name in imports)
