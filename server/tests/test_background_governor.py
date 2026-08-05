"""Acceptance for 契約 background-color-openness (2026-08-02).

Why this file exists: the frozen corpora do not traverse this layer. Measured
before the contract was issued -- `ddl-engine-4` reproduces 33/33 digests while
BOTH perturbations of this change move 0 of the 33 cases, and `render-engine-20`
has 520/525 white backgrounds. CI staying green there is evidence that nobody
looks at the background governor, not evidence that it is correct. The gate for
this contract has to be built here.

Everything below goes through `coerce_score`, the entry point. Calling
`_with_background_dominance_governor` or `_has_explicit_background_intent`
directly bypasses the caller's gate and over-reports (see the 44%-vs-0% incident
recorded in gate_bypass_measurement_error).
"""

from __future__ import annotations

import json
import pathlib

import pytest

from inku_server.coerce import coerce_score
from inku_server.composer import SYSTEM_PROMPT, SYSTEM_PROMPT_EN
from inku_server.interpreter import _build_system_prompt
from inku_server.schema import Score

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES_PATH = pathlib.Path(__file__).resolve().parent / "data" / "background-governor-cases.json"

# 72 production works replayed from the pentala DB (build >= 800), 23 of which
# lost the background colour the DDL asked for. The original descriptions are
# the author's own works, so they were replaced with marker-equivalent synthetic
# text; the fixture reproduces the production baseline of 1/23 and 49/49 exactly.
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
LOST = [case for case in CASES if case["group"] == "lost"]
REACHED = [case for case in CASES if case["group"] == "reached"]


def _coerce_context(ddl: str, original_description: str | None) -> str:
    """Mirror of render.py:_coerce_context -- the production context string."""
    original = (original_description or "").strip()
    normalized = (ddl or "").strip()
    if original and original != normalized:
        return f"{original}\n{normalized}"
    return normalized


def _replay(case: dict) -> str:
    payload = dict(case["score"])
    payload["background"] = case["asked"]  # hand the requested colour back
    score = coerce_score(
        Score.model_validate(payload),
        ddl=_coerce_context(case["stage2_input"], case.get("source_text")),
    )
    return score.background


def _score_with_background(background: str) -> Score:
    return Score.model_validate(
        {
            "background": background,
            "instructions": [
                {"primitive": "circle", "color": "white", "center": [0.5, 0.5], "radius": 0.1}
            ],
        }
    )


def test_fixture_is_the_measured_population() -> None:
    """Guard the arithmetic the two gates below depend on."""
    assert len(CASES) == 72
    assert len(LOST) == 23
    assert len(REACHED) == 49


# --------------------------------------------------------------------------- #
# T-1                                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", LOST, ids=[c["id"] for c in LOST])
def test_t1_lost_works_keep_the_requested_background(case: dict) -> None:
    """The 23 production losses keep the colour their DDL asked for.

    Baseline before the fix: 1 / 23 (22 turned white by the dominance governor,
    which read only the scenery words of the original description and never the
    "背景を黒で埋める" clause the description itself wrote).
    """
    assert _replay(case) == case["asked"]


# --------------------------------------------------------------------------- #
# T-2                                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", REACHED, ids=[c["id"] for c in REACHED])
def test_t2_reached_works_are_unchanged(case: dict) -> None:
    """Control. Without this, "always keep the background" would pass T-1."""
    assert _replay(case) == case["got"] == case["asked"]


# --------------------------------------------------------------------------- #
# T-3 -- characterization, not a property                                      #
# --------------------------------------------------------------------------- #


