"""Acceptance: contract the-glossary-reaches-the-documents (2026-08-09, [I-161]).

``GLOSSARY.md`` is canonical for every English word in the project, and until
today the only machine reading it was ``npm run lint:i18n``, which opens
``en.ts`` and the web components and no markdown file at all. Twenty-four lines
across five published documents still said ``artwork`` and ``palette`` while the
Japanese originals were already right. ``check_docs.py`` now reads the documents
for the four forbidden words that can occur in them.

**Both lists the new check consults are configuration tables, not product code.**
Delete a word from ``FORBIDDEN_WORDS`` or a row from ``PAIRS`` and every check
stays green while looking at less -- the same shape as the dependency upgrade
that emptied ``app.routes`` from 81 to 0 with two checks still green. So the four
words, the seventeen documents, and the three deliberately exempt documents are
asserted one at a time, never as a total.

The two behavioural tests call ``check_docs.py``'s own functions rather than
re-implementing the match, and the wiring test reads ``main`` out of the syntax
tree: ``grep`` for ``check_terminology`` also matches the word in this file's
own comments and in the docstring of the function it is looking for.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK_DOCS = ROOT / "server/scripts/check_docs.py"

# GLOSSARY.md §5-1 forbids seven words. These are the four that can occur in a
# document: `fluctuation`, `jitter` and `okugaki` stand at zero in all twenty
# documents today but were left out on purpose -- SPEC may yet explain `okugaki`
# as a concept name, and `jitter` is a drawing term. Adding them is a separate
# decision that owes its own measurement.
FORBIDDEN_WORDS = ("artwork", "palette", "AI-powered", "magic")

# The seventeen English documents the check reads, named one by one.
CHECKED_DOCUMENTS = (
    "README.md",
    "docs/spec/render-engine-history.md",
    "docs/guide/gallery.md",
    "docs/guide/how-it-works.md",
    "docs/guide/revision.md",
    "SETUP.md",
    "PROJECT_CONTEXT.md",
    "android/ANDROID_SPEC.md",
    "SPEC.md",
    "docs/spec/implementation-status.md",
    "manual/en/README.md",
    "manual/en/image-creation.md",
    "manual/en/cli-reference.md",
    "manual/en/cli-reference-for-ai.md",
    "manual/en/application-install.md",
    "manual/en/server-configuration.md",
    "manual/en/revision-history.md",
)

# The control. The author ruled on 2026-08-09 that the three changelogs stay out:
# a changelog is a frozen record, and CHANGELOG.md:461 quotes `palette` as the
# mistake it is recording. **The exclusion was decided, not overlooked** -- an
# exclusion nobody asserts is one that can disappear without a reader noticing,
# which is the same failure the seventeen above are asserted against.
EXEMPT_DOCUMENTS = (
    "CHANGELOG.md",
    "docs/history/changelog-v1.72-v2.4.md",
    "docs/history/changelog-v0.1-v1.71.md",
)


def _check_docs() -> types.ModuleType:
    """Load ``check_docs.py``, which is a script rather than a package module."""
    spec = importlib.util.spec_from_file_location("check_docs_under_test", CHECK_DOCS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("word", FORBIDDEN_WORDS)
def test_forbidden_word_is_still_looked_for(word: str) -> None:
    """T-1: each of the four words is in the list, one assertion per word."""
    words = _check_docs().FORBIDDEN_WORDS
    assert word in words, (
        f"{word!r} is no longer in FORBIDDEN_WORDS. GLOSSARY.md §5-1 still "
        f"forbids it, nothing else reads the documents for it, and check_docs.py "
        f"stays green while looking for one word fewer."
    )


@pytest.mark.parametrize("name", CHECKED_DOCUMENTS)
def test_document_is_read_for_forbidden_words(name: str) -> None:
    """T-2: each of the seventeen documents is a target, one assertion each."""
    targets = _check_docs().terminology_targets()
    assert name in targets, (
        f"{name} is no longer read for forbidden words. It either left PAIRS or "
        f"joined TERMINOLOGY_EXEMPT; either way the check stays green while this "
        f"document's English is no longer compared with the glossary."
    )


@pytest.mark.parametrize("name", EXEMPT_DOCUMENTS)
def test_exempt_document_is_not_read(name: str) -> None:
    """T-3: the control -- the three changelogs are out, and say so."""
    module = _check_docs()
    assert name in module.TERMINOLOGY_EXEMPT, (
        f"{name} is no longer named in TERMINOLOGY_EXEMPT. The 2026-08-09 ruling "
        f"that a frozen record is not corrected has stopped being written down."
    )
    assert name not in module.terminology_targets()


def test_main_reports_what_the_terminology_check_finds() -> None:
    """T-4: the wiring -- main calls it *and* adds its findings to the exit code.

    A call whose result is dropped leaves the check running and reporting
    nothing, which reads as a green run rather than as a missing gate.
    """
    tree = ast.parse(CHECK_DOCS.read_text(encoding="utf-8"))
    main = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    bound = {
        target.id
        for node in ast.walk(main)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "check_terminology"
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert bound, "main() no longer calls check_terminology()"
    summed = {
        node.id
        for assign in ast.walk(main)
        if isinstance(assign, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "problems" for t in assign.targets
        )
        for node in ast.walk(assign.value)
        if isinstance(node, ast.Name)
    }
    assert bound & summed, (
        "check_terminology() is called but its findings never reach `problems`, "
        "so a forbidden word would be printed while main() still exits 0."
    )


def test_a_backticked_identifier_is_not_a_violation() -> None:
    """T-5: an identifier stays an identifier.

    `Artwork` is a Kotlin enum member and `palette` is a field of the catalog
    JSON. Aiming for zero grep hits would erase both, which GLOSSARY.md:146
    warns against; wrapping them in backticks is how a document says "this is
    the code's word, not mine".
    """
    text = "The `Artwork` tab shows the work drawn from the catalog's `palette`.\n"
    assert _check_docs().forbidden_hits(text) == []


def test_a_bare_forbidden_word_is_found() -> None:
    """T-6: the same words outside backticks are reported, plural included."""
    text = (
        "A quiet line crosses the paper.\n"
        "Refinement draws with the artwork's own catalog.\n"
        "Catalog palettes already carried twelve yellows.\n"
    )
    assert _check_docs().forbidden_hits(text) == [(2, "artwork"), (3, "palettes")]
