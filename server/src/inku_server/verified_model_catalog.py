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


_info = catalog_info()
MODEL_CATALOG = _info["catalog"]
MODEL_CONFIG_VERSION = _info["version"]
MODEL_CONFIG_LAST_UPDATED = MODEL_CATALOG["updated"]
STORED_LABEL_KEYS = _info["stored_label_keys"]


def internal_model(record):
    return core_catalog("internal", model=record)["model"]


DEFAULT_OPENAI_MODELS = _info["defaults"]["openai"]
DEFAULT_ANTHROPIC_MODELS = _info["defaults"]["anthropic"]
DEFAULT_GEMINI_MODELS = _info["defaults"]["gemini"]
VERIFIED_NVIDIA_MODELS = _info["defaults"]["nvidia"]
VERIFIED_OLLAMA_LOCAL_MODELS = _info["defaults"]["ollama"]
VERIFIED_OLLAMA_CLOUD_MODELS = _info["defaults"]["ollama-cloud"]
