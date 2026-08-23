"""Acceptance for the I-322 documentation version-parity guard."""

from __future__ import annotations

import importlib.util
import pathlib
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK_DOCS = ROOT / "server/scripts/check_docs.py"


def _check_docs() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs_version_gate", CHECK_DOCS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_marks_handle_japanese_adjacency_and_english_plural() -> None:
    module = _check_docs()
    assert module.version_marks(
        "Build 557では、これをBuild 518から引き継いだ。Builds 733 to 753. v2.4.7"
    ) == {"Build 557", "Build 518", "Build 733", "v2.4.7"}


def test_build_and_builds_are_the_same_mark() -> None:
    module = _check_docs()
    assert module.version_mark_differences("Build 733", "Builds 733") == (set(), set())


def test_a_mark_on_only_one_side_is_reported() -> None:
    module = _check_docs()
    assert module.version_mark_differences("v2.4.7", "v2.4.7 Build 999") == (
        set(),
        {"Build 999"},
    )


def test_current_public_pairs_have_version_parity(capsys: object) -> None:
    module = _check_docs()
    assert module.check_version_parity() == []
    assert "version-mark pairs compared: 32" in capsys.readouterr().out


def test_root_changelog_uses_entry_parity_instead() -> None:
    module = _check_docs()
    assert module.VERSION_PARITY_EXEMPT == {"CHANGELOG.ja.md"}