def test_t3_bare_background_marker_still_escapes_the_governor() -> None:
    """Pin today's marker behaviour so widening it later turns red.

    EXPLICIT_SURFACE_MARKERS contains the bare word 背景, so an original
    description that merely mentions the background is already treated as
    explicit intent -- no fill clause required. That escape hatch is wider than
    the governor's stated purpose, and the contract for this change deliberately
    left it alone (作者裁定 2026-08-02: removing it changes the governor's
    behaviour and belongs to a separate decision). This test exists so that a
    later edit to EXPLICIT_SURFACE_MARKERS shows up as a failure here instead of
    silently widening the hatch.
    """
    ddl = _coerce_context("黒い線を一本引く。", "背景に静かな気配。")
    assert coerce_score(_score_with_background("black"), ddl=ddl).background == "black"


def test_t3_no_marker_and_no_clause_is_still_governed() -> None:
    """The control for the case above: the governor is not vacuous."""
    ddl = _coerce_context("黒い線を一本引く。", "静かな気配。")
    assert coerce_score(_score_with_background("black"), ddl=ddl).background == "white"


def test_t3_explicit_clause_alone_survives_without_any_marker() -> None:
    """The clause added by this contract, isolated from the marker path.

    Same governing context as the test above -- the only difference is that the
    normalized DDL carries the fill clause. This is the 22-work mechanism in
    miniature.
    """
    ddl = _coerce_context("背景を黒で埋める。黒い線を一本引く。", "静かな気配。")
    assert coerce_score(_score_with_background("black"), ddl=ddl).background == "black"


def test_t3_english_clause_survives_without_any_marker() -> None:
    ddl = _coerce_context("Fill background with black. Draw one black line.", "A quiet presence.")
    assert coerce_score(_score_with_background("black"), ddl=ddl).background == "black"


# --------------------------------------------------------------------------- #
# T-5 -- the prompts no longer restrict the background colour set              #
# --------------------------------------------------------------------------- #

WEB_DDL_SPEC = ROOT / "android/app/src/main/java/app/inku/mobile/pipeline/WebDdlSpec.kt"

# `android/` is permanently excluded from every pentala sync path (standing rule
# 2026-07-30), so on the deployed server the whole tree is absent and reading the
# Kotlin file raised FileNotFoundError in 15 T-5 cases. Key the skip to the
# DIRECTORY, not the file: wherever `android/` exists -- every checkout, every
# developer machine, CI -- the assertions below still run, and a moved or renamed
# WebDdlSpec.kt is still a failure rather than a skip.
ANDROID_TREE = ROOT / "android"
android_only = pytest.mark.skipif(
    not ANDROID_TREE.is_dir(),
    reason="android/ is never synced to the server; the Kotlin prompts are checked where the tree exists",
)

# Every phrasing that pinned the background to five colours or named gray as
# forbidden, across ja and en, stage 1 and stage 2, server and Android. Asserting
# only on the five-colour set is not enough: WebDdlSpec.kt's LiteRT stage 1
# prompt said 灰背景は禁止 without listing five colours, so a set-only assertion
# stays green while that line survives.
FIVE_COLOUR_SETS = (
    "白・黒・青・赤・緑",
    "white/black/blue/red/green",
    "black/red/blue/green",
    "black, red, blue, or green",
    "黒・赤・青・緑",
)

GRAY_PROHIBITIONS = (
    'background="gray" を使ってはいけない',
    'Do not use background="gray"',
    "「背景を灰で埋める」を出力してはいけない",
    'Do not output "Fill background with gray"',
    "gray背景は禁止",
    "灰背景は禁止",
    "灰色は背景ではなく",
    "not as the background",
    "Use gray only as a foreground",
)


def _server_prompt_sources() -> dict[str, str]:
    return {
        "composer.SYSTEM_PROMPT": SYSTEM_PROMPT,
        "composer.SYSTEM_PROMPT_EN": SYSTEM_PROMPT_EN,
        "interpreter ja": _build_system_prompt("白い背景に白い線を引く"),
        "interpreter en": _build_system_prompt("white lines on a white background", lang="en"),
    }


