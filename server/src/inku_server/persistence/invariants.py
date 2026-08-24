"""Streaming, aggregate-only guards for an in-place SQLite migration."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.engine import Connection


class PersistenceInvariantError(RuntimeError):
    """A migration changed persistent identity or canonical artwork bytes."""


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ADDITIVE_PK_TABLES = {"lineage_nodes", "permission_groups", "user_permission_groups"}


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise PersistenceInvariantError("unexpected SQLite identifier in invariant guard")
    return f'"{value}"'


def _encode_value(value: object) -> bytes:
    if value is None:
        return b"n"
    if isinstance(value, bytes):
        payload = value
        prefix = b"b"
    elif isinstance(value, memoryview):
        payload = value.tobytes()
        prefix = b"b"
    else:
        payload = str(value).encode("utf-8")
        prefix = b"t"
    return prefix + len(payload).to_bytes(8, "big") + payload


def _hash_query(connection: Connection, statement: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    result = connection.exec_driver_sql(statement)
    while rows := result.fetchmany(512):
        for row in rows:
            digest.update(len(row).to_bytes(2, "big"))
            for value in row:
                digest.update(_encode_value(value))
            count += 1
    return count, digest.hexdigest()


def _primary_key_columns(connection: Connection, table: str) -> tuple[str, ...]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({_identifier(table)})").mappings()
    ordered = sorted(
        ((int(row["pk"]), str(row["name"])) for row in rows if int(row["pk"])),
        key=lambda item: item[0],
    )
    return tuple(name for _position, name in ordered)


@dataclass(frozen=True)
class TableIdentity:
    """Pre-migration identity aggregate for one table."""

    table: str
    primary_key: tuple[str, ...]
    temp_table: str
    count: int
    digest: str


@dataclass(frozen=True)
class InvariantEvidence:
    """Aggregate evidence retained by the migration coordinator."""

    tables: tuple[TableIdentity, ...]
    history_count: int
    history_digest: str


def capture_invariants(connection: Connection) -> InvariantEvidence:
    """Capture existing PKs in connection-local temp tables and stream hashes."""
    tables = [
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'history_fts%' AND name <> 'schema_migrations' "
            "ORDER BY name"
        )
    ]
    identities: list[TableIdentity] = []
    for index, table in enumerate(tables):
        primary_key = _primary_key_columns(connection, table)
        if not primary_key:
            continue
        quoted_columns = ", ".join(_identifier(column) for column in primary_key)
        order = ", ".join(_identifier(column) for column in primary_key)
        count, digest = _hash_query(
            connection,
            f"SELECT {quoted_columns} FROM {_identifier(table)} ORDER BY {order}",
        )
        temp_table = f"i372_pk_{index}"
        connection.exec_driver_sql(
            f"CREATE TEMP TABLE {_identifier(temp_table)} AS "
            f"SELECT {quoted_columns} FROM {_identifier(table)}"
        )
        identities.append(TableIdentity(table, primary_key, temp_table, count, digest))

    history_count = 0
    history_digest = hashlib.sha256(b"").hexdigest()
    if "history" in tables:
        history_count, history_digest = _hash_query(
            connection,
            "SELECT CAST(id AS BLOB), CAST(input AS BLOB), CAST(score AS BLOB), "
            "CAST(svg AS BLOB) FROM history ORDER BY id",
        )
    return InvariantEvidence(tuple(identities), history_count, history_digest)


def verify_invariants(connection: Connection, before: InvariantEvidence) -> None:
    """Require every old PK and every canonical history byte to survive."""
    for identity in before.tables:
        predicates = " AND ".join(
            f"current.{_identifier(column)} IS old.{_identifier(column)}"
            for column in identity.primary_key
        )
        missing = connection.exec_driver_sql(
            f"SELECT count(*) FROM {_identifier(identity.temp_table)} AS old "
            f"WHERE NOT EXISTS (SELECT 1 FROM {_identifier(identity.table)} AS current "
            f"WHERE {predicates})"
        ).scalar_one()
        if int(missing):
            raise PersistenceInvariantError(
                f"migration removed primary keys from {identity.table}: count={int(missing)}"
            )
        columns = ", ".join(_identifier(column) for column in identity.primary_key)
        order = ", ".join(_identifier(column) for column in identity.primary_key)
        after_count, after_digest = _hash_query(
            connection,
            f"SELECT {columns} FROM {_identifier(identity.table)} ORDER BY {order}",
        )
        if identity.table not in _ADDITIVE_PK_TABLES and (
            after_count != identity.count or after_digest != identity.digest
        ):
            raise PersistenceInvariantError(
                f"migration changed primary-key identity for {identity.table}"
            )

    if any(identity.table == "history" for identity in before.tables):
        after_count, after_digest = _hash_query(
            connection,
            "SELECT CAST(id AS BLOB), CAST(input AS BLOB), CAST(score AS BLOB), "
            "CAST(svg AS BLOB) FROM history ORDER BY id",
        )
        if after_count != before.history_count or after_digest != before.history_digest:
            raise PersistenceInvariantError("migration changed canonical history bytes")


def require_integrity(connection: Connection) -> None:
    """Require bounded SQLite structural and foreign-key integrity results."""
    quick_check = connection.exec_driver_sql("PRAGMA quick_check").fetchall()
    if quick_check != [("ok",)]:
        raise PersistenceInvariantError("SQLite quick_check failed")
    foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchmany(1)
    if foreign_keys:
        raise PersistenceInvariantError("SQLite foreign_key_check failed")
