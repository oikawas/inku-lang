"""Read only the reviewed notice files shipped with this Server distribution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


_PACKAGE_ROOT = Path(__file__).resolve().parent
_CONTAINER_LICENSES = Path("/opt/inku-sqlite/licenses")
_RUST_NOTICES = Path("/app/licenses/RUST_THIRD_PARTY_NOTICES.txt")


class NoticeComponent(BaseModel):
    id: str
    group: Literal["server", "resources", "rust"]
    name: str
    version: str
    license: str
    source: str


class NoticesResponse(BaseModel):
    components: list[NoticeComponent]


@dataclass(frozen=True)
class _Notice:
    component: NoticeComponent
    path: Path


def _notices(server_version: str) -> list[_Notice]:
    """The caller supplies an ID, never a filename or a directory to search."""
    resources = _PACKAGE_ROOT
    return [
        _Notice(NoticeComponent(
            id="server", group="server", name="inku-server", version=server_version,
            license="", source="https://github.com/oikawas/inku-lang",
        ), resources / "notices" / "server-distribution-NOTICES.txt"),
        _Notice(NoticeComponent(
            id="sudachidict-small", group="resources", name="SudachiDict Small / UniDic",
            version="20260723.1", license="Apache-2.0 / BSD",
            source="https://github.com/WorksApplications/SudachiDict/blob/3e49051e71011cac7d74df779e80ef1dab818e56/LEGAL",
        ), resources / "notices" / "sudachidict-small-20260723.1-LEGAL.txt"),
        _Notice(NoticeComponent(
            id="cmudict", group="resources", name="CMU Pronouncing Dictionary",
            version="74790861f652b15e4ac49015a90074ad62a27690", license="BSD-style",
            source="https://github.com/cmusphinx/cmudict/blob/74790861f652b15e4ac49015a90074ad62a27690/LICENSE",
        ), resources / "cmudict" / "LICENSE"),
        _Notice(NoticeComponent(
            id="noto-serif-jp", group="resources", name="Noto Serif JP", version="",
            license="SIL OFL 1.1", source="https://github.com/notofonts/noto-cjk",
        ), resources / "fonts" / "OFL.txt"),
        _Notice(NoticeComponent(
            id="sqlite", group="server", name="SQLite (Ubuntu)", version="",
            license="", source="https://packages.ubuntu.com/jammy/libsqlite3-0",
        ), _CONTAINER_LICENSES / "Ubuntu-libsqlite3-copyright.txt"),
        _Notice(NoticeComponent(
            id="cpython", group="server", name="CPython", version="3.12.15",
            license="PSF", source="https://www.python.org/downloads/release/python-31215/",
        ), _CONTAINER_LICENSES / "CPython-LICENSE.txt"),
        _Notice(NoticeComponent(
            id="rust", group="rust", name="Rust", version="", license="",
            source="https://github.com/oikawas/inku-lang",
        ), _RUST_NOTICES),
    ]


def notice_catalog(server_version: str) -> NoticesResponse:
    # Native deployment and the API image ship different sets of files. Do not
    # advertise a container-only notice as present on the source host.
    return NoticesResponse(components=[
        notice.component for notice in _notices(server_version) if notice.path.is_file()
    ])


def notice_bytes(notice_id: str) -> bytes:
    for notice in _notices(""):
        if notice.component.id == notice_id:
            try:
                return notice.path.read_bytes()
            except OSError:
                break
    raise FileNotFoundError("Notice not found")
