"""Juxtaposition: candidates from the author's own works, and the model's four picks."""

from __future__ import annotations

import json
import random

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from inku_server import juxtaposition
from inku_server.juxtaposition import JuxtapositionAnswerError, gather_candidates, same_text, suggest_juxtaposition
from inku_server.persistence import juxtaposition as sources_module
from inku_server.persistence.schema import HistoryRow
from inku_server.persistence.settings import checked_juxtaposition_limit, normalize_juxtaposition_settings

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="2"/></svg>'
OTHERS = ["雪原の狼。", "港の灯台。", "砂の時計。", "森の鹿。", "川の舟。"]


def _candidates(count: int) -> list[dict]:
    return [{"id": f"c{n:04d}", "sentence": f"一文{n}。", "history_ids": [f"w{n}"]} for n in range(1, count + 1)]


def test_the_same_poem_in_another_spelling_and_a_sentence_already_added_are_not_offered():
    # Failure: the author is offered their own poem again in kana, a sentence the lineage already
    # added, or one of the four just shown, which the prototype's models kept returning to.
    sources = [
        ("a", "ちはやぶる　神代も聞かず　竜田川　からくれなゐに　水くくるとは"),
        ("b", "ちはやぶる神代もきかず竜田川からくれなゐに水くくるとは"),
        ("c", "廃駅のホームに時刻表だけが残り、来ない列車の時間を正確に告げ続けた。続きの文。"),
        ("d", "満月の夜、塩田は一面の鏡になり、歩く人はみな空を渡る人になった。(AI)"),
        ("e", "雪原を渡るオオカミの群れ。"),
        ("f", "#5 雪原を渡るオオカミの群れ。"),
        ("g", "A sentence in English."),
    ]
    candidates = gather_candidates(
        sources,
        description="満月の夜、塩田は一面の鏡になり、歩く人はみな空を渡る人になった。",
        lineage=["夜の港で、灯台の光だけが、黒い波を一本ずつ数えていた。"],
        added=["廃駅のホームに時刻表だけが残り、来ない列車の時間を正確に告げ続けた。"],
        exclude=[],
        rng=random.Random(0),
        limit=10,
    )
    by_sentence = {candidate["sentence"]: candidate["history_ids"] for candidate in candidates}
    poem = "ちはやぶる　神代も聞かず　竜田川　からくれなゐに　水くくるとは"
    assert set(by_sentence) == {poem, "雪原を渡るオオカミの群れ。"}
    assert by_sentence[poem] == ["a", "b"]
    assert by_sentence["雪原を渡るオオカミの群れ。"] == ["e", "f"]
    assert same_text("満月の夜、塩田は鏡になったが、月も人も映らなかった。", "満月の夜、塩田は一面の鏡になり、歩く人はみな空を渡る人になった。") is False


def test_candidates_are_drawn_down_to_the_limit_in_a_fresh_order():
    # Failure: a long list goes out whole and in one fixed order, so the model's lean to the head
    # of the list chooses the same sentences every time.
    sources = [(f"w{n}", "".join(chr(0x4E00 + n * 5 + k) for k in range(4)) + "の文。") for n in range(50)]
    first = gather_candidates(sources, description="今の記述。", rng=random.Random(1), limit=20)
    second = gather_candidates(sources, description="今の記述。", rng=random.Random(2), limit=20)
    assert len(first) == len(second) == 20
    assert [c["sentence"] for c in first] != [c["sentence"] for c in second]
    assert len({c["id"] for c in first}) == 20


