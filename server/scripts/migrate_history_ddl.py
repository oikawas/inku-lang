"""Inspect or manually unify one explicit SQLite history database.

Stop API writes before --apply. This command selects text without providers,
compilers, rendering, or normal application startup. A safety backup remains
beside the database; a failure never retries itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from inku_server.persistence.backup import SQLiteSnapshotError
from inku_server.persistence.ddl_migration import (
    DdlMigrationError, inspect_database, migrate_history_ddl,
)
from inku_server.persistence.migrations import MigrationStateError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expect-version", type=int, default=3)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--expect-fingerprint")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--restore-copy", type=Path,
                        help="restore a reviewed older database to this new copy before unification")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.dry_run and (args.report or args.restore_copy):
        parser.error("--dry-run does not create a report or restoration copy")
    options = dict(source_commit=args.source_commit, expect_version=args.expect_version,
                   expected_fingerprint=args.expect_fingerprint)
    try:
        restoration = None
        if args.restore_copy:
            from inku_server.persistence.legacy_restore import restore_copy
            restoration = restore_copy(args.database, args.restore_copy)
            args.database = args.restore_copy
            options["_restored_fingerprint"] = restoration["fingerprint"]
            options["_restoration"] = restoration
        report = (inspect_database(args.database, **options) if args.dry_run else
                  migrate_history_ddl(args.database, report_path=args.report, **options))
    except (MigrationStateError, OSError) as error:
        json.dump({"status": "failed", "error": str(error),
                   "backup": str(error.backup) if isinstance(error, DdlMigrationError) and error.backup else None},
                  sys.stderr, sort_keys=True)
        sys.stderr.write("\n")
        return 1
    except (SQLAlchemyError, SQLiteSnapshotError) as error:
        json.dump({"status": "failed", "error": type(error).__name__}, sys.stderr, sort_keys=True)
        sys.stderr.write("\n")
        return 1
    json.dump(report, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
