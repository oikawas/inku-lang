"""Endpoints for the auth group, moved out of api.py unchanged."""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from ...security import SlidingWindowRateLimiter
from ... import db as _db
from ..deps import _SESSION_COOKIE_NAME, _session_token, _user_manager
from ..models import UserAccountItem


router = APIRouter()
manager_router = APIRouter(dependencies=[Depends(_user_manager)])


_SESSION_COOKIE_MAX_AGE = int(os.getenv("INKU_SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 30)))


_SESSION_COOKIE_SECURE = os.getenv("INKU_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"}


_LOGIN_RATE_ATTEMPTS = max(1, int(os.getenv("INKU_LOGIN_RATE_ATTEMPTS", "10")))


_LOGIN_RATE_WINDOW_SECONDS = max(1, int(os.getenv("INKU_LOGIN_RATE_WINDOW_SECONDS", "60")))


_login_rate_limiter = SlidingWindowRateLimiter(
    attempts=_LOGIN_RATE_ATTEMPTS,
    window_seconds=_LOGIN_RATE_WINDOW_SECONDS,
)


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=320)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    user: UserAccountItem


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


@router.get("/api/auth/config")
def api_auth_config() -> dict:
    return _db.get_auth_settings()


class AuthSettingsBody(BaseModel):
    google_enabled: bool
    local_enabled: bool


@manager_router.put("/api/auth/config")
def api_auth_config_update(body: AuthSettingsBody) -> dict:
    return _db.update_auth_settings(body.google_enabled, body.local_enabled)


@router.post("/api/auth/login", response_model=LoginResponse)
def api_auth_login(body: LoginBody, response: Response, request: Request) -> LoginResponse:
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


@router.post("/api/auth/logout")
def api_auth_logout(response: Response, token: str = Depends(_session_token)) -> dict[str, bool]:
    _db.delete_session(token)
    _clear_session_cookie(response)
    return {"ok": True}