def _web_ddl_spec_text() -> str:
    # Read as text: the Kotlin constants are the Android copies of the same
    # prompts, and editing only the Python side must turn the Android pair red.
    return WEB_DDL_SPEC.read_text(encoding="utf-8").replace('\\"', '"')


@pytest.mark.parametrize("phrase", FIVE_COLOUR_SETS)
def test_t5_no_server_prompt_limits_the_background_to_five_colours(phrase: str) -> None:
    offenders = [name for name, text in _server_prompt_sources().items() if phrase in text]
    assert offenders == [], f"{phrase!r} still restricts: {offenders}"


@pytest.mark.parametrize("phrase", GRAY_PROHIBITIONS)
def test_t5_no_server_prompt_forbids_a_gray_background(phrase: str) -> None:
    offenders = [name for name, text in _server_prompt_sources().items() if phrase in text]
    assert offenders == [], f"{phrase!r} still forbids gray: {offenders}"


@android_only
@pytest.mark.parametrize("phrase", FIVE_COLOUR_SETS + GRAY_PROHIBITIONS)
def test_t5_web_ddl_spec_carries_no_background_restriction(phrase: str) -> None:
    """The Android half of T-5, kept in its own test so it can skip on the server.

    Folding the Kotlin text into the server helper made all 15 T-5 cases raise
    FileNotFoundError on pentala, where `android/` does not exist.
    """
    assert phrase not in _web_ddl_spec_text(), f"{phrase!r} still restricts WebDdlSpec.kt"


@android_only
def test_t5_web_ddl_spec_is_where_we_think_it_is() -> None:
    """Without this, a moved or renamed Kotlin file makes T-5 pass on nothing."""
    assert WEB_DDL_SPEC.is_file()
    text = WEB_DDL_SPEC.read_text(encoding="utf-8")
    for const in (
        "STAGE1_PROMPT_PREFIX_JA",
        "STAGE1_PROMPT_PREFIX_EN",
        "STAGE2_SYSTEM_PROMPT_JA",
        "STAGE2_SYSTEM_PROMPT_EN",
        "STAGE2_SYSTEM_PROMPT_JA_LITERT",
        "STAGE1_PROMPT_PREFIX_JA_LITERT",
    ):
        assert const in text


# --------------------------------------------------------------------------- #
# T-7 -- stage 5 (I-104): gray leaves coerce_score gray                        #
# --------------------------------------------------------------------------- #


def test_t7_a_gray_background_survives_coerce() -> None:
    """The fourth block on the colour, found after stages 1-3 were already in.

    Stages 2 and 3 were measured working on pentala at Build 834 (0 -> 20 stage-1
    clauses, 0 -> 19 stage-2 `background="gray"`), and all 19 still came out
    white: `coerce_score` called `_visible_background` at the entry, ahead of the
    governor, and it rewrote gray unconditionally. Stage 5 removed it
    (作者裁定 2026-08-02, option A of I-104).

    The context here carries a density marker and no fill clause -- the exact
    shape that governs black to white in the T-3 control above -- so this also
    pins that gray is outside the governor's set rather than merely escaping it.
    """
    ddl = _coerce_context("灰色の線を一本引く。", "静かな気配。")
    assert coerce_score(_score_with_background("gray"), ddl=ddl).background == "gray"
    assert coerce_score(_score_with_background("black"), ddl=ddl).background == "white"


def test_t7_gray_on_gray_stays_legible_without_moving_the_background() -> None:
    """"Keep the background" must not be bought by dropping the foreground rule.

    The visibility of gray on gray was carried by two mechanisms; only the
    background-side one was removed. This asserts the foreground-side one still
    fires on its own.
    """
    score = Score.model_validate(
        {
            "background": "gray",
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": "gray"}
            ],
        }
    )

    fixed = coerce_score(score)

    assert fixed.background == "gray"
    assert fixed.instructions[0].color == "black"
    assert "made visible" in (fixed.instructions[0].note or "")
