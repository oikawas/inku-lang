"""Direct ownership coverage for bootstrap-admin password resolution."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect

import pytest

from inku_server import db
from inku_server.persistence import accounts


def _resolver_or_skip():
    resolver = getattr(accounts, "BootstrapAdminPasswordResolver", None)
    if resolver is None:
        pytest.skip("bootstrap password resolver is intentionally absent during fail-first")
    return resolver


def _resolver(values):
    return _resolver_or_skip()(lambda name, default=None: values.get(name, default))


def test_accounts_owns_bootstrap_password_resolution_and_db_delegates() -> None:
    resolver = getattr(accounts, "BootstrapAdminPasswordResolver", None)
    assert resolver is not None
    assert is_dataclass(resolver) and resolver.__dataclass_params__.frozen
    instance = resolver(None)
    with pytest.raises(FrozenInstanceError):
        instance.getenv_fn = None
    function = ast.parse(inspect.getsource(db._bootstrap_admin_password)).body[0]
    assert isinstance(function.body[-1], ast.Return)


def test_bootstrap_password_factory_receives_runtime_getenv(monkeypatch) -> None:
    _resolver_or_skip()
    received = []

    class Recording:
        def __init__(self, *args):
            received.append(args)

    marker = object()
    monkeypatch.setattr(db._accounts, "BootstrapAdminPasswordResolver", Recording)
    monkeypatch.setattr(db.os, "getenv", marker)
    db._bootstrap_admin_password_resolver()
    assert received == [(marker,)]


def test_bootstrap_password_preserves_explicit_blank_and_minimum_length() -> None:
    assert _resolver({"INKU_BOOTSTRAP_ADMIN_PASSWORD": "secure-password"}).resolve() == (
        "secure-password"
    )
    assert _resolver({"INKU_BOOTSTRAP_ADMIN_PASSWORD": ""}).resolve() is None
    with pytest.raises(
        ValueError,
        match="^INKU_BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters$",
    ):
        _resolver({"INKU_BOOTSTRAP_ADMIN_PASSWORD": "short"}).resolve()


def test_bootstrap_password_preserves_insecure_opt_in_spellings_and_fallback() -> None:
    assert _resolver({}).resolve() is None
    for value in ("1", "true", "TRUE", "yes"):
        assert _resolver({"INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN": value}).resolve() == (
            "inku-admin"
        )
    assert _resolver({"INKU_ALLOW_INSECURE_BOOTSTRAP_ADMIN": "on"}).resolve() is None
