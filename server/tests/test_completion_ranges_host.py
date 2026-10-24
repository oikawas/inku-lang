"""A3 host transport and persistence, without native drawing or model calls."""

from __future__ import annotations

import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from inku_server import pipeline_compat
from inku_server.persistence.schema import Base, HistoryRow, PipelineHistoryLinkRow
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import AuthorDdlBody, PipelineService, pipeline_router
from inku_server.pipeline_product import _performance_idempotency

_action = runpy.run_path(str(Path(__file__).with_name("test_persistence_variation_authority.py")))["_action"]


RECORD = {"schema": "inku.completion-ranges.v1", "ranges": [{
    "words": "右下", "horizontal": ["2/3", "1"], "vertical": ["2/3", "1"],
    "sentence": "\ufffcに、橙色の小さな円。", "future_field": {"kept": True},
}]}
SOURCE = "  🌙\r\n右下（横2/3〜1、縦2/3〜1）に、橙色の小さな円。  "
CONFIG = {"saved_setting": "this performance"}
DIAGNOSTICS = {"upstream_diagnostics": [], "downstream_diagnostics": [],
               "resource_omissions": [], "relation_omissions": [],
               "render_diagnostics": None, "resource_execution": None}


@pytest.fixture
def saved_work(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'a3.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine)
    with engine.begin() as connection:
        connection.execute(HistoryRow.__table__.insert().values(
            id="work", user_id="owner", at=1, input="circle", ddl=SOURCE,
            score='{}', svg="<svg/>", elapsed_ms=0,
        ))
    store.commit_effect("owner", _action(action_digit="8", source=SOURCE,
                        expected_revision="0", next_revision="1"), create_if_missing=True)
    snapshot = {"variation_id": "variation-1", "authority": {"revision": "1"},
                "document": {"source": SOURCE}, "config": CONFIG,
                "delivery": {"source_digest": hashlib.sha256(SOURCE.encode()).hexdigest()},
                "phase": {"tag": "awaiting_llm"}, "completion_ranges": deepcopy(RECORD)}
    store.link_history("owner", "work", "variation-1", "1", snapshot["delivery"]["source_digest"],
                       snapshot=snapshot, context={"host_options": {}, "macro_catalog": {}},
                       pipeline_diagnostics=DIAGNOSTICS)
    yield store, snapshot
    engine.dispose()


def test_saved_record_is_opaque_and_old_fork_contexts_have_no_record(saved_work):
    store, snapshot = saved_work
    assert store.read_linked_history("owner", "work").completion_ranges == RECORD
    assert store.read_linked_history("other", "work") is None
    assert "completion_ranges" not in {column["name"] for column in inspect(store.engine).get_columns("pipeline_history_links")}
    with store.engine.connect() as connection:
        row = connection.execute(select(PipelineHistoryLinkRow)).mappings().one()
        payload = json.loads(bytes(row["fork_context_bytes"]))
    assert payload["protocol_version"] == "inku.pipeline-history-fork-context.v3"
    assert payload["completion_ranges"] == snapshot["completion_ranges"]
    for version in ("v3", "v2", "v1"):
        old = {**payload, "protocol_version": f"inku.pipeline-history-fork-context.{version}"}
        del old["completion_ranges"]
        if version == "v1":
            del old["pipeline_diagnostics"]
        encoded = json.dumps(old, ensure_ascii=False).encode()
        with store.engine.begin() as connection:
            connection.execute(PipelineHistoryLinkRow.__table__.update().values(
                fork_context_bytes=encoded, fork_context_digest=hashlib.sha256(encoded).hexdigest()))
        linked = store.read_linked_history("owner", "work")
        assert linked.completion_ranges is None
        assert linked.saved_config == CONFIG


def make_service(store, binding=None, prepare_for=None):
    return PipelineService(binding or SimpleNamespace(canvas_registry={"registry": {"formats": []}}), store,
                           config_for=lambda _owner, work: (work or {}).get("saved_config", CONFIG),
                           provider_for=lambda _owner: pytest.fail("no model call"), render_for=None,
                           max_workers=1, max_effect_steps=1, max_retained_runs=16, prepare_for=prepare_for)


def actor(x_owner: str = Header(...)):
    return {"id": x_owner}


def test_only_saved_and_settings_changed_starts_receive_the_record(saved_work, monkeypatch):
    store, _ = saved_work
    starts, commands = [], []
    service = make_service(store)

    class Run:
        def __init__(self, config, context):
            self.config, self.context = config, context
            self.image_data = {}
            self.record = None

        def start_new(self, authoring):
            starts.append(deepcopy(authoring))
            self.record = authoring.get("completion_ranges")
            self.shown = {"execution_id": str(len(starts)), "variation_id": "variation-1",
                          "authority": {"revision": "1"}, "document": {"source": authoring.get("source", "")},
                          "busy": False, "phase": {"tag": "score_ready"}, "result": {"svg": "<svg/>"}}

        def view(self):
            return self.shown

        def snapshot(self):
            return {"config": self.config, "completion_ranges": self.record}

        def command(self, payload, **kwargs):
            commands.append(payload)
            self.shown["document"]["source"] = payload["source"]

    monkeypatch.setattr(service, "_host", lambda _owner, config, context: Run(config, context))
    app = FastAPI()
    app.include_router(pipeline_router(service, actor))
    with TestClient(app) as client:
        response = client.post("/api/pipeline/history/work/fork", headers={"x-owner": "owner"},
                               json={"kind": "direct_ddl", "text": SOURCE})
        assert response.status_code == 200
    assert starts[-1] == {"tag": "direct_ddl", "source": SOURCE, "completion_ranges": RECORD}
    execution_id = response.json()["execution_id"]
    current_record = {**RECORD, "current_snapshot": True}
    service._runs[("owner", execution_id)].record = current_record
    service.author_ddl("owner", execution_id, AuthorDdlBody(expected_revision="1", source=SOURCE + "\n円。"))
    assert commands[-1] == {"tag": "commit_user_ddl", "expected_revision": "1", "source": SOURCE + "\n円。"}
    assert len(starts) == 1
    service.prepare_for = lambda *_: ({"different_setting": True}, {"host_options": {}})
    service.author_ddl("owner", execution_id, AuthorDdlBody(expected_revision="1", source=SOURCE))
    assert starts[-1]["completion_ranges"] == current_record
    service.prepare_for = None
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    monkeypatch.setattr(pipeline_compat, "_settled", lambda _owner, view, **_: view)
    pipeline_compat.compose("owner", {"work_id": "work", "ddl": SOURCE})
    assert starts[-1]["completion_ranges"] == RECORD
    service.start("owner", "direct_ddl", SOURCE)
    assert "completion_ranges" not in starts[-1]
    # A legacy history has no pipeline record to inherit.
    with store.engine.begin() as connection:
        connection.execute(HistoryRow.__table__.insert().values(id="legacy", user_id="owner", at=2,
                           input="circle", ddl=SOURCE, score='{}', svg="<svg/>", elapsed_ms=0))
    pipeline_compat.compose("owner", {"work_id": "legacy", "ddl": SOURCE})
    assert "completion_ranges" not in starts[-1]
    service.close()


def test_authenticated_states_use_saved_or_run_inputs_and_pass_core_response_through(saved_work, monkeypatch):
    store, snapshot = saved_work
    requests = []
    answer = {"schema": "inku.completion-range-states.v1", "ranges": [
        {"utf16_start": 7, "utf16_end": 27, "state": "words_changed", "future_field": "kept"}]}

    def states(encoded):
        requests.append(json.loads(encoded))
        return json.dumps(answer).encode()

    binding = SimpleNamespace(completion_range_states=states)
    service = make_service(store, binding)
    monkeypatch.setattr(service, "execution", lambda *_: pytest.fail("state lookup must not resume"))
    store.create_execution("owner", "run", "variation-1", "0", json.dumps({"snapshot": snapshot, "context": {}, "rendered": None}).encode())
    service._runs[("owner", "active")] = SimpleNamespace(snapshot=lambda: snapshot, view=lambda: {"busy": False}, image_data={})
    app = FastAPI()
    app.include_router(pipeline_router(service, actor))
    edited = "  🌙\r\n月のそば（横2/3〜1、縦2/3〜1）に、円。  "
    empty = {"schema": "inku.completion-range-states.v1", "ranges": []}
    with TestClient(app) as client:
        for work in ({"history_id": "work"}, {"execution_id": "run"}, {"execution_id": "active"}):
            body = {**work, "source": edited}
            assert client.post("/api/pipeline/completion-range-states", json=body).status_code == 422
            response = client.post("/api/pipeline/completion-range-states", headers={"x-owner": "owner"}, json=body)
            assert response.status_code == 200
            assert response.json() == answer
            assert requests[-1] == {"config": CONFIG, "source": edited, "completion_ranges": RECORD}
            assert client.post("/api/pipeline/completion-range-states", headers={"x-owner": "other"}, json=body).status_code == 404
        del binding.completion_range_states
        assert client.post("/api/pipeline/completion-range-states", headers={"x-owner": "owner"},
                           json={"history_id": "work", "source": edited}).json() == empty
        binding.completion_range_states = states
        snapshot.pop("completion_ranges")
        before = len(requests)
        assert client.post("/api/pipeline/completion-range-states", headers={"x-owner": "owner"},
                           json={"execution_id": "active", "source": edited}).json() == empty
        assert len(requests) == before
        assert client.post("/api/pipeline/completion-range-states", headers={"x-owner": "owner"},
                           json={"history_id": "work", "execution_id": "active", "source": edited}).status_code == 422
    service.close()


def test_same_svg_with_updated_record_is_saved_as_a_distinct_performance():
    projected = []
    updated = {**RECORD, "updated_words": True}

    class Binding:
        @staticmethod
        def step(previous_bytes, input_bytes):
            request = json.loads(input_bytes)
            if not previous_bytes:
                snapshot = {"execution_id": "same-numbers", "variation_id": "variation-1", "sequence": "0",
                            "authority": {"revision": "1"}, "document": {"source": SOURCE}, "config": request["payload"]["config"],
                            "completion_ranges": RECORD, "delivery": {"score": {}}, "phase": {"tag": "awaiting_llm"},
                            "action": {"tag": "complete_visible_ddl_holes", "delay_ms": "0", "identity": {}}}
                rendered = {"svg": "<svg/>"}
            else:
                snapshot = json.loads(previous_bytes)
                snapshot["sequence"] = request["sequence"]
                if request["payload"]["tag"] == "effect_result":
                    snapshot.update(completion_ranges=updated, action=None, phase={"tag": "score_ready"})
                rendered = None
            return json.dumps({"kind": "output", "payload": {"result": {
                "snapshot": snapshot, "rendered": rendered, "events": [],
            }}}).encode()

    store = SimpleNamespace(create_execution=lambda *_: None, compare_and_set_execution=lambda *_, **__: None)
    service = make_service(store, Binding())

    def project(_owner, snapshot, _context, rendered):
        projected.append((deepcopy(snapshot), rendered))
        return {"saved": len(projected)}

    service.project_result = project
    service.provider_for = lambda _owner: lambda _action: {"tag": "fixture_result"}
    config = {"envelope_limits": {"max_snapshot_bytes": 100000, "max_input_bytes": 100000, "max_output_bytes": 100000}}
    run = service._host("owner", config, {})
    run.start_new({"tag": "direct_ddl", "source": SOURCE})
    run.run_effect()
    assert len(projected) == 2
    before, after = (row[0] for row in projected)
    assert before["completion_ranges"] == RECORD
    assert after["completion_ranges"] == updated
    assert before["document"] == after["document"]
    assert projected[0][1] == projected[1][1]
    for settings in ({}, {"request_idempotency_key": "one-request"}):
        assert _performance_idempotency(settings, before, "same-render") != _performance_idempotency(settings, after, "same-render")
    run.command({"tag": "cancel"})
    assert len(projected) == 2, "an unchanged record still reuses its saved work"
    no_record = {key: value for key, value in after.items() if key != "completion_ranges"}
    assert _performance_idempotency({"request_idempotency_key": "old-key"}, no_record, "same-render") == "old-key"
    service.close()
