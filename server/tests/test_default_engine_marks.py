"""Stage 4-3 guards for the default engine mark domain boundary."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
from pathlib import Path

import inku_server.renderer as renderer
from inku_server.schema import Score


PROFILE_DIGESTS = {
    "display": "b24cadaa068b31100f56bb749b20e1b28a01b6dc7f77922b2c7877399d9fbd8f",
    "editable": "53a4ce8b93c37566dc089fb2d14ee148bb2ac8a8e1131d7d7bf59ec62300a5a0",
    "compat": "8adbc921f30afbcdb59248a3f5c9fe6b163cb640cca8b48c654e1f54d407da6a",
}


def _representative_score() -> Score:
    return Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.06, 0.10],
                    "to": [0.42, 0.24],
                    "weight": "pen",
                    "color": "blue",
                    "variation": {
                        "amplitude": "fine",
                        "frequency": "high",
                        "quality": "wave",
                        "dimensions": ["position_y"],
                    },
                },
                {
                    "primitive": "circle",
                    "center": [0.68, 0.17],
                    "radius": 0.10,
                    "weight": "brush_thick",
                    "color": "red",
                    "surface": {"texture": "solid"},
                },
                {
                    "primitive": "ellipse",
                    "center": [0.24, 0.43],
                    "size": [0.26, 0.14],
                    "weight": "pencil",
                    "thinness": "fine",
                    "color": "gray",
                    "filled": True,
                },
                {
                    "primitive": "square",
                    "position": [0.52, 0.34],
                    "size": [0.22, 0.18],
                    "weight": "computer",
                    "color": "green",
                    "filled": True,
                },
                {
                    "primitive": "triangle",
                    "position": [0.08, 0.63],
                    "size": [0.23, 0.20],
                    "weight": "chalk",
                    "color": "orange",
                    "filled": True,
                },
                {
                    "primitive": "polygon",
                    "center": [0.48, 0.72],
                    "radius": 0.12,
                    "sides": 6,
                    "rotation": 17,
                    "weight": "drypoint",
                    "color": "black",
                    "mode": "carve",
                    "carve_depth": "half",
                },
                {
                    "primitive": "arc",
                    "center": [0.76, 0.68],
                    "radius": 0.14,
                    "angle_start": 15,
                    "angle_end": 245,
                    "weight": "burin",
                    "color": "purple",
                    "variation": {
                        "amplitude": "medium",
                        "frequency": "slow",
                        "quality": "perlin",
                        "dimensions": ["position_x", "position_y"],
                    },
                },
                {
                    "primitive": "cloudform",
                    "center": [0.78, 0.89],
                    "size": [0.24, 0.12],
                    "weight": "brush_thin",
                    "color": "blue",
                    "filled": True,
                },
            ],
        }
    )


def test_t3_mark_profiles_keep_the_pre_move_bytes() -> None:
    score = _representative_score()

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(score, svg_profile=profile, render_seed=24680)
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


def test_t1_renderer_facade_uses_canonical_mark_owners() -> None:
    marks = importlib.import_module("inku_server.render_engines.default.marks")

    for name in (
        "WEIGHT_TO_STROKE_WIDTH",
        "WEIGHT_STYLE",
        "TEXTURE_FILTER_WEIGHTS",
        "FILL_COVERAGE_BRANCH",
        "_mark_width_px",
        "_texture_filter_xml",
        "_line_with_variation",
        "_stroke_attrs",
        "_material_outline_profile",
        "_render_fill_strokes",
        "_render_fill_texture",
        "_interior_fill",
        "_render_hand_stroke",
        "_render_contour_hand_stroke",
        "_render_arc_hand_stroke",
        "_render_corner_shape",
    ):
        assert getattr(renderer, name) is getattr(marks, name)

    assert renderer.render.__module__ == "inku_server.renderer"
    assert renderer._render_instruction.__module__ == "inku_server.renderer"


def test_t1_marks_has_a_small_frozen_surface_projection() -> None:
    marks = importlib.import_module("inku_server.render_engines.default.marks")

    assert dataclasses.is_dataclass(marks.MarkSurfaceOps)
    assert [field.name for field in dataclasses.fields(marks.MarkSurfaceOps)] == [
        "fills_interior",
        "scatter",
    ]
    assert marks.MarkSurfaceOps.__dataclass_params__.frozen is True


def test_t1_marks_does_not_import_orchestration_domains() -> None:
    path = Path(renderer.__file__).parent / "render_engines" / "default" / "marks.py"
    tree = ast.parse(path.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert not {"renderer", "surfaces", "layers"} & imported


def test_t1_renderer_is_smaller_after_mark_extraction() -> None:
    assert len(Path(renderer.__file__).read_text().splitlines()) < 4554
