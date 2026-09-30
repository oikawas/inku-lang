"""The sounds (on, morae) of a Japanese description.

The description meter compares a description's length with the verse forms --
haiku 5-7-5, tanka 5-7-5-7-7 and the rest -- and those forms are counted in
sounds, not characters: 「古池や」 is five sounds in three characters. A kanji's
sounds come only from its reading, so the reading of each word is looked up
with SudachiPy and its small dictionary (Apache-2.0, both), and the reading's
kana are counted: a small ャュョ joins the kana before it, while ッ, ン and ー
each count one.

It is a guide, not a scansion. The dictionary reads modern Japanese; a
classical reading (「来にけらし」), a poet's own reading, or a word it does not
know can be counted differently from the way the poem is read aloud. A
character the dictionary cannot read at all is returned in ``unread`` and
counted as ``UNREAD_KANJI_MORA`` for a kanji or one for anything else, so the
total stays near the truth and the page can say that it is approximate.

The description is read the way the drawing reads it (numbering and comments
removed), and split into phrases at line breaks, spaces and 、。 so that a
poem set out 5-7-5 is counted phrase by phrase.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from .description_labels import pipeline_description

# A kanji the dictionary cannot read is counted as the sounds a kanji most
# often has; the total then errs by about one per unread kanji, not by two.
UNREAD_KANJI_MORA = 2

# Small kana that join the kana before them. ヵ and ヶ are not here: they are
# read as a whole sound (「一ヶ月」).
_JOINING_KANA = frozenset("ァィゥェォャュョヮ")
_PHRASE_BREAK = re.compile(r"[\s、。，．,.!！?？・]+")
_KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆〇]")


@dataclass
class MoraCount:
    total: int = 0
    phrases: list[int] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)


def _katakana(text: str) -> str:
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch for ch in text)


def kana_mora(text: str) -> int:
    """The sounds in a run of kana; anything else counts nothing."""
    count = 0
    for ch in _katakana(text):
        if ch == "ー" or ("ァ" <= ch <= "ヺ" and ch not in _JOINING_KANA):
            count += 1
    return count


def _unread(reading: str) -> list[str]:
    """Letters and digits left in a reading: the dictionary did not read them."""
    left: list[str] = []
    for ch in reading:
        if ch == "ー" or "ァ" <= ch <= "ヺ":
            continue
        if unicodedata.category(ch)[0] in ("L", "N"):
            left.append(ch)
    return left


@lru_cache(maxsize=1)
def _tokenizer():
    # Loaded on the first count, not at import: the dictionary takes about
    # half a second to open, and most requests never count.
    from sudachipy import dictionary

    return dictionary.Dictionary(dict="small").create()


# A SudachiPy tokenizer is not safe to share between threads, and FastAPI runs
# a plain endpoint on a thread pool.
_TOKENIZER_LOCK = threading.Lock()


def _phrase_mora(phrase: str, unread: list[str]) -> int:
    count = 0
    with _TOKENIZER_LOCK:
        morphemes = [(m.surface(), m.reading_form()) for m in _tokenizer().tokenize(phrase)]
    for surface, reading in morphemes:
        reading = _katakana(reading or surface)
        count += kana_mora(reading)
        for ch in _unread(reading):
            unread.append(ch)
            count += UNREAD_KANJI_MORA if _KANJI.match(ch) else 1
    return count


def count_mora(text: str | None) -> MoraCount:
    """The sounds of a description, in total and phrase by phrase."""
    source = pipeline_description(text).strip()
    result = MoraCount()
    for phrase in _PHRASE_BREAK.split(source):
        if not phrase:
            continue
        mora = _phrase_mora(phrase, result.unread)
        result.phrases.append(mora)
        result.total += mora
    return result
