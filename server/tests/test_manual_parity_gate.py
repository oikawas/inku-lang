"""Acceptance: contract manual-parity-gate (2026-08-05, [I-140]).

``check_docs.py`` compares the two language versions of thirteen documents, and
``manual/`` was in none of them. The two sides drifted eleven days apart in
last-modified time before anyone noticed, and the alignment they have today was
reached by hand rather than by a check.

**``PAIRS`` is a configuration table, not product code.** Deleting rows from it
leaves every check green and silently narrows what is looked at -- the same
shape as the dependency upgrade that emptied ``app.routes`` from 81 to 0 while
two checks stayed green. So the seven rows are asserted one at a time here:
asserting only the total would pass on six manual pairs plus one other.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK_DOCS = ROOT / "server/scripts/check_docs.py"
MANUAL = ROOT / "manual"

# Decide the skip on the directory, not on a file name: a file-level test turns
# red on a tree that carries no manual at all, where a directory-level skip stays
# quiet. Reading `check_docs.py` needs no such guard, since it sits under
# `server/`, which every tree has.
#
# This guard is defensive, not a description of pentala. The contract asserted
# that `manual/` is outside the rsync payload and therefore absent there; that
# was measured on 2026-08-05 and is false -- pentala carries `manual/` (a stale
# v1.85 copy, with the two languages still matching each other, so `check_parity`
# is green there rather than reporting seven missing originals).
manual_tree_only = pytest.mark.skipif(not MANUAL.is_dir(), reason="manual/ is absent")

# The seven pairs this contract adds, named one by one.
MANUAL_PAIRS = (
    ("manual/ja/README.md", "manual/en/README.md", "shape"),
    ("manual/ja/image-creation.md", "manual/en/image-creation.md", "shape"),
    ("manual/ja/cli-reference.md", "manual/en/cli-reference.md", "shape"),
    ("manual/ja/cli-reference-for-ai.md", "manual/en/cli-reference-for-ai.md", "shape"),
    ("manual/ja/application-install.md", "manual/en/application-install.md", "shape"),
    ("manual/ja/server-configuration.md", "manual/en/server-configuration.md", "shape"),
    ("manual/ja/revision-history.md", "manual/en/revision-history.md", "shape"),
)


# Public architecture pairs added when the internal investigation was published.
ARCHITECTURE_PAIRS = (
    ("docs/architecture/README.ja.md", "docs/architecture/README.md", "shape"),
    (
        "docs/architecture/evidence-inventory.ja.md",
        "docs/architecture/evidence-inventory.md",
        "shape",
    ),
    (
        "docs/architecture/system-context.ja.md",
        "docs/architecture/system-context.md",
        "shape",
    ),
    (
        "docs/architecture/runtime-containers.ja.md",
        "docs/architecture/runtime-containers.md",
        "shape",
    ),
    (
        "docs/architecture/ddl-processing-pipeline.ja.md",
        "docs/architecture/ddl-processing-pipeline.md",
        "shape",
    ),
    (
        "docs/architecture/server-components.ja.md",
        "docs/architecture/server-components.md",
        "shape",
    ),
    (
        "docs/architecture/client-boundaries.ja.md",
        "docs/architecture/client-boundaries.md",
        "shape",
    ),
    (
        "docs/architecture/data-history-lineage.ja.md",
        "docs/architecture/data-history-lineage.md",
        "shape",
    ),
    (
        "docs/architecture/operations-security.ja.md",
        "docs/architecture/operations-security.md",
        "shape",
    ),
    (
        "docs/architecture/change-impact-map.ja.md",
        "docs/architecture/change-impact-map.md",
        "shape",
    ),
    (
        "docs/architecture/known-differences.ja.md",
        "docs/architecture/known-differences.md",
        "shape",
    ),
    (
        "docs/architecture/description-to-svg.ja.md",
        "docs/architecture/description-to-svg.md",
        "shape",
    ),
    (
        "docs/architecture/future-plan.ja.md",
        "docs/architecture/future-plan.md",
        "shape",
    ),
)

# The thirteen pairs that were already there, as the control: adding seven rows
# must not take an existing one with it.
EXISTING_PAIRS = (
    "README.ja.md",
    "docs/spec/render-engine-history.ja.md",
    "docs/guide/gallery.ja.md",
    "docs/guide/how-it-works.ja.md",
    "docs/guide/revision.ja.md",
    "SETUP.ja.md",
    "PROJECT_CONTEXT.ja.md",
    "android/ANDROID_SPEC.ja.md",
    "SPEC.ja.md",
    "docs/spec/implementation-status.ja.md",
    "CHANGELOG.ja.md",
    "docs/history/changelog-v1.72-v2.4.ja.md",
    "docs/history/changelog-v0.1-v1.71.ja.md",
)


def _pairs() -> tuple[tuple[str, str, str, str | None], ...]:
    """Read ``PAIRS`` out of the syntax tree.

    Not by grep: ``grep '"shape"'`` also matches the word inside the comment
    that documents the three modes, and counts thirteen pairs as fourteen.
    """
    tree = ast.parse(CHECK_DOCS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "PAIRS" for t in targets):
            return ast.literal_eval(node.value)
    raise AssertionError("PAIRS is not defined in check_docs.py")


@pytest.mark.parametrize(
    ("ja_name", "en_name", "mode"), MANUAL_PAIRS, ids=[pair[0] for pair in MANUAL_PAIRS]
)
def test_manual_pair_is_checked(ja_name: str, en_name: str, mode: str) -> None:
    """T-1: each of the seven pairs is in PAIRS, with its English side and mode."""
    by_ja = {pair[0]: pair for pair in _pairs()}
    assert ja_name in by_ja, (
        f"{ja_name} is no longer in check_docs.py PAIRS. Nothing compares the two "
        f"language versions of this manual page any more, and the check stays green."
    )
    _, actual_en, actual_mode, exception = by_ja[ja_name]
    assert actual_en == en_name
    assert actual_mode == mode
    # A declared reason turns the failure into a printed note, so the row would
    # still be listed while checking nothing.
    assert exception is None, f"{ja_name} carries a declared exception: {exception}"


@pytest.mark.parametrize(
    ("ja_name", "en_name", "mode"),
    ARCHITECTURE_PAIRS,
    ids=[pair[0] for pair in ARCHITECTURE_PAIRS],
)
def test_architecture_pair_is_checked(ja_name: str, en_name: str, mode: str) -> None:
    """Each public architecture pair remains in the documentation gate."""
    by_ja = {pair[0]: pair for pair in _pairs()}
    assert ja_name in by_ja
    _, actual_en, actual_mode, exception = by_ja[ja_name]
    assert actual_en == en_name
    assert actual_mode == mode
    assert exception is None
    assert (ROOT / ja_name).is_file()
    assert (ROOT / en_name).is_file()


def test_the_thirteen_earlier_pairs_are_intact() -> None:
    """T-2: the control -- no existing row was displaced by the seven new ones."""
    pairs = _pairs()
    ja_names = [pair[0] for pair in pairs]
    missing = [name for name in EXISTING_PAIRS if name not in ja_names]
    assert not missing, f"pairs that check_docs.py used to compare are gone: {missing}"
    assert len(pairs) == 34, (
        f"PAIRS holds {len(pairs)} pairs, not the 13 earlier, 7 manual, "
        "13 architecture, and 1 plugin pair"
    )


@manual_tree_only
@pytest.mark.parametrize(
    "name",
    [name for pair in MANUAL_PAIRS for name in pair[:2]],
)
def test_manual_pair_names_a_file_that_exists(name: str) -> None:
    """T-3: the fourteen files the seven pairs name are really there.

    ``check_parity`` reports a missing Japanese original, but an English side
    that was never written is only reported when the pair is declared without a
    reason -- and a path typed wrong on both sides is reported as one absent
    original rather than as a typo.
    """
    assert (ROOT / name).is_file(), f"{name} is named in PAIRS but does not exist"
