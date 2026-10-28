"""Server-side model provider settings.

API keys are stored only in server app settings and are never returned to the
browser. The UI receives masked status fields.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .secrets import decrypt_secret, encrypt_secret
from .verified_model_catalog import core_catalog

# Metadata field sets come from the same core that normalizes and refreshes models.
_PROVIDER_METADATA = core_catalog("provider_metadata")
MODEL_RECOMMENDATION_KEYS = tuple(_PROVIDER_METADATA["recommendation"])
MODEL_MEASUREMENT_KEYS = tuple(_PROVIDER_METADATA["measurement"])
MODEL_METADATA_KEYS = tuple(_PROVIDER_METADATA["metadata"])
CATALOG_MODEL_KEYS = tuple(_PROVIDER_METADATA["catalog"])


def normalize_rate_limits(value: Any, *, provider_id: str = "") -> dict[str, int]:
    return core_catalog("rate_limits", value=value, provider=provider_id)["rate_limits"]


PROVIDER_DEFINITIONS: list[dict[str, Any]] = core_catalog("providers", host="server")["providers"]

BUILTIN_PROVIDER_IDS = {str(provider["id"]) for provider in PROVIDER_DEFINITIONS}

# Providers withdrawn from the catalog. Dropping the definition is not enough to
# remove one from an installation: a provider id the builtin list does not know
# is kept as though the operator had added it by hand (see the fallback branch in
# normalize_model_settings), and the metadata refresh that MODEL_CONFIG_VERSION
# triggers sits inside `if builtin`, so it never reaches it either. So a withdrawn
# id has to be named here and dropped on the way in.
#
# ovms (Intel OpenVINO Model Server) was the local OpenAI-compatible backend
# until 2026-07-30. Its endpoint had stopped serving models while still answering
# /health, and the models it offered are reachable through Ollama instead.
RETIRED_PROVIDER_IDS = {provider["id"] for provider in core_catalog("retired_providers")["providers"]}
def _normalize_models(models: Any) -> list[dict[str, Any]]:
    return core_catalog("normalize_models", models=models)["models"]


def normalize_chatgpt_models(entries: Any) -> list[dict[str, Any]]:
    """The shared assessments of ChatGPT plan models (the author, 2026-10-13).

    A model's measurements are the same for every subscriber, so they are kept
    with the other providers' instead of in each person's registration, in the
    same keys. Which models a person publishes, and for what, stays personal, so
    the purposes are not kept here; the purposes it was measured not to answer are.
    """
    return [{key: value for key, value in model.items() if key != "purposes"} for model in _normalize_models(entries)]


def chatgpt_assessments(settings: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The shared assessment of each ChatGPT plan model, by model id.

    The catalog's `chatgpt` entries, with what an administrator changed since the catalog last
    changed laid over them (see normalize_model_settings).
    """
    entries = normalize_model_settings(settings)["chatgpt_models"]
    return {model["id"]: model for model in entries}


def _settings_environment() -> dict[str, str]:
    names = {str(p[key]) for p in PROVIDER_DEFINITIONS for key in ("api_key_env", "base_url_env")}
    return {name: os.environ[name] for name in names if name in os.environ}


def _ordered_settings(result: dict[str, Any]) -> dict[str, Any]:
    settings = result["settings"]
    providers = settings["providers"]
    settings["providers"] = {key: providers[key] for key in result["order"] if key in providers}
    return settings


def default_model_settings() -> dict[str, Any]:
    return _ordered_settings(core_catalog("default_settings", env=_settings_environment()))


def default_user_model_settings() -> dict[str, Any]:
    return core_catalog("user_defaults")["settings"]


def normalize_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    incoming = settings.get("providers") if isinstance(settings, dict) else None
    order = list(incoming) if isinstance(incoming, dict) else []
    return _ordered_settings(core_catalog("normalize_settings", settings=settings, order=order, env=_settings_environment()))


def _user_catalog_context() -> dict[str, Any]:
    from .color_catalogs import DEFAULT_COLOR_CATALOG_ID, color_catalog_ids
    return {"color_ids": sorted(color_catalog_ids()), "default_color": DEFAULT_COLOR_CATALOG_ID}


def normalize_user_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    return core_catalog("normalize_user", settings=settings, **_user_catalog_context())["settings"]


