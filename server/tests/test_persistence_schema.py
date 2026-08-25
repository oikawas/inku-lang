from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable


SERVER_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = SERVER_ROOT / "src" / "inku_server" / "db.py"
OWNER_PATH = SERVER_ROOT / "src" / "inku_server" / "persistence" / "schema.py"
MODEL_NAMES = (
    "Base",
    "HistoryRow",
    "CoerceTraceCatalogRow",
    "LineageNodeRow",
    "LineageEdgeRow",
    "OkugakiRow",
    "HistoryAclRow",
    "UnreadWordRow",
    "UserGroupRow",
    "UserAccountRow",
    "PermissionGroupRow",
    "UserPermissionGroupRow",
    "UserSessionRow",
    "ExternalIdentityRow",
    "AppSettingRow",
)
EXPECTED_TABLE_NAMES = {
    "history",
    "coerce_trace_catalogs",
    "lineage_nodes",
    "lineage_edges",
    "okugaki",
    "history_acl",
    "unread_words",
    "user_groups",
    "user_accounts",
    "permission_groups",
    "user_permission_groups",
    "user_sessions",
    "external_identities",
    "app_settings",
}
PRE_EXTRACTION_SCHEMA_SHA256 = "6f95e2f40a2352bfbcdfad721259e2a480b93c27a876809c6c4f2f0681bf7186"


def _compiled_schema_payload(base) -> bytes:
    payload = []
    for table in base.metadata.tables.values():
        indexes = [
            str(CreateIndex(index).compile(dialect=sqlite.dialect()))
            for index in sorted(table.indexes, key=lambda item: item.name or "")
        ]
        payload.append(
            [table.name, str(CreateTable(table).compile(dialect=sqlite.dialect())), indexes]
        )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def test_orm_schema_has_one_persistence_owner_and_creates_the_same_tables():
    assert OWNER_PATH.is_file(), "persistence.schema must own the ORM declarations"

    inline_classes = {
        node.name
        for node in ast.parse(DB_PATH.read_text()).body
        if isinstance(node, ast.ClassDef)
    }
    assert inline_classes.isdisjoint(MODEL_NAMES)

    from inku_server import db
    from inku_server.persistence import schema

    for name in MODEL_NAMES:
        assert getattr(db, name) is getattr(schema, name)
    assert db.Base.metadata is schema.Base.metadata
    assert (
        hashlib.sha256(_compiled_schema_payload(schema.Base)).hexdigest()
        == PRE_EXTRACTION_SCHEMA_SHA256
    )

    engine = create_engine("sqlite:///:memory:", future=True)
    try:
        schema.Base.metadata.create_all(engine)
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLE_NAMES
    finally:
        engine.dispose()
