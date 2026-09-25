"""The settings status describes the pool that actually runs model effects.

Before the shared pipeline, Stage 1/2 calls went through a Stage executor. That
executor lost its last caller at the cutover, so a status built from it showed
a pool nothing used and counters nothing moved.
"""

from __future__ import annotations

from inku_server import db, pipeline_product
from inku_server.api_core import state
from inku_server.api_core.routers.settings import _stage_execution_status
from inku_server.pipeline_defaults import HOST_LIMITS


def test_the_status_names_the_pipeline_worker_pool(monkeypatch) -> None:
    monkeypatch.delenv("INKU_PIPELINE_CONFIG", raising=False)
    status = _stage_execution_status()
    assert status.workers == HOST_LIMITS["max_workers"]
    assert status.queue_limit == HOST_LIMITS["max_retained_runs"]


def test_each_provider_effect_is_counted_by_its_outcome(monkeypatch) -> None:
    effects = pipeline_product.ProductPipelineEffects.__new__(pipeline_product.ProductPipelineEffects)
    effects.manifest = {
        "provider": {"stage1_model": "model", "stage2_model": "model", "max_tokens": 16, "stage1_max_tokens": 16},
        "pipeline": {"prompt_limits": {"max_response_bytes": 1024}},
    }
    results = iter([
        {"tag": "normalized_ddl_generated", "response": "{}", "elapsed_ms": "5"},
        {"tag": "provider_failed", "failure": "transport_timeout", "elapsed_ms": "7"},
        {"tag": "provider_failed", "failure": "provider_rejected", "elapsed_ms": "1"},
    ])
    monkeypatch.setattr(
        pipeline_product, "SingleAttemptProvider",
        lambda options, observation=None: (lambda action: next(results)),
    )
    monkeypatch.setattr(db, "get_model_settings", lambda: {})
    perform = effects.provider_for("author-1", {"host_options": {}, "execution_id": "execution-1"})
    action = {"tag": "generate_normalized_ddl", "identity": {"attempt": "1"}}

    before = state._stage_execution_stats()
    for _ in range(3):
        perform(action)
    after = state._stage_execution_stats()

    moved = {name: after[name] - before[name] for name in after}
    assert moved == {"submitted": 3, "completed": 1, "failed": 1, "timed_out": 1, "rejected": 0}
