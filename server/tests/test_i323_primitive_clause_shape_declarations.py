from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from inku_server.coerce import compose
from inku_server.language_support.en import COERCE_MARKERS as EN_MARKERS
from inku_server.language_support.ja import COERCE_MARKERS as JA_MARKERS


DECLARATIONS = {
    "clause_shape_polygon": {
        "ja": ("多角形", "五角", "六角"),
        "en": ("polygon",),
    },
    "clause_shape_square": {
        "ja": ("四角",),
        "en": ("square", "rectangle"),
    },
    "clause_shape_triangle": {
        "ja": ("三角",),
        "en": ("triangle",),
    },
    "clause_shape_arc": {
        "ja": ("弧",),
        "en": ("arc",),
    },
}


def _primitive_tree() -> ast.Module:
    return ast.parse(textwrap.dedent(inspect.getsource(compose._primitive_from_clause)))


def test_i323_four_shape_families_are_declared_exactly() -> None:
    for system, expected in DECLARATIONS.items():
        assert JA_MARKERS[system] == expected["ja"]
        assert EN_MARKERS[system] == expected["en"]


def test_i323_four_shape_predicates_use_named_observed_sites() -> None:
    tree = _primitive_tree()
    expected_sites = {
        f"coerce.compose._primitive_from_clause.{system}" for system in DECLARATIONS
    }
    actual_sites = {
        keyword.value.value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "decision_site"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }
    assert expected_sites <= actual_sites

    moved_words = {
        word
        for declarations in DECLARATIONS.values()
        for language_words in declarations.values()
        for word in language_words
    }
    inline_words = {
        node.left.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Constant)
        and isinstance(node.left.value, str)
        and node.left.value in moved_words
    }
    assert inline_words == set()


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("多角形", "polygon"),
        ("五角", "polygon"),
        ("六角", "polygon"),
        ("polygon", "polygon"),
        ("四角", "square"),
        ("square", "square"),
        ("rectangle", "square"),
        ("三角", "triangle"),
        ("triangle", "triangle"),
        ("弧", "arc"),
        ("arc", "arc"),
    ],
)
def test_i323_existing_shape_words_keep_their_primitive(
    clause: str, expected: str
) -> None:
    assert compose._primitive_from_clause(clause) == expected


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("cloudform polygon square triangle arc ellipse circle", "cloudform"),
        ("polygon square triangle arc ellipse circle", "polygon"),
        ("square triangle arc ellipse circle", "square"),
        ("triangle arc ellipse circle", "triangle"),
        ("arc ellipse circle", "arc"),
        ("ellipse circle", "ellipse"),
        ("circle line", "circle"),
        ("line", "line"),
    ],
)
def test_i323_shape_precedence_and_line_fallback_are_unchanged(
    clause: str, expected: str
) -> None:
    assert compose._primitive_from_clause(clause) == expected
