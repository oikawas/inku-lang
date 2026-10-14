"""Changing the touches swaps each asked sentence's weight in the saved Score and nothing else."""

import random

from inku_server.tool_variants import DEFAULT_TOOL, TOOLS, drawn_tools, options, score_with_tools


def _instruction(index: int, weight: str | None) -> dict:
    instruction = {"primitive": "line", "color": "blue",
                   "arrangement": {"resolved": {"owner": {"kind": "source_instruction", "instruction_index": index}}}}
    if weight:
        instruction["weight"] = weight
    return instruction


def test_the_saijiki_names_twelve_tools_and_the_pen_is_the_default():
    assert TOOLS == ("silverpoint", "pencil", "pen", "rotring", "crayon", "chalk", "brush_thin",
                     "brush_thick", "oil_paint", "burin", "drypoint", "computer")
    assert DEFAULT_TOOL == "pen"


def test_the_drawn_tools_are_read_from_the_score_by_sentence():
    score = {"instructions": [_instruction(0, "chalk"), _instruction(1, None), _instruction(2, "crayon")]}
    assert drawn_tools(score, [0, 1]) == {0: "chalk", 1: "pen"}


def test_only_the_asked_sentences_change_their_weight():
    score = {"version": "0.13.0", "instructions": [_instruction(0, "chalk"), _instruction(1, "pen"), {"primitive": "fill"}]}
    changed = score_with_tools(score, {1: "oil_paint"})
    assert [instruction.get("weight") for instruction in changed["instructions"]] == ["chalk", "oil_paint", None]
    assert {k: v for k, v in changed["instructions"][1].items() if k != "weight"} == {
        k: v for k, v in score["instructions"][1].items() if k != "weight"}
    assert score["instructions"][1]["weight"] == "pen"


def test_uniform_options_give_every_sentence_one_tool_that_changes_something():
    drawn = {0: "chalk", 3: "chalk"}
    chosen = options(drawn, "uniform", random.Random(1))
    assert len(chosen) == 4
    assert all(len(set(option.values())) == 1 and set(option) == {0, 3} for option in chosen)
    assert all(option[0] != "chalk" for option in chosen)
    assert len({option[0] for option in chosen}) == 4
    # A tool one sentence already has is still offered when another sentence changes.
    offered = {option[0] for seed in range(40) for option in options({0: "pen", 1: "chalk"}, "uniform", random.Random(seed))}
    assert offered == set(TOOLS)


def test_per_sentence_options_draw_another_tool_for_each_sentence():
    drawn = {0: "chalk", 1: "pen", 2: "oil_paint"}
    chosen = options(drawn, "per_sentence", random.Random(2))
    assert len(chosen) == 4 and len({tuple(sorted(option.items())) for option in chosen}) == 4
    assert all(option[index] != drawn[index] for option in chosen for index in drawn)
