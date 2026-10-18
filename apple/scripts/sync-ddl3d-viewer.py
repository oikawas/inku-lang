#!/usr/bin/env python3
"""Copy the Web's registered 3D viewer into the macOS app's resources, or check the copy.

The Web registers one immutable viewer build in web/src/lib/features/experimental-3d/installation.json
(`viewerUrl` /experimental/ddl-3d/<build>/index.html) and serves web/static/experimental/ddl-3d/<build>/.
The app bundles the same files unchanged in apple/Sources/InkuUI/Resources/ddl3d/<build>/, beside a copy of
the registration. The app reads only that registration: an empty `viewerUrl` there hides the 3D switch and
reads no viewer file, and then no build is bundled.

  sync-ddl3d-viewer.py              replace the app's copy with the Web's registered build
  sync-ddl3d-viewer.py --check      compare the registration and every file of the copy with the Web's build
  sync-ddl3d-viewer.py --check --app PATH/Inku.app   the same for the copy inside a built application

The check prints how many files it compared. Only `.DS_Store` is ignored, on both sides.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
WEB_REGISTRATION = ROOT / "web/src/lib/features/experimental-3d/installation.json"
WEB_BUILDS = ROOT / "web/static/experimental/ddl-3d"
APP_COPY = ROOT / "apple/Sources/InkuUI/Resources/ddl3d"
BUNDLED = Path("Contents/Resources/InkuApple_InkuUI.bundle/Contents/Resources/ddl3d")
# Web configuredViewer (web/src/lib/features/experimental-3d/input.ts) and the app's Ddl3DInstallation.
VIEWER_URL = re.compile(r"^/experimental/ddl-3d/([a-zA-Z0-9][a-zA-Z0-9._-]{0,63})/index\.html$")
IGNORED = {".DS_Store"}


class SyncError(Exception):
    pass


def registered_build(path: Path) -> str | None:
    """The build a registration names, None when it is empty, an error when it names anything else."""
    value = json.loads(path.read_text(encoding="utf-8")).get("viewerUrl")
    if value == "":
        return None
    match = VIEWER_URL.match(value) if isinstance(value, str) else None
    if not match:
        raise SyncError(f"{path.relative_to(ROOT)} names no versioned viewer: {value!r}")
    return match[1]


def files(directory: Path) -> dict[str, str]:
    """SHA-256 of every regular file below `directory`, by relative path. Links are refused."""
    result: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.name in IGNORED:
            continue
        if path.is_symlink():
            raise SyncError(f"{path} is a symbolic link")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def compare(copy: Path, label: str) -> int:
    """Check one copy (the source resources or a built bundle) against the Web; return the files compared."""
    web_build = registered_build(WEB_REGISTRATION)
    registration = copy / "installation.json"
    if not registration.is_file():
        raise SyncError(f"{label}: no installation.json")
    build = registered_build(registration)
    entries = sorted(path.name for path in copy.iterdir() if path.name not in IGNORED)
    if build is None:
        if entries != ["installation.json"]:
            raise SyncError(f"{label}: the 3D view is disabled but {entries} are bundled")
        print(f"{label}: the 3D view is disabled (empty viewerUrl); no viewer build bundled")
        return 0
    if registration.read_bytes() != WEB_REGISTRATION.read_bytes():
        raise SyncError(f"{label}: installation.json differs from the Web's registration ({web_build})")
    if entries != sorted(["installation.json", build]):
        raise SyncError(f"{label}: expected installation.json and {build}/, found {entries}")
    expected, actual = files(WEB_BUILDS / build), files(copy / build)
    if not expected:
        raise SyncError(f"the Web has no files for {build}")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    different = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    if missing or extra or different:
        raise SyncError(f"{label}: {build} differs from the Web's: missing {missing}, extra {extra}, different {different}")
    print(f"{label}: {len(expected)} files of {build} compared with web/static/experimental/ddl-3d/{build}/; "
          f"all SHA-256 equal ({', '.join(expected)})")
    return len(expected)


def sync() -> None:
    build = registered_build(WEB_REGISTRATION)
    APP_COPY.mkdir(parents=True, exist_ok=True)
    for path in APP_COPY.iterdir():
        if path.name == "installation.json":
            continue
        if path.is_symlink() or not path.is_dir():
            raise SyncError(f"unexpected entry in the app's copy: {path}")
        shutil.rmtree(path)
    if build is not None:
        source = WEB_BUILDS / build
        files(source)  # refuses links before anything is copied
        shutil.copytree(source, APP_COPY / build, ignore=shutil.ignore_patterns(*IGNORED))
    shutil.copyfile(WEB_REGISTRATION, APP_COPY / "installation.json")
    print(f"Copied {'no build (the Web registration is empty)' if build is None else build} "
          f"into {APP_COPY.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="compare instead of copying")
    parser.add_argument("--app", type=Path, help="with --check, also compare the copy inside this built Inku.app")
    arguments = parser.parse_args()
    try:
        if not arguments.check:
            if arguments.app:
                parser.error("--app needs --check")
            sync()
        compare(APP_COPY, str(APP_COPY.relative_to(ROOT)))
        if arguments.app:
            compare(arguments.app / BUNDLED, str(arguments.app / BUNDLED))
    except (SyncError, OSError, ValueError, KeyError) as error:
        print(f"3D viewer copy check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
