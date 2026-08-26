"""Direct compatibility coverage for account password credentials."""

from __future__ import annotations

import ast
from hashlib import pbkdf2_hmac
import inspect

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _owner_or_skip():
    owner = getattr(accounts, "hash_password", None)
    if owner is None:
        pytest.skip("password credential owner is intentionally absent during fail-first")
    return owner


def test_accounts_owns_password_credentials_and_db_delegates() -> None:
    assert hasattr(accounts, "hash_password")
    assert hasattr(accounts, "verify_password")
    assert hasattr(accounts, "DUMMY_PASSWORD_HASH")
    for name in ("_hash_password", "verify_password"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert isinstance(facade.body[-1], ast.Return)
    assert db._DUMMY_PASSWORD_HASH is accounts.DUMMY_PASSWORD_HASH


def test_password_hash_preserves_exact_format_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hash_password = _owner_or_skip()
    salt = bytes(range(16))
    monkeypatch.setattr(accounts.secrets, "token_bytes", lambda size: salt)
    expected = pbkdf2_hmac("sha256", b"password-123", salt, 310_000)
    assert hash_password("password-123") == (
        f"pbkdf2_sha256$310000${salt.hex()}${expected.hex()}"
    )
    with pytest.raises(ValueError, match="password is required"):
        hash_password("")


def test_password_verification_preserves_valid_wrong_and_malformed() -> None:
    hash_password = _owner_or_skip()
    stored = hash_password("correct-password")
    assert accounts.verify_password("correct-password", stored) is True
    assert accounts.verify_password("wrong-password", stored) is False
    for malformed in ("", "broken", "sha256$1$00$00", "pbkdf2_sha256$x$00$00"):
        assert accounts.verify_password("password", malformed) is False


def test_dummy_hash_remains_a_valid_timing_guard() -> None:
    _owner_or_skip()
    assert accounts.verify_password(
        "inku-nonexistent-account-timing-guard", accounts.DUMMY_PASSWORD_HASH
    )
    assert not accounts.verify_password("wrong", accounts.DUMMY_PASSWORD_HASH)
