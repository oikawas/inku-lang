"""写生 (Stage 0.5) acceptance -- contract tasks/stage05-sketch.md, T-1/T-2/T-5/T-6/T-7/T-9.

Every gate here asserts on the arguments the production path actually passed.
Asserting on a helper called in isolation would pass while the layer reached
nobody: an unconsumed probe is a vacuous gate.

T-3 (dynamic range) and T-4 (semantic carry) are not here. Both need the model
and at least two repetitions of twenty poems; they are measured by the harness
under cli/out2/ and reported with their numbers.
"""

from __future__ import annotations

import pytest

# Importing the app is what creates the schema for the test database; these
# gates call the paint generator directly rather than through HTTP.
from inku_server.api import app as _app  # noqa: F401
from inku_server.api_core.routers import render as render_routes
from inku_server.schema import Score
from inku_server.sketch import DEFAULT_SKETCH_GRAIN, SKETCH_GRAINS, build_system_prompt, normalize_sketch_grain


SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)


class Recorder:
    """What each consumer of the description was actually handed."""

    def __init__(self) -> None:
        self.sketch_inputs: list[tuple[str, str, str]] = []  # (text, lang, grain)
        self.stage1_text: list[str] = []
        self.plugin_source: list[str | None] = []
        self.plugin_seed: list[str | None] = []
        self.stage15_context: list[str | None] = []
        self.stage2_description: list[str | None] = []
        self.coerce_ddl: list[str] = []


