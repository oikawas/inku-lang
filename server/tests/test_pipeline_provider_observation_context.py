"""The provider capture context must contain the durable execution identity."""

import json

from sqlalchemy import create_engine

from inku_server.persistence.schema import Base
from inku_server.persistence.variation_authority import VariationAuthorityStore
from inku_server.pipeline_api import PipelineService


class _Binding:
    canvas_registry = {"registry": {"formats": []}}

    @staticmethod
    def step(snapshot_bytes: bytes, input_bytes: bytes) -> bytes:
        request = json.loads(input_bytes)
        if not snapshot_bytes:
            snapshot = {
                "execution_id": "execution-1", "variation_id": "variation-1",
                "sequence": request["sequence"], "authority": {"revision": "0"},
                "document": None, "delivery": None,
                "phase": {"tag": "awaiting_llm", "stage": "generate_normalized_ddl"},
                "action": {"tag": "generate_normalized_ddl", "delay_ms": "0", "timeout_ms": "1000",
                           "identity": {"action_id": "action-1", "attempt": 1, "request_digest": "request-1"},
                           "payload": {"prompt": {}}},
            }
        else:
            snapshot = json.loads(snapshot_bytes)
            snapshot["sequence"] = request["sequence"]
            snapshot["action"] = None
            snapshot["phase"] = {"tag": "failed", "reason": "stage1_failed"}
        return json.dumps({"kind": "output", "payload": {"result": {
            "snapshot": snapshot, "events": [], "rendered": None,
        }}}).encode()


def test_provider_context_and_first_saved_snapshot_include_execution_id(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline-context.db'}")
    Base.metadata.create_all(engine)
    store = VariationAuthorityStore(engine)
    seen: list[str] = []

    def provider_with_context(_owner: str, context: dict):
        seen.append(context["execution_id"])
        return lambda action: {
            "tag": "provider_failed", "identity": action["identity"],
            "failure": "provider_rejected", "elapsed_ms": "1",
        }

    service = PipelineService(
        _Binding(), store, config_for=lambda _owner, _work: {"envelope_limits": {
            "max_input_bytes": 1024 * 1024, "max_snapshot_bytes": 1024 * 1024,
            "max_output_bytes": 1024 * 1024,
        }}, provider_for=lambda _owner: None, render_for=None,
        provider_with_context=provider_with_context,
        max_workers=1, max_effect_steps=2, max_retained_runs=1,
    )
    try:
        view = service.start("owner", "description", "description")
        service._jobs[("owner", view["execution_id"])].result(timeout=2)
        assert seen == ["execution-1"]
        saved = json.loads(store.read_execution("owner", "execution-1").state_bytes)
        assert saved["context"]["execution_id"] == "execution-1"
    finally:
        service.close()
        engine.dispose()
