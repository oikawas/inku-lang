"""Compatibility projections through the shared pipeline."""

from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import pipeline_compat
from inku_server.api_core.routers.render import ComposeResponse
from inku_server.persistence.schema import Base


def test_compose_projects_opaque_score_and_never_approves_a_hole(monkeypatch) -> None:
    commands: list[dict] = []

    class Service:
        def __init__(self):
            self.view: dict = {}

        def start(self, owner, kind, text, **kwargs):
            assert owner == "author-1"
            assert kind == "direct_ddl"
            assert kwargs["options"]["save_history"] is False
            assert kwargs["options"]["count_generation"] is False
            patch = "many circle" in text
            self.view = {
                "execution_id": "execution-1",
                "variation_id": "variation-1",
                "authority": {"revision": "1"},
                "document": {"source": text, "language": "en"},
                "delivery": None if patch else {"score": {"schema": "inku.score.v0.10"}},
                "phase": {
                    "tag": "awaiting_patch_approval" if patch else "score_ready",
                    "proposal_digest": "proposal-1" if patch else None,
                },
                "busy": False,
                "result": None,
            }
            return self.view

        def get(self, owner, variation_id):
            return self.view

        def command(self, owner, execution_id, command):
            commands.append(command)
            assert command == {"tag": "perform"}
            self.view["result"] = {
                "ddl": self.view["document"]["source"],
                "score": {
                    "schema": "inku.score.v0.10",
                    "future_field": {"kept": True},
                },
                "svg": "<svg/>",
                "compiler_outcome": "complete_with_omissions",
                "pipeline_diagnostics": {
                    "upstream_diagnostics": [{"issue_id": "issue-1"}],
                    "downstream_diagnostics": [],
                    "resource_omissions": [],
                    "relation_omissions": [],
                    "render_diagnostics": {"diagnostics": []},
                    "resource_execution": {"omitted_units": []},
                },
            }
            return self.view

    service = Service()
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)

    result = pipeline_compat.compose(
        "author-1",
        {"ddl": "one circle", "description": "circle", "model": "stage2"},
    )
    projected = ComposeResponse.model_validate(result).model_dump()
    assert projected["score"]["future_field"] == {"kept": True}
    assert projected["compiler_outcome"] == "complete_with_omissions"
    assert projected["pipeline_diagnostics"] == service.view["result"][
        "pipeline_diagnostics"
    ]
    assert projected["pipeline_variation_id"] == "variation-1"
    assert commands == [{"tag": "perform"}]

    with pytest.raises(HTTPException) as raised:
        pipeline_compat.compose(
            "author-1",
            {"ddl": "many circle", "description": "circles"},
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["current_view"]["phase"]["tag"] == (
        "awaiting_patch_approval"
    )
    assert raised.value.detail["pipeline_execution_id"] == "execution-1"
    assert commands == [{"tag": "perform"}]


def test_paint_409_exposes_persisted_compiler_failure_detail(
    tmp_path, monkeypatch
) -> None:
    from inku_server import db, pipeline_product
    from inku_server.persistence.variation_authority import VariationAuthorityStore
    from inku_server.pipeline_api import PipelineService
    from inku_server.pipeline_candidate import PipelineBinding
    from inku_server.pipeline_defaults import default_manifest
    from inku_server.pipeline_product import ProductPipelineEffects

    binding = PipelineBinding()
    manifest = default_manifest(binding)
    config = deepcopy(manifest["pipeline"])
    config["stage1_retry"]["max_attempts"] = 1
    engine = create_engine(f"sqlite:///{tmp_path / 'provider-failure.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine)
    effects = ProductPipelineEffects(binding, manifest)

    class RejectedProvider:
        def __init__(self, _options, **_kwargs):
            pass

        def __call__(self, action):
            return {
                "tag": "normalized_ddl_generated",
                "identity": action["identity"],
                "response": json.dumps({"normalized_ddl": "Unknown.Macro."}),
                "elapsed_ms": "7",
            }

    def prepare(_owner, _kind, _text, _options, _source):
        return deepcopy(config), {
            "host_options": {
                "stage1_model": "fixture:stage1",
                "stage2_model": "fixture:stage2",
            },
            "metrics": {},
        }

    monkeypatch.setattr(db, "get_model_settings", lambda: {})
    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", RejectedProvider)
    service = PipelineService(
        binding,
        store,
        config_for=lambda _owner, _source: deepcopy(config),
        provider_for=lambda _owner: pytest.fail("context-free provider used"),
        render_for=None,
        prepare_for=prepare,
        provider_with_context=effects.provider_for,
        max_workers=1,
        max_effect_steps=4,
        max_retained_runs=1,
    )
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)

    try:
        with pytest.raises(HTTPException) as raised:
            pipeline_compat.paint(
                "author",
                {"description": "One quiet black circle", "save_history": False},
                None,
            )
        detail = raised.value.detail
        diagnostic = {
            "failure": "semantic_violation",
            "stage": "stage1",
            "attempt": 1,
            "elapsed_ms": 7,
            "detail": "macro_resolution_missing_lock",
        }
        assert raised.value.status_code == 409
        assert detail["current_view"]["provider_failure"] == diagnostic
        record = store.read_execution(
            "author", execution_id=detail["pipeline_execution_id"]
        )
        persisted = json.loads(record.state_bytes)
        assert persisted["context"]["provider_failure"] == diagnostic
    finally:
        service.close()
        engine.dispose()


def test_description_pipeline_forces_typed_stage1_transport_and_renders_svg(
    tmp_path, monkeypatch
) -> None:
    from inku_server import db, pipeline_product, pipeline_provider, pipeline_runtime

    description = "山の向こうに月が昇る"
    normalized_ddl = "中心に赤い鉛筆の細い線をひとつ置く。"
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        arguments = json.dumps(
            {"normalized_ddl": normalized_ddl},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "submit_pipeline_response",
                                        "arguments": arguments,
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    engine = create_engine(f"sqlite:///{tmp_path / 'description-pipeline.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(
        pipeline_provider,
        "provider_for_model",
        lambda *args, **kwargs: ("fixture", "fixture-model"),
    )
    monkeypatch.setattr(
        pipeline_provider,
        "connection_for",
        lambda *args: {
            "id": "fixture",
            "kind": "openai_compatible",
            "base_url": "https://provider.invalid/v1",
            "api_key": "test-only",
            "requires_api_key": True,
        },
    )
    provider_class = pipeline_provider.SingleAttemptProvider
    monkeypatch.setattr(
        pipeline_product,
        "SingleAttemptProvider",
        lambda options, **kwargs: provider_class(
            options,
            transport=httpx.MockTransport(respond),
            **kwargs,
        ),
    )

    pipeline_runtime.shutdown()
    try:
        result = pipeline_compat.paint(
            "author-1",
            {
                "description": description,
                "stage1_model": "fixture-model",
                "stage2_model": "fixture-model",
                "instruction_lang": "ja",
                "ui_lang": "ja",
                "catalog_id": "default",
                "catalog_mode": "fixed",
                "canvas_aspect": "square",
                "render_seed": 77,
                "composition_seed": 17,
                "save_history": False,
                "count_generation": False,
            },
            None,
        )
        view = pipeline_runtime.get_service().get(
            "author-1", result["pipeline_variation_id"]
        )
    finally:
        pipeline_runtime.shutdown()
        engine.dispose()

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://provider.invalid/v1/chat/completions"
    body = json.loads(request.content)
    assert json.loads(body["messages"][1]["content"])["description"] == description
    assert body["temperature"] == 0.3
    function = body["tools"][0]["function"]
    assert function["name"] == "submit_pipeline_response"
    # Stage 1 asks for a typed work plan; the plan is printed as the visible DDL.
    assert function["parameters"]["required"] == ["background", "ground", "layers"]
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_pipeline_response"},
    }
    assert result["description"] == description
    assert result["source_ddl"] == normalized_ddl
    assert result["score"]["instructions"]
    assert result["svg"].startswith("<svg ")
    assert 'xmlns="http://www.w3.org/2000/svg"' in result["svg"]
    assert view["phase"]["tag"] == "completed"
    assert view["busy"] is False
    assert view["result"]["svg"] == result["svg"]


def test_a_supplementing_sketch_reaches_stage1_and_is_saved(tmp_path, monkeypatch) -> None:
    from inku_server import db, pipeline_product, pipeline_provider, pipeline_runtime

    description = "鶴が一羽立つ"
    supplement = "広い湿原。冬の淡い空。"
    normalized_ddl = "中心に赤い鉛筆の細い線をひとつ置く。"
    requests: list[dict] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        parameters = body["tools"][0]["function"]["parameters"]
        answer = (
            {"sketch": supplement}
            if list(parameters["properties"]) == ["sketch"]
            else {"normalized_ddl": normalized_ddl}
        )
        arguments = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"type": "function", "function": {"name": "submit_pipeline_response", "arguments": arguments}}
        ]}}]})

    engine = create_engine(f"sqlite:///{tmp_path / 'sketch-pipeline.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(pipeline_provider, "provider_for_model", lambda *args, **kwargs: ("fixture", "fixture-model"))
    monkeypatch.setattr(pipeline_provider, "connection_for", lambda *args: {
        "id": "fixture", "kind": "openai_compatible", "base_url": "https://provider.invalid/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    provider_class = pipeline_provider.SingleAttemptProvider
    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider",
                        lambda options, **kwargs: provider_class(options, transport=httpx.MockTransport(respond)))

    pipeline_runtime.shutdown()
    try:
        result = pipeline_compat.paint("author-1", {
            "description": description, "sketch": True,
            "stage1_model": "fixture-model", "stage2_model": "fixture-model",
            "instruction_lang": "ja", "ui_lang": "ja", "catalog_id": "default", "catalog_mode": "fixed",
            "canvas_aspect": "square", "render_seed": 77, "composition_seed": 17,
            "save_history": False, "count_generation": False,
        }, None)
    finally:
        pipeline_runtime.shutdown()
        engine.dispose()

    assert len(requests) == 2
    assert json.loads(requests[0]["messages"][1]["content"]) == {"description": description}
    stage1 = json.loads(requests[1]["messages"][1]["content"])
    assert stage1["description"] == description
    assert stage1["sketch"] == supplement
    assert result["description"] == description
    assert result["sketch_text"] == supplement
    assert result["sketch_state"] == "supplemented"
