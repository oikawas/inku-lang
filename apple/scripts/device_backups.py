#!/usr/bin/env python3
"""Keep a device's app data copies to the author's rule: one copy a day, at most two kept (2026-11-15).

build-ios.sh --device copies the installed app's data into <backup root>/<UDID>/<YYYYMMDD-HHMMSS>[-<note>] before
installing. Every folder there whose name starts with a date and time is one copy, a note such as
"-before-check" included.

  device_backups.py taken-today DIR    print the newest copy of today in DIR and exit 0; exit 1 when there is none
  device_backups.py prune DIR          remove the oldest copies in DIR until two remain, printing each one removed

Only the folders directly in DIR are read or removed.
"""

from __future__ import annotations

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

KEEP = 2
COPY_NAME = re.compile(r"^(\d{8})-\d{6}(?:-[A-Za-z0-9._-]+)?$")


def copies(directory: Path) -> list[Path]:
    """The copies in a device's folder, newest first (by the date and time in the name)."""
    if not directory.is_dir():
        return []
    found = [path for path in directory.iterdir() if path.is_dir() and not path.is_symlink() and COPY_NAME.match(path.name)]
    return sorted(found, key=lambda path: path.name, reverse=True)


def taken_today(directory: Path, today: str) -> Path | None:
    return next((path for path in copies(directory) if COPY_NAME.match(path.name).group(1) == today), None)


def prune(directory: Path, keep: int = KEEP) -> list[Path]:
    removed = copies(directory)[keep:]
    for path in removed:
        shutil.rmtree(path)
    return removed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["taken-today", "prune"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--today", default=datetime.date.today().strftime("%Y%m%d"), help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.command == "taken-today":
        found = taken_today(arguments.directory, arguments.today)
        if found is None:
            return 1
        print(found)
        return 0
    for path in prune(arguments.directory):
        print(f"removed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
