"""The syllables of an English description, line by line.

The description meter tells English forms apart by lines and, where the form
is made of syllables -- a haiku's three short lines, a cinquain's 2-4-6-8-2 --
by syllables too. A word's syllables are the vowels of its pronunciation in
the Carnegie Mellon Pronouncing Dictionary (``cmudict/``, bundled with its
BSD-style licence from cmusphinx/cmudict at commit
74790861f652b15e4ac49015a90074ad62a27690): each vowel phoneme carries a stress
digit, so the digits are counted. The first pronunciation listed is used.

A word the dictionary does not have (a coinage, most names) is counted by its
vowel groups less a silent final e, as the page does before the Server
answers, and is returned in ``unknown``.

The description is read the way the drawing reads it (numbering and comments
removed); each non-empty line is one line of the poem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .description_labels import pipeline_description

_DICTIONARY = Path(__file__).parent / "cmudict" / "cmudict.dict"
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


@dataclass
class SyllableCount:
    total: int = 0
    lines: list[int] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _pronunciations() -> dict[str, int]:
    # Read on the first count, not at import: 135,000 lines take about a third
    # of a second, and most requests never count.
    syllables: dict[str, int] = {}
    with _DICTIONARY.open(encoding="utf-8") as handle:
        for line in handle:
            entry = line.split("#", 1)[0].split()
            if not entry:
                continue
            word = entry[0]
            if "(" in word:  # "word(2)": an alternative pronunciation; the first stands
                continue
            syllables[word] = sum(1 for phoneme in entry[1:] if phoneme[-1].isdigit())
    return syllables


def estimated_syllables(word: str) -> int:
    """Vowel groups less a silent final e: the count for a word the dictionary lacks."""
    word = word.lower().replace("'", "")
    if len(word) > 2 and word.endswith("e") and not re.search(r"[^aeiouy]le$", word):
        word = word[:-1]
    return max(1, len(re.findall(r"[aeiouy]+", word)))


def _line_syllables(line: str, unknown: list[str]) -> int:
    known = _pronunciations()
    count = 0
    for word in _WORD.findall(line):
        found = known.get(word.lower())
        if found is None:
            unknown.append(word)
            found = estimated_syllables(word)
        count += found
    return count


def count_syllables(text: str | None) -> SyllableCount:
    """The syllables of a description, in total and line by line."""
    source = pipeline_description(text).strip()
    result = SyllableCount()
    for line in source.split("\n"):
        if not line.strip():
            continue
        syllables = _line_syllables(line, result.unknown)
        result.lines.append(syllables)
        result.total += syllables
    return result
