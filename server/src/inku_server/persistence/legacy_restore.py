"""Restore recognized old SQLite data into a new, explicit v3 copy."""

from __future__ import annotations

import sys
from pathlib import Path

from . import legacy_v3_migrations as frozen
from . import legacy_v3_schema as schema
from .backup import create_sqlite_snapshot
from .ddl_migration import DdlMigrationError, _database, _engine, _require_v3

# Exact physical baselines made from the frozen metadata at each registry
# version. Older registered backups with a different physical shape require
# characterization before admission, just as pre-registry backups do.
_REGISTERED_FINGERPRINTS = {
    "previous": "436fe490265edf792d0c0393a7959442d32612ef7e11694ebeec36c369df8831",
    "v1": "8f8c6fd2aab62daffc1266fef1e1fb2e4b78600628e5154f6f56c4a5250f4944",
}


def _require_source(connection) -> None:
    tables = frozen._user_tables(connection)
    if not tables:
        raise DdlMigrationError("empty databases are not legacy restoration sources")
    fingerprint = frozen.schema_fingerprint(connection)
    if "schema_migrations" in tables:
        state = frozen._verify_registry(connection)
        if state == "current":
            _require_v3(connection)
        elif _REGISTERED_FINGERPRINTS.get(state) != fingerprint:
            raise DdlMigrationError("unrecognized registered restoration source fingerprint")
    elif (fingerprint, frozen.history_fts_state(connection)) not in frozen.ACCEPTED_LEGACY_STATES:
        raise DdlMigrationError("unrecognized pre-registry restoration source")
    if frozen.history_fts_state(connection) == "partial":
        raise DdlMigrationError("partial FTS is not a restoration source")
    frozen.require_integrity(connection)


def restore_copy(source: Path, destination: Path) -> dict:
    """Keep the original; execute the old adapter only in the new copy.

    This entry runs in the operator's standalone CLI, never beside an API
    thread. The old ORM is temporarily supplied to the existing callback
    façade; each callback receives the copy's transaction explicitly.
    """
    source = _database(source)
    if (not destination.is_absolute() or destination != destination.resolve() or
            destination.exists() or destination.is_symlink() or not destination.parent.is_dir()):
        raise DdlMigrationError("restoration requires a new canonical copy in an existing directory")
    probe = _engine(source, readonly=True)
    try:
        with probe.connect() as connection:
            _require_source(connection)
    finally:
        probe.dispose()
    snapshot = create_sqlite_snapshot(source, destination)
    # Importing this façade constructs no database and starts no services.
    from inku_server import db
    from .schema import HistoryRow as CurrentHistoryRow
    substitutions = []
    for name, module in tuple(sys.modules.items()):
        if name.startswith("inku_server") and getattr(module, "HistoryRow", None) is CurrentHistoryRow:
            substitutions.append((module, CurrentHistoryRow))
            module.HistoryRow = schema.HistoryRow
    # New read projections may ask for the factual origin; it did not exist
    # in the frozen schema and must remain unknown during the old phase.
    schema.HistoryRow.ddl_source_origin = None
    engine = _engine(destination, readonly=False)
    try:
        with engine.connect() as connection:
            _require_source(connection)
        callbacks = frozen.MigrationBaselineCallbacks(
            schema.Base.metadata, db.Session, db._ensure_default_user_group,
            db._ensure_permission_groups, db._ensure_bootstrap_admin, db._migrate_columns,
            db._migrate_roles_to_permission_groups, db._assign_unowned_history_to_admin,
            db._backfill_history_identity_and_lineage,
        )
        outcome = frozen.ensure_current_schema(
            engine=engine, database_path=destination, create_schema=callbacks.create_schema,
            seed_fresh=callbacks.seed_fresh, apply_legacy=callbacks.apply_legacy,
        )
        with engine.connect() as connection:
            fingerprint = frozen.schema_fingerprint(connection)
            _require_v3(connection, restored_fingerprint=fingerprint)
        return {"source": str(source), "database": str(destination), "mode": outcome.mode,
                "source_preserved": True, "version": frozen.MIGRATION_VERSION,
                "copy_bytes": snapshot.size_bytes, "fingerprint": fingerprint,
                "backup": str(outcome.snapshot.path) if outcome.snapshot else None}
    finally:
        engine.dispose()
        del schema.HistoryRow.ddl_source_origin
        for module, original in substitutions:
            module.HistoryRow = original
