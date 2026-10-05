"""The compose host chooses numeric ranges before its existing direct-DDL run."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from inku_server import pipeline_compat
from inku_server.api_core.routers.render import ComposeRequest, ComposeResponse


SOURCE = "白い地に右下（横2/3〜1、縦2/3〜1）の赤い円を置く。\n作者の追記。"
RECOMPOSED = "白い地に左上（横0〜1/3、縦0〜1/3）の赤い円を置く。\n作者の追記。"
MOVE = {
    "layer": 0, "from_key": "cell-22", "from": "右下（横2/3〜1、縦2/3〜1）",
    "to_key": "cell-00", "to": "左上（横0〜1/3、縦0〜1/3）",
}


class ComposeService:
    def __init__(self, native):
        self.binding = SimpleNamespace(recompose=native)
        self.config = {
            "language": "ja", "compiler": {"composition_seed": "17"},
            "definitions": [{"qualified_name": "fixture.Macro", "source": "kept"}],
        }
        self.preparations = []
        self.starts = []
        self.prepared = None

    def prepare_for(self, owner, kind, source, options, source_work):
        self.preparations.append((owner, kind, source, deepcopy(options), source_work))
        self.prepared = self.config, {"host_options": {"render_seed": "19"}}
        return self.prepared

    def start(self, owner, kind, source, **kwargs):
        self.starts.append((owner, kind, source, kwargs))
        assert kwargs["options"]["save_history"] is False
        assert kwargs["options"]["count_generation"] is False
        if kwargs.get("prepared") is None:
            self.prepare_for(owner, kind, source, kwargs["options"], kwargs["source_work"])
        else:
            assert kwargs["prepared"] is self.prepared
        return {
            "execution_id": "execution", "variation_id": "work", "authority": {"revision": "1"},
            "delivery": {"score": {}}, "busy": False,
            "result": {"ddl": source, "score": {"future_field": {"kept": True}}, "svg": "fixture"},
        }


def test_compose_rechooses_ranges_with_the_exact_prepared_configuration(monkeypatch):
    native_requests = []

    def native(request):
        native_requests.append(json.loads(request))
        return json.dumps({
            "schema": "inku.composition-recompose.v1", "outcome": "recomposed",
            "source": RECOMPOSED, "moves": [MOVE], "answer": "chance",
        }, ensure_ascii=False).encode()

    service = ComposeService(native)
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    data = {
        "ddl": SOURCE, "description": "saved prose", "composition_seed": 17,
        "recompose_mode": "chance", "imported_plugins": [{"definition": "kept"}],
    }
    original = deepcopy(data)
    result = pipeline_compat.compose("author", data)
    assert result["ddl"] == RECOMPOSED
    assert len(native_requests) == len(service.preparations) == len(service.starts) == 1
    request = native_requests[0]
    assert request == {
        "config": service.config, "source": SOURCE, "mode": "chance", "seed": "17",
        "work_id": "sha256:" + hashlib.sha256(SOURCE.encode()).hexdigest(),
    }
    assert service.preparations[0][:3] == ("author", "direct_ddl", SOURCE)
    assert service.preparations[0][3]["imported_plugins"] == data["imported_plugins"]
    assert "recompose_mode" not in service.preparations[0][3]
    assert service.starts[0][2] == RECOMPOSED
    assert data == original
    projected = ComposeResponse.model_validate(result).model_dump(mode="json", by_alias=True)
    assert projected["recomposition"] == {
        "mode": "chance", "outcome": "recomposed", "moves": [MOVE], "answer": "chance", "reason": None,
    }
    assert projected["score"]["future_field"] == {"kept": True}
    assert projected["pipeline_variation_id"] == "work"
    assert ComposeRequest.model_validate(data).recompose_mode == "chance"
    with pytest.raises(ValidationError):
        ComposeRequest.model_validate({**data, "recompose_mode": "unknown"})


def test_a_range_without_a_catalog_key_survives_the_http_projection(monkeypatch):
    move = {**MOVE, "from_key": None}
    service = ComposeService(lambda _request: json.dumps({
        "schema": "inku.composition-recompose.v1", "outcome": "recomposed",
        "source": RECOMPOSED, "moves": [move], "answer": "near",
    }).encode())
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    result = pipeline_compat.compose("author", {"ddl": SOURCE, "recompose_mode": "principled"})
    projected = ComposeResponse.model_validate(result).model_dump(mode="json", by_alias=True, exclude_none=True)
    assert projected["ddl"] == RECOMPOSED
    assert projected["recomposition"]["moves"][0]["from"] == move["from"]
    assert projected["recomposition"]["moves"][0].get("from_key") is None


def test_unchanged_errors_and_older_bindings_keep_the_saved_ddl(monkeypatch):
    replies = [
        ({"schema": "inku.composition-recompose.v1", "outcome": "unchanged", "reason": "nothing_to_move"}, "nothing_to_move"),
        ({"schema": "inku.composition-recompose.v1", "outcome": "unchanged", "reason": "unsolved"}, "unsolved"),
        ({"error": "internal_invariant"}, "internal_invariant"),
        (b"not JSON", "invalid_response"),
    ]
    source = "白い地に赤い円を置く。\n作者の追記。"
    stable_work_ids = []
    for reply, reason in replies:
        def native(request, reply=reply):
            stable_work_ids.append(json.loads(request)["work_id"])
            return reply if isinstance(reply, bytes) else json.dumps(reply).encode()

        service = ComposeService(native)
        monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
        result = pipeline_compat.compose("author", {"ddl": source, "recompose_mode": "principled", "composition_seed": 17})
        assert result["ddl"] == service.starts[0][2] == source
        assert result["recomposition"] == {"mode": "principled", "outcome": "unchanged", "reason": reason, "moves": []}
        assert len(service.preparations) == 1
    assert len(set(stable_work_ids)) == 1

    def failed_native(_request):
        raise RuntimeError("fixture")

    service = ComposeService(failed_native)
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    failed = pipeline_compat.compose("author", {"ddl": source, "recompose_mode": "principled"})
    assert failed["ddl"] == source and failed["recomposition"]["reason"] == "recompose_failed"

    from inku_server import pipeline_candidate
    module = SimpleNamespace(
        pipeline_version_report=lambda: b'{"binding_version":"1.1.0","protocol_version":"1.0.0"}',
        pipeline_canvas_registry=lambda: b"{}", pipeline_step=None, pipeline_resolve_palette=None,
        pipeline_render_saved=None, pipeline_resolve_macro_catalog=None,
    )
    monkeypatch.setattr(pipeline_candidate, "importlib", SimpleNamespace(import_module=lambda _name: module))
    service = ComposeService(None)
    service.binding = pipeline_candidate.PipelineBinding()
    assert service.binding.recompose is None
    assert service.binding.composition_ranges is None
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    old = pipeline_compat.compose("author", {"ddl": source, "recompose_mode": "principled"})
    assert old["ddl"] == source and old["recomposition"]["reason"] == "binding_unavailable"
    assert len(service.preparations) == 1

    service = ComposeService(lambda _request: pytest.fail("legacy compose called recompose"))
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    legacy = pipeline_compat.compose("author", {"ddl": source})
    assert legacy["ddl"] == source and "recomposition" not in legacy
    assert len(service.preparations) == 1


class SavedWorks:
    """The two saved works a recomposition can name: one the shared pipeline
    drew (its config and context kept with it), and one drawn before that."""

    def __init__(self):
        from inku_server.persistence.variation_authority import (
            LegacyHistoryRecord, LinkedHistoryForkRecord,
        )

        def history(history_id, metadata):
            return LegacyHistoryRecord(
                history_id=history_id, description="saved prose", source=SOURCE, score_json="{}",
                svg="<svg/>", authority="ddl_authoritative", metadata=metadata,
            )

        self.linked = LinkedHistoryForkRecord(
            history=history("linked", {"lineage_node_id": "node-linked"}),
            variation_id="parent-variation", revision="3", ddl_digest="digest",
            saved_config={"language": "ja", "compiler": {"composition_seed": None}, "definitions": ["saved"]},
            host_options={"render_seed": "23", "catalog_id": "saved-catalog"},
            macro_catalog={"definition_locks": ["saved-lock"]}, pipeline_diagnostics=None,
        )
        self.legacy = history("legacy", {"lineage_node_id": "node-legacy", "render_seed": 29})

    def read_linked_history(self, owner, history_id):
        assert owner == "author"
        return self.linked if history_id == "linked" else None

    def read_legacy_history(self, owner, history_id):
        assert owner == "author"
        return {"linked": self.linked.history, "legacy": self.legacy}.get(history_id)


def test_a_recomposition_of_a_saved_work_forks_from_it(monkeypatch):
    """SPEC §12.7.1: the saved performance's config, seeds, catalog and limits
    are authoritative, and the new direct-DDL variation keeps a parent."""
    service = ComposeService(lambda _request: json.dumps({
        "schema": "inku.composition-recompose.v1", "outcome": "unchanged", "reason": "nothing_to_move",
    }).encode())
    service.store = SavedWorks()
    monkeypatch.setattr(pipeline_compat, "_service", lambda: service)
    data = {"ddl": SOURCE, "description": "saved prose", "recompose_mode": "principled", "work_id": "linked"}
    assert ComposeRequest.model_validate(data).model_dump(mode="json")["work_id"] == "linked"

    pipeline_compat.compose("author", data)
    source_work = service.preparations[0][4]
    assert source_work["saved_config"] == service.store.linked.saved_config
    assert source_work["host_options"] == {"render_seed": "23", "catalog_id": "saved-catalog"}
    assert source_work["macro_catalog"] == {"definition_locks": ["saved-lock"]}
    assert source_work["result"] == {"lineage_node_id": "node-linked"}
    assert service.starts[0][3]["parent"] == {"kind": "variation", "id": "parent-variation"}
    assert service.starts[0][3]["source_work"] is source_work

    service.preparations.clear()
    service.starts.clear()
    pipeline_compat.compose("author", {**data, "work_id": "legacy"})
    assert service.preparations[0][4]["metadata"]["render_seed"] == 29
    assert service.starts[0][3]["parent"] == {"kind": "legacy_history", "id": "legacy"}

    with pytest.raises(HTTPException) as missing:
        pipeline_compat.compose("author", {**data, "work_id": "someone-else"})
    assert missing.value.status_code == 404
