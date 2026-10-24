"""Endpoints for the auth group, moved out of api.py unchanged."""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from ...security import SlidingWindowRateLimiter
from ... import db as _db
from ..deps import _SESSION_COOKIE_NAME, _SINGLE_USER_TOKEN, _admin_user, _current_user, _session_token
from ..models import UserAccountItem


router = APIRouter()
# Everything in the auth group except logging in itself: reading how the server
# authenticates is not something logging in needs to know beforehand.
authenticated_router = APIRouter(dependencies=[Depends(_current_user)])
# Changing how the whole server authenticates is a global setting, which the
# SPEC gives to `admins` alone. It used to sit behind the user-manager guard, so
# a leader -- who manages the members of one organisation group -- could turn
# local sign-in off for every account on the server.
admin_router = APIRouter(dependencies=[Depends(_admin_user)])


_SESSION_COOKIE_MAX_AGE = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))


_SESSION_COOKIE_SECURE = os.getenv("INKU_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}


_LOGIN_RATE_ATTEMPTS = max(1, int(os.getenv("INKU_LOGIN_RATE_ATTEMPTS", "10")))


_LOGIN_RATE_WINDOW_SECONDS = max(1, int(os.getenv("INKU_LOGIN_RATE_WINDOW_SECONDS", "60")))


_login_rate_limiter = SlidingWindowRateLimiter(
    attempts=_LOGIN_RATE_ATTEMPTS,
    window_seconds=_LOGIN_RATE_WINDOW_SECONDS,
)


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=320, description="Username of the account to sign in to, 1 to 320 characters.")
    password: str = Field(..., min_length=1, max_length=1024, description="Password of that account, 1 to 1,024 characters.")


class LoginResponse(BaseModel):
    user: UserAccountItem = Field(..., description="The account that signed in.")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE_NAME,
        token,
        max_age=_SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=_SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(_SESSION_COOKIE_NAME, path="/", samesite="lax")


@authenticated_router.get("/api/auth/config", summary="Get sign-in method settings")
def api_auth_config() -> dict:
    """Return the stored sign-in method settings, `google_enabled` and `local_enabled`.

    Requires a signed-in user.
    """
    return _db.get_auth_settings()


class AuthSettingsBody(BaseModel):
    google_enabled: bool = Field(
        ...,
        description="Stored switch for Google sign-in. The server does not sign anyone in through it yet.",
    )
    local_enabled: bool = Field(
        ...,
        description="Whether username and password sign-in is enabled. Must be true; false is rejected with 409.",
    )


@admin_router.put("/api/auth/config", summary="Update sign-in method settings")
def api_auth_config_update(body: AuthSettingsBody) -> dict:
    """Store which sign-in methods are enabled. Requires an administrator.

    Returns 409 when `local_enabled` is false, because local sign-in is the only method the server
    can use to sign anyone in.
    """
    # Local sign-in is the only way in this server implements: the Google
    # switch is stored, but nothing signs anyone in through it. Turning local
    # off therefore locked out every account, and `inku-admin reset-password`
    # could not help, since a new password still has nowhere to be entered.
    if not body.local_enabled:
        raise HTTPException(
            status_code=409,
            detail="local sign-in is the only sign-in method and cannot be turned off",
        )
    return _db.update_auth_settings(body.google_enabled, body.local_enabled)


@router.post("/api/auth/login", response_model=LoginResponse, summary="Sign in with username and password")
def api_auth_login(body: LoginBody, response: Response, request: Request) -> LoginResponse:
    """Check a username and password, start a session and set its session cookie.

    Returns the signed-in account. Returns 403 when local sign-in is disabled, 429 with a
    `Retry-After` header after too many attempts from one client for one username, and 401 when
    the username or password is wrong. This route needs no session.
    """
    auth_config = _db.get_auth_settings()
    if not auth_config.get("local_enabled", True):
        raise HTTPException(status_code=403, detail="Local authentication is disabled")
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{body.username.strip().casefold()}"
    rate_result = _login_rate_limiter.check(rate_key)
    if not rate_result.allowed:
        raise HTTPException(
            status_code=429,
            detail="too many login attempts",
            headers={"Retry-After": str(rate_result.retry_after)},
        )
    user = _db.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    _login_rate_limiter.reset(rate_key)
    token = _db.create_session(user["id"])
    _set_session_cookie(response, token)
    return LoginResponse(user=UserAccountItem(**user))


@router.post("/api/auth/logout", summary="Sign out of the current session")
def api_auth_logout(response: Response, token: str = Depends(_session_token)) -> dict[str, bool]:
    """End the current session and clear its session cookie.

    Also stops the signed-in user's pending ChatGPT connection attempts and cancels their
    ChatGPT work. An unknown or expired token is accepted. Returns 401 when no session token is sent,
    and `{"ok": true}` otherwise.
    """
    actor = _db.get_session_user(token)
    if actor is None and token == _SINGLE_USER_TOKEN:
        actor = _db.single_user_account()
    if actor:
        from ...chatgpt_auth import attempts
        from ...chatgpt_runtime import cancel_owner
        attempts.stop(actor["id"])
        cancel_owner(actor["id"])
    _db.delete_session(token)
    _clear_session_cookie(response)
    return {"ok": True}
