"""FastAPI dependencies every router group is gated on."""

from __future__ import annotations

import logging
from fastapi import Cookie, Depends, Header, HTTPException
from .. import db as _db


# Pinned to the pre-split module name on purpose: every router group and api.py
# itself logs through this one logger, so __name__ here would rename the channel
# operators (and caplog) already select on.
_logger = logging.getLogger("inku_server.api")


_SESSION_COOKIE_NAME = "inku_session"


def _session_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=_SESSION_COOKIE_NAME),
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if session_cookie:
        return session_cookie
    raise HTTPException(status_code=401, detail="authentication required")


def _current_user(token: str = Depends(_session_token)) -> dict:
    user = _db.get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _user_manager(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] not in {"admin", "group_lead"}:
        raise HTTPException(status_code=403, detail="user management is not permitted")
    return actor


def _admin_user(actor: dict = Depends(_current_user)) -> dict:
    if actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="administrator permission is required")
    return actor