def test_an_answer_naming_a_sentence_not_offered_is_sent_back_once_then_refused():
    # Failure: an id the list never held reaches the author, or a wrong answer is retried forever.
    candidates = _candidates(6)
    prompts = []

    def reader(**kwargs):
        prompts.append(kwargs["text"])
        if len(prompts) == 1:
            return json.dumps({"choices": [{"id": "c9999", "reason": "r"}] + [
                {"id": f"c000{n}", "reason": "r"} for n in (1, 2, 3)]})
        return "```json\n" + json.dumps({"choices": [
            {"id": "c0003", "reason": "三つ目"}, {"id": "c0001", "reason": "一つ目"},
            {"id": "c0006", "reason": "六つ目"}, {"id": "c0002", "reason": "二つ目"}]}) + "\n```"

    result = suggest_juxtaposition(svg=SVG, description="今の記述。", lineage=["今の記述。"], candidates=candidates,
                                   model="test:vision", language="ja", settings={}, reader=reader)
    assert [choice["sentence"] for choice in result["choices"]] == ["一文3。", "一文1。", "一文6。", "一文2。"]
    assert [choice["rank"] for choice in result["choices"]] == [1, 2, 3, 4]
    assert result["choices"][0]["history_ids"] == ["w3"] and result["choices"][2]["position"] == 1.0
    assert "c9999" in prompts[1] and "c9999" not in prompts[0]

    with pytest.raises(JuxtapositionAnswerError, match="同じ番号"):
        suggest_juxtaposition(svg=SVG, description="今の記述。", lineage=[], candidates=candidates, model="test:vision",
                              language="ja", settings={}, reader=lambda **_: json.dumps({"choices": [
                                  {"id": "c0001", "reason": "r"}] * 4}))


def test_only_the_authors_own_usable_works_lend_a_sentence(monkeypatch):
    # Failure: a shared work, another person's work, or a test, demo, DDL or trashed work lends its
    # words to the author's juxtaposition.
    engine = create_engine("sqlite://")
    HistoryRow.__table__.create(engine)
    session = Session(engine)

    def work(history_id, user_id="u", **fields):
        session.add(HistoryRow(id=history_id, user_id=user_id, at=0, input="入力。", **fields))

    work("own", source_text="作者の文。")
    work("input-only", source_text=None)
    work("other", user_id="v", source_text="ほかの人の文。")
    work("trashed", source_text="捨てた文。", trashed=1)
    work("lineage-only", source_text="系譜だけの文。", history_visibility="lineage_only")
    work("ddl", source_text="", display_label="DDL")
    work("demo", source_text="見本の文。", display_label="[demo]")
    work("test", source_text="試験の文。", note="Test Data 2026-10-19")
    work("held", source_text="固定の文。")
    work("empty", source_text="  ")
    session.commit()
    monkeypatch.setattr(sources_module, "locked_history_ids", lambda _session, ids: {"held"} & set(ids))
    assert sorted(sources_module.owned_description_sources(session, {"id": "u"})) == [
        ("input-only", "入力。"), ("own", "作者の文。")]


def test_the_route_refuses_a_held_work_and_keeps_the_lineage_out_of_the_candidates(monkeypatch):
    # Failure: a work held by its DDL is offered a redraw from its words, or the work itself, its
    # lineage or a sentence the lineage already added comes back among the candidates.
    from inku_server.api_core.routers import render

    work = {"id": "w", "source_text": "今の記述。", "svg": SVG, "lineage_node_id": "n-w"}
    monkeypatch.setattr(render._db, "get_items", lambda *_: [dict(work, description_locked=True)])
    with pytest.raises(HTTPException) as held:
        render.api_juxtaposition(render.JuxtapositionBody(history_id="w"), {"id": "u"})
    assert held.value.status_code == 409

    monkeypatch.setattr(render._db, "get_items", lambda *_: [dict(work)])
    monkeypatch.setattr(render._db, "get_lineage_branch", lambda *_: {
        "nodes": [{"history": {"source_text": "根の記述。"}}, {"history": {"source_text": "今の記述。"}}],
        "edges": [{"metadata": {"juxtaposition": {"sentence": "前に足した一文。"}}}],
    })
    monkeypatch.setattr(render._db, "juxtaposition_sources", lambda _user: [
        ("w", "今の記述。"), ("r", "根の記述。"), ("p", "前に足した一文。")] + [
        (f"s{n}", text) for n, text in enumerate(OTHERS)])
    monkeypatch.setattr(render._db, "get_juxtaposition_settings", lambda: {"candidate_limit": 10})
    monkeypatch.setattr(render._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(render, "prepare_vision_settings", lambda *_: {})
    seen = {}

    def suggest(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"sentence": c["sentence"], "reason": "r", "history_ids": c["history_ids"], "rank": n,
                             "position": 0.0, "joined": kwargs["description"] + c["sentence"]}
                            for n, c in enumerate(kwargs["candidates"][:4], start=1)],
                "candidates": len(kwargs["candidates"]), "model": kwargs["model"]}

    monkeypatch.setattr(render, "suggest_juxtaposition", suggest)
    answer = render.api_juxtaposition(render.JuxtapositionBody(history_id="w", model="test:vision"), {"id": "u"})
    offered = {candidate["sentence"] for candidate in seen["candidates"]}
    assert offered == set(OTHERS)
    assert seen["lineage"] == ["根の記述。", "今の記述。"]
    assert len(answer.choices) == 4 and answer.candidates == 5


