"""Change a saved work's touches (the てざわり category) and nothing else (the author, 2026-10-14).

A touch is the tool a sentence is drawn with, and it reaches the Score as each
instruction's `weight`. Swapping the weights in the saved Score draws what those
sentences would have drawn with the other tools, while every placement, color and
seed stays the parent's: an instruction's strokes do not move when another
instruction's tool changes (measured on 5173, 2026-10-14). The shared core writes
the new tool words into the instructions and reads them back, so the child's
instructions say what was drawn.

Four options either give every sentence one tool (the default) or draw a tool for
each sentence. An option is the tool asked for each sentence by its instruction
index, and the child records it, so the Server draws the child again from the
parent when it is saved.
"""

from __future__ import annotations

import random
from copy import deepcopy

from .saijiki import SAIJIKI

_TEZAWARI = next(category for category in SAIJIKI if category.key == "tezawari")
TOOLS: tuple[str, ...] = tuple(word.score_value for word in _TEZAWARI.words if word.score_value)
DEFAULT_TOOL = next(word.score_value for word in _TEZAWARI.words if word.default)
_LABELS = {word.score_value: {"ja": word.surface_ja, "en": word.surface_en} for word in _TEZAWARI.words if word.score_value}
MODES = ("uniform", "per_sentence")
OPTION_COUNT = 4


def tool_label(tool: str, lang: str) -> str:
    return _LABELS[tool]["ja" if lang == "ja" else "en"]


def _owner_index(instruction: dict) -> int | None:
    arrangement = instruction.get("arrangement")
    resolved = arrangement.get("resolved") if isinstance(arrangement, dict) else None
    owner = resolved.get("owner") if isinstance(resolved, dict) else None
    if not isinstance(owner, dict) or owner.get("kind") != "source_instruction":
        return None
    index = owner.get("instruction_index")
    return index if type(index) is int else None


def drawn_tools(score: dict, sentences: list[int]) -> dict[int, str]:
    """The tool each sentence was drawn with, read from the saved Score."""
    drawn: dict[int, str] = {}
    for instruction in score.get("instructions") or []:
        if not isinstance(instruction, dict):
            continue
        index = _owner_index(instruction)
        if index in sentences and index not in drawn:
            weight = instruction.get("weight")
            drawn[index] = weight if weight in TOOLS else DEFAULT_TOOL
    return {index: drawn.get(index, DEFAULT_TOOL) for index in sentences}


def score_with_tools(score: dict, tools: dict[int, str]) -> dict:
    """The saved Score with each asked sentence's instructions drawn with its tool."""
    for tool in tools.values():
        if tool not in TOOLS:
            raise ValueError(f"unknown tool: {tool}")
    changed = deepcopy(score)
    for instruction in changed.get("instructions") or []:
        if isinstance(instruction, dict):
            index = _owner_index(instruction)
            if index in tools:
                instruction["weight"] = tools[index]
    return changed


def options(drawn: dict[int, str], mode: str, rng: random.Random | None = None) -> list[dict[int, str]]:
    """Up to four tool assignments, each changing at least one sentence.

    `uniform` gives every sentence one tool, a different one per option; a tool
    every sentence already has is not offered. `per_sentence` draws, for each
    sentence, a tool other than the one it has.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    rng = rng or random.SystemRandom()
    sentences = sorted(drawn)
    if not sentences:
        return []
    if mode == "uniform":
        offered = [tool for tool in TOOLS if any(drawn[index] != tool for index in sentences)]
        return [{index: tool for index in sentences} for tool in rng.sample(offered, min(OPTION_COUNT, len(offered)))]
    chosen: list[dict[int, str]] = []
    for _ in range(OPTION_COUNT * 8):
        option = {index: rng.choice([tool for tool in TOOLS if tool != drawn[index]]) for index in sentences}
        if option not in chosen:
            chosen.append(option)
        if len(chosen) == OPTION_COUNT:
            break
    return chosen
