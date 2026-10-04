"""Self-owned SIWC state. No OAuth secret crosses the LAN HTTP API."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ... import chatgpt_runtime as runtime
from ...chatgpt_auth import USAGE_URL, attempts, sign_out
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


@router.get("")
def state(actor: dict = Depends(_current_user)) -> dict:
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
    profile_id: str | None = Field(default=None, max_length=128)
    consent: bool = False
    language: Literal["ja", "en"] = "en"


@router.post("/authorize")
def authorize(body: AuthorizeBody, actor: str = Depends(owner)) -> dict:
    if runtime._startup and runtime._startup.self_hosted:
        return {"status": "local_authorization_required", "action": "local_helper",
                **({"helper_target": "container"} if os.getenv("INKU_CHATGPT_HELPER_TARGET") == "container" else {})}
    try:
        return attempts.begin(actor, body.profile_id, body.consent, lambda: runtime.check_owner(actor), language=body.language)
    except ChatGPTError as error:
        raise _error(error) from None


@router.get("/attempts/{attempt_id}")
def attempt(attempt_id: str, actor: str = Depends(owner)) -> dict:
    try:
        return attempts.public(actor, attempt_id)
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/attempts/{attempt_id}/cancel")
def cancel(attempt_id: str, actor: str = Depends(owner)) -> dict:
    try:
        return attempts.cancel(actor, attempt_id)
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/select")
def select(profile_id: str, actor: str = Depends(owner)) -> dict:
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


@router.post("/profiles/{profile_id}/sign-out")
def disconnect(profile_id: str, actor: str = Depends(owner)) -> dict:
    try:
        return asyncio.run(sign_out(actor, profile_id))
    except ChatGPTError as error:
        raise _error(error) from None


@router.post("/profiles/{profile_id}/retry")
def retry(profile_id: str, actor: str = Depends(owner)) -> dict:
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


@router.get("/models")
def get_models(actor: str = Depends(owner)) -> dict:
    return models(actor)


@router.post("/models/refresh")
def refresh_models(actor: str = Depends(owner)) -> dict:
    return models(actor, force=True)


class PublishedModelsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    published_models: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(max_length=1024)


@router.get("/models/settings")
def model_settings(actor: str = Depends(owner)) -> dict:
    try:
        profile_id, generation = pin(actor)
        return saved_publication(actor, profile_id, generation)
    except ChatGPTError as error:
        raise _error(error) from None


@router.put("/models/settings")
def publish_models(body: PublishedModelsBody, actor: str = Depends(owner)) -> dict:
    try:
        return save_publication(actor, body.profile_id, body.generation, body.published_models)
    except ChatGPTError as error:
        raise _error(error) from None
