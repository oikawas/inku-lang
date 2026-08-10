"""A number the description states in plain words is the number that gets drawn.

Until `with_stated_count_fidelity` there was one branch that made a stated count
true, and it answered only to "だけ / のみ / only / just". A plain 「三つ」 was
protected from thinning and nothing else: a count Stage 2 had already missed
stayed missed. Production bore this out -- of the counts stated in the band a
reader can count by eye, one in five never reached the Score, and in 88.8% of
those the group was there with the wrong number on it.

Every case here is synthetic. The production works this repair was measured
against stay in the private overlay (2026-08-10 ruling), so nothing in this file
is copied from one.
"""

from __future__ import annotations

import pytest

from inku_server.coerce import coerce_score
from inku_server.coerce.compose import (
    EXPLICIT_COUNT_NOTE,
    MAX_STATED_COUNT_FIDELITY,
    STATED_COUNT_FIDELITY_NOTE,
    _primitive_from_clause,
    _fallback_instruction_from_clause,
)
from inku_server.schema import Score

BRANCH = "with_stated_count_fidelity"


def _group(primitive: str = "circle", *, count: int, color: str = "black", weight: str = "pen", x: float = 0.5) -> dict:
    group: dict = {
        "primitive": primitive,
        "color": color,
        "weight": weight,
        "arrangement": {"count": count, "layout": "scatter"},
    }
    if primitive in {"circle", "arc", "polygon"}:
        group.update({"center": [x, 0.5], "radius": 0.08})
    elif primitive in {"ellipse", "cloudform"}:
        group.update({"center": [x, 0.5], "size": [0.16, 0.09]})
    elif primitive == "line":
        group.update({"from": [0.18, 0.5], "to": [0.82, 0.5]})
    else:
        group.update({"position": [x, 0.5], "size": [0.14, 0.10]})
    return group


def _score(*groups: dict, background: str = "white") -> Score:
    return Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": {"aspect": "square"},
            "background": background,
            "instructions": list(groups),
        }
    )


def _replay(score: Score, ddl: str) -> tuple[list[int], list[str], dict[str, int]]:
    report: dict[str, int] = {}
    out = coerce_score(score, ddl=ddl, branch_report=report)
    counts = [(ins.arrangement.count if ins.arrangement else 1) for ins in out.instructions]
    notes = [ins.note or "" for ins in out.instructions]
    return counts, notes, report


# T-1 -- the plain number is the one that gets drawn, in both languages and from
# either side. Six circles is as wrong as two when the description says three.
@pytest.mark.parametrize(
    ("ddl", "primitive"),
    [
        ("黒いペンの円を三つ並べる。", "circle"),
        ("Line up three black pen circles.", "circle"),
    ],
)
@pytest.mark.parametrize("stage_two_said", [2, 6])
def test_a_count_stated_in_plain_words_reaches_the_score(ddl: str, primitive: str, stage_two_said: int) -> None:
    counts, _, report = _replay(_score(_group(primitive, count=stage_two_said)), ddl)
    assert counts == [3], f"{ddl!r} with {stage_two_said} drawn returned {counts}"
    assert report[BRANCH] > 0


def test_the_repair_says_which_branch_made_the_count_true() -> None:
    """Attribution: two branches now honour a count, and a Score must name which one.

    A shared note would make the question "did 'だけ' do this, or did the plain
    number" unanswerable from a stored Score, and that question is the whole
    reason this branch was not folded into the other one.
    """
    _, notes, _ = _replay(_score(_group(count=2)), "黒いペンの円を三つ並べる。")
    assert any(STATED_COUNT_FIDELITY_NOTE in note for note in notes)
    assert not any(EXPLICIT_COUNT_NOTE in note for note in notes)
    assert STATED_COUNT_FIDELITY_NOTE != EXPLICIT_COUNT_NOTE


# T-2 -- the road that already worked still works, and still signs its own name.
@pytest.mark.parametrize("ddl", ["黒いペンの円を三つだけ並べる。", "Line up only three black pen circles."])
@pytest.mark.parametrize("stage_two_said", [2, 6])
def test_the_strict_road_is_unchanged(ddl: str, stage_two_said: int) -> None:
    counts, notes, report = _replay(_score(_group(count=stage_two_said)), ddl)
    assert counts == [3]
    assert any(EXPLICIT_COUNT_NOTE in note for note in notes)
    assert report[BRANCH] == 0, "the strict road decided this one; the plain-word branch must stay out"


