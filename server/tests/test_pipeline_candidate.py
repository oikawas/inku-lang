"""One real-binding host/DB connection; no provider network or native rendering."""

import json
import logging

import pytest
from sqlalchemy import create_engine

from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import (
    CandidateExecution,
    CandidateHostError,
    PipelineBinding,
    _pipeline_failures,
)


def _fixture_config() -> dict:
    # Explicit acceptance values, corresponding to the Step12 focused flow.
    # These are not shipping defaults for the additional resource dimensions.
    white = {"abstract_color": "white", "concrete_rgb": [255, 255, 255], "oklch_lightness": 1.0}
    black = {"abstract_color": "black", "concrete_rgb": [0, 0, 0], "oklch_lightness": 0.0}
    budget = {"maximum": {
        "logical_objects": 400, "primitive_marks": 400, "object_templates": 64,
        "maximum_per_template_primitive_marks": 240, "maximum_resolved_count": 2000,
        "template_nodes": 512, "anchor_instances": 400, "transform_instances": 400,
        "placement_instances": 400, "fill_instances": 400,
    }}
    retry = {"max_attempts": 2, "attempt_timeout_ms": "1000", "total_timeout_ms": "3000", "retry_delay_ms": "10"}
    return {
        "envelope_limits": {"max_input_bytes": 1_000_000, "max_snapshot_bytes": 1_000_000, "max_output_bytes": 2_000_000},
        "language": "en",
        "compiler": {
            "host": {
                "canvas_format_id": "square", "canvas_format_registry_id": "inku.canvas-format-registry.v1",
                # Shared known answer: core/crates/inku-score/tests/fixtures/canvas-format-registry-v1.json.
                "canvas_format_registry_digest": "16fde66009a901ec65887303389a0253235467cb0437ab38084ff15ea4f8ae18",
                "resolved_catalog_id": "default", "catalog_mode": "default", "background": "white",
                "palette": {"background": white, "black": black, "white": white, "observations": None},
            },
            "composition_seed": "17",
            "macro_expansion_limits": {"max_invocations": "16", "max_depth": "16", "max_evaluation_steps": "1000", "max_nodes_per_invocation": "100", "max_total_nodes": "500"},
            "stage15_variation": None, "error_policy": "omit_and_continue",
            "hard_resource_policy": {"identity": "pipeline-fixture.v1", "budget": budget},
            "operational_resource_budget": budget,
        },
        "definitions": [], "macro_summaries": [], "catalogs": [],
        "prompt_limits": {"max_catalog_entries": 16, "max_summary_bytes": 1024, "max_catalog_serialized_bytes": 32768, "max_source_bytes": 8192, "max_response_bytes": 16384},
        "catalog_retry": retry, "stage1_retry": retry, "hole_retry": retry,
    }


def test_core_compiler_failure_detail_is_allowlisted():
    state = {
        "action": {
            "tag": "generate_normalized_ddl",
            "identity": {"attempt": 4},
        }
    }
    envelope = {
        "payload": {
            "tag": "effect_result",
            "result": {"elapsed_ms": "855"},
        }
    }
    result = {
        "events": [{
            "tag": "failed",
            "payload": {
                "reason": "semantic_violation",
                "detail": "upstream_unknown",
            },
        }]
    }

    assert _pipeline_failures(state, envelope, result) == [(
        "failed",
        {
            "failure": "semantic_violation",
            "stage": "stage1",
            "detail": "upstream_unknown",
            "attempt": 4,
            "elapsed_ms": 855,
        },
    )]

    result["events"][0]["payload"]["detail"] = "raw response marker"
    assert "detail" not in _pipeline_failures(state, envelope, result)[0][1]


