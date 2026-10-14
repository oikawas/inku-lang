"""Change a saved work's support (the じ category) and nothing else (the author, 2026-10-14).

A ground written in the instructions reaches the Score as `canvas.ground` with only its
material named (the compiler adds no texture, seed or tone of its own), so swapping the
material in the saved Score draws what that instruction would have drawn, while every
placement, color and touch stays the parent's. Recompiling edited instructions would not:
seeded angles are drawn again from the whole document. The child's instructions carry the
new ground sentence so that they say what was drawn.

A work offers every named support it is not on: six when it names one, all seven when it
names none (its ground is `plain`, which is not a word one can write).
"""

from __future__ import annotations

from copy import deepcopy

from .saijiki import SAIJIKI

_JI = next(category for category in SAIJIKI if category.key == "ji")
GROUND_MATERIALS: tuple[str, ...] = tuple(word.score_value for word in _JI.words if word.score_value)
_SURFACES = {word.score_value: {"ja": word.surface_ja, "en": word.surface_en} for word in _JI.words if word.score_value}


def current_material(score: dict) -> str:
    canvas = score.get("canvas")
    ground = canvas.get("ground") if isinstance(canvas, dict) else None
    material = ground.get("material") if isinstance(ground, dict) else None
    return material if isinstance(material, str) else "plain"


def unused_materials(score: dict) -> list[str]:
    current = current_material(score)
    return [material for material in GROUND_MATERIALS if material != current]


def ground_label(material: str, lang: str) -> str:
    return _SURFACES[material]["ja" if lang == "ja" else "en"]


def score_with_ground(score: dict, material: str) -> dict:
    if material not in GROUND_MATERIALS:
        raise ValueError(f"unknown ground material: {material}")
    changed = deepcopy(score)
    canvas = changed.get("canvas", "square")
    if isinstance(canvas, dict):
        ground = canvas.get("ground") if isinstance(canvas.get("ground"), dict) else {}
        canvas["ground"] = {**ground, "material": material}
    else:
        changed["canvas"] = {"aspect": canvas, "ground": {"material": material}}
    return changed


def _sentence(material: str, lang: str) -> str:
    surface = ground_label(material, lang)
    return f"{surface}。" if lang == "ja" else f"{surface[:1].upper()}{surface[1:]}."


def _ground_line(line: str) -> str | None:
    """The language of a line that is one ground sentence, or None."""
    text = line.strip()
    for material in GROUND_MATERIALS:
        if text == _sentence(material, "ja"):
            return "ja"
        if text.lower() == _sentence(material, "en").lower():
            return "en"
    return None


def ddl_with_ground(ddl: str, material: str, lang: str | None) -> str:
    """The instructions with their ground sentence replaced, or one placed first."""
    lines = ddl.split("\n")
    for index, line in enumerate(lines):
        line_lang = _ground_line(line)
        if line_lang:
            lines[index] = _sentence(material, line_lang)
            return "\n".join(lines)
    if lang not in ("ja", "en"):
        lang = "ja" if any("぀" <= character <= "鿿" for character in ddl) else "en"
    sentence = _sentence(material, lang)
    return f"{sentence}\n{ddl}" if ddl else sentence
