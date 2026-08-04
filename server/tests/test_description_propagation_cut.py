"""記述の伝播を Stage 1.5 で切る -- 契約 tasks/description-propagation-cut.md.

T-1 / T-2 / T-3 / T-3b / T-5 / T-9. T-4 は test_background_governor.py が持ち、
T-6 は test_carriage.py、T-7 は test_ddl_reference_corpus.py、T-8 は Kotlin 側。

Every gate here is entered through the production path. Calling a predicate on
its own skips the caller's gate and over-reports -- the 44%-vs-0% incident.
"""

from __future__ import annotations

import pytest

# Importing the app is what creates the schema for the test database.
from inku_server.api import app as _app  # noqa: F401
from inku_server import composer
from inku_server.api_core.routers import render as render_routes
from inku_server.coerce import coerce_score
from inku_server.schema import Score

DESCRIPTION = "ひさかたの光のどけき春の日にしづ心なく花の散るらむ"
PROSE = "[fine] 円がある。円は黒い。"
STAGE1_DDL = "黒い円を中心に置く。"

SCORE = Score.model_validate(
    {"instructions": [{"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1}]}
)


class Recorder:
    """What each consumer was handed on the production path."""

    def __init__(self) -> None:
        self.plugin_source: list[str | None] = []
        self.plugin_seed: list[str | None] = []
        self.stage15_context: list[str | None] = []
        self.stage2_ddl: list[str] = []
        self.stage2_kwargs: list[dict] = []
        self.coerce_ddl: list[str] = []


@pytest.fixture
def wired(monkeypatch):
    rec = Recorder()

    class FakeExpansion:
        ddl = STAGE1_DDL
        provenance: list = []
        warnings: list = []
        instructions: list = []

    def fake_sketch(text, *, model=None, lang="ja", grain="fine"):
        return PROSE, 11, 22

    def fake_interpret(text, **kwargs):
        return STAGE1_DDL, None, 3, 4

    def fake_expand(ddl, *, source_text=None, lang="ja", seed_text=None, **kwargs):
        rec.plugin_source.append(source_text)
        rec.plugin_seed.append(seed_text)
        return FakeExpansion()

    def fake_expand_intermediate(ddl, *, context_text=None, **kwargs):
        rec.stage15_context.append(context_text)
        return ddl

    def fake_compose(ddl, **kwargs):
        rec.stage2_ddl.append(ddl)
        rec.stage2_kwargs.append(dict(kwargs))
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
        "description": DESCRIPTION,
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


def compose_request(**overrides):
    body = {
        "ddl": STAGE1_DDL,
        "description": DESCRIPTION,
        "sketch_text": PROSE,
        "sketch_grain": "fine",
        "instruction_lang": "ja",
    }
    body.update(overrides)
    return render_routes.ComposeRequest(**body)


def interpret_request(**overrides):
    body = {
        "description": DESCRIPTION,
        "sketch": True,
        "instruction_lang": "ja",
        "expand_intermediate": True,
    }
    body.update(overrides)
    return render_routes.InterpretRequest(**body)


# --------------------------------------------------------------------- T-1

def test_t1_the_paint_path_hands_coerce_the_ddl_alone(wired):
    """/api/paint. One of the two call sites; the other has its own test, so a
    perturbation that restores the concatenation at one site turns exactly one
    of them red instead of being absorbed by the other."""
    run_paint(paint())

    assert wired.coerce_ddl == [STAGE1_DDL]
    assert PROSE not in wired.coerce_ddl[0]
    assert DESCRIPTION not in wired.coerce_ddl[0]


def test_t1_the_compose_path_hands_coerce_the_ddl_alone(wired):
    """/api/compose. Forgetting this site leaves the endpoint on the old
    behaviour while the paint endpoint looks fixed."""
    render_routes.api_compose(compose_request(), {"id": "test-user"})

    assert wired.coerce_ddl == [STAGE1_DDL]
    assert PROSE not in wired.coerce_ddl[0]
    assert DESCRIPTION not in wired.coerce_ddl[0]


def test_t1_coerce_reads_a_single_line_even_when_the_prose_is_long(wired):
    """The concatenation was `prose\\nDDL`, so its trace is a leading line the
    DDL never wrote. A context that still carries one is the old shape."""
    run_paint(paint(sketch_text="岩の面を水が速く流れ落ちる。濡れた岩は黒い。"))

    assert wired.coerce_ddl[0].split("\n", 1)[0] == STAGE1_DDL


# --------------------------------------------------------------------- T-2

def test_t2_stage2_is_called_with_the_ddl_and_no_description(wired):
    run_paint(paint())

    assert wired.stage2_ddl == [STAGE1_DDL]
    # No keyword carries the prose or the description into Stage 2.
    for kwargs in wired.stage2_kwargs:
        assert PROSE not in repr(kwargs)
        assert DESCRIPTION not in repr(kwargs)


def test_t2_the_user_message_the_provider_receives_is_the_ddl(monkeypatch, wired):
    """End to end, down to the string handed to the Stage 2 provider.

    Re-adding the [原文] branch is what turns this red. Asserting only on
    `compose`'s arguments would stay green if the branch came back inside
    composer and read the description from somewhere else.
    """
    sent: list[str] = []

    def fake_anthropic(user_msg, **kwargs):
        sent.append(user_msg)
        return SCORE, 5, 6

    monkeypatch.setattr(composer, "_compose_anthropic", fake_anthropic)
    monkeypatch.setattr(render_routes, "compose", composer.compose)
    monkeypatch.setattr(render_routes, "_resolved_stage2_model", lambda model, actor=None: None)
    monkeypatch.delenv("INKU_LLM_BACKEND", raising=False)

    run_paint(paint())

    assert sent == [STAGE1_DDL]
    assert "[原文]" not in sent[0]
    assert "[original text]" not in sent[0]
    assert PROSE not in sent[0]
    assert DESCRIPTION not in sent[0]


# --------------------------------------------------------------------- T-3

MULTILINE_DDL = (
    "地: 生成りの紙、細かい紙目。\n"
    "夜空に白い小さな楕円を静かに散らす。"
)


def test_t3_a_surface_word_on_the_second_line_is_read():
    """13.6% of production works have a multi-line expanded_ddl. Reading only
    the first line -- which was the original description before the cut -- makes
    the governor blind to everything the DDL wrote below it.

    The surface word, not a fill clause: `_EXPLICIT_BACKGROUND_CLAUSE` is
    searched against the whole ddl either way, so a clause on the second line
    is found even by a first-line read and gates nothing. What passes through
    `_source_context` is the marker path, and this case is the one that turns
    red when the first-line read comes back -- measured, not assumed.
    """
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.05, 0.03], "color": "white"}
            ],
        }
    )

    assert coerce_score(score, ddl=MULTILINE_DDL).background == "black"