def test_the_route_offers_the_model_no_more_sentences_than_the_administrators_limit(monkeypatch):
    # Failure: the limit is saved in the settings, yet every sentence in the database still goes out.
    from inku_server.api_core.routers import render

    monkeypatch.setattr(render._db, "get_items", lambda *_: [{"id": "w", "source_text": "今の記述。", "svg": SVG}])
    monkeypatch.setattr(render._db, "juxtaposition_sources", lambda _user: [
        (f"s{n}", "".join(chr(0x4E00 + n * 5 + k) for k in range(4)) + "の文。") for n in range(30)])
    monkeypatch.setattr(render._db, "get_juxtaposition_settings", lambda: {"candidate_limit": 10})
    monkeypatch.setattr(render._db, "get_model_settings", lambda: {})
    monkeypatch.setattr(render, "prepare_vision_settings", lambda *_: {})
    seen = {}

    def suggest(**kwargs):
        seen.update(kwargs)
        return {"choices": [{"sentence": c["sentence"], "reason": "r", "history_ids": c["history_ids"], "rank": n,
                             "position": 0.0, "joined": kwargs["description"] + c["sentence"]}
                            for n, c in enumerate(kwargs["candidates"][:4], start=1)],
                "candidates": len(kwargs["candidates"]), "model": kwargs["model"]}

    monkeypatch.setattr(render, "suggest_juxtaposition", suggest)
    answer = render.api_juxtaposition(render.JuxtapositionBody(history_id="w", model="test:vision"), {"id": "u"})
    assert len(seen["candidates"]) == 10 and answer.candidates == 10


def test_the_limit_stays_in_its_range_when_saved_and_when_read():
    # Failure: a limit out of range is saved, or a stored row that says a million, or nothing
    # usable, offers the model every sentence there is.
    assert normalize_juxtaposition_settings(None) == {"candidate_limit": 400}
    assert normalize_juxtaposition_settings({"candidate_limit": 50}) == {"candidate_limit": 50}
    for stored in (1_000_000, 9, True, "400", None):
        assert normalize_juxtaposition_settings({"candidate_limit": stored}) == {"candidate_limit": 400}
    for refused in (9, 1001, "400"):
        with pytest.raises(ValueError):
            checked_juxtaposition_limit(refused)
    assert checked_juxtaposition_limit(10) == 10 and checked_juxtaposition_limit(1000) == 1000


def test_the_prompt_lists_every_candidate_with_its_id_and_the_image(monkeypatch):
    # Failure: the candidates or the picture never reach the model.
    calls = []
    candidates = _candidates(4)

    def reader(**kwargs):
        calls.append(kwargs)
        return json.dumps({"choices": [{"id": c["id"], "reason": "r"} for c in candidates]})

    suggest_juxtaposition(svg=SVG, description="今の記述。", lineage=[], candidates=candidates, model="test:vision",
                          language="en", settings={}, reader=reader)
    assert all(f"{c['id']}: {c['sentence']}" in calls[0]["text"] for c in candidates)
    assert calls[0]["image"].startswith("data:image/png;base64,")
    assert "Return JSON only" in calls[0]["system"]
    assert juxtaposition.CHOICES == 4


def test_the_sentence_follows_the_description_as_the_work_keeps_it():
    # Failure: the child is drawn from the description without the author's labels (a batch number,
    # a [comment] naming the poem's source), which Web kept when it joined the sentence itself.
    candidates = _candidates(4)
    answer = json.dumps({"choices": [{"id": c["id"], "reason": "r"} for c in candidates]})
    result = suggest_juxtaposition(svg=SVG, description="ちはやぶる神代も聞かず", lineage=[], candidates=candidates,
                                   model="test:vision", language="ja", settings={}, reader=lambda **_: answer,
                                   written="1. ちはやぶる神代も聞かず [古今和歌集]")
    assert result["choices"][0]["joined"] == "1. ちはやぶる神代も聞かず [古今和歌集]。一文1。"
