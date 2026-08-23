"""Stage 6 guards for default-engine orchestration and facade boundaries."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
from pathlib import Path
from typing import get_type_hints

import inku_server.renderer as renderer
from inku_server.render_engines import current_render_engine
from inku_server.render_engines.base import RenderEngineResult
from inku_server.schema import Score
from inku_server.render_engines.default import document


PROFILE_DIGESTS = {
    "display": "32deeb6aa00c2ddc2dbc035663491da98f453c762bc99dbe29e6f262f0bb0954",
    "editable": "19bb36c7888e94169ecd310ea272a253d4eac294fd28847c07f28f199a38c079",
    "compat": "864cc7e5a2194d33ae8966c26997360c77fae770c8a5f467c95896eead4fd1d2",
}


def _representative_score() -> Score:
    return Score.model_validate(
        {
            "canvas": {
                "aspect": "square",
                "ground": {"material": "paper", "tone": "warm", "grain": "medium"},
            },
            "instructions": [
                {
                    "primitive": "circle",
                    "center": [0.5, 0.5],
                    "radius": 0.16,
                    "weight": "pencil",
                    "variation": {
                        "amplitude": "medium",
                        "frequency": "high",
                        "quality": "perlin",
                        "dimensions": ["position_x", "position_y"],
                    },
                    "filled": True,
                    "surface": {
                        "texture": "wash",
                        "density": 0.3,
                        "opacity": 0.45,
                    },
                }
            ],
        }
    )


def test_t1_engine_returns_svg_and_metadata_as_one_result() -> None:
    engine = importlib.import_module("inku_server.render_engines.default.engine")
    score = _representative_score()

    result = engine.render_result(score, svg_profile="compat", render_seed=431)

    assert isinstance(result, RenderEngineResult)
    assert result.metadata["render_engine_id"] == "default"
    assert result.metadata["render_engine_version"] == "40"
    assert result.metadata["render_texture_profile"] == "compat"
    assert result.metadata["texture_degraded"] is True
    assert result.metadata["render_canvas_ground"]["material"] == "paper"
    assert result.metadata["render_surface_textures"][0]["texture"] == "wash"
    assert renderer.render(score, svg_profile="compat", render_seed=431) == result.svg
    assert (
        current_render_engine().render(
            score, svg_profile="compat", render_seed=431
        )
        == result
    )


def test_t2_adapter_returns_the_canonical_result_directly(monkeypatch) -> None:
    adapter = importlib.import_module("inku_server.render_engines.default.adapter")
    engine = importlib.import_module("inku_server.render_engines.default.engine")
    score = _representative_score()
    expected = RenderEngineResult(svg="<svg />", metadata={"sentinel": "yes"})
    captured: dict[str, object] = {}

    def fake_render_result(received_score: Score, **kwargs: object) -> RenderEngineResult:
        captured["score"] = received_score
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(engine, "render_result", fake_render_result)

    actual = adapter.DefaultRenderEngine().render(
        score,
        color_map={"black": "#111111"},
        catalog_id="test-catalog",
        canvas_aspect="wide",
        svg_profile="editable",
        render_seed=17,
        composition_seed=23,
        wild=True,
    )

    assert actual is expected
    assert captured == {
        "score": score,
        "color_map": {"black": "#111111"},
        "catalog_id": "test-catalog",
        "canvas_aspect": "wide",
        "svg_profile": "editable",
        "render_seed": 17,
        "composition_seed": 23,
        "wild": True,
    }


def test_t3_three_profiles_keep_the_pre_move_bytes() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.15, 0.25],
                    "to": [0.85, 0.75],
                    "weight": "pencil",
                    "variation": {
                        "amplitude": "medium",
                        "frequency": "high",
                        "quality": "perlin",
                        "dimensions": ["position_x", "position_y"],
                    },
                }
            ]
        }
    )

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(score, svg_profile=profile, render_seed=431)
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


def test_t4_engine_states_the_orchestration_order_explicitly() -> None:
    engine = importlib.import_module("inku_server.render_engines.default.engine")
    source = inspect.getsource(engine.render_result)
    steps = (
        "document._normalize_svg_profile",
        "canvas_size_for_aspect",
        "planning._resolve_performance_score",
        "document._new_svg_drawing",
        "layers._render_canvas_ground",
        "dispatch._render_instruction",
        "surfaces._render_surface_texture",
        "layers._render_presence_layer",
        "document._inject_extra_defs",
        "validate_compat_svg",
        "return RenderEngineResult(",
    )

    offsets = [source.index(step) for step in steps]
    assert offsets == sorted(offsets)


def test_t5_facade_and_adapter_have_no_orchestration_binding() -> None:
    adapter = importlib.import_module("inku_server.render_engines.default.adapter")
    engine = importlib.import_module("inku_server.render_engines.default.engine")
    registry = importlib.import_module("inku_server.render_engines")

    assert list(inspect.signature(renderer.render).parameters) == [
        "score",
        "color_map",
        "catalog_id",
        "canvas_aspect",
        "svg_profile",
        "render_seed",
        "composition_seed",
        "wild",
    ]
    assert renderer.render.__module__ == "inku_server.renderer"
    assert document.build_texture_metadata.__module__ == (
        "inku_server.render_engines.default.document"
    )
    assert "_render_engines.current_render_engine" in inspect.getsource(renderer.render)
    assert not hasattr(adapter, "render_svg")
    assert not hasattr(adapter, "build_texture_metadata")
    assert not hasattr(adapter, "_bind_renderer")
    assert "_bind_renderer" not in Path(registry.__file__).read_text()
    assert not hasattr(renderer, "_SURFACE_MARK_STYLE")
    assert not hasattr(renderer, "_MARK_SURFACE_OPS")
    assert engine._SURFACE_MARK_STYLE is not None


def test_t7_host_contract_owns_profiles_and_seed() -> None:
    host_contract = importlib.import_module("inku_server.render_engines")
    profiles = importlib.import_module("inku_server.render_engines.profiles")
    seeds = importlib.import_module("inku_server.render_engines.seeds")
    determinism = importlib.import_module(
        "inku_server.render_engines.default.determinism"
    )

    assert host_contract.SVG_PROFILES is profiles.SVG_PROFILES
    assert document.SVG_PROFILES is profiles.SVG_PROFILES
    assert document._normalize_svg_profile is profiles.normalize_svg_profile
    assert host_contract.new_render_seed is seeds.new_render_seed
    assert determinism.new_render_seed is seeds.new_render_seed
    assert 0 <= host_contract.new_render_seed() <= 2**53 - 1


def test_t8_render_metadata_type_accepts_json_compatible_values() -> None:
    hints = get_type_hints(RenderEngineResult)

    assert hints["metadata"] == dict[str, object]


def test_t6_default_engine_modules_do_not_import_renderer() -> None:
    package = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "inku_server"
        / "render_engines"
        / "default"
    )

    for source in sorted(package.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        )
        assert not any(
            name == "renderer" or name.endswith(".renderer") for name in imported
        )
