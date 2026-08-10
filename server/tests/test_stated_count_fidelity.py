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
    STATED_COUNT_FIDELITY_NOTE,
    _primitive_from_clause,
    _fallback_instruction_from_clause,
    _stated_count_fidelity_band,
)
from inku_server.limits import DEFAULT_LIMITS, Limits
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


def _replay(
    score: Score, ddl: str, limits: Limits = DEFAULT_LIMITS
) -> tuple[list[int], list[str], dict[str, int]]:
    report: dict[str, int] = {}
    out = coerce_score(score, ddl=ddl, branch_report=report, limits=limits)
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


# T-1 (the widened band) -- a number a reader cannot count on one hand is still a
# number the description states. Thirty circles drawn as two is not a matter of
# density; it is the description not being read.
@pytest.mark.parametrize(
    ("stated", "ja", "en"),
    [
        (12, "十二個", "twelve"),
        (30, "三十個", "thirty"),
        (120, "百二十個", "one hundred twenty"),
        (233, "二百三十三個", "two hundred thirty-three"),
    ],
)
@pytest.mark.parametrize("lang", ["ja", "en"])
@pytest.mark.parametrize("stage_two_said", [2, 40])
def test_a_stated_count_in_the_literal_band_reaches_the_score(
    stated: int, ja: str, en: str, lang: str, stage_two_said: int
) -> None:
    ddl = f"黒いペンの円を{ja}散らす。" if lang == "ja" else f"Scatter {en} black pen circles."
    counts, _, report = _replay(_score(_group(count=stage_two_said)), ddl)
    assert counts == [stated], f"{ddl!r} with {stage_two_said} drawn returned {counts}"
    assert report[BRANCH] > 0


# T-2 -- at `literal_count_threshold` and above, SPEC asks for the group to be
# shown rather than counted, and this branch has no business overruling that.
# Which of density and the total budget wins up there has not been ruled on.
@pytest.mark.parametrize(
    ("ddl", "primitive", "stage_two_said"),
    [
        ("黒いペンの円を三百個散らす。", "circle", 2),
        ("黒いペンの円を三百個散らす。", "circle", 40),
        ("黒いペンの線を五百本引く。", "line", 2),
        ("Scatter three hundred black pen circles.", "circle", 40),
    ],
)
def test_a_count_above_the_literal_band_is_left_where_it_is(
    ddl: str, primitive: str, stage_two_said: int
) -> None:
    counts, _, report = _replay(_score(_group(primitive, count=stage_two_said)), ddl)
    assert counts == [stage_two_said], f"{ddl!r} moved the count to {counts}"
    assert report[BRANCH] == 0


# T-3 -- the top of the band is not a number of its own. It is the literal side
# of the line `literal_count_threshold` already draws, so moving that line moves
# the band with it -- in both directions, because a hard-coded 239 would still
# honour 99 when the threshold is lowered and would still refuse 240 when it is
# raised.
def test_the_band_is_the_literal_side_of_the_threshold() -> None:
    lowered = Limits(literal_count_threshold=100)
    assert _stated_count_fidelity_band(lowered) == 99
    counts, _, _ = _replay(_score(_group(count=2)), "黒いペンの円を九十九個散らす。", lowered)
    assert counts == [99], "the band did not follow the threshold down"
    counts, _, _ = _replay(_score(_group(count=2)), "黒いペンの円を百個散らす。", lowered)
    assert counts == [2], "a count the lowered threshold represents was drawn literally"

    raised = Limits(literal_count_threshold=480)
    assert _stated_count_fidelity_band(raised) == 479
    counts, _, _ = _replay(_score(_group(count=2)), "黒いペンの円を二百四十個散らす。", raised)
    assert counts == [240], "the band did not follow the threshold up"


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


def test_the_clause_is_read_through_the_same_hints_the_instructions_went_through() -> None:
    """A material word in a neighbouring clause must not hide the matching group.

    Every instruction passes through `_with_ddl_instruction_hints` on the way in,
    which reads the whole description: a group whose own clause names no material
    still leaves that step as `pencil` when 鉛筆 appears anywhere. The clause read
    on its own says `pen`, so comparing the two unhinted finds no match on the
    triple at all and falls through to the figure, where two circles are
    ambiguous and nothing is repaired. Measured on the 214 frozen cases, reading
    the clause through the same hints is worth 8 of them.
    """
    ddl = "黒い円を三つ並べる。赤い円を置く。やわらかい鉛筆で描く。"
    score = _score(
        _group(count=6, color="black", x=0.3),
        _group(count=4, color="red", x=0.7),
    )
    counts, notes, report = _replay(score, ddl)
    assert counts == [3, 4], f"the black group was not found through the material hint: {counts}"
    assert report[BRANCH] > 0
    assert STATED_COUNT_FIDELITY_NOTE in notes[0]


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


