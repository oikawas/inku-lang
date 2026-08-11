"""The reader that turns a stated count into a number exists once.

Two layers ask "how many did the description say" -- the coerce layer and the
plugin expansion layer.  While each kept its own reader, a hole was fixed on one
side only.  These tests measure the positive form: one definition in the tree,
and a public door that the two callers outside `coerce` still come through.
"""

from __future__ import annotations

import pathlib
import re

import pytest

SERVER_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# Each pattern is the *definition* of a name the readers are built from, not a
# use of it.  A second definition anywhere in the tree is the accident this
# guards against: an extraction that leaves the original standing.
DEFINITION_PATTERNS = {
    "COUNTED_OBJECT_WORDS": r"^COUNTED_OBJECT_WORDS: frozenset",
    "JAPANESE_COUNT_PATTERN": r"^JAPANESE_COUNT_PATTERN = re\.compile",
    "ENGLISH_COUNT_UNITS": r"^ENGLISH_COUNT_UNITS: dict",
    "ENGLISH_SMALL_NUMBERS": r"^ENGLISH_SMALL_NUMBERS: dict",
    "count_hint_from_ddl": r"^def count_hint_from_ddl",
    "_explicit_counts_from_ddl": r"^def _explicit_counts_from_ddl",
    "_english_count_hint": r"^def _english_count_hint",
    "_parse_small_japanese_number": r"^def _parse_small_japanese_number",
    "_count_follows_ddl_request": r"^def _count_follows_ddl_request",
}


def _definition_sites(pattern: str) -> list[str]:
    compiled = re.compile(pattern, re.MULTILINE)
    return [
        str(path.relative_to(SERVER_SRC))
        for path in sorted(SERVER_SRC.rglob("*.py"))
        if compiled.search(path.read_text(encoding="utf-8"))
    ]


@pytest.mark.parametrize("name,pattern", sorted(DEFINITION_PATTERNS.items()))
def test_t1_each_count_reader_is_defined_once(name: str, pattern: str) -> None:
    sites = _definition_sites(pattern)
    assert sites == ["inku_server/counts.py"], f"{name} is defined at {sites}"


def test_t1_the_coerce_layer_reads_the_shared_module() -> None:
    """The negative form above passes on a tree with no reader at all."""
    from inku_server.coerce import compose
    from inku_server import counts

    assert compose.count_hint_from_ddl is counts.count_hint_from_ddl
    assert compose._explicit_counts_from_ddl is counts._explicit_counts_from_ddl
    assert compose._is_literal_grid_request is counts._is_literal_grid_request


def test_t3_the_public_door_of_the_coerce_package_is_open() -> None:
    """`render.py` and `composer.py` reach the reader through `coerce`."""
    import inku_server.coerce as coerce_package
    from inku_server.coerce import count_hint_from_ddl
    from inku_server import counts

    assert "count_hint_from_ddl" in coerce_package.__all__
    assert count_hint_from_ddl is counts.count_hint_from_ddl
    assert count_hint_from_ddl("円を12個描く。") == 12


def test_t3_the_two_callers_outside_coerce_still_resolve_it() -> None:
    from inku_server import counts
    from inku_server.api_core.routers import render as render_router

    assert render_router.count_hint_from_ddl is counts.count_hint_from_ddl

    # `composer.py` imports it inside the function body, so only running that body
    # proves the door is open there.  Three cloudforms asked for, none delivered:
    # the transcription reads the count through `coerce`.
    from inku_server.composer import _enforce_cloudform_literal_delivery
    from inku_server.schema import Score

    score = Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": {"aspect": "square"},
            "background": "white",
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.5], "to": [0.8, 0.5], "color": "black", "weight": "pen"}
            ],
        }
    )
    out = _enforce_cloudform_literal_delivery(score, "灰色の雲形を3個置く。")
    transcribed = [ins for ins in out.instructions if ins.primitive == "cloudform"]
    assert len(transcribed) == 1
    assert transcribed[0].arrangement is not None
    assert transcribed[0].arrangement.count == 3
