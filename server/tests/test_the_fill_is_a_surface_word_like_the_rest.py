"""Acceptance for ddl-engine 18: a fill is a surface word like the other eight.

Contract `the-fill-is-a-surface-word-like-the-rest` ([I-227], 2026-08-13 ruling:
"the interior's state is said in one vocabulary; stop using `filled` as the road
that says 塗り").

The measurement that made the contract, taken 2026-08-13 against a live model
with the production ceilings lifted: `Surface: flat.` reached `filled` 0 times
out of 14 in English and 2 out of 4 in Japanese, while `Surface: hatch.` reached
`texture` 4 out of 4 and the three texture words together 12 out of 14. Not the
language, not the word count, not sentence-versus-field -- `Fill it solid.`
shortened to `Fill it.` still reached 0 of 3 and the field form `Surface: fill.`
0 of 4. **The destination field was the only thing that moved.**

T-7 is not here. Its observation point is
`test_a_small_mark_stays_small_whoever_wrote_it.py::test_no_frozen_engine_below_this_one_was_rewritten`,
which reads every frozen directory below the current version against its own
manifest; a second copy of that check here would be one more thing to forget to
update. T-13 is not here either: it is an Android JVM test, outside
`make test-server` entirely (`prompts.json` is read by zero server-side checks).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import get_args

from inku_server import composer, saijiki, schema
from inku_server.coerce import coerce_score
from inku_server.interpreter import SYSTEM_PROMPT_PREFIX, SYSTEM_PROMPT_PREFIX_EN
from inku_server.renderer import render
from inku_server.schema import Instruction, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOT = SERVER_ROOT.parent
ANDROID_CONTRACT = (
    ROOT / "android/app/src/test/resources/server_reference/score_schema_contract.json"
)
BRANCH = "with_fill_as_a_surface_word"

# The nine quality words of おもて. 濃い / 薄い are the two density words beside
# them, and they say how dense a quality is rather than which one it is.
QUALITY_WORDS = ("空", "塗り", "薄墨", "粒", "点", "平行線", "交差線", "にじみ", "アクアチント")


def _score(instructions: list[dict]) -> Score:
    return Score.model_validate({"instructions": instructions})


def _coerced(instructions: list[dict]) -> tuple[Score, dict[str, int]]:
    report: dict[str, int] = {}
    score = coerce_score(_score(instructions), ddl=None, lang="ja", branch_report=report)
    return score, report


def _circle(**changes) -> dict:
    base = {"primitive": "circle", "center": [0.5, 0.5], "radius": 0.2, "color": "black"}
    base.update(changes)
    return base


def _line(**changes) -> dict:
    base = {"primitive": "line", "from": [0.18, 0.5], "to": [0.82, 0.5], "color": "black"}
    base.update(changes)
    return base


# --- T-1 / T-2: the vocabulary reaches the Score value set -------------------


def test_solid_is_a_texture_and_every_quality_word_reaches_the_enum() -> None:
    """T-1. `solid` is in the enum, and all nine quality words land inside it.

    Written as "every word's value is in the enum" rather than as set equality,
    because the two sides are not equal and should not be: `paper_grain` is a
    ground word that `地:` keeps (I-229), so the enum is one value wider than the
    vocabulary. A set comparison would have to be relaxed to say that, and a
    relaxed set comparison is what let 塗り sit outside the enum for two days.
    """
    textures = set(get_args(schema.SurfaceTexture))
    assert "solid" in textures

    omote = next(c for c in saijiki.SAIJIKI if c.key == "omote")
    values = {word.surface_ja: word.score_value for word in omote.words}
    for word in QUALITY_WORDS:
        assert values[word] is not None, f"{word} carries no Score value"
        assert values[word] in textures, f"{word} -> {values[word]} is not a texture"
    # And the two density words still carry none: they are not qualities, and
    # giving one a texture value is how a density word would quietly become one.
    assert values["濃い"] is None and values["薄い"] is None


def test_texture_for_surface_maps_both_languages() -> None:
    """T-2. Surface word -> enum, in the shape `weight_for_surface` already had."""
    mapping = saijiki.texture_for_surface()
    assert mapping["塗り"] == "solid"
    assert mapping["flat"] == "solid"
    assert mapping["空"] == "none"
    assert mapping["empty"] == "none"
    assert mapping["薄墨"] == "wash"
    assert mapping["pale ink wash"] == "wash"
    # Nine words, both languages, and not one density word among them.
    assert len(mapping) == 18
    assert "濃い" not in mapping and "dense" not in mapping


# --- T-3: Stage 1 is not what changed ---------------------------------------


def test_the_stage1_phrases_did_not_move() -> None:
    """T-3. The DDL still reads `面: 塗り。` / `Surface: flat.`

    The contract changes where the word goes, not what an author writes or what
    Stage 1 hands over. If this is red, the measurement the contract rests on no
    longer describes the input the model is given.
    """
    assert "- 塗る、塗りつぶす、ベタ、中を塗る、面で満たす → 「面: 塗り。」" in SYSTEM_PROMPT_PREFIX
    assert (
        '- fill, paint, solid fill, filled interior → "Surface: flat."'
        in SYSTEM_PROMPT_PREFIX_EN
    )
    # The whole mapping line, not just the phrase: 「面: 塗る。」 also appears in
    # the prompt, as the counter-example that says not to write a verb, so a
    # bare `"面: 塗り。" in prompt` would stay green while the rule changed.


# --- T-4 / T-5: coerce says it one way, whichever way it arrived -------------


def test_a_filled_closed_shape_gains_the_solid_texture() -> None:
    """T-4. The 2,972 works already saved say their interior the new way too."""
    score, report = _coerced([_circle(filled=True)])
    circle = score.instructions[0]
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert circle.filled is True
    assert report[BRANCH] == 1


def test_filled_on_a_line_does_not_gain_a_surface() -> None:
    """T-4, the half that must not fire. A line has no interior.

    `_with_surface_on_a_closed_shape` exists because 53.4% of production's
    surfaces sat on a line and were drawn as nothing. Deriving a surface onto one
    here would put those straight back.
    """
    score, report = _coerced([_line(filled=True)])
    line = score.instructions[0]
    assert line.surface is None or line.surface.texture == "none"
    assert report.get(BRANCH, 0) == 0


def test_a_solid_texture_gains_filled() -> None:
    """T-5, the other direction.

    Not redundant with T-4: every reader that only knows the boolean depends on
    it -- a saved Score replayed by an older client, and the Android port, whose
    coercer drops a texture it has not heard of and would draw no fill at all.
    """
    score, report = _coerced([_circle(surface={"texture": "solid"})])
    circle = score.instructions[0]
    assert circle.filled is True
    assert circle.surface is not None and circle.surface.texture == "solid"
    assert report[BRANCH] == 1


def test_saying_it_both_ways_fires_nothing() -> None:
    """The branch is a repair. A Score that already says it once must not move."""
    _, report = _coerced([_circle(filled=True, surface={"texture": "solid"})])
    assert report.get(BRANCH, 0) == 0


# --- T-6: the drawing does not move -----------------------------------------


def test_the_two_ways_of_asking_for_a_fill_render_identical_bytes() -> None:
    """T-6. `filled=true` and `texture="solid"` are one performance.

    Coerce is the compatibility boundary that makes both request forms canonical
    before Engine 40 selects its solid material profile.
    """
    filled, _ = _coerced([_circle(filled=True)])
    solid, _ = _coerced([_circle(surface={"texture": "solid"})])
    assert render(filled, render_seed=1234) == render(solid, render_seed=1234)


def test_a_solid_surface_fills_the_interior() -> None:
    """T-6, the positive half. Byte-equality alone would hold if neither filled.

    Engine 40 gives solid its own stable base-fill class. It does not route the
    request through the older generic fill-v2 layer or a surface texture group.
    """
    solid = render(_score([_circle(surface={"texture": "solid"})]), render_seed=1234)
    outline = render(_score([_circle()]), render_seed=1234)
    assert "solid-fill-v1" in solid and "solid-base-fill-v1" in solid
    assert "fill-v2" not in solid
    assert "fill-v2" not in outline
    # It is a fill, so it is not reported as a texture the SVG shows.
    assert 'id="surface_' not in solid


# --- T-8 / T-9: what travels to the model -----------------------------------


def test_the_instruction_declaration_order_did_not_move() -> None:
    """T-8. Adding an enum value must not move a field.

    Declaration order reaches the model with the tool schema and decides how
    often an optional field is carried (I-038); `filled` is the thirteenth, and
    removing it would move twelve fields up. The Android contract file is the
    other side of the same claim, checked here where the tree has it.
    """
    # The schema's own order, which is what travels: it carries the aliases
    # (`from`, not `from_`), and it is the order the Android contract froze.
    order = list(
        composer._score_tool_schema()["properties"]["instructions"]["items"]["properties"]
    )
    assert order[12] == "filled"
    assert order[-2:] == ["thinness", "surface"]
    assert list(Instruction.model_fields)[-2:] == ["thinness", "surface"]
    if ANDROID_CONTRACT.is_file():
        contract = json.loads(ANDROID_CONTRACT.read_text(encoding="utf-8"))
        assert contract["instruction_property_order"] == order


def test_the_tool_schema_offers_solid() -> None:
    """T-9. A value the model is never shown is one it cannot choose.

    The whole finding is that the model writes what the destination field offers
    it, so this is the mechanism the contract turns on.
    """
    schema_json = composer._score_tool_schema()
    texture = schema_json["properties"]["instructions"]["items"]["properties"]["surface"]
    enum = texture["anyOf"][0]["properties"]["texture"]["enum"]
    assert "solid" in enum
    assert "solid" in json.dumps(composer._submit_tool(), ensure_ascii=False)


# --- T-10: the repairs leave a trace ----------------------------------------


def test_the_visible_particle_repair_leaves_a_note() -> None:
    """T-10. The repair fills a shape nobody asked to fill; it says so now.

    Its neighbour `_with_visible_color` has left a note since it was written. A
    repair whose only evidence is the drawing cannot be told apart from a Stage 2
    that asked for it.
    """
    particle = _circle(radius=0.002, arrangement={"count": 60, "layout": "scatter"})
    score, _ = _coerced([particle])
    note = score.instructions[0].note or ""
    assert "tiny particle made visible" in note
    assert score.instructions[0].filled is True


def test_the_branch_is_named_in_the_report() -> None:
    """T-10, the other half. A branch with no name cannot be counted."""
    _, report = _coerced([_circle()])
    assert BRANCH in report
    assert report[BRANCH] == 0


# --- T-11: the few-shot examples --------------------------------------------


def test_the_few_shot_examples_carry_the_surface_sentence() -> None:
    """T-11. Of 133 frozen input examples, 0 were in the `面: ...` form.

    Its sibling `地: ...` had six (three per language), and the ground route
    carries. [I-108] does not explain the whole gap -- the texture words arrive
    with zero examples too -- so this is one input to the reach measurement, not
    the cause.
    """
    assert "入力: 黒い円を中央に置く。面: 塗り。" in composer.SYSTEM_PROMPT
    assert "Input: Place a black circle at the center. Surface: flat." in composer.SYSTEM_PROMPT_EN
    for prompt in (composer.SYSTEM_PROMPT, composer.SYSTEM_PROMPT_EN):
        assert '"surface":{"texture":"solid"}' in prompt


def test_stage2_no_longer_sends_a_fill_to_the_boolean() -> None:
    """The four mapping lines the contract names, read as what they no longer say.

    Paired with T-11 because "the new example is present" would stay green beside
    a table that still tells the model to write `filled=true` for 塗り -- which is
    the internal contradiction that made the earlier prompt teach both.
    """
    assert "「面: 塗り」は texture=\"solid\"" in composer.SYSTEM_PROMPT
    assert '"Surface: flat" is texture="solid"' in composer.SYSTEM_PROMPT_EN
    assert "「面: 塗り」は質感ではなく filled=true" not in composer.SYSTEM_PROMPT
    assert '"Surface: flat" is not a texture; it is filled=true' not in composer.SYSTEM_PROMPT_EN


# --- T-12: the corpus is baked ----------------------------------------------


def test_ddl_engine_18_is_baked_and_matches_its_manifest() -> None:
    """T-12. Raising the version without baking freezes a record of nothing.

    Pinned to directory 18 rather than to whatever the current version is: this
    says engine 18 was baked, and that claim does not expire when engine 19
    arrives. Reading `DDL_ENGINE_VERSION` here would have moved the subject of
    the sentence every time the number rose.
    """
    directory = SERVER_ROOT / "reference" / "ddl-engine-18"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["engine_version"] == "18"

    for case_id, case in manifest["cases"].items():
        data = (directory / case["output_path"]).read_bytes()
        assert len(data) == case["bytes"], case_id
        assert hashlib.sha256(data).hexdigest()[:32] == case["digest"], case_id

    # The three whose Score actually moved: every closed-shape instruction in
    # them carried `filled=true` with no surface of its own. The other coerce
    # cases are listed only because the branch report gained a key.
    changed = set(manifest["changed_from_previous"])
    assert {
        "B-production-fill-clause",
        "B-production-no-fill-clause",
        "B-white-filled-circle",
    } <= changed
