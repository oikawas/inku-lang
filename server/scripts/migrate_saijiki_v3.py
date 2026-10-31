"""One stopped-service Saijiki v3 cutover, with explicit operator approval."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from inku_server.persistence.saijiki_v3_cutover import cutover, recover


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write", "recover"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--author-approved", action="store_true")
    args = parser.parse_args()
    if not args.author_approved:
        parser.error("the author must explicitly approve this cutover")
    os.umask(0o077)
    if args.database.is_symlink() or args.packages.is_symlink() or args.recovery.is_symlink():
        raise ValueError("symlink_not_allowed")
    if args.action == "recover":
        state = recover(args.database, args.packages, args.recovery)
        print(json.dumps({"status": state}))
        return 0
    report = cutover(args.database, args.packages, args.recovery,
                     journal=args.recovery / "journal.jsonl")
    result = args.recovery / "report.json"
    with result.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, sort_keys=True)
    print(json.dumps({"status": "completed", "report": str(result),
                      "refused": len(report["refused_records"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
