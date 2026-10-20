"""The juxtaposition's rules are the shared core's (2026-10-20).

The rows in data/juxtaposition-cases.json were written by the rules Server and
Web held before (juxtaposition.py, joinJuxtaposition), and the core reads the
same file; Android and Swift read it when they call the core. These checks ask
the rows of Server's own entry points, which now carry the requests to the core.
"""

from __future__ import annotations

import json
import pathlib
import random

import pytest

from inku_server.juxtaposition import JuxtapositionAnswerError, _core, gather_candidates, same_text, suggest_juxtaposition

CASES = json.loads((pathlib.Path(__file__).parent / "data" / "juxtaposition-cases.json").read_text(encoding="utf-8"))
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'


@pytest.mark.parametrize("row", CASES["same"], ids=[r["why"] for r in CASES["same"]])
def test_every_shared_pair_is_told_apart_as_before(row):
    assert same_text(row["a"], row["b"]) is row["same"]


@pytest.mark.parametrize("row", CASES["join"], ids=[r["joined"] or "empty" for r in CASES["join"]])
def test_every_shared_sentence_is_joined_as_web_joined_it(row):
    assert _core("join", description=row["description"], sentence=row["sentence"])["joined"] == row["joined"]


@pytest.mark.parametrize("row", CASES["gather"], ids=[r["why"] for r in CASES["gather"]])
def test_every_shared_gathering_keeps_the_sentences_server_kept(row):
    request = row["request"]
    sources = [(source["id"], source["text"]) for source in request["sources"]]
    fields = {key: request[key] for key in ("description", "lineage", "added", "exclude")}
    drawn = gather_candidates(sources, **fields, rng=random.Random(3), limit=request["limit"])
    assert len(drawn) == row["count"]
    assert all(candidate["history_ids"] == row["kept"][candidate["sentence"]] for candidate in drawn)
    everything = gather_candidates(sources, **fields, rng=random.Random(3), limit=10_000)
    assert {candidate["sentence"]: candidate["history_ids"] for candidate in everything} == row["kept"]


@pytest.mark.parametrize("row", CASES["check"], ids=[r["why"] for r in CASES["check"]])
def test_every_shared_answer_is_taken_or_sent_back_as_before(row):
    request = row["request"]
    asked = []

    def reader(**kwargs):
        asked.append(kwargs)
        return request["answer"]

    def suggest():
        return suggest_juxtaposition(svg=SVG, description=request["description"], lineage=[],
                                     candidates=request["candidates"], model="m", language=request["language"],
                                     settings={}, reader=reader)

    if "choices" in row:
        assert suggest()["choices"] == row["choices"]
        assert len(asked) == 1
    else:
        with pytest.raises(JuxtapositionAnswerError) as refused:
            suggest()
        assert str(refused.value) == row["detail"]
        assert len(asked) == 2 and row["detail"] in asked[1]["text"]


@pytest.mark.parametrize("row", CASES["prompt"], ids=[r["why"] for r in CASES["prompt"]])
def test_every_shared_prompt_is_the_text_server_sent(row):
    answer = _core("prompt", **row["request"])
    assert (answer["system"], answer["text"]) == (row["system"], row["text"])
