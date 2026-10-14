"""Index distinct concrete-color assignments without sampling or factorial lists."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from xml.etree import ElementTree


_HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
_SHORT_HEX = re.compile(r"#[0-9a-fA-F]{3}\Z")
_PAINT_ATTRIBUTES = {"fill", "stroke", "stop-color", "flood-color", "lighting-color", "color"}


def normalized_hex(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if _SHORT_HEX.fullmatch(value):
        return "#" + "".join(character * 2 for character in value[1:])
    return value if _HEX.fullmatch(value) else None


@dataclass(frozen=True)
class ColorArrangements:
    palette: tuple[str, ...]
    used: tuple[str, ...]
    identity_rank: int

    @classmethod
    def from_saved(cls, svg: str, color_map: dict[str, str]) -> ColorArrangements:
        colors = [normalized_hex(value) for key, value in color_map.items() if key.startswith("palette:")]
        if not colors or any(color is None for color in colors):
            raise ValueError("saved color catalog has no usable palette")
        palette = tuple(sorted(set(colors)))
        try:
            root = ElementTree.fromstring(svg)
        except ElementTree.ParseError as error:
            raise ValueError("saved work has no usable SVG") from error
        paints = set()
        for element in root.iter():
            attributes = dict(element.attrib)
            for declaration in attributes.get("style", "").split(";"):
                name, separator, value = declaration.partition(":")
                if separator:
                    attributes[name.strip()] = value.strip()
            for name, value in attributes.items():
                color = normalized_hex(value) if name in _PAINT_ATTRIBUTES else None
                if color in palette:
                    paints.add(color)
        used = tuple(sorted(paints))
        remaining = list(palette)
        identity_rank = 0
        for position, color in enumerate(used):
            digit = remaining.index(color)
            identity_rank += digit * math.perm(len(remaining) - 1, len(used) - position - 1)
            remaining.pop(digit)
        return cls(palette, used, identity_rank)

    @property
    def total(self) -> int:
        return math.perm(len(self.palette), len(self.used)) - 1

    def page(self, cursor: int = 0) -> dict:
        if cursor < 0:
            raise ValueError("color arrangement cursor must be nonnegative")
        end = min(cursor + 8, self.total)
        return {
            "entries": [{"index": index} for index in range(cursor, end)],
            "next_cursor": end if end < self.total else None,
            "total": self.total,
        }

    def substitution(self, index: int) -> dict[str, str]:
        if not 0 <= index < self.total:
            raise ValueError("color arrangement index is exhausted or invalid")
        rank = index + (index >= self.identity_rank)
        remaining = list(self.palette)
        chosen = []
        for position in range(len(self.used)):
            block = math.perm(len(remaining) - 1, len(self.used) - position - 1)
            digit, rank = divmod(rank, block)
            chosen.append(remaining.pop(digit))
        return dict(zip(self.used, chosen, strict=True))

    def color_map(self, parent_map: dict[str, str], index: int) -> dict[str, str]:
        """Compose the parent's one-pass substitutions with this visible assignment."""
        substitution = self.substitution(index)
        previous = {
            normalized_hex(key.removeprefix("recolor:")): normalized_hex(value)
            for key, value in parent_map.items()
            if key.startswith("recolor:")
        }
        if any(source is None or target is None for source, target in previous.items()):
            raise ValueError("saved work has an invalid color arrangement")
        result = {key: value for key, value in parent_map.items() if not key.startswith("recolor:")}
        originals = {normalized_hex(value) for value in result.values()} | set(previous)
        for original in originals - {None}:
            current = previous.get(original, original)
            target = substitution.get(current, current)
            if target != original:
                result[f"recolor:{original}"] = target
        return result
