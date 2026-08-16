"""Acceptance for the おもて / surfaces saijiki category (ddl-engine 15).

Contract `a-shape-can-say-how-its-surface-is`, ruling
`RULING-omote-surface-category-20260812.md`. The category exists because the
lower layers held a mechanism the upper layer had no word for: a fill was asked
for in words in 1.3% of works with a closed shape, 96.7% of the works that came
out filled were never asked to be, and five descriptions that stated a fill
outright reached `filled` zero times out of five. Stage 1 could write 埋める and
Stage 2 read 塗る -- an empty intersection in Japanese.

T-3 through T-6 of the contract are not here. They go through Stage 2, which is
an LLM, so they are measured by running `inku-cli paint --input-mode ddl`
against a deployed server and reported as reach rates rather than as green or
red. What is here is everything a deterministic layer decides.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import get_args

from fastapi.testclient import TestClient

from inku_server import db, saijiki, schema
from inku_server.api import app
from inku_server.coerce import coerce_score
from inku_server.interpreter import SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT_PREFIX_EN
from inku_server.reference import build_reference
from inku_server.renderer import build_texture_metadata
from inku_server.schema import Score

client = TestClient(app)

_FIXTURES = Path(__file__).parent / "fixtures" / "prompts"
_BRANCH = "with_surface_on_a_closed_shape"


def _omote() -> saijiki.SaijikiCategory:
    return next(category for category in saijiki.SAIJIKI if category.key == "omote")


# --- T-1: the table ---------------------------------------------------------


def test_omote_holds_eleven_words_and_one_default() -> None:
    """T-1. Eleven words, and 空 alone carries the default."""
    category = _omote()
    assert category.name_ja == "おもて"
    assert category.name_en == "surfaces"
    assert len(category.words) == 11
    defaults = [word.surface_ja for word in category.words if word.default]
    assert defaults == ["空"]
    # つらなり says how a line is and おもて says how a surface is, so the second
    # stands beside the first.
    keys = [c.key for c in saijiki.SAIJIKI]
    assert keys[keys.index("tsuranari") + 1] == "omote"


def test_omote_texture_values_cover_the_enum_minus_ground() -> None:
    """The `score_value`s are the SurfaceTexture enum, minus one by ruling.

    `paper_grain` is ground rather than surface, so 地: keeps it (I-229). Without
    this the values would be a field nothing reads, free to drift into a texture
    the renderer has never heard of.

    **Two by ruling until 2026-08-13, when `none` joined.** 空 does mean "no
    texture at all", and while that was written as "the word carries no value"
    the category had two roads out of it -- eight words to `surface.texture` and
    塗り to `filled` -- and the measurement said the second road did not carry
    (ddl-engine 18).
    """
    values = {word.score_value for word in _omote().words if word.score_value}
    assert values == set(get_args(schema.SurfaceTexture)) - {"paper_grain"}


def test_the_two_words_that_are_not_qualities_carry_no_texture_value() -> None:
    """塗り is a texture like the other eight; the density words are not qualities.

    Pinned by pair rather than by set: `wash` is already in the set from 薄墨, so
    giving another word a second copy of it would leave a set comparison green
    while that word had quietly become a wash.

    **This test said the opposite until 2026-08-13** -- 塗り fell to `filled` and
    carried no texture value, which the 2026-08-12 ruling chose deliberately: a
    solid fill is the material's default way of filling and `surface` was the
    printmaker's mark (measured brightness 224.9 against 41.9-131.1). What the
    later ruling changed is not that judgement but where the word is *said*. The
    renderer still keeps the two apart -- `solid` reaches the fill layer and
    never the surface-texture layer -- and 塗り now travels in the field the
    other eight travel in, because that is the only field the model writes into
    (0/14 in English through `filled`, 12/14 through `texture`).
    """
    values = {word.surface_ja: word.score_value for word in _omote().words}
    assert values == {
        "空": "none",
        "塗り": "solid",
        "薄墨": "wash",
        "粒": "grain",
        "点": "stipple",
        "平行線": "hatch",
        "交差線": "crosshatch",
        "にじみ": "bleed",
        "アクアチント": "aquatint",
        "濃い": None,
        "薄い": None,
    }


# --- T-2: what is published -------------------------------------------------


def _auth():
    suffix = uuid.uuid4().hex[:8]
    group = db.add_user_group(f"omote-{suffix}")
    user = db.add_user(
        username=f"omote-{suffix}",
        email=f"omote-{suffix}@example.test",
        password="password-123",
        permission_groups=["users"],
        group_id=group["id"],
    )
    token = db.create_session(user["id"])
    return {"Authorization": f"Bearer {token}"}, user, group, token


def test_api_and_reference_publish_the_category() -> None:
    """T-2. `GET /api/saijiki` and the reference document both carry おもて."""
    headers, user, group, token = _auth()
    try:
        for lang, name, word in (("ja", "おもて", "塗り"), ("en", "surfaces", "flat")):
            response = client.get(f"/api/saijiki?lang={lang}", headers=headers)
            assert response.status_code == 200
            categories = response.json()["categories"]
            published = next(c for c in categories if c["key"] == "omote")
            assert published["name_ja"] == "おもて"
            assert published["name_en"] == "surfaces"
            assert word in published["words"]
            assert name in json.dumps(categories, ensure_ascii=False)
    finally:
        db.delete_session(token)
        db.delete_user(user["id"])
        db.delete_user_group(group["id"])

    saijiki_section = build_reference()["saijiki"]
    assert "おもて" in saijiki_section["core_categories_ja"]
    assert "surfaces" in saijiki_section["core_categories_en"]
    assert "塗り" in saijiki_section["core_categories_ja"]["おもて"]
    assert "flat" in saijiki_section["core_categories_en"]["surfaces"]


def test_display_flag_and_membership_are_separate_properties() -> None:
    """The pair T-1 and T-2 measure. `display` decides publication alone."""
    assert all(word.display for word in _omote().words)
    published = {
        word
        for category in saijiki.display_categories("ja")
        if category["key"] == "omote"
        for word in category["words"]
    }
    assert published == {word.surface_ja for word in _omote().words}


# --- T-9 / T-10: what the category must not hold ----------------------------


def test_paper_grain_is_not_a_surface_word() -> None:
    """T-9. 紙目 is ground, not surface; `地:` keeps it (2026-08-12 ruling)."""
    surfaces = {word.surface_ja for word in _omote().words}
    surfaces |= {word.surface_en for word in _omote().words}
    assert "紙目" not in surfaces
    assert "paper grain" not in surfaces
    assert "paper_grain" not in {word.score_value for word in _omote().words}


def test_every_surface_word_is_a_state_noun() -> None:
    """T-10. No verbs.

    Principle 5 says the output is a static image and SPEC §3.1 says the action
    vocabulary is about placing, not marking; `描く` was pruned in v1.92 for
    being the second kind. Adding 塗る would reverse that ruling, so the word is
    塗り, the noun -- how a surface is, not what a hand did to it (author's
    ruling, 2026-08-12, which chose the noun over べた). The named three are the
    ones the contract lists; the ending test is what catches the next one
    (粒立つ and 滲む were both verbs in the Stage 1 phrases this replaces).
    """
    words = _omote().words
    # 塗る is the verb and 塗り is the noun: the ruling turns on exactly that
    # difference, so the verb stays forbidden while the noun is the word.
    named_verbs = {"塗る", "塗りつぶす", "埋める", "paint", "fill"}
    assert not named_verbs & {w.surface_ja for w in words}
    assert not named_verbs & {w.surface_en for w in words}
    # Japanese dictionary-form verb endings. 濃い / 薄い end in い (adjectives).
    dictionary_form = tuple("うくぐすつぬぶむる")
    assert [w.surface_ja for w in words if w.surface_ja.endswith(dictionary_form)] == []


# --- T-13: the Stage 1 phrase ----------------------------------------------


def test_stage1_prompt_defines_the_solid_surface_phrase() -> None:
    """T-13. The phrase in `interpreter.py`, not the word in `saijiki.py`.

    T-1 reads the table; a table entry with no phrase to write it in reaches
    nothing. The contract's own note on P-4 -- that reverting only the Stage 1
    side of the hatch fix would miss -- is this gap named.
    """
    assert "「面: 塗り。」" in SYSTEM_PROMPT_PREFIX
    assert '"Surface: flat."' in SYSTEM_PROMPT_PREFIX_EN
    # T-4's other half, the one defect A was: Stage 1 wrote 面: 斜めに埋める。 and
    # the Stage 2 table read 平行線, which was not in it. Four in the DDL, zero
    # in the Score.
    assert "「面: 平行線。」" in SYSTEM_PROMPT_PREFIX
    assert "面: 斜めに埋める。" not in SYSTEM_PROMPT_PREFIX
    assert '"Surface: hatch."' in SYSTEM_PROMPT_PREFIX_EN
    assert '"Surface: hatched diagonally."' not in SYSTEM_PROMPT_PREFIX_EN
    # The density words, whose only carriage into the Score is a Stage 1 phrase.
    assert "「面: 濃い。」" in SYSTEM_PROMPT_PREFIX and "「面: 薄い。」" in SYSTEM_PROMPT_PREFIX
    assert '"Surface: dense."' in SYSTEM_PROMPT_PREFIX_EN
    assert '"Surface: faint."' in SYSTEM_PROMPT_PREFIX_EN


# --- T-12: the golden fixture is declared against, not rewritten ------------


def test_golden_fixture_is_not_regenerated() -> None:
    """T-12. The allow-list carries a dated declaration and the fixture is intact.

    The fixture is the Build 591 prompt. Regenerating it is the mistake this
    forbids: it would erase the diff instead of declaring it, and every later
    reader would see a prompt that matches itself and learn nothing.
    """
    ja = (_FIXTURES / "stage1_prefix_ja.golden.txt").read_text(encoding="utf-8")
    en = (_FIXTURES / "stage1_prefix_en.golden.txt").read_text(encoding="utf-8")
    # The pre-change text is still there, in both directions.
    assert "面: 斜めに埋める。" in ja
    assert "「面: 塗り。」" not in ja
    assert "おもて:" not in ja
    assert '"Surface: hatched diagonally."' in en
    assert '"Surface: flat."' not in en
    assert "surfaces: empty" not in en

    declarations = Path(__file__).with_name("test_saijiki_golden.py").read_text(
        encoding="utf-8"
    )
    assert "2026-08-12" in declarations
    assert "a-shape-can-say-how-its-surface-is" in declarations


# --- T-7: coerce moves a surface onto a shape that has an interior ----------


def _instruction(**changes) -> dict:
    base = {
        "primitive": "line",
        "from": [0.18, 0.50],
        "to": [0.82, 0.50],
        "color": "black",
        "weight": "pen",
    }
    base.update(changes)
    return base


def _circle(**changes) -> dict:
    return _instruction(
        primitive="circle", center=[0.5, 0.5], radius=0.2, **{"from": None}, to=None, **changes
    )


def _coerced(instructions: list[dict]) -> tuple[Score, dict[str, int]]:
    report: dict[str, int] = {}
    score = coerce_score(
        Score.model_validate(
            {
                "version": "0.1.0",
                "canvas": {"aspect": "square", "ground": None},
                "background": "white",
                "presence": None,
                "instructions": instructions,
            }
        ),
        ddl=None,
        lang="ja",
        branch_report=report,
    )
    return score, report


def test_surface_on_a_line_moves_to_the_closed_shape_before_it() -> None:
    """T-7, the moving half.

    53.4% of every surface in production sat on a line (739) or an arc (59) and
    was drawn as nothing. The `面: ...` sentence was about the shape it followed,
    so that is where the surface goes back to.
    """
    score, report = _coerced(
        [_circle(), _instruction(surface={"texture": "wash", "density": 0.5})]
    )
    circle = next(ins for ins in score.instructions if ins.primitive == "circle")
    line = next(ins for ins in score.instructions if ins.primitive == "line")
    assert circle.surface is not None and circle.surface.texture == "wash"
    assert circle.surface.density == 0.5
    assert line.surface is None or line.surface.texture == "none"
    assert report[_BRANCH] >= 1


def test_surface_with_no_shape_to_move_to_is_dropped_and_counted() -> None:
    """T-7, the dropping half. Nothing is invented where there is no interior."""
    score, report = _coerced([_instruction(surface={"texture": "hatch"})])
    line = next(ins for ins in score.instructions if ins.primitive == "line")
    assert line.surface is None or line.surface.texture == "none"
    assert report[_BRANCH] >= 1


def test_a_shape_that_already_has_a_surface_keeps_its_own() -> None:
    """One texture request must not become two textured instructions."""
    score, _ = _coerced(
        [
            _circle(surface={"texture": "hatch"}),
            _instruction(surface={"texture": "wash"}),
        ]
    )
    circle = next(ins for ins in score.instructions if ins.primitive == "circle")
    line = next(ins for ins in score.instructions if ins.primitive == "line")
    assert circle.surface is not None and circle.surface.texture == "hatch"
    assert line.surface is None or line.surface.texture == "none"


def test_a_surface_already_on_a_closed_shape_does_not_fire_the_branch() -> None:
    """The branch is a repair, so a Score that needs none must not move."""
    score, report = _coerced([_circle(surface={"texture": "wash"})])
    circle = next(ins for ins in score.instructions if ins.primitive == "circle")
    assert circle.surface is not None and circle.surface.texture == "wash"
    assert report.get(_BRANCH, 0) == 0


def test_the_search_walks_back_past_other_lines() -> None:
    """`直前の閉図形` is the nearest closed shape before it, not the nearest
    instruction. A line between the shape and the stray surface must not stop
    the walk.

    **The word was `grain` until ddl-engine 20.** It had to change: 粒 stopped
    being a stray that day -- it says how the mark runs, so on a line it is
    where it belongs and there is nothing to walk back for. `hatch` is a word
    about an interior, which is what this test has always been about. The two
    words are kept apart by `MARK_SURFACE_WORDS`, and the mark-word half is
    measured in `test_a_named_sheet_changes_how_the_mark_runs.py` (T-11).
    """
    score, _ = _coerced(
        [
            _circle(),
            _instruction(**{"from": [0.1, 0.2], "to": [0.9, 0.2]}),
            _instruction(**{"from": [0.1, 0.8], "to": [0.9, 0.8]}, surface={"texture": "hatch"}),
        ]
    )
    circle = next(ins for ins in score.instructions if ins.primitive == "circle")
    assert circle.surface is not None and circle.surface.texture == "hatch"


def test_a_mark_word_on_a_line_is_not_walked_back_at_all() -> None:
    """The control for the test above, from ddl-engine 20.

    Without it, an implementation that kept walking every surface back would
    leave the test above green and this category's split unmeasured on the side
    that changed.
    """
    # Named, not read from the set: a loop over the production set is empty --
    # and so green -- exactly when the set has been emptied.
    assert set(schema.MARK_SURFACE_WORDS) == {"grain", "bleed"}
    for word in ("grain", "bleed"):
        score, report = _coerced(
            [
                _circle(),
                _instruction(**{"from": [0.1, 0.8], "to": [0.9, 0.8]}, surface={"texture": word}),
            ]
        )
        circle = next(ins for ins in score.instructions if ins.primitive == "circle")
        line = next(ins for ins in score.instructions if ins.primitive == "line")
        assert circle.surface is None or circle.surface.texture == "none", word
        assert line.surface is not None and line.surface.texture == word, word
        assert report.get(_BRANCH, 0) == 0, word


# --- T-8: metadata reports only what is drawn -------------------------------


def test_texture_metadata_omits_a_surface_on_a_line() -> None:
    """T-8. The render JSON used to say a texture was there that no pixel showed.

    This is independent of T-7: the renderer is handed Scores that never went
    through coerce -- a saved Score replayed, a Score composed elsewhere -- so
    the report has to make the judgement itself.
    """
    score = Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": {"aspect": "square", "ground": None},
            "background": "white",
            "presence": None,
            "instructions": [
                _instruction(surface={"texture": "wash"}),
                _circle(surface={"texture": "hatch"}),
            ],
        }
    )
    metadata = build_texture_metadata(score, svg_profile="display")
    reported = metadata["render_surface_textures"]
    assert [entry["texture"] for entry in reported] == ["hatch"]
    assert [entry["instruction_index"] for entry in reported] == [1]

    # And with nothing drawable left, the key is absent rather than empty --
    # which is also what `texture_degraded` reads to decide.
    only_a_line = score.model_copy(update={"instructions": score.instructions[:1]})
    bare = build_texture_metadata(only_a_line, svg_profile="compat")
    assert "render_surface_textures" not in bare
    assert bare["texture_degraded"] is False
