"""Server-side model provider settings.

API keys are stored only in server app settings and are never returned to the
browser. The UI receives masked status fields.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .secrets import decrypt_secret, encrypt_secret
from .verified_model_catalog import (
    MODEL_CONFIG_VERSION,
    VERIFIED_NVIDIA_MODELS,
    VERIFIED_OLLAMA_CLOUD_MODELS,
    VERIFIED_OLLAMA_LOCAL_MODELS,
)

# Every recommendation key, named once. Three places have to agree about them --
# the normalizer's receiving end, the metadata refresh a catalog version bump
# triggers, and the set carried across a live model-list fetch (api.py) -- and a
# key added to only some of them is lost in whichever path was missed, without
# anything failing.
#
# The stage keys refine recommendation_llm rather than replacing it. A model
# measured end to end -- every NVIDIA and Ollama Cloud entry -- has one number and
# both stages read it, so adding these migrated nothing. They exist because the
# local Ollama models were measured per stage and the two stages disagree: the
# pair inku recommends is a Stage 1 model that covers 32% of Stage 2 and a Stage 2
# model that breaks Stage 1 in English. One number cannot say that.
MODEL_RECOMMENDATION_KEYS = (
    "recommendation_llm",
    "recommendation_vision",
    "recommendation_stage1",
    "recommendation_stage2",
    "recommendation_level",
)
MODEL_METADATA_KEYS = (
    "purposes",
    *MODEL_RECOMMENDATION_KEYS,
    "speed_class",
    "speed_label",
    "comment_ja",
    "comment_en",
)

PROVIDER_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI API Platform",
        "kind": "openai_compatible",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "default_base_url": "https://api.openai.com/v1",
        "requires_api_key": True,
        "models": [
            {"id": "gpt-5.1", "label": "GPT-5.1"},
            {"id": "gpt-5.1-mini", "label": "GPT-5.1 mini"},
            {"id": "gpt-4.1", "label": "GPT-4.1"},
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
        ],
    },
    {
        "id": "anthropic",
        "label": "Claude API",
        "kind": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_base_url": "https://api.anthropic.com",
        "requires_api_key": True,
        "models": [
            {"id": "claude-opus-4-7", "label": "Claude Opus 4.7"},
            {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ],
    },
    {
        "id": "gemini",
        "label": "Gemini API",
        "kind": "gemini",
        "api_key_env": "GEMINI_API_KEY",
        "base_url_env": "GEMINI_BASE_URL",
        "default_base_url": "https://generativelanguage.googleapis.com",
        "requires_api_key": True,
        "models": [
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite"},
        ],
    },
    {
        "id": "nvidia",
        "label": "NVIDIA NIM",
        "kind": "openai_compatible",
        "developer_only": True,
        "api_key_env": "NVIDIA_API_KEY",
        "base_url_env": "NVIDIA_BASE_URL",
        "default_base_url": "https://integrate.api.nvidia.com/v1",
        "requires_api_key": True,
        "models": VERIFIED_NVIDIA_MODELS,
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "kind": "openai_compatible",
        "api_key_env": "OLLAMA_API_KEY",
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "http://localhost:11434/v1",
        "requires_api_key": False,
        # Tags name the quantization. A bare tag is a moving target upstream, and the
        # measurements behind these entries were taken against one build of one file.
        "models": VERIFIED_OLLAMA_LOCAL_MODELS,
        # Speed was taken out of what a release presents (decided 2026-07-27: there is
        # no GPU here, so there is no speed to promise). The numbers are still worth
        # having while experimenting locally, and they were measured on one machine
        # that no one else is running, so they are shown in developer mode only.
        "speed_developer_only": True,
    },
    {
        "id": "ollama-cloud",
        "label": "Ollama Cloud (ollama.com)",
        "kind": "openai_compatible",
        "api_key_env": "OLLAMA_CLOUD_API_KEY",
        "base_url_env": "OLLAMA_CLOUD_BASE_URL",
        "default_base_url": "https://ollama.com/v1",
        "requires_api_key": True,
        # The free tier refuses work by concurrency rather than by volume: eight
        # simultaneous requests returned 429 while only 7.6% of the weekly allowance
        # had been spent (measured 2026-07-27). Two is a property of the service, not
        # a taste, so it is fixed here instead of being offered as a setting.
        "max_concurrency": 2,
        "models": VERIFIED_OLLAMA_CLOUD_MODELS,
        # Same reason as local Ollama, for a different cause: there the machine is
        # nobody else's, here the queue is everybody's. The same request to the same
        # model ran 1.2 and 110 seconds on one day (2026-07-27), and gemma4:31b's
        # median moved 11s -> 105s -> 35s across three runs of the same four cases
        # on 2026-07-29. The numbers are worth having while measuring and are not a
        # promise to anyone else, so a release does not show them.
        "speed_developer_only": True,
    },
]

BUILTIN_PROVIDER_IDS = {str(provider["id"]) for provider in PROVIDER_DEFINITIONS}
_BUILTIN_PROVIDER_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}

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
RETIRED_PROVIDER_IDS = {"ovms"}
_OPENAI_LEGACY_LOCAL_BASE_URLS = {
    "http://127.0.0.1:18000/v3",
    "http://localhost:18000/v3",
    "http://localhost:8000/v3",
}


def _normalize_provider_base_url(provider_id: str, value: str) -> str:
    base_url = value.strip().rstrip("/")
    if provider_id == "openai" and base_url in _OPENAI_LEGACY_LOCAL_BASE_URLS:
        return str(_BUILTIN_PROVIDER_BY_ID["openai"]["default_base_url"])
    return base_url


def _normalize_provider_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"})


def _normalize_provider_kind(value: Any) -> str:
    return str(value) if value in {"openai_compatible", "anthropic", "gemini"} else "openai_compatible"


def _normalize_models(models: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(models, list):
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            item = {"id": model_id, "label": str(model.get("label") or model_id).strip() or model_id}
            if isinstance(model.get("notes"), str) and model["notes"].strip():
                item["notes"] = model["notes"].strip()
            purposes = model.get("purposes")
            if isinstance(purposes, list):
                clean_purposes = [purpose for purpose in ("llm", "vision") if purpose in purposes]
            else:
                marker = f"{model_id} {item.get('notes', '')}".lower()
                clean_purposes = ["vision"] if "vision" in marker else ["llm"]
            if not clean_purposes:
                clean_purposes = ["llm"]
            item["purposes"] = clean_purposes
            # v1.98: 推奨度は用途ごとに持つ。LLM は「3 回成功したか・スキーマを壊さないか・
            # 補正発火が少ないか」、Vision は画像特徴の再現率で決まり、尺度が異なるため。
            # 旧 recommendation_level は用途別の値が無いときだけ読む (書き出しはしない)。
            legacy = model.get("recommendation_level")
            for key in ("recommendation_llm", "recommendation_vision"):
                purpose = "llm" if key == "recommendation_llm" else "vision"
                value = model.get(key)
                if not isinstance(value, int) or isinstance(value, bool):
                    value = legacy if purpose in clean_purposes else None
                if isinstance(value, int) and not isinstance(value, bool):
                    item[key] = max(1, min(5, value))
            # Stage levels have no purpose of their own -- they narrow the LLM
            # level -- so they are read straight through with no legacy fallback.
            # Absent means "not measured for that stage", which the picker shows
            # as an em dash; it must not be filled in with a 0 or with the other
            # stage's number.
            for key in ("recommendation_stage1", "recommendation_stage2"):
                value = model.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    item[key] = max(1, min(5, value))
            for key in ("speed_class", "speed_label", "comment_ja", "comment_en", "eol_date"):
                value = model.get(key)
                if isinstance(value, str) and value.strip():
                    item[key] = value.strip()
            # v1.98: 提供終了 (EOL) の印。新規描画では選べないが一覧には残す。
            if model.get("eol") is True:
                item["eol"] = True
            # 提供元の有料プランでしか叩けないモデルの印。EOL とは別の理由で選べない
            # (退役したのではなく、こちらの契約が届いていない)。一覧には残す — 消すと
            # 契約を変えたときに戻す作業が要るうえ、存在自体が見えなくなる。
            if model.get("requires_subscription") is True:
                item["requires_subscription"] = True
            normalized.append(item)
    return normalized


def default_model_settings() -> dict[str, Any]:
    return {
        "model_catalog_version": MODEL_CONFIG_VERSION,
        "providers": {
            str(provider["id"]): {
                "id": provider["id"],
                "label": provider["label"],
                "kind": provider["kind"],
                "api_key_env": provider["api_key_env"],
                "base_url_env": provider["base_url_env"],
                "default_base_url": provider["default_base_url"],
                "requires_api_key": provider["requires_api_key"],
                "memo": "",
                "models": _normalize_models(deepcopy(provider["models"])),
                "builtin": True,
                "active": True,
                "base_url": _normalize_provider_base_url(
                    str(provider["id"]),
                    os.getenv(str(provider["base_url_env"]), str(provider["default_base_url"])),
                ),
                "api_key": os.getenv(str(provider["api_key_env"]), ""),
                "enabled_models": {str(model["id"]): True for model in provider["models"]},
            }
            for provider in PROVIDER_DEFINITIONS
        },
    }


def default_user_model_settings() -> dict[str, Any]:
    return {
        "stage1_provider": "nvidia",
        "stage1_model": "google/gemma-4-31b-it",
        "stage2_provider": "nvidia",
        "stage2_model": "google/gemma-4-31b-it",
        "vision_provider": "nvidia",
        "vision_model": "meta/llama-3.2-90b-vision-instruct",
        # v2.9.1: okugaki used to keep one qualified string while every other
        # stage kept a (provider, model) pair. The pair is the canonical form;
        # the single string is still read (see normalize_user_model_settings).
        "okugaki_provider": "nvidia",
        "okugaki_model": "meta/llama-3.2-90b-vision-instruct",
        "model_inspection_selected_models": [],
        "instruction_caption_visible": True,
        # The colour catalogue the user draws with. "auto" is not a catalogue:
        # it asks the server to read each description (see color_selector).
        "color_catalog_id": "default",
    }


def normalize_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    default = default_model_settings()
    if not isinstance(settings, dict):
        return default
    clean = deepcopy(default)
    incoming_catalog_version = str(settings.get("model_catalog_version") or "")
    providers = settings.get("providers")
    if isinstance(providers, dict):
        for raw_provider_id, incoming in providers.items():
            provider_id = _normalize_provider_id(raw_provider_id)
            if not provider_id or not isinstance(incoming, dict):
                continue
            if provider_id in RETIRED_PROVIDER_IDS:
                continue
            builtin = _BUILTIN_PROVIDER_BY_ID.get(provider_id)
            provider = clean["providers"].get(provider_id) or {
                "id": provider_id,
                "label": provider_id,
                "kind": "openai_compatible",
                "api_key_env": "",
                "base_url_env": "",
                "default_base_url": "",
                "requires_api_key": False,
                "memo": "",
                "models": [],
                "builtin": False,
                "active": True,
                "base_url": "",
                "api_key": "",
                "enabled_models": {},
            }
            if isinstance(incoming.get("delete"), bool) and incoming["delete"]:
                if provider.get("builtin"):
                    provider["active"] = False
                    clean["providers"][provider_id] = provider
                else:
                    clean["providers"].pop(provider_id, None)
                continue
            if incoming.get("active") is not None:
                provider["active"] = bool(incoming["active"])
            elif provider_id not in clean["providers"]:
                provider["active"] = True
            if isinstance(incoming.get("label"), str) and incoming["label"].strip():
                provider["label"] = incoming["label"].strip()
            elif builtin:
                provider["label"] = builtin["label"]
            if incoming.get("kind") is not None:
                provider["kind"] = _normalize_provider_kind(incoming["kind"])
            if isinstance(incoming.get("api_key_env"), str):
                provider["api_key_env"] = incoming["api_key_env"].strip()
            if isinstance(incoming.get("base_url_env"), str):
                provider["base_url_env"] = incoming["base_url_env"].strip()
            if isinstance(incoming.get("default_base_url"), str) and incoming["default_base_url"].strip():
                provider["default_base_url"] = _normalize_provider_base_url(provider_id, incoming["default_base_url"])
            if incoming.get("requires_api_key") is not None:
                provider["requires_api_key"] = bool(incoming["requires_api_key"])
            if isinstance(incoming.get("memo"), str):
                provider["memo"] = incoming["memo"].strip()
            models = _normalize_models(incoming.get("models"))
            if models:
                # A stored list is the installation's own -- it may name models pulled
                # locally that no catalog knows -- so it decides which models exist.
                # What it must not do is outlive a catalog whose measurements changed:
                # the stored copy carries whatever metadata was current when it was
                # written, and a list refreshed from a live endpoint carries none at
                # all (pentala's Ollama entries held id, label and purposes only). So
                # on a catalog version bump the builtin metadata is laid back over the
                # matching ids, which is the whole reason MODEL_CONFIG_VERSION exists.
                catalog_moved = incoming_catalog_version != MODEL_CONFIG_VERSION
                builtin_by_id = {str(model["id"]): model for model in provider["models"]}
                if builtin and (provider_id == "nvidia" or catalog_moved):
                    metadata_keys = MODEL_METADATA_KEYS
                    # NVIDIA additionally keeps builtin-only models the stored list has
                    # dropped, because artworks name them and a dropped id would leave
                    # those artworks labelless.
                    merged = dict(builtin_by_id) if provider_id == "nvidia" else {}
                    for model in models:
                        model_id = str(model["id"])
                        combined = {**builtin_by_id.get(model_id, {}), **model}
                        if catalog_moved and model_id in builtin_by_id:
                            combined.update({
                                key: builtin_by_id[model_id][key]
                                for key in metadata_keys if key in builtin_by_id[model_id]
                            })
                        merged[model_id] = combined
                    provider["models"] = list(merged.values())
                else:
                    provider["models"] = models
            if not provider.get("default_base_url") and provider.get("base_url"):
                provider["default_base_url"] = provider["base_url"]
            known_model_ids = {str(model["id"]) for model in provider["models"]}
            provider["enabled_models"] = {
                model_id: bool((provider.get("enabled_models") or {}).get(model_id, True))
                for model_id in known_model_ids
            }
            if isinstance(incoming.get("base_url"), str) and incoming["base_url"].strip():
                provider["base_url"] = _normalize_provider_base_url(provider_id, incoming["base_url"])
            if isinstance(incoming.get("api_key"), str):
                provider["api_key"] = incoming["api_key"]
            enabled_models = incoming.get("enabled_models")
            if isinstance(enabled_models, dict):
                for model_id, enabled in enabled_models.items():
                    if model_id in known_model_ids:
                        provider["enabled_models"][model_id] = bool(enabled)
            clean["providers"][provider_id] = provider
    return clean


def _normalize_selected_model_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    clean: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        model_id = item.strip()
        if not model_id or model_id in seen:
            continue
        clean.append(model_id)
        seen.add(model_id)
        if len(clean) >= 4:
            break
    return clean


# "auto" sits in the same slot as a catalog id but is not one: it asks the paint
# endpoint to read the description (catalog_mode=auto).  Anything else has to be
# a catalog that still exists -- a retired id would be stored only to answer 422
# on the next drawing.
AUTO_COLOR_CATALOG_ID = "auto"


def _normalize_catalog_choice(value: Any) -> str:
    from .color_catalogs import DEFAULT_COLOR_CATALOG_ID, color_catalog_ids

    if not isinstance(value, str):
        return DEFAULT_COLOR_CATALOG_ID
    choice = value.strip()
    if choice == AUTO_COLOR_CATALOG_ID or choice in color_catalog_ids():
        return choice
    return DEFAULT_COLOR_CATALOG_ID


_USER_PROVIDER_KEYS = ("stage1_provider", "stage2_provider", "vision_provider", "okugaki_provider")
_USER_MODEL_KEYS = ("stage1_model", "stage2_model", "vision_model", "okugaki_model")


def normalize_user_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    default = default_user_model_settings()
    if not isinstance(settings, dict):
        return default
    clean = dict(default)
    for key in _USER_PROVIDER_KEYS:
        if isinstance(settings.get(key), str) and settings[key].strip():
            clean[key] = str(settings[key])
    for key in _USER_MODEL_KEYS:
        if isinstance(settings.get(key), str) and settings[key].strip():
            clean[key] = settings[key].strip()
    # v2.9.1: read both shapes, write the pair. Values stored before the pair
    # existed carry the provider inside okugaki_model ("openai:gpt-4.1-mini").
    # The prefix is authoritative when present because it is what the picker
    # actually wrote. Only builtin provider ids are recognised here: this
    # function is called once per user row and must not read the stored
    # catalog. A custom provider's qualified value simply stays a single
    # string, which qualify_model_ref() then leaves alone.
    okugaki_prefix, okugaki_bare = split_model_ref(str(clean["okugaki_model"]), None)
    if okugaki_prefix:
        clean["okugaki_provider"] = okugaki_prefix
        clean["okugaki_model"] = okugaki_bare
    clean["model_inspection_selected_models"] = _normalize_selected_model_ids(settings.get("model_inspection_selected_models"))
    clean["instruction_caption_visible"] = settings.get("instruction_caption_visible") is not False
    clean["color_catalog_id"] = _normalize_catalog_choice(settings.get("color_catalog_id"))
    return clean


def update_user_model_settings(current: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_user_model_settings(current)
    for key in _USER_PROVIDER_KEYS:
        if isinstance(patch.get(key), str) and patch[key].strip():
            clean[key] = str(patch[key])
    for key in _USER_MODEL_KEYS:
        if isinstance(patch.get(key), str) and patch[key].strip():
            clean[key] = patch[key].strip()
    if "instruction_caption_visible" in patch:
        clean["instruction_caption_visible"] = bool(patch["instruction_caption_visible"])
    if "model_inspection_selected_models" in patch:
        clean["model_inspection_selected_models"] = _normalize_selected_model_ids(patch.get("model_inspection_selected_models"))
    if "color_catalog_id" in patch:
        clean["color_catalog_id"] = _normalize_catalog_choice(patch.get("color_catalog_id"))
    return normalize_user_model_settings(clean)


def model_provider_catalog(
    settings: dict[str, Any] | None = None,
    *,
    include_disabled: bool = True,
    include_developer: bool = True,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    clean = normalize_model_settings(settings)
    catalog: list[dict[str, Any]] = []
    for provider_id, provider in clean["providers"].items():
        if not provider.get("active", True):
            continue
        builtin = _BUILTIN_PROVIDER_BY_ID.get(provider_id)
        if not include_developer and builtin and builtin.get("developer_only"):
            continue
        enabled_models = provider["enabled_models"]
        # Hiding here rather than at the source keeps to what developer mode means:
        # it changes what is shown, never what is stored or which model gets called.
        hide_speed = bool(
            not include_developer and builtin and builtin.get("speed_developer_only")
        )
        models = []
        for model in provider["models"]:
            enabled = bool(enabled_models.get(str(model["id"]), True))
            if purpose and purpose not in model.get("purposes", ["llm"]):
                continue
            if include_disabled or enabled:
                shown = {**model, "enabled": enabled}
                if hide_speed:
                    shown.pop("speed_class", None)
                    shown.pop("speed_label", None)
                models.append(shown)
        catalog.append({
            "id": provider["id"],
            "label": provider["label"],
            "kind": provider["kind"],
            "api_key_env": provider["api_key_env"],
            "base_url_env": provider["base_url_env"],
            "default_base_url": provider["default_base_url"],
            "requires_api_key": provider["requires_api_key"],
            "builtin": provider.get("builtin", False),
            "active": provider.get("active", True),
            "models": models,
        })
        if include_disabled:
            catalog[-1]["memo"] = str(provider.get("memo") or "")
    return catalog


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


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
    providers: dict[str, dict[str, Any]] = {}
    for provider_id, provider in clean["providers"].items():
        if not provider.get("active", True):
            continue
        builtin = _BUILTIN_PROVIDER_BY_ID.get(provider_id)
        if not include_developer and builtin and builtin.get("developer_only"):
            continue
        stored = clean["providers"][provider_id]
        api_key = decrypt_secret(str(stored.get("api_key") or ""))
        providers[provider_id] = {
            "base_url": stored.get("base_url") or provider["default_base_url"],
            "api_key_set": bool(api_key),
            "api_key_hint": mask_secret(api_key),
            "enabled_models": dict(stored.get("enabled_models") or {}),
        }
    return {"providers": providers}


def update_model_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(current)
    providers = patch.get("providers")
    if isinstance(providers, dict):
        for raw_provider_id, incoming in providers.items():
            provider_id = _normalize_provider_id(raw_provider_id)
            if not isinstance(incoming, dict):
                continue
            if incoming.get("delete") is True:
                if provider_id in BUILTIN_PROVIDER_IDS and provider_id in clean["providers"]:
                    clean["providers"][provider_id]["active"] = False
                else:
                    clean["providers"].pop(provider_id, None)
                continue
            existing = clean["providers"].get(provider_id)
            if not existing:
                clean["providers"][provider_id] = {
                    "id": provider_id,
                    "label": incoming.get("label") or provider_id,
                    "kind": _normalize_provider_kind(incoming.get("kind")),
                    "api_key_env": incoming.get("api_key_env") or "",
                    "base_url_env": incoming.get("base_url_env") or "",
                    "default_base_url": incoming.get("default_base_url") or incoming.get("base_url") or "",
                    "requires_api_key": bool(incoming.get("requires_api_key")),
                    "memo": incoming.get("memo") or "",
                    "models": _normalize_models(incoming.get("models")),
                    "builtin": False,
                    "active": True,
                    "base_url": incoming.get("base_url") or incoming.get("default_base_url") or "",
                    "api_key": "",
                    "enabled_models": {},
                }
            else:
                clean["providers"][provider_id].update({k: v for k, v in incoming.items() if k in {
                    "label", "kind", "api_key_env", "base_url_env", "default_base_url", "requires_api_key", "memo", "models", "active"
                }})
            if isinstance(incoming.get("base_url"), str) and incoming["base_url"].strip():
                clean["providers"][provider_id]["base_url"] = _normalize_provider_base_url(provider_id, incoming["base_url"])
            if incoming.get("clear_api_key") is True:
                clean["providers"][provider_id]["api_key"] = ""
            elif isinstance(incoming.get("api_key"), str) and incoming["api_key"]:
                clean["providers"][provider_id]["api_key"] = incoming["api_key"]
            enabled_models = incoming.get("enabled_models")
            if isinstance(enabled_models, dict):
                known_models = {str(model["id"]) for model in clean["providers"][provider_id].get("models", [])}
                for model_id, enabled in enabled_models.items():
                    if model_id in known_models:
                        clean["providers"][provider_id]["enabled_models"][model_id] = bool(enabled)
    return normalize_model_settings(clean)


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
        return {str(provider_id) for provider_id in settings["providers"]} | RETIRED_PROVIDER_IDS
    return set(BUILTIN_PROVIDER_IDS) | RETIRED_PROVIDER_IDS


def split_model_ref(ref: str, settings: dict[str, Any] | None) -> tuple[str | None, str]:
    """Split "provider:model"; return (None, ref) when it is not qualified.

    _normalize_provider_id keeps only [a-z0-9_-], so a provider id can never
    contain ":". The first colon is therefore the only possible split point and
    the model id is free to carry as many colons as it likes -- "gpt-oss:20b"
    and "qwen3.5:4b-q4_K_M" both survive the round trip.
    """
    text = str(ref or "")
    index = text.find(":")
    if index <= 0:
        return None, text
    head, rest = text[:index], text[index + 1 :]
    if rest and head in _known_provider_ids(settings):
        return head, rest
    return None, text


def qualify_model_ref(provider: str, ref: str, settings: dict[str, Any] | None) -> str:
    """Prefix the provider unless the reference is already qualified.

    The test is "qualified by a known provider", not "starts with my own id",
    so passing a reference that names a different provider leaves it alone
    instead of producing "ollama:ollama-cloud:gemma4:31b".
    """
    clean_provider = str(provider or "").strip()
    clean_ref = str(ref or "").strip()
    if not clean_provider or not clean_ref:
        return clean_ref
    known, _ = split_model_ref(clean_ref, settings)
    return clean_ref if known else f"{clean_provider}:{clean_ref}"


def _providers_owning_model(model_id: str, catalog: dict[str, Any]) -> list[str]:
    owners: list[str] = []
    for provider_id, provider in catalog.get("providers", {}).items():
        if not provider.get("active", True):
            continue
        if any(str(model.get("id")) == model_id for model in provider.get("models", [])):
            owners.append(str(provider_id))
    return owners


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
    stage_key = "stage1_provider" if stage == "stage1" else "stage2_provider"
    if not model:
        clean = normalize_user_model_settings(settings)
        model_id = clean["stage1_model"] if stage == "stage1" else clean["stage2_model"]
        return str(clean[stage_key]), str(model_id)
    catalog = normalize_model_settings(settings)
    provider_id, model_id = split_model_ref(model, catalog)
    if provider_id:
        return provider_id, model_id
    owners = _providers_owning_model(model, catalog)
    if len(owners) == 1:
        return owners[0], model
    return str(normalize_user_model_settings(settings)[stage_key]), model


def provider_concurrency_limit(provider_id: str) -> int:
    """How many requests this provider will take at once. 0 means no limit.

    Read from the builtin definition rather than from stored settings: a provider
    that answers 429 above two simultaneous requests is describing itself, not
    expressing a preference the operator should be able to raise.
    """
    builtin = _BUILTIN_PROVIDER_BY_ID.get(provider_id)
    if not builtin:
        return 0
    limit = builtin.get("max_concurrency")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
        return limit
    return 0


def connection_for(provider_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Where to reach a provider. An unknown id is an error, not a redirection.

    A name nobody configured used to fall through to ovms, which meant a typo or a
    retired reference reached a real endpoint and got a real-looking answer from
    the wrong machine. Raising here is what makes the withdrawal of a provider
    visible at the point of use.
    """
    clean = normalize_model_settings(settings)
    provider = clean["providers"].get(provider_id)
    if not provider:
        raise ValueError(f"unknown model provider: {provider_id}")
    return {
        "id": provider_id,
        "kind": provider["kind"],
        "base_url": provider.get("base_url") or provider["default_base_url"],
        "api_key": decrypt_secret(str(provider.get("api_key") or "")) or os.getenv(str(provider["api_key_env"]), ""),
        "requires_api_key": provider["requires_api_key"],
    }
