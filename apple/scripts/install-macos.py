#!/usr/bin/env python3
"""Update a fixed local Inku.app without replacing its Dock-bookmarked directory."""

import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile


BUNDLE_IDS = {"app.inku.macos", "app.inku.macos.authorreview"}
DATABASE_KEY = "InkuDatabasePath"


class InstallError(Exception):
    pass


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise InstallError(f"{command[0]} failed ({result.returncode}): {detail}")
    return result.stdout


def bundle(path: Path) -> tuple[dict, Path]:
    if path.suffix != ".app" or path.is_symlink() or not path.is_dir():
        raise InstallError(f"Expected a real .app directory: {path}")
    contents = path / "Contents"
    info_path = contents / "Info.plist"
    if contents.is_symlink() or not contents.is_dir() or info_path.is_symlink():
        raise InstallError(f"Unsafe or missing bundle Contents/Info.plist: {path}")
    try:
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        raise InstallError(f"Cannot read bundle Info.plist: {path}") from error
    if not isinstance(info, dict):
        raise InstallError(f"Expected an Info.plist dictionary: {path}")
    identifier = info.get("CFBundleIdentifier")
    if not isinstance(identifier, str) or identifier not in BUNDLE_IDS:
        raise InstallError(f"Refusing an unknown bundle identifier: {path}")
    if info.get("CFBundlePackageType") != "APPL" or info.get("CFBundleExecutable") != "Inku":
        raise InstallError(f"Expected the Inku application bundle: {path}")
    executable = contents / "MacOS" / "Inku"
    if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise InstallError(f"Missing or nonexecutable Inku binary: {executable}")
    if not executable.resolve().is_relative_to(path.resolve()):
        raise InstallError(f"Executable escapes its application bundle: {executable}")
    return info, executable


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def database_path(value: object, source: Path, destination: Path) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\0" in value:
        raise InstallError("InkuDatabasePath/--database must be an absolute file path")
    path = Path(value)
    if not path.is_file():
        raise InstallError(f"Database must already exist as a file: {path}")
    resolved = path.resolve()
    if resolved.is_relative_to(source) or resolved.is_relative_to(destination):
        raise InstallError("Database must be outside both app bundles; installation never copies or modifies it")
    return value


def not_running(destination: Path, executable: Path) -> None:
    pids: set[str] = set()
    for line in run(["/bin/ps", "-ww", "-axo", "pid=,comm="]).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[1].startswith("/"):
            if Path(parts[1]).resolve().is_relative_to(destination):
                pids.add(parts[0])
    # Also catch an executable mapped through an alias to the installed file.
    mapped = subprocess.run(["/usr/sbin/lsof", "-t", "-a", "-d", "txt", "--", str(executable)],
                            text=True, capture_output=True)
    if mapped.returncode not in (0, 1) or (mapped.returncode == 1 and mapped.stderr.strip()):
        raise InstallError(f"Cannot check whether installed Inku is running: {mapped.stderr.strip()}")
    pids.update(line for line in mapped.stdout.splitlines() if line.isdecimal())
    if pids:
        raise InstallError(f"Close the installed application before updating {destination} (PID {', '.join(sorted(pids))})")


def install(arguments: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        raise InstallError("The local Inku application installer requires macOS")
    if sys.version_info < (3, 11):
        raise InstallError("Python 3.11 or newer is required")
    source_argument = Path(arguments.app).expanduser().absolute()
    destination_argument = Path(arguments.destination).expanduser().absolute()
    if source_argument.is_symlink() or destination_argument.is_symlink():
        raise InstallError("Source and destination app directories must not be symlinks")
    source = source_argument.resolve()
    destination = destination_argument.parent.resolve() / destination_argument.name
    if destination.suffix != ".app":
        raise InstallError("Destination must end in .app")
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise InstallError("Source and destination app paths must not overlap")
    source_info, source_executable = bundle(source)
    executable_digest = digest(source_executable)
    installed_info = None
    original_inode = None
    if destination.exists():
        installed_info, installed_executable = bundle(destination)
        original_inode = (destination.stat().st_dev, destination.stat().st_ino)
        not_running(destination, installed_executable)
    bundle_id = arguments.bundle_id if arguments.bundle_id is not None else (installed_info or source_info)["CFBundleIdentifier"]
    if bundle_id not in BUNDLE_IDS:
        raise InstallError("--bundle-id must be app.inku.macos or app.inku.macos.authorreview")
    if arguments.database is not None:
        selected_database = database_path(arguments.database, source, destination)
    else:
        selected_database = (installed_info if installed_info is not None else source_info).get(DATABASE_KEY)
        if selected_database is not None:
            selected_database = database_path(selected_database, source, destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".inku-install-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "Inku.app"
        run(["/usr/bin/ditto", str(source), str(staged)])
        staged_info, staged_executable = bundle(staged)
        if digest(staged_executable) != executable_digest:
            raise InstallError("Staged executable differs from the built application; destination was not changed")
        staged_info["CFBundleIdentifier"] = bundle_id
        if selected_database is None:
            staged_info.pop(DATABASE_KEY, None)
        else:
            staged_info[DATABASE_KEY] = selected_database
        if staged_info != source_info:
            if (staged / "Contents" / "_CodeSignature" / "CodeResources").exists():
                raise InstallError("Source has a signing resource envelope; Info.plist cannot be changed by this unsigned local installer")
            with (staged / "Contents" / "Info.plist").open("wb") as stream:
                plistlib.dump(staged_info, stream, sort_keys=False)
        validated_info, staged_executable = bundle(staged)
        if validated_info != staged_info or digest(staged_executable) != executable_digest:
            raise InstallError("Staged bundle validation failed; destination was not changed")

        if installed_info is not None:
            current_info, installed_executable = bundle(destination)
            current_inode = (destination.stat().st_dev, destination.stat().st_ino)
            if current_inode != original_inode or current_info != installed_info:
                raise InstallError("Installed bundle changed during staging; refusing to overwrite it")
            not_running(destination, installed_executable)
        else:
            try:
                destination.mkdir()
            except FileExistsError as error:
                raise InstallError("Destination appeared during staging; refusing to overwrite it") from error
            original_inode = (destination.stat().st_dev, destination.stat().st_ino)
        run(["/usr/bin/rsync", "-a", "--checksum", "--delete",
             str(staged / "Contents") + "/", str(destination / "Contents") + "/"])
        final_info, installed_executable = bundle(destination)
        if (destination.stat().st_dev, destination.stat().st_ino) != original_inode:
            raise InstallError("Installed app directory identity changed during update")
        if final_info != staged_info or digest(installed_executable) != executable_digest:
            raise InstallError("Installed bundle does not match the validated staging copy")
    print(f"Installed Inku: {destination}")
    print(f"Bundle identifier: {bundle_id}")
    print(f"Database: {selected_database or 'product default'}")
    print("Application directory identity preserved; Dock configuration was not changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="Built Inku.app")
    parser.add_argument("--destination", default="~/Applications/Inku.app", help="Fixed installed .app path")
    parser.add_argument("--database", help="Absolute path to an existing database outside the app bundle")
    parser.add_argument("--bundle-id", help="Optional fixed local Inku bundle identifier")
    arguments = parser.parse_args()
    try:
        install(arguments)
    except (InstallError, OSError) as error:
        print(f"Inku installation refused/failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
