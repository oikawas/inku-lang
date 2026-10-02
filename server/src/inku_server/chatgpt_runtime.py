"""Startup and owner gates shared by the SIWC API, CLI and transport."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass

from .chatgpt_store import ChatGPTError, CredentialStore


@dataclass(frozen=True)
class Startup:
    host: str
    port: int
    self_hosted: bool


_startup: Startup | None = None
_stopping = threading.Event()
_cancels: dict[tuple[str, str], threading.Event] = {}
_cancel_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("INKU_CHATGPT_PLAN_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def mode_allowed() -> bool:
    from . import db
    return os.getenv("INKU_DEVELOPER_MODE", "").lower() in {"1", "true", "yes", "on"} or db.single_user_mode_enabled()


def configure_startup(host: str, port: int, *, self_hosted: bool) -> None:
    global _startup
    if not self_hosted and host not in {"127.0.0.1", "::1"}:
        raise ChatGPTError("chatgpt_local_bind_required")
    if not 1 <= port <= 65535:
        raise ChatGPTError("chatgpt_startup_unverified")
    _startup = Startup(host, port, self_hosted)
    _stopping.clear()


def availability() -> tuple[bool, str | None]:
    if not enabled():
        return False, "chatgpt_disabled"
    if not mode_allowed():
        return False, "chatgpt_mode_not_allowed"
    if _startup is None or _stopping.is_set():
        return False, "chatgpt_startup_unverified"
    return True, None


def check_owner(owner: str, *, cli: bool = False) -> None:
    from . import db
    if cli:
        if not enabled() or not mode_allowed():
            raise ChatGPTError("chatgpt_mode_not_allowed", action="settings")
    else:
        available, reason = availability()
        if not available:
            raise ChatGPTError(reason or "chatgpt_disabled", action="settings")
    account = db.get_user(owner)
    if not account:
        raise ChatGPTError("chatgpt_owner_not_allowed")
    if db.single_user_mode_enabled():
        fixed = db.single_user_account()
        if not fixed or fixed["id"] != owner:
            raise ChatGPTError("chatgpt_owner_not_allowed")


def cancel_execution(owner: str, execution: str) -> None:
    with _cancel_lock:
        event = _cancels.get((owner, execution))
        if event:
            event.set()


def execution_cancel(owner: str, execution: str) -> threading.Event:
    with _cancel_lock:
        return _cancels.setdefault((owner, execution), threading.Event())


def begin_execution(owner: str, execution: str) -> None:
    # Called only when the prior worker has finished. Old requests retain the
    # old event, so a subsequent author action cannot revive cancelled I/O.
    with _cancel_lock:
        _cancels[(owner, execution)] = threading.Event()


def retire_execution(owner: str, execution: str) -> None:
    with _cancel_lock:
        _cancels.pop((owner, execution), None)


def cancel_owner(owner: str) -> None:
    with _cancel_lock:
        for (actor, _execution), event in _cancels.items():
            if actor == owner:
                event.set()


def stop() -> None:
    _stopping.set()
    with _cancel_lock:
        for event in _cancels.values():
            event.set()
    from .chatgpt_auth import attempts
    attempts.stop()


def check_session(owner: str, profile_id: str, generation: int, cancel: threading.Event | None = None) -> dict:
    check_owner(owner)
    if cancel is not None and cancel.is_set():
        raise ChatGPTError("chatgpt_cancelled", action="retry")
    profile = CredentialStore().profile(owner, profile_id)
    if profile["generation"] != generation:
        raise ChatGPTError("chatgpt_session_changed")
    if profile["state"] != "connected":
        action = "usage" if profile["state"] == "quota" else "reconnect"
        raise ChatGPTError("chatgpt_" + profile["state"], action=action)
    if "chatgpt.tokens.use.direct" not in profile["scopes"]:
        raise ChatGPTError("chatgpt_scope_required", action="consent")
    return profile


async def guarded(awaitable, check, deadline: float):
    """Abort a blocked HTTP operation when its trusted runtime changes."""
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            check()
            if time.monotonic() >= deadline:
                raise TimeoutError
            await asyncio.wait({task}, timeout=min(0.1, max(0, deadline - time.monotonic())))
        check()
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
