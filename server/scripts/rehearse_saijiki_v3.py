"""Count or rehearse Saijiki v3 only inside a marked isolated run directory."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from count_saijiki_v1_migration import _resolve_guarded_database
from inku_server.persistence.saijiki_v3_migration import census, migrate_once, migrate_unit_v3
from inku_server.persistence.saijiki_v3_plugins import plan_packages


def _inside(root: Path, name: Path, *, directory: bool = False) -> Path:
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("path_must_be_relative")
    value = root / name
    if value.is_symlink():
        raise ValueError("symlink_not_allowed")
    resolved = value.resolve(strict=True)
    resolved.relative_to(root)
    if directory and not resolved.is_dir():
        raise ValueError("directory_required")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("census", "rehearse"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.run_root.resolve(strict=True)
    database = _resolve_guarded_database(root, args.database)
    packages = _inside(root, args.package_root, directory=True)
    output = _inside(root, args.out, directory=True)
    report_path = output / "report.json"
    journal_path = output / "journal.jsonl"
    if report_path.exists() or journal_path.exists():
        raise ValueError("output_already_exists")
    package_report, proposed = plan_packages(packages)
    if args.mode == "census":
        with sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True) as connection:
            report = census(connection, migrate_unit_v3, workers=args.workers, timeout=args.timeout,
                            journal=journal_path)
    else:
        if package_report["refused_records"]:
            raise ValueError("package_refusals_prevent_rehearsal")
        report = migrate_once(database, packages, output / "recovery", workers=args.workers,
                              timeout=args.timeout, journal=journal_path, allow_refused=True)
        package_report["written"] = len(proposed)
    result = {"mode": args.mode, "database": report, "packages": package_report}
    with report_path.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, ensure_ascii=False, sort_keys=True, indent=2)
    print(json.dumps({"status": "completed", "report": str(report_path), "journal": str(journal_path),
                      "refused": len(report["refused_records"]), "packages": package_report["packages"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
