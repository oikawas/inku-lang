"""I-327: the published image can name its own version.

`server/Dockerfile` copied `web/BUILD_NUMBER` and not `web/APP_VERSION`, so
every published image answered `/api/info` with `version: unknown`. Nothing
caught it: `test_version_consistency.py` reads the file out of the tree, which
is always there, and the only workflow that builds the image fires on a tag
push -- after publishing.

So the check here is static. It reads which repository files the server code
opens relative to the repository root, reads which files the image copies in,
and compares the two. It cannot see anything about a built image; what it can
see is the shape of mistake that produced I-327, at the moment it is made.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "server" / "src" / "inku_server"
DOCKERFILE = ROOT / "server" / "Dockerfile"

# `_REPO_ROOT / "web" / "APP_VERSION"` and the parents[4] spelling in
# api_core/common.py. Both are one expression on one line today; a reader
# written differently would not be found, which is why the scan is asserted to
# be non-empty rather than trusted.
READ = re.compile(r'parents\[\d+\]\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"|/\s*"(web)"\s*/\s*"([^"]+)"')


def _files_the_server_reads() -> set[str]:
    found: set[str] = set()
    for path in SOURCE.rglob("*.py"):
        for match in READ.finditer(path.read_text(encoding="utf-8")):
            directory = match.group(1) or match.group(3)
            name = match.group(2) or match.group(4)
            if directory and name:
                found.add(f"{directory}/{name}")
    return found


def _files_the_image_copies() -> set[str]:
    copied: set[str] = set()
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("COPY "):
            copied.add(line.split()[1])
    return copied


def _is_covered(wanted: str, copied: set[str]) -> bool:
    if wanted in copied:
        return True
    # `COPY shared/ /app/shared/` carries every file under it.
    return any(entry.endswith("/") and wanted.startswith(entry) for entry in copied)


def test_every_repository_file_the_server_reads_is_copied_into_the_image():
    """T-295"""
    read = _files_the_server_reads()
    copied = _files_the_image_copies()

    missing = sorted(name for name in read if not _is_covered(name, copied))

    assert not missing, (
        f"the image does not carry {missing}; the server reads {sorted(read)} "
        f"and the Dockerfile copies {sorted(copied)}"
    )


def test_the_scan_finds_the_readers_it_is_meant_to_find():
    """T-296

    Both sides empty would make the comparison above pass while looking at
    nothing, which is how the original defect survived every check.
    """
    read = _files_the_server_reads()

    assert len(read) >= 2, f"the scan found only {sorted(read)}"
    assert "web/APP_VERSION" in read
    assert "web/BUILD_NUMBER" in read


@pytest.mark.parametrize("relative", ["web/APP_VERSION", "web/BUILD_NUMBER"])
def test_the_image_copies_the_version_files_by_name(relative):
    """T-297"""
    assert _is_covered(relative, _files_the_image_copies()), (
        f"{relative} is not copied into the image; /api/info would answer 'unknown'"
    )
