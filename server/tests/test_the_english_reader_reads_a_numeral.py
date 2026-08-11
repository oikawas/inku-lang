"""The English path reads a numeral, and asks nothing of the noun that follows.

Ruling B ([I-204], 2026-08-11).  The Japanese path read both number words and
numerals and never asked what was being counted; the English path read only number
words and only when one of 32 nouns followed.  One reader in two shapes gives two
answers, and the English answer was wrong on sixteen stored works.

The Japanese path is deliberately not widened here.  A bare numeral with no
counter is true as often as it is false in Japanese (angles, fractions and
percentages read as counts), and settling that needs its own ruling.
"""

from __future__ import annotations

import pytest

from inku_server.counts import _explicit_counts_from_ddl


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        ("Draw 12 circles.", {12}),
        ("Draw 233 marks.", {233}),
        ("Line up 40 short horizontal red strokes.", {40}),
    ],
)
def test_t15_a_numeral_is_a_count(ddl: str, expected: set[int]) -> None:
    assert _explicit_counts_from_ddl(ddl) == frozenset(expected)


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        # `petals` was not in the noun table, and neither was anything else a
        # description is free to name.
        ("Draw twelve petals.", {12}),
        ("Scatter one hundred twenty small black pen circles.", {120}),
    ],
)
def test_t16_the_reader_does_not_require_a_noun_it_knows(ddl: str, expected: set[int]) -> None:
    assert _explicit_counts_from_ddl(ddl) == frozenset(expected)


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        # Still unread: Japanese with no counter. True and false in equal number.
        ("十二の円を描く。", set()),
        # Read, and by the Japanese path, which asks for a counter.
        ("円を12個描く。", {12}),
        # An angle, a fraction and a percentage are not counts.
        ("立方体の向き: 30度回転。", set()),
        ("画面下1/3に灰色の線を引く。", set()),
        ("下草を50散らす。", set()),
    ],
)
def test_t17_the_japanese_path_did_not_move(ddl: str, expected: set[int]) -> None:
    assert _explicit_counts_from_ddl(ddl) == frozenset(expected)


@pytest.mark.parametrize(
    "ddl",
    [
        # A radius, not two counts. Without this, the fifty-case count corpus reads
        # one work's radius as the counts 0 and 11.
        "Place a circle of radius 0.11 in the lower-right focus.",
        "Cover 1/3 of the field in gray.",
        "Leave 40% of the field empty.",
    ],
)
def test_a_digit_inside_another_number_is_not_a_count(ddl: str) -> None:
    assert _explicit_counts_from_ddl(ddl) == frozenset()


def test_the_reader_still_finds_nothing_where_there_is_nothing() -> None:
    assert _explicit_counts_from_ddl("Fill background with white.") == frozenset()
    assert _explicit_counts_from_ddl(None) == frozenset()
