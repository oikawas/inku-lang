"""Sign in with ChatGPT's procedures, run as the shared core answers them.

The core holds each procedure step for step (SIWC step 5, 2026-11-14): sign-in,
using or refreshing the token, the model list, sign-out, the pause on a usage
limit and its resume, tidying the store to its one registration, and the
identity check of an imported registration. It
answers one thing to do (`todo`) at a time; this module does it and gives back
what came of it. What stays here: the store and its locks, HTTP, the signature
check, randomness, the callback's socket, the attempts' bookkeeping and the
owner gate (chatgpt_runtime).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import http
import secrets
import socket
import threading
import time
import uuid
from datetime import datetime

import httpx
import jwt

from .chatgpt_runtime import check_owner, check_session, guarded
from .chatgpt_store import ChatGPTError, CredentialStore
from .verified_model_catalog import sign_in, sign_in_service

ISSUER = sign_in("auth_constants")["issuer"]
# The subscriber's usage page, from the service's descriptor.
USAGE_URL = sign_in_service("chatgpt")["usage_url"]


def auth_policy(action, **fields):
    result = sign_in("auth_" + action, **fields)
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


def _monotonic(deadline: float) -> float:
    """A deadline on the core's clock (`time.time()`) as one on the monotonic clock."""
    return time.monotonic() + (deadline - time.time())


def flow_failure(todo: dict) -> ChatGPTError:
    if todo.get("status") is not None:
        from .chatgpt_provider import ResponseFailure
        return ResponseFailure(todo)
    return ChatGPTError(todo["code"], failure=todo.get("failure"), action=todo.get("action"))


class Callback:
    """The sign-in's loopback listener: the next request head, and its answer."""

    def __init__(self, host_id: str | None):
        self.host_id = host_id
        self.server: socket.socket | None = None
        self.connection: socket.socket | None = None
        self.reply: bytes | None = None

    def listen(self) -> dict:
        self.server = socket.create_server(("127.0.0.1", 0))
        self.server.settimeout(0.2)
        return {"port": self.server.getsockname()[1]}

    def wait(self, todo: dict, check) -> dict:
        deadline = _monotonic(todo["deadline"])
        while time.monotonic() < deadline:
            check()
            try:
                connection, _address = self.server.accept()
            except TimeoutError:
                continue
            head = self._head(connection)
            if head is None:
                connection.close()
                continue
            self.connection = connection
            return {"head_base64": base64.b64encode(head).decode()}
        # Past the deadline: the core ends the sign-in on the next step.
        return {}

    @staticmethod
    def _head(connection: socket.socket) -> bytes | None:
        # Up to the blank line; a longer head is given cut, for the core to refuse.
        connection.settimeout(1)
        received = bytearray()
        try:
            while b"\r\n\r\n" not in received and len(received) <= 16 * 1024 + 4:
                chunk = connection.recv(4096)
                if not chunk:
                    return None
                received.extend(chunk)
        except OSError:
            return None
        end = received.find(b"\r\n\r\n")
        return bytes(received[:end]) if end >= 0 else bytes(received[:16 * 1024 + 1])

    def respond(self, todo: dict) -> dict:
        # Sent with the next step, so an attempt that ends is settled before the browser hears.
        body = todo["body"].encode("utf-8")
        lines = [f"HTTP/1.1 {todo['status']} {http.HTTPStatus(todo['status']).phrase}",
                 *(f"{name}: {value}" for name, value in todo["headers"].items()), f"Content-Length: {len(body)}"]
        self.reply = "\r\n".join(lines).encode("latin-1") + b"\r\n\r\n" + body
        return {}

    def flush(self) -> None:
        """Send the answer the last `respond` named, if any, and close its connection."""
        if self.reply is None:
            return
        reply, self.reply = self.reply, None
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            connection.sendall(reply)
        except OSError:
            pass
        finally:
            connection.close()

    def close(self) -> None:
        self.flush()
        for held in (self.connection, self.server):
            if held is not None:
                held.close()
        self.connection = self.server = None


