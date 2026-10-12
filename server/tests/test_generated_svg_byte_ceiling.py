"""SVG output safety at the host boundary, with no native/image execution."""

from __future__ import annotations

import json
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from concurrent.futures import Future

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from inku_server.api_core import rendering
from inku_server.pipeline_candidate import CandidateExecution
from inku_server import db, limits
from inku_server.api_core.routers import settings, history, render
from inku_server.api_core.deps import _admin_user, _current_user
from inku_server.persistence.settings import RenderLimitSettingsStore
from inku_server.persistence.variation_authority import VariationAuthorityStore, ExecutionSnapshotConflict
from inku_server.pipeline_api import PipelineService
from inku_server.pipeline_product import ProductPipelineEffects


def _snapshot():
    return {
        "execution_id": "execution", "variation_id": "variation", "sequence": "1",
        "authority": {"revision": "1"}, "document": {"source": "a circle"},
        "delivery": {"score": {"instructions": []}}, "phase": {"tag": "score_ready"},
        "action": None,
    }


class _Binding:
    def __init__(self, svg):
        self.svg = svg
        self.limits = []

    def step(self, snapshot_bytes, input_bytes):
        snapshot = json.loads(snapshot_bytes)
        snapshot["sequence"] = json.loads(input_bytes)["sequence"]
        return json.dumps({"kind": "output", "payload": {"result": {
            "snapshot": snapshot, "events": [], "rendered": {"svg": self.svg, "metadata": {}},
        }}}).encode()

    def step_with_svg_limit(self, snapshot_bytes, input_bytes, limit):
        self.limits.append(limit)
        result = json.loads(self.step(snapshot_bytes, input_bytes))
        result["payload"]["result"]["rendered"]["svg"] = ""
        return json.dumps(result).encode(), self.svg


def _run(monkeypatch, svg, *, context=None):
    monkeypatch.setattr(rendering, "_generated_svg_limit_bytes", lambda: 5, raising=False)
    monkeypatch.setattr(rendering, "_render_capacity", lambda _owner: nullcontext())
    saved = []
    run = CandidateExecution(
        _Binding(svg), SimpleNamespace(), owner_id="author",
        config={"envelope_limits": {
            "max_input_bytes": 4096, "max_snapshot_bytes": 4096, "max_output_bytes": 4096,
        }}, provider=lambda _: None, allow_render=True, context=context,
        save_snapshot=lambda *args: saved.append(deepcopy(args)),
    )
    run.restore(_snapshot())
    return run, saved


def test_oversized_fresh_svg_is_refused_before_transcript_projection_or_save(monkeypatch):
    run, saved = _run(monkeypatch, "日本")  # Six UTF-8 bytes, only two characters.
    before = run.snapshot()
    with pytest.raises(HTTPException) as refused:
        run.command({"tag": "render"})
    assert refused.value.status_code == 422
    assert refused.value.detail["code"] == "generated_svg_too_large"
    assert refused.value.detail["limit_bytes"] == 5
    assert run.snapshot() == before
    assert run.transcript == []
    assert saved == []
    assert run.view()["result"] is None
    assert run.view()["rendered"] is None


def test_byte_boundary_multibyte_and_production_units():
    assert limits.SVG_LIMIT_DEFAULT_MIB * limits.SVG_MIB == 12_582_912
    assert limits.SVG_LIMIT_MIN_MIB * limits.SVG_MIB == 1_048_576
    assert limits.SVG_LIMIT_MAX_MIB * limits.SVG_MIB == 33_554_432
    rendering._validate_generated_svg("日", 3)
    with pytest.raises(HTTPException) as refused:
        rendering._validate_generated_svg("日a", 3)
    assert refused.value.status_code == 422
    assert refused.value.detail["limit_bytes"] == 3


def test_accepted_raw_svg_is_unchanged_and_runtime_policy_is_not_serialized(monkeypatch):
    run, saved = _run(monkeypatch, "日ab")
    run.command({"tag": "render"})
    assert saved[-1][3]["svg"] == "日ab"
    assert run.view()["rendered"]["svg"] == "日ab"
    assert run.binding.limits == [5]
    assert "max_svg_bytes" not in json.dumps(run.snapshot())
    assert "max_generated_svg_mib" not in json.dumps(run.snapshot())


