"""Server-side model provider settings.

API keys are stored only in server app settings and are never returned to the
browser. The UI receives masked status fields.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

PROVIDER_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI",
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
        "label": "Claude",
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
        "label": "Gemini",
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

PROVIDER_IDS = {str(provider["id"]) for provider in PROVIDER_DEFINITIONS}
_PROVIDER_BY_ID = {str(provider["id"]): provider for provider in PROVIDER_DEFINITIONS}


def default_model_settings() -> dict[str, Any]:
    return {
        "stage1_provider": "nvidia",
        "stage1_model": "google/gemma-4-31b-it",
        "stage2_provider": "nvidia",
        "stage2_model": "google/gemma-4-31b-it",
        "providers": {
            str(provider["id"]): {
                "base_url": os.getenv(str(provider["base_url_env"]), str(provider["default_base_url"])),
                "api_key": os.getenv(str(provider["api_key_env"]), ""),
            }
            for provider in PROVIDER_DEFINITIONS
        },
    }


def normalize_model_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    default = default_model_settings()
    if not isinstance(settings, dict):
        return default
    clean = deepcopy(default)
    if settings.get("stage1_provider") in PROVIDER_IDS:
        clean["stage1_provider"] = settings["stage1_provider"]
    if isinstance(settings.get("stage1_model"), str) and settings["stage1_model"].strip():
        clean["stage1_model"] = settings["stage1_model"].strip()
    if settings.get("stage2_provider") in PROVIDER_IDS:
        clean["stage2_provider"] = settings["stage2_provider"]
    if isinstance(settings.get("stage2_model"), str) and settings["stage2_model"].strip():
        clean["stage2_model"] = settings["stage2_model"].strip()
    providers = settings.get("providers")
    if isinstance(providers, dict):
        for provider_id, provider in _PROVIDER_BY_ID.items():
            incoming = providers.get(provider_id)
            if not isinstance(incoming, dict):
                continue
            if isinstance(incoming.get("base_url"), str) and incoming["base_url"].strip():
                clean["providers"][provider_id]["base_url"] = incoming["base_url"].strip().rstrip("/")
            if isinstance(incoming.get("api_key"), str):
                clean["providers"][provider_id]["api_key"] = incoming["api_key"]
    return clean


def model_provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": provider["id"],
            "label": provider["label"],
            "kind": provider["kind"],
            "api_key_env": provider["api_key_env"],
            "base_url_env": provider["base_url_env"],
            "default_base_url": provider["default_base_url"],
            "requires_api_key": provider["requires_api_key"],
            "models": provider["models"],
        }
        for provider in PROVIDER_DEFINITIONS
    ]


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def public_model_settings(settings: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(settings)
    providers: dict[str, dict[str, Any]] = {}
    for provider_id, provider in _PROVIDER_BY_ID.items():
        stored = clean["providers"][provider_id]
        api_key = str(stored.get("api_key") or "")
        providers[provider_id] = {
            "base_url": stored.get("base_url") or provider["default_base_url"],
            "api_key_set": bool(api_key),
            "api_key_hint": mask_secret(api_key),
        }
    return {
        "stage1_provider": clean["stage1_provider"],
        "stage1_model": clean["stage1_model"],
        "stage2_provider": clean["stage2_provider"],
        "stage2_model": clean["stage2_model"],
        "providers": providers,
    }


def update_model_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    clean = normalize_model_settings(current)
    for key in ("stage1_provider", "stage2_provider"):
        if patch.get(key) in PROVIDER_IDS:
            clean[key] = patch[key]
    for key in ("stage1_model", "stage2_model"):
        if isinstance(patch.get(key), str) and patch[key].strip():
            clean[key] = patch[key].strip()
    providers = patch.get("providers")
    if isinstance(providers, dict):
        for provider_id in PROVIDER_IDS:
            incoming = providers.get(provider_id)
            if not isinstance(incoming, dict):
                continue
            if isinstance(incoming.get("base_url"), str) and incoming["base_url"].strip():
                clean["providers"][provider_id]["base_url"] = incoming["base_url"].strip().rstrip("/")
            if incoming.get("clear_api_key") is True:
                clean["providers"][provider_id]["api_key"] = ""
            elif isinstance(incoming.get("api_key"), str) and incoming["api_key"]:
                clean["providers"][provider_id]["api_key"] = incoming["api_key"]
    return normalize_model_settings(clean)


def provider_for_model(model: str | None, *, stage: str, settings: dict[str, Any]) -> tuple[str, str]:
    clean = normalize_model_settings(settings)
    if not model:
        provider_id = clean["stage1_provider"] if stage == "stage1" else clean["stage2_provider"]
        model_id = clean["stage1_model"] if stage == "stage1" else clean["stage2_model"]
        return str(provider_id), str(model_id)
    if ":" in model:
        prefix, model_id = model.split(":", 1)
        if prefix in PROVIDER_IDS and model_id:
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
    provider = _PROVIDER_BY_ID.get(provider_id) or _PROVIDER_BY_ID["ovms"]
    stored = clean["providers"].get(provider_id, {})
    return {
        "id": provider_id,
        "kind": provider["kind"],
        "base_url": stored.get("base_url") or provider["default_base_url"],
        "api_key": stored.get("api_key") or os.getenv(str(provider["api_key_env"]), ""),
        "requires_api_key": provider["requires_api_key"],
    }
