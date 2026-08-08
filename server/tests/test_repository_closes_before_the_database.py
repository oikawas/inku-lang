"""The instrumented tests must close the repository before the database (I-150).

Saving a work schedules a thumbnail write on a coroutine the save does not wait
for, and every one of these tests closes the database in its teardown. When the
close lands on a write still in flight, the throw happens on the background
coroutine rather than on the caller, so it takes the whole instrumentation
process down: the run ends with most of its tests unrecorded instead of with one
red test. Twelve runs produced five such truncations, and the truncation is only
visible by counting the XML.

`InkuRepository.close()` now waits for the scheduled write before it returns, so
closing the repository first is what makes the database close safe. That is a
property of every teardown, not of the one class that happened to crash, and
four of the twelve were closing the database without closing the repository at
all -- they leaned on a 500 ms sleep instead.

This lives on the server side because there are four precedents for reading the
Kotlin sources from pytest, and because pytest runs in every acceptance cycle
while Gradle runs only in the cycles that touch `android/`. The gate that
watches for a regression should sit on the surface that is walked more often.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the tree is absent. Key the skip to the
# DIRECTORY: wherever `android/` exists these assertions still run, and a moved
# or renamed test is a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
INSTRUMENTED = ANDROID_TREE / "app/src/androidTest"

android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(), reason="android/ is absent (pentala)"
)

BUILDS_REPOSITORY = re.compile(r"\bInkuRepository\(")
CLOSE = re.compile(r"\b(repository|database)\.close\(\)")


def _sources() -> list[pathlib.Path]:
    return sorted(INSTRUMENTED.rglob("*.kt"))


@android_only
def test_every_database_close_is_covered_by_an_earlier_repository_close() -> None:
    """T-2: at each `database.close()`, a repository close already happened.

    Stated as a running count rather than as adjacency, because the closes are
    not always neighbours -- one class still keeps a settle between them, and a
    settle is not the thing being asserted. What must hold is the pairing: by
    the time the Nth database close runs, at least N repository closes have.
    """
    offenders: list[str] = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if not BUILDS_REPOSITORY.search(text):
            continue
        repositories = databases = 0
        for match in CLOSE.finditer(text):
            if match.group(1) == "repository":
                repositories += 1
                continue
            databases += 1
            if repositories < databases:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert offenders == [], (
        "these database closes are not covered by a repository close before them,"
        " so a scheduled thumbnail write can be cut off mid-flight and take the"
        f" instrumentation process down (I-150): {offenders}"
    )


@android_only
def test_the_gate_has_something_to_watch() -> None:
    """The contrast: a pairing rule over an empty set would pass for nothing.

    Counted rather than named, because the count is what the rule is worth. If a
    refactor moves the teardowns somewhere this file cannot see, the number
    drops and this fails rather than the rule above quietly guarding nothing.
    """
    watched = [
        path
        for path in _sources()
        if BUILDS_REPOSITORY.search(path.read_text(encoding="utf-8"))
    ]
    assert len(watched) >= 12, (
        f"only {len(watched)} instrumented classes build a repository;"
        " 12 did when this gate was written"
    )