# T-3 -- above the band a number is density, not a promise, and which of density
# and the total budget wins up there has not been ruled on.
@pytest.mark.parametrize(
    ("ddl", "primitive", "stage_two_said"),
    [
        ("黒いペンの線を十二本並べる。", "line", 2),
        ("黒いペンの線を十二本並べる。", "line", 40),
        ("Line up one hundred thirty black pen lines.", "line", 2),
        ("Line up one hundred thirty black pen lines.", "line", 40),
    ],
)
def test_a_count_above_the_band_is_left_where_it_is(ddl: str, primitive: str, stage_two_said: int) -> None:
    counts, _, report = _replay(_score(_group(primitive, count=stage_two_said)), ddl)
    assert counts == [stage_two_said], f"{ddl!r} moved the count to {counts}"
    assert report[BRANCH] == 0


def test_the_band_stops_at_eleven() -> None:
    assert MAX_STATED_COUNT_FIDELITY == 11
    counts, _, _ = _replay(_score(_group(count=2)), "黒いペンの円を十一個並べる。")
    assert counts == [11]
    counts, _, _ = _replay(_score(_group(count=2)), "黒いペンの円を十二個並べる。")
    assert counts == [2]


# T-4 -- a number pushed onto a guess changes the count of a group the clause
# never named, which is worse than the miss being repaired.
def test_two_groups_answering_the_clause_leave_both_alone() -> None:
    score = _score(
        _group(count=2, x=0.3),
        _group(count=5, x=0.7),
    )
    counts, _, report = _replay(score, "黒いペンの円を三つ並べる。")
    assert counts == [2, 5], f"an ambiguous pairing moved a count: {counts}"
    assert report[BRANCH] == 0


def test_no_group_of_that_figure_leaves_the_score_alone() -> None:
    counts, _, report = _replay(_score(_group("square", count=2)), "黒いペンの円を三つ並べる。")
    assert counts == [2]
    assert report[BRANCH] == 0


# T-5 -- 雲形 is the one shape word no other branch of `_primitive_from_clause`
# catches, so before this it fell through to the `line` default and a repair
# pairing clauses with groups would push its count onto a line.
@pytest.mark.parametrize(
    "clause",
    ["白いチョークの雲形を三つ散らす", "Scatter three white chalk cloudforms", "雲形をひとつ置く"],
)
def test_a_cloudform_clause_reads_as_a_cloudform(clause: str) -> None:
    assert _primitive_from_clause(clause) == "cloudform"


def test_a_cloudform_clause_becomes_a_drawable_cloudform() -> None:
    """The renderer draws a cloudform only when it has both `center` and `size`.

    The fallback's last branch writes `position` + `size`, which is right for a
    square and invisible for a cloudform, so reading 雲形 correctly and then
    laying it out like a square would trade a wrong shape for no shape at all.
    """
    fallback = _fallback_instruction_from_clause(
        "白いチョークの雲形を散らす", index=0, background="white"
    )
    assert fallback.primitive == "cloudform"
    assert fallback.center is not None
    assert fallback.size is not None


# The guard that keeps this branch from paying for one promise with another.
def test_a_group_that_is_the_only_answer_to_another_stated_count_is_not_renumbered() -> None:
    """`_primitive_from_clause` reads a shape word anywhere in the clause, and
    「焦点」 carries 点, so a clause about lines reads as a clause about circles.
    The circles standing next to it are the only group answering the count the
    description states for them, and taking three of them would break that.
    """
    ddl = "白いペンの小さな円を百五十五個散らす。白いペンの短い線を右下の焦点から外へ三本散らす。"
    counts, _, report = _replay(_score(_group(count=155, color="white")), ddl)
    assert counts == [155], f"the only group answering 155 was renumbered: {counts}"
    assert report[BRANCH] == 0


def test_one_group_answers_one_clause() -> None:
    """Two clauses can name the same single group. Neither number is more right
    than the other, so the group keeps the answer it gave first -- otherwise
    which number survives is decided by the order the clauses were written in.
    """
    ddl = "黒いペンの円を三つ並べる。黒いペンの円を五つ並べる。"
    counts, _, _ = _replay(_score(_group(count=2)), ddl)
    assert counts == [3], f"the later clause overwrote the earlier one: {counts}"


# T-10 -- INKU_COERCE_DISABLE switches off the style layer. This branch is part
# of it: it is a reading of the description, not a guard on drawing cost.
def test_the_disabled_exit_does_not_run_this_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    counts, notes, report = _replay(_score(_group(count=2)), "黒いペンの円を三つ並べる。")
    assert counts == [2]
    assert BRANCH not in report
    assert not any(STATED_COUNT_FIDELITY_NOTE in note for note in notes)
