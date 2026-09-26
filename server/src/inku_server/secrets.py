"""Secret value encryption for server-side app settings."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets as py_secrets
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SECRET_PREFIX = "enc:v1:"
_DEFAULT_KEY_FILE = Path.home() / ".local" / "share" / "inku" / "secret.key"


def _read_key_file(key_file: Path) -> str:
    """The stored key, waiting briefly for a file another process is writing.

    Between another process creating the file and writing the key into it the
    file is empty, and an empty key would silently derive a different cipher.
    """
    for _ in range(20):
        material = key_file.read_text(encoding="utf-8").strip()
        if material:
            return material
        time.sleep(0.05)
    return material


def _key_material() -> str:
    env_value = os.getenv("INKU_SECRET_KEY", "").strip()
    if env_value:
        return env_value
    key_file = Path(os.getenv("INKU_SECRET_KEY_FILE", str(_DEFAULT_KEY_FILE))).expanduser()
    if key_file.exists():
        return _read_key_file(key_file)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    material = py_secrets.token_urlsafe(48)
    # Created owner-only and exclusively in one step. Writing first and
    # narrowing afterwards left the key readable under the umask in between,
    # and two processes starting together could each write a key -- the later
    # one replacing the key the earlier had already encrypted provider
    # credentials with, which would then decrypt to nothing.
    try:
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_key_file(key_file)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(material)
    return material


def _fernet() -> Fernet:
    digest = hashlib.sha256(_key_material().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted_secret(value: str | None) -> bool:
    return bool(value and value.startswith(SECRET_PREFIX))


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if is_encrypted_secret(value):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{SECRET_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if not is_encrypted_secret(value):
        return value
    token = value[len(SECRET_PREFIX):].encode("ascii")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError):
        return ""