def test_real_binding_commits_source_and_authority_before_automatic_hole_request(tmp_path):
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate.db'}")
    store = VariationAuthorityStore(engine)
    store.install_schema()
    calls = []

    def provider(action):
        calls.append(action)
        if action["tag"] == "generate_normalized_ddl":
            return {
                "tag": "normalized_ddl_generated", "identity": action["identity"],
                "response": json.dumps({"normalized_ddl": "place one black circle at center."}),
                "elapsed_ms": "1",
            }
        assert action["tag"] == "complete_visible_ddl_holes"
        return {"tag": "provider_failed", "identity": action["identity"], "failure": "provider_rejected", "elapsed_ms": "1"}

    run = CandidateExecution(binding, store, owner_id="acceptance", config=_fixture_config(), provider=provider)
    run.start_new({"tag": "description", "description": "One quiet black circle", "auto_catalog": False})
    run.run_effect()  # Recorded provider result -> atomic commit request, no Score yet.
    assert run.view()["delivery"] is None
    assert store.inventory().candidate_variations == 0
    run.run_effect()  # Actual SQL transaction -> Rust compile/finalize.
    view = run.view()
    assert view["phase"]["tag"] == "score_ready"
    assert view["delivery"]["score"] is not None
    assert len(calls) == 1
    saved = store.read("acceptance", view["variation_id"])
    assert saved["document"] == view["document"]
    assert saved["authority"] == view["authority"]
    assert saved["authority"]["authority"] == "description_authoritative"

    edited = "place one black circle at center. many square."
    run.command({"tag": "commit_user_ddl", "expected_revision": "1", "source": edited})
    assert store.read("acceptance", view["variation_id"])["document"]["source"] != edited
    run.run_effect()
    locked = store.read("acceptance", view["variation_id"])
    assert locked["document"]["source"] == edited
    assert locked["authority"]["authority"] == "ddl_authoritative"
    assert locked["authority"]["revision"] == "2"
    assert locked["authority"]["origin"] == "stage1_generated"
    run.run_effect()  # No CompleteHoles command: core issued it after the save ACK.
    assert [action["tag"] for action in calls] == ["generate_normalized_ddl", "complete_visible_ddl_holes"]
    assert run.view()["phase"]["tag"] == "needs_user_edit"
    assert store.inventory().action_acknowledgments == 2
    with pytest.raises(CandidateHostError, match="description_locked"):
        run.command({"tag": "generate_from_description", "expected_revision": "2", "description": "overwrite", "auto_catalog": False})
    assert store.read("acceptance", view["variation_id"])["document"]["source"] == edited
    engine.dispose()


def test_core_failures_are_persisted_and_logged_once_per_transition(caplog):
    class FixtureBinding:
        def step(self, snapshot_bytes, _input_bytes):
            if not snapshot_bytes:
                snapshot = {
                    "execution_id": "execution-1",
                    "variation_id": "variation-1",
                    "sequence": "0",
                    "authority": {"revision": "0"},
                    "document": None,
                    "phase": {"tag": "awaiting_llm"},
                    "delivery": None,
                    "action": {
                        "tag": "generate_normalized_ddl",
                        "identity": {"attempt": 1},
                        "delay_ms": "0",
                    },
                }
                events = []
            else:
                snapshot = json.loads(snapshot_bytes)
                attempt = snapshot["action"]["identity"]["attempt"]
                snapshot["sequence"] = str(int(snapshot["sequence"]) + 1)
                if attempt == 1:
                    snapshot["action"]["identity"]["attempt"] = 2
                    events = [
                        {
                            "tag": "retry_scheduled",
                            "payload": {"failure": "schema_violation"},
                        }
                    ]
                else:
                    snapshot["action"] = None
                    snapshot["phase"] = {"tag": "failed", "reason": "stage1_failed"}
                    events = [
                        {
                            "tag": "failed",
                            "payload": {
                                "stage": "generate_normalized_ddl",
                                "reason": "schema_violation",
                            },
                        }
                    ]
            return json.dumps(
                {
                    "kind": "output",
                    "payload": {
                        "result": {
                            "snapshot": snapshot,
                            "events": events,
                            "rendered": None,
                        }
                    },
                }
            ).encode()

    persisted = []

    def provider(action):
        return {
            "tag": "normalized_ddl_generated",
            "identity": action["identity"],
            "response": "raw response marker that must not be logged",
            "elapsed_ms": "7",
        }

    def save(_previous, _snapshot, context, _rendered):
        persisted.append(json.loads(json.dumps(context)))

    run = CandidateExecution(
        FixtureBinding(),
        object(),
        owner_id="acceptance",
        config=_fixture_config(),
        provider=provider,
        context={
            "provider_failure": {
                "failure": "schema_violation",
                "stage": "stage1",
                "attempt": 1,
                "elapsed_ms": 7,
                "detail": "credentials_unavailable",
            }
        },
        save_snapshot=save,
    )
    with caplog.at_level(logging.WARNING, logger="inku_server.pipeline_candidate"):
        run.start_new(
            {
                "tag": "description",
                "description": "One quiet black circle",
                "auto_catalog": False,
            }
        )
        run.run_effect()
        run.run_effect()

    diagnostic = {
        "failure": "schema_violation",
        "stage": "stage1",
        "attempt": 2,
        "elapsed_ms": 7,
    }
    assert run.view()["provider_failure"] == diagnostic
    assert "detail" not in run.view()["provider_failure"]
    assert persisted[-1]["provider_failure"] == diagnostic
    records = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("pipeline_failure ")
    ]
    assert len(records) == 2
    payloads = [json.loads(message.removeprefix("pipeline_failure ")) for message in records]
    assert [payload["transition"] for payload in payloads] == ["retry_scheduled", "failed"]
    assert [payload["attempt"] for payload in payloads] == [1, 2]
    assert all(payload["failure"] == "schema_violation" for payload in payloads)
    assert all(payload["stage"] == "stage1" for payload in payloads)
    assert all(payload["elapsed_ms"] == 7 for payload in payloads)
    assert all(payload["execution_id"] == run.view()["execution_id"] for payload in payloads)
    assert all(payload["variation_id"] == run.view()["variation_id"] for payload in payloads)
    assert "raw response marker" not in caplog.text


