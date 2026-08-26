"""Direct ownership coverage for history group-share writes."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, is_dataclass
import inspect
import textwrap
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from inku_server import db
from inku_server.persistence import history
from inku_server.persistence.schema import Base, HistoryAclRow, HistoryRow, UserGroupRow


def _row(
    item_id: str,
    user_id: str | None,
    *,
    for_share: int = 0,
    share_group_id: str | None = None,
) -> HistoryRow:
    return HistoryRow(
        id=item_id,
        user_id=user_id,
        at=1,
        input="work",
        score="{}",
        svg="<svg/>",
        for_share=for_share,
        share_group_id=share_group_id,
    )


def _project(row: HistoryRow) -> dict:
    return {
        "id": row.id,
        "for_share": bool(row.for_share),
        "share_group_id": row.share_group_id,
        "input": row.input,
    }


_FORBIDDEN_HISTORY_IMPORT_PARTS = {
    "api_core",
    "config",
    "db",
    "engine",
    "lineage",
    "renderer",
    "render_engines",
    "router",
    "search",
    "share",
    "share_policy",
}


def _import_targets(source: str) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            module_prefix = f"{prefix}{node.module}." if node.module else prefix
            targets.update(f"{module_prefix}{alias.name}" for alias in node.names)
    return targets


def _is_forbidden_history_import(target: str) -> bool:
    return bool(set(target.lstrip(".").split(".")) & _FORBIDDEN_HISTORY_IMPORT_PARTS)


def test_history_share_writer_owns_the_write_and_db_delegates() -> None:
    owner = getattr(history, "HistoryShareWriter", None)
    assert owner is not None, "HistoryShareWriter must own group-share writes"
    assert is_dataclass(owner)
    assert owner.__dataclass_params__.frozen
    with pytest.raises(FrozenInstanceError):
        owner(None, None, None, None).session_factory = None

    assert str(inspect.signature(owner.set_item_for_share)) == (
        "(self, user_id: 'str', item_id: 'str', for_share: 'bool', "
        "share_group_id: 'str | None' = None) -> 'dict | None'"
    )
    assert str(inspect.signature(db.set_item_for_share)) == (
        "(user_id: 'str', item_id: 'str', for_share: 'bool', "
        "share_group_id: 'str | None' = None) -> 'dict | None'"
    )
    facade_tree = ast.parse(inspect.getsource(db.set_item_for_share))
    facade = facade_tree.body[0]
    assert isinstance(facade, ast.FunctionDef)
    assert len(facade.body) == 1
    assert isinstance(facade.body[0], ast.Return)
    facade_source = inspect.getsource(db.set_item_for_share)
    assert "_history.HistoryShareWriter(" in facade_source
    assert "SessionLocal, _actor_of, _row_to_dict, has_permission_group" in facade_source
    assert ").set_item_for_share(user_id, item_id, for_share, share_group_id)" in facade_source
    assert "session.query" not in facade_source

    owner_source = inspect.getsource(owner.set_item_for_share)
    owner_tree = ast.parse(textwrap.dedent(owner_source))
    writable_calls = [
        node
        for node in ast.walk(owner_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "access"
        and node.func.attr == "_writable_by"
    ]
    assert len(writable_calls) == 1
    writable = writable_calls[0]
    assert len(writable.args) == 3
    assert ast.unparse(writable.args[0]) == "actor"
    assert ast.unparse(writable.args[1]) == "HistoryRow.user_id"
    assert ast.unparse(writable.args[2]) == "HistoryRow.id"
    assert "Only a NAMED group is checked" in owner_source
    assert "Dropping the bit leaves the destination" in owner_source

    imported_modules = _import_targets(inspect.getsource(history))
    assert all(not _is_forbidden_history_import(module) for module in imported_modules)
    assert ".access" in imported_modules
    assert ".schema.HistoryRow" in imported_modules
    assert ".schema.UserGroupRow" in imported_modules
    assert any(
        _is_forbidden_history_import(target)
        for target in _import_targets("from inku_server import db as compatibility_facade")
    )


def test_share_facade_resolves_dependencies_at_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class RecordingWriter:
        def __init__(self, *dependencies: object) -> None:
            calls.append(("dependencies", dependencies))

        def set_item_for_share(self, *arguments: object) -> dict:
            calls.append(("share", arguments))
            return {"delegated": True}

    first_dependencies = (object(), object(), object(), object())
    second_dependencies = (object(), object(), object(), object())
    monkeypatch.setattr(db._history, "HistoryShareWriter", RecordingWriter)
    monkeypatch.setattr(db, "SessionLocal", first_dependencies[0])
    monkeypatch.setattr(db, "_actor_of", first_dependencies[1])
    monkeypatch.setattr(db, "_row_to_dict", first_dependencies[2])
    monkeypatch.setattr(db, "has_permission_group", first_dependencies[3])
    assert db.set_item_for_share("first-user", "first-item", True) == {"delegated": True}
    monkeypatch.setattr(db, "SessionLocal", second_dependencies[0])
    monkeypatch.setattr(db, "_actor_of", second_dependencies[1])
    monkeypatch.setattr(db, "_row_to_dict", second_dependencies[2])
    monkeypatch.setattr(db, "has_permission_group", second_dependencies[3])
    assert db.set_item_for_share("second-user", "second-item", False, "named-group") == {
        "delegated": True
    }
    assert calls == [
        ("dependencies", first_dependencies),
        ("share", ("first-user", "first-item", True, None)),
        ("dependencies", second_dependencies),
        ("share", ("second-user", "second-item", False, "named-group")),
    ]


def test_share_writer_preserves_real_sqlalchemy_access_and_destination_state() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    actors = {
        "owner": {"id": "owner", "permission_groups": [], "group_id": "owner-group"},
        "admin": {"id": "admin", "permission_groups": ["admins"], "group_id": None},
        "leader": {"id": "leader", "permission_groups": ["leaders"], "group_id": "owner-group"},
        "reader": {"id": "reader", "permission_groups": [], "group_id": "owner-group"},
        "writer": {"id": "writer", "permission_groups": [], "group_id": "owner-group"},
        "other": {"id": "other", "permission_groups": [], "group_id": "other-group"},
        "loner": {"id": "loner", "permission_groups": [], "group_id": None},
    }
    with sessions() as session:
        session.add_all(
            [
                UserGroupRow(id="owner-group", name="owner", at=1),
                UserGroupRow(id="target-group", name="target", at=1),
                UserGroupRow(id="stored-group", name="stored", at=1),
                _row("fresh", "owner"),
                _row("stored", "owner", share_group_id="stored-group"),
                _row("write", "owner"),
                _row("nullable", None, share_group_id="stored-group"),
                _row("lonely", "loner"),
            ]
        )
        session.add_all(
            [
                HistoryAclRow(
                    id="read-acl", history_id="fresh", subject_type="user", subject_id="reader", permission="read", at=1
                ),
                HistoryAclRow(
                    id="write-acl", history_id="write", subject_type="user", subject_id="writer", permission="write", at=1
                ),
            ]
        )
        session.commit()

    writer = history.HistoryShareWriter(
        sessions,
        actors.__getitem__,
        _project,
        lambda actor, group: group in actor["permission_groups"],
    )
    assert writer.set_item_for_share("owner", "fresh", True) == {
        "id": "fresh",
        "for_share": True,
        "share_group_id": "owner-group",
        "input": "work",
    }
    assert writer.set_item_for_share("writer", "write", True)["share_group_id"] == "owner-group"
    assert writer.set_item_for_share("admin", "fresh", True, "target-group")["share_group_id"] == "target-group"
    assert writer.set_item_for_share("reader", "fresh", True) is None
    assert writer.set_item_for_share("leader", "fresh", True) is None
    assert writer.set_item_for_share("other", "fresh", True) is None
    assert writer.set_item_for_share("owner", "missing", True) is None
    assert writer.set_item_for_share("admin", "nullable", True) == {
        "id": "nullable",
        "for_share": True,
        "share_group_id": "stored-group",
        "input": "work",
    }

    assert writer.set_item_for_share("owner", "fresh", False)["share_group_id"] == "target-group"
    assert writer.set_item_for_share("owner", "fresh", True)["share_group_id"] == "target-group"
    assert writer.set_item_for_share("owner", "stored", True)["share_group_id"] == "stored-group"
    assert writer.set_item_for_share("admin", "stored", True, "target-group")["share_group_id"] == "target-group"


def test_share_writer_refusals_do_not_commit_and_keep_exact_errors() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    actors = {
        "owner": {"id": "owner", "permission_groups": [], "group_id": "owner-group"},
        "admin": {"id": "admin", "permission_groups": ["admins"], "group_id": None},
        "loner": {"id": "loner", "permission_groups": [], "group_id": None},
    }
    with sessions() as session:
        session.add(UserGroupRow(id="owner-group", name="owner", at=1))
        session.add_all([_row("owned", "owner"), _row("lonely", "loner")])
        session.commit()

    commits: list[str] = []

    class TrackingSession:
        def __init__(self) -> None:
            self.session = sessions()

        def __enter__(self) -> "TrackingSession":
            self.session.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self.session.__exit__(*args)

        def __getattr__(self, name: str) -> object:
            return getattr(self.session, name)

        def commit(self) -> None:
            commits.append("commit")
            self.session.commit()

    writer = history.HistoryShareWriter(
        TrackingSession,
        actors.__getitem__,
        _project,
        lambda actor, group: group in actor["permission_groups"],
    )
    with pytest.raises(PermissionError, match="^only administrators may share a work outside their own group$"):
        writer.set_item_for_share("owner", "owned", True, "external")
    with pytest.raises(ValueError, match="^this work has no organisation group to be shared with$"):
        writer.set_item_for_share("loner", "lonely", True)
    with pytest.raises(ValueError, match="^no such organisation group: missing$"):
        writer.set_item_for_share("admin", "owned", True, "missing")
    assert commits == []
    with sessions() as session:
        assert _project(session.get(HistoryRow, "owned")) == {
            "id": "owned",
            "for_share": False,
            "share_group_id": None,
            "input": "work",
        }
        assert _project(session.get(HistoryRow, "lonely"))["for_share"] is False


def test_share_writer_preserves_lookup_timing_order_and_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    row = SimpleNamespace(id="ordered", user_id="owner", for_share=0, share_group_id=None, input="keep")

    class Query:
        def filter(self, *clauses: object) -> "Query":
            events.append("filter")
            return self

        def first(self) -> SimpleNamespace:
            events.append("first")
            return row

    class Session:
        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def query(self, model: object) -> Query:
            events.append("query")
            return Query()

        def get(self, model: object, target: str) -> object:
            events.append(f"get:{target}")
            return object()

        def commit(self) -> None:
            events.append("commit")

        def refresh(self, refreshed: object) -> None:
            assert refreshed is row
            events.append("refresh")

    def actor_of(user_id: str) -> dict:
        events.append(f"actor:{user_id}")
        return {"id": user_id, "group_id": "owner-group", "permission_groups": []}

    monkeypatch.setattr(history.access, "_writable_by", lambda *arguments: events.append("writable") or True)
    writer = history.HistoryShareWriter(
        lambda: Session(),
        actor_of,
        lambda value: events.append("project") or _project(value),
        lambda actor, group: False,
    )
    assert writer.set_item_for_share("writer", "ordered", True) == {
        "id": "ordered",
        "for_share": True,
        "share_group_id": "owner-group",
        "input": "keep",
    }
    assert events == [
        "actor:writer",
        "query",
        "writable",
        "filter",
        "first",
        "actor:owner",
        "get:owner-group",
        "commit",
        "refresh",
        "project",
    ]

    events.clear()
    assert writer.set_item_for_share("writer", "ordered", False)["share_group_id"] == "owner-group"
    assert events == [
        "actor:writer",
        "query",
        "writable",
        "filter",
        "first",
        "commit",
        "refresh",
        "project",
    ]

    failing = history.HistoryShareWriter(
        lambda: (_ for _ in ()).throw(RuntimeError("session failure")),
        actor_of,
        _project,
        lambda actor, group: False,
    )
    with pytest.raises(RuntimeError, match="^session failure$"):
        failing.set_item_for_share("writer", "ordered", True)
    resolver_failing = history.HistoryShareWriter(
        lambda: Session(),
        lambda user_id: (_ for _ in ()).throw(RuntimeError("actor failure")),
        _project,
        lambda actor, group: False,
    )
    with pytest.raises(RuntimeError, match="^actor failure$"):
        resolver_failing.set_item_for_share("writer", "ordered", True)
