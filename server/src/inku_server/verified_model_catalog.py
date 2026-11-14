"""Python access to the embedded core model catalog."""

import json
import math
from functools import lru_cache

import inku_render


@lru_cache(maxsize=1)
def catalog_info():
    return core_catalog("catalog")


def core_catalog(action, **fields):
    request = {"schema": "inku.model-catalog-request.v1", "action": action, **fields}
    def json_value(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_value(item) for item in value]
        return value
    result = json.loads(inku_render.pipeline_model_catalog(json.dumps(json_value(request), ensure_ascii=False, allow_nan=False).encode("utf-8")))
    if result.get("outcome") != "ok":
        raise ValueError(f"model catalog refused: {result}")
    return result


def sign_in(action, **fields):
    """A Sign in with ChatGPT action of the shared core.

    The core takes only ``sign_in_<action>`` with the service it serves; the
    old ``chatgpt_*`` names are refused there (step 6, 2026-11-15).
    """
    return core_catalog("sign_in_" + action, service="chatgpt", **fields)


_info = catalog_info()
MODEL_CATALOG = _info["catalog"]
MODEL_CONFIG_VERSION = _info["version"]
MODEL_CONFIG_LAST_UPDATED = MODEL_CATALOG["updated"]
STORED_LABEL_KEYS = _info["stored_label_keys"]


def sign_in_service(service_id):
    """The core descriptor of a sign-in service (labels in both languages, abbreviation, usage page)."""
    return next(row for row in core_catalog("sign_in_services")["services"] if row["id"] == service_id)


def sign_in_provider_groups(groups, sign_in):
    """Place the signed-in services' groups first, in the core descriptor's order, then `groups` as given."""
    return core_catalog("provider_groups", groups=groups, sign_in=sign_in)["groups"]


def internal_model(record):
    return core_catalog("internal", model=record)["model"]


DEFAULT_OPENAI_MODELS = _info["defaults"]["openai"]
DEFAULT_ANTHROPIC_MODELS = _info["defaults"]["anthropic"]
DEFAULT_GEMINI_MODELS = _info["defaults"]["gemini"]
VERIFIED_NVIDIA_MODELS = _info["defaults"]["nvidia"]
VERIFIED_OLLAMA_LOCAL_MODELS = _info["defaults"]["ollama"]
VERIFIED_OLLAMA_CLOUD_MODELS = _info["defaults"]["ollama-cloud"]
