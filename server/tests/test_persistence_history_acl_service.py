"""Direct ownership coverage for history ACL operations."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
from types import SimpleNamespace

import pytest

from inku_server import db
from inku_server.persistence import access


def _service_or_skip():
    service = getattr(access, "HistoryAclService", None)
    if service is None:
        pytest.skip("production ACL owner is intentionally absent during fail-first")
    return service


def test_persistence_access_owns_acl_service_and_db_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = getattr(access, "HistoryAclService", None)
    assert service is not None, "HistoryAclService must own history ACL operations"
    assert is_dataclass(service) and service.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        service(None, None, None).session_factory = None

    assert db.ACL_SUBJECT_TYPES is access.ACL_SUBJECT_TYPES
    assert db.ACL_PERMISSIONS is access.ACL_PERMISSIONS
    facade_names = (
        "_acl_to_dict",
        "_may_share",
        "_validated_acl_entries",
        "list_history_acl",
        "replace_history_acl",
        "grant_history_acl",
        "revoke_history_acl",
        "_delete_acl_for_histories",
    )
    for name in facade_names:
        facade = ast.parse(inspect.getsource(getattr(db, name))).body[0]
        assert isinstance(facade, ast.FunctionDef)
        assert len(facade.body) == 1 and isinstance(facade.body[0], ast.Return)

    calls: list[tuple[tuple[object, ...], str, tuple[object, ...]]] = []

    class RecordingService:
        def __init__(self, *dependencies: object) -> None:
            self.dependencies = dependencies

        def __getattr__(self, name: str):
            def call(*args: object):
                calls.append((self.dependencies, name, args))
                return "sentinel"

            return call

    monkeypatch.setattr(db._access, "HistoryAclService", RecordingService)
    dependencies = (object(), object(), object())
    for name, dependency in zip(("SessionLocal", "_actor_of", "_now_ms"), dependencies, strict=True):
        monkeypatch.setattr(db, name, dependency)
    assert db.list_history_acl("actor", "item") == "sentinel"
    assert calls == [(dependencies, "list_history_acl", ("actor", "item"))]


def test_acl_validation_preserves_messages_order_and_last_duplicate_wins() -> None:
    _service_or_skip()
    assert access.validated_acl_entries([
        {"subject_type": "user", "subject_id": "a", "permission": "read"},
        {"subject_type": "org_group", "subject_id": "g", "permission": "read"},
        {"subject_type": "user", "subject_id": "a", "permission": "write"},
    ]) == [("user", "a", "write"), ("org_group", "g", "read")]

    for entry, message in (
        ({"subject_type": "bad", "subject_id": "a", "permission": "read"}, "invalid subject_type: bad"),
        ({"subject_type": "user", "subject_id": "a", "permission": "bad"}, "invalid permission: bad"),
        ({"subject_type": "user", "subject_id": "", "permission": "read"}, "subject_id is required"),
    ):
        with pytest.raises(ValueError, match=message):
            access.validated_acl_entries([entry])


def test_may_share_keeps_admin_and_owner_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    owned_checks: list[str] = []

    class Query:
        def __init__(self, result: object | None) -> None:
            self.result = result

        def filter(self, *_conditions: object) -> Query:
            return self

        def first(self) -> object | None:
            return self.result

    class Session:
        def __init__(self, result: object | None) -> None:
            self.result = result

        def query(self, _row_type: object) -> Query:
            return Query(self.result)

    monkeypatch.setattr(access, "has_permission_group", lambda actor, name: name == "admins" and actor["admin"])
    monkeypatch.setattr(
        access,
        "_owned_by",
        lambda actor, _column: owned_checks.append(actor["id"]) or object(),
    )

    assert access.may_share({"id": "admin", "admin": True}, Session(object()), "item")
    assert not access.may_share({"id": "admin", "admin": True}, Session(None), "item")
    assert owned_checks == []
    assert access.may_share({"id": "owner", "admin": False}, Session(object()), "item")
    assert not access.may_share({"id": "leader-or-grantee", "admin": False}, Session(None), "item")
    assert owned_checks == ["owner", "leader-or-grantee"]


def test_acl_service_preserves_list_order_replace_commit_and_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_type = _service_or_skip()
    monkeypatch.setattr(access, "may_share", lambda *_args: True)
    first = SimpleNamespace(
        id="acl-1", history_id="item", subject_type="user", subject_id="a", permission="read", at=1
    )
    second = SimpleNamespace(
        id="acl-2", history_id="item", subject_type="org_group", subject_id="g", permission="write", at=2
    )
    order_calls: list[tuple[object, ...]] = []

    class ListQuery:
        def filter(self, *_conditions: object) -> ListQuery:
            return self

        def order_by(self, *columns: object) -> ListQuery:
            order_calls.append(columns)
            return self

        def all(self) -> list[object]:
            return [first, second]

    class ListSession:
        def __enter__(self) -> ListSession:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> ListQuery:
            return ListQuery()

    service = service_type(ListSession, lambda user_id: {"id": user_id}, lambda: 77)
    assert [entry["subject_id"] for entry in service.list_history_acl("owner", "item")] == ["a", "g"]
    assert len(order_calls) == 1 and len(order_calls[0]) == 2

    kept = SimpleNamespace(subject_type="user", subject_id="a", permission="read", at=1)
    stale = SimpleNamespace(subject_type="user", subject_id="b", permission="read", at=1)
    added: list[object] = []
    deleted: list[object] = []
    commits: list[str] = []

    class ReplaceQuery:
        def filter(self, *_conditions: object) -> ReplaceQuery:
            return self

        def all(self) -> list[object]:
            return [kept, stale]

    class ReplaceSession:
        def __enter__(self) -> ReplaceSession:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def query(self, _row_type: object) -> ReplaceQuery:
            return ReplaceQuery()

        def add(self, row: object) -> None:
            added.append(row)

        def delete(self, row: object) -> None:
            deleted.append(row)

        def commit(self) -> None:
            commits.append("commit")

    service = service_type(ReplaceSession, lambda user_id: {"id": user_id}, lambda: 77)
    object.__setattr__(service, "list_history_acl", lambda *_args: ["after"])
    assert service.replace_history_acl("owner", "item", [
        {"subject_type": "user", "subject_id": "a", "permission": "write"},
        {"subject_type": "org_group", "subject_id": "new", "permission": "read"},
    ]) == ["after"]
    assert (kept.permission, kept.at) == ("write", 77)
    assert deleted == [stale]
    assert commits == ["commit"]
    assert len(added) == 1
    assert (added[0].history_id, added[0].subject_type, added[0].subject_id, added[0].permission, added[0].at) == (
        "item", "org_group", "new", "read", 77,
    )

    class CommitError(RuntimeError):
        pass

    class RaisingSession(ReplaceSession):
        def commit(self) -> None:
            raise CommitError("commit failed")

    failing_service = service_type(RaisingSession, lambda user_id: {"id": user_id}, lambda: 88)
    with pytest.raises(CommitError, match="commit failed"):
        failing_service.replace_history_acl("owner", "item", [])


def test_acl_service_composes_grant_revoke_and_cleanup_without_widening() -> None:
    service_type = _service_or_skip()
    events: list[object] = []

    class Query:
        def filter(self, *conditions: object) -> Query:
            events.append(("filter", conditions))
            return self

        def delete(self, *, synchronize_session: bool) -> int:
            events.append(("delete", synchronize_session))
            return 1

    class Session:
        def query(self, row_type: object) -> Query:
            events.append(("query", row_type))
            return Query()

    service = service_type(None, None, None)
    service.delete_acl_for_histories(Session(), [])
    assert events == []
    service.delete_acl_for_histories(Session(), ["one", "two"])
    assert events[-1] == ("delete", False)

    object.__setattr__(service, "list_history_acl", lambda *_args: [
        {"subject_type": "user", "subject_id": "a", "permission": "read"},
        {"subject_type": "user", "subject_id": "b", "permission": "read"},
    ])
    replaced: list[list[dict]] = []
    object.__setattr__(service, "replace_history_acl", lambda _u, _i, entries: replaced.append(entries) or entries)
    service.grant_history_acl("u", "i", "user", "a", "write")
    assert replaced[-1] == [
        {"subject_type": "user", "subject_id": "b", "permission": "read"},
        {"subject_type": "user", "subject_id": "a", "permission": "write"},
    ]
    service.revoke_history_acl("u", "i", "user", "b")
    assert replaced[-1] == [
        {"subject_type": "user", "subject_id": "a", "permission": "read"},
    ]
