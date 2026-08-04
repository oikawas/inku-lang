"""The label rule, and the fact that the stored work keeps what the drawing drops.

The cases live in data/description-label-cases.json because the web editor has
to paint exactly the ranges the server removes, and its own test reads the same
file.  A rule that exists twice needs one corpus.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.description_labels import excluded_spans, pipeline_description

CASES = json.loads(
    (pathlib.Path(__file__).parent / "data" / "description-label-cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_the_pipeline_reads_the_description_without_its_labels(case):
    assert pipeline_description(case["text"]) == case["pipeline"]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_the_spans_name_exactly_what_was_removed(case):
    spans = [[s.start, s.end, s.kind] for s in excluded_spans(case["text"])]
    assert spans == [list(s) for s in case["spans"]]


@pytest.mark.parametrize("case", CASES, ids=[c["why"] for c in CASES])
def test_a_span_covers_the_text_it_claims(case):
    # A span is what the editor greys out: if it named the wrong range, the
    # author would see one thing greyed and another thing dropped.
    text = case["text"]
    for start, end, kind in case["spans"]:
        assert 0 <= start < end <= len(text)
        excerpt = text[start:end]
        if kind == "comment":
            assert excerpt[0] in "[［" and excerpt[-1] in "]］"
        else:
            assert excerpt.strip(" \t　")[0] in "0123456789０１２３４５６７８９"


def test_the_corpus_covers_both_kinds_and_the_cases_that_must_not_be_cut():
    kinds = {kind for case in CASES for _s, _e, kind in case["spans"]}
    assert kinds == {"number", "comment"}
    untouched = [c for c in CASES if not c["spans"]]
    assert len(untouched) >= 4, "the corpus has to say what is description, not only what is a label"


def test_the_original_is_not_modified_in_place():
    text = "01. 春の雪 [出典]"
    pipeline_description(text)
    assert text == "01. 春の雪 [出典]"