class Procedure:
    """One procedure of the core, done step by step.

    `check` runs before each wait and while HTTP is in flight; it raises when
    the trusted runtime, the session or the attempt changed. Locks the caller
    already holds (`held`) are taken as given. With `soft_http`, a check that
    stops HTTP reads as an unavailable server, as sign-out's revocation did.
    """

    def __init__(self, flow: str, input: dict, owner: str | None, *, store: CredentialStore | None = None,
                 check=None, held: tuple[str, ...] = (), soft_http: bool = False,
                 callback: Callback | None = None, on_write=None, on_end=None):
        self.flow, self.owner = flow, owner
        self.store = store or CredentialStore()
        self.check = check or (lambda: None)
        self.given, self.soft_http = set(held), soft_http
        self.callback, self.on_write, self.on_end = callback, on_write, on_end
        self.locks: dict[str, object] = {}
        self.answer = sign_in("flow_start", flow=flow, input=input, now=time.time())
        self.result, self.stopping = None, False

    def _lock_name(self, lock: str) -> str:
        if lock == "wire":
            return f"wire:{self.owner}:{self.answer['state']['input']['profile_id']}"
        return {"edit": "edit:" + self.owner, "refresh": self.owner}[lock]

    async def until(self, stop: str | None = None) -> dict:
        """Do each todo until the procedure ends, or until one named `stop` (left undone)."""
        try:
            while True:
                if self.result is not None:
                    self.answer = sign_in("flow_next", state=self.answer["state"],
                                          result=self.result, now=time.time())
                    self.result = None
                todo = self.answer["todo"]
                if todo["todo"] in {"done", "failed"}:
                    if self.on_end:
                        self.on_end(todo)
                    self.release()
                    if self.callback:
                        self.callback.flush()
                    return todo
                if self.callback:
                    self.callback.flush()
                if todo["todo"] == stop:
                    return todo
                self.result = await self._do(todo)
        except BaseException:
            if self.flow != "login" or self.answer.get("state") is None or self.stopping:
                self.release()
                raise
            # A sign-in stopped by its attempt or the runtime: past its deadline, the
            # core releases what is held and answers a callback it had taken.
            # The caller settles the attempt by the cause, not by the deadline.
            self.stopping, self.result = True, None
            self.check, self.on_end = (lambda: None), None
            self.answer = sign_in("flow_next", state=self.answer["state"], result={},
                                  now=max(time.time(), self.answer["deadline"]))
            await self.until()
            raise

    def give(self, result: dict) -> None:
        self.result = result

    def release(self) -> None:
        while self.locks:
            _name, lock = self.locks.popitem()
            lock.__exit__(None, None, None)

    async def _do(self, todo: dict) -> dict:
        kind = todo["todo"]
        if kind == "acquire":
            if todo["lock"] in self.given:
                return {"acquired": True}
            lock = self.store.lock(self._lock_name(todo["lock"]), _monotonic(todo["deadline"]), self.check)
            try:
                lock.__enter__()
            except TimeoutError:
                return {"acquired": False}
            self.locks[todo["lock"]] = lock
            return {"acquired": True}
        if kind == "release":
            lock = self.locks.pop(todo["lock"], None)
            if lock is not None:
                lock.__exit__(None, None, None)
            return {}
        if kind == "read":
            return {"value": self.store.read(self.owner)}
        if kind == "write":
            if self.on_write:
                self.on_write(lambda: self.store.write(self.owner, todo["value"]), todo["value"])
            else:
                self.store.write(self.owner, todo["value"])
            return {}
        if kind == "http":
            return await self._http(todo)
        if kind == "verify":
            return {"valid": _verify(todo)}
        if kind == "offset":
            return {"seconds": _offset(todo["local"])}
        if kind == "random":
            return {"values": {name: secrets.token_urlsafe(size) for name, size in todo["bytes"].items()}}
        if kind == "host_id":
            return {"host_id": self.callback.host_id or self.store.host_id()}
        if kind == "listen":
            return self.callback.listen()
        if kind == "await_callback":
            return self.callback.wait(todo, self.check)
        if kind == "respond":
            return self.callback.respond(todo)
        if kind == "open":
            return {}
        raise ChatGPTError("chatgpt_auth_unavailable")

    async def _http(self, todo: dict) -> dict:
        deadline = _monotonic(todo["deadline"])
        body = todo["body"].encode("utf-8") if "body" in todo else None
        try:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                self.check()
                stream = client.stream(todo["method"], todo["url"], headers=todo["headers"], content=body,
                                       timeout=max(0.001, deadline - time.monotonic()))
                response = await guarded(stream.__aenter__(), self.check, deadline)
                try:
                    limit = todo["answer_limit"] if response.is_success else todo["error_limit"]
                    content = await read_limited(response, self.check, deadline, limit)
                finally:
                    await stream.__aexit__(None, None, None)
        except ChatGPTError as error:
            if error.code == "chatgpt_response_too_large":
                return {"transport": "too_large"}
            if self.soft_http:
                return {"transport": "unavailable"}
            raise
        except (TimeoutError, httpx.TimeoutException):
            return {"transport": "timeout"}
        except httpx.HTTPError:
            return {"transport": "unavailable"}
        result = {"status": response.status_code, "body": _text(content, strict=todo["purpose"] != "models")}
        if todo.get("request_id_header"):
            result["request_id"] = response.headers.get(todo["request_id_header"])
        return result


