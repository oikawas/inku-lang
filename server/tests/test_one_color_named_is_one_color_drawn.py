"""ddl-engine 10: a description that names one color is drawn in one color.

`arrangement.color_cycle` hands one color to each member of a group in turn --
`cycle[i % len(cycle)]` in `renderer.py`. A pure cycle has no head and no
ranking, so n colors take 1/n of the members each. When the description named
one color and the cycle carried two, that color reached half the members and a
color nobody asked for took the other half.

That is not a distribution the description chose. No description states one, so
this is not about honouring a stated share ([I-173] stage B, out of scope here)
-- it is about removing a share nobody stated. coerce's own docstring already
says the rule: every branch repairs an instruction or delivers something the
description asked for, and nothing invents.

The pairs matter. T-1 alone would pass an implementation that always folds, so
T-2, T-3 and T-4 hold the three ways a description can ask for more than one
color: it names two, it says "colorful", or it names none and the colors came
from somewhere this layer cannot see. T-5 alone would pass an implementation
that empties the cycle and leaves `color` behind, which would draw the group in
whatever color the instruction happened to carry. T-6 separates "not a mark
color" from "not the background field": a white mark on a black background is
one named color, and an implementation that subtracts `score.background` reads
it as none.

T-9 is a control on the function this change deliberately leaves alone, and
T-10 holds the second exit: `INKU_COERCE_DISABLE` turns off style repair, not
the ban on inventing, for the same reason the hard ceiling holds there too.
"""

from __future__ import annotations

import pytest

from inku_server.coerce import coerce_score
from inku_server.coerce.compose import _marks_only_ddl, _requested_colors_from_ddl
from inku_server.render_engines.default.planning import _apply_color_cycle
from inku_server.schema import Instruction, Score


def _grouped(color: str, cycle: list[str] | None, *, count: int = 12) -> Instruction:
    arrangement: dict = {"count": count, "layout": "scatter"}
    if cycle is not None:
        arrangement["color_cycle"] = list(cycle)
    return Instruction.model_validate(
        {
            "primitive": "ellipse",
            "center": [0.5, 0.5],
            "size": [0.18, 0.08],
            "color": color,
            "arrangement": arrangement,
        }
    )


def _score(instruction: Instruction, *, background: str = "white") -> Score:
    return Score.model_validate(
        {"background": background, "instructions": [instruction.model_dump(by_alias=True)]}
    )


def _cycles(score: Score) -> list[list[str]]:
    return [
        list(ins.arrangement.color_cycle)
        for ins in score.instructions
        if ins.arrangement is not None
    ]


# T-1: the description names one color, so the cycle goes away and that color stays.


def test_t1_one_named_color_empties_the_cycle_and_keeps_the_color() -> None:
    fixed = coerce_score(
        _score(_grouped("green", ["green", "gray"])),
        ddl="緑の小さな楕円を十二散らす。",
    )

    assert _cycles(fixed) == [["green"]]
    assert [ins.color for ins in fixed.instructions] == ["green"]


def test_t1_holds_when_a_background_clause_precedes_the_one_color() -> None:
    # The named color is one only after the background clause is dropped.
    fixed = coerce_score(
        _score(_grouped("white", ["white", "gray"]), background="black"),
        ddl="背景を黒で塗りつぶす。白い細い線を十二本引く。",
        )

    assert _cycles(fixed) == [["white"]]
    assert [ins.color for ins in fixed.instructions] == ["white"]


# T-2: two named mark colors are two, and the cycle is left alone.


def test_t2_two_named_colors_leave_every_cycle_member_in_place() -> None:
    before = ["red", "blue"]
    fixed = coerce_score(
        _score(_grouped("red", list(before))),
        ddl="赤と青の小さな楕円を十二散らす。",
    )

    for cycle in _cycles(fixed):
        assert set(before) <= set(cycle), cycle
        assert len(cycle) >= 2


# T-3: a description that asks for many colors keeps its cycle.


@pytest.mark.parametrize(
    "ddl",
    ["色とりどりの緑の楕円を十二散らす。", "a colorful scatter of twelve green ellipses"],
)
def test_t3_a_polychrome_phrase_leaves_the_cycle_in_place(ddl: str) -> None:
    # The sample names exactly one color on purpose. `色とりどりの楕円を…` names
    # none, so condition 1 stops the fold before the polychrome check is ever
    # consulted -- removing the check outright left this test green. Naming one
    # color makes condition 2 the only thing standing between this cycle and the
    # fold, which is what the test is for.
    assert len(_requested_colors_from_ddl(_marks_only_ddl(ddl))) == 1

    fixed = coerce_score(_score(_grouped("green", ["green", "gray"])), ddl=ddl)

    for cycle in _cycles(fixed):
        assert len(cycle) >= 2, cycle


# T-4: no named mark color at all is out of scope, and stays out of scope.
#
# "no color word" means `_requested_colors_from_ddl` returns nothing. The
# function reads subjects as well as color words -- 落ち葉 gives green and
# 水面 gives blue -- so a sample has to be checked, not assumed.