def test_matching_safe_provider_detail_is_persisted_and_logged(caplog):
    class FixtureBinding:
        def step(self, snapshot_bytes, _input_bytes):
            if not snapshot_bytes:
                snapshot = {
                    "execution_id": "execution-credentials",
                    "variation_id": "variation-credentials",
                    "sequence": "0",
                    "authority": {"revision": "0"},
                    "document": None,
                    "phase": {"tag": "awaiting_llm"},
                    "delivery": None,
                    "action": {
                        "tag": "generate_normalized_ddl",
                        "identity": {"attempt": 1},
                        "delay_ms": "0",
                    },
                }
                events = []
            else:
                snapshot = json.loads(snapshot_bytes)
                snapshot["sequence"] = "1"
                snapshot["action"] = None
                snapshot["phase"] = {"tag": "failed", "reason": "stage1_failed"}
                events = [{
                    "tag": "failed",
                    "payload": {
                        "stage": "generate_normalized_ddl",
                        "reason": "provider_rejected",
                    },
                }]
            return json.dumps({
                "kind": "output",
                "payload": {
                    "result": {
                        "snapshot": snapshot,
                        "events": events,
                        "rendered": None,
                    }
                },
            }).encode()

    persisted = []
    holder = {}

    def provider(action):
        holder["run"].context["provider_failure"] = {
            "failure": "provider_rejected",
            "stage": "stage1",
            "attempt": 1,
            "elapsed_ms": 3,
            "detail": "credentials_unavailable",
        }
        return {
            "tag": "provider_failed",
            "identity": action["identity"],
            "failure": "provider_rejected",
            "elapsed_ms": "3",
        }

    def save(_previous, _snapshot, context, _rendered):
        persisted.append(json.loads(json.dumps(context)))

    run = CandidateExecution(
        FixtureBinding(),
        object(),
        owner_id="acceptance",
        config=_fixture_config(),
        provider=provider,
        save_snapshot=save,
    )
    holder["run"] = run
    with caplog.at_level(logging.WARNING, logger="inku_server.pipeline_candidate"):
        run.start_new({
            "tag": "description",
            "description": "One quiet black circle",
            "auto_catalog": False,
        })
        run.run_effect()

    diagnostic = {
        "failure": "provider_rejected",
        "stage": "stage1",
        "attempt": 1,
        "elapsed_ms": 3,
        "detail": "credentials_unavailable",
    }
    assert run.view()["provider_failure"] == diagnostic
    assert persisted[-1]["provider_failure"] == diagnostic
    records = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("pipeline_failure ")
    ]
    assert len(records) == 1
    payload = json.loads(records[0].removeprefix("pipeline_failure "))
    assert payload == {
        "execution_id": "execution-credentials",
        "variation_id": "variation-credentials",
        "transition": "failed",
        **diagnostic,
    }