def _text(content: bytes, *, strict: bool) -> str:
    # The sign-in server's answers are JSON, read as json.loads read the bytes;
    # bytes that are not UTF-8 are not JSON. The model list is read as received.
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "" if strict else content.decode("utf-8-sig", errors="replace")


def _verify(todo: dict) -> bool:
    try:
        algorithm = jwt.get_algorithm_by_name(todo["alg"])
        key = jwt.PyJWK.from_dict(todo["key"], algorithm=todo["alg"]).key
        signature = jwt.utils.base64url_decode(todo["signature"].encode("ascii"))
        return bool(algorithm.verify(todo["signing_input"].encode("ascii"), key, signature))
    except (jwt.PyJWTError, NotImplementedError, ValueError, KeyError, TypeError, binascii.Error):
        return False


def _offset(local: str) -> int | None:
    """The host's local offset on that date and time, for a value without one."""
    try:
        value = datetime.fromisoformat(local)
        if value.tzinfo is None:
            return int(value.astimezone().utcoffset().total_seconds())
    except (TypeError, ValueError, OverflowError):
        pass
    return None


async def run_flow(flow: str, input: dict, owner: str | None, **options) -> dict:
    """Run one procedure to its end: the core's `done` answer, or its failure raised."""
    todo = await Procedure(flow, input, owner, **options).until()
    if todo["todo"] == "failed":
        raise flow_failure(todo)
    return todo


async def validate_identity(token: str, client_id: str, nonce: str | None, check, deadline: float) -> dict:
    return (await run_flow("identity", {"id_token": token, "client_id": client_id, "nonce": nonce,
                                        "deadline": time.time() + (deadline - time.monotonic())},
                           None, check=check))["claims"]


async def access_token(owner: str, profile_id: str, generation: int, deadline: float, cancel=None) -> str:
    def check():
        return check_session(owner, profile_id, generation, cancel)
    check()
    return (await run_flow("access", {"profile_id": profile_id, "generation": generation,
                                      "deadline": time.time() + (deadline - time.monotonic())},
                           owner, check=check))["access_token"]


