"""Personal publication preferences, separate from the shared API-key registry."""

from __future__ import annotations

import time

from .chatgpt_runtime import check_session
from .chatgpt_store import ChatGPTError, CredentialStore


def publication(profile: dict, models: list[dict] | None = None) -> dict:
    if models is None:
        models = profile.get("catalog", {}).get("models", [])
    selected = set(profile.get("published_models", []))
    annotated = [{**model, "enabled": model["id"] in selected} for model in models]
    return {"profile_id": profile["id"], "generation": profile["generation"], "models": annotated,
            "enabled_models": {model["id"]: model["enabled"] for model in annotated}}


def saved_publication(owner: str, profile_id: str, generation: int) -> dict:
    # Opening model settings never starts an external catalog or token refresh.
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        if store.read(owner)["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        return publication(profile)


def save_publication(owner: str, profile_id: str, generation: int, selected: list[str]) -> dict:
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        saved = store.read(owner)
        if saved["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        offered = {model["id"] for model in profile.get("catalog", {}).get("models", [])}
        if any(model not in offered for model in selected):
            raise ChatGPTError("chatgpt_model_not_offered", action="models")
        profile["published_models"] = list(dict.fromkeys(selected))
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
        return publication(profile)
