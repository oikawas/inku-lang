"""Personal publication preferences, separate from the shared API-key registry."""

from __future__ import annotations

import time

from .chatgpt_runtime import check_session
from .chatgpt_store import ChatGPTError, CredentialStore


def purposes_for_model(profile: dict, model: str) -> list[str]:
    # Catalogs describe availability; personal purposes remain profile-local.
    return list(profile.get("model_purposes", {}).get(model, ["llm", "vision"]))


def publication(profile: dict, models: list[dict] | None = None) -> dict:
    if models is None:
        models = profile.get("catalog", {}).get("models", [])
    selected = set(profile.get("published_models", []))
    metadata = profile.get("model_metadata", {})
    annotated = [{**model, **metadata.get(model["id"], {}), "purposes": purposes_for_model(profile, model["id"]),
                  "enabled": model["id"] in selected} for model in models]
    return {"profile_id": profile["id"], "generation": profile["generation"], "models": annotated,
            "enabled_models": {model["id"]: model["enabled"] for model in annotated},
            "model_metadata": {model["id"]: dict(metadata[model["id"]]) for model in models if model["id"] in metadata}}


def saved_publication(owner: str, profile_id: str, generation: int) -> dict:
    # Opening model settings never starts an external catalog or token refresh.
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        if store.read(owner)["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        return publication(profile)


def save_publication(owner: str, profile_id: str, generation: int, selected: list[str] | None,
                     model_purposes: dict[str, list[str]] | None = None,
                     model_metadata: dict[str, dict | None] | None = None) -> dict:
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        saved = store.read(owner)
        if saved["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        offered = {model["id"] for model in profile.get("catalog", {}).get("models", [])}
        if selected is not None and any(model not in offered for model in selected):
            raise ChatGPTError("chatgpt_model_not_offered", action="models")
        if model_metadata is not None:
            if any(model not in offered for model in model_metadata):
                raise ChatGPTError("chatgpt_model_not_offered", action="models")
            metadata = {model: dict(fields) for model, fields in profile.get("model_metadata", {}).items()}
            for model, patch in model_metadata.items():
                if patch is None:
                    metadata.pop(model, None)
                    continue
                fields = metadata.setdefault(model, {})
                for key, value in patch.items():
                    if value is None:
                        fields.pop(key, None)
                    else:
                        fields[key] = value.strip() if isinstance(value, str) else value
                if not fields:
                    metadata.pop(model, None)
            profile["model_metadata"] = metadata
        if model_purposes is not None:
            if not isinstance(model_purposes, dict) or any(
                model not in offered or not isinstance(purposes, list)
                or any(purpose not in ("llm", "vision") for purpose in purposes)
                for model, purposes in model_purposes.items()
            ):
                raise ChatGPTError("chatgpt_model_not_offered", action="models")
            profile["model_purposes"] = {
                **profile.get("model_purposes", {}),
                **{model: [purpose for purpose in ("llm", "vision") if purpose in purposes]
                   for model, purposes in model_purposes.items()},
            }
        selected_models = selected if selected is not None else profile.get("published_models", [])
        if any(model in offered and not purposes_for_model(profile, model) for model in selected_models):
            raise ChatGPTError("chatgpt_model_not_offered", action="models")
        if selected is not None:
            profile["published_models"] = list(dict.fromkeys(selected))
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
        return publication(profile)
