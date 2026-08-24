from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from inku_server.render_engines import RenderEngineResult, current_render_engine
from inku_server.render_engines.default import adapter
from inku_server.render_engines.default.adapter import DefaultRenderEngine
from inku_server.schema import Score


SERVER_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_41_CORPUS_DIR = SERVER_ROOT / "reference" / "render-engine-41"


def _reference_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_render_reference_explicit", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_adapter_uses_one_canonical_request(monkeypatch):
    calls: list[dict] = []

    def render(request_json: str) -> tuple[str, str]:
        request = json.loads(request_json)
        calls.append(request)
        return "<svg/>", json.dumps(
            {"render_engine_id": "default", "render_engine_version": "41"}
        )

    native = SimpleNamespace(
        default_color_map_json=lambda: json.dumps({"black": "#111111"}),
        render_engine_id=lambda: "default",
        render_engine_version=lambda: "41",
        render=render,
    )
    monkeypatch.setattr(adapter, "_native_binding", lambda: native)
    engine = DefaultRenderEngine()
    score = Score.model_validate(
        {
            "canvas": {"aspect": "a4"},
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.2], "to": [0.9, 0.8]}
            ],
        }
    )
    result = engine.render(
        score,
        svg_profile="compat",
        render_seed=0,
        composition_seed=-7,
    )
    assert engine.id == "default"
    assert engine.version == "41"
    assert result.svg == "<svg/>"
    assert result.metadata["render_engine_version"] == "41"
    assert len(calls) == 1
    request = calls[0]
    assert request["score"]["instructions"][0]["from"] == [0.1, 0.2]
    assert request["score"]["instructions"][0]["radius"] is None
    assert request["options"]["svg_profile"] == "compat"
    assert request["options"]["render_seed"] == 0
    assert request["options"]["composition_seed"] == -7
    assert request["options"]["canvas"]["height"] == 1000
    assert request["options"]["canvas"]["width"] < 1000


def test_current_engine_is_the_default_rust_adapter():
    assert current_render_engine() is adapter.DEFAULT_RENDER_ENGINE
    assert current_render_engine().id == "default"
    assert current_render_engine().version == "41"


def test_default_package_exports_the_thin_adapter_contract():
    default_engine = __import__(
        "inku_server.render_engines.default", fromlist=["DEFAULT_RENDER_ENGINE"]
    )

    assert default_engine.DefaultRenderEngine is DefaultRenderEngine
    assert default_engine.DEFAULT_RENDER_ENGINE is current_render_engine()
    assert list(inspect.signature(DefaultRenderEngine.render).parameters) == [
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


def test_reference_case_uses_the_explicit_engine():
    generator = _reference_generator()
    render_input = generator.build_inputs()["A-pen-line"]
    calls: list[tuple[Score, dict[str, object]]] = []

    class ExplicitEngine:
        id = "explicit"
        version = "41"

        def render(self, score: Score, **options: object) -> RenderEngineResult:
            calls.append((score, options))
            return RenderEngineResult(svg="<svg data-engine='explicit'/>", metadata={})

    svg = generator.render_case(render_input, engine=ExplicitEngine())

    assert svg == "<svg data-engine='explicit'/>"
    assert len(calls) == 1
    score, options = calls[0]
    assert score.instructions[0].primitive == "line"
    assert options["render_seed"] == render_input["render_seed"]
    assert options["svg_profile"] == render_input["svg_profile"]


def test_explicit_generation_reuses_manifest_logic_in_an_explicit_destination(
    tmp_path: Path,
    monkeypatch,
):
    generator = _reference_generator()
    render_input = generator.build_inputs()["A-pen-line"]
    calls: list[Score] = []

    class ExplicitEngine:
        id = "explicit"
        version = "41"

        def render(self, score: Score, **_options: object) -> RenderEngineResult:
            calls.append(score)
            return RenderEngineResult(svg="<svg class='explicit'/>", metadata={})

    monkeypatch.setattr(generator, "build_inputs", lambda: {"A-pen-line": render_input})
    output_dir = tmp_path / "explicit-corpus"
    generator.generate(
        engine=ExplicitEngine(),
        output_dir=output_dir,
        frozen_at="2026-08-24",
        source_commit="explicit-engine",
        reason="Explicit engine freeze.",
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest["engine_id"] == "explicit"
    assert manifest["engine_version"] == "41"
    assert manifest["frozen_at"] == "2026-08-24"
    assert manifest["commit"] == "explicit-engine"
    assert manifest["reason"] == "Explicit engine freeze."
    assert set(manifest["cases"]) == {"A-pen-line"}
    assert (output_dir / "A-pen-line.svg").read_text() == "<svg class='explicit'/>"
    assert len(calls) == 1


def test_explicit_generation_requires_an_explicit_destination():
    generator = _reference_generator()

    with pytest.raises(ValueError, match="explicit output directory"):
        generator.generate(engine=SimpleNamespace(id="candidate", version="41"))


def test_explicit_generation_requires_freeze_metadata(tmp_path: Path):
    generator = _reference_generator()

    with pytest.raises(ValueError, match="explicit freeze metadata"):
        generator.generate(
            engine=SimpleNamespace(id="candidate", version="41"),
            output_dir=tmp_path / "candidate-corpus",
        )


def test_accepted_engine_41_corpus_is_internally_complete():
    generator = _reference_generator()
    manifest = json.loads((ENGINE_41_CORPUS_DIR / "manifest.json").read_text())

    assert manifest["engine_id"] == "default"
    assert manifest["engine_version"] == "41"
    assert manifest["frozen_at"] == "2026-08-24"
    assert manifest["commit"] == "56fae469e94c6a9f8d31de26ca9207fde7155831"
    cases = manifest["cases"]
    changed = set(manifest["changed_from_previous"])
    bodies = {path.stem for path in ENGINE_41_CORPUS_DIR.glob("*.svg")}
    assert len(cases) == 610
    assert changed == set(cases) == bodies
    for case_id, case in cases.items():
        svg = (ENGINE_41_CORPUS_DIR / f"{case_id}.svg").read_text()
        assert len(svg.encode()) == case["bytes"], case_id
        assert generator._normalized_digest(svg) == case["digest"], case_id
