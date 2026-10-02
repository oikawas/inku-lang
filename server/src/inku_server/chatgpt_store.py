"""Protected SIWC registrations. No credentials enter the artwork database."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import stat
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class ChatGPTError(Exception):
    """Only this fixed diagnostic, never a transport exception, is public."""

    def __init__(self, code: str, *, failure: str = "provider_rejected", action: str = "reconnect"):
        super().__init__(code)
        self.code, self.failure, self.action = code, failure, action


def canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _check_file(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ChatGPTError("chatgpt_storage_unsafe")


def protected_read(path: Path, *, limit: int = 256 * 1024) -> bytes:
    if path.is_symlink():
        raise ChatGPTError("chatgpt_storage_unsafe")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        _check_file(os.fstat(handle.fileno()))
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ChatGPTError("chatgpt_payload_too_large")
    return data


def protected_write(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return
    if path.is_symlink():
        raise ChatGPTError("chatgpt_storage_unsafe")
    if path.exists():
        _check_file(path.lstat())
    fd, temporary = tempfile.mkstemp(prefix=".chatgpt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CredentialStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("INKU_CHATGPT_AUTH_DIR", "~/.config/ddl-server/chatgpt")).expanduser()

    def _directory(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ChatGPTError("chatgpt_storage_unsafe")

    @contextmanager
    def lock(self, name: str, deadline: float | None = None, check=None):
        self._directory()
        path = self.root / (hashlib.sha256(name.encode()).hexdigest() + ".lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            _check_file(os.fstat(fd))
            while True:
                if check:
                    check()
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(0.02)
            yield
        finally:
            os.close(fd)

    def _cipher(self) -> Fernet:
        path = self.root / "credential.key"
        try:
            key = protected_read(path, limit=256)
        except FileNotFoundError:
            key = Fernet.generate_key()
            try:
                protected_write(path, key, exclusive=True)
            except FileExistsError:
                key = protected_read(path, limit=256)
        try:
            return Fernet(key)
        except ValueError as error:
            raise ChatGPTError("chatgpt_storage_unsafe") from error

    def _path(self, owner: str) -> Path:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ChatGPTError("chatgpt_owner_not_allowed")
        return self.root / (hashlib.sha256(owner.encode()).hexdigest() + ".enc")

    def read(self, owner: str) -> dict:
        if self.root.exists() or self.root.is_symlink():
            self._directory()
        try:
            raw = protected_read(self._path(owner), limit=1024 * 1024)
        except FileNotFoundError:
            return {"owner_id": owner, "active": None, "profiles": {}, "requests": {}, "receipts": {}}
        try:
            if not raw.startswith(b"enc:v1:"):
                raise ValueError
            result = json.loads(self._cipher().decrypt(raw[7:]))
            if not isinstance(result, dict) or result.get("owner_id") != owner:
                raise ValueError
            return result
        except (InvalidToken, ValueError, KeyError, TypeError) as error:
            raise ChatGPTError("chatgpt_credentials_unavailable") from error

    def write(self, owner: str, value: dict) -> None:
        if value.get("owner_id") != owner:
            raise ChatGPTError("chatgpt_owner_not_allowed")
        encrypted = b"enc:v1:" + self._cipher().encrypt(canonical(value))
        if len(encrypted) > 1024 * 1024:
            raise ChatGPTError("chatgpt_storage_full")
        protected_write(self._path(owner), encrypted)

    def host_id(self) -> str:
        with self.lock("installation", time.monotonic() + 5):
            path = self.root / "host-id"
            try:
                value = protected_read(path, limit=128).decode()
            except FileNotFoundError:
                value = "urn:uuid:" + str(uuid.uuid4())
                protected_write(path, value.encode(), exclusive=True)
            try:
                if not value.startswith("urn:uuid:") or uuid.UUID(value[9:]).version != 4:
                    raise ValueError
            except ValueError as error:
                raise ChatGPTError("chatgpt_storage_unsafe") from error
            return value

    def profile(self, owner: str, profile_id: str | None = None) -> dict:
        value = self.read(owner)
        profile = value["profiles"].get(profile_id or value["active"])
        if not profile:
            raise ChatGPTError("chatgpt_not_connected")
        return profile

    def save_profile(self, owner: str, profile: dict, *, expected_generation: int | None = None, activate: bool = True, deadline: float | None = None) -> None:
        with self.lock("edit:" + owner, deadline or time.monotonic() + 5):
            value = self.read(owner)
            previous = value["profiles"].get(profile["id"])
            if expected_generation is not None and (not previous or previous["generation"] != expected_generation):
                raise ChatGPTError("chatgpt_session_changed")
            if previous and any(previous[key] != profile[key] for key in ("issuer", "sub", "client_id")):
                raise ChatGPTError("chatgpt_identity_mismatch")
            if not previous and len(value["profiles"]) >= 8:
                raise ChatGPTError("chatgpt_profile_limit")
            value["profiles"][profile["id"]] = profile
            if activate:
                value["active"] = profile["id"]
            self.write(owner, value)

    def public_state(self, owner: str) -> dict:
        if not self.root.exists():
            return {"active_profile_id": None, "profiles": [], "pending_registrations": []}
        # Atomic encrypted replacement makes reads coherent without waiting for
        # refresh HTTP. Sign-out must be visible while that request is blocked.
        value = self.read(owner)
        fields = ("id", "label", "email", "client_id", "state", "generation", "scopes", "expires_at")
        return {"active_profile_id": value["active"], "profiles": [
            {key: profile.get(key) for key in fields} for profile in value["profiles"].values()
        ], "pending_registrations": [
            {"id": key, "client_id": entry["client_id"]}
            for key, entry in value.get("registrations_pending", {}).items() if key not in value["profiles"]
        ]}


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def unb64(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
