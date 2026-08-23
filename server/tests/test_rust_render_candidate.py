from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from inku_server.render_engines import RenderEngineResult
from inku_server.render_engines import rust_candidate
from inku_server.render_engines.rust_candidate import RustCandidateRenderEngine
from inku_server.schema import Score


SERVER_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_render_reference.py"
ENGINE_41_CORPUS_DIR = SERVER_ROOT / "reference" / "render-engine-41"


def _reference_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_render_reference_candidate", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_adapter_uses_one_canonical_request(monkeypatch):
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
    monkeypatch.setattr(rust_candidate, "_native_binding", lambda: native)
    engine = RustCandidateRenderEngine()
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


def test_current_engine_is_the_accepted_rust_engine():
    from inku_server.render_engines import RUST_RENDER_ENGINE, current_render_engine

    assert current_render_engine() is RUST_RENDER_ENGINE
    assert current_render_engine().id == "default"
    assert current_render_engine().version == "41"


def test_reference_case_uses_the_explicit_candidate_engine():
    generator = _reference_generator()
    render_input = generator.build_inputs()["A-pen-line"]
    calls: list[tuple[Score, dict[str, object]]] = []

    class CandidateEngine:
        id = "candidate"
        version = "41"

        def render(self, score: Score, **options: object) -> RenderEngineResult:
            calls.append((score, options))
            return RenderEngineResult(svg="<svg data-engine='candidate'/>", metadata={})

    svg = generator.render_case(render_input, engine=CandidateEngine())

    assert svg == "<svg data-engine='candidate'/>"
    assert len(calls) == 1
    score, options = calls[0]
    assert score.instructions[0].primitive == "line"
    assert options["render_seed"] == render_input["render_seed"]
    assert options["svg_profile"] == render_input["svg_profile"]


def test_candidate_generation_reuses_manifest_logic_in_an_explicit_destination(
    tmp_path: Path,
    monkeypatch,
):
    generator = _reference_generator()
    render_input = generator.build_inputs()["A-pen-line"]
    calls: list[Score] = []

    class CandidateEngine:
        id = "candidate"
        version = "41"

        def render(self, score: Score, **_options: object) -> RenderEngineResult:
            calls.append(score)
            return RenderEngineResult(svg="<svg class='candidate'/>", metadata={})

    monkeypatch.setattr(generator, "build_inputs", lambda: {"A-pen-line": render_input})
    for check in (
        "_assert_fade_cases_discriminate",
        "_assert_fade_reaches_every_member",
        "_assert_size_cases_discriminate",
        "_assert_angle_cases_discriminate",
    ):
        monkeypatch.setattr(generator, check, lambda *_args, **_kwargs: None)

    output_dir = tmp_path / "candidate-corpus"
    generator.generate(
        engine=CandidateEngine(),
        output_dir=output_dir,
        frozen_at="2026-08-24",
        source_commit="accepted-candidate",
        reason="Accepted candidate freeze.",
    )

    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest["engine_id"] == "candidate"
    assert manifest["engine_version"] == "41"
    assert manifest["frozen_at"] == "2026-08-24"
    assert manifest["commit"] == "accepted-candidate"
    assert manifest["reason"] == "Accepted candidate freeze."
    assert set(manifest["cases"]) == {"A-pen-line"}
    assert (output_dir / "A-pen-line.svg").read_text() == "<svg class='candidate'/>"
    assert len(calls) == 1


def test_explicit_candidate_generation_requires_an_explicit_destination():
    generator = _reference_generator()

    with pytest.raises(ValueError, match="explicit output directory"):
        generator.generate(engine=SimpleNamespace(id="candidate", version="41"))


def test_explicit_candidate_generation_requires_freeze_metadata(tmp_path: Path):
    generator = _reference_generator()

    with pytest.raises(ValueError, match="explicit freeze metadata"):
        generator.generate(
            engine=SimpleNamespace(id="candidate", version="41"),
            output_dir=tmp_path / "candidate-corpus",
        )


def test_accepted_engine_41_candidate_corpus_is_internally_complete():
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
