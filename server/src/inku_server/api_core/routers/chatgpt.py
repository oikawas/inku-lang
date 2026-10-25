"""Self-owned SIWC state. No OAuth secret crosses the LAN HTTP API."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from ... import chatgpt_runtime as runtime
from ...chatgpt_auth import USAGE_URL, attempts, delete_profile, sign_out
from ...chatgpt_models import save_publication, saved_publication
from ...chatgpt_provider import catalog, pin
from ...chatgpt_store import ChatGPTError, CredentialStore
from ..deps import _current_user

router = APIRouter(prefix="/api/me/chatgpt")


def _error(error: ChatGPTError) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": error.code, "action": error.action})


def owner(actor: dict = Depends(_current_user)) -> str:
    try:
        runtime.check_owner(actor["id"])
    except ChatGPTError as error:
        raise _error(error) from None
    return actor["id"]


@router.get("", summary="Read ChatGPT plan connection state")
def state(actor: dict = Depends(_current_user)) -> dict:
    """Return the signed-in user's ChatGPT plan state.

    The result holds `available` and `reason` (set when the feature is unavailable), `self_hosted`,
    `usage_url`, `active_profile_id`, `profiles` and `pending_registrations`. A profile's `state` is
    `connected`, `quota` (paused by a usage limit) or `signed_out`. An ownership failure is reported
    as `available: false` with the error code in `reason`, not as an HTTP error.
    """
    available, reason = runtime.availability()
    try:
        if available:
            runtime.check_owner(actor["id"])
        value = CredentialStore().public_state(actor["id"]) if available else {"active_profile_id": None, "profiles": [], "pending_registrations": []}
    except ChatGPTError as error:
        available, reason = False, error.code
        value = {"active_profile_id": None, "profiles": [], "pending_registrations": []}
    return {"available": available, "reason": reason, "self_hosted": bool(runtime._startup and runtime._startup.self_hosted),
            "usage_url": USAGE_URL, **value}


class AuthorizeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str | None = Field(
        default=None,
        max_length=128,
        description="Id of an existing plan to reconnect, or null to connect a new plan. An id not registered for the user is rejected with 403.",
    )
    consent: bool = Field(
        default=False,
        description="Whether ChatGPT's sign-in page shows its consent prompt. Defaults to false.",
    )
    language: Literal["ja", "en"] = Field(
        default="en",
        description="Language of the sign-in page, `ja` or `en`. Defaults to `en`.",
    )


@router.post("/authorize", summary="Start connecting a ChatGPT plan")
def authorize(body: AuthorizeBody, actor: str = Depends(owner)) -> dict:
    """Begin connecting a ChatGPT plan and return the connection attempt to poll.

    On a self-hosted server this returns status `local_authorization_required` with action
    `local_helper`. The `helper_target` field is added when INKU_CHATGPT_HELPER_TARGET is `container`.
    Returns 403 with an error code when another connection attempt is pending
    (`chatgpt_attempt_busy`) or the profile is not registered (`chatgpt_not_connected`). A declined
    consent is reported later, as status `failed` with code `chatgpt_consent_declined`, by
    GET /attempts/{attempt_id}.
    """
    if runtime._startup and runtime._startup.self_hosted:
        return {"status": "local_authorization_required", "action": "local_helper",
                **({"helper_target": "container"} if os.getenv("INKU_CHATGPT_HELPER_TARGET") == "container" else {})}
    try:
        return attempts.begin(actor, body.profile_id, body.consent, lambda: runtime.check_owner(actor), language=body.language)
    except ChatGPTError as error:
        raise _error(error) from None


@router.get("/attempts/{attempt_id}", summary="Get a connection attempt")
def attempt(
    attempt_id: str = Path(..., description="Id of the connection attempt returned by authorize."),
    actor: str = Depends(owner),
) -> dict:
    """Return the `id`, `status`, `code` and `profile_id` of one connection attempt of the signed-in user.

    Returns 403 when the attempt does not exist or belongs to another user.
    """
    try:
        return attempts.public(actor, attempt_id)
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/attempts/{attempt_id}/cancel", summary="Cancel a connection attempt")
def cancel(
    attempt_id: str = Path(..., description="Id of the connection attempt to cancel."),
    actor: str = Depends(owner),
) -> dict:
    """Cancel a pending connection attempt and return its resulting status.

    An attempt that is no longer pending is returned unchanged. Returns 403 when the attempt does
    not exist or belongs to another user.
    """
    try:
        return attempts.cancel(actor, attempt_id)
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/select", summary="Make a ChatGPT plan the active one")
def select(
    profile_id: str = Path(..., description="Id of the ChatGPT plan profile to make active."),
    actor: str = Depends(owner),
) -> dict:
    """Make a registered ChatGPT plan the active one and return the updated plan state.

    Returns 403 with `chatgpt_not_connected` when the profile is not registered for the user.
    """
    store = CredentialStore()
    try:
        with store.lock("edit:" + actor, time.monotonic() + 5):
            value = store.read(actor)
            if profile_id not in value["profiles"]:
                raise ChatGPTError("chatgpt_not_connected")
            value["active"] = profile_id
            store.write(actor, value)
        return state({"id": actor})
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/sign-out", summary="Sign out a ChatGPT plan")
def disconnect(
    profile_id: str = Path(..., description="Id of the ChatGPT plan profile to sign out."),
    actor: str = Depends(owner),
) -> dict:
    """Sign out one ChatGPT plan, removing its stored tokens and ending its session.

    Returns the sign-out result, including whether revocation was confirmed. Returns 403 when the
    profile is not registered for the user.
    """
    try:
        return asyncio.run(sign_out(actor, profile_id))
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/delete", summary="Delete a ChatGPT plan registration")
def delete(
    profile_id: str = Path(..., description="Id of the ChatGPT plan profile to delete."),
    actor: str = Depends(owner),
) -> dict:
    """Sign out one ChatGPT plan, then remove its registration and its saved model settings.

    A connected plan is signed out first, as by sign-out. When the deleted plan was the active one,
    no plan is active afterwards. Returns the result, including whether revocation was confirmed.
    Returns 403 when the profile is not registered for the user, or with `chatgpt_session_changed`
    when it was reconnected while being deleted.
    """
    try:
        return asyncio.run(delete_profile(actor, profile_id))
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/retry",summary="Retry a ChatGPT plan paused by its usage limit")
def retry(
    profile_id: str = Path(..., description="Id of the ChatGPT plan profile to resume."),
    actor: str = Depends(owner),
) -> dict:
    """Resume a ChatGPT plan that a usage limit had paused, returning it to `connected`.

    Only a profile in the `quota` state can be retried. Any other profile, or an unknown one, is
    rejected with 403 and `chatgpt_not_connected`. Returns the updated plan state.
    """
    store = CredentialStore()
    try:
        with store.lock("edit:" + actor, time.monotonic() + 5):
            value = store.read(actor)
            profile = value["profiles"].get(profile_id)
            if not profile or profile["state"] != "quota":
                raise ChatGPTError("chatgpt_not_connected")
            profile["state"] = "connected"
            store.write(actor, value)
        return state({"id": actor})
    except ChatGPTError as error:
        raise _error(error) from None


def models(actor: str, *, force: bool = False) -> dict:
    try:
        profile_id, generation = pin(actor)
        asyncio.run(catalog(actor, profile_id, generation, time.monotonic() + 15, force=force))
        return saved_publication(actor, profile_id, generation)
    except ChatGPTError as error:
        raise _error(error) from None
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError):
        raise HTTPException(status_code=503, detail={"code": "chatgpt_transport_unavailable", "action": "retry"}) from None


@router.get("/models", summary="Get the model list of the active ChatGPT plan")
def get_models(actor: str = Depends(owner)) -> dict:
    """Return the model list of the active ChatGPT plan with its saved publication settings.

    The list is fetched from ChatGPT only when it is not already cached. Returns 403 for ownership
    or session errors, including an unreachable sign-in service (`chatgpt_auth_unavailable`). Returns
    503 when the model list request itself cannot reach ChatGPT.
    """
    return models(actor)


@router.post("/models/refresh", summary="Refresh the ChatGPT model list")
def refresh_models(actor: str = Depends(owner)) -> dict:
    """Fetch the model list of the active ChatGPT plan from ChatGPT again, ignoring the cache.

    Returns the same result and error statuses as the model list: 403 for ownership or session
    errors, including an unreachable sign-in service, and 503 when the model list request itself
    cannot reach ChatGPT.
    """
    return models(actor, force=True)


class PublishedModelsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(
        min_length=1,
        max_length=128,
        description="Id of the active ChatGPT plan profile the settings are saved for. Rejected with 403 when it is no longer the active plan.",
    )
    generation: int = Field(
        ge=1,
        description="Sign-in generation of the profile the settings were read under, from 1. Rejected with 403 when it no longer matches the profile.",
    )
    published_models: list[Annotated[str, Field(min_length=1, max_length=256)]] | None = Field(
        default=None,
        max_length=1024,
        description="Model ids to publish, each 1 to 256 characters and at most 1,024 ids. Each must be in the plan's offered list. Null leaves the published selection unchanged.",
    )
    model_purposes: dict[Annotated[str, Field(min_length=1, max_length=256)], list[Literal["llm", "vision"]]] | None = Field(
        default=None,
        description="For each offered model id, the purposes it is published for, from `llm` and `vision`. The listed models' purposes are replaced and the others are kept. Null leaves the stored purposes unchanged.",
    )


@router.get("/models/settings", summary="Get saved model publication settings")
def model_settings(actor: str = Depends(owner)) -> dict:
    """Return the saved model publication settings of the active ChatGPT plan.

    This does not contact ChatGPT. Returns 403 for ownership or session errors.
    """
    try:
        profile_id, generation = pin(actor)
        return saved_publication(actor, profile_id, generation)
    except ChatGPTError as error:
        raise _error(error) from None


@router.put("/models/settings", summary="Save published models for the active ChatGPT plan")
def publish_models(body: PublishedModelsBody, actor: str = Depends(owner)) -> dict:
    """Save which models are published for the active ChatGPT plan, and their purposes.

    Returns the saved settings. Returns 403 when a model is not in the plan's offered list, when the
    profile is no longer the active plan, or when its sign-in generation has changed.
    """
    try:
        # Assessments are shared model settings now, saved through /api/settings/models.
        return save_publication(actor, body.profile_id, body.generation, body.published_models, body.model_purposes)
    except ChatGPTError as error:
        raise _error(error) from None
