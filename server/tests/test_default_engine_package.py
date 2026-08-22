"""Stage 1 guards for the default-engine package and determinism kernel."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path

import inku_server.renderer as renderer
from inku_server.render_engines import current_render_engine
from inku_server.schema import Score


PROFILE_DIGESTS = {
    "display": "32deeb6aa00c2ddc2dbc035663491da98f453c762bc99dbe29e6f262f0bb0954",
    "editable": "19bb36c7888e94169ecd310ea272a253d4eac294fd28847c07f28f199a38c079",
    "compat": "864cc7e5a2194d33ae8966c26997360c77fae770c8a5f467c95896eead4fd1d2",
}


def _representative_score() -> Score:
    return Score.model_validate(
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


def test_t3_three_profiles_keep_the_pre_move_bytes() -> None:
    score = _representative_score()

    for profile, expected in PROFILE_DIGESTS.items():
        svg = renderer.render(score, svg_profile=profile, render_seed=431)
        assert hashlib.sha256(svg.encode()).hexdigest() == expected


def test_t1_default_engine_import_path_is_a_package_with_the_same_adapter() -> None:
    default_engine = importlib.import_module("inku_server.render_engines.default")
    adapter = importlib.import_module("inku_server.render_engines.default.adapter")

    assert hasattr(default_engine, "__path__")
    assert default_engine.DefaultRenderEngine is adapter.DefaultRenderEngine
    assert default_engine.DEFAULT_RENDER_ENGINE is current_render_engine()
    assert current_render_engine().id == "default"
    assert current_render_engine().version == "40"
    assert list(inspect.signature(adapter.DefaultRenderEngine.render).parameters) == [
        "self",
        "score",
        "color_map",
        "catalog_id",
        "canvas_aspect",
        "svg_profile",
        "render_seed",
        "composition_seed",
        "wild",
    ]


def test_t2_renderer_reexports_the_canonical_determinism_objects() -> None:
    determinism = importlib.import_module(
        "inku_server.render_engines.default.determinism"
    )
    names = (
        "_VARIATION_SEED_FIELDS_ALL",
        "_WORK_COLOR_SEED_FIELDS",
        "_SEED_INSTRUCTION_FIELDS",
        "_SEED_ARRANGEMENT_FIELDS",
        "_variation_seed_fields",
        "_seed_for_instruction",
        "new_render_seed",
        "_hash_to_unit",
        "_value_noise_1d",
        "_periodic_value_noise_1d",
        "_hash01",
        "_wave_phase",
    )

    for name in names:
        assert getattr(renderer, name) is getattr(determinism, name)


def test_t4_default_package_does_not_import_the_renderer_facade() -> None:
    package = Path(renderer.__file__).with_name("render_engines") / "default"

    for source in sorted(package.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        assert "inku_server.renderer" not in text
        assert "from ...renderer" not in text
        assert "from ..renderer" not in text