@pytest.mark.parametrize("ddl", ["線が一本。", "円だけを三つ描く。", "細かい線が散る。"])
def test_t4_a_ddl_with_no_named_color_leaves_the_cycle_unchanged(ddl: str) -> None:
    assert _requested_colors_from_ddl(_marks_only_ddl(ddl)) == set()

    before = ["green", "gray"]
    fixed = coerce_score(_score(_grouped("green", list(before))), ddl=ddl)

    assert _cycles(fixed) == [before]


# T-5: folding never loses the color that was named.


@pytest.mark.parametrize(
    ("ddl", "named", "carried", "background"),
    [
        ("紫の小さな楕円を十二散らす。", "purple", "black", "white"),
        ("橙の小さな楕円を十二散らす。", "orange", "gray", "white"),
        ("黄色い小さな楕円を十二散らす。", "yellow", "blue", "white"),
        # White is the case that makes this test discriminating.
        # `_with_primary_color_delivery` runs before the fold and skips white and
        # the background color, so for every row above it has already moved the
        # named color onto the primary stroke and the fold's own `color` write
        # agrees with what is there. Only here is the fold the sole writer, and
        # only here does dropping that write change the drawing.
        ("背景を黒で塗りつぶす。白い小さな楕円を十二散らす。", "white", "gray", "black"),
    ],
)
def test_t5_the_folded_instruction_carries_the_named_color(
    ddl: str, named: str, carried: str, background: str
) -> None:
    # The instruction arrives carrying a color the description did not name, so
    # emptying the cycle without setting `color` would draw the whole group in
    # `carried` and take the named color out of the picture entirely.
    fixed = coerce_score(
        _score(_grouped(carried, [carried, named]), background=background), ddl=ddl
    )

    assert _cycles(fixed) == [[named]]
    assert [ins.color for ins in fixed.instructions] == [named]


# T-6: the background is not a mark color, and not a field to subtract either.


def test_t6_a_white_mark_on_black_is_one_named_color() -> None:
    ddl = "背景を黒で塗りつぶす。白い細い線を十二本引く。"

    # The distinction the pair holds: dropping the background *clause* leaves
    # white alone; subtracting `score.background` from the whole text would
    # leave white alone too, but only by accident -- it reads the black of the
    # background as a mark color first.
    assert _requested_colors_from_ddl(_marks_only_ddl(ddl)) == {"white"}
    assert _requested_colors_from_ddl(ddl) == {"black", "white"}


def test_t6_a_white_mark_on_a_white_background_is_still_one_named_color() -> None:
    # The case that separates the two implementations. Dropping the background
    # clause leaves white named once. Subtracting `score.background` instead
    # takes white away entirely, so a description that named one color reads as
    # naming none and the cycle survives -- the mark colour is the background
    # colour here, and only the clause structure says which mention was which.
    ddl = "背景を白で塗りつぶす。白い細い線を十二本引く。"
    assert _requested_colors_from_ddl(_marks_only_ddl(ddl)) == {"white"}

    fixed = coerce_score(
        _score(_grouped("gray", ["gray", "white"]), background="white"), ddl=ddl
    )

    assert _cycles(fixed) == [["white"]]
    assert [ins.color for ins in fixed.instructions] == ["white"]


def test_t6_a_black_mark_on_a_black_background_clause_is_still_one_color() -> None:
    ddl = "背景を白で塗りつぶす。黒い細い線を十二本引く。"

    assert _requested_colors_from_ddl(_marks_only_ddl(ddl)) == {"black"}

    fixed = coerce_score(
        _score(_grouped("black", ["black", "gray"]), background="white"), ddl=ddl
    )

    assert _cycles(fixed) == [["black"]]
    assert [ins.color for ins in fixed.instructions] == ["black"]


# T-9: control. The cycle itself is not touched by this change.


def test_t9_apply_color_cycle_still_hands_each_member_the_next_color() -> None:
    members = [_grouped("black", None) for _ in range(6)]
    cycle = ["red", "blue", "green"]

    applied = _apply_color_cycle(members, cycle)

    assert [ins.color for ins in applied] == [cycle[i % len(cycle)] for i in range(6)]
    assert len({ins.color for ins in applied}) == 3


# T-10: the rule holds on the INKU_COERCE_DISABLE exit too.


def test_t10_the_rule_holds_when_style_coercion_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")

    fixed = coerce_score(
        _score(_grouped("green", ["green", "gray"])),
        ddl="緑の小さな楕円を十二散らす。",
    )

    assert _cycles(fixed) == [["green"]]
    assert [ins.color for ins in fixed.instructions] == ["green"]


def test_t10_the_disabled_exit_still_leaves_a_two_color_description_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INKU_COERCE_DISABLE", "1")

    fixed = coerce_score(
        _score(_grouped("red", ["red", "blue"])),
        ddl="赤と青の小さな楕円を十二散らす。",
    )

    assert _cycles(fixed) == [["red", "blue"]]
