"""A mark the description called small is small whoever wrote it (契約 I-234, T-1..T-11).

Stage 2 writes a circle and leaves the radius empty often enough to matter: 115 of the
2,972 production works carry a mark at coerce's default size. That default -- 0.15 in
`normalize.PRIMITIVE_SPECS` -- does not read a character of the description, so 「小さな円を三つ」
and 「円を三つ」 were drawn at exactly the same size.

When coerce writes the mark itself it does read the clause, and answers 0.038
(`compose._fallback_instruction_from_clause`). The same description therefore produced marks
four times apart depending on who wrote them. `_with_stated_size` closes that: it runs on the
instruction the model handed over, before `_coerce_instruction`'s defaults erase the
difference between "the model said nothing" and "the model said 0.15", and fills the empty
size from the same clause with the same two readers.

What it does not do: invent a size where the description names none (T-3), overrule a size the
model did state (T-4), read the description whole instead of clause by clause (T-5), or guess
which clause a mark answers when two of them fit (T-6).
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from inku_server.coerce import coerce_score
from inku_server.coerce.compose import _fallback_instruction_from_clause
from inku_server.coerce.normalize import PRIMITIVE_SPECS
from inku_server.layer_versions import DDL_ENGINE_VERSION
from inku_server.schema import Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_ROOT = SERVER_ROOT / "reference"
# The version this file is about. Attribution belongs to the version that made
# the change, so it is named here rather than derived from the current one.
ENGINE_16_DIR = REFERENCE_ROOT / "ddl-engine-16"

CIRCLE = {"primitive": "circle", "center": [0.5, 0.5]}
ELLIPSE = {"primitive": "ellipse", "center": [0.5, 0.5]}
SQUARE = {"primitive": "square", "position": [0.3, 0.3]}
LINE = {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5]}


def _default(primitive: str, field: str):
    """The size `_coerce_instruction` fills when nothing else speaks for the field."""
    for spec in PRIMITIVE_SPECS[primitive]:
        if spec.name == field:
            return spec.default
    raise AssertionError(f"{primitive} has no {field} spec")


def _coerced(ddl: str | None, instructions: list[dict]) -> list:
    score = Score.model_validate({"instructions": instructions})
    return list(coerce_score(score, ddl=ddl, lang="ja").instructions)


def test_a_small_circle_with_no_radius_takes_the_size_the_clause_states() -> None:
    """T-1."""
    marks = _coerced("小さな円を三つ並べる。", [CIRCLE])
    assert [ins.primitive for ins in marks] == ["circle"]
    assert marks[0].radius == 0.038
    # Say what the default was, so the assertion above cannot be satisfied by the
    # default quietly becoming 0.038 in `normalize.py`.
    assert _default("circle", "radius") == 0.15


def test_a_small_ellipse_with_no_size_takes_the_size_the_clause_states() -> None:
    """T-2."""
    marks = _coerced("ごく小さな楕円を五つ散らす。", [ELLIPSE])
    assert [ins.primitive for ins in marks] == ["ellipse"]
    assert marks[0].size == (0.06, 0.032)
    assert _default("ellipse", "size") == [0.3, 0.3]


def test_a_description_with_no_size_word_keeps_the_default() -> None:
    """T-3, the control. The rule fills nothing where the description says nothing."""
    marks = _coerced("円を三つ並べる。", [CIRCLE])
    assert marks[0].radius == _default("circle", "radius") == 0.15


def test_a_size_the_model_stated_is_not_overruled_by_the_description() -> None:
    """T-4. The rule fills an empty field; it never argues with a written one."""
    marks = _coerced("小さな円を三つ並べる。", [{**CIRCLE, "radius": 0.3}])
    assert marks[0].radius == 0.3


def test_the_size_word_reaches_only_the_mark_its_own_clause_names() -> None:
    """T-5. Read clause by clause, not description-wide.

    The square is here because it is what the contract names, and the ellipse is here
    because it is what a description-wide reading would actually get wrong: this rule
    does not touch squares at all, so a whole-DDL predicate would leave the square
    alone and shrink the ellipse instead.
    """
    marks = _coerced(
        "小さな円を三つ並べる。四角を一つ置く。楕円を一つ描く。", [CIRCLE, SQUARE, ELLIPSE]
    )
    by_primitive = {ins.primitive: ins for ins in marks}
    assert by_primitive["circle"].radius == 0.038
    assert by_primitive["square"].size == tuple(_default("square", "size"))
    assert by_primitive["ellipse"].size == tuple(_default("ellipse", "size"))


def test_two_clauses_that_both_fit_leave_the_mark_alone() -> None:
    """T-6. With two the description does not say which one this mark answers."""
    marks = _coerced("小さな円を三つ並べる。小さな円を五つ散らす。", [CIRCLE])
    assert marks[0].radius == _default("circle", "radius") == 0.15


def test_a_radius_the_clause_states_outranks_the_small_default() -> None:
    """T-7. 0.02 is what the description asked for; 0.038 is only the fallback."""
    marks = _coerced("半径0.02の小さな円を置く。", [CIRCLE])
    assert marks[0].radius == 0.02


def test_the_mark_is_the_same_size_whichever_layer_wrote_it() -> None:
    """T-8 -- the claim of the whole contract, and the only test that measures both paths.

    `_with_ddl_coverage` writes a mark of coerce's own when the Score holds a single
    instruction and the description names more clauses than that, which is why the two
    Scores differ by the circle alone. The assertion is a relation, not a constant: a
    change that moved both paths to the same wrong number would still have to move them
    together, and one that moved neither is caught by the comparison with the default.
    """
    ddl = "小さな円を三つ並べる。横線を一本引く。"

    written_by_coerce = _coerced(ddl, [LINE])
    written_by_stage_two = _coerced(ddl, [LINE, CIRCLE])

    own = next(ins for ins in written_by_coerce if ins.primitive == "circle")
    theirs = next(ins for ins in written_by_stage_two if ins.primitive == "circle")

    assert theirs.radius == own.radius
    assert theirs.radius != _default("circle", "radius")
    # The value is borrowed, not written twice: the clause reader coerce uses for its
    # own marks answers the same number.
    assert own.radius == _fallback_instruction_from_clause(
        "小さな円を三つ並べる。", index=0, background="white", lang="ja"
    ).radius


def test_switching_the_style_coercion_off_does_not_switch_the_size_off(monkeypatch) -> None:
    """T-9. Being faithful to a stated size is not a matter of style."""
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    marks = _coerced("小さな円を三つ並べる。", [CIRCLE])
    assert marks[0].radius == 0.038
    # The exit really was the disabled one: the production exit runs the DDL hints,
    # and this one does not, so a monkeypatch that failed to take would show up as
    # the governors below having run.
    assert marks[0].note is None


# The four cases ddl-engine 16 adds, and what each is for. Read from here rather
# than from the manifest so a case deleted from the generator is a failure and not
# a silently smaller corpus.
NEW_COERCE_CASES = {
    "B-small-circle-with-no-radius": ("circle", "radius", 0.038),
    "B-small-ellipse-with-no-size": ("ellipse", "size", [0.06, 0.032]),
    "B-no-size-word-keeps-the-default": ("circle", "radius", 0.15),
    "B-stated-size-outranks-the-word": ("circle", "radius", 0.3),
}
MOVED_BY_THE_RULE = {"B-small-circle-with-no-radius", "B-small-ellipse-with-no-size"}


def _generator():
    import importlib.util

    path = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"
    spec = importlib.util.spec_from_file_location("gen_ddl_reference", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_corpus_holds_the_two_marks_that_move_and_the_two_controls() -> None:
    """T-10.

    Three claims, and the middle one is why this is a gate rather than a record: the
    frozen bytes are reproduced by running today's `coerce_score` over the same input,
    so taking the repair out turns this red even though not a byte on disk moved.
    """
    generator = _generator()
    inputs = generator.build_coerce_inputs()
    # Pinned to 16, not to whatever the current version is. The claim is about
    # what engine 16 moved, and a directory holds only the cases that moved in
    # it -- reading a later manifest swaps the subject of the claim in silence
    # and takes the four cases' frozen bytes out of reach with it.
    manifest = json.loads(
        (ENGINE_16_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    for case_id, (primitive, field, expected) in NEW_COERCE_CASES.items():
        assert case_id in inputs, case_id
        case = inputs[case_id]

        score = coerce_score(
            Score.model_validate(case["score"]), ddl=case["ddl"], lang=case["lang"]
        )
        mark = next(ins for ins in score.instructions if ins.primitive == primitive)
        written = getattr(mark, field)
        assert written == (tuple(expected) if isinstance(expected, list) else expected), case_id

        # The same run reproduces the frozen file, byte for byte.
        frozen = (ENGINE_16_DIR / manifest["cases"][case_id]["output_path"]).read_bytes()
        assert hashlib.sha256(frozen).hexdigest()[:32] == manifest["cases"][case_id]["digest"]
        assert json.loads(frozen)["score"]["instructions"] == json.loads(
            score.model_dump_json(by_alias=True)
        )["instructions"]

    # Nothing that existed before moved: the four new names are the whole of the list.
    assert manifest["changed_from_previous"] == sorted(NEW_COERCE_CASES)
    assert MOVED_BY_THE_RULE <= set(manifest["changed_from_previous"])


def test_no_frozen_engine_below_this_one_was_rewritten() -> None:
    """T-11. The version rose, so every older directory must still match its own manifest.

    `test_ddl_reference_output_files_match_manifest` checks the current version only.
    Baking engine 17 is exactly the moment an older directory gets rewritten by
    accident, which is what this reads for.
    """
    assert DDL_ENGINE_VERSION == "18"

    checked = 0
    for version in range(1, int(DDL_ENGINE_VERSION)):
        directory = REFERENCE_ROOT / f"ddl-engine-{version}"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["engine_version"] == str(version)
        for case_id, case in manifest["cases"].items():
            data = (directory / case["output_path"]).read_bytes()
            assert len(data) == case["bytes"], f"{version}/{case_id}"
            assert hashlib.sha256(data).hexdigest()[:32] == case["digest"], f"{version}/{case_id}"
            checked += 1
    # A gate that silently read nothing reads exactly like a gate that passed.
    # 522 while engine 16 was the current one; engine 17 moves 16's own 49 cases
    # into the set this reads, and engine 18 moves 17's, which is what the number
    # rising says. This is also T-7 of the ddl-engine 18 contract -- the check
    # that the version that was baked is the only directory that moved.
    assert checked == 620