@pytest.fixture
def wired(monkeypatch):
    """Replace every model call with a recorder, leaving the wiring untouched."""
    rec = Recorder()

    def fake_sketch(text, *, model=None, lang="ja", grain=DEFAULT_SKETCH_GRAIN):
        rec.sketch_inputs.append((text, lang, grain))
        return f"[{grain}] 円がある。円は黒い。", 11, 22

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

    monkeypatch.setattr(render_routes, "sketch_from_life", fake_sketch)
    monkeypatch.setattr(render_routes, "interpret_detail", fake_interpret)
    monkeypatch.setattr(render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", fake_expand)
    monkeypatch.setattr(render_routes, "expand_intermediate_for_lang", fake_expand_intermediate)
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    monkeypatch.setattr(render_routes, "coerce_score", fake_coerce)
    return rec


def paint(**overrides):
    body = {
        "description": "ひさかたの光のどけき春の日にしづ心なく花の散るらむ",
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


# --------------------------------------------------------------------- T-1

def test_t1_stage05_runs_and_its_output_reaches_stage1(wired):
    response = run_paint(paint())

    assert wired.sketch_inputs, "Stage 0.5 was never called"
    assert wired.sketch_inputs[0][0] == "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"
    # Stage 1 read the prose, not the description.
    assert wired.stage1_text == ["[fine] 円がある。円は黒い。"]
    assert response.sketch_text == "[fine] 円がある。円は黒い。"
    # Perturbation check: returning the description unchanged from 0.5 makes the
    # two sides equal, and this assertion is what turns red.
    assert wired.stage1_text[0] != req_description()


def req_description() -> str:
    return "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"


# --------------------------------------------------------------------- T-2

def test_t2_the_same_text_reaches_all_five_consumers(wired):
    run_paint(paint())

    prose = "[fine] 円がある。円は黒い。"
    # The five places the description used to go, asserted on what was passed:
    # Stage 1, the plugin expansion (twice: source and seed), Stage 1.5, Stage 2
    # and coerce. If 0.5 only reached Stage 1 the cut contract cannot be written
    # and M1's range does not reproduce (contract section 0.2).
    assert wired.stage1_text == [prose]
    assert wired.plugin_source == [prose]
    assert wired.plugin_seed == [prose]
    assert wired.stage15_context == [prose]
    assert wired.stage2_description == [prose]
    assert wired.coerce_ddl and wired.coerce_ddl[0].startswith(prose)
    # None of them kept the raw description.
    assert req_description() not in wired.coerce_ddl[0]


def test_t2_with_the_layer_off_the_description_travels_as_before(wired):
    run_paint(paint(sketch=False))

    assert wired.sketch_inputs == []
    assert wired.stage1_text == [req_description()]
    assert wired.plugin_source == [req_description()]
    assert wired.stage15_context == [req_description()]
    assert wired.stage2_description == [req_description()]


def test_t2_saving_and_display_keep_the_authors_own_words(wired):
    response = run_paint(paint())

    # The prose is what the pipeline read; the description is what the work is.
    assert response.description == req_description()
    assert response.sketch_text != response.description


# --------------------------------------------------------------------- T-5

def test_t5_a_failing_stage05_still_paints_from_the_description(wired, monkeypatch):
    def boom(text, **kwargs):
        raise RuntimeError("the provider is down")

    monkeypatch.setattr(render_routes, "sketch_from_life", boom)
    response = run_paint(paint())

    assert wired.stage1_text == [req_description()]
    assert response.svg, "the paint did not complete"
    assert response.sketch_fallback_used is True
    assert response.sketch_text == req_description()


def test_t5_an_empty_answer_counts_as_a_failure(wired, monkeypatch):
    monkeypatch.setattr(render_routes, "sketch_from_life", lambda text, **kwargs: ("   ", None, None))
    response = run_paint(paint())

    assert wired.stage1_text == [req_description()]
    assert response.sketch_fallback_used is True


# --------------------------------------------------------------------- T-6

def test_t6_an_edited_prose_is_what_gets_interpreted(wired):
    edited = "岩の面を水が速く流れ落ちる。濡れた岩は黒い。"
    run_paint(paint(sketch_text=edited))

    # The author's own prose reached all five, and the model was not asked again.
    assert wired.sketch_inputs == []
    assert wired.stage1_text == [edited]
    assert wired.plugin_source == [edited]
    assert wired.stage15_context == [edited]
    assert wired.stage2_description == [edited]
    assert wired.coerce_ddl[0].startswith(edited)


# --------------------------------------------------------------------- T-7

def test_t7_a_saved_work_redraws_without_calling_the_layer_again(wired):
    stored = "白い花びらが幾つも落ちる。影は薄い。"
    response = run_paint(paint(sketch=False, sketch_text=stored, sketch_grain="coarse"))

    # No model call, and the stored prose is what the pipeline read. Deleting the
    # stored-column read is what turns this red.
    assert wired.sketch_inputs == []
    assert wired.stage1_text == [stored]
    assert response.sketch_text == stored
    assert response.sketch_grain == "coarse"


def test_t7_the_compose_path_carries_the_stored_prose_without_running_the_layer(wired):
    stored = "白い花びらが幾つも落ちる。影は薄い。"
    req = render_routes.ComposeRequest(
        ddl="黒い円を中心に置く。",
        description=req_description(),
        sketch_text=stored,
        sketch_grain="coarse",
        instruction_lang="ja",
    )
    response = render_routes.api_compose(req, {"id": "test-user"})

    assert wired.sketch_inputs == []
    assert wired.plugin_source == [stored]
    assert wired.stage15_context == [stored]
    assert wired.stage2_description == [stored]
    assert wired.coerce_ddl[0].startswith(stored)
    assert response.sketch_text == stored
    assert response.sketch_grain == "coarse"


def test_t7_the_grain_is_stored_with_the_work(monkeypatch, wired):
    saved: dict = {}

    def fake_add(**kwargs):
        saved.update(kwargs)
        return {"id": "h1", "description_hash": None, "lineage_node_id": None,
                "lineage_parent_node_id": None, "derivation_kind": None}

    monkeypatch.setattr(render_routes, "_add_history_item", fake_add)
    run_paint(paint(sketch_grain="coarse", save_history=True))

    assert saved["sketch_grain"] == "coarse"
    assert saved["sketch_text"] == "[coarse] 円がある。円は黒い。"
    # What the author wrote is what the work records as its text.
    assert saved["input_text"] == req_description()
    assert saved["source_text"] == req_description()


# --------------------------------------------------------------------- T-9

def test_t9_no_grain_given_means_fine(wired):
    response = run_paint(paint())

    assert wired.sketch_inputs[0][2] == "fine"
    assert response.sketch_grain == "fine"


def test_t9_coarse_changes_the_prose_and_the_ddl_end_to_end(wired):
    fine = run_paint(paint(sketch_grain="fine"))
    coarse = run_paint(paint(sketch_grain="coarse"))

    # The prose differs...
    assert fine.sketch_text != coarse.sketch_text
    # ...and the difference is what the downstream layers read, not a value
    # recorded and dropped. Ignoring the parameter inside the 0.5 call makes the
    # two runs identical here.
    assert wired.stage1_text[0] != wired.stage1_text[1]
    assert wired.stage2_description[0] != wired.stage2_description[1]
    assert wired.coerce_ddl[0] != wired.coerce_ddl[1]
    assert coarse.sketch_grain == "coarse"


def test_t9_an_unknown_grain_is_refused_rather_than_defaulted():
    with pytest.raises(Exception):
        render_routes.PaintRequest(description="x", sketch=True, sketch_grain="segmented")


def test_t9_both_grains_write_a_different_prompt():
    prompts = {grain: build_system_prompt(lang="ja", grain=grain) for grain in SKETCH_GRAINS}
    assert prompts["fine"] != prompts["coarse"]
    for lang in ("ja", "en"):
        assert build_system_prompt(lang=lang, grain="fine") != build_system_prompt(lang=lang, grain="coarse")
    # Both languages are served, and neither prompt is empty.
    assert build_system_prompt(lang="en", grain="fine") != build_system_prompt(lang="ja", grain="fine")


def test_t9_the_grain_normalizer_falls_back_only_where_nothing_was_asked():
    assert normalize_sketch_grain(None) == "fine"
    assert normalize_sketch_grain("") == "fine"
    assert normalize_sketch_grain("coarse") == "coarse"
    assert normalize_sketch_grain("COARSE") == "coarse"


# ------------------------------------------------------- the layer's own rules

def test_the_prompt_forbids_the_vocabulary_of_feeling():
    """Design principles 3 and 7: the layer writes in the language of things."""
    for grain in SKETCH_GRAINS:
        ja = build_system_prompt(lang="ja", grain=grain)
        assert "感情語" in ja and "美しい" in ja
        en = build_system_prompt(lang="en", grain=grain)
        assert "no words of feeling" in en.lower()


def test_the_english_prompt_never_says_the_word_that_means_a_pencil_weight():
    """`sketch` is a weight word in the Stage 1 English prompt (pale, faint,
    sketch -> pencil). Putting it in this layer's output vocabulary would move a
    Stage 1 field, so the English prompt names the job without naming the word."""
    for grain in SKETCH_GRAINS:
        assert "sketch" not in build_system_prompt(lang="en", grain=grain).lower()


def test_the_layer_is_observable_in_the_trace(wired):
    response = run_paint(paint(include_trace=True))

    assert response.trace is not None
    assert response.trace["sketch_text"] == "[fine] 円がある。円は黒い。"
    assert response.trace["sketch_grain"] == "fine"
    assert response.trace["sketch_fallback_used"] is False
    assert response.trace["sketch_prompt_digest"]
