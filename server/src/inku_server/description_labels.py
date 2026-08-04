"""What the author writes for themselves, and the drawing never reads.

Two things in a description are labels rather than description:

  - a **leading number** ("1. ", "０１．", "12) ") that orders lines in a batch;
  - a **comment** in brackets ("[疎  紀友則 / 古今和歌集（春下）]") naming a source.

Both are kept verbatim in the stored work -- they are the author's document --
and both are cut before the text reaches any layer, Stage 0.5 included.  The cut
happens here, once, so that every client gets the same rule: the web editor
greys these ranges out, but the web is not what enforces them.

The functions return spans as well as text so the editor can paint exactly what
the server will drop.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# A numbering has to be a numbering, not a measurement: "3本の線" and "2026年"
# are description.  Digits (either width) followed by one of the separators an
# author actually types, and the ideographic space counts as one because "１　花"
# is how a numbered line is written in Japanese.
_LEADING_NUMBER = re.compile(r"^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*")

# Brackets of both widths, closed on the line they were opened on.  An unclosed
# "[" is description: it would otherwise swallow the rest of the text.
_COMMENT = re.compile(r"\[[^\[\]\n]*\]|［[^［］\n]*］")


class Span(NamedTuple):
    """A half-open range of the original text that the drawing does not read."""

    start: int
    end: int
    kind: str  # "number" | "comment"


def excluded_spans(text: str) -> list[Span]:
    """Every range the drawing does not read, in order of appearance."""
    if not text:
        return []
    spans: list[Span] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        number = _LEADING_NUMBER.match(line)
        if number:
            spans.append(Span(offset + number.start(), offset + number.end(), "number"))
        for comment in _COMMENT.finditer(line):
            spans.append(Span(offset + comment.start(), offset + comment.end(), "comment"))
        offset += len(line)
    spans.sort()
    return spans


def pipeline_description(text: str | None) -> str:
    """The description with its labels removed, as every layer should read it.

    Whitespace left behind by a removal is collapsed so that a comment taken out
    of the middle of a sentence does not leave a double space; line breaks are
    kept, because they are the author's.
    """
    if not text:
        return text or ""
    spans = excluded_spans(text)
    if not spans:
        return text
    kept: list[str] = []
    at = 0
    for start, end, _kind in spans:
        kept.append(text[at:start])
        at = end
    kept.append(text[at:])
    stripped = "".join(kept)
    # Collapse the gap a removal leaves, per line, without touching the breaks.
    lines = [re.sub(r"[ \t　]{2,}", " ", line).strip(" \t　") for line in stripped.split("\n")]
    return "\n".join(lines)
