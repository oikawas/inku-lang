"""Public-client PKCE/OIDC, token rotation and owner-bound loopback attempts."""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt

from .chatgpt_runtime import check_owner, check_session, guarded
from .chatgpt_store import ChatGPTError, CredentialStore
from .verified_model_catalog import core_catalog

_AUTH_CONSTANTS = core_catalog("chatgpt_auth_constants")
ISSUER = _AUTH_CONSTANTS["issuer"]
AUTHORIZE = _AUTH_CONSTANTS["authorize"]
TOKEN = _AUTH_CONSTANTS["token"]
RESOURCE = _AUTH_CONSTANTS["resource"]
SCOPES = _AUTH_CONSTANTS["scopes"]
USAGE_URL = "https://chatgpt.com/settings/usage"


def callback_page(language: str, *, completed: bool) -> bytes:
    if language == "ja":
        title = "ChatGPTの認証が完了しました" if completed else "ChatGPTの認証は完了していません"
        message = ("このタブを閉じ、inkuへ戻って「接続状態を確認」を押してください。別のホストへ接続する場合は、Macの登録移送完了を待ってから確認してください。"
                   if completed else "inkuへ戻り、接続の案内を確認してください。この画面から認証を自動でやり直すことはありません。")
    else:
        title = "ChatGPT authorization completed" if completed else "ChatGPT authorization did not complete"
        message = ("Close this tab, return to inku and press Check connection. For a remote host, wait until the Mac registration transfer finishes first."
                   if completed else "Return to inku and check the connection message. This page does not retry authorization automatically.")
    return (f'<!doctype html><html lang="{language}"><head><meta charset="utf-8"><title>{title}</title></head>'
            f'<body><main><h1>{title}</h1><p>{message}</p></main></body></html>').encode("utf-8")


def auth_endpoint(url: str) -> str:
    return auth_policy("endpoint", url=url)["url"]


def auth_policy(action, **fields):
    result = core_catalog("chatgpt_auth_" + action, **fields)
    if "error" in result:
        raise ChatGPTError(result["error"])
    return result


async def read_limited(response: httpx.Response, check, deadline: float, limit: int) -> bytes:
    result = bytearray()
    iterator = response.aiter_bytes(chunk_size=16 * 1024)
    while True:
        try:
            chunk = await guarded(anext(iterator), check, deadline)
        except StopAsyncIteration:
            break
        if len(result) + len(chunk) > limit:
            raise ChatGPTError("chatgpt_response_too_large")
        result.extend(chunk)
    return bytes(result)


async def auth_json(client: httpx.AsyncClient, method: str, url: str, check, deadline: float, **kwargs) -> dict:
    check()
    stream = client.stream(method, auth_endpoint(url), timeout=max(0.001, deadline - time.monotonic()), **kwargs)
    response = await guarded(stream.__aenter__(), check, deadline)
    try:
        content = await read_limited(response, check, deadline, 1024 * 1024)
    finally:
        await stream.__aexit__(None, None, None)
    try:
        value = json.loads(content)
    except ValueError as error:
        auth_policy("http", status=response.status_code, json_valid=False)
        raise ChatGPTError("chatgpt_auth_unavailable") from error
    if auth_policy("http", status=response.status_code, json_valid=True, value=value).get("type_error"):
        raise TypeError("unhashable OAuth error code")
    return value


async def discovery(client, check, deadline) -> dict:
    value = await auth_json(client, "GET", ISSUER + "/.well-known/openid-configuration", check, deadline)
    auth_policy("discovery", discovery=value)
    return value


async def validate_identity(client, token: str, client_id: str, nonce: str | None, check, deadline) -> dict:
    metadata = await discovery(client, check, deadline)
    keys = await auth_json(client, "GET", auth_endpoint(metadata["jwks_uri"]), check, deadline)
    try:
        header = jwt.get_unverified_header(token)
        chosen = auth_policy("key", header=header, discovery=metadata, keys=keys)
        key = jwt.PyJWK.from_dict(chosen["key"], algorithm=chosen["alg"]).key
        claims = jwt.decode(token, key, algorithms=[header["alg"]],
                            options={"verify_iss": False, "verify_aud": False, "verify_exp": False,
                                     "verify_iat": False, "verify_nbf": False, "verify_jti": False})
        auth_policy("claims", claims=claims, client_id=client_id, nonce=nonce, now=time.time())
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
        raise ChatGPTError("chatgpt_identity_invalid") from error
    check()
    return claims


