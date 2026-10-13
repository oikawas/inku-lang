"""The Python face of model_catalog.json, the one catalog of model information.

Every provider's model information -- purposes, recommendations, measured seconds and costs,
comments, and the labels that file a model away (older model, not supported, end of life) -- is
kept in model_catalog.json beside this file, in the common format inku.model-catalog.v2, and
nowhere else (the author, 2026-10-13). The ChatGPT plan's models are in it too. The Server reads
it, the Web gets it through the API, and the macOS and Android apps bundle it. A measurement is
reflected by editing that file. What each figure rests on is in that model's comment; the notes
on method that the Python catalog carried until 2026-10-13 are in this file's git history.

This module keeps the names the Server and apple/scripts/export-server-resources.py have read
since July: the catalog version, and each builtin provider's default models (what a fresh
installation lists) in the Server's own form, where a stored label is a boolean of the same name
(`subscription` is `requires_subscription`). It loads JSON and nothing else, so that script can
still run this file on its own.
"""

import hashlib
import json
from pathlib import Path

MODEL_CATALOG = json.loads(Path(__file__).with_name("model_catalog.json").read_text(encoding="utf-8"))

# Every change to the catalog is laid back over the copy an installation stored (see
# normalize_model_settings), so the version names the content rather than a number someone has to
# remember to raise.
MODEL_CONFIG_VERSION = MODEL_CATALOG["version"] + "+" + hashlib.sha256(
    json.dumps(MODEL_CATALOG, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:12]
MODEL_CONFIG_LAST_UPDATED = MODEL_CATALOG["updated"]

# The labels the Server keeps as booleans, and the boolean each is kept as.
STORED_LABEL_KEYS = {"legacy": "legacy", "subscription": "requires_subscription",
                     "not_supported": "not_supported", "eol": "eol"}


def internal_model(record: dict) -> dict:
    """A catalog entry in the Server's form: each stored label becomes its boolean."""
    model = {key: value for key, value in record.items() if key != "labels"}
    for label in record.get("labels", []):
        model[STORED_LABEL_KEYS[label]] = True
    return model


def _defaults(provider_id: str) -> list[dict]:
    provider = MODEL_CATALOG["providers"][provider_id]
    by_id = {record["id"]: record for record in provider["models"]}
    return [internal_model(by_id[model_id]) for model_id in provider["defaults"]]


DEFAULT_OPENAI_MODELS = _defaults("openai")
DEFAULT_ANTHROPIC_MODELS = _defaults("anthropic")
DEFAULT_GEMINI_MODELS = _defaults("gemini")
VERIFIED_NVIDIA_MODELS = _defaults("nvidia")
VERIFIED_OLLAMA_LOCAL_MODELS = _defaults("ollama")
VERIFIED_OLLAMA_CLOUD_MODELS = _defaults("ollama-cloud")
