"""The autonomous refinement's progression, gate and record are the shared core's (2026-10-20).

The rows in data/autonomous-refine-cases.json were written from the plan's rules by a
generator that holds them apart from the core, and the core reads the same file.
Server asks the rows through its binding, as its own autonomous refinement will, and
checks that a juxtaposition child's record reads back as a sentence its lineage added.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_render import pipeline_autonomous_refine

CASES = json.loads((pathlib.Path(__file__).parent / "data" / "autonomous-refine-cases.json").read_text(encoding="utf-8"))
ROWS = [(group, row) for group in ("next", "record", "invalid", "measure", "refused") for row in CASES[group]]


def ask(request: dict) -> dict:
    return json.loads(pipeline_autonomous_refine(json.dumps(request, ensure_ascii=False).encode("utf-8")))


@pytest.mark.parametrize(("group", "row"), ROWS, ids=[f"{group}: {row['why']}" for group, row in ROWS])
def test_every_shared_case_answers_as_the_table_says(group, row):
    # Failure: Server's binding answers a row otherwise than the core's own test, or draws the gate otherwise.
    answer = ask(row["request"])
    if answer.get("outcome") == "refused":
        assert answer.pop("detail")
    assert answer == row["answer"]


def test_a_juxtaposition_childs_record_reads_back_as_a_sentence_its_lineage_added(monkeypatch):
    # Failure: the record lacks the key Server reads, so the next juxtaposition offers the same sentence again.
    from inku_server.api_core.routers import render

    row = next(row for row in CASES["record"] if row["request"]["kind"] == "juxtaposition")
    metadata = ask(row["request"])["metadata"]
    monkeypatch.setattr(render._db, "get_lineage_branch", lambda *_: {
        "nodes": [{"history": {"source_text": "根の記述。"}}],
        "edges": [{"metadata": metadata}],
    })
    _lineage, added = render._juxtaposition_lineage({"id": "u"}, {"lineage_node_id": "n"})
    assert added == [row["request"]["juxtaposition"]["sentence"]]