def test_a_count_the_score_already_carries_is_not_answered_a_second_time() -> None:
    """The request is answered work-wide, not group by group, and that is a choice.

    Here the three the description asks for is already on the squares, and the
    circles the clause names are five. The branch declines: a work that carries
    the number somewhere is not one it has anything to add to, and renumbering a
    second group takes a count nobody asked to change.

    Measured on the 214 frozen production cases, this reading is worth 12 of
    them -- 144 against 132 with no such check, and 140 with the narrower reading
    that excludes only the group already holding the number. The reason removing
    it costs cases is not this shape but the neighbouring clauses: without it the
    branch renumbers groups that were already answering, and consumes the group
    a later clause needed.
    """
    score = _score(
        _group("square", count=3, x=0.15),
        _group("circle", count=5, x=0.7),
    )
    counts, _, report = _replay(score, "黒いペンの円を三つ並べる。")
    assert counts == [3, 5], f"a second group was made to answer the same request: {counts}"
    assert report[BRANCH] == 0


def test_one_group_answers_one_clause() -> None:
    """Two clauses can name the same single group, and the later one must not win.

    Otherwise which number survives is decided by the order the clauses happen to
    be written in. Nothing here enforces this directly: an explicit "already
    answered by an earlier clause" guard was written, measured, and removed as
    unreachable. Once the first clause sets the group to three, that group is the
    only thing in the Score answering the three the description also states, and
    `_is_the_only_answer_to_another_count` refuses it to the second clause. The
    property is real and is what this asserts; the guard was a second lock on a
    door already shut.
    """
    ddl = "黒いペンの円を三つ並べる。黒いペンの円を五つ並べる。"
    counts, _, _ = _replay(_score(_group(count=2)), ddl)
    assert counts == [3], f"the later clause overwrote the earlier one: {counts}"


# T-5 -- a number this branch cannot deliver whole is one it declines to write.
#
# Both cases are about the same thing seen from two budgets. The branch runs
# after both density governors, so nothing above it will make room; what runs
# after it is the hard ceiling at the exit of coerce, and that ceiling TRIMS.
# Without these guards the 233 below leaves as 200 -- neither the number the
# description stated, nor the number Stage 2 chose, nor a representative count,
# but whatever the ceiling's division returned. The assertions therefore check
# that Stage 2's own count survives untouched, which is what separates declining
# from trimming; asserting only "not 233" would pass for both.
def test_a_count_that_would_break_the_work_budget_is_not_written() -> None:
    over = _score(
        _group("square", count=200, x=0.15),
        _group("circle", count=5, x=0.7),
    )
    counts, notes, report = _replay(over, "黒いペンの円を二百三十三個散らす。")
    assert counts == [200, 5], f"the branch wrote a count the work cannot carry: {counts}"
    assert report[BRANCH] == 0
    assert not any(STATED_COUNT_FIDELITY_NOTE in note for note in notes)
    assert not any("hard ceiling" in note for note in notes), "declined, so the ceiling has nothing to trim"


def test_the_same_count_is_written_when_the_work_has_room_for_it() -> None:
    """The other half of the guard: it must decline for want of room, not always.

    Same clause, same target group, same stated number -- only the neighbouring
    group is smaller. Without this, a guard that simply never fires would pass
    the test above.
    """
    within = _score(
        _group("square", count=100, x=0.15),
        _group("circle", count=5, x=0.7),
    )
    counts, _, report = _replay(within, "黒いペンの円を二百三十三個散らす。")
    assert counts == [100, 233], f"the branch declined a count that fits: {counts}"
    assert report[BRANCH] > 0


def test_a_count_no_single_group_may_hold_is_not_written() -> None:
    """The per-instruction budget, which the shipping limits cannot reach.

    The band tops out one below `literal_count_threshold`, and that equals
    `max_expanded_per_instruction` at the defaults, so 239 can never exceed 240.
    The two are separate settings with no rounding between them, so an install
    that lowers the per-instruction budget -- or raises the threshold -- reaches
    this. Measured at the defaults it would be a test of nothing.
    """
    narrow = Limits(max_expanded_per_instruction=20)
    counts, notes, report = _replay(_score(_group(count=5)), "黒いペンの円を三十個散らす。", narrow)
    assert counts == [5], f"a count above the per-instruction budget was written: {counts}"
    assert report[BRANCH] == 0
    assert not any(STATED_COUNT_FIDELITY_NOTE in note for note in notes)

    # And the same limits honour a number that fits, so the guard is bounded by
    # the budget rather than by the presence of a non-default setting.
    counts, _, report = _replay(_score(_group(count=5)), "黒いペンの円を八個散らす。", narrow)
    assert counts == [8]
    assert report[BRANCH] > 0


# T-10 -- INKU_COERCE_DISABLE switches off the style layer. This branch is part
# of it: it is a reading of the description, not a guard on drawing cost.
def test_the_disabled_exit_does_not_run_this_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    counts, notes, report = _replay(_score(_group(count=2)), "黒いペンの円を三つ並べる。")
    assert counts == [2]
    assert BRANCH not in report
    assert not any(STATED_COUNT_FIDELITY_NOTE in note for note in notes)
