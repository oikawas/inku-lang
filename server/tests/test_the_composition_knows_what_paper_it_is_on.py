"""The support reaches Stage 2, and the Score keeps what Stage 2 said about it.

Contract: the-composition-knows-what-paper-it-is-on ([I-135] option A).

Before this, the composition was built without knowing which paper it would be
drawn on, and the paper was written over its declaration just before rendering.
Two things changed: the prompt now states the support, and the Score keeps the
support the composition declared even when the performance uses another one.

The gates here are the deterministic half. Whether the model obeys is measured
by running it, not asserted -- an LLM is not a fixture.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from inku_server import composer

# Imported for the side effect: the app's startup is what creates the tables the
# paint route reads its model settings from.
from inku_server.api import app as _app  # noqa: F401
from inku_server.api_core.routers import render as render_routes
from inku_server.limits import DEFAULT_LIMITS
from inku_server.schema import Score

ROOT = pathlib.Path(__file__).resolve().parents[2]

# The three papers the gates use: one taller than wide, one wider than tall, and
# the default. `square` is in the set on purpose -- the ruling says a square
# request states its paper too, so it must not be silently the same as no paper.
PAPERS = ("pillar", "wide", "square")

_HEADINGS = {
    "ja": composer._CANVAS_BLOCK_HEADING_JA,
    "en": composer._CANVAS_BLOCK_HEADING_EN,
}


def _support_block(prompt: str, lang: str) -> str:
    """The support block alone.

    Cut out rather than searched for: "支持体" and "support" both appear in the
    conversion rules, so a search over the whole prompt is satisfied by an
    occurrence that has nothing to do with the paper this work is drawn on.
    """
    heading = _HEADINGS[lang]
    start = prompt.find(heading)
    if start < 0:
        return ""
    rest = prompt[start + len(heading) :]
    end = rest.find("\n#")
    return heading + (rest if end < 0 else rest[:end])


def _score(canvas: object | None = None) -> Score:
    payload: dict = {
        "instructions": [
            {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.1, "color": "red"}
        ]
    }
    if canvas is not None:
        payload["canvas"] = canvas
    return Score.model_validate(payload)


# --------------------------------------------------------------- T-1  the body


@pytest.mark.parametrize("lang", ["ja", "en"])
@pytest.mark.parametrize("paper", PAPERS)
def test_t1_the_prompt_states_the_support_it_was_given(lang, paper):
    block = _support_block(composer.build_system_prompt(lang, DEFAULT_LIMITS, paper), lang)
    assert block, f"no support block for {paper}/{lang}"
    assert paper in block
    # The ratio, not only the id: an id alone tells a model nothing about shape.
    assert re.search(r"\d+(\.\d+)?:\d+(\.\d+)?", block)


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_t1_the_orientation_is_not_the_word_used_for_a_shape(lang):
    """`横長` is taught in the conversion rules as the proportion of a MARK
    (`横長の四角` is an ellipse twice as wide as tall). The support has to be
    described in words that cannot be read as an adjective of a mark."""
    block = _support_block(composer.build_system_prompt(lang, DEFAULT_LIMITS, "wide"), lang)
    assert "横長" not in block
    assert ("wider than it is tall" in block) if lang == "en" else ("横に広い" in block)


# ------------------------------------------------------- T-2  paper by paper


def test_t2_a_different_paper_is_a_different_prompt():
    digests = {
        paper: composer._stage2_prompt_digest(
            composer.build_system_prompt("ja", DEFAULT_LIMITS, paper)
        )
        for paper in PAPERS
    }
    assert len(set(digests.values())) == len(PAPERS), digests


# ------------------------------------------- T-3  compose() carries the paper


def test_t3_compose_hands_the_paper_to_the_prompt(monkeypatch):
    seen: dict[str, object] = {}

    def fake_backend(user_msg, *, model=None, system_prompt="", settings=None, trace_sink=None):
        seen["system_prompt"] = system_prompt
        return _score(), 1, 2

    monkeypatch.setattr(composer, "_current_model_settings", dict)
    monkeypatch.setattr(composer, "provider_for_model", lambda *a, **k: ("anthropic", "m"))
    monkeypatch.setattr(composer, "_compose_anthropic", fake_backend)

    metadata: dict[str, str] = {}
    composer.compose(
        "赤い円を三つ散らす。",
        model="m",
        prompt_metadata=metadata,
        canvas_aspect="pillar",
    )
    assert seen["system_prompt"] == composer.build_system_prompt("ja", DEFAULT_LIMITS, "pillar")
    assert metadata["stage2_prompt_digest"] == composer._stage2_prompt_digest(
        composer.build_system_prompt("ja", DEFAULT_LIMITS, "pillar")
    )
    assert metadata["stage2_prompt_digest"] != composer._stage2_prompt_digest(
        composer.SYSTEM_PROMPT
    )


# ------------------------------- T-4  the carriage alone does not move the body


@pytest.mark.parametrize("lang", ["ja", "en"])
@pytest.mark.parametrize("paper", PAPERS)
def test_t4_the_paper_moves_the_support_block_and_nothing_else(lang, paper):
    """Take the support block back out and the prompt is the paperless one, byte
    for byte. Carrying the paper is not licence to reword the rest of the body."""
    paperless = composer.build_system_prompt(lang, DEFAULT_LIMITS, None)
    with_paper = composer.build_system_prompt(lang, DEFAULT_LIMITS, paper)
    assert _support_block(with_paper, lang), "no support block to take back out"
    inserted = composer._canvas_block(paper, lang) + "\n\n"
    assert inserted in with_paper
    assert with_paper.replace(inserted, "", 1) == paperless


# ------------------------------------------------------------ T-5  the examples


@pytest.mark.parametrize(
    "prompt", [composer.SYSTEM_PROMPT, composer.SYSTEM_PROMPT_EN], ids=["ja", "en"]
)
def test_t5_the_examples_show_a_paper_other_than_square(prompt):
    values = set(re.findall(r'"aspect":"([a-z0-9_]+)"', prompt))
    assert len(values) >= 2, values
    assert values - {"square"}


# ----------------------------------------- T-6  the declaration is not erased


def _paint(monkeypatch, *, stage2_score: Score, canvas_aspect: str | None):
    ddl = "赤い円を三つ散らす。"
    monkeypatch.setattr(
        render_routes, "interpret_detail", lambda text, **kwargs: (ddl, None, 3, 4)
    )
    monkeypatch.setattr(
        render_routes, "compose", lambda d, **kwargs: (stage2_score, 5, 6)
    )
    request = render_routes.PaintRequest(
        description="赤い円が三つ散っている",
        sketch=False,
        instruction_lang="ja",
        save_history=False,
        save_artifacts=False,
        count_generation=False,
        auto_repair=False,
        canvas_aspect=canvas_aspect,
    )
    for event in render_routes._paint_events(request, None, {"id": "test-user"}):
        if event["event"] == "done":
            return event["response"]
    raise AssertionError("the paint route produced no answer")


def test_t6_a_declaration_that_disagrees_with_the_performance_survives(monkeypatch):
    response = _paint(
        monkeypatch, stage2_score=_score({"aspect": "pillar"}), canvas_aspect="wide"
    )
    # What the composition was built for.
    assert response.score.canvas.aspect == "pillar"
    # What the picture was drawn on -- the disagreement is readable, not lost.
    assert response.render_canvas_aspect_id == "wide"
    # And the picture really is on that paper: wide is 2350x1000, pillar 200x1000.
    assert 'width="2350"' in response.svg


def test_t6_the_ground_of_a_declaration_survives_with_it(monkeypatch):
    response = _paint(
        monkeypatch,
        stage2_score=_score({"aspect": "pillar", "ground": {"material": "washi"}}),
        canvas_aspect="wide",
    )
    assert response.score.canvas.aspect == "pillar"
    assert response.score.canvas.ground.material == "washi"


# ------------------------------------------------- T-7  no paper, no sentence


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_t7_no_paper_states_no_paper(lang):
    paperless = composer.build_system_prompt(lang, DEFAULT_LIMITS, None)
    constant = composer.SYSTEM_PROMPT if lang == "ja" else composer.SYSTEM_PROMPT_EN
    assert paperless == constant
    # Not only equality with the constant -- that is true by construction and
    # stays true if the support sentence moves INTO the constant. The frozen
    # digest is what a body carrying a paper cannot match.
    assert _support_block(paperless, lang) == ""
    assert _HEADINGS[lang] not in paperless


def test_t7_the_paperless_digests_are_the_frozen_ones():
    """Measured on 2026-08-13 on this branch, after the examples of stage 3 went
    in. The pre-contract values were cfa0e44d64743a14 / c4c26cdbeb3383e7.

    Re-measured 2026-08-14 (ddl-engine 18: a fill is a surface word like the
    other eight). What this test is about -- that a body naming no paper carries
    no support block -- is untouched; the digests move because the Stage 2 body
    and the tool schema moved beneath it. The 2026-08-13 pair was
    e5ebae81b0b41055 / e25a01dc97e8a608."""
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT) == "10e063b6cc175427"
    assert composer._stage2_prompt_digest(composer.SYSTEM_PROMPT_EN) == "7aee944049dbc058"


# The senders. A request that never names `canvas_aspect` gets `None`, and `None`
# means "state no paper" -- so a sender that goes quiet does not fail, it just
# stops composing for its paper. Keyed to the directory: neither tree is synced
# to the deployed server.
_SENDERS = {
    "web": (ROOT / "web", ROOT / "web/src/routes/+page.svelte"),
    "cli": (ROOT / "cli", ROOT / "cli/src/inku_cli/cli.py"),
}


@pytest.mark.parametrize("sender", sorted(_SENDERS))
def test_t7_every_sender_still_names_the_paper(sender):
    tree, source = _SENDERS[sender]
    if not tree.is_dir():
        pytest.skip(f"{sender}/ is not synced to the server; the roll call runs where it exists")
    assert "canvas_aspect" in source.read_text(encoding="utf-8")


# ---------------------------------------------- T-8  the size caveat is stated


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_t8_the_prompt_says_the_paper_may_not_overrule_a_stated_size(lang):
    """A wording gate, and weak on purpose: nothing in this contract MAKES the
    model obey it. Whether it does is M-4, measured by running the model."""
    block = _support_block(composer.build_system_prompt(lang, DEFAULT_LIMITS, "pillar"), lang)
    if lang == "en":
        assert "never a size the description" in block or "may not overrule a size" in block
        assert "may not move the COUNT" in block
    else:
        assert "記述が述べた大きさを支持体の都合で覆さない" in block
        assert "支持体で個数を変えない" in block


# ------------------------------------------- T-10  the effective value travels


def test_t10_a_request_with_no_paper_hands_stage_2_the_default(monkeypatch):
    """`None` on the request means square. The composition must be told square,
    not `None` -- otherwise the default is decided in two places."""
    seen: dict[str, object] = {}

    def fake_compose(ddl, **kwargs):
        seen.update(kwargs)
        return _score(), 5, 6

    monkeypatch.setattr(
        render_routes, "interpret_detail", lambda text, **kwargs: ("赤い円。", None, 3, 4)
    )
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    request = render_routes.PaintRequest(
        description="赤い円が三つ散っている",
        sketch=False,
        instruction_lang="ja",
        save_history=False,
        save_artifacts=False,
        count_generation=False,
        canvas_aspect=None,
    )
    for _event in render_routes._paint_events(request, None, {"id": "test-user"}):
        pass
    assert seen["canvas_aspect"] == "square"


# --------------------------------------------- T-11  the retry knows it too


def test_t11_the_retry_prompt_moves_with_the_paper():
    bodies = {
        paper: render_routes._compose_retry_prompt(
            reason="empty_instructions", lang="ja", canvas_aspect=paper
        )
        for paper in PAPERS
    }
    assert len(set(bodies.values())) == len(PAPERS)
    for paper, body in bodies.items():
        assert paper in body


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_t11_a_retry_with_no_paper_states_none(lang):
    without = render_routes._compose_retry_prompt(
        reason="empty_instructions", lang=lang, canvas_aspect=None
    )
    with_paper = render_routes._compose_retry_prompt(
        reason="empty_instructions", lang=lang, canvas_aspect="pillar"
    )
    assert "pillar" not in without
    assert without != with_paper


def test_t11_the_retry_is_reached_with_the_same_paper_the_first_call_got(monkeypatch):
    """Not the prompt in isolation: the retry is a second call through the same
    site, and a paper that reaches the first call but not the second is exactly
    the defect this stage is for."""
    papers: list[object] = []
    prompts: list[object] = []

    def fake_compose(ddl, **kwargs):
        papers.append(kwargs.get("canvas_aspect"))
        prompts.append(kwargs.get("system_prompt"))
        # The first answer is empty, which is what forces the retry.
        if len(papers) == 1:
            return Score.model_validate({"instructions": []}), 1, 2
        return _score(), 3, 4

    monkeypatch.setattr(composer, "compose", fake_compose)
    monkeypatch.setattr(render_routes, "compose", fake_compose)
    detail = render_routes._call_compose_detail("赤い円。", canvas_aspect="pillar")

    assert papers == ["pillar", "pillar"]
    assert prompts[0] is None
    assert "pillar" in prompts[1]
    assert detail.retry_reasons == ["empty_instructions"]


# ------------------------------------------ the CLI source keys parse cleanly


def test_the_cli_still_sends_the_paper_as_a_literal_key():
    """The census in test_cli_sender_census reads the payload dict by name. This
    narrower check exists so that a rename of the key shows up here too, next to
    the gates that depend on it."""
    tree = ROOT / "cli"
    if not tree.is_dir():
        pytest.skip("cli/ is not synced to the server")
    source = (tree / "src/inku_cli/cli.py").read_text(encoding="utf-8")
    keys = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "canvas_aspect" in keys


# ------------------------------- T-6b  the redraw reads the paper it was on
#
# Added at acceptance, not by the contract. Stage 4 grew a third answer to
# "which paper" when the ruling moved it from "stop overwriting the Score" to
# "read the performed paper off the work's row", and nothing walked that
# entrance: removing the middle branch of `_render_score_svg` left 186 tests
# green (measured on the merged tree). It only binds for a work composed after
# this change, because before it the Score's declaration was overwritten with
# the requested paper and the two answers could never disagree.


def test_t6b_a_redraw_performs_on_the_paper_the_work_was_drawn_on():
    from inku_server.api_core.rendering import _render_score_svg

    payload = _score({"aspect": "pillar"}).model_dump()
    # The work was performed on `wide` even though the composition was built
    # for `pillar` -- exactly the disagreement T-6 makes possible.
    svg, _, _ = _render_score_svg(
        payload,
        catalog_id=None,
        svg_profile="editable",
        work={"render_canvas_aspect_id": "wide"},
    )
    # wide is 2350x1000; pillar, which the Score declares, would be 200x1000.
    assert 'width="2350"' in svg

    # With no row to read, the Score's own declaration still stands.
    fallback, _, _ = _render_score_svg(payload, catalog_id=None, svg_profile="editable")
    assert 'width="200"' in fallback
