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

from inku_server import counts
from inku_server.counts import (
    _DEFAULT_COUNT_LANG,
    _explicit_counts_from_ddl,
    _numeral_is_a_bare_count,
    count_hint_from_ddl,
)
from inku_server.layer_versions import DDL_ENGINE_VERSION

SERVER_ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = SERVER_ROOT / "scripts" / "gen_ddl_reference.py"
MANIFEST_PATH = SERVER_ROOT / "reference" / f"ddl-engine-{DDL_ENGINE_VERSION}" / "manifest.json"


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
