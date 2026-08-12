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


def count_hint_from_ddl(
    ddl: str, limits: Limits = DEFAULT_LIMITS, *, lang: str | None = None
) -> int | None:
    """Extract a conservative count hint from a normalized DDL fragment."""
    literal_grid = _is_literal_grid_request(ddl)
    clauses = re.split(r"[。.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    pattern = r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)"
    for candidate in candidates:
        match = re.search(pattern, candidate)
        if not match:
            continue
        if _names_an_axis_ja(candidate, match.end()):
            continue
        value = _parse_small_japanese_number(match.group(1))
        if value is not None:
            maximum = limits.ddl_count_max_grid if literal_grid else limits.ddl_count_max
            return min(max(value, 1), maximum)
    return _english_count_hint(ddl, limits, lang=lang)


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


def _english_count_hint(
    ddl: str, limits: Limits = DEFAULT_LIMITS, *, lang: str | None = None
) -> int | None:
    """The count this description states first, once the counter pass found none.

    Ruling B ([I-212], 2026-08-12): this reader and `_explicit_counts_from_ddl`
    answer "how many did the description say" the same way, because they are now
    the same scan.  They disagreed on four of six descriptions while this one
    kept a walk of its own: it dropped numerals on the floor (`re.findall` over
    `[a-z]+` alone) and demanded one of twelve counted nouns within nine words,
    so `Draw 12 circles.` and `Scatter twelve small ellipses.` read as nothing at
    all.  Both narrownesses are gone with the walk that held them.
    """
    literal_grid = _is_literal_grid_request(ddl)
    # Split the way `count_hint_from_ddl` splits. Two answers to "which clause is
    # the tiling request" is the same defect as two answers to "how many": with
    # `[.!?]+` alone a Japanese description is one clause, and this fallback then
    # read a count from a sentence that asked for no tiling at all.
    clauses = re.split(r"[。.!?]+", ddl)
    candidates = [clause for clause in clauses if _is_literal_grid_request(clause)] if literal_grid else [ddl]
    maximum = limits.ddl_count_max_grid if literal_grid else limits.ddl_count_max
    for candidate in candidates:
        for _, value in _counts_in_reading_order(candidate, lang=lang):
            return min(max(value, 1), maximum)
    return None


def _parse_count_token(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    if token in ENGLISH_SMALL_NUMBERS:
        return ENGLISH_SMALL_NUMBERS[token]
    return _parse_small_japanese_number(token)


JAPANESE_COUNT_PATTERN = re.compile(r"(\d{1,4}|[一二三四五六七八九十百千]{1,8})(?:本|個|つ(?!の方向)|点|枚)")

# Ruling B ([I-204], 2026-08-11): the English path reads numerals as well as number
# words, and asks nothing of the noun that follows.  The Japanese path never asked
# for a noun; a table of 32 counted objects on one side only is why `Draw 12
# circles.` and `Draw twelve petals.` both went unread.  The table is gone -- it had
# no other reader.
_COUNT_TOKEN_PATTERN = re.compile(r"[a-z]+|\d+")
_CJK_PATTERN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_CJK_WINDOW = 12
_NUMBER_EXPRESSION_PUNCTUATION = ".,/:"

# Ruling (2026-08-12): a number is a count of marks only if what it counts is a
# thing that gets drawn.  The old guard had this the wrong way round -- it listed
# what MAY be counted (32 words, then 12), and the set of drawable things is open,
# so `circles`, `ellipses` and `petals` leaked out of it and went unread.  This
# lists what may NOT be: words naming an axis or a dimension rather than an
# object.  That set is closed and small, which is the whole reason it can be
# written down.
#
# It is the same judgement `_numeral_is_a_bare_count` already makes about `0.11`
# and `1/3` -- "this digit belongs to another kind of quantity" -- with the
# quantity marked by a word instead of by punctuation.  `四つの方向` was the one
# case of it the tree already held, written into the counter pattern itself; both
# languages now read it off one table, so `four directions` and `四つの方向`
# answer the same way.
#
# Reading the four in `four directions` as a mark count does not deliver more of
# the description, it delivers less: the number is taken off the thing it
# qualifies, and `across the wall` -- the field coverage the same sentence asks
# for -- is lost with it.
_AXIS_WORDS_EN = frozenset(
    {
        "direction", "directions", "degree", "degrees", "row", "rows",
        "column", "columns", "kind", "kinds", "type", "types",
        "layer", "layers", "percent", "time", "times",
    }
)
_AXIS_WORDS_JA = ("方向", "向き", "種類", "層", "行", "列", "度", "回", "倍", "割")
# How far past the number the noun it qualifies may sit. Three covers a number
# with up to two adjectives (`four different directions`); the old table looked
# nine words ahead, which is far enough to catch a noun belonging to something
# else entirely.
_AXIS_LOOKAHEAD = 3

# The same ruling, applied to the word before the number instead of after it. An
# index says WHICH ONE, not HOW MANY. This matters because the DDL coerce reads
# is the one the plugin layer has already expanded, and that layer writes its own
# `Place member 2 in region [...] with rotation 21 degrees.` into it -- machine
# text the reader was taking for a count the author stated.
_INDEX_WORDS_EN = frozenset({"member", "no"})
_INDEX_WORDS_JA = ("第",)


def _names_an_axis_ja(text: str, end: int) -> bool:
    """Does an axis word follow this counter, as in `四つの方向`?"""
    rest = text[end:]
    if rest.startswith("の"):
        rest = rest[1:]
    return rest.startswith(_AXIS_WORDS_JA)


def _names_an_axis_en(tokens: list[tuple[str, int, int]], after: int) -> bool:
    """Does an axis word follow this number, as in `four directions`?"""
    return any(
        token in _AXIS_WORDS_EN for token, _, _ in tokens[after : after + _AXIS_LOOKAHEAD]
    )


def _is_an_index_en(tokens: list[tuple[str, int, int]], at: int) -> bool:
    """Is this number an index, as in `member 2`?"""
    return at > 0 and tokens[at - 1][0] in _INDEX_WORDS_EN


def _is_an_index_ja(text: str, start: int) -> bool:
    """Is this number an index, as in `第2`?"""
    return text[:start].endswith(_INDEX_WORDS_JA)

# What a reader falls back to when its caller does not name a language.  Every
# call site that predates the language port resolves here, so opening the port
# moves nothing: `ja` is the language the exclusions below were measured on.
_DEFAULT_COUNT_LANG = "ja"


def _cjk_neighbourhood_is_excluded(lang: str | None) -> bool:
    """Does a numeral with CJK beside it stay unread?

    Ruling B ([I-216], 2026-08-12): what decides this is the language the body is
    written in, not the characters that happen to sit next to the digit.  An
    English body naming a plugin whose word is Japanese placed one unit because
    of the name it referred to.  A Japanese body keeps the exclusion: it writes
    angles, fractions and percentages as bare numerals, and reading those moved
    true and false readings in equal number.
    """
    return (lang or _DEFAULT_COUNT_LANG) != "en"


def _numeral_is_a_bare_count(text: str, start: int, end: int, *, lang: str | None = None) -> bool:
    """Is this digit run a count, or a piece of some other number?

    Two exclusions, both measured on the stored works (2026-08-11):

    - CJK within twelve characters, in a body written in Japanese.  Japanese
      writes angles, fractions and percentages as bare numerals, and reading
      those moved nineteen works with true and false readings in equal number.
      Which language the body is in decides this exclusion, not which characters
      neighbour the digit -- see `_cjk_neighbourhood_is_excluded`.
    - a digit that belongs to a decimal, fraction or ratio (`radius 0.11`,
      `1/3 of the screen`), or carries a percent sign.  Ruling B calls those false
      on the Japanese side, and the digits inside them are no more a count in
      English.  Measured: without this, one work in the fifty-case count corpus
      reads a radius as the counts 0 and 11.
    """
    if _cjk_neighbourhood_is_excluded(lang) and _CJK_PATTERN.search(
        text[max(0, start - _CJK_WINDOW) : end + _CJK_WINDOW]
    ):
        return False
    if start >= 2 and text[start - 1] in _NUMBER_EXPRESSION_PUNCTUATION and text[start - 2].isdigit():
        return False
    if end < len(text):
        if text[end] == "%":
            return False
        if (
            text[end] in _NUMBER_EXPRESSION_PUNCTUATION
            and end + 1 < len(text)
            and text[end + 1].isdigit()
        ):
            return False
    return True

# LITERAL_COUNT_THRESHOLD and REPRESENTED_COUNT_RANGE used to be defined here, a
# second name for the band `..limits` already holds. Both readers now go through
# Limits, so the band exists under one name only.


def _counts_in_reading_order(
    ddl: str | None, *, lang: str | None = None
) -> list[tuple[int, int]]:
    """Every count the description states, as (position, value), in reading order.

    The one scan both readers stand on.  `_explicit_counts_from_ddl` asks it which
    counts were stated at all; `_english_count_hint` asks it which one comes
    first.  Two readers over one scan cannot disagree about what a count is, and
    they did disagree -- on four of six descriptions, measured 2026-08-12 -- for
    as long as the hint kept a walk of its own.

    Counter-marked numbers (`三つ`, `12個`) and bare numbers are gathered in the
    same pass so that "first" means first in the text, not first in whichever
    pass happened to run first.
    """
    if not ddl:
        return []
    # One coordinate system for both passes: `lower()` leaves digits and CJK
    # alone and `replace` keeps the length, so a position means the same thing to
    # the counter pattern and to the token walk.
    text = ddl.lower().replace("-", " ")
    found: list[tuple[int, int]] = []
    for match in JAPANESE_COUNT_PATTERN.finditer(text):
        value = _parse_small_japanese_number(match.group(1))
        if value and not _names_an_axis_ja(text, match.end()):
            found.append((match.start(), value))
    tokens = [(match.group(0), match.start(), match.end()) for match in _COUNT_TOKEN_PATTERN.finditer(text)]
    number_words = set(ENGLISH_COUNT_UNITS) | {"hundred", "thousand", "and"}
    index = 0
    while index < len(tokens):
        token, start, stop = tokens[index]
        if token.isdigit():
            value = int(token)
            if (
                value
                and _numeral_is_a_bare_count(text, start, stop, lang=lang)
                and not _names_an_axis_en(tokens, index + 1)
                and not _is_an_index_en(tokens, index)
                and not _is_an_index_ja(text, start)
            ):
                found.append((start, value))
            index += 1
            continue
        if token not in number_words or token == "and":
            index += 1
            continue
        end = index
        phrase: list[str] = []
        while end < len(tokens) and tokens[end][0] in number_words:
            phrase.append(tokens[end][0])
            end += 1
        total = 0
        current = 0
        for word in phrase:
            if word == "and":
                continue
            if word == "hundred":
                current = max(current, 1) * 100
            elif word == "thousand":
                total += max(current, 1) * 1000
                current = 0
            else:
                current += ENGLISH_COUNT_UNITS[word]
        if total + current and not _names_an_axis_en(tokens, end):
            found.append((start, total + current))
        index = end
    found.sort()
    return found


def _explicit_counts_from_ddl(ddl: str | None, *, lang: str | None = None) -> frozenset[int]:
    """Every count the description states outright, in either language.

    `count_hint_from_ddl` answers "what is the count here" and stops at the first
    match. This answers "which counts were asked for at all", which is what tells a
    group written to order apart from one a governor is free to thin.  Both read
    `_counts_in_reading_order`, so the two answers cannot come from two rules.

    `lang` is the language the body is written in, and only the exclusions consult
    it. A caller that does not know resolves to `_DEFAULT_COUNT_LANG`, which is
    what every caller did before the port was opened.
    """
    return frozenset(value for _, value in _counts_in_reading_order(ddl, lang=lang))


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
