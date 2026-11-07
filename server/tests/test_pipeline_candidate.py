"""One real-binding host/DB connection; no provider network or native rendering."""

import json
import logging
import time

import pytest
from sqlalchemy import create_engine

from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_candidate import (
    CandidateExecution,
    CandidateHostError,
    PipelineBinding,
    _hole_completion_checks,
    _pipeline_failures,
    _sync_hole_completion_check,
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
            "error_policy": "omit_and_continue",
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


def test_hole_completion_event_projects_only_safe_per_hole_diagnostics():
    first_hole = "hole:" + "a" * 64
    second_hole = "hole:" + "b" * 64
    third_hole = "hole:" + "c" * 64
    author_source = "右下に、青い円。\r\n線。"
    result = {
        "events": [
            {
                "tag": "hole_completion_checked",
                "payload": {
                    "results": [
                        {"hole_id": first_hole, "status": "rejected", "reason": "owner_changed", "source": author_source, "proposal": "model text must not be retained"},
                        {"hole_id": second_hole, "status": "unresolved", "reason": "ambiguous", "source": "空" * 8193},
                        {"hole_id": third_hole, "status": "unresolved", "reason": "unsupported", "source": {"model": "not author text"}},
                        {"hole_id": "hole:not-hex", "status": "rejected", "reason": "owner_changed"},
                    ],
                    "raw_response": "must not be retained",
                    "base_source_digest": "trusted-but-not-user-diagnostic",
                },
            }
        ]
    }

    expected = {
        "results": [
            {"hole_id": first_hole, "status": "rejected", "reason": "owner_changed", "source": author_source},
            {"hole_id": second_hole, "status": "unresolved", "reason": "ambiguous", "source": "空" * 8192},
            {"hole_id": third_hole, "status": "unresolved", "reason": "unsupported"},
        ]
    }
    assert _hole_completion_checks(result) == [expected]
    context = {"hole_completion_check": {"results": [{"hole_id": "stale"}]}}
    assert _sync_hole_completion_check(
        context,
        {
            "hole_completion_check": {
                **expected,
                "base_source_digest": "not-visible",
            }
        },
    ) == expected
    assert context["hole_completion_check"] == expected
    assert _sync_hole_completion_check(context, {"hole_completion_check": None}) is None
    assert "hole_completion_check" not in context


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
    assert run.transcript is None and run.last_output is None
    run.run_effect()  # Recorded provider result -> atomic commit request, no Score yet.
    assert run.transcript is None and run.last_output is None
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


def test_a_running_model_call_is_numbered_and_given_a_deadline(tmp_path):
    # W4: the page showed only elapsed time, so a first attempt that timed out
    # looked like a slow answer.
    binding = PipelineBinding()
    engine = create_engine(f"sqlite:///{tmp_path / 'candidate.db'}")
    store = VariationAuthorityStore(engine)
    store.install_schema()
    seen = []

    def provider(action):
        seen.append((time.time() * 1000, run.view()["provider_attempt"]))
        if action["identity"]["attempt"] == 1:
            return {"tag": "provider_failed", "identity": action["identity"],
                    "failure": "transport_timeout", "elapsed_ms": "1000"}
        return {
            "tag": "normalized_ddl_generated", "identity": action["identity"],
            "response": json.dumps({"normalized_ddl": "place one black circle at center."}),
            "elapsed_ms": "1",
        }

    run = CandidateExecution(binding, store, owner_id="acceptance", config=_fixture_config(), provider=provider)
    run.start_new({"tag": "description", "description": "One quiet black circle", "auto_catalog": False})
    # Not begun yet, as after a restart: numbered, but no deadline to show.
    assert "deadline_at" not in run.view()["provider_attempt"]
    run.run_effect()
    run.run_effect()

    assert [(attempt["action"], attempt["attempt"], attempt["max_attempts"]) for _, attempt in seen] == [
        ("generate_normalized_ddl", 1, 2), ("generate_normalized_ddl", 2, 2),
    ]
    for called, attempt in seen:
        # The deadline counts from before the delay, so it falls within the timeout of the call.
        assert 0 < attempt["deadline_at"] - called <= int(attempt["timeout_ms"])
    assert "provider_attempt" not in run.view()
    engine.dispose()


def test_pipeline_view_and_stream_share_progress_from_fake_provider(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from inku_server import pipeline_compat
    from inku_server.pipeline_product import _add_provider_usage

    engine = create_engine(f"sqlite:///{tmp_path / 'progress.db'}")
    store = VariationAuthorityStore(engine)
    store.install_schema()
    observed = []

    def provider(action):
        run.context["provider_receiving"] = {"action": action["tag"], "attempt": 1, "bytes": 4096}
        observed.append(run.view()["progress"])
        run.context.pop("provider_receiving")
        used = {"input_tokens": 123, "output_tokens": 45}
        _add_provider_usage(run.context, "stage1", used)
        run.context.setdefault("provider_sends", []).append({"action": action["tag"], "attempt": 1, **used})
        return {"tag": "normalized_ddl_generated", "identity": action["identity"],
                "response": json.dumps({"normalized_ddl": "place one black circle at center."}), "elapsed_ms": "1"}

    run = CandidateExecution(PipelineBinding(), store, owner_id="acceptance", config=_fixture_config(), provider=provider)
    run.start_new({"tag": "description", "description": "One quiet black circle", "auto_catalog": False})
    run.run_effect()
    view = run.view()
    assert observed[0]["received_bytes"] == 4096
    assert view["progress"]["stage_tokens"] == {"generate_normalized_ddl": {"input_tokens": 123, "output_tokens": 45, "unreported_sends": 0}}
    assert "previous" not in view["progress"]
    assert view["progress"]["total"] == {"input_tokens": 123, "output_tokens": 45, "unreported_sends": 0}
    monkeypatch.setattr(pipeline_compat, "_service", lambda: SimpleNamespace(execution=lambda *_: run))
    events = list(pipeline_compat._progress("acceptance", view, time.monotonic(), set()))
    streamed = next(event for event in events if event["event"] == "progress")
    assert {key: value for key, value in streamed.items() if key != "event"} == view["progress"]
    engine.dispose()


def test_progress_groups_retries_and_unreported_sends_by_action():
    from inku_server.pipeline_candidate import progress_projection
    from inku_server.pipeline_product import _add_provider_usage

    class Binding:
        def run_progress(self, _state):
            return b'{"run_progress":{"current":null,"finished":[]}}'

    context = {"provider_sends": []}
    for action, used in [("read_description", {"input_tokens": 10, "output_tokens": 2}),
                         ("read_description", None),
                         ("read_description", {"input_tokens": 5, "output_tokens": 3}),
                         ("choose_colors", {"input_tokens": 7, "output_tokens": 1})]:
        _add_provider_usage(context, "stage1", used)
        context["provider_sends"].append({"action": action, "usage_reported": used is not None, **(used or {})})
    progress = progress_projection(Binding(), {}, context)
    assert progress["stage_tokens"] == {
        "read_description": {"input_tokens": 15, "output_tokens": 5, "unreported_sends": 1},
        "choose_colors": {"input_tokens": 7, "output_tokens": 1, "unreported_sends": 0},
    }
    for key in ("input_tokens", "output_tokens", "unreported_sends"):
        assert sum(row[key] or 0 for row in progress["stage_tokens"].values()) == progress["total"][key]


@pytest.mark.parametrize("mode", ["step", "restore", "old_wheel", "null"])
def test_snapshot_reports_are_reused_but_host_progress_and_deadlines_stay_live(mode):
    class Binding:
        def __init__(self):
            self.calls = {"provider_attempt": 0, "run_progress": 0}

        def step(self, snapshot_bytes, _input):
            sequence = str(int(json.loads(snapshot_bytes)["sequence"]) + 1) if snapshot_bytes else "0"
            state = {
                "execution_id": "execution-1", "variation_id": "variation-1", "sequence": sequence,
                "authority": {"revision": "0"}, "document": None,
                "phase": {"tag": "awaiting_llm"}, "delivery": None,
                "action": {"tag": "generate_normalized_ddl", "identity": {"attempt": 1}},
            }
            payload = {"result": {"snapshot": state, "rendered": None, "events": []}}
            if mode != "old_wheel":
                payload.update(provider_attempt=self.attempt(), run_progress=self.progress(state))
            return json.dumps({"kind": "output", "payload": payload}).encode()

        def attempt(self):
            return None if mode == "null" else {"attempt": 1, "delay_ms": "10", "timeout_ms": "1000"}

        def progress(self, state):
            return None if mode == "null" else {"sequence": state["sequence"]}

        def provider_attempt(self, _state):
            self.calls["provider_attempt"] += 1
            return json.dumps({"provider_attempt": self.attempt()}).encode()

        def run_progress(self, state):
            self.calls["run_progress"] += 1
            return json.dumps({"run_progress": self.progress(json.loads(state))}).encode()

    binding = Binding()
    run = CandidateExecution(binding, None, owner_id="fixture", config=_fixture_config(), provider=lambda _: None)
    run.start_new({"tag": "description", "description": "fixture", "auto_catalog": False})
    if mode == "restore":
        snapshot = run.snapshot()
        run = CandidateExecution(binding, None, owner_id="fixture", config=_fixture_config(), provider=lambda _: None)
        run.restore(snapshot)
    first = run.view()
    expected_calls = 1 if mode in {"restore", "old_wheel"} else 0
    assert binding.calls == {"provider_attempt": expected_calls, "run_progress": expected_calls}
    if mode == "null":
        assert "provider_attempt" not in first and "progress" not in first
        assert run.view() == first
    else:
        assert "deadline_at" not in first["provider_attempt"]
        run._attempt_began = (run.snapshot()["action"], 2000)
        run.context["provider_receiving"] = {"bytes": 4096}
        run.context["provider_sends"] = [{"action": "generate_normalized_ddl", "input_tokens": 7}]
        run.context["provider_usage"] = {"stage1": {"input_tokens": 7, "output_tokens": 0, "unreported_sends": 0}}
        second = run.view()
        assert second["provider_attempt"]["deadline_at"] == 3010
        assert second["progress"]["received_bytes"] == 4096
        assert second["progress"]["stage_tokens"]["generate_normalized_ddl"]["input_tokens"] == 7
        assert second["progress"]["total"]["input_tokens"] == 7
        assert run.view() == second
        assert "deadline_at" not in run._snapshot_reports["provider_attempt"]
        run._attempt_began = None
        assert "deadline_at" not in run.view()["provider_attempt"]
    assert binding.calls == {"provider_attempt": expected_calls, "run_progress": expected_calls}
    run.command({"tag": "cancel"})
    latest = run.view()
    if mode != "null":
        assert latest["progress"]["run_progress"] == {"sequence": "1"}
    if mode == "old_wheel":
        assert binding.calls == {"provider_attempt": 2, "run_progress": 2}
    else:
        assert binding.calls == {"provider_attempt": expected_calls, "run_progress": expected_calls}


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


def test_reading_fallback_is_logged_once_without_provider_text(caplog):
    class FixtureBinding:
        def step(self, snapshot_bytes, _input_bytes):
            if snapshot_bytes:
                snapshot = json.loads(snapshot_bytes)
                snapshot["action"] = None
                events = [{"tag": "description_reading_fallback", "payload": {
                    "failure": "transport_timeout", "detail": "no_core_image", "response": "PRIVATE RESPONSE"}}]
            else:
                snapshot = {"execution_id": "execution-1", "variation_id": "variation-1", "sequence": "0",
                            "authority": {"revision": "0"}, "document": None, "phase": {"tag": "awaiting_llm"},
                            "delivery": None, "action": {"tag": "read_description", "delay_ms": "0",
                            "identity": {"attempt": 2, "action_id": "action-1"}}}
                events = []
            return json.dumps({"kind": "output", "payload": {"result": {
                "snapshot": snapshot, "events": events, "rendered": None}}}).encode()

    def provider(action):
        return {"tag": "provider_failed", "identity": action["identity"], "failure": "transport_timeout",
                "elapsed_ms": "123", "response": "PRIVATE RESPONSE"}

    run = CandidateExecution(FixtureBinding(), object(), owner_id="acceptance", config=_fixture_config(), provider=provider)
    with caplog.at_level(logging.WARNING, logger="inku_server.pipeline_candidate"):
        run.start_new({"tag": "description", "description": "PRIVATE PROMPT", "auto_catalog": False})
        run.run_effect()
    lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("pipeline_fallback ")]
    assert len(lines) == 1
    assert json.loads(lines[0].removeprefix("pipeline_fallback ")) == {
        "event": "description_reading_fallback", "failure": "transport_timeout", "detail": "no_core_image",
        "stage": "read_and_draw", "action_id": "action-1", "attempt": 2, "elapsed_ms": 123,
        "execution_id": "execution-1", "variation_id": "variation-1",
    }
    assert "PRIVATE" not in caplog.text


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
