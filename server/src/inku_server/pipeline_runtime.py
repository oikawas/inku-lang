"""Normal Server composition of the shared core and host effects.

The configuration file contains explicit deployment policies and definitions,
never credentials. There is no old/new runtime selector or Python fallback.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .pipeline_candidate import PipelineBinding

_binding: PipelineBinding | None = None
_service = None
_lock = threading.RLock()


def get_binding() -> PipelineBinding:
    global _binding
    with _lock:
        if _binding is None:
            _binding = PipelineBinding()
        return _binding


def host_limits() -> dict:
    """The worker-pool limits in force, without starting the service."""
    with _lock:
        if _service is not None:
            return {"max_workers": _service.max_workers,
                    "max_effect_steps": _service.max_effect_steps,
                    "max_retained_runs": _service.max_retained_runs}
    path = os.environ.get("INKU_PIPELINE_CONFIG")
    if path:
        return dict(json.loads(Path(path).read_bytes())["host_limits"])
    from .pipeline_defaults import HOST_LIMITS

    return dict(HOST_LIMITS)


def get_service():
    global _service
    with _lock:
        if _service is not None:
            return _service
        path = os.environ.get("INKU_PIPELINE_CONFIG")
        from . import db
        from .pipeline_api import PipelineService
        from .pipeline_product import ProductPipelineEffects
        from .pipeline_defaults import default_manifest
        from .persistence.variation_authority import VariationAuthorityStore

        binding = get_binding()
        manifest = json.loads(Path(path).read_bytes()) if path else default_manifest(binding)
        effects = ProductPipelineEffects(binding, manifest)
        limits = manifest["host_limits"]
        _service = PipelineService(
            binding, VariationAuthorityStore(db.engine), config_for=effects.settings.config_for,
            provider_for=lambda owner: effects.provider_for(owner, {}), render_for=None,
            prepare_for=effects.prepare, provider_with_context=effects.provider_for,
            render_with_context=effects.render_options, project_result=effects.save_result,
            replay_for=effects.replay, provider_observations=effects.provider_observations,
            max_workers=limits["max_workers"], max_effect_steps=limits["max_effect_steps"],
            max_retained_runs=limits["max_retained_runs"],
        )
        return _service


def shutdown() -> None:
    global _service
    with _lock:
        if _service is not None:
            _service.close()
            _service = None
