"""Stage 5 guards for the default engine instruction dispatch boundary."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib
import inspect
from pathlib import Path

import pytest
import svgwrite

import inku_server.renderer as renderer
from inku_server.plugins.system.canvas_aspect import canvas_size_for_aspect
from inku_server.schema import Instruction, Score


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
            ]
        }
    )


def test_t4_dispatch_profiles_keep_the_pre_move_bytes() -> None:
    score = _representative_score()

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(score, svg_profile=profile, render_seed=24680)
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


def test_t3_unknown_primitive_keeps_the_explicit_fallback() -> None:
    instruction = Instruction.model_construct(primitive="unknown")
    canvas = canvas_size_for_aspect(None)
    drawing = svgwrite.Drawing(size=(canvas.width, canvas.height))

    with pytest.raises(
        NotImplementedError,
        match=r"^primitive 'unknown' not yet supported$",
    ):
        renderer._render_instruction(
            drawing,
            instruction,
            canvas=canvas,
            support=renderer._score_support(Score(instructions=[])),
        )


def test_t3_dispatch_signature_keeps_the_renderer_contract() -> None:
    parameters = inspect.signature(renderer._render_instruction).parameters

    assert list(parameters) == [
        "dwg",
        "ins",
        "cmap",
        "canvas",
        "work_assignment",
        "use_filters",
        "solid_mottle_filter_id",
        "support",
        "render_seed",
        "ins_idx",
        "mark_idx",
        "wild",
    ]
    assert parameters["cmap"].default is renderer.COLOR_MAP
    assert parameters["canvas"].default is None
    assert parameters["work_assignment"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["support"].default is inspect.Parameter.empty


def test_t1_renderer_facade_uses_the_canonical_dispatch() -> None:
    dispatch = importlib.import_module("inku_server.render_engines.default.dispatch")

    assert renderer._render_instruction is dispatch._render_instruction
    assert renderer._render_instruction.__module__ == (
        "inku_server.render_engines.default.dispatch"
    )
    assert renderer.render.__module__ == "inku_server.renderer"


def test_t2_dispatch_order_is_explicit_and_has_no_registry() -> None:
    dispatch = importlib.import_module("inku_server.render_engines.default.dispatch")
    source = inspect.getsource(dispatch._render_instruction)
    primitives = [
        "line",
        "circle",
        "ellipse",
        "cloudform",
        "square",
        "triangle",
        "polygon",
        "arc",
    ]

    offsets = [source.index(f'if ins.primitive == "{name}":') for name in primitives]
    assert offsets == sorted(offsets)
    assert "NotImplementedError" in source
    assert "registry" not in source
    assert "getattr(" not in source


def test_t5_dispatch_imports_only_explicit_lower_domains() -> None:
    dispatch = importlib.import_module("inku_server.render_engines.default.dispatch")
    path = Path(dispatch.__file__)
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                modules.add(node.module.rsplit(".", 1)[-1])
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)

    assert not {"renderer", "layers", "document", "engine"} & modules


def test_t5_dispatch_keeps_the_two_field_frozen_surface_projection() -> None:
    dispatch = importlib.import_module("inku_server.render_engines.default.dispatch")

    projection = dispatch._MARK_SURFACE_OPS
    assert [field.name for field in dataclasses.fields(projection)] == [
        "fills_interior",
        "scatter",
    ]
    assert type(projection).__dataclass_params__.frozen is True


def test_t6_renderer_is_smaller_after_dispatch_extraction() -> None:
    assert len(Path(renderer.__file__).read_text().splitlines()) < 1144