def test_t3_a_second_line_with_no_surface_word_is_still_governed():
    """Control: the whole-string read is not "keep every background". Same two
    lines, with the surface word taken out."""
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {"primitive": "ellipse", "center": [0.5, 0.5], "size": [0.05, 0.03], "color": "white"}
            ],
        }
    )
    ddl = "地: 生成りの紙、細かい紙目。\n静かに白い小さな楕円を散らす。"

    assert coerce_score(score, ddl=ddl).background == "white"


# -------------------------------------------------------------------- T-3b

PRODUCTION_SHAPED_DDL = (
    "背景を黒で塗りつぶす。白い細筆の細い縦線を三百本、上から下へ散らす。"
    "黒い細い余白線を存在の重心として右上の焦点へ二本引く。透明な膜を重ねる。境界が滲む。"
)


def test_t3b_a_production_shaped_ddl_keeps_the_background_it_asked_for():
    """The guard `_looks_like_generated_background_plan` suspected a single-line,
    four-clause string beginning with 背景を of being a machine-generated plan
    pasted into the DESCRIPTION field, and returned before the clause check.

    That is the ordinary shape of a DDL. With the description gone from the
    context the guard had nothing left to judge and only misfired: 54 of 604
    dark production works washed to white with it, 1 without it. Fixing
    `_source_context` alone does not move that 54 -- the DDL here is a single
    line, so a whole-string read changes nothing.
    """
    score = Score.model_validate(
        {
            "background": "blue",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "white",
                    "arrangement": {"count": 110, "layout": "vertical"},
                }
            ],
        }
    )

    assert coerce_score(score, ddl=PRODUCTION_SHAPED_DDL).background == "blue"