def update_user_model_settings(current: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    return core_catalog("update_user", settings=current, patch=patch, **_user_catalog_context())["settings"]


def model_provider_catalog(
    settings: dict[str, Any] | None = None,
    *,
    include_disabled: bool = True,
    include_developer: bool = True,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    clean = normalize_model_settings(settings)
    return core_catalog("provider_catalog", settings=clean, order=list(clean["providers"]),
                        include_disabled=include_disabled, include_developer=include_developer,
                        purpose=purpose)["providers"]


def model_is_offered(
    provider_id: str,
    model_id: str,
    settings: dict[str, Any] | None,
    *,
    purpose: str,
) -> bool:
    """Whether an active provider lists this model for `purpose` and it is switched on.

    Developer mode is not asked: it decides what the lists show, never which
    model may be called (see model_provider_catalog), and the built-in Stage
    defaults sit with a provider that only developer mode shows.
    """
    clean = normalize_model_settings(settings)
    return core_catalog("model_offered", settings=clean, order=list(clean["providers"]),
                        provider=provider_id, model=model_id, purpose=purpose)["offered"]


def mask_secret(value: str | None) -> str | None:
    return core_catalog("mask_secret", secret=value)["masked"]


def storage_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    stored = deepcopy(clean)
    for provider in stored.get("providers", {}).values():
        provider["api_key"] = encrypt_secret(str(provider.get("api_key") or ""))
    return stored


def public_model_settings(
    settings: dict[str, Any],
    *,
    include_developer: bool = True,
) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    providers = clean["providers"]
    visible = core_catalog("provider_catalog", settings=clean, order=list(providers),
                           include_disabled=True, include_developer=include_developer, purpose=None)["providers"]
    keys = {provider["id"]: decrypt_secret(str(providers[provider["id"]].get("api_key") or ""))
            for provider in visible}
    result = core_catalog("public_settings", settings=clean, order=list(providers), keys=keys,
                          include_developer=include_developer)["settings"]
    result["providers"] = {key: result["providers"][key] for key in providers if key in result["providers"]}
    return result


def update_model_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    providers = current.get("providers") if isinstance(current, dict) else None
    changes = patch.get("providers") if isinstance(patch, dict) else None
    return _ordered_settings(core_catalog("update_settings", settings=current, patch=patch,
        order=list(providers) if isinstance(providers, dict) else [],
        patch_order=list(changes) if isinstance(changes, dict) else [], env=_settings_environment()))


def _known_provider_ids(settings: dict[str, Any] | None) -> set[str]:
    """Provider ids the reference may be qualified with.

    A dict carrying "providers" is taken as a catalog and read directly rather
    than normalized: normalize_model_settings() deep-copies the whole catalog,
    and splitting a reference only needs the keys.

    Retired ids are recognised too, so "ovms:gemma3-4b-api" -- five artworks carry
    that exact string -- splits into a provider and a model rather than being read
    as one long model id. Recognising the prefix is not offering the provider:
    connection_for() then raises for it, which says what is actually wrong instead
    of asking NVIDIA for a model named "ovms:gemma3-4b-api".
    """
    if isinstance(settings, dict) and isinstance(settings.get("providers"), dict):
        return {str(provider_id) for provider_id in settings["providers"]} | RETIRED_PROVIDER_IDS | {"chatgpt"}
    return set(BUILTIN_PROVIDER_IDS) | RETIRED_PROVIDER_IDS | {"chatgpt"}


def split_model_ref(ref: str, settings: dict[str, Any] | None) -> tuple[str | None, str]:
    """Split "provider:model"; return (None, ref) when it is not qualified.

    _normalize_provider_id keeps only [a-z0-9_-], so a provider id can never
    contain ":". The first colon is therefore the only possible split point and
    the model id is free to carry as many colons as it likes -- "gpt-oss:20b"
    and "qwen3.5:4b-q4_K_M" both survive the round trip.
    """
    result = core_catalog("split_ref", ref=str(ref or ""), providers={key: {} for key in _known_provider_ids(settings)})
    return result["provider"], result["model"]


def qualify_model_ref(provider: str, ref: str, settings: dict[str, Any] | None) -> str:
    """Prefix the provider unless the reference is already qualified.

    The test is "qualified by a known provider", not "starts with my own id",
    so passing a reference that names a different provider leaves it alone
    instead of producing "ollama:ollama-cloud:gemma4:31b".
    """
    return core_catalog("qualify_ref", provider=str(provider or ""), ref=str(ref or ""),
                        providers={key: {} for key in _known_provider_ids(settings)})["ref"]


def provider_for_model(model: str | None, *, stage: str, settings: dict[str, Any]) -> tuple[str, str]:
    """Resolve a model reference to (provider, model). Three rules, no guessing.

    1. explicit qualification wins
    2. sole ownership -- exactly one configured provider lists this model id
    3. the stage default

    Rule 2 must be *exactly* one: "gpt-oss:20b" is offered by both ollama and
    ollama-cloud, so nothing in the string can decide between them and the
    reference falls to rule 3 rather than being guessed. There is deliberately no
    default landing provider: the rules that preceded these sent everything
    unrecognised to one, and it went on answering /health long after it had
    stopped serving models, so an unresolvable reference looked like a working
    one.
    """
    stage_key = "stage1" if stage == "stage1" else "stage2"
    defaults = normalize_user_model_settings(settings)
    catalog = normalize_model_settings(settings)
    result = core_catalog("resolve_ref", ref=str(model or ""), providers=catalog["providers"],
                          default_provider=str(defaults[f"{stage_key}_provider"]),
                          default_model=str(defaults[f"{stage_key}_model"]))
    return result["provider"], result["model"]


def provider_concurrency_limit(provider_id: str) -> int:
    return core_catalog("provider_concurrency", provider=provider_id)["limit"]


def connection_for(provider_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    answer = core_catalog("connection", provider=provider_id, settings=clean)
    if "error" in answer:
        raise ValueError(answer["error"])
    provider = clean["providers"][provider_id]
    answer["connection"]["api_key"] = decrypt_secret(str(provider.get("api_key") or "")) or os.getenv(str(provider["api_key_env"]), "")
    return answer["connection"]
