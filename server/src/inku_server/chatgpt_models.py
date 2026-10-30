"""Personal publication preferences, separate from the shared API-key registry.

What a ChatGPT plan model is -- its recommendation, cost, speed, comments and
the purposes it was measured not to answer -- is shared model settings, the same
for every subscriber and kept in the same keys as every other provider's (the
author, 2026-10-13). Which of the offered models a person publishes, and for
what, stays in that person's registration.
"""

from __future__ import annotations

import time

from .chatgpt_runtime import check_session
from .chatgpt_store import ChatGPTError, CredentialStore
from .verified_model_catalog import core_catalog


def purposes_for_model(profile: dict, model: str) -> list[str]:
    # Catalogs describe availability; personal purposes remain profile-local.
    return core_catalog("chatgpt_usable", profile=profile, model=model, assessment={})["purposes"]


def shared_assessments() -> dict[str, dict]:
    """The administration's assessments of ChatGPT plan models, read at each use."""
    from . import db
    from .model_settings import chatgpt_assessments
    return chatgpt_assessments(db.get_model_settings())


def usable_purposes(profile: dict, model: str, assessment: dict) -> list[str]:
    # A purpose the model was measured not to answer is not offered, whatever was ticked.
    return core_catalog("chatgpt_usable", profile=profile, model=model, assessment=assessment)["purposes"]


def publication(profile: dict, models: list[dict] | None = None) -> dict:
    return core_catalog("chatgpt_publication", profile=profile, models=models,
                        assessments=shared_assessments())["publication"]


def saved_publication(owner: str, profile_id: str, generation: int) -> dict:
    # Opening model settings never starts an external catalog or token refresh.
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        result = core_catalog("chatgpt_auth_publication_active", active=store.read(owner)["active"], profile_id=profile_id)
        if "error" in result:
            raise ChatGPTError(result["error"])
        return publication(profile)


def save_publication(owner: str, profile_id: str, generation: int, selected: list[str] | None,
                     model_purposes: dict[str, list[str]] | None = None) -> dict:
    checked = core_catalog("chatgpt_auth_publication_input", profile_id=profile_id, generation=generation,
                           selected=selected, model_purposes=model_purposes)
    if "error" in checked:
        raise ChatGPTError(checked["error"])
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        saved = store.read(owner)
        result = core_catalog("chatgpt_auth_publication_active", active=saved["active"], profile_id=profile_id)
        if "error" in result:
            raise ChatGPTError(result["error"])
        result = core_catalog("chatgpt_publication_update", profile=profile, selected=selected,
                              model_purposes=model_purposes, assessments={})
        if "error" in result:
            raise ChatGPTError(result["error"])
        if selected is not None:
            result = core_catalog("chatgpt_publication_update", profile=profile, selected=selected,
                                  model_purposes=model_purposes, assessments=shared_assessments())
            if "error" in result:
                raise ChatGPTError(result["error"])
        profile = result["profile"]
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
        return publication(profile)
