"""A work keeps the tokens its sends used (SPEC §12.5): each send's usage, read
alike for every provider by the shared core, is added under the stage it is
timed under and saved with the work, as a total and by stage."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence.schema import Base, UserAccountRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService, pipeline_router, register_pipeline_errors
from inku_server.pipeline_candidate import PipelineBinding
from inku_server.pipeline_defaults import default_manifest
from inku_server.pipeline_product import ProductPipelineEffects, usage_result
from inku_server.pipeline_provider import ProviderOptions, SingleAttemptProvider


def _action() -> dict:
    return {
        "tag": "generate_normalized_ddl",
        "identity": {"action_id": "a", "attempt": 1, "request_digest": "b"},
        "timeout_ms": "1000",
        "payload": {"prompt": {
            "system": "s", "message": "m", "action_name": "generate_normalized_ddl",
            "response_schema": {"type": "object", "properties": {"normalized_ddl": {"type": "string"}}},
        }},
    }


def test_a_send_keeps_its_usage_even_when_its_answer_was_cut(monkeypatch):
    monkeypatch.setattr("inku_server.pipeline_provider.provider_for_model", lambda *args, **kwargs: ("openai", "gpt-4.1"))
    monkeypatch.setattr("inku_server.pipeline_provider.connection_for", lambda *args: {
        "id": "openai", "kind": "openai_compatible", "base_url": "https://api.openai.com/v1",
        "api_key": "test-only", "requires_api_key": True,
    })
    answers = [
        httpx.Response(200, json={"status": "completed", "output": [
            {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "submit_pipeline_response",
             "arguments": '{"normalized_ddl":"x"}', "status": "completed"},
        ], "usage": {"input_tokens": 120, "output_tokens": 30, "input_tokens_details": {"cached_tokens": 100}}}),
        httpx.Response(200, json={"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                                  "output": [], "usage": {"input_tokens": 12, "output_tokens": 256}}),
        httpx.Response(500, json={"error": "fixture"}),
    ]

    async def request(_):
        return answers.pop(0)

    provider = SingleAttemptProvider(ProviderOptions({}, "m", "m", 256, 8192), transport=httpx.MockTransport(request))
    assert provider(_action())["tag"] == "normalized_ddl_generated"
    assert provider.usage == {"input_tokens": 120, "output_tokens": 30, "cached_input_tokens": 100}
    assert provider(_action())["failure"] == "malformed_payload"
    assert provider.usage == {"input_tokens": 12, "output_tokens": 256, "cached_input_tokens": None}
    assert provider(_action())["failure"] == "transport_unavailable"
    assert provider.usage is None


def test_hole_completion_is_stage_2_and_every_other_send_stage_1():
    def entry(sends, tokens_in, tokens_out, unreported=0):
        return {"sends": sends, "unreported_sends": unreported, "input_tokens": tokens_in,
                "output_tokens": tokens_out, "cached_input_tokens": None}
    record = {"stage1": entry(2, 1000, 200), "laws": entry(1, 300, 40), "stage2": entry(1, 50, 5)}
    result = usage_result(record)
    assert (result["tokens_in"], result["tokens_out"]) == (1350, 245)
    assert (result["tokens_in_stage1"], result["tokens_out_stage1"]) == (1300, 240)
    assert (result["tokens_in_stage2"], result["tokens_out_stage2"]) == (50, 5)
    assert result["provider_usage"] == record
    # A work that sent nothing used nothing; one whose sends reported nothing is unknown.
    nothing = usage_result({})
    assert (nothing["tokens_in"], nothing["tokens_out"], nothing["provider_usage"]) == (0, 0, None)
    assert usage_result({"stage1": entry(1, None, None, unreported=1)})["tokens_in"] is None


POEM = "紫のにほへる妹を憎くあらば人妻ゆゑに我恋ひめやも"
DDL = "背景を黄で埋める。\n画面の横0.3、縦0.7の位置に、直径0.1の赤の塗りの円を1個置く。"
ANSWERS = {
    "write_description_ddl": ("description_ddl_written", {"ddl": DDL, "figures": []}),
    "review_description_ddl": ("description_ddl_reviewed", {"ddl": DDL, "figures": []}),
}
USAGE = {
    "write_description_ddl": {"input_tokens": 4000, "output_tokens": 900, "cached_input_tokens": 3000},
    "review_description_ddl": None,
}


@pytest.fixture
def host(tmp_path, monkeypatch):
    from inku_server import model_settings, pipeline_product
    from inku_server.api_core import common, rendering, thumbnails
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'tokens.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _: None)

    def offered(provider, model, settings, *, purpose):
        return provider == "openai" and model == "fixture-vision"

    monkeypatch.setattr(model_settings, "model_is_offered", offered)
    monkeypatch.setattr(common, "model_is_offered", offered)
    with engine.begin() as connection:
        connection.execute(UserAccountRow.__table__.insert().values(
            id="owner", username="owner", email="owner@example.test", password_hash="unused", role="user", at=1,
        ))

    class Transport:
        """The send stands in for the provider; the host adds what it reports."""

        def __init__(self, options, **kwargs):
            self.usage = None

        def __call__(self, action):
            tag, response = ANSWERS[action["tag"]]
            self.usage = USAGE[action["tag"]]
            return {"tag": tag, "identity": action["identity"], "response": json.dumps(response, ensure_ascii=False),
                    "elapsed_ms": "1"}

    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", Transport)
    effects = ProductPipelineEffects(binding, default_manifest(binding))
    service = PipelineService(
        binding, VariationAuthorityStore(engine), config_for=effects.settings.config_for,
        prepare_for=effects.prepare, provider_for=lambda _: pytest.fail("provider without context"),
        provider_with_context=effects.provider_for, image_provider_with_context=effects.provider_for,
        image_review_options=effects.image_review_options,
        render_for=None, render_with_context=effects.render_options, project_result=effects.save_result,
        max_workers=1, max_effect_steps=32, max_retained_runs=4,
    )
    app = FastAPI()

    def actor(x_owner: str = Header(...)):
        return {"id": x_owner}

    app.include_router(pipeline_router(service, actor))
    register_pipeline_errors(app)
    with TestClient(app) as client:
        yield client, service
    service.close()
    engine.dispose()


def _wait(service, execution_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        view = service.execution("owner", execution_id).view()
        if not view["busy"]:
            return view
        time.sleep(0.01)
    pytest.fail("the run did not finish")


def test_a_saved_work_keeps_its_total_and_its_stages(host):
    client, service = host
    started = client.post("/api/pipeline/variations", headers={"x-owner": "owner"}, json={
        "kind": "description", "text": POEM,
        "options": {"stage1_model": "openai:fixture-vision", "route": "read_and_draw", "save_artifacts": False}})
    assert started.status_code == 200, started.text
    view = _wait(service, started.json()["execution_id"])
    assert view["phase"]["tag"] == "score_ready", view
    done = service.command("owner", view["execution_id"], {"tag": "perform"})
    assert (done["result"]["tokens_in_stage1"], done["result"]["tokens_out_stage1"]) == (4000, 900)
    item = db.get_items("owner", [done["result"]["history_id"]])[0]
    assert (item["tokens_in"], item["tokens_out"]) == (4000, 900)
    assert item["provider_usage"] == {"read_and_draw": {
        "sends": 2, "unreported_sends": 1, "input_tokens": 4000, "output_tokens": 900, "cached_input_tokens": 3000}}