def test_t3b_the_governor_is_still_reached_without_a_clause():
    """Control for the case above: removing the guard did not disarm the
    governor. A dark background with no fill clause and no surface marker is
    still washed."""
    score = Score.model_validate(
        {
            "background": "black",
            "instructions": [
                {
                    "primitive": "line",
                    "from": [0.5, 0.0],
                    "to": [0.5, 1.0],
                    "color": "white",
                    "arrangement": {"count": 110, "layout": "vertical"},
                }
            ],
        }
    )
    ddl = "静かな気配の中に、白い細い縦線を三百本、上から下へ散らす。境界が滲む。透明な膜を重ねる。"

    assert coerce_score(score, ddl=ddl).background == "white"


# --------------------------------------------------------------------- T-5

def test_t5_the_compose_trio_still_receives_the_prose(wired):
    """Stage 1.5 and earlier are not what this contract cuts. Without this,
    "cut everything" passes T-1 and T-2 while deleting the 0.5 layer's effect."""
    run_paint(paint())

    assert wired.plugin_source == [PROSE]
    assert wired.stage15_context == [PROSE]


def test_t5_the_interpret_trio_still_receives_the_prose(wired):
    """The second trio. render.py has two sets of these three arguments and
    only the first is on the paint path."""
    render_routes.api_interpret(interpret_request(), {"id": "test-user"})

    assert wired.plugin_source == [PROSE]
    assert wired.stage15_context == [PROSE]


def test_t5_the_compose_endpoint_trio_still_receives_the_prose(wired):
    render_routes.api_compose(compose_request(), {"id": "test-user"})

    assert wired.plugin_source == [PROSE]
    assert wired.stage15_context == [PROSE]


# --------------------------------------------------------------------- T-9

def test_t9_the_plugin_seed_is_the_description_on_every_entry_path(wired):
    """The seed is hashed, never read as language, and `source_text` beside it
    is the prose. Two arguments of one call with different jobs."""
    run_paint(paint())
    render_routes.api_compose(compose_request(), {"id": "test-user"})
    render_routes.api_interpret(interpret_request(), {"id": "test-user"})

    assert wired.plugin_seed == [DESCRIPTION, DESCRIPTION, DESCRIPTION]
    assert wired.plugin_source == [PROSE, PROSE, PROSE]


# The real plugin manager below. An argument-equality assert would pass while
# the seed still moved through some other path, so the gate is on the RESOLVED
# numbers: `若葉` fires Nature.leaves, whose expansion writes 葉形を 4〜6枚 and a
# per-leaf lean, and both are resolved out of the seed by sha256. The resolved
# values land in the expansion's instructions, not in its text -- the ranges are
# consumed into structured instructions, so comparing the expanded DDL string
# would compare two strings that never carried a seed at all.

PLUGIN_DESCRIPTION_A = "若葉の頃、山の斜面がひかる。"
PLUGIN_DESCRIPTION_B = "若葉が出そろい、風が渡っていく。"
PLUGIN_PROSE_A = "若葉が枝に付いている。葉は小さい。"
PLUGIN_PROSE_B = "若葉が枝に付いている。葉は小さく、数は多い。"


@pytest.fixture
def real_expansion(monkeypatch):
    """Only the model calls are replaced. The expansion runs for real and every
    instruction it resolved is recorded as it is produced on the entry path."""
    resolved: list[list[dict]] = []
    expand = render_routes.DOCUMENT_PLUGIN_MANAGER.expand

    def recording_expand(ddl, **kwargs):
        result = expand(ddl, **kwargs)
        resolved.append([dict(item) for item in result.instructions])
        return result

    def fake_sketch(text, *, model=None, lang="ja", grain="fine"):
        return PROSE, 11, 22

    def fake_interpret(text, **kwargs):
        return STAGE1_DDL, None, 3, 4

    def fake_compose(ddl, **kwargs):
        return SCORE, 5, 6

    monkeypatch.setattr(render_routes.DOCUMENT_PLUGIN_MANAGER, "expand", recording_expand)
    monkeypatch.setattr(render_routes, "sketch_from_life", fake_sketch)
    monkeypatch.setattr(render_routes, "interpret_detail", fake_interpret)
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    return resolved


