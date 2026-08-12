"""Every reader counts the same way ([I-212] .. [I-216], 2026-08-12).

The rule that decides whether a number written in a description is a *count* used
to live in four places at once.  `Draw 12 circles.` was twelve to one reader and
nothing to the other; Japanese read a number only when a counter followed it; a
count that sat outside the phrase naming a plugin went unread; and a plugin whose
word is Japanese turned off numeral reading in an English body.

These tests measure the one rule the five rulings collapse into.  Where two
readers are supposed to agree, the test compares the two readers -- not a table
of expected values written by hand, which would stay green from the day the rule
next moves and freeze the drift in place.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re

from inku_server import counts
from inku_server.counts import (
    _DEFAULT_COUNT_LANG,
    _explicit_counts_from_ddl,
    _is_literal_grid_request,
    _numeral_is_a_bare_count,
    count_hint_from_ddl,
)
from inku_server.layer_versions import DDL_ENGINE_VERSION
from inku_server.plugins.document_format import expand_plugin_ddl, parse_plugin_document

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"
MANIFEST_PATH = SERVER_ROOT / "reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json"
# The shipped plugin, the one the frozen corpus expands. Its `Nature.青葉` is the
# Japanese name that was switching numeral reading off in an English body.
NATURE_PLUGIN = SERVER_ROOT / "plugins" / "nature-leaves.inku-plugin.md"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_ddl_reference_ports", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Descriptions that exercise both exclusions in both languages.  Used wherever a
# test needs "a set of inputs" rather than one hand-picked string.
SAMPLE_DESCRIPTIONS = (
    "Draw 12 circles.",
    "Draw twelve circles.",
    "Draw 12 lines.",
    "Draw twelve lines.",
    "Scatter twelve small ellipses.",
    "Place a circle of radius 0.11 near the center.",
    "円を12個描く。",
    "立方体の向き: 30度回転",
    "画面下1/3に線を引く。",
    "緑の下草を50散らす。",
    "A1-1 の入力に対する",
    "Place 12 Nature.青葉 marks.",
)


# --- T-1 ------------------------------------------------------------------
# Stage 1 opens a port and wires nothing to it.  Parts A and B of the frozen
# corpus are the measurement of that claim, and they keep measuring it after the
# later stages: no case in either part states a count the widened rule reads.
# Part C is excluded on purpose -- ruling [I-216] B moves
# `C-plugin-count-as-a-numeral-beside-cjk`, and the receiving session bakes it.


def test_t1_the_expand_and_coerce_corpora_are_byte_identical() -> None:
    frozen = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["cases"]
    cases, _ = _generator()._render_cases()
    moved = [
        case_id
        for case_id, case in sorted(cases.items())
        if case["part"] in ("a_expand", "b_coerce")
        and case["digest"] != frozen[case_id]["digest"]
    ]
    assert moved == []


# --- T-2, T-3 -------------------------------------------------------------
# The port's default is today's behaviour.  Both tests compare the unnamed call
# against the named one rather than against a frozen table of answers: the
# answers themselves move in stages 3 to 6, but "unnamed means `ja`" does not.


def test_t2_naming_no_language_reads_the_way_the_default_language_reads() -> None:
    assert _DEFAULT_COUNT_LANG == "ja"
    for ddl in SAMPLE_DESCRIPTIONS:
        assert _explicit_counts_from_ddl(ddl) == _explicit_counts_from_ddl(
            ddl, lang=_DEFAULT_COUNT_LANG
        ), ddl
        assert count_hint_from_ddl(ddl) == count_hint_from_ddl(ddl, lang=_DEFAULT_COUNT_LANG), ddl


def test_t3_a_japanese_body_still_leaves_a_numeral_beside_cjk_unread() -> None:
    """The exclusion the stored works were measured on, still in force for `ja`.

    The second half of each pair is what makes this test see a flipped default:
    an unnamed call has to answer the same way a `ja` call does.
    """
    angle = "立方体の向き: 30度回転"
    assert _explicit_counts_from_ddl(angle, lang="ja") == frozenset()
    assert _explicit_counts_from_ddl(angle) == frozenset()

    for probe in ("緑の下草を50散らす。", "A1-1 の入力に対する", "画面下1/3に線を引く。"):
        assert _explicit_counts_from_ddl(probe, lang="ja") == frozenset(), probe
        assert _explicit_counts_from_ddl(probe) == frozenset(), probe

    # The same claim one level down, where the exclusion is written.
    text = "立方体の向き: 30度回転"
    start = text.index("30")
    assert not _numeral_is_a_bare_count(text, start, start + 2, lang="ja")
    assert not _numeral_is_a_bare_count(text, start, start + 2)
    assert counts._cjk_neighbourhood_is_excluded("ja")
    assert counts._cjk_neighbourhood_is_excluded(None)


# --- T-4 ------------------------------------------------------------------


def test_t4_every_caller_of_coerce_score_hands_it_a_language() -> None:
    """A roll call, because a sender that stays silent still answers 200.

    Nothing downstream fails when the language is left out; the route just keeps
    deciding counts by the other language's rules. So the check is on the senders
    themselves, and it counts them: a sixth call site added without a language is
    the same defect as one of these five losing it.
    """
    senders: list[tuple[str, int, bool]] = []
    for path in sorted((SERVER_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name != "coerce_score":
                continue
            keywords = {keyword.arg for keyword in node.keywords}
            senders.append((str(path.relative_to(SERVER_ROOT)), node.lineno, "lang" in keywords))

    silent = [(path, line) for path, line, has_lang in senders if not has_lang]
    assert silent == [], f"call sites of coerce_score that name no language: {silent}"
    assert len(senders) == 5, f"expected five senders, found {sorted(senders)}"


# --- T-5 to T-8 -----------------------------------------------------------


def test_t5_the_two_readers_make_the_same_judgement() -> None:
    """Compare the two readers, not either one against a table written by hand.

    A table would go on passing from the day the rule next moves, and freeze the
    drift it was written to catch.  What is being measured is that "how many did
    the description say" has one answer: whatever the hint names, the set of
    stated counts has to contain.
    """
    for ddl in SAMPLE_DESCRIPTIONS:
        for lang in (None, "ja", "en"):
            stated = _explicit_counts_from_ddl(ddl, lang=lang)
            hint = count_hint_from_ddl(ddl, lang=lang)
            if hint is not None:
                assert hint in stated, (ddl, lang, hint, sorted(stated))
            # Outside a literal-grid request the two also agree on *whether* a
            # count was stated. A grid request narrows the hint to the clauses
            # that ask for tiling, so there the hint may stay silent about a
            # count stated elsewhere in the description.
            if not _is_literal_grid_request(ddl):
                assert (hint is None) == (not stated), (ddl, lang, hint, sorted(stated))


def test_t6_the_english_path_reads_a_numeral_and_asks_for_no_particular_noun() -> None:
    """The two narrownesses [I-212] B removed, one description each."""
    assert count_hint_from_ddl("Draw 12 circles.") == 12  # a numeral, and no listed noun
    assert count_hint_from_ddl("Draw 12 lines.") == 12  # a numeral beside a listed noun
    assert count_hint_from_ddl("Scatter twelve small ellipses.") == 12  # no listed noun


def test_t7_what_was_already_read_is_still_read() -> None:
    assert count_hint_from_ddl("Draw twelve lines.") == 12
    assert count_hint_from_ddl("円を12個描く。") == 12
    assert _explicit_counts_from_ddl("Draw twelve lines.") == frozenset({12})
    assert _explicit_counts_from_ddl("円を12個描く。") == frozenset({12})


def test_t8_a_digit_inside_another_number_is_still_not_a_count() -> None:
    """Ruling A of [I-214] keeps these out, and widening the reader does not.

    Both are read as an English body on purpose: with `ja` the CJK exclusion
    would answer first, and this test would stop measuring the exclusion it is
    named for.
    """
    radius = "Place a circle of radius 0.11 near the center."
    assert _explicit_counts_from_ddl(radius, lang="en") == frozenset()
    assert count_hint_from_ddl(radius, lang="en") is None

    fraction = "Draw lines across the 画面下1/3 band."
    stated = _explicit_counts_from_ddl(fraction, lang="en")
    assert 1 not in stated and 3 not in stated, sorted(stated)


# --- T-23, T-24 -----------------------------------------------------------
# Added by the author's ruling of 2026-08-12, mid-contract: dropping the noun
# table let `four directions` read as four marks, which took the four off the
# thing it qualifies and lost the field coverage the same sentence asks for.
# What replaced the table is its inverse -- a closed list of words naming an axis
# rather than an object.


def test_t23_a_number_that_counts_an_axis_is_not_a_count_of_marks() -> None:
    """And both languages answer the same way, which is the point of the table.

    Before the ruling the English side read every one of these and the Japanese
    side read none: Japanese requires a counter, and `度` `行` `列` `種類` `層`
    are not counters, so it never needed a list.
    """
    pairs = (
        ("Tile thin black lines in four directions across the wall.", "黒い線を四つの方向で敷き詰める。"),
        ("Draw black lines in a grid of three rows and four columns.", "黒い線を三行四列の格子に並べる。"),
        ("Rotate the cube 30 degrees.", "立方体を30度回転する。"),
        ("Use three kinds of gray.", "灰を三種類使う。"),
        ("Draw lines in two layers.", "線を二層に描く。"),
    )
    for english, japanese in pairs:
        assert _explicit_counts_from_ddl(english, lang="en") == frozenset(), english
        assert count_hint_from_ddl(english, lang="en") is None, english
        assert _explicit_counts_from_ddl(japanese, lang="ja") == frozenset(), japanese
        assert count_hint_from_ddl(japanese, lang="ja") is None, japanese

    # The control: the exclusion takes the axis word's number and leaves the
    # mark's. Both numbers sit in one sentence, so a table that swallowed the
    # sentence would fail here.
    both = "Draw 12 lines in four directions."
    assert _explicit_counts_from_ddl(both, lang="en") == frozenset({12})
    assert count_hint_from_ddl(both, lang="en") == 12


def test_t24_an_index_is_which_one_not_how_many() -> None:
    """The DDL coerce reads is post-expansion, and the expander writes indices.

    `Place member 2 in region [...] with rotation 21 degrees.` is written by the
    plugin layer, not by the author. Reading its `2` as a stated count made
    `with_stated_count_fidelity` build a group of two out of a member's number.
    """
    expanded = "Place member 2 in region [0.165, 0.168, 0.285, 0.288] with rotation 21 degrees."
    assert _explicit_counts_from_ddl(expanded, lang="en") == frozenset()
    assert _explicit_counts_from_ddl("第2の線を引く。", lang="ja") == frozenset()

    # The control: the same digit, counting marks instead of naming one.
    assert _explicit_counts_from_ddl("Place 2 marks.", lang="en") == frozenset({2})


# --- T-9, T-10 ------------------------------------------------------------


def _units_placed(ddl: str, *, lang: str) -> list[int]:
    """How many whole units the expansion layer placed, per plugin fired."""
    document = parse_plugin_document(NATURE_PLUGIN.read_text(encoding="utf-8"))
    result = expand_plugin_ddl(
        ddl, source_text=ddl, lang=lang, documents=[document], seed_text="reference"
    )
    return [int(entry["units"]) for entry in result.provenance if "units" in entry]


def test_t9_an_english_body_reads_a_numeral_beside_a_japanese_plugin_name() -> None:
    """The CJK the reader saw was the plugin's own name.

    `Place 12 Nature.青葉 marks.` placed one unit while `Place twelve Nature.青葉
    marks.` placed twelve -- the same description, differing only in how the
    number was written.
    """
    assert _units_placed("Place 12 Nature.青葉 marks.", lang="en") == [12]
    # The number word was never blocked, and must not move.
    assert _units_placed("Place twelve Nature.青葉 marks.", lang="en") == [12]


def test_t10_a_japanese_body_still_leaves_a_bare_numeral_unread() -> None:
    """The other side of stage 4: `ja` keeps the exclusion `en` gives up.

    The probe is a bare numeral rather than a counter phrase on purpose. A
    counter phrase like `四つの方向` is held out by the axis table as well, and a
    case two exclusions both cover cannot measure either one.
    """
    assert _explicit_counts_from_ddl("立方体の向き: 30度回転", lang="ja") == frozenset()
    assert _explicit_counts_from_ddl("立方体の向き: 30度回転", lang="en") == frozenset({30})


# --- T-11 to T-13 ---------------------------------------------------------


def _expansion(ddl: str, *, lang: str):
    document = parse_plugin_document(NATURE_PLUGIN.read_text(encoding="utf-8"))
    return expand_plugin_ddl(
        ddl, source_text=ddl, lang=lang, documents=[document], seed_text="reference"
    )


def _requested_over_budget(result) -> list[int]:
    """The counts the layer read but had no room for.

    The warning names the count it declined, so a description whose count cannot
    fit still says whether the count was read at all. Without this, a count that
    reached the layer and a count that never did look identical: both leave
    `units` at one.
    """
    return [int(match) for warning in result.warnings for match in re.findall(r": (\d+) units", warning)]


def test_t11_a_count_outside_the_naming_phrase_reaches_the_expansion() -> None:
    """The phrase names the plugin, a later phrase states how many.

    Two halves, because the work budget is a separate rule: the first shows the
    count is read, the second shows the units are placed when there is room for
    them. `Nature.枯草` costs fourteen marks a unit, so thirty of it is 420
    against a 400-mark work, and the layer declines the whole count by a rule
    that predates this contract.
    """
    outside = "Nature.枯草の細い鉛筆の縦線を、画面下半分に三十本、不揃いに並べる。"
    read = _expansion(outside, lang="ja")
    assert [int(entry["units"]) for entry in read.provenance] == [1]
    assert _requested_over_budget(read) == [30]

    affordable = "Nature.枯葉の小さな影を、画面下半分に三十個、不揃いに並べる。"
    placed = _expansion(affordable, lang="ja")
    assert [int(entry["units"]) for entry in placed.provenance] == [30]
    assert placed.warnings == ()


def test_t12_a_count_the_phrase_states_is_not_overruled_by_the_sentence() -> None:
    """The control for T-11: widening happens on silence, never on a spoken count.

    Two plugins, two counts, one description. Read at sentence granularity both
    would see both counts and the ambiguity rule would drop each to one unit.
    """
    both = (
        "Nature.枯草の細い縦線を下半分に百二十本並べる。"
        "Nature.落葉の小さな楕円を右下にひとつ置く。"
    )
    result = _expansion(both, lang="ja")
    # 枯草 keeps its own 120 -- over budget, so declined whole, but read as 120.
    assert _requested_over_budget(result) == [120]
    # 落葉 keeps its one, and does not pick up 枯草's count from the sentence.
    assert [int(entry["units"]) for entry in result.provenance] == [1, 1]


def test_t13_a_sentence_stating_two_counts_stays_at_one_unit() -> None:
    """The existing ambiguity rule, still in force at the widened scope.

    Choosing between the two would place a number nobody wrote.
    """
    ambiguous = "Nature.枯葉の小さな影を、三十個と十個に分けて並べる。"
    result = _expansion(ambiguous, lang="ja")
    assert [int(entry["units"]) for entry in result.provenance] == [1]
    assert result.warnings == ()
