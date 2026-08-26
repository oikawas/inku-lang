"""Direct ownership coverage for single-user mode resolution."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _resolver_or_skip():
    resolver = getattr(accounts, "SingleUserModeResolver", None)
    if resolver is None:
        pytest.skip("single-user mode resolver is intentionally absent during fail-first")
    return resolver


def _resolver(value):
    return _resolver_or_skip()(lambda name: value)


def test_accounts_owns_single_user_mode_resolution_and_db_delegates(monkeypatch) -> None:
    resolver = getattr(accounts, "SingleUserModeResolver", None)
    assert resolver is not None
    assert is_dataclass(resolver) and resolver.__dataclass_params__.frozen
    instance = resolver(None)
    with pytest.raises(FrozenInstanceError):
        instance.getenv_fn = None
    parsed = ast.parse(inspect.getsource(db.single_user_mode_enabled)).body[0]
    assert isinstance(parsed.body[-1], ast.Return)

    class Delegate:
        def enabled(self):
            return "delegated"

    monkeypatch.setattr(db, "_single_user_mode_resolver", lambda: Delegate())
    assert db.single_user_mode_enabled() == "delegated"


def test_single_user_mode_factory_receives_runtime_getenv(monkeypatch) -> None:
    _resolver_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    marker = object()
    monkeypatch.setattr(db._accounts, "SingleUserModeResolver", Recording)
    monkeypatch.setattr(db.os, "getenv", marker)
    db._single_user_mode_resolver()
    assert received == [(marker,)]


def test_single_user_mode_preserves_missing_blank_and_false_values() -> None:
    for value in (None, "", "0", "false", "no", "off", "anything"):
        assert _resolver(value).enabled() is False


def test_single_user_mode_preserves_true_spellings_case_and_whitespace() -> None:
    for value in ("1", "true", "yes", "on", " TRUE ", " Yes\t", "ON"):
        assert _resolver(value).enabled() is True