def _pair(resolved: list[list[dict]]) -> tuple[list[dict], list[dict]]:
    assert len(resolved) == 2, f"expected two expansions, got {len(resolved)}"
    assert resolved[0], "the plugin never fired -- the gate would be vacuous"
    return resolved[0], resolved[1]


def run_compose(**overrides):
    return render_routes.api_compose(compose_request(**overrides), {"id": "test-user"})


def run_interpret(**overrides):
    return render_routes.api_interpret(interpret_request(**overrides), {"id": "test-user"})


# (a) stability -- the prose is an LLM output that moves between runs and the
# author can edit it; the description is the identity of the work.

def test_t9a_compose_the_same_description_with_two_proses_resolves_alike(real_expansion):
    run_compose(description=PLUGIN_DESCRIPTION_A, sketch_text=PLUGIN_PROSE_A)
    run_compose(description=PLUGIN_DESCRIPTION_A, sketch_text=PLUGIN_PROSE_B)

    first, second = _pair(real_expansion)
    assert first == second


def test_t9a_paint_the_same_description_with_two_proses_resolves_alike(real_expansion):
    run_paint(paint(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_A))
    run_paint(paint(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_B))

    first, second = _pair(real_expansion)
    assert first == second


def test_t9a_interpret_the_same_description_with_two_proses_resolves_alike(real_expansion):
    """api_interpret holds its own trio; the other two share the one inside
    _call_compose_detail."""
    run_interpret(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_A)
    run_interpret(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_B)

    first, second = _pair(real_expansion)
    assert first == second


# (b) bound to the description. Without this direction, an implementation that
# seeds from the ddl, from a constant, or from req.seed_text -- the RENDERER
# performance seed, normally None, exactly the accident the name collision
# invites -- passes (a): none of them move when the prose changes.

def test_t9b_compose_two_descriptions_with_the_same_prose_resolve_apart(real_expansion):
    run_compose(description=PLUGIN_DESCRIPTION_A, sketch_text=PLUGIN_PROSE_A)
    run_compose(description=PLUGIN_DESCRIPTION_B, sketch_text=PLUGIN_PROSE_A)

    first, second = _pair(real_expansion)
    assert first != second


def test_t9b_paint_two_descriptions_with_the_same_prose_resolve_apart(real_expansion):
    run_paint(paint(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_A))
    run_paint(paint(description=PLUGIN_DESCRIPTION_B, sketch=False, sketch_text=PLUGIN_PROSE_A))

    first, second = _pair(real_expansion)
    assert first != second


def test_t9b_interpret_two_descriptions_with_the_same_prose_resolve_apart(real_expansion):
    run_interpret(description=PLUGIN_DESCRIPTION_A, sketch=False, sketch_text=PLUGIN_PROSE_A)
    run_interpret(description=PLUGIN_DESCRIPTION_B, sketch=False, sketch_text=PLUGIN_PROSE_A)

    first, second = _pair(real_expansion)
    assert first != second


def test_t9_the_resolved_numbers_are_what_the_gate_compares(real_expansion):
    """Guard the arithmetic the six gates above depend on: the seed's effect is
    a count and a rotation, and the two runs must differ in those, not in some
    unrelated field that happens to be present."""
    run_compose(description=PLUGIN_DESCRIPTION_A, sketch_text=PLUGIN_PROSE_A)
    run_compose(description=PLUGIN_DESCRIPTION_B, sketch_text=PLUGIN_PROSE_A)

    first, second = _pair(real_expansion)
    rotations = [
        [item.get("rotation") for item in side]
        for side in (first, second)
    ]
    assert any(value is not None for value in rotations[0]), "no rotation was resolved"
    assert (len(first), rotations[0]) != (len(second), rotations[1])
