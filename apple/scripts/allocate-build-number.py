#!/usr/bin/env python3
"""Allocate a Mac-local build number shared by all Inku worktrees."""

import argparse
import fcntl
import os
from pathlib import Path
import tempfile


def allocate(directory: Path, floor: int) -> int:
    if floor < 1:
        raise ValueError("build number floor must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "counter.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        counter = directory / "counter"
        if counter.exists():
            text = counter.read_text(encoding="ascii").strip()
            if not text.isascii() or not text.isdecimal() or int(text) < 1:
                raise ValueError("invalid build number counter")
            previous = int(text)
        else:
            previous = 0
        number = max(previous, floor) + 1
        descriptor, temporary = tempfile.mkstemp(prefix=".counter-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(f"{number}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, counter)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", required=True, type=int)
    parser.add_argument("--directory", type=Path,
                        default=Path.home() / "Library/Application Support/Inku/build-numbers")
    arguments = parser.parse_args()
    print(allocate(arguments.directory, arguments.floor))


if __name__ == "__main__":
    main()
