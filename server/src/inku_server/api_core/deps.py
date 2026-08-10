"""FastAPI dependencies every router group is gated on."""

from __future__ import annotations

import logging
import secrets
from fastapi import Cookie, Depends, Header, HTTPException
from .. import db as _db


# Pinned to the pre-split module name on purpose: every router group and api.py
# itself logs through this one logger, so __name__ here would rename the channel
# operators (and caplog) already select on.
_logger = logging.getLogger("inku_server.api")


_SESSION_COOKIE_NAME = "inku_session"


# Stands in for a session token when single-user mode answers for a request
# that carried no credentials.  Minted per process and never stored, so a
# client cannot present it: only _session_token can put it into circulation.
_SINGLE_USER_TOKEN = "single-user:" + secrets.token_urlsafe(32)


def _session_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=_SESSION_COOKIE_NAME),
) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if session_cookie:
        return session_cookie
    if _db.single_user_mode_enabled():
        # This server belongs to one person, so an unauthenticated request is
        # theirs.  Resolution can still fail -- a database whose accounts
        # include no administrator has nobody to hand it to -- and
        # _current_user turns that back into the 401 this line used to raise.
        return _SINGLE_USER_TOKEN
    raise HTTPException(status_code=401, detail="authentication required")


def _current_user(token: str = Depends(_session_token)) -> dict:
    user = _db.get_session_user(token)
    if not user and token == _SINGLE_USER_TOKEN:
        user = _db.single_user_account()
    if not user:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _user_manager(actor: dict = Depends(_current_user)) -> dict:
    if not (
        _db.has_permission_group(actor, "admins")
        or _db.has_permission_group(actor, "leaders")
    ):
        raise HTTPException(status_code=403, detail="user management is not permitted")
    return actor


def _admin_user(actor: dict = Depends(_current_user)) -> dict:
    if not _db.has_permission_group(actor, "admins"):
        raise HTTPException(status_code=403, detail="administrator permission is required")
    return actor
