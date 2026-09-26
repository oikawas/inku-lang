"""Actual core compilation to normal history projection, without SVG execution."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from inku_server.persistence.schema import (
    Base,
    HistoryRow,
    PipelineHistoryLinkRow,
    UserAccountRow,
)
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import CandidateExecution, CandidateHostError, PipelineBinding
from inku_server.pipeline_defaults import ADDITIONAL_RESOURCE_LIMITS, default_manifest
from inku_server.pipeline_product import ProductPipelineEffects, RunOptions, _apply_developer_options


def test_stage1_default_budget_is_separate_from_legacy_request_timeout(
    monkeypatch,
):
    monkeypatch.setenv("INKU_LLM_REQUEST_TIMEOUT_SECONDS", "17")
    monkeypatch.delenv("INKU_LLM_STAGE1_ATTEMPT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("INKU_LLM_STAGE1_TOTAL_TIMEOUT_SECONDS", raising=False)
    manifest = default_manifest(PipelineBinding())

    assert manifest["pipeline"]["catalog_retry"] == {
        "max_attempts": 4,
        "attempt_timeout_ms": "17000",
        "total_timeout_ms": "17000",
        "retry_delay_ms": "2000",
    }
    assert manifest["pipeline"]["hole_retry"] == manifest["pipeline"][
        "catalog_retry"
    ]
    assert manifest["pipeline"]["stage1_retry"] == {
        "max_attempts": 4,
        "attempt_timeout_ms": "300000",
        "total_timeout_ms": "540000",
        "retry_delay_ms": "2000",
    }


def test_developer_retry_opt_in_does_not_change_the_normal_default():
    config = {
        name: {"max_attempts": 4}
        for name in ("catalog_retry", "stage1_retry", "hole_retry")
    }
    _apply_developer_options(config, {"developer_disable_llm_retries": True}, developer_mode=True)
    assert [config[name]["max_attempts"] for name in (
        "catalog_retry", "stage1_retry", "hole_retry",
    )] == [1, 1, 1]
    normal = {
        name: {"max_attempts": 4}
        for name in ("catalog_retry", "stage1_retry", "hole_retry")
    }
    _apply_developer_options(normal, {}, developer_mode=False)
    assert [normal[name]["max_attempts"] for name in normal] == [4, 4, 4]
    with pytest.raises(CandidateHostError, match="developer_mode_required"):
        _apply_developer_options(normal, {"developer_capture_provider_io": True}, developer_mode=False)
    with pytest.raises(ValidationError):
        RunOptions.model_validate({"developer_disable_llm_retries": "true"})


def test_stage1_timeout_retries_inside_total_budget_then_stops(
    tmp_path, monkeypatch
):
    binding = PipelineBinding()
    config = default_manifest(binding)["pipeline"]
    engine = create_engine(f"sqlite:///{tmp_path / 'stage1-budget.db'}")
    store = VariationAuthorityStore(engine)
    calls: list[tuple[int, int]] = []

    def provider(action):
        calls.append(
            (
                int(action["identity"]["attempt"]),
                int(action["timeout_ms"]),
            )
        )
        return {
            "tag": "provider_failed",
            "identity": action["identity"],
            "failure": "transport_timeout",
            "elapsed_ms": action["timeout_ms"],
        }

    monkeypatch.setattr("inku_server.pipeline_candidate.time.sleep", lambda _delay: None)
    run = CandidateExecution(
        binding,
        store,
        owner_id="author",
        config=config,
        provider=provider,
    )
    run.start_new(
        {
            "tag": "description",
            "description": "One quiet black circle",
            "auto_catalog": False,
        }
    )

    run.run_effect()
    retry = run.snapshot()["action"]
    assert retry["identity"]["attempt"] == 2
    assert retry["timeout_ms"] == "238000"
    run.run_effect()

    assert calls == [(1, 300000), (2, 238000)]
    assert run.view()["phase"] == {"tag": "failed", "reason": "stage1_failed"}
    assert run.view()["busy"] is False
    engine.dispose()


def test_provider_failure_diagnostic_is_cleared_by_success(monkeypatch):
    from inku_server import db, pipeline_product

    binding = PipelineBinding()
    effects = ProductPipelineEffects(binding, default_manifest(binding))
    context = {
        "host_options": {
            "stage1_model": "fixture:stage1",
            "stage2_model": "fixture:stage2",
        },
        "metrics": {},
    }
    results = [
        {
            "tag": "provider_failed",
            "failure": "provider_rejected",
            "elapsed_ms": "300000",
        },
        {
            "tag": "normalized_ddl_generated",
            "response": json.dumps({"normalized_ddl": "one black circle"}),
            "elapsed_ms": "11",
        },
    ]

    class FixtureProvider:
        def __init__(self, _options, **_kwargs):
            self.failure_detail = None

        def __call__(self, action):
            result = results.pop(0)
            if result["tag"] == "provider_failed":
                self.failure_detail = "credentials_unavailable"
            return {**result, "identity": action["identity"]}

    monkeypatch.setattr(db, "get_model_settings", lambda: {})
    monkeypatch.setattr(pipeline_product, "SingleAttemptProvider", FixtureProvider)
    perform = effects.provider_for("author", context)
    action = {
        "tag": "generate_normalized_ddl",
        "identity": {
            "action_id": "action-1",
            "attempt": 1,
            "request_digest": "request-1",
        },
    }

    perform(action)
    assert context["provider_failure"] == {
        "failure": "provider_rejected",
        "stage": "stage1",
        "attempt": 1,
        "elapsed_ms": 300000,
        "detail": "credentials_unavailable",
    }
    perform(
        {
            **action,
            "identity": {
                **action["identity"],
                "action_id": "action-2",
                "attempt": 2,
            },
        }
    )
    assert "provider_failure" not in context
    assert context["metrics"] == {"stage1": 300011}


def test_bundled_macro_enters_new_work_with_localized_summary_and_saved_lock(tmp_path, monkeypatch):
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'bundled-macro.db'}")
    Base.metadata.create_all(engine)
    from inku_server import db

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    effects = ProductPipelineEffects(binding, default_manifest(binding))
    source = "Nature.青葉。"
    config, context = effects.prepare("author", "direct_ddl", source,
        {"instruction_lang": "ja", "catalog_id": "default", "composition_seed": 17, "render_seed": 77}, None)
    assert len(config["definitions"]) == 7
    assert config["language"] == "ja"
    assert any("青葉" in summary for summary in config["macro_summaries"])
    omissions = context["macro_catalog"]["diagnostics"]
    assert omissions == []
    context.update(description="", committed_description="", derivation_kind="new")
    store = VariationAuthorityStore(engine)
    run = CandidateExecution(binding, store, owner_id="author", config=config,
        context=context, provider=lambda _action: pytest.fail("complete Macro called a provider"))
    run.start_new({"tag": "direct_ddl", "source": source})
    run.run_effect()
    snapshot = run.snapshot()
    assert snapshot["phase"]["tag"] == "score_ready"
    assert snapshot["document"]["source"] == source
    score = snapshot["delivery"]["score"]
    assert score["version"] == "0.11.0"
    assert score["resource_policy"]
    contacts = [instruction["relation"] for instruction in score["instructions"]
                if (instruction.get("relation") or {}).get("target_path_position") is not None]
    assert 6 <= len(contacts) <= 8
    assert all(relation["target_instruction_index"] == 0 for relation in contacts)
    stored = store.read("author", snapshot["variation_id"])
    assert stored["document"]["macro_locks"]
    engine.dispose()


def test_unsaved_success_exposes_compiler_delivery_and_logs_safe_projection(
    monkeypatch, caplog
):
    from inku_server import db

    effects = object.__new__(ProductPipelineEffects)
    effects.binding = SimpleNamespace(canvas_registry={
        "registry": {"formats": [{"id": "square", "width_units": 1, "height_units": 1}]}
    })
    monkeypatch.setattr(db, "render_hash_for_item", lambda _item: "a" * 64)
    monkeypatch.setattr(db, "render_hash_short", lambda digest: digest[:12])
    source = "raw DDL must not enter the log"
    snapshot = {
        "execution_id": "execution-1",
        "variation_id": "variation-1",
        "authority": {"revision": "1"},
        "document": {"source": source},
        "delivery": {
            "score": {"version": "0.10.0", "instructions": []},
            "source_digest": "b" * 64,
            "outcome": "complete_with_omissions",
            "compiler_options": {
                "host": {"resolved_catalog_id": "default"},
                "composition_seed": None,
                "operational_resource_budget": {"maximum": {
                    "primitive_marks": 1,
                    "maximum_per_template_primitive_marks": 1,
                    "maximum_resolved_count": 1,
                    "object_templates": 1,
                }},
            },
            "upstream_diagnostics": [{
                "issue_kind": "blocking_diagnostic",
                "issue_id": "compiler-issue:0",
                "reason": "provider raw response",
                "span": {"start": 0, "end": 7},
                "owner": {"credential": "secret-value"},
                "target": "provider raw response",
                "disposition": {"kind": "omitted"},
            }],
            "downstream_diagnostics": [{
                "reason": {"type": "unbound_macro_caller_meaning", "value": "provider raw response"},
                "owner": {"credential": "secret-value"},
                "disposition": {"kind": "omitted", "unit": {
                    "kind": "macro_caller_field", "field": "action",
                    "source_instruction_index": 0, "invocation_ordinal": "0",
                }},
            }],
            "resource_omissions": [{
                "owner": {"kind": "source_instruction", "value": {"source_instruction_index": 0}},
                "cause": {
                    "owner": {"kind": "object", "value": {"kind": "source_instruction", "instruction_index": 0}},
                    "reason": {"kind": "budget_exceeded", "value": {
                        "authority": "hard_policy",
                        "dimension": "maximum_per_template_primitive_marks",
                        "required": 300,
                        "maximum": 240,
                    }},
                },
                "partial_execution": {"requested_count": 300, "executed_count": 240},
            }],
            "relation_omissions": [],
        },
    }
    context = {
        "committed_description": "private description",
        "host_options": {
            "stage1_model": "fixture:stage1",
            "stage2_model": "fixture:stage2",
            "render_seed": "71",
            "instruction_lang": "auto",
            "instruction_lang_resolved": "en",
            "catalog_mode": "fixed",
            "save_history": False,
            "count_generation": False,
        },
        "performance_options": {
            "canvas_aspect_id": "square",
            "resolved_color_map": {},
            "wild": False,
        },
    }
    render_diagnostics = {"diagnostics": []}
    resource_execution = {"omitted_units": []}
    rendered = {
        "svg": "<svg/>",
        "metadata": {
            "render_engine_id": "default",
            "render_engine_version": "1",
            "execution": render_diagnostics,
            "resource_execution": resource_execution,
        },
    }

    with caplog.at_level("INFO", logger="inku_server.pipeline_product"):
        result = effects.save_result("author", snapshot, context, rendered)

    assert result["compiler_outcome"] == "complete_with_omissions"
    assert result["pipeline_diagnostics"] == {
        "upstream_diagnostics": snapshot["delivery"]["upstream_diagnostics"],
        "downstream_diagnostics": snapshot["delivery"]["downstream_diagnostics"],
        "resource_omissions": snapshot["delivery"]["resource_omissions"],
        "relation_omissions": [],
        "render_diagnostics": render_diagnostics,
        "resource_execution": resource_execution,
        "plugin_diagnostics": [],
    }
    assert "history_id" not in result
    records = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("pipeline_compiler_outcome ")
    ]
    assert len(records) == 1
    assert json.loads(records[0].removeprefix("pipeline_compiler_outcome ")) == {
        "execution_id": "execution-1",
        "variation_id": "variation-1",
        "revision": "1",
        "source_digest": "b" * 64,
        "compiler_outcome": "complete_with_omissions",
        "diagnostic_counts": {
            "upstream_diagnostics": 1,
            "downstream_diagnostics": 1,
            "resource_omissions": 1,
            "relation_omissions": 0,
        },
        "diagnostics": [
            {
                "channel": "upstream_diagnostics",
                "kind": "blocking_diagnostic",
                "issue_id": "compiler-issue:0",
                "actual_action": "omitted",
            },
            {
                "channel": "downstream_diagnostics",
                "kind": "unbound_macro_caller_meaning",
                "issue_id": None,
                "actual_action": "omitted",
            },
            {
                "channel": "resource_omissions",
                "kind": "budget_exceeded",
                "issue_id": None,
                "actual_action": "partially_executed",
            },
        ],
    }
    assert source not in records[0]
    assert "provider raw response" not in records[0]
    assert "secret-value" not in records[0]


def test_compact_delivery_preserves_authority_in_normal_history(tmp_path, monkeypatch):
    from inku_server import db
    from inku_server.api_core import rendering, thumbnails
    from inku_server.api_core.models import HistoryItem

    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'normal-history.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(rendering, "_submit_history_artifact_save", lambda _item: None)
    monkeypatch.setattr(thumbnails, "submit_thumbnail_build", lambda _item: None)
    with engine.begin() as connection:
        connection.execute(UserAccountRow.__table__.insert().values(
            id="author", username="author", email="author@example.test",
            password_hash="unused", role="user", at=1,
        ))
    manifest = default_manifest(binding)
    manifest["pipeline"]["definitions"] = [{
        "schema": "inku.macro-definition.v1", "namespace": "Example", "heading": "Circle",
        "version": "1.0.0", "parameters": {}, "components": {}, "body": [{
            "op": "emit", "binding": None, "fields": {
                "shape": {"expr": "semantic_ref", "category": "shape", "id": "circle"},
                "movement": {"expr": "semantic_ref", "category": "movement", "id": "place"},
                "color": {"expr": "semantic_ref", "category": "color", "id": "black"},
                "position_x": {"expr": "exact_decimal", "value": "0.5"},
                "position_y": {"expr": "exact_decimal", "value": "0.5"},
                "count": {"expr": "integer", "value": 1},
            },
        }],
    }]
    manifest["pipeline"]["macro_summaries"] = ["A black circle at the center"]
    effects = ProductPipelineEffects(binding, manifest)
    source = "Example.Circle."
    options, context = effects.prepare("author", "direct_ddl", source,
                                       {"canvas_aspect": "hd_monitor", "render_seed": "71"}, None)
    context.update(description="", committed_description="", derivation_kind="new")
    assert options["definitions"][0]["heading"] == "Circle"
    lock = context["macro_catalog"]["definition_locks"][0]
    assert lock["qualified_name"] == "Example.Circle"
    assert lock["version"] == "1.0.0"
    assert len(lock["digest"]) == 64
    maximum = options["compiler"]["hard_resource_policy"]["budget"]["maximum"]
    assert {key: maximum[key] for key in ADDITIONAL_RESOURCE_LIMITS} == {
        "logical_objects": 4096, "template_nodes": 128, "anchor_instances": 4096,
        "transform_instances": 4096, "placement_instances": 64, "fill_instances": 64,
    }
    assert maximum["primitive_marks"] == 400
    assert maximum["maximum_per_template_primitive_marks"] == 240
    assert maximum["maximum_resolved_count"] == 2000
    assert maximum["object_templates"] == 64
    saved = effects.settings.config_for("author", {"saved_config": options})
    saved["compiler"]["hard_resource_policy"]["budget"]["maximum"]["logical_objects"] = 257
    restored = effects.settings.config_for("author", {"saved_config": saved})
    assert restored == saved
    assert options["compiler"]["hard_resource_policy"]["budget"]["maximum"]["logical_objects"] == 4096
    store = VariationAuthorityStore(engine)
    run = CandidateExecution(binding, store, owner_id="author", config=options,
                             context=context, provider=lambda _action: pytest.fail("complete DDL called a provider"))
    run.start_new({"tag": "direct_ddl", "source": source})
    run.run_effect()
    snapshot = run.snapshot()
    assert snapshot["phase"]["tag"] == "score_ready"
    assert snapshot["delivery"]["score"]["version"] == "0.10.0"
    render = effects.render_options(snapshot, run.context, {"tag": "perform"})
    assert render["options"]["canvas"] == {"width": 1778, "height": 1000}
    # Only history projection is exercised here. Native SVG execution belongs
    # to the Linux check, and artifact/thumbnail workers above are disconnected.
    render_diagnostics = {
        "rendered_instruction_indices": [0],
        "omitted_instruction_indices": [],
        "diagnostics": [],
    }
    resource_execution = {
        "demand": {"primitive_marks": 1},
        "omitted_units": [],
        "relation_omissions": [],
    }
    rendered = {"svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
                "metadata": {"render_engine_id": "default", "render_engine_version": "59",
                             "execution": render_diagnostics,
                             "resource_execution": resource_execution}}
    expected_diagnostics = {
        "upstream_diagnostics": snapshot["delivery"]["upstream_diagnostics"],
        "downstream_diagnostics": snapshot["delivery"]["downstream_diagnostics"],
        "resource_omissions": snapshot["delivery"]["resource_omissions"],
        "relation_omissions": snapshot["delivery"]["relation_omissions"],
        "render_diagnostics": render_diagnostics,
        "resource_execution": resource_execution,
        "plugin_diagnostics": [],
    }
    result = effects.save_result("author", snapshot, run.context, rendered)
    replay = effects.save_result("author", snapshot, run.context, rendered)
    assert result["history_id"] == replay["history_id"]
    assert result["compiler_outcome"] == snapshot["delivery"]["outcome"]
    assert result["pipeline_diagnostics"] == expected_diagnostics
    item = db.get_items("author", [result["history_id"]])[0]
    response = HistoryItem.model_validate(item).model_dump()
    assert response["score"] == snapshot["delivery"]["score"]
    assert response["ddl"] == snapshot["document"]["source"]
    assert response["svg"] == rendered["svg"]
    assert response["pipeline_variation_id"] == snapshot["variation_id"]
    assert response["pipeline_revision"] == "1"
    assert response["render_canvas_aspect_id"] == "hd_monitor"
    assert response["render_seed"] == 71
    assert response["pipeline_diagnostics"] == expected_diagnostics
    with engine.begin() as connection:
        connection.execute(
            PipelineHistoryLinkRow.__table__.update()
            .where(PipelineHistoryLinkRow.history_id == result["history_id"])
            .values(fork_context_digest="invalid")
        )
    damaged = db.get_items("author", [result["history_id"]])[0]
    assert damaged["data_warnings"] == ["pipeline_diagnostics_invalid"]
    assert "pipeline_diagnostics" not in damaged
    assert damaged["ddl"] == snapshot["document"]["source"]
    assert damaged["score"] == snapshot["delivery"]["score"]
    assert damaged["svg"] == rendered["svg"]
    assert store.history_link("another", result["history_id"]) is None
    assert store.read("author", snapshot["variation_id"])["authority"]["authority"] == "ddl_authoritative"
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(HistoryRow)) == 1
        assert connection.scalar(select(UserAccountRow.image_generation_count)) == 1
    engine.dispose()


def test_partway_score_replay_routes_preserve_the_symbolic_position(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from inku_server.api_core.routers import render as render_routes
    from inku_server import pipeline_runtime

    app = FastAPI()
    app.include_router(render_routes.router)
    app.dependency_overrides[render_routes._current_user] = lambda: {"id": "author"}
    client = TestClient(app)
    score = {"version": "0.13.0", "instructions": [
        {"primitive": "arc"}, {"primitive": "line", "relation": {
            "type": "connected", "target_instruction_index": 0,
            "target_path_position": "interior", "position_authority": "named_movable",
        }},
    ]}
    calls = []

    def replay(owner_id, payload, work):
        calls.append((owner_id, payload, work))
        # Stop at the shared service boundary without producing SVG on the host.
        raise HTTPException(status_code=409, detail="shared replay reached")

    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: SimpleNamespace(replay_for=replay))
    for path in ("/api/render-score", "/api/render-svg"):
        response = client.post(path, json={"score": score, "render_seed": 77})
        assert response.status_code == 409
        assert response.json()["detail"] == "shared replay reached"
    assert len(calls) == 2
    for owner_id, payload, work in calls:
        assert owner_id == "author"
        assert payload["score"] == score
        assert payload["render_seed"] == 77
        assert work is None


def test_a_compact_work_exports_through_the_shared_replay(monkeypatch):
    # Every profile but display redraws the saved work. The plain render
    # refuses a compact Score without its resource policy, so editable, compat
    # and live exports of such a work answered 422 InvalidCompactPerformance.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from inku_server.api_core.routers import history as history_routes
    from inku_server import pipeline_runtime

    app = FastAPI()
    app.include_router(history_routes.router)
    app.dependency_overrides[history_routes._current_user] = lambda: {"id": "author"}
    client = TestClient(app)
    work = {"id": "work", "score": {"version": "0.10.0", "instructions": []}, "svg": "<svg/>",
            "render_seed": 77, "composition_seed": 5, "render_wild": True, "catalog_id": "default"}
    monkeypatch.setattr(history_routes._db, "get_items", lambda owner, ids: [work])
    calls = []

    def replay(owner_id, payload, row):
        calls.append((owner_id, payload, row))
        return {"svg": "<svg id='replayed'/>"}

    monkeypatch.setattr(pipeline_runtime, "get_service", lambda: SimpleNamespace(replay_for=replay))
    response = client.get("/api/history/work/svg", params={"profile": "live"})
    assert response.status_code == 200
    assert response.text == "<svg id='replayed'/>"
    [(owner_id, payload, row)] = calls
    assert owner_id == "author"
    assert row is work
    assert payload["svg_profile"] == "live"
    assert (payload["render_seed"], payload["composition_seed"], payload["wild"]) == (77, 5, True)
