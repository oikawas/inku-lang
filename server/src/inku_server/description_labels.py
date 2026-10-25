"""What the author writes for themselves, and the drawing never reads.

Two things in a description are labels rather than description:

  - a **leading number** ("1. ", "０１．", "12) ") that orders lines in a batch;
  - a **comment** in brackets ("[疎  紀友則 / 古今和歌集（春下）]") naming a source.

Both are kept verbatim in the stored work -- they are the author's document --
and both are cut before the text reaches any layer, Stage 0.5 included.  The cut
happens here, once, so that every client gets the same rule: the web editor
greys these ranges out, but the web is not what enforces them.

The rule (which numbers and brackets are labels, and the ranges they cover) is
the shared core's ``description_labels.rs``; the editor paints the same ranges
from ``server/tests/data/description-label-cases.json``.
"""

from __future__ import annotations

import importlib
import json


def pipeline_description(text: str | None) -> str:
    """The description with its labels removed, as every layer should read it.

    Whitespace left behind by a removal is collapsed so that a comment taken out
    of the middle of a sentence does not leave a double space; line breaks are
    kept, because they are the author's.  The shared core does the cut, so
    Server and every app read a description alike.
    """
    if not text:
        return text or ""
    return importlib.import_module("inku_render").pipeline_description_without_labels(text)


def source_labels(text: str | None) -> list[str]:
    """The bracketed comments' contents, brackets and outer spaces cut, in order.

    Read and draw (SPEC §12.6.7) hands them to the reading only, as words the
    description's source gives; a leading number is not one. The ranges are
    the shared core's, as the cut is.
    """
    if not text:
        return []
    spans = json.loads(importlib.import_module("inku_render").pipeline_description_label_spans(text))
    return [label for start, end, kind in spans if kind == "comment" and (label := text[start + 1:end - 1].strip())]
