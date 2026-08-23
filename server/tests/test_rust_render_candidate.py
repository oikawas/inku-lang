from __future__ import annotations

import json
from types import SimpleNamespace

from inku_server.render_engines import rust_candidate
from inku_server.render_engines.rust_candidate import RustCandidateRenderEngine
from inku_server.schema import Score


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


def test_candidate_import_does_not_change_the_current_engine():
    from inku_server.render_engines import current_render_engine

    assert current_render_engine().version == "40"
