"""Direct ownership and transaction coverage for authentication sessions."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import importlib
import importlib.util
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db

sessions = (
    importlib.import_module("inku_server.persistence.sessions")
    if importlib.util.find_spec("inku_server.persistence.sessions") is not None
    else None
)


def _store_or_skip():
    if sessions is None:
        pytest.skip("production sessions module is intentionally absent during fail-first")
    store = getattr(sessions, "SessionStore", None)
    if store is None:
        pytest.skip("production session owner is intentionally absent during fail-first")
    return store


def _store(session_factory, *, now: int = 2_000, max_age: int = 1):
    return _store_or_skip()(
        session_factory,
        lambda size: f"token-{size}",
        lambda token: f"hash:{token}",
        lambda: now,
        max_age,
        lambda row, group_name=None: {"id": row.id, "group_name": group_name},
    )


def test_persistence_sessions_owns_store_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sessions is not None, "persistence.sessions must own authentication sessions"
    store = getattr(sessions, "SessionStore", None)
    assert store is not None, "SessionStore must own authentication sessions"
    dependencies = (None, None, None, None, 1, None)
    assert is_dataclass(store) and store.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        store(*dependencies).session_factory = None

    names = (
        "create_session",
        "_session_expiry_cutoff_ms",
        "_delete_expired_sessions",
        "get_session_user",
        "delete_session",
    )
    for name in names:
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...], dict[str, object]]] = []

    class RecordingStore:
        def __init__(self, *received: object) -> None:
            self.received = received

        def __getattr__(self, name: str):
            def call(*args: object, **kwargs: object):
                calls.append((self.received, name, args, kwargs))
                return "sentinel"

            return call

    monkeypatch.setattr(db._sessions, "SessionStore", RecordingStore)
    session_factory = object()
    token_fn = object()
    hash_fn = object()
    now_fn = object()
    project_fn = object()
    monkeypatch.setattr(db, "SessionLocal", session_factory)
    monkeypatch.setattr(db.secrets, "token_urlsafe", token_fn)
    monkeypatch.setattr(db, "_hash_token", hash_fn)
    monkeypatch.setattr(db, "_now_ms", now_fn)
    monkeypatch.setattr(db, "_SESSION_MAX_AGE_SECONDS", 17)
    monkeypatch.setattr(db, "_user_to_dict", project_fn)
    expected_dependencies = (session_factory, token_fn, hash_fn, now_fn, 17, project_fn)

    assert db.create_session("user") == "sentinel"
    assert db._session_expiry_cutoff_ms(10) == "sentinel"
    assert db._delete_expired_sessions("session") == "sentinel"
    assert db.get_session_user("token") == "sentinel"
    assert db.delete_session("token") == "sentinel"
    assert calls == [
        (expected_dependencies, "create_session", ("user",), {}),
        (expected_dependencies, "session_expiry_cutoff_ms", (10,), {}),
        (expected_dependencies, "delete_expired_sessions", ("session",), {}),
        (expected_dependencies, "get_session_user", ("token",), {}),
        (expected_dependencies, "delete_session", ("token",), {}),
    ]


def test_create_preserves_token_account_prune_add_commit_and_missing_error() -> None:
    store_type = _store_or_skip()
    token_sizes: list[int] = []

    class Query:
        def __init__(self, events: list[object]) -> None:
            self.events = events

        def filter(self, *_conditions: object) -> Query:
            self.events.append("filter-expired")
            return self

        def delete(self, *, synchronize_session: bool) -> int:
            self.events.append(("prune", synchronize_session))
            return 2

    class Session:
        def __init__(self, account: object | None) -> None:
            self.account = account
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, _key: object) -> object | None:
            self.events.append("get-account")
            return self.account

        def query(self, _row_type: object) -> Query:
            return Query(self.events)

        def add(self, row: object) -> None:
            self.events.append(("add", row))

        def commit(self) -> None:
            self.events.append("commit")

    def make_store(session: Session):
        return store_type(
            lambda: session,
            lambda size: token_sizes.append(size) or "raw-token",
            lambda token: f"hashed:{token}",
            lambda: 5_000,
            1,
            lambda *_args: {},
        )

    missing = Session(None)
    with pytest.raises(ValueError, match="user not found"):
        make_store(missing).create_session("missing")
    assert token_sizes == [32]
    assert missing.events == ["get-account"]

    present = Session(object())
    assert make_store(present).create_session("user") == "raw-token"
    assert token_sizes == [32, 32]
    assert present.events[:3] == ["get-account", "filter-expired", ("prune", False)]
    added = present.events[3][1]
    assert (added.token_hash, added.user_id, added.at) == ("hashed:raw-token", "user", 5_000)
    assert present.events[4] == "commit"


def test_expiry_cutoff_and_prune_preserve_disabled_and_bulk_delete() -> None:
    store_type = _store_or_skip()

    class Query:
        def __init__(self) -> None:
            self.delete_args: list[bool] = []

        def filter(self, *_conditions: object) -> Query:
            return self

        def delete(self, *, synchronize_session: bool) -> int:
            self.delete_args.append(synchronize_session)
            return 3

    class Session:
        def __init__(self) -> None:
            self.queries = 0
            self.query_object = Query()

        def query(self, _row_type: object) -> Query:
            self.queries += 1
            return self.query_object

    disabled_session = Session()
    disabled = store_type(
        lambda: disabled_session,
        lambda _size: "token",
        str,
        lambda: 9_000,
        0,
        lambda *_args: {},
    )
    assert disabled.session_expiry_cutoff_ms() is None
    assert disabled.delete_expired_sessions(disabled_session) == 0
    assert disabled_session.queries == 0

    active_session = Session()
    active = _store(lambda: active_session, now=2_000, max_age=1)
    assert active.session_expiry_cutoff_ms() == 1_000
    assert active.session_expiry_cutoff_ms(2_500) == 1_500
    assert active.delete_expired_sessions(active_session) == 3
    assert active_session.query_object.delete_args == [False]


def test_lookup_preserves_missing_expired_orphan_and_valid_projection() -> None:
    session_row = SimpleNamespace(user_id="user", at=2_000)
    user_row = SimpleNamespace(id="user", group_id="group")
    group_row = SimpleNamespace(name="Group")

    class Session:
        def __init__(self, answers: list[object | None]) -> None:
            self.answers = answers
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, key: object) -> object | None:
            self.events.append(("get", key))
            return self.answers.pop(0)

        def delete(self, row: object) -> None:
            self.events.append(("delete", row))

        def commit(self) -> None:
            self.events.append("commit")

    missing = Session([None])
    assert _store(lambda: missing).get_session_user("raw") is None
    assert missing.events == [("get", "hash:raw")]

    expired_row = SimpleNamespace(user_id="user", at=999)
    expired = Session([expired_row])
    assert _store(lambda: expired).get_session_user("raw") is None
    assert expired.events[1:] == [("delete", expired_row), "commit"]

    orphan = Session([session_row, None])
    assert _store(lambda: orphan).get_session_user("raw") is None
    assert orphan.events[2:] == [("delete", session_row), "commit"]

    projected: list[tuple[object, str | None]] = []
    valid = Session([session_row, user_row, group_row])
    store = _store_or_skip()(
        lambda: valid,
        lambda _size: "token",
        lambda token: f"hash:{token}",
        lambda: 2_000,
        1,
        lambda row, group_name=None: projected.append((row, group_name)) or {"id": row.id},
    )
    assert store.get_session_user("raw") == {"id": "user"}
    assert projected == [(user_row, "Group")]
    assert not any(event == "commit" for event in valid.events)


def test_delete_preserves_bool_commit_and_exceptions() -> None:
    row = object()

    class Session:
        def __init__(self, answer: object | None, *, fail_get: bool = False) -> None:
            self.answer = answer
            self.fail_get = fail_get
            self.events: list[object] = []

        def __enter__(self) -> Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _row_type: object, key: object) -> object | None:
            if self.fail_get:
                raise RuntimeError("lookup failed")
            self.events.append(("get", key))
            return self.answer

        def delete(self, value: object) -> None:
            self.events.append(("delete", value))

        def commit(self) -> None:
            self.events.append("commit")

    missing = Session(None)
    assert not _store(lambda: missing).delete_session("raw")
    assert missing.events == [("get", "hash:raw")]

    present = Session(row)
    assert _store(lambda: present).delete_session("raw")
    assert present.events == [("get", "hash:raw"), ("delete", row), "commit"]

    failing = Session(None, fail_get=True)
    with pytest.raises(RuntimeError, match="lookup failed"):
        _store(lambda: failing).delete_session("raw")
