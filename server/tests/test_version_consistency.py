"""The places that record a version must agree.

A stamping touches four systems and v2.9.24 shipped with one of them missed:
both project-context files still said `v2.9.23 / Build 820` after the release
had moved on.  Nothing caught it -- the API surface digest, the authorization
sweep and the frozen corpora all stayed green, because none of them reads a
document.  These tests read the documents.

They are skipped, not failed, when a file is absent: the deployment host carries
only `server/` and `web/src`, so a partial tree must not turn red here (that is
the failure mode ledger item I-059 already records for the repository-shape
test).
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

APP_VERSION_FILE = ROOT / "web" / "APP_VERSION"
BUILD_NUMBER_FILE = ROOT / "web" / "BUILD_NUMBER"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT)} is absent (partial tree)")
    return path.read_text(encoding="utf-8")


def app_version() -> str:
    return _read(APP_VERSION_FILE).strip()


def build_number() -> str:
    return _read(BUILD_NUMBER_FILE).strip()


def _one(pattern: str, text: str, where: str) -> str:
    found = re.findall(pattern, text)
    assert len(found) == 1, f"{where}: expected exactly one match, got {len(found)}"
    return found[0]


def test_app_version_file_is_well_formed():
    value = app_version()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", value), (
        f"web/APP_VERSION must look like v2.9.25, got {value!r}"
    )


def test_the_server_reports_the_file_as_its_application_version():
    from inku_server.api_core.common import _APP_VERSION, _RELEASE_VERSION

    assert _APP_VERSION == app_version()
    # The release version is a different thing and is allowed to lag, but it
    # must still be a real value rather than the not-installed placeholder.
    assert _RELEASE_VERSION != "0.0.0+unknown"


def test_the_reference_dump_reports_the_same_application_version():
    from inku_server import reference

    assert reference._app_version() == app_version()


def test_the_ui_does_not_carry_its_own_copy_of_the_version():
    """+page.svelte must read the injected constant, not a literal.

    reference.py used to scrape `const APP_VERSION = '...'` out of this file,
    which pinned one line of a 7,400-line component.  A literal coming back
    would re-create both the duplicate and the pin.
    """
    page = ROOT / "web" / "src" / "routes" / "+page.svelte"
    text = _read(page)
    assert "const APP_VERSION = __APP_VERSION__;" in text
    assert not re.search(r"const\s+APP_VERSION\s*=\s*['\"]", text)


@pytest.mark.parametrize(
    ("relative", "pattern"),
    [
        ("PROJECT_CONTEXT.ja.md", r"\*\*対象バージョン: (v[\d.]+) / Build (\d+)\*\*"),
        ("PROJECT_CONTEXT.md", r"\*\*Target version: (v[\d.]+) / Build (\d+)\*\*"),
    ],
)
def test_the_project_context_target_line_matches(relative: str, pattern: str):
    text = _read(ROOT / relative)
    version, build = _one(pattern, text, relative)
    assert version == app_version(), f"{relative} names {version}"
    assert build == build_number(), f"{relative} names Build {build}"


@pytest.mark.parametrize(
    ("relative", "version_row", "build_row"),
    [
        (
            "docs/spec/render-engine-history.ja.md",
            r"\| `APP_VERSION` \| アプリの版 \| (v[\d.]+) ",
            r"\| `web/BUILD_NUMBER` \| ビルド通し番号 \| (\d+) ",
        ),
        (
            "docs/spec/render-engine-history.md",
            r"\| `APP_VERSION` \| the application version \| (v[\d.]+) ",
            r"\| `web/BUILD_NUMBER` \| build serial \| (\d+) ",
        ),
    ],
)
def test_the_version_marker_table_matches(relative: str, version_row: str, build_row: str):
    text = _read(ROOT / relative)
    assert _one(version_row, text, relative) == app_version()
    assert _one(build_row, text, relative) == build_number()
