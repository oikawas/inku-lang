"""The one place a stated count is read from a description.

Two layers ask "how many did the description say": the coerce layer, which
repairs a Score against what was asked for, and the plugin expansion layer,
which places a macro as many times as the body states.  When each keeps its own
reader, a hole gets fixed on one side only -- which is how the English path came
to read number words but not numerals while the Japanese path read both.  Both
layers import from here, so a fix lands once.

This module is a leaf: it imports `Limits` and nothing else from the package.
Neither `coerce` nor `plugins` may be imported from here.
"""

from __future__ import annotations

import re

from .limits import DEFAULT_LIMITS, Limits


_KANJI_NUMBERS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "百": 100,
    "千": 1000,
}


def _parse_small_japanese_number(text: str) -> int | None:
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "千":
        return 1000
    if "千" in text:
        head, tail = text.split("千", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 1000
        rest = _parse_small_japanese_number(tail)
        return value + (rest or 0)
    if text == "百":
        return 100
    if text.endswith("百") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 100
    if "百" in text:
        head, tail = text.split("百", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 100
        rest = _parse_small_japanese_number(tail)
        return value + (rest or 0)
    if text == "十":
        return 10
    if text.endswith("十") and len(text) == 2:
        return _KANJI_NUMBERS.get(text[0], 1) * 10
    if "十" in text:
        head, tail = text.split("十", 1)
        value = (_KANJI_NUMBERS.get(head, 1) if head else 1) * 10
        return value + (_KANJI_NUMBERS.get(tail, 0) if tail else 0)
    if len(text) == 1:
        return _KANJI_NUMBERS.get(text)
    return None


def _is_literal_grid_request(ddl: str | None) -> bool:
    if not ddl:
        return False
    lower = ddl.lower()
    if any(marker in ddl for marker in ("敷き詰め", "格子状", "格子に", "一面に並", "全面に並")):
        return True
    return re.search(r"\b(?:tile|tiled|tiling)\b", lower) is not None


def count_hint_from_ddl(ddl: str, limits: Limits = DEFAULT_LIMITS) -> int | None:
    """Extract a conservative count hint from a normalized DDL fragment."""
    literal_grid = _is_literal_grid_request(ddl)
    clauses = re.split(r"[。.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    pattern = r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)"
    for candidate in candidates:
        match = re.search(pattern, candidate)
        if not match:
            continue
        value = _parse_small_japanese_number(match.group(1))
        if value is not None:
            maximum = limits.ddl_count_max_grid if literal_grid else limits.ddl_count_max
            return min(max(value, 1), maximum)
    return _english_count_hint(ddl, limits)


ENGLISH_SMALL_NUMBERS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


ENGLISH_COUNT_UNITS: dict[str, int] = {
    **ENGLISH_SMALL_NUMBERS,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


def _english_count_hint(ddl: str, limits: Limits = DEFAULT_LIMITS) -> int | None:
    literal_grid = _is_literal_grid_request(ddl)
    clauses = re.split(r"[.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    words = re.findall(r"[a-z]+", " ".join(candidates).lower().replace("-", " "))
    count_nouns = {
        "line", "lines", "stroke", "strokes", "square", "squares",
        "cloudform", "cloudforms", "tile", "tiles", "brick", "bricks",
    }
    number_words = set(ENGLISH_COUNT_UNITS) | {"hundred", "thousand", "and"}
    for start, word in enumerate(words):
        if word not in number_words or word == "and":
            continue
        end = start
        phrase: list[str] = []
        while end < len(words) and words[end] in number_words:
            phrase.append(words[end])
            end += 1
        if not any(noun in count_nouns for noun in words[end : end + 9]):
            continue
        total = 0
        current = 0
        for token in phrase:
            if token == "and":
                continue
            if token == "hundred":
                current = max(current, 1) * 100
            elif token == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                current += ENGLISH_COUNT_UNITS[token]
        value = total + current
        if value:
            maximum = (
                limits.ddl_count_max_grid if _is_literal_grid_request(ddl) else limits.ddl_count_max
            )
            return min(max(value, 1), maximum)
    return None


def _parse_count_token(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    if token in ENGLISH_SMALL_NUMBERS:
        return ENGLISH_SMALL_NUMBERS[token]
    return _parse_small_japanese_number(token)


COUNTED_OBJECT_WORDS: frozenset[str] = frozenset(
    {
        "line", "lines", "stroke", "strokes", "square", "squares", "circle", "circles",
        "ellipse", "ellipses", "oval", "ovals", "triangle", "triangles", "arc", "arcs",
        "polygon", "polygons", "cloudform", "cloudforms", "dot", "dots", "mark", "marks",
        "point", "points", "tile", "tiles", "brick", "bricks", "shape", "shapes",
    }
)

JAPANESE_COUNT_PATTERN = re.compile(r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)")

# LITERAL_COUNT_THRESHOLD and REPRESENTED_COUNT_RANGE used to be defined here, a
# second name for the band `..limits` already holds. Both readers now go through
# Limits, so the band exists under one name only.


def _explicit_counts_from_ddl(ddl: str | None) -> frozenset[int]:
    """Every count the description states outright, in either language.

    `count_hint_from_ddl` answers "what is the count here" and stops at the first
    match. This answers "which counts were asked for at all", which is what tells a
    group written to order apart from one a governor is free to thin.
    """
    if not ddl:
        return frozenset()
    counts: set[int] = set()
    for token in JAPANESE_COUNT_PATTERN.findall(ddl):
        value = _parse_small_japanese_number(token)
        if value:
            counts.add(value)
    words = re.findall(r"[a-z]+", ddl.lower().replace("-", " "))
    number_words = set(ENGLISH_COUNT_UNITS) | {"hundred", "thousand", "and"}
    index = 0
    while index < len(words):
        if words[index] not in number_words or words[index] == "and":
            index += 1
            continue
        end = index
        phrase: list[str] = []
        while end < len(words) and words[end] in number_words:
            phrase.append(words[end])
            end += 1
        if any(word in COUNTED_OBJECT_WORDS for word in words[end : end + 9]):
            total = 0
            current = 0
            for token in phrase:
                if token == "and":
                    continue
                if token == "hundred":
                    current = max(current, 1) * 100
                elif token == "thousand":
                    total += max(current, 1) * 1000
                    current = 0
                else:
                    current += ENGLISH_COUNT_UNITS[token]
            if total + current:
                counts.add(total + current)
        index = end
    return frozenset(counts)


def _count_follows_ddl_request(
    count: int, requested: frozenset[int], limits: Limits = DEFAULT_LIMITS
) -> bool:
    """Is this count the one the description asked for, literally or as its stand-in?"""
    if count in requested:
        return True
    if limits.represented_count_min <= count <= limits.represented_count_max:
        return any(value >= limits.literal_count_threshold for value in requested)
    return False


def _strict_count_hint_from_ddl(ddl: str | None) -> int | None:
    if not ddl:
        return None
    lower = ddl.lower()
    patterns = (
        r"(\d{1,3}|[一二三四五六七八九十百]{1,8})(?:本|個|つ|点|枚)?(?:だけ|のみ)",
        r"(?:only|just)\s+(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:only|just)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lower if "only" in pattern or "just" in pattern else ddl)
        if not match:
            continue
        value = _parse_count_token(match.group(1))
        if value is not None:
            return min(max(value, 1), 1000)
    return None


def _single_mark_count_from_clause(clause: str) -> int | None:
    lower = clause.lower()
    if re.search(r"\b(one|a|single)\b", lower) or any(marker in clause for marker in ("一つ", "一個", "一点", "一本")):
        return 1
    return count_hint_from_ddl(clause)
