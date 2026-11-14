"""Personal publication preferences, separate from the shared API-key registry.

What a Sign in with ChatGPT model is -- its recommendation, cost, speed, comments and
the purposes it was measured not to answer -- is shared model settings, the same
for every subscriber and kept in the same keys as every other provider's (the
author, 2026-10-13). Which of the offered models a person publishes, and for
what, stays in that person's registration.
"""

from __future__ import annotations

import time

from .chatgpt_runtime import check_session
from .chatgpt_store import ChatGPTError, CredentialStore
from .verified_model_catalog import sign_in


def shared_assessments() -> dict[str, dict]:
    """The administration's assessments of Sign in with ChatGPT models, read at each use."""
    from . import db
    from .model_settings import chatgpt_assessments
    return chatgpt_assessments(db.get_model_settings())


def offered(models: list[dict], model: str, purpose: str) -> bool:
    """Whether a published model may be used for a purpose: the core's answer."""
    return sign_in("offered", models=models, model=model, purpose=purpose)["offered"]


def publication(profile: dict, models: list[dict] | None = None) -> dict:
    return sign_in("publication", profile=profile, models=models,
                        assessments=shared_assessments())["publication"]


def saved_publication(owner: str, profile_id: str, generation: int) -> dict:
    # Opening model settings never starts an external catalog or token refresh.
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        result = sign_in("auth_publication_active", active=store.read(owner)["active"], profile_id=profile_id)
        if "error" in result:
            raise ChatGPTError(result["error"])
        return publication(profile)


def save_publication(owner: str, profile_id: str, generation: int, selected: list[str] | None,
                     model_purposes: dict[str, list[str]] | None = None) -> dict:
    checked = sign_in("auth_publication_input", profile_id=profile_id, generation=generation,
                           selected=selected, model_purposes=model_purposes)
    if "error" in checked:
        raise ChatGPTError(checked["error"])
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        saved = store.read(owner)
        result = sign_in("auth_publication_active", active=saved["active"], profile_id=profile_id)
        if "error" in result:
            raise ChatGPTError(result["error"])
        result = sign_in("publication_update", profile=profile, selected=selected,
                              model_purposes=model_purposes, assessments={})
        if "error" in result:
            raise ChatGPTError(result["error"])
        if selected is not None:
            result = sign_in("publication_update", profile=profile, selected=selected,
                                  model_purposes=model_purposes, assessments=shared_assessments())
            if "error" in result:
                raise ChatGPTError(result["error"])
        profile = result["profile"]
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
        return publication(profile)
