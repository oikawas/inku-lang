"""Direct compatibility coverage for authentication session token hashes."""

from __future__ import annotations

import ast
from hashlib import sha256
import inspect

import pytest

from inku_server import db
from inku_server.persistence import sessions


def _owner_or_skip():
    owner = getattr(sessions, "hash_token", None)
    if owner is None:
        pytest.skip("session token hash owner is intentionally absent during fail-first")
    return owner


def test_sessions_owns_token_hash_and_db_delegates() -> None:
    assert hasattr(sessions, "hash_token")
    facade = ast.parse(inspect.getsource(db._hash_token)).body[0]
    assert isinstance(facade, ast.FunctionDef)
    assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)


def test_token_hash_preserves_exact_utf8_sha256_vectors() -> None:
    hash_token = _owner_or_skip()
    for token in ("", "raw-token", "認証トークン"):
        assert hash_token(token) == sha256(token.encode("utf-8")).hexdigest()


def test_token_hash_preserves_raw_input_without_normalization() -> None:
    hash_token = _owner_or_skip()
    assert hash_token(" token ") != hash_token("token")
    assert hash_token("Token") != hash_token("token")
    assert len(hash_token("token")) == 64
    assert hash_token("token") == hash_token("token").lower()


def test_session_factory_still_receives_db_compatibility_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owner_or_skip()
    received: list[tuple[object, ...]] = []

    class RecordingStore:
        def __init__(self, *dependencies: object) -> None:
            received.append(dependencies)

    marker = object()
    monkeypatch.setattr(db, "_hash_token", marker)
    monkeypatch.setattr(db._sessions, "SessionStore", RecordingStore)
    db._session_store()
    assert received[0][2] is marker