def token_fields(value: dict, previous: dict | None = None) -> dict:
    offset = None
    earliest = value.get("earliest_refresh_at")
    if isinstance(earliest, str):
        try:
            local = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
            if local.tzinfo is None:
                offset = int(local.astimezone().utcoffset().total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return auth_policy("tokens", value=value, previous=previous, now=time.time(),
                       local_offset_seconds=offset)["tokens"]


async def access_token(owner: str, profile_id: str, generation: int, deadline: float, cancel=None) -> str:
    def check():
        return check_session(owner, profile_id, generation, cancel)
    store = CredentialStore()
    with store.lock(owner, deadline, check):
        profile = check()
        if auth_policy("access", profile=profile, now=time.time())["decision"] == "use":
            return profile["access_token"]
        try:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                result = await auth_json(client, "POST", TOKEN, check, deadline, data={
                    "grant_type": "refresh_token", "client_id": profile["client_id"],
                    "refresh_token": profile["refresh_token"], "resource": RESOURCE,
                })
                if result.get("id_token"):
                    claims = await validate_identity(client, result["id_token"], profile["client_id"], None, check, deadline)
                    auth_policy("identity", previous=profile, sub=claims["sub"])
            check()
            profile = auth_policy("refresh_profile", profile=profile, tokens=token_fields(result, profile))["profile"]
            store.save_profile(owner, profile, expected_generation=generation, activate=False, deadline=deadline)
        except ChatGPTError as error:
            if error.code == "chatgpt_reauthentication_required":
                profile = auth_policy("transition", profile=profile, state="reauthentication_required")["profile"]
                store.save_profile(owner, profile, expected_generation=generation, activate=False, deadline=deadline)
            raise
        return profile["access_token"]


async def sign_out(owner: str, profile_id: str) -> dict:
    check_owner(owner)
    store = CredentialStore()
    # This lock is deliberately separate from the refresh/slot lock: sign-out
    # invalidates the session immediately, including while refresh is blocked.
    with store.lock("edit:" + owner, time.monotonic() + 5):
        value = store.read(owner)
        profile = value["profiles"].get(profile_id)
        if not profile:
            raise ChatGPTError("chatgpt_not_connected")
        old = dict(profile)
        profile = auth_policy("transition", profile=profile, state="signed_out")["profile"]
        value["profiles"][profile_id] = profile
        store.write(owner, value)
    confirmed = False
    try:
        deadline = time.monotonic() + 10
        if auth_policy("revocation", profile=old)["send"]:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                metadata = await discovery(client, lambda: check_owner(owner), deadline)
                stream = client.stream("POST", auth_endpoint(metadata["revocation_endpoint"]), data={
                    "token": old["refresh_token"], "token_type_hint": "refresh_token", "client_id": old["client_id"],
                }, timeout=10)
                response = await guarded(stream.__aenter__(), lambda: check_owner(owner), deadline)
                try:
                    await read_limited(response, lambda: check_owner(owner), deadline, 64 * 1024)
                    confirmed = auth_policy("revocation", profile=old, status=response.status_code)["confirmed"]
                finally:
                    await stream.__aexit__(None, None, None)
    except (ChatGPTError, httpx.HTTPError, TimeoutError, KeyError):
        pass
    return {"status": "signed_out", "revocation_confirmed": confirmed}


async def delete_profile(owner: str, profile_id: str) -> dict:
    # Sign out first so a connected registration's tokens are revoked, then drop the entry.
    result = await sign_out(owner, profile_id)
    store = CredentialStore()
    with store.lock("edit:" + owner, time.monotonic() + 5):
        value = store.read(owner)
        profile = value["profiles"].get(profile_id)
        if not profile:
            raise ChatGPTError("chatgpt_not_connected")
        # A reconnection that landed during revocation is newer than this request.
        if profile["state"] != "signed_out":
            raise ChatGPTError("chatgpt_session_changed")
        del value["profiles"][profile_id]
        value.get("registrations_pending", {}).pop(profile_id, None)
        if value["active"] == profile_id:
            value["active"] = None
        store.write(owner, value)
    return {"status": "deleted", "revocation_confirmed": result["revocation_confirmed"]}


class AuthorizationAttempts:
    def __init__(self):
        self.attempts: dict[str, dict] = {}
        self.lock = threading.RLock()

    def stop(self, owner: str | None = None) -> None:
        with self.lock:
            for attempt in self.attempts.values():
                if (owner is None or attempt["owner"] == owner) and attempt["status"] == "pending":
                    attempt["cancel"].set()
                    attempt.update(status="cancelled", code="chatgpt_cancelled")

    def public(self, owner: str, attempt_id: str) -> dict:
        with self.lock:
            attempt = self.attempts.get(attempt_id)
            if not attempt or attempt["owner"] != owner:
                raise ChatGPTError("chatgpt_attempt_not_found")
            return {key: attempt[key] for key in ("id", "status", "code", "profile_id")}

    def cancel(self, owner: str, attempt_id: str) -> dict:
        with self.lock:
            attempt = self.attempts.get(attempt_id)
            if not attempt or attempt["owner"] != owner:
                raise ChatGPTError("chatgpt_attempt_not_found")
            if attempt["status"] == "pending":
                attempt.update(status="cancelled", code="chatgpt_cancelled")
                attempt["cancel"].set()
        return self.public(owner, attempt_id)

    def begin(self, owner: str, profile_id: str | None, consent: bool, guard, *, registration_host_id: str | None = None, language: str = "en") -> dict:
        if language not in {"ja", "en"}:
            raise ChatGPTError("chatgpt_language_invalid")
        guard()
        with self.lock:
            self.attempts = {key: value for key, value in self.attempts.items() if time.monotonic() < value["retain_until"]}
            pending = [value for value in self.attempts.values() if value["status"] == "pending"]
            if len(pending) >= 4 or sum(value["owner"] == owner for value in pending) >= 1:
                raise ChatGPTError("chatgpt_attempt_busy")
            saved = CredentialStore().read(owner) if CredentialStore().root.exists() else {"profiles": {}}
            previous = saved["profiles"].get(profile_id) if profile_id else None
            if profile_id and not previous:
                pending = saved.get("registrations_pending", {}).get(profile_id)
                if not pending:
                    raise ChatGPTError("chatgpt_not_connected")
                previous = {**pending, "pending": True}
            attempt = {"id": str(uuid.uuid4()), "owner": owner, "profile_id": profile_id or str(uuid.uuid4()),
                       "status": "pending", "code": None, "state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32),
                       "verifier": secrets.token_urlsafe(64), "used": False, "cancel": threading.Event(),
                       "deadline": time.monotonic() + 300, "retain_until": time.monotonic() + 600}
            def check():
                guard()
                if attempt["cancel"].is_set() or time.monotonic() >= attempt["deadline"]:
                    raise ChatGPTError("chatgpt_cancelled")
            coordinator = self
            class Listener(HTTPServer):
                def get_request(self):
                    sock, address = super().get_request()
                    sock.settimeout(1)
                    return sock, address

                def handle_error(self, *_args):
                    # Malformed callback sockets must never produce a traceback.
                    pass

            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    parsed = urlsplit(self.path)
                    query = parse_qs(parsed.query)
                    status = 400
                    try:
                        if parsed.path != "/auth/callback" or any(len(value) != 1 for value in query.values()):
                            raise ChatGPTError("chatgpt_callback_invalid")
                        auth_policy("callback", state=query.get("state", [""])[0],
                                    expected_state=attempt["state"], code="state-check", error=None)
                        with coordinator.lock:
                            check()
                            if attempt["used"]:
                                raise ChatGPTError("chatgpt_callback_invalid")
                            attempt["used"] = True
                        if "error" in query:
                            auth_policy("callback", state=attempt["state"], expected_state=attempt["state"],
                                        code="error-check", error=query["error"][0])
                        issued = query.get("client_id", [previous["client_id"] if previous else ""])[0]
                        auth_policy("callback_client", issued=issued, previous=previous)
                        code = auth_policy("callback", state=attempt["state"], expected_state=attempt["state"],
                                           code=query.get("code", [None])[0], error=None)["code"]
                        asyncio.run(coordinator._exchange(attempt, issued, code, previous, check))
                        status = 200
                    except Exception as error:
                        if attempt["used"]:
                            attempt.update(status="failed", code=error.code if isinstance(error, ChatGPTError) else "chatgpt_auth_unavailable")
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.end_headers()
                    self.wfile.write(callback_page(language, completed=status == 200))
            server = Listener(("127.0.0.1", 0), Callback)
            server.timeout = 0.2
            attempt["redirect_uri"] = f"http://127.0.0.1:{server.server_port}/auth/callback"
            self.attempts[attempt["id"]] = attempt
            def listen():
                try:
                    while attempt["status"] == "pending":
                        check()
                        server.handle_request()
                except ChatGPTError as error:
                    attempt.update(status="failed", code=error.code)
                finally:
                    server.server_close()
                    for field in ("state", "nonce", "verifier"):
                        attempt.pop(field, None)
            url = auth_policy("url", previous=previous, consent=consent,
                              host_id=registration_host_id or CredentialStore().host_id(),
                              redirect_uri=attempt["redirect_uri"], state=attempt["state"],
                              nonce=attempt["nonce"], verifier=attempt["verifier"])["url"]
            threading.Thread(target=listen, daemon=True, name="inku-chatgpt-callback").start()
            return {"attempt_id": attempt["id"], "profile_id": attempt["profile_id"], "authorization_url": url}

    async def _exchange(self, attempt, issued, code, previous, check):
        store = CredentialStore()
        with store.lock(attempt["owner"], attempt["deadline"], check):
            with store.lock("edit:" + attempt["owner"], attempt["deadline"], check):
                value = store.read(attempt["owner"])
                registrations = value.setdefault("registrations_pending", {})
                auth_policy("pending_check", exists=attempt["profile_id"] in registrations, count=len(registrations))
                registrations[attempt["profile_id"]] = {"client_id": issued}
                store.write(attempt["owner"], value)
        async with httpx.AsyncClient(follow_redirects=False) as client:
            tokens = await auth_json(client, "POST", TOKEN, check, attempt["deadline"], data={
                "grant_type": "authorization_code", "client_id": issued, "code": code, "code_verifier": attempt["verifier"],
                "redirect_uri": attempt["redirect_uri"], "resource": RESOURCE,
            })
            claims = await validate_identity(client, tokens["id_token"], issued, attempt["nonce"], check, attempt["deadline"])
        auth_policy("identity", previous=previous, sub=claims["sub"])
        display = auth_policy("display", claims=claims, client_id=issued,
                              email_json=json.dumps(claims["email"], ensure_ascii=False) if "email" in claims else None)
        profile = {"id": attempt["profile_id"], "issuer": ISSUER, "sub": claims["sub"], "client_id": issued,
                   "email": display["email"], "label": display["label"],
                   "generation": auth_policy("generation", previous=previous)["generation"], "state": "connected", "refresh_owner": "runtime",
                   "oidc_nonce": attempt["nonce"], **token_fields(tokens)}
        with store.lock(attempt["owner"], attempt["deadline"], check):
            # Cancellation and verified adoption have one linearization point.
            # Never hold this coordinator lock during HTTP.
            with self.lock:
                check()
                store.save_profile(attempt["owner"], profile, expected_generation=previous.get("generation") if previous else None, deadline=attempt["deadline"])
                with store.lock("edit:" + attempt["owner"], attempt["deadline"], check):
                    value = store.read(attempt["owner"])
                    value.get("registrations_pending", {}).pop(attempt["profile_id"], None)
                    store.write(attempt["owner"], value)
                attempt.update(status="completed", code=None)


attempts = AuthorizationAttempts()
