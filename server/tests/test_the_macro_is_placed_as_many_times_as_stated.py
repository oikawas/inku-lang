"""A plugin offers one whole unit; the body says how many of them to place.

Ruling A (2026-08-11): what a plugin hands over is one unit, and a count stated in
the body means "that whole, N times".  The body does not reach inside the unit --
how many marks one unit becomes is settled by the plugin document's own range
declaration and the seed.

The two quantities are measured separately here on purpose.  A change that
multiplies the wrong one (N leaves inside one unit instead of N units) passes any
test that only counts marks.
"""

from __future__ import annotations

import pytest

from inku_server.plugins.document_format import DOCUMENT_PLUGIN_MANAGER

# A real plugin entry, so the unit's breakdown comes from a plugin document rather
# than from anything this test invents.  `Nature.青葉` declares 6-8 leaf forms.
REFERENCE_JA = "Nature.青葉"


def _expand(ddl: str, *, lang: str = "ja", source_text: str | None = None, seed: str | None = None):
    return DOCUMENT_PLUGIN_MANAGER.expand(ddl, source_text=source_text, lang=lang, seed_text=seed)


def _units(result) -> list[int]:
    return [int(entry["units"]) for entry in result.provenance]


def test_t6_a_stated_count_becomes_the_number_of_units_ja() -> None:
    result = _expand("Nature.青葉を三つ置く。")
    assert [entry["plugin_term"] for entry in result.provenance] == [REFERENCE_JA]
    assert _units(result) == [3]


def test_t6_a_stated_count_becomes_the_number_of_units_en() -> None:
    result = _expand("Place three Nature.青葉 marks.", lang="en")
    assert [entry["plugin_term"] for entry in result.provenance] == [REFERENCE_JA]
    assert _units(result) == [3]


@pytest.mark.parametrize(
    ("numeral", "expected"),
    [("三つ", 3), ("十二個", 12), ("二十個", 20)],
)
def test_t7_changing_the_numeral_changes_the_number_of_units(numeral: str, expected: int) -> None:
    """The count has to be read, not defaulted: three numerals, three answers."""
    result = _expand(f"Nature.青葉を{numeral}置く。")
    assert _units(result) == [expected]


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("three", 3), ("twelve", 12), ("twenty", 20)],
)
def test_t7_changing_the_numeral_changes_the_number_of_units_en(phrase: str, expected: int) -> None:
    result = _expand(f"Place {phrase} Nature.青葉 marks.", lang="en")
    assert _units(result) == [expected]


def test_t8_the_seed_moves_the_breakdown_and_not_the_number_of_units() -> None:
    """Same count, two seeds: the unit count is fixed by the body, the inside is not."""
    fixed = "Nature.青葉を三つ置く。"
    first = _expand(fixed, seed="seed-a")
    second = _expand(fixed, seed="seed-b")
    assert _units(first) == [3]
    assert _units(second) == [3]
    # The breakdown is the seed's to move -- these two seeds resolve the plugin's
    # 6-8 range differently, which is what tells the two quantities apart.
    assert len(first.instructions) != len(second.instructions)


def test_t9_an_explicit_reference_fires_with_or_without_the_source_text() -> None:
    written = "Nature.青葉を三つ置く。"
    assert _units(_expand(written, source_text=None)) == [3]
    assert _units(_expand(written, source_text=written)) == [3]


def test_t9_a_firing_word_needs_the_source_text_and_the_count_comes_with_it() -> None:
    """`菖蒲` is a firing word of `Nature.下草`, and firing words read the description."""
    ddl = "菖蒲を三つ置く。"
    with_source = _expand(ddl, source_text=ddl)
    assert [entry["plugin_term"] for entry in with_source.provenance] == ["Nature.下草"]
    assert _units(with_source) == [3]

    without_source = _expand(ddl, source_text=None)
    assert without_source.provenance == ()
    assert without_source.instructions == ()


def test_t10_a_count_that_cannot_be_delivered_whole_is_declined() -> None:
    """Forty units of thirteen marks is over the 400-mark work budget.

    Declining leaves one unit standing.  Trimming to whatever fits would put a
    number in the work that neither the description nor the plugin ever named.
    """
    result = _expand("Nature.青葉を四十個置く。")
    assert _units(result) == [1]
    assert len(result.instructions) < 400


def test_t11_the_declined_count_is_on_the_record() -> None:
    result = _expand("Nature.青葉を四十個置く。")
    declined = [line for line in result.warnings if "40" in line and REFERENCE_JA in line]
    assert declined, result.warnings


def test_t12_the_body_does_not_reach_inside_the_unit() -> None:
    """The breakdown is the plugin document's and the seed's: twelve marks, as before.

    The counted case is measured per unit as well.  A change that multiplied the
    stated count into the unit's own range -- thirty-six leaves on one branch
    instead of three branches of twelve -- would leave the mark total looking right.
    """
    plain = _expand("Nature.青葉を置く。")
    assert _units(plain) == [1]
    assert len(plain.instructions) == 12

    counted = _expand("Nature.青葉を三つ置く。")
    # Per unit, against the units actually placed -- whether the count reached the
    # unit total at all is T-6's and T-7's question, and keeping it out of here is
    # what makes the two quantities separately measurable.
    units = _units(counted)[0]
    per_unit = len(counted.instructions) / units
    # `Nature.青葉` declares 6-8 leaf forms, each transcribed as a pair of arcs.
    assert 12 <= per_unit <= 16, per_unit


# T-13 stood here through the stage 2 commit: `Draw 12 circles.` had to stay
# unread, so that widening the reader could not ride in on ruling A.  Ruling B
# widened it in the next commit, which turns that assertion false by design; the
# reader's behaviour is now gated by T-15 to T-17 in
# `test_the_english_reader_reads_a_numeral.py`.