def test_settings_partial_update_range_reset_and_no_work_limit_identity(monkeypatch):
    class MemorySettings:
        value = {"max_expanded_primitives": 321}

        def read(self, _key):
            return self.value

        def write(self, _key, value):
            self.value = value
            return value

    memory = MemorySettings()
    store = RenderLimitSettingsStore(memory, limits.normalize_render_limit_settings)
    monkeypatch.setattr(db, "_render_limit_settings_store", lambda: store)
    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[_admin_user] = lambda: {"id": "admin"}
    client = TestClient(app)
    assert settings._render_limits_status().limits[limits.SVG_LIMIT_FIELD] == 12
    for requested, expected in [(32, 32), (0, 1), (33, 32), (1, 1)]:
        response = client.put("/api/settings/limits", json={limits.SVG_LIMIT_FIELD: requested})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["limits"][limits.SVG_LIMIT_FIELD] == expected
        assert payload["limits"]["max_expanded_primitives"] == 321
        assert payload["defaults"][limits.SVG_LIMIT_FIELD] == 12
        assert payload["field_bounds"][limits.SVG_LIMIT_FIELD] == {"min": 1, "max": 32, "step": 1}
        assert limits.SVG_LIMIT_FIELD not in limits.limits_as_dict(limits.limits_from_settings(payload["limits"]))
    assert store.get()[limits.SVG_LIMIT_FIELD] == 1
    for invalid in [1.5, True, "garbage"]:
        assert client.put("/api/settings/limits", json={limits.SVG_LIMIT_FIELD: invalid}).status_code == 422
    assert client.put("/api/settings/limits", json={"reset_to_defaults": True}).json()["limits"][limits.SVG_LIMIT_FIELD] == 12
    assert client.put("/api/settings/limits", json={"max_instructions": 10}).json()["limits"][limits.SVG_LIMIT_FIELD] == 12


def test_refusal_survives_restore_without_replacing_the_legal_core_state(tmp_path):
    store = VariationAuthorityStore(create_engine(f"sqlite:///{tmp_path / 'refusal.db'}"))
    store.install_schema()
    snapshot = _snapshot()
    legal = {"svg": "<svg/>", "metadata": {}}
    context = {"result": {"svg": "<svg/>", "history_id": "legal-work"}}
    wrapper = {"snapshot": snapshot, "context": context, "rendered": legal}
    store.create_execution("author", "execution", "variation", "1", json.dumps(wrapper).encode())
    detail = {"code": "generated_svg_too_large", "limit_bytes": limits.SVG_MIB, "limit_mib": 1}
    store.record_render_refusal("author", "execution", expected_sequence="1", detail=detail)
    stored = json.loads(store.read_execution("author", "execution").state_bytes)
    assert stored["snapshot"] == snapshot
    assert stored["rendered"] == legal
    assert stored["context"]["result"] == context["result"]
    run = CandidateExecution(SimpleNamespace(), store, owner_id="author", config={},
                             provider=lambda _: None, context=stored["context"])
    run.restore(stored["snapshot"], rendered=stored["rendered"])
    assert run.view()["current_render_refusal"] == detail
    assert run.view()["result"] is None
    assert run.view()["rendered"] is None
    with pytest.raises(ExecutionSnapshotConflict):
        store.record_render_refusal("another-owner", "execution", expected_sequence="1", detail=detail)
    with pytest.raises(ExecutionSnapshotConflict):
        store.record_render_refusal("author", "execution", expected_sequence="2", detail=detail)


