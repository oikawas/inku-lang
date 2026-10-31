"""Record core inputs and outputs for plugins on an isolated snapshot only."""

import argparse
import json
import os
from pathlib import Path

from count_saijiki_v1_migration import _resolve_guarded_database
from inku_server.persistence.saijiki_v3_plugins import plan_packages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve(strict=True)
    _resolve_guarded_database(root, Path("candidate.db"))
    packages = root / "plugins"
    if packages.is_symlink() or packages.resolve(strict=True).parent != root:
        raise ValueError("invalid_isolated_plugins")
    output = root / "out-plugin-journal"
    output.mkdir(mode=0o700)
    descriptor = os.open(output / "plugin-journal.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as journal:
        def write(entry):
            journal.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

        report, _proposed = plan_packages(packages, journal=write)
    descriptor = os.open(output / "plugin-report.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        json.dump(report, destination, ensure_ascii=False, sort_keys=True)
    print(json.dumps({"status": "completed", "packages": report["packages"],
                      "refused": len(report["refused_records"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
