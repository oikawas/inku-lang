"""Direct ownership and transaction coverage for external identities."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db

identities = (
    importlib.import_module("inku_server.persistence.identities")
    if importlib.util.find_spec("inku_server.persistence.identities") is not None
    else None
)


def _store_or_skip():
    if identities is None:
        pytest.skip("production identities module is intentionally absent during fail-first")
    store = getattr(identities, "ExternalIdentityStore", None)
    if store is None:
        pytest.skip("production external-identity owner is intentionally absent during fail-first")
    return store


def test_persistence_identities_owns_store_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert identities is not None, "persistence.identities must own external identities"
    store = getattr(identities, "ExternalIdentityStore", None)
    assert store is not None, "ExternalIdentityStore must own external identities"
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(None, None, None, None).session_factory = None

    for name in ("link_external_identity", "get_user_by_external_identity"):
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...], dict[str, object]]] = []

    class RecordingStore:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object, **kwargs: object):
                calls.append((self.dependencies, name, args, kwargs))
                return "sentinel"

            return call

    monkeypatch.setattr(db._identities, "ExternalIdentityStore", RecordingStore)
    session_factory = object()
    uuid_fn = object()
    now_fn = object()
    project_fn = object()
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db.uuid, "uuid4", uuid_fn)
    monkeypatch.setattr(db, "_now_ms", now_fn)
    monkeypatch.setattr(db, "_user_to_dict", project_fn)
    dependencies = (session_factory, uuid_fn, now_fn, project_fn)

    assert db.link_external_identity(
        "user", provider="provider", subject="subject", email="email"
    ) == "sentinel"
    assert db.get_user_by_external_identity("provider", "subject") == "sentinel"
    assert calls == [
        (
            dependencies,
            "link_external_identity",
            ("user",),
            {"provider": "provider", "subject": "subject", "email": "email"},
        ),
        (dependencies, "get_user_by_external_identity", ("provider", "subject"), {}),
    ]


def test_link_validates_before_session_and_preserves_projection_transaction() -> None:
    store_type = _store_or_skip()

    def fail_if_opened() -> None:
        raise AssertionError("invalid identity input must not open a session")

    validating = store_type(fail_if_opened, lambda: "uuid", lambda: 10, lambda *_args: {})
    for provider in ("", "   ", "p" * 65):
        with pytest.raises(ValueError, match="invalid identity provider"):
            validating.link_external_identity("user", provider=provider, subject="subject")
    for subject in ("", "   ", "s" * 513):
        with pytest.raises(ValueError, match="invalid external subject"):
            validating.link_external_identity("user", provider="provider", subject=subject)

    class Session:
        def __init__(self, account: object | None) -> None:
            self.account = account
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, key: object) -> object | None:
            self.events.append(("get", key))
            return self.account

        def add(self, row: object) -> None:
            self.events.append(("add", row))

        def commit(self) -> None:
            self.events.append("commit")

    uuid_calls: list[bool] = []
    missing = Session(None)
    missing_store = store_type(
        lambda: missing,
        lambda: uuid_calls.append(True) or "uuid",
        lambda: 10,
        lambda *_args: {},
    )
    with pytest.raises(ValueError, match="user not found"):
        missing_store.link_external_identity("missing", provider="provider", subject="subject")
    assert uuid_calls == []
    assert missing.events == [("get", "missing")]

    present = Session(object())
    linked = store_type(
        lambda: present,
        lambda: "uuid-1",
        lambda: 20,
        lambda *_args: {},
    ).link_external_identity(
        "user",
        provider=" Google ",
        subject=" subject-1 ",
        email=" address@example.test ",
    )
    assert present.events[0] == ("get", "user")
    row = present.events[1][1]
    assert (row.id, row.user_id, row.provider, row.subject) == (
        "uuid-1", "user", "google", "subject-1"
    )
    assert (row.email, row.at) == ("address@example.test", 20)
    assert present.events[2] == "commit"
    assert linked == {
        "id": "uuid-1",
        "user_id": "user",
        "provider": "google",
        "subject": "subject-1",
        "email": "address@example.test",
        "at": 20,
    }


def test_lookup_preserves_normalization_missing_orphan_and_group_projection() -> None:
    store_type = _store_or_skip()
    identity = SimpleNamespace(user_id="user")
    user = SimpleNamespace(id="user", group_id="group")
    group = SimpleNamespace(name="Group")

    class Query:
        def __init__(self, answer: object | None) -> None:
            self.answer = answer
            self.values: list[object] = []

        def filter(self, *conditions: object) -> Query:
            self.values = [condition.right.value for condition in conditions]
            return self

        def first(self) -> object | None:
            return self.answer

    class Session:
        def __init__(self, identity_answer: object | None, gets: list[object | None]) -> None:
            self.query_object = Query(identity_answer)
            self.gets = gets

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> Query:
            return self.query_object

        def get(self, _row_type: object, _key: object) -> object | None:
            return self.gets.pop(0)

    missing = Session(None, [])
    store = store_type(lambda: missing, lambda: "uuid", lambda: 10, lambda *_args: {})
    assert store.get_user_by_external_identity(" GOOGLE ", " subject ") is None
    assert missing.query_object.values == ["google", "subject"]

    orphan = Session(identity, [None])
    store = store_type(lambda: orphan, lambda: "uuid", lambda: 10, lambda *_args: {})
    assert store.get_user_by_external_identity("google", "subject") is None

    projected: list[tuple[object, str | None]] = []
    valid = Session(identity, [user, group])
    store = store_type(
        lambda: valid,
        lambda: "uuid",
        lambda: 10,
        lambda row, group_name=None: projected.append((row, group_name)) or {"id": row.id},
    )
    assert store.get_user_by_external_identity("google", "subject") == {"id": "user"}
    assert projected == [(user, "Group")]


def test_link_and_lookup_exceptions_propagate() -> None:
    store_type = _store_or_skip()

    class Query:
        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> object:
            raise RuntimeError("query failed")

    class Session:
        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, _key: object) -> object:
            return object()

        def add(self, _row: object) -> None:
            return None

        def commit(self) -> None:
            raise RuntimeError("commit failed")

        def query(self, _row_type: object) -> Query:
            return Query()

    store = store_type(Session, lambda: "uuid", lambda: 10, lambda *_args: {})
    with pytest.raises(RuntimeError, match="commit failed"):
        store.link_external_identity("user", provider="provider", subject="subject")
    with pytest.raises(RuntimeError, match="query failed"):
        store.get_user_by_external_identity("provider", "subject")
