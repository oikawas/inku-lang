"""ddl-engine 8: the color cycle stops inventing an order.

`arrangement.color_cycle` hands one color to each member of a group in turn --
`cycle[i % len(cycle)]` in `renderer.py`. A pure cycle has no head and no
ranking: n colors take 1/n of the members each. coerce was writing two kinds of
order into it anyway, and the description asked for neither.

It inserted the instruction's own color without looking, so a color already in
the cycle took twice the members. That weighting reads as emphasis, but its size
is an accident of length -- with a three-color cycle the doubled color goes from
33% to 50%, with five colors from 20% to 40%. And `_color_repair_order` ran the
requested colors through a six-word table that predates yellow, orange, and
purple, so `return ordered or sorted(colors)` dropped every new color as soon as
one old color was present: `{red, yellow}` became `[red]`.

These eight tests hold both halves. T-1 and T-2 are a pair on purpose -- T-1
alone would pass an implementation that never puts the primary color in the
cycle at all, which would take that color out of the picture, because the
renderer overwrites `ins.color` whenever a cycle is present. T-5 to T-7 separate
the three things the table now does and does not do: it drops nothing, it keeps
the relative order of the words it names, and it puts the words it does not name
after them rather than in front. T-8 is a control on the one caller this change
deliberately leaves alone.

What this does NOT do: it does not remove a duplicate the input already carried.
`_with_color_cycle_delivery` copies an existing cycle through as it is, so a
stored score written by an older coerce keeps its duplicate (H-03 and H-14 in
the golden set). The property held here is that this layer stops *authoring*
one.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.coerce.compose import (
    _color_only_constraint_from_ddl,
    _color_repair_order,
    _with_color_cycle_delivery,
)
from inku_server.layer_versions import DDL_ENGINE_VERSION
from inku_server.schema import Instruction, Score

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
COERCE_CORPUS = SERVER_ROOT / "reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "b_coerce"

# The six words `_color_repair_order` names, in the order it names them.
KNOWN_ORDER = ("red", "blue", "green", "white", "black", "gray")
# `Instruction.color` accepts nine. The three the table never learned are the
# ones `return ordered or sorted(colors)` used to drop.
ALL_COLORS = frozenset(KNOWN_ORDER) | {"yellow", "orange", "purple"}


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


def _cycles(score: Score) -> list[list[str]]:
    return [
        list(ins.arrangement.color_cycle)
        for ins in score.instructions
        if ins.arrangement is not None and ins.arrangement.color_cycle
    ]


def _corpus_cycles() -> list[tuple[str, list[str]]]:
    found: list[tuple[str, list[str]]] = []

    def walk(node: object, name: str) -> None:
        if isinstance(node, dict):
            cycle = node.get("color_cycle")
            if isinstance(cycle, list) and cycle:
                found.append((name, [str(color) for color in cycle]))
            for value in node.values():
                walk(value, name)
        elif isinstance(node, list):
            for value in node:
                walk(value, name)

    for path in sorted(COERCE_CORPUS.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")), path.name)
    return found


# T-1: the delivery never hands the cycle a color it already carries.


def test_t1_delivery_does_not_add_a_color_the_cycle_already_carries() -> None:
    # The H-01 shape: the instruction's own color is already the head of its
    # cycle, and a DDL color arrives that is not yet in it.
    delivered = _with_color_cycle_delivery(_grouped("red", ["red", "black"]), ["yellow"])

    assert delivered.arrangement is not None
    cycle = list(delivered.arrangement.color_cycle)
    assert cycle == ["red", "black", "yellow"]
    assert len(cycle) == len(set(cycle))


def test_t1_repaired_score_carries_no_duplicated_color_in_a_cycle() -> None:
    score = Score.model_validate({"instructions": [_grouped("red", ["red", "black"]).model_dump(by_alias=True)]})

    fixed = coerce_score(score, ddl="黄色い小さな四角を点々と散らす。")

    cycles = _cycles(fixed)
    assert cycles, "the repair must have written a cycle for this to measure anything"
    for cycle in cycles:
        assert len(cycle) == len(set(cycle)), cycle


def test_t1_frozen_coerce_corpus_holds_no_duplicated_cycle() -> None:
    cycles = _corpus_cycles()
    assert len(cycles) >= 10, f"only {len(cycles)} cycles in the corpus; the census stopped seeing them"
    duplicated = [(name, cycle) for name, cycle in cycles if len(cycle) != len(set(cycle))]
    assert duplicated == []


# T-2: the primary color stays in the cycle. Not doubling it is not dropping it.


def test_t2_primary_color_is_present_in_the_cycle_it_receives() -> None:
    delivered = _with_color_cycle_delivery(_grouped("red", None), ["blue"])

    assert delivered.arrangement is not None
    assert "red" in delivered.arrangement.color_cycle
    assert delivered.arrangement.color_cycle[0] == "red"


def test_t2_primary_color_survives_when_it_is_already_in_the_cycle() -> None:
    # This is the case T-1 changes. Removing the duplicate must not remove the
    # color: the renderer overwrites `ins.color` from the cycle, so a primary
    # color missing from the cycle is a primary color missing from the picture.
    delivered = _with_color_cycle_delivery(_grouped("red", ["red", "black"]), ["yellow"])

    assert delivered.arrangement is not None
    assert "red" in delivered.arrangement.color_cycle


def test_t2_every_repaired_instruction_keeps_its_own_color_in_its_cycle() -> None:
    score = Score.model_validate({"instructions": [_grouped("red", ["red", "black"]).model_dump(by_alias=True)]})

    fixed = coerce_score(score, ddl="黄色い小さな四角を点々と散らす。")

    grouped = [ins for ins in fixed.instructions if ins.arrangement is not None and ins.arrangement.color_cycle]
    assert grouped, "the repair must have written a cycle for this to measure anything"
    for ins in grouped:
        assert ins.color in ins.arrangement.color_cycle, (ins.color, list(ins.arrangement.color_cycle))


# T-5: the order table orders. It does not decide which colors survive.


@pytest.mark.parametrize(
    "colors",
    [
        {"red", "yellow"},
        {"red", "yellow", "purple"},
        {"yellow", "orange", "purple"},
        {"gray", "red"},
        set(ALL_COLORS),
    ],
)
def test_t5_color_repair_order_drops_nothing(colors: set[str]) -> None:
    ordered = _color_repair_order(set(colors))

    assert set(ordered) == colors
    assert len(ordered) == len(colors), f"a color was repeated: {ordered}"


def test_t5_an_old_color_no_longer_evicts_the_new_ones() -> None:
    # The exact shape [I-060] was filed for: before ddl-engine 8 this returned
    # ["red"], and the yellow the author wrote never reached the score.
    assert _color_repair_order({"red", "yellow"}) == ["red", "yellow"]


# T-6: the six words the table names keep the order it names them in.


@pytest.mark.parametrize(
    "colors,expected",
    [
        ({"gray", "red"}, ["red", "gray"]),
        ({"black", "blue", "red"}, ["red", "blue", "black"]),
        (set(KNOWN_ORDER), list(KNOWN_ORDER)),
    ],
)
def test_t6_known_words_keep_their_relative_order(colors: set[str], expected: list[str]) -> None:
    assert _color_repair_order(set(colors)) == expected


def test_t6_known_words_keep_their_relative_order_with_new_colors_mixed_in() -> None:
    ordered = _color_repair_order({"gray", "red", "yellow", "purple"})

    known = [color for color in ordered if color in KNOWN_ORDER]
    assert known == ["red", "gray"]


# T-7: the words the table does not name follow it, rather than displacing it.


@pytest.mark.parametrize(
    "colors,expected",
    [
        ({"yellow", "red"}, ["red", "yellow"]),
        ({"orange", "gray", "purple"}, ["gray", "orange", "purple"]),
        ({"purple", "red", "yellow"}, ["red", "purple", "yellow"]),
    ],
)
def test_t7_unnamed_colors_follow_the_table(colors: set[str], expected: list[str]) -> None:
    assert _color_repair_order(set(colors)) == expected


def test_t7_no_unnamed_color_precedes_a_named_one() -> None:
    ordered = _color_repair_order(set(ALL_COLORS))

    last_named = max(index for index, color in enumerate(ordered) if color in KNOWN_ORDER)
    first_unnamed = min(index for index, color in enumerate(ordered) if color not in KNOWN_ORDER)
    assert last_named < first_unnamed, ordered


def test_t7_colors_the_table_does_not_name_are_ordered_deterministically() -> None:
    # Sorted, not by chance: `_requested_colors_from_ddl` returns a set, so the
    # order the author wrote them in is already gone by the time this is called.
    ordered = _color_repair_order({"yellow", "orange", "purple"})
    assert ordered == sorted(ordered)


# T-8: control. The color-only path is not part of this change.


def test_t8_color_only_constraint_still_picks_the_first_visible_color() -> None:
    assert _color_only_constraint_from_ddl("赤と青だけで描く。") == ["red", "blue"]

    score = Score.model_validate(
        {
            "background": "white",
            "instructions": [
                {"primitive": "line", "from": [0.2, 0.2], "to": [0.8, 0.8], "color": "green"},
            ],
        }
    )

    fixed = coerce_score(score, ddl="赤と青だけで描く。")

    assert fixed.instructions[0].color == "red"
    assert "explicit color-only constraint enforced" in (fixed.instructions[0].note or "")