async def sign_out(owner: str, profile_id: str) -> dict:
    # Sign-out takes only the edit lock, never the refresh lock, so it is seen
    # at once, even while a refresh is blocked.
    check_owner(owner)
    result = await run_flow("sign_out", {"profile_id": profile_id}, owner, check=lambda: check_owner(owner), soft_http=True)
    return {"status": result["status"], "revocation_confirmed": result["revocation_confirmed"]}


_tidied: set[str] = set()
_tidy_lock = threading.Lock()


def tidy(owner: str) -> None:
    """Once per owner and start, the core's `tidy`: the store down to its one registration.

    The host keeps one registration (the author, 2026-11-14). OpenAI has no way to
    remove a registration; the author removes the others in ChatGPT's settings.
    """
    with _tidy_lock:
        if owner in _tidied:
            return
        if CredentialStore().root.exists():
            asyncio.run(run_flow("tidy", {}, owner))
        _tidied.add(owner)


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

    def begin(self, owner: str, consent: bool, guard, *, new_registration: bool = False,
              registration_host_id: str | None = None, language: str = "en") -> dict:
        # The core signs in the host's one registration with its own client id;
        # `new_registration` replaces it, after the account changed.
        if language not in {"ja", "en"}:
            raise ChatGPTError("chatgpt_language_invalid")
        guard()
        with self.lock:
            self.attempts = {key: value for key, value in self.attempts.items() if time.monotonic() < value["retain_until"]}
            pending = [value for value in self.attempts.values() if value["status"] == "pending"]
            counts = {"pending_count": len(pending), "owner_count": sum(value["owner"] == owner for value in pending)}
            attempt = {"id": str(uuid.uuid4()), "owner": owner, "profile_id": None, "status": "pending",
                       "code": None, "cancel": threading.Event()}

            def check():
                guard()
                if attempt["cancel"].is_set():
                    raise ChatGPTError("chatgpt_cancelled")

            def write(save, value):
                # Cancellation and the kept registration have one linearization point.
                with self.lock:
                    check()
                    save()
                    if attempt["profile_id"] not in value.get("registrations_pending", {}):
                        attempt.update(status="completed", code=None)

            callback = Callback(registration_host_id)
            procedure = Procedure("login", {"consent": consent, "new_registration": new_registration, "language": language, **counts},
                                  owner, check=check, callback=callback, on_write=write,
                                  on_end=lambda todo: self._settle(attempt, None if todo["todo"] == "done" else todo["code"]))
            try:
                opened = asyncio.run(procedure.until("open"))
            except BaseException:
                callback.close()
                raise
            if opened["todo"] != "open":
                callback.close()
                raise flow_failure(opened)
            limits = auth_policy("attempt", **counts)
            attempt.update(profile_id=opened["profile_id"], retain_until=time.monotonic() + limits["retain_seconds"])
            self.attempts[attempt["id"]] = attempt
            procedure.give({})
            threading.Thread(target=self._finish, args=(attempt, procedure, callback), daemon=True,
                             name="inku-chatgpt-callback").start()
            # The page opens the URL only at the core's authorization endpoint, and waits the core's deadline.
            return {"attempt_id": attempt["id"], "profile_id": attempt["profile_id"], "authorization_url": opened["url"],
                    "authorization_endpoint": sign_in("auth_constants")["authorize"],
                    "deadline_seconds": limits["deadline_seconds"]}

    def _finish(self, attempt: dict, procedure: Procedure, callback: Callback) -> None:
        # The procedure settles the attempt as it ends (`on_end`); a stop names its own cause.
        try:
            asyncio.run(procedure.until())
        except ChatGPTError as error:
            self._settle(attempt, error.code)
        except Exception:
            self._settle(attempt, "chatgpt_auth_unavailable")
        finally:
            callback.close()

    def _settle(self, attempt: dict, code: str | None) -> None:
        with self.lock:
            if attempt["status"] == "pending":
                attempt.update(status="completed" if code is None else "failed", code=code)


attempts = AuthorizationAttempts()