@pytest.mark.parametrize("common", ["_render_score_svg", "_render_with_metadata"])
def test_legacy_common_paths_refuse_before_return_and_use_same_runtime_limit(monkeypatch, common):
    calls = []

    class Engine:
        def render(self, _score, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(svg="日本", metadata={})

    monkeypatch.setattr(rendering, "_render_capacity", lambda _owner: nullcontext())
    monkeypatch.setattr(rendering, "_generated_svg_limit_bytes", lambda: 5)
    monkeypatch.setattr(rendering, "current_render_engine", lambda: Engine())
    monkeypatch.setattr(rendering, "_limits_for_render", lambda *_: (object(), "settings"))
    monkeypatch.setattr(rendering, "coerce_saved_score", lambda *_, **__: object())
    monkeypatch.setattr(rendering, "_color_render_metadata", lambda **_: ({"render_color_map": {}}, "default", "catalog"))
    with pytest.raises(HTTPException) as refused:
        if common == "_render_score_svg":
            rendering._render_score_svg({}, catalog_id="default")
        else:
            rendering._render_with_metadata(object(), {"render_color_map": {}, "render_seed": 1})
    assert refused.value.detail["code"] == "generated_svg_too_large"
    assert calls[0]["max_svg_bytes"] == 5


def test_stored_display_is_exact_but_fresh_history_profile_is_checked(monkeypatch):
    stored_svg = "日本"  # Oversized only under the tiny injected fixture bound.
    monkeypatch.setattr(history._db, "get_items", lambda *_: [{"score": {}, "svg": stored_svg}])

    def refuse(*_, **__):
        rendering._validate_generated_svg(stored_svg, 5)

    monkeypatch.setattr(history, "_render_score_svg", refuse)
    assert history.api_history_svg("work", profile="display", actor={"id": "author"}).body == stored_svg.encode()
    with pytest.raises(HTTPException) as refused:
        history.api_history_svg("work", profile="editable", actor={"id": "author"})
    assert refused.value.status_code == 422


def test_stream_refusal_keeps_status_and_detail_and_has_no_done(monkeypatch):
    detail = {"code": "generated_svg_too_large", "limit_mib": 1, "limit_bytes": limits.SVG_MIB}

    def events(*_):
        yield {"event": "stage1", "ddl": "a circle"}
        raise HTTPException(422, detail)

    monkeypatch.setattr(render._pipeline_compat, "paint_events", events)
    app = FastAPI()
    app.include_router(render.router)
    app.dependency_overrides[_current_user] = lambda: {"id": "author"}
    response = TestClient(app).post("/api/paint/stream", json={"description": "a circle"})
    assert response.status_code == 200
    data = [json.loads(line) for line in response.text.splitlines()]
    assert [item["event"] for item in data] == ["stage1", "error"]
    assert data[-1] == {"event": "error", "status": 422, "detail": detail}


def test_async_refusal_is_422_after_cache_eviction_and_restore(tmp_path):
    store = VariationAuthorityStore(create_engine(f"sqlite:///{tmp_path / 'async-refusal.db'}"))
    store.install_schema()
    snapshot = {**_snapshot(), "config": {}}
    detail = {"code": "generated_svg_too_large", "limit_mib": 1, "limit_bytes": limits.SVG_MIB}
    wrapper = {"snapshot": snapshot, "context": {"result": {"svg": "<svg/>"}}, "rendered": {"svg": "<svg/>"}}
    store.create_execution("author", "execution", "variation", "1", json.dumps(wrapper).encode())
    store.record_render_refusal("author", "execution", expected_sequence="1", detail=detail)
    service = PipelineService(SimpleNamespace(), store, config_for=lambda *_: {},
                              provider_for=lambda _: lambda _: None, render_for=None,
                              max_workers=1, max_effect_steps=1, max_retained_runs=1)
    future = Future()
    future.set_exception(HTTPException(422, detail))
    service._jobs[("author", "execution")] = future
    try:
        for cached in [True, False]:
            if not cached:
                service._runs.clear()
                service._jobs.clear()
            with pytest.raises(HTTPException) as refused:
                service.get("author", "variation")
            assert refused.value.status_code == 422
            assert refused.value.detail == detail
            assert service.execution("author", "execution").view()["result"] is None
    finally:
        service.close()


def test_compact_replay_checks_before_hash_or_result_projection(monkeypatch):
    binding = SimpleNamespace(
        render_saved=lambda _: b"unused old binding",
        canvas_registry={"registry": {"formats": [{"id": "square", "width_units": 1, "height_units": 1}]}},
    )
    seen = []

    def render_saved(_payload, limit):
        seen.append(limit)
        return b'{"svg":"","metadata":{}}', "日本"

    binding.render_saved_with_svg_limit = render_saved
    effect = object.__new__(ProductPipelineEffects)
    effect.binding = binding
    effect.manifest = {"render": {"options": {"canvas": {"height": 100}}, "clip": {}}}
    effect.settings = SimpleNamespace(config_for=lambda *_: {"compiler": {
        "hard_resource_policy": {}, "operational_resource_budget": {"maximum": {}},
    }})
    monkeypatch.setattr(rendering, "_generated_svg_limit_bytes", lambda: 5)
    monkeypatch.setattr("inku_server.api_core.state._render_capacity", lambda _: nullcontext())
    monkeypatch.setattr(rendering, "_limits_for_render", lambda *_: (limits.DEFAULT_LIMITS, "settings"))
    hash_calls = []
    monkeypatch.setattr(db, "render_hash_for_item", lambda *args: hash_calls.append(args))
    with pytest.raises(HTTPException) as refused:
        effect.replay("author", {"score": {"instructions": []}}, None)
    assert refused.value.status_code == 422
    assert seen == [5]
    assert hash_calls == []


def test_missing_native_safety_capability_does_not_fall_back(monkeypatch):
    run, saved = _run(monkeypatch, "abc")
    run.binding.step_with_svg_limit = None
    with pytest.raises(HTTPException) as refused:
        run.command({"tag": "render"})
    assert refused.value.status_code == 503
    assert refused.value.detail["code"] == "svg_limit_binding_unavailable"
    assert run.transcript == []
    assert saved == []

