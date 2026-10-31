#!/usr/bin/env python3
"""Allocate a Mac-local version and build number shared by Inku worktrees."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import tempfile


def parse_version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isascii() or not part.isdecimal() or (len(part) > 1 and part[0] == "0") for part in parts):
        raise ValueError("version must have three nonnegative decimal components")
    return tuple(map(int, parts))


def atomic_write(directory: Path, name: str, value: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{name}-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, directory / name)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def allocate(directory: Path, floor: int, version_floor: str) -> tuple[str, int]:
    if floor < 1:
        raise ValueError("build number floor must be positive")
    base = parse_version(version_floor)
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
        state_path = directory / "version-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="ascii"))
            if not isinstance(state, dict) or type(state.get("build")) is not int or state["build"] < 1 or not isinstance(state.get("version"), str):
                raise ValueError("invalid version allocation state")
            previous = max(previous, state["build"])
            base = max(base, parse_version(state["version"]))
        number = max(previous, floor) + 1
        version = f"{base[0]}.{base[1]}.{base[2] + 1}"
        # Publish the legacy build counter first: a crash may skip a build number,
        # but an older worktree cannot reuse a number already handed out here.
        atomic_write(directory, "counter", f"{number}\n")
        atomic_write(directory, "version-state.json", json.dumps({"version": version, "build": number}) + "\n")
        return version, number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=int)
    parser.add_argument("--version-floor", required=True)
    parser.add_argument("--check-version", help="validate an allocated version against the floor without allocating")
    parser.add_argument("--directory", type=Path,
                        default=Path.home() / "Library/Application Support/Inku/build-numbers")
    arguments = parser.parse_args()
    if arguments.check_version is not None:
        if parse_version(arguments.check_version) <= parse_version(arguments.version_floor):
            parser.error("allocated version must be greater than the version floor")
        return
    if arguments.floor is None:
        parser.error("--floor is required when allocating")
    version, number = allocate(arguments.directory, arguments.floor, arguments.version_floor)
    print(version, number)


if __name__ == "__main__":
    main()
