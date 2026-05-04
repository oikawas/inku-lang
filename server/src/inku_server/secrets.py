"""Secret value encryption for server-side app settings."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets as py_secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SECRET_PREFIX = "enc:v1:"
_DEFAULT_KEY_FILE = Path.home() / ".local" / "share" / "inku" / "secret.key"


def _key_material() -> str:
    env_value = os.getenv("INKU_SECRET_KEY", "").strip()
    if env_value:
        return env_value
    key_file = Path(os.getenv("INKU_SECRET_KEY_FILE", str(_DEFAULT_KEY_FILE))).expanduser()
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    material = py_secrets.token_urlsafe(48)
    key_file.write_text(material, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
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
