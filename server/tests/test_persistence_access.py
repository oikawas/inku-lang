"""Direct ownership and behavior checks for persistence access predicates."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from inku_server import db
from inku_server.persistence import access
from inku_server.persistence.schema import HistoryRow, LineageEdgeRow, LineageNodeRow


ACCESS_SOURCE = Path(access.__file__).read_text(encoding="utf-8")
PREDICATES = (
    "has_permission_group",
    "_owner_actor",
    "_acl_grants",
    "_shared_with_group",
    "_same_org_group",
    "_readable_by",
    "_writable_by",
    "_owned_by",
    "_readable_node",
    "_readable_edge",
    "_readable_node_sql",
    "_readable_sql",
)


def _sql(expression, selected=HistoryRow.id) -> str:
    compiled = select(selected).where(expression).compile(
        dialect=sqlite.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def _parameter_shape(function) -> tuple[tuple[str, object], ...]:
    return tuple(
        (parameter.name, parameter.default)
        for parameter in inspect.signature(function).parameters.values()
    )


def test_access_is_the_bounded_implementation_owner() -> None:
    tree = ast.parse(ACCESS_SOURCE)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    imported_modules = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in imports
        for alias in (node.names if isinstance(node, ast.Import) else [node.names[0]])
    }
    assert imported_modules == {"__future__", "sqlalchemy", "schema"}

    sqlalchemy_import = next(
        node for node in imports if isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy"
    )
    assert {alias.name for alias in sqlalchemy_import.names} == {"and_", "or_", "select", "true"}
    schema_import = next(
        node
        for node in imports
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "schema"
    )
    assert {alias.name for alias in schema_import.names} == {
        "HistoryAclRow",
        "HistoryRow",
        "LineageEdgeRow",
        "LineageNodeRow",
        "UserAccountRow",
    }
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == set(PREDICATES)
    assert "inku_server.db" not in ACCESS_SOURCE
    assert "SessionLocal" not in ACCESS_SOURCE
    assert "create_sqlite_engine" not in ACCESS_SOURCE


def test_db_keeps_exact_facade_shapes_and_delegates_at_call_time(monkeypatch) -> None:
    expected_shapes = {
        "has_permission_group": (("actor", inspect.Parameter.empty), ("name", inspect.Parameter.empty)),
        "_owner_actor": (("user_id", inspect.Parameter.empty),),
        "_acl_grants": (("actor", inspect.Parameter.empty), ("permissions", inspect.Parameter.empty)),
        "_shared_with_group": (("actor", inspect.Parameter.empty),),
        "_same_org_group": (("actor", inspect.Parameter.empty),),
        "_readable_by": (
            ("actor", inspect.Parameter.empty),
            ("owner_column", inspect.Parameter.empty),
            ("acl_history_id", None),
        ),
        "_writable_by": (
            ("actor", inspect.Parameter.empty),
            ("owner_column", inspect.Parameter.empty),
            ("acl_history_id", None),
        ),
        "_owned_by": (("actor", inspect.Parameter.empty), ("owner_column", inspect.Parameter.empty)),
        "_readable_node": (("actor", inspect.Parameter.empty),),
        "_readable_edge": (("actor", inspect.Parameter.empty),),
        "_readable_node_sql": (("actor", inspect.Parameter.empty), ("alias", "n")),
        "_readable_sql": (
            ("actor", inspect.Parameter.empty),
            ("owner_column", inspect.Parameter.empty),
            ("acl_history_id", None),
        ),
    }
    call_args = {
        "has_permission_group": ({}, "admins"),
        "_owner_actor": ("user-1",),
        "_acl_grants": ({"id": "user-1"}, ("read",)),
        "_shared_with_group": ({"id": "user-1", "group_id": "group-1"},),
        "_same_org_group": ({"id": "user-1", "group_id": "group-1"},),
        "_readable_by": ({"id": "user-1"}, object(), None),
        "_writable_by": ({"id": "user-1"}, object(), None),
        "_owned_by": ({"id": "user-1"}, object()),
        "_readable_node": ({"id": "user-1"},),
        "_readable_edge": ({"id": "user-1"},),
        "_readable_node_sql": ({"id": "user-1"}, "n"),
        "_readable_sql": ({"id": "user-1"}, "h.user_id", None),
    }

    assert access.ACL_SUBJECT_TYPES == db.ACL_SUBJECT_TYPES == ("user", "org_group")
    assert access.ACL_PERMISSIONS == db.ACL_PERMISSIONS == ("read", "write")
    assert db.ACL_SUBJECT_TYPES is access.ACL_SUBJECT_TYPES
    assert db.ACL_PERMISSIONS is access.ACL_PERMISSIONS

    for name in PREDICATES:
        assert _parameter_shape(getattr(access, name)) == expected_shapes[name]
        assert _parameter_shape(getattr(db, name)) == expected_shapes[name]
        calls = []
        marker = object()

        def replacement(*args, **kwargs):
            calls.append((args, kwargs))
            return marker

        monkeypatch.setattr(access, name, replacement)
        assert getattr(db, name)(*call_args[name]) is marker
        assert calls == [(call_args[name], {})]


def test_permission_group_and_identity_only_actor_are_exact() -> None:
    assert access.has_permission_group({}, "admins") is False
    assert access.has_permission_group({"permission_groups": None}, "admins") is False
    assert access.has_permission_group({"permission_groups": ["admins", "users"]}, "admins") is True
    assert access.has_permission_group({"permission_groups": ["leaders"]}, "admins") is False
    assert access._owner_actor("owner-1") == {
        "id": "owner-1",
        "permission_groups": [],
        "group_id": None,
    }


def test_orm_predicates_keep_scope_acl_share_and_ownership_distinct() -> None:
    admin = {"id": "admin-1", "permission_groups": ["admins"], "group_id": None}
    leader = {"id": "leader-1", "permission_groups": ["leaders"], "group_id": "group-1"}
    groupless_leader = {"id": "leader-2", "permission_groups": ["leaders"], "group_id": None}
    user = {"id": "user-1", "permission_groups": ["users"], "group_id": "group-1"}

    assert _sql(access._readable_by(admin, HistoryRow.user_id, HistoryRow.id)).endswith("WHERE 1 = 1")
    assert _sql(access._writable_by(admin, HistoryRow.user_id, HistoryRow.id)).endswith("WHERE 1 = 1")

    leader_read = _sql(access._readable_by(leader, HistoryRow.user_id, HistoryRow.id))
    assert "user_accounts.group_id = 'group-1'" in leader_read
    assert "history_acl.permission IN ('read', 'write')" in leader_read
    assert "history.for_share = 1 AND history.share_group_id = 'group-1'" in leader_read

    groupless_read = _sql(access._readable_by(groupless_leader, HistoryRow.user_id, HistoryRow.id))
    assert "user_accounts" not in groupless_read
    assert "org_group" not in groupless_read
    assert "history.for_share" not in groupless_read
    assert "history.user_id = 'leader-2'" in groupless_read

    user_read = _sql(access._readable_by(user, HistoryRow.user_id, HistoryRow.id))
    assert "user_accounts" not in user_read
    assert "subject_type = 'org_group'" in user_read
    assert "history.for_share = 1" in user_read

    user_write = _sql(access._writable_by(user, HistoryRow.user_id, HistoryRow.id))
    assert "history.user_id = 'user-1'" in user_write
    assert "history_acl.permission IN ('write')" in user_write
    assert "history.for_share" not in user_write
    assert "user_accounts" not in user_write

    owned = _sql(access._owned_by(admin, HistoryRow.user_id))
    assert owned.endswith("WHERE history.user_id = 'admin-1'")
    assert " OR " not in owned


def test_node_follows_its_work_and_edge_follows_its_child() -> None:
    actor = {"id": "user-1", "permission_groups": ["users"], "group_id": "group-1"}
    node_sql = _sql(access._readable_node(actor), LineageNodeRow.id)
    assert "lineage_nodes.user_id = 'user-1'" in node_sql
    assert "lineage_nodes.history_id IN (SELECT history_acl.history_id" in node_sql

    edge_sql = _sql(access._readable_edge(actor), LineageEdgeRow.id)
    assert "lineage_edges.child_node_id IN (SELECT lineage_nodes.id" in edge_sql
    assert "lineage_edges.parent_node_id" not in edge_sql
    assert "lineage_nodes.history_id IN (SELECT history_acl.history_id" in edge_sql


def test_raw_sql_keeps_clause_order_and_bind_values() -> None:
    admin = {"id": "admin-1", "permission_groups": ["admins"], "group_id": None}
    leader = {"id": "leader-1", "permission_groups": ["leaders"], "group_id": "group-1"}
    groupless_leader = {"id": "leader-2", "permission_groups": ["leaders"], "group_id": None}
    user = {"id": "user-1", "permission_groups": ["users"], "group_id": "group-1"}
    groupless_user = {"id": "user-2", "permission_groups": ["users"], "group_id": None}

    assert access._readable_sql(admin, "h.user_id", "h.id") == ("1 = 1", {})
    assert access._readable_sql(leader, "h.user_id", "h.id") == (
        "(h.user_id = :acl_owner_id OR h.user_id IN (SELECT id FROM user_accounts WHERE group_id = :acl_group_id) OR h.id IN (SELECT history_id FROM history_acl WHERE permission IN ('read', 'write') AND ((subject_type = 'user' AND subject_id = :acl_owner_id) OR (subject_type = 'org_group' AND subject_id = :acl_group_id))) OR h.id IN (SELECT id FROM history WHERE for_share = 1 AND share_group_id = :acl_group_id))",
        {"acl_owner_id": "leader-1", "acl_group_id": "group-1"},
    )
    assert access._readable_sql(groupless_leader, "h.user_id", "h.id") == (
        "(h.user_id = :acl_owner_id OR h.id IN (SELECT history_id FROM history_acl WHERE permission IN ('read', 'write') AND ((subject_type = 'user' AND subject_id = :acl_owner_id))))",
        {"acl_owner_id": "leader-2"},
    )
    assert access._readable_sql(user, "h.user_id", "h.id") == (
        "(h.user_id = :acl_owner_id OR h.id IN (SELECT history_id FROM history_acl WHERE permission IN ('read', 'write') AND ((subject_type = 'user' AND subject_id = :acl_owner_id) OR (subject_type = 'org_group' AND subject_id = :acl_group_id))) OR h.id IN (SELECT id FROM history WHERE for_share = 1 AND share_group_id = :acl_group_id))",
        {"acl_owner_id": "user-1", "acl_group_id": "group-1"},
    )
    assert access._readable_sql(groupless_user, "h.user_id", "h.id") == (
        "(h.user_id = :acl_owner_id OR h.id IN (SELECT history_id FROM history_acl WHERE permission IN ('read', 'write') AND ((subject_type = 'user' AND subject_id = :acl_owner_id))))",
        {"acl_owner_id": "user-2"},
    )
    assert access._readable_node_sql(user, "node_alias") == access._readable_sql(
        user, "node_alias.user_id", "node_alias.history_id"
    )
