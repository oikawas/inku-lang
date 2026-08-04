"""The label and the comment reach no layer, and the work keeps them anyway.

The unit rule lives in test_description_labels.py.  These gates assert on the
arguments the production path actually passed, because a rule that is correct in
isolation and wired nowhere is a vacuous gate: the recorder below replaces every
model call and leaves the wiring alone.
"""

from __future__ import annotations

import pytest

# Importing the app is what creates the schema for the test database.
from inku_server.api import app as _app  # noqa: F401
from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Score

SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)

RAW = "01. ひさかたの光のどけき春の日に [疎  紀友則 / 古今和歌集（春下）]"
CUT = "ひさかたの光のどけき春の日に"


class Recorder:
    def __init__(self) -> None:
        self.sketch_inputs: list[str] = []
        self.stage1_text: list[str] = []
        self.plugin_source: list[str | None] = []
        self.stage15_context: list[str | None] = []
        self.stage2_description: list[str | None] = []
        self.coerce_ddl: list[str] = []
        self.catalog_source: list[str] = []
        self.plugin_seed: list[str | None] = []


@pytest.fixture
def wired(monkeypatch):
    rec = Recorder()

    def fake_sketch(text, *, model=None, lang="ja", grain="fine"):
        rec.sketch_inputs.append(text)
        return "円がある。円は黒い。", 11, 22

    def fake_interpret(text, **kwargs):
        rec.stage1_text.append(text)
        return "黒い円を中心に置く。", None, 3, 4

    class FakeExpansion:
        ddl = "黒い円を中心に置く。"
        provenance: list = []
        warnings: list = []
        instructions: list = []

    def fake_expand(ddl, *, source_text=None, lang="ja", seed_text=None, **kwargs):
        rec.plugin_source.append(source_text)
        rec.plugin_seed.append(seed_text)
        return FakeExpansion()

    def fake_expand_intermediate(ddl, *, context_text=None, **kwargs):
        rec.stage15_context.append(context_text)
        return ddl

    def fake_compose(ddl, *, original_description=None, **kwargs):
        rec.stage2_description.append(original_description)
        return SCORE, 5, 6

    def fake_coerce(score, *, ddl="", **kwargs):
        rec.coerce_ddl.append(ddl)
        return score

    def fake_select_catalog(source_text, *, fallback_id):
        rec.catalog_source.append(source_text)
        return fallback_id

    monkeypatch.setattr(render_routes, "sketch_from_life", fake_sketch)
    monkeypatch.setattr(render_routes, "interpret_detail", fake_interpret)
    monkeypatch.setattr(render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", fake_expand)
    monkeypatch.setattr(render_routes, "expand_intermediate_for_lang", fake_expand_intermediate)
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    monkeypatch.setattr(render_routes, "coerce_score", fake_coerce)
    monkeypatch.setattr(render_routes, "select_catalog_id", fake_select_catalog)
    return rec


def paint(**overrides):
    body = {
        "description": RAW,
        "sketch": True,
        "instruction_lang": "ja",
        "save_history": False,
        "save_artifacts": False,
        "count_generation": False,
    }
    body.update(overrides)
    return render_routes.PaintRequest(**body)


def run_paint(req):
    for event in render_routes._paint_events(req, None, {"id": "test-user"}):
        if event["event"] == "done":
            return event["response"]
    raise AssertionError("the paint produced no result")


def test_stage05_is_handed_the_description_without_its_labels(wired):
    run_paint(paint())

    assert wired.sketch_inputs == [CUT]
    assert "01." not in wired.sketch_inputs[0]
    assert "[" not in wired.sketch_inputs[0]


def test_with_the_sketch_layer_off_no_later_layer_sees_them_either(wired):
    run_paint(paint(sketch=False))

    assert wired.sketch_inputs == []
    for seen in (wired.stage1_text, wired.plugin_source, wired.stage15_context):
        assert seen == [CUT], seen
    # Since the cut contract, Stage 2 is handed no description at all and coerce
    # reads the DDL alone -- so the labels cannot arrive there by any route.
    assert wired.stage2_description == [None]
    assert wired.coerce_ddl and "紀友則" not in wired.coerce_ddl[0]
    assert wired.coerce_ddl and "01." not in wired.coerce_ddl[0]


def test_the_catalog_selector_reads_the_cut_description_too(wired):
    run_paint(paint(sketch=False, catalog_mode="auto"))

    assert wired.catalog_source == [CUT]


def test_an_injected_stage1_input_is_cut_the_same_way(wired):
    run_paint(paint(sketch=False, stage1_input="02． 春の日に [出典]"))

    assert wired.stage1_text == ["春の日に"]


def test_the_work_keeps_what_the_drawing_dropped(wired):
    response = run_paint(paint())

    # The author's document is the description they wrote, labels and all.
    assert response.description == RAW


def test_a_description_with_no_labels_travels_exactly_as_before(wired):
    plain = "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"
    run_paint(paint(description=plain, sketch=False))

    # The control: the rule must not touch a description that carries no label.
    assert wired.stage1_text == [plain]
    assert wired.plugin_source == [plain]
    assert wired.plugin_seed == [plain]


def test_the_interpret_path_cuts_them_as_the_paint_path_does(wired):
    req = render_routes.InterpretRequest(
        description=RAW, sketch=True, instruction_lang="ja"
    )
    render_routes.api_interpret(req, {"id": "test-user"})

    assert wired.sketch_inputs == [CUT]


def test_the_plugin_seed_is_the_cut_description_too(wired):
    # The seed decides how many leaves a plugin resolves, so it is the
    # description rather than the prose (the cut contract, stage 6).  It is
    # still a layer: the author's numbering must not reach it either, or two
    # works differing only in their label would resolve different counts.
    run_paint(paint())

    assert wired.plugin_seed == [CUT]
