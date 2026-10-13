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
from .model_catalog import MODEL_LABELS, model_fold, model_labels


def purposes_for_model(profile: dict, model: str) -> list[str]:
    # Catalogs describe availability; personal purposes remain profile-local.
    return list(profile.get("model_purposes", {}).get(model, ["llm", "vision"]))


def shared_assessments() -> dict[str, dict]:
    """The administration's assessments of ChatGPT plan models, read at each use."""
    from . import db
    from .model_settings import chatgpt_assessments
    return chatgpt_assessments(db.get_model_settings())


def usable_purposes(profile: dict, model: str, assessment: dict) -> list[str]:
    # A purpose the model was measured not to answer is not offered, whatever was ticked.
    unsupported = assessment.get("unsupported_purposes", [])
    return [purpose for purpose in purposes_for_model(profile, model) if purpose not in unsupported]


def publication(profile: dict, models: list[dict] | None = None) -> dict:
    if models is None:
        models = profile.get("catalog", {}).get("models", [])
    selected = set(profile.get("published_models", []))
    assessments = shared_assessments()
    annotated = []
    for model in models:
        assessment = assessments.get(model["id"], {})
        purposes = usable_purposes(profile, model["id"], assessment)
        shared = {key: value for key, value in assessment.items() if key not in ("id", "label")}
        # The labels read the shared assessment, not the person's ticks: a person who
        # publishes a model for neither purpose has not measured it without a response.
        labels = model_labels({**shared, "purposes": [purpose for purpose in ("llm", "vision")
                                                      if purpose not in assessment.get("unsupported_purposes", [])]})
        annotated.append({**model, **shared, "purposes": purposes, "labels": labels, "fold": model_fold(labels),
                          "enabled": model["id"] in selected and bool(purposes) and not assessment.get("not_supported")})
    return {"profile_id": profile["id"], "generation": profile["generation"], "models": annotated,
            "enabled_models": {model["id"]: model["enabled"] for model in annotated},
            "model_labels": [dict(label) for label in MODEL_LABELS]}


def saved_publication(owner: str, profile_id: str, generation: int) -> dict:
    # Opening model settings never starts an external catalog or token refresh.
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        if store.read(owner)["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        return publication(profile)


def save_publication(owner: str, profile_id: str, generation: int, selected: list[str] | None,
                     model_purposes: dict[str, list[str]] | None = None) -> dict:
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        profile = check_session(owner, profile_id, generation)
        saved = store.read(owner)
        if saved["active"] != profile_id:
            raise ChatGPTError("chatgpt_session_changed", action="models")
        offered = {model["id"] for model in profile.get("catalog", {}).get("models", [])}
        if selected is not None and any(model not in offered for model in selected):
            raise ChatGPTError("chatgpt_model_not_offered", action="models")
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
            # A newly published model must have a purpose left after the shared
            # assessment; an older choice it has since emptied is simply not offered.
            assessments = shared_assessments()
            if any(model in offered and (not usable_purposes(profile, model, assessments.get(model, {}))
                                         or assessments.get(model, {}).get("not_supported"))
                   for model in selected):
                raise ChatGPTError("chatgpt_model_not_offered", action="models")
            profile["published_models"] = list(dict.fromkeys(selected))
        saved["profiles"][profile_id] = profile
        store.write(owner, saved)
        return publication(profile)
