"""Versioned, fail-closed startup coordination for the canonical SQLite DB."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from .backup import SQLiteSnapshot, create_sqlite_snapshot
from .invariants import capture_invariants, require_integrity, verify_invariants


class MigrationStateError(RuntimeError):
    """The database is not a recognized, safely migratable state."""


class MigrationExecutionError(MigrationStateError):
    """A migration failed after a verified safety snapshot was retained."""

    def __init__(self, snapshot: SQLiteSnapshot) -> None:
        super().__init__("migration failed after the safety snapshot completed")
        self.snapshot = snapshot


MIGRATION_VERSION = 1
MIGRATION_NAME = "legacy_baseline"
_MIGRATION_MANIFEST = (
    "create-current-metadata-v1",
    "history-column-and-index-transforms-v1",
    "permission-and-owner-transforms-v1",
    "history-identity-and-lineage-transform-v1",
    "history-fts5-trigram-v1",
    "pk-and-canonical-history-invariants-v1",
)
MIGRATION_CHECKSUM = hashlib.sha256(
    json.dumps(_MIGRATION_MANIFEST, separators=(",", ":")).encode("utf-8")
).hexdigest()

_REGISTRY_DDL = """
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at INTEGER NOT NULL
)
"""
_EXCLUDED_PREFIXES = ("sqlite_", "history_fts")
PRODUCTION_STAGE0_FINGERPRINT = "ae5bc3143a1e18c5b6b6f0aeb90254bacd009c052e58b7283f68f81c7f906b6f"

# Exact fixture fingerprints are added only when a supported init_db fixture is
# characterized. Partial schemas used to test a transform helper do not belong
# here. The production Stage 0 fingerprint is the first accepted legacy shape.
ACCEPTED_LEGACY_STATES: dict[tuple[str, str], str] = {
    (PRODUCTION_STAGE0_FINGERPRINT, "complete"): "production-stage0",
    (
        "929e05c6a0b86201b4d3fd607469e38329a8858943c64185e6f4cf9fab8c8790",
        "complete",
    ): "local-development-stage0",
    (
        "c5f965b2309bea96288c56b78dd8e67dd2ab80f277b1479d34afe51c0f012e52",
        "complete",
    ): "fixture-current-without-registry",
    (
        "01f03f2602e5a98c8fa2129195e0243db1375054cfeedd28265260a0d6d27737",
        "absent",
    ): "fixture-v175",
    (
        "4e431e35915f5cf7673ca888a0e66b9f4b8ac25257a84b83274652fa85e05236",
        "absent",
    ): "fixture-pre-compose-fallback",
    (
        "74b85c989bf1166378c4b6719244607e70bf30969ec3a08ffb1a5498abccbff2",
        "absent",
    ): "fixture-pre-sketch-state",
    (
        "1b6d862a48016f52de9cdbe8965393336fbf71b87f6334965a887432587237a2",
        "absent",
    ): "fixture-pre-share",
}

_FTS_TABLES = {
    "history_fts",
    "history_fts_config",
    "history_fts_data",
    "history_fts_docsize",
    "history_fts_idx",
}
_FTS_TRIGGERS = {"history_fts_ai", "history_fts_ad", "history_fts_au"}
_FTS_SCHEMA_DIGESTS = {
    "79f29c365a5035187af3be772e32ae0cb083fb3216d19e9471dcbfd255ed4d1f",
}


@dataclass(frozen=True)
class MigrationOutcome:
    """Bounded startup evidence; paths are retained only for local recovery."""

    mode: str
    fts_enabled: bool
    fingerprint_name: str | None = None
    snapshot: SQLiteSnapshot | None = None


@dataclass(frozen=True)
class MigrationBaselineCallbacks:
    """Own the callbacks that create, seed, and migrate the startup baseline."""

    metadata: object
    session_factory: Callable[..., object]
    ensure_default_user_group: Callable[[object], object]
    ensure_permission_groups: Callable[[object], object]
    ensure_bootstrap_admin: Callable[[object], object]
    migrate_columns: Callable[..., object]
    migrate_roles_to_permission_groups: Callable[[object], object]
    assign_unowned_history_to_admin: Callable[[object], object]
    backfill_history_identity_and_lineage: Callable[[object], object]

    def create_schema(self, connection) -> None:
        self.metadata.create_all(bind=connection)

    def seed_fresh(self, connection) -> None:
        """Seed only rows required by a new, already-current database."""
        with self.session_factory(
            bind=connection,
            autocommit=False,
            autoflush=False,
        ) as session:
            self.ensure_default_user_group(session)
            self.ensure_permission_groups(session)
            self.ensure_bootstrap_admin(session)
            session.flush()

    def apply_legacy(self, connection) -> None:
        """Run the reviewed legacy transforms inside the coordinator transaction."""
        self.migrate_columns(connection, include_fts=False)
        with self.session_factory(
            bind=connection,
            autocommit=False,
            autoflush=False,
        ) as session:
            self.ensure_default_user_group(session)
            self.ensure_permission_groups(session)
            self.ensure_bootstrap_admin(session)
            # The bootstrap account must exist before the legacy role mirror is
            # converted and before orphaned works resolve their canonical owner.
            self.migrate_roles_to_permission_groups(session)
            self.assign_unowned_history_to_admin(session)
            self.backfill_history_identity_and_lineage(session)
            session.flush()


@dataclass(frozen=True)
class RenamedCatalogNameplateMigrator:
    """Point the display column at the id a renamed catalog answers to today.

    Only `catalog_id` moves. `render_color_catalog_id` is the id the work was
    DRAWN with, and the renderer hashes it into the seed that assigns each
    chromatic work color, so rewriting it would repaint the work out of its own
    unchanged snapshot -- the very silence this whole change exists to end
    (author's ruling 2026-08-09). `render_color_map` is never touched by
    anything here.

    Idempotent: after the first pass no row matches an old id any more.
    """

    renamed_catalog_ids: Mapping[str, str]
    text_fn: Callable[[str], object]

    def migrate(self, connection) -> None:
        for old_id, new_id in self.renamed_catalog_ids.items():
            try:
                connection.execute(
                    self.text_fn(
                        "UPDATE history SET catalog_id = :new_id WHERE catalog_id = :old_id"
                    ),
                    {"new_id": new_id, "old_id": old_id},
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"failed to migrate renamed color catalog nameplate: {old_id} -> {new_id}"
                ) from exc


@dataclass(frozen=True)
class LegacyHistoryFtsInstaller:
    """Install legacy history FTS only when its external content is usable.

    Focused transform fixtures can predate columns that the historical init_db
    baseline always had. They exercise the column transform only; creating an
    unusable external-content FTS table would leave a partial installation for
    the next startup to reject.
    """

    required_columns: frozenset[str]
    inspect_fn: Callable[[object], object]
    install_fn: Callable[..., bool]

    def install(self, connection) -> bool:
        history_columns = {
            column["name"]
            for column in self.inspect_fn(connection).get_columns("history")
        }
        if not self.required_columns <= history_columns:
            return False
        return self.install_fn(connection, rebuild=True)


def _canonical_schema_objects(connection: Connection) -> list[dict[str, str]]:
    rows = connection.exec_driver_sql(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'index', 'trigger', 'view') ORDER BY type, name"
    ).mappings()
    normalized: list[dict[str, str]] = []
    for row in rows:
        name = str(row["name"])
        if name.startswith(_EXCLUDED_PREFIXES):
            continue
        normalized.append(
            {
                "type": str(row["type"]).lower(),
                "name": name,
                "table": str(row["tbl_name"]),
                "sql": re.sub(r"\s+", " ", str(row["sql"] or "")).strip(),
            }
        )
    return sorted(normalized, key=lambda item: (item["type"], item["name"], item["table"]))


def schema_fingerprint(connection: Connection) -> str:
    """Return the I-370 canonical legacy schema digest."""
    payload = json.dumps(
        _canonical_schema_objects(connection),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def history_fts_state(connection: Connection) -> str:
    """Classify the optional FTS installation without repairing partial state."""
    rows = connection.exec_driver_sql(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name LIKE 'history_fts%'"
    ).mappings().all()
    tables = {str(row["name"]) for row in rows if row["type"] == "table"}
    triggers = {str(row["name"]) for row in rows if row["type"] == "trigger"}
    if not tables and not triggers:
        return "absent"
    normalized = sorted(
        (
            {
                "type": str(row["type"]).lower(),
                "name": str(row["name"]),
                "table": str(row["tbl_name"]),
                "sql": re.sub(r"\s+", " ", str(row["sql"] or "")).strip(),
            }
            for row in rows
        ),
        key=lambda item: (item["type"], item["name"], item["table"]),
    )
    digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if (
        tables == _FTS_TABLES
        and triggers == _FTS_TRIGGERS
        and digest in _FTS_SCHEMA_DIGESTS
    ):
        return "complete"
    return "partial"


def _create_registry(connection: Connection) -> None:
    connection.exec_driver_sql(_REGISTRY_DDL)


def _record_baseline(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
            "VALUES (:version, :name, :checksum, :applied_at)"
        ),
        {
            "version": MIGRATION_VERSION,
            "name": MIGRATION_NAME,
            "checksum": MIGRATION_CHECKSUM,
            "applied_at": int(time.time() * 1000),
        },
    )


def _verify_registry(connection: Connection) -> None:
    rows = connection.exec_driver_sql(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    expected = [(MIGRATION_VERSION, MIGRATION_NAME, MIGRATION_CHECKSUM)]
    if rows != expected:
        raise MigrationStateError("schema_migrations does not match the reviewed baseline")


def install_history_fts(connection: Connection, *, rebuild: bool) -> bool:
    """Install the canonical FTS objects, optionally indexing legacy rows once."""
    state = history_fts_state(connection)
    if state == "partial":
        raise MigrationStateError("history FTS objects are internally inconsistent")
    if state == "complete":
        if rebuild:
            connection.exec_driver_sql("INSERT INTO history_fts(history_fts) VALUES ('rebuild')")
        return True
    try:
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE history_fts USING fts5("
            "input, ddl, stage1_model, stage2_model, catalog_id, "
            "content='history', content_rowid='rowid', tokenize='trigram')"
        )
    except Exception:  # SQLite builds without FTS5 retain the LIKE fallback.
        return False
    trigger_sql = (
        """CREATE TRIGGER history_fts_ai AFTER INSERT ON history BEGIN
        INSERT INTO history_fts(rowid, input, ddl, stage1_model, stage2_model, catalog_id)
        VALUES (new.rowid, new.input, new.ddl, new.stage1_model, new.stage2_model, new.catalog_id);
        END""",
        """CREATE TRIGGER history_fts_ad AFTER DELETE ON history BEGIN
        INSERT INTO history_fts(history_fts, rowid, input, ddl, stage1_model, stage2_model, catalog_id)
        VALUES ('delete', old.rowid, old.input, old.ddl, old.stage1_model, old.stage2_model, old.catalog_id);
        END""",
        """CREATE TRIGGER history_fts_au AFTER UPDATE OF input, ddl, stage1_model, stage2_model, catalog_id ON history BEGIN
        INSERT INTO history_fts(history_fts, rowid, input, ddl, stage1_model, stage2_model, catalog_id)
        VALUES ('delete', old.rowid, old.input, old.ddl, old.stage1_model, old.stage2_model, old.catalog_id);
        INSERT INTO history_fts(rowid, input, ddl, stage1_model, stage2_model, catalog_id)
        VALUES (new.rowid, new.input, new.ddl, new.stage1_model, new.stage2_model, new.catalog_id);
        END""",
    )
    try:
        for statement in trigger_sql:
            connection.exec_driver_sql(statement)
        if rebuild:
            connection.exec_driver_sql("INSERT INTO history_fts(history_fts) VALUES ('rebuild')")
    except Exception as exc:
        raise MigrationStateError("history FTS installation failed after table creation") from exc
    return True


def _user_tables(connection: Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _begin_immediate(connection: Connection) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def ensure_current_schema(
    *,
    engine: Engine,
    database_path: Path | None,
    create_schema: Callable[[Connection], None],
    seed_fresh: Callable[[Connection], None],
    apply_legacy: Callable[[Connection], None],
) -> MigrationOutcome:
    """Create, verify, or migrate the canonical database exactly once."""
    with engine.connect() as connection:
        tables = _user_tables(connection)
        if not tables:
            _begin_immediate(connection)
            try:
                create_schema(connection)
                _create_registry(connection)
                seed_fresh(connection)
                fts_enabled = install_history_fts(connection, rebuild=False)
                require_integrity(connection)
                _record_baseline(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return MigrationOutcome(mode="fresh", fts_enabled=fts_enabled)

        if "schema_migrations" in tables:
            _verify_registry(connection)
            state = history_fts_state(connection)
            if state == "partial":
                raise MigrationStateError("history FTS objects are internally inconsistent")
            return MigrationOutcome(mode="current", fts_enabled=state == "complete")

        fingerprint = schema_fingerprint(connection)
        fts_state = history_fts_state(connection)
        if fts_state == "partial":
            raise MigrationStateError("history FTS objects are internally inconsistent")
        fingerprint_name = ACCEPTED_LEGACY_STATES.get((fingerprint, fts_state))
        if fingerprint_name is None:
            raise MigrationStateError(
                f"unrecognized pre-registry SQLite schema: fingerprint={fingerprint} fts={fts_state}"
            )
        require_integrity(connection)

    if database_path is None:
        raise MigrationStateError("an existing in-memory database cannot be snapshotted")
    snapshot_path = database_path.parent / "migration-backups" / (
        f"{database_path.stem}-pre-v{MIGRATION_VERSION}-{time.time_ns()}.db"
    )
    snapshot = create_sqlite_snapshot(database_path, snapshot_path)

    with engine.connect() as connection:
        _begin_immediate(connection)
        try:
            if (
                schema_fingerprint(connection) != fingerprint
                or history_fts_state(connection) != fts_state
            ):
                raise MigrationStateError("pre-registry schema changed before writer lock")
            before = capture_invariants(connection)
            create_schema(connection)
            apply_legacy(connection)
            fts_enabled = install_history_fts(connection, rebuild=True)
            verify_invariants(connection, before)
            require_integrity(connection)
            _create_registry(connection)
            _record_baseline(connection)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise MigrationExecutionError(snapshot) from exc
    return MigrationOutcome(
        mode="legacy",
        fts_enabled=fts_enabled,
        fingerprint_name=fingerprint_name,
        snapshot=snapshot,
    )
