"""Server-side model provider settings.

API keys are stored only in server app settings and are never returned to the
browser. The UI receives masked status fields.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from .secrets import decrypt_secret, encrypt_secret

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
        "api_key_env": "NVIDIA_API_KEY",
        "base_url_env": "NVIDIA_BASE_URL",
        "default_base_url": "https://integrate.api.nvidia.com/v1",
        "requires_api_key": True,
        "models": [
            {"id": "google/gemma-4-31b-it", "label": "Google Gemma 4 31B Instruct"},
            {"id": "meta/llama-3.3-70b-instruct", "label": "Meta Llama 3.3 70B Instruct"},
            {"id": "mistralai/mistral-large-2-instruct", "label": "Mistral AI Mistral Large 2 Instruct"},
        ],
    },
    {
        "id": "ollama",
        "label": "Ollama",
        "kind": "openai_compatible",
        "api_key_env": "OLLAMA_API_KEY",
        "base_url_env": "OLLAMA_BASE_URL",
        "default_base_url": "http://localhost:11434/v1",
        "requires_api_key": False,
        "models": [
            {"id": "llama3.2", "label": "Llama 3.2"},
            {"id": "gpt-oss:20b", "label": "gpt-oss 20B"},
            {"id": "qwen3:8b", "label": "Qwen3 8B"},
        ],
    },
    {
        "id": "ovms",
        "label": "Intel OVMS",
        "kind": "openai_compatible",
        "api_key_env": "OVMS_API_KEY",
        "base_url_env": "OVMS_BASE_URL",
        "default_base_url": "http://127.0.0.1:18000/v3",
        "requires_api_key": False,
        "models": [
            {"id": "qwen3-api", "label": "Qwen3 8B Instruct", "notes": "thinking"},
            {"id": "qwen-api", "label": "Qwen2.5 7B Instruct"},
            {"id": "gemma3-12b-api", "label": "Google Gemma 3 12B Instruct"},
            {"id": "gemma3-4b-api", "label": "Google Gemma 3 4B Instruct"},
        ],
    },
]

BUILTIN_PROVIDER_IDS = {str(provider["id"]) for provider in PROVIDER_DEFINITIONS}
_BUILTIN_PROVIDER_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}
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


def _normalize_models(models: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
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
            normalized.append(item)
    return normalized


def default_model_settings() -> dict[str, Any]:
    return {
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
                "models": deepcopy(provider["models"]),
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
        "model_inspection_selected_models": [],
    }


def normalize_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    default = default_model_settings()
    if not isinstance(settings, dict):
        return default
    clean = deepcopy(default)
    providers = settings.get("providers")
    if isinstance(providers, dict):
        for raw_provider_id, incoming in providers.items():
            provider_id = _normalize_provider_id(raw_provider_id)
            if not provider_id or not isinstance(incoming, dict):
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


def normalize_user_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    default = default_user_model_settings()
    if not isinstance(settings, dict):
        return default
    clean = dict(default)
    for key in ("stage1_provider", "stage2_provider"):
        if isinstance(settings.get(key), str) and settings[key].strip():
            clean[key] = str(settings[key])
    for key in ("stage1_model", "stage2_model"):
        if isinstance(settings.get(key), str) and settings[key].strip():
            clean[key] = settings[key].strip()
    clean["model_inspection_selected_models"] = _normalize_selected_model_ids(settings.get("model_inspection_selected_models"))
    return clean


def update_user_model_settings(current: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_user_model_settings(current)
    for key in ("stage1_provider", "stage2_provider"):
        if isinstance(patch.get(key), str) and patch[key].strip():
            clean[key] = str(patch[key])
    for key in ("stage1_model", "stage2_model"):
        if isinstance(patch.get(key), str) and patch[key].strip():
            clean[key] = patch[key].strip()
    if "model_inspection_selected_models" in patch:
        clean["model_inspection_selected_models"] = _normalize_selected_model_ids(patch.get("model_inspection_selected_models"))
    return normalize_user_model_settings(clean)


def model_provider_catalog(settings: dict[str, Any] | None = None, *, include_disabled: bool = True) -> list[dict[str, Any]]:
    clean = normalize_model_settings(settings)
    catalog: list[dict[str, Any]] = []
    for provider_id, provider in clean["providers"].items():
        if not provider.get("active", True):
            continue
        enabled_models = provider["enabled_models"]
        models = []
        for model in provider["models"]:
            enabled = bool(enabled_models.get(str(model["id"]), True))
            if include_disabled or enabled:
                models.append({**model, "enabled": enabled})
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


def public_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    providers: dict[str, dict[str, Any]] = {}
    for provider_id, provider in clean["providers"].items():
        if not provider.get("active", True):
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


def provider_for_model(model: str | None, *, stage: str, settings: dict[str, Any]) -> tuple[str, str]:
    if not model:
        clean = normalize_user_model_settings(settings)
        provider_id = clean["stage1_provider"] if stage == "stage1" else clean["stage2_provider"]
        model_id = clean["stage1_model"] if stage == "stage1" else clean["stage2_model"]
        return str(provider_id), str(model_id)
    if ":" in model:
        prefix, model_id = model.split(":", 1)
        if prefix in normalize_model_settings(settings)["providers"] and model_id:
            return prefix, model_id
    if model.startswith("anthropic:"):
        return "anthropic", model.removeprefix("anthropic:")
    if model.startswith("gemini-"):
        return "gemini", model
    if "/" in model:
        return "nvidia", model
    return "ovms", model


def connection_for(provider_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    provider = clean["providers"].get(provider_id) or clean["providers"].get("ovms")
    if not provider:
        raise ValueError(f"unknown model provider: {provider_id}")
    stored = clean["providers"].get(provider_id, {})
    return {
        "id": provider_id,
        "kind": provider["kind"],
        "base_url": stored.get("base_url") or provider["default_base_url"],
        "api_key": decrypt_secret(str(stored.get("api_key") or "")) or os.getenv(str(provider["api_key_env"]), ""),
        "requires_api_key": provider["requires_api_key"],
    }
