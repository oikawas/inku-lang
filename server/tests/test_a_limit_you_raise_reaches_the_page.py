"""A ceiling you raise reaches the paper, and the one that decides is the setting.

Three numbers that govern how much ink a work may carry were written straight
into the code, past `limits.py`, so they alone ignored the stored setting. The
loudest of them was the default for a tiling with no numeral in it: a bare 400.

Lowering the total ceiling always worked, because `_enforce_hard_ceiling` trims
at the exit and says so. RAISING it did nothing, and said nothing -- 400 was the
ORDER, not the result of a trim, so on the record the work got exactly what it
asked for. An administrator saw a limit go up, the page stay the same, and no
reason anywhere.

Two claims are kept apart here on purpose:

  T-123  at the DEFAULTS the bands return today's values, to the integer
  T-124  when the ceiling MOVES, the amount of ink in one cluster holds

An implementation that froze the bands as constants passes the first and fails
the second; one that scaled them but got the arithmetic wrong fails the first.
Neither number is a restatement of the other.

Every case here is synthetic.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

import inku_server.coerce as coerce_entry
from inku_server.coerce import coerce_score
from inku_server.coerce.normalize import (
    _cluster_count,
    _clustered_visual_count,
    _density_label,
    _with_clustered_density,
)
from inku_server.limits import DEFAULT_LIMITS, Limits, max_cluster_count, using_limits
from inku_server.schema import Instruction, Score

# One of the six markers `_is_literal_grid_request` reads, and no numeral: the
# description states coverage, so the count is the machine's to pick.
TILING_DDL = "細い線を紙一面に敷き詰める"


def _score() -> Score:
    return Score.model_validate(
        {
            "version": "0.1.0",
            "canvas": {"aspect": "square"},
            "background": "white",
            "instructions": [
                {
                    "primitive": "line",
                    "color": "black",
                    "weight": "pen",
                    "from": [0.18, 0.5],
                    "to": [0.82, 0.5],
                    "arrangement": {"count": 12, "layout": "scatter"},
                }
            ],
        }
    )


def _limits(**overrides: int) -> Limits:
    return dataclasses.replace(DEFAULT_LIMITS, **overrides)


def _drawn(limits: Limits) -> int:
    out = coerce_score(_score(), ddl=TILING_DDL, limits=limits)
    grids = [
        ins.arrangement.count
        for ins in out.instructions
        if ins.arrangement is not None and ins.arrangement.layout == "grid"
    ]
    assert len(grids) == 1, f"the tiling should be one grid, got {grids}"
    return grids[0]


# T-121 -- a numberless tiling follows the total ceiling in BOTH directions.
#
# `style_coerce_disabled` is not a stylistic variation here: it selects which of
# the two call sites of `_with_literal_grid_fidelity` runs. Both are exercised,
# so neither can be left on the default argument without a test going red.
@pytest.mark.parametrize("style_coerce_disabled", [False, True])
@pytest.mark.parametrize(
    "max_expanded_primitives,expected",
    [
        (100, 100),  # lowered: worked before this contract too
        (400, 400),  # the default: the picture must not move
        (1200, 1200),  # raised: stayed at 400 before this contract
    ],
)
def test_t121_a_numberless_tiling_follows_the_total_ceiling(
    monkeypatch, style_coerce_disabled: bool, max_expanded_primitives: int, expected: int
):
    if style_coerce_disabled:
        monkeypatch.setenv("INKU_COERCE_DISABLE", "1")
    else:
        monkeypatch.delenv("INKU_COERCE_DISABLE", raising=False)
    assert _drawn(_limits(max_expanded_primitives=max_expanded_primitives)) == expected


# T-122 -- the roll-call. A default argument is not the wiring; it is what hides
# a missing wire. Both call sites must name `limits`, and there must still be
# exactly two, so a third one arriving unwired is red rather than silent.
def test_t122_every_literal_grid_call_site_passes_the_limits():
    source = Path(coerce_entry.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_with_literal_grid_fidelity"
    ]
    assert len(calls) == 2, (
        "coerce has two exits that repair a literal grid -- the style-coercion "
        f"bypass and the main path. Found {len(calls)}; a new one must be wired too."
    )
    for call in calls:
        keywords = {kw.arg for kw in call.keywords}
        assert "limits" in keywords, (
            f"the call at line {call.lineno} leans on the default argument, so "
            "that path keeps the shipping ceiling whatever the setting says"
        )


# The eight inputs both band tests read. They straddle every boundary the
# defaults have: below 120, between 120 and 240, between 240 and 500, and above.
BAND_INPUTS = (120, 180, 240, 300, 500, 600, 1000, 1500)

# What the tree returned before this contract, measured at the defaults on
# c360429b. Frozen here as integers rather than recomputed from the ratios: a
# gate that derives its expectation from the code it checks measures nothing.
TODAYS_CLUSTERS = {120: 5, 180: 5, 240: 7, 300: 7, 500: 9, 600: 9, 1000: 9, 1500: 9}
TODAYS_LABELS = {
    120: "medium",
    180: "high",
    240: "high",
    300: "high",
    500: "high",
    600: "high",
    1000: "high",
    1500: "high",
}


# T-123 -- at the defaults the ratios land on today's integers exactly. This is
# the half that a frozen-constant implementation also passes; T-124 is the half
# that separates them.
@pytest.mark.parametrize("original_count", BAND_INPUTS)
def test_t123_the_bands_are_one_to_one_with_today_at_the_defaults(original_count: int):
    assert _cluster_count(original_count, DEFAULT_LIMITS) == TODAYS_CLUSTERS[original_count]
    assert _density_label(original_count, DEFAULT_LIMITS) == TODAYS_LABELS[original_count]


# The range one cluster's ink actually occupies at the defaults, over the eight
# inputs above: 120 drawn in 5 groups at the top, 120 in 9 at the bottom. The
# look this preserves is that range, not the digits in the bands.
INK_PER_CLUSTER_FLOOR = 13.3
INK_PER_CLUSTER_CEILING = 24.0

MOVED_CEILINGS = {
    # A third of the representation ceiling. Before this contract the ink per
    # cluster fell to 4.4 here: the drawn count followed the setting and the
    # cluster count did not.
    "a third": _limits(represented_count_max=40, represented_count_min=27),
    # Three times it. `literal_count_threshold` has to come along because
    # normalize_limits will not let the band start above where counting stops.
    # Before this contract the ink per cluster rose to 42.9 here.
    "three times": _limits(
        represented_count_max=360, represented_count_min=240, literal_count_threshold=360
    ),
}


def _clustered(original_count: int, limits: Limits) -> tuple[int, int, str]:
    """Ink and clusters as the production path assigns them.

    Read through `_with_clustered_density` rather than off the two band
    functions, because the call site is part of what is being checked: a caller
    that stopped passing `limits` would leave the band functions correct and the
    drawing wrong.

    `using_limits` is not scaffolding either. The clamp on `cluster_count` is one
    of the two readers that cannot take an argument, so a request sets the
    context var from the same resolved limits it passes explicitly. Calling
    without it would measure the coercion under one configuration and the schema
    under another, which is not a state any request is ever in.
    """
    ins = Instruction.model_validate(
        {
            "primitive": "circle",
            "color": "black",
            "weight": "pen",
            "center": [0.5, 0.5],
            "radius": 0.02,
            "arrangement": {"count": original_count, "layout": "scatter"},
        }
    )
    with using_limits(limits):
        out = _with_clustered_density(ins, "probe", limits)
    assert out.arrangement is not None
    return out.arrangement.count, out.arrangement.cluster_count, out.arrangement.density


# T-124 -- move the representation ceiling and the amount of ink in one cluster
# stays inside the range the defaults produce. The drawn count and the cluster
# count are a pair; before this contract only one of them followed the setting.
@pytest.mark.parametrize("which", sorted(MOVED_CEILINGS))
@pytest.mark.parametrize("original_count", BAND_INPUTS)
def test_t124_one_cluster_holds_the_same_ink_when_the_ceiling_moves(
    which: str, original_count: int
):
    limits = MOVED_CEILINGS[which]
    drawn, clusters, _ = _clustered(original_count, limits)
    assert clusters >= 1
    ink = drawn / clusters
    assert INK_PER_CLUSTER_FLOOR <= ink <= INK_PER_CLUSTER_CEILING, (
        f"{which} the ceiling: {original_count} drawn as {drawn} in {clusters} "
        f"clusters is {ink:.1f} per cluster, outside the {INK_PER_CLUSTER_FLOOR}"
        f"-{INK_PER_CLUSTER_CEILING} the defaults hold"
    )


# The same claim for the label, which has no cluster count to divide by: the
# boundary itself has to move with the ceiling. At the defaults 180 marks are
# "high"; with the ceiling tripled the same 180 are not, because they are no
# longer large RELATIVE TO what may be represented. A frozen 180 says "high"
# in both, which is what P-5 puts back.
def test_t124_the_density_label_moves_with_the_ceiling():
    assert _density_label(180, DEFAULT_LIMITS) == "high"
    assert _density_label(180, MOVED_CEILINGS["three times"]) != "high"
    assert _density_label(120, DEFAULT_LIMITS) == "medium"
    assert _density_label(120, MOVED_CEILINGS["a third"]) == "high"


# The upper end of the cluster count is not a constant either. Nine was the most
# a work could ever be split into, and it is what pins the ink per cluster at
# 40+ once the ceiling is raised: the drawn count grows and the divisor cannot.
def test_t124_the_cluster_count_passes_nine_when_the_ceiling_is_raised():
    tripled = MOVED_CEILINGS["three times"]
    assert max(_cluster_count(count, tripled) for count in BAND_INPUTS) > 9
    # And the defaults are untouched by that headroom.
    assert max(_cluster_count(count, DEFAULT_LIMITS) for count in BAND_INPUTS) == 9

    # Nine was not the real stop: `Arrangement.cluster_count` carried a static
    # le=12, and a value coerce computed above it made the whole Score invalid.
    # That bound follows the setting now, and at the defaults it is still the
    # same 12 the field used to spell out.
    assert max_cluster_count(DEFAULT_LIMITS) == 12
    assert max_cluster_count(tripled) == 36
    assert max_cluster_count(MOVED_CEILINGS["a third"]) == 4


# The drawn count was already a setting before this contract. Stated here so the
# pair T-124 measures is visible: it is this half that moved and the cluster
# count that did not.
def test_t124_reverse_the_drawn_count_already_followed_the_ceiling():
    assert _clustered_visual_count(1000, DEFAULT_LIMITS) == 120
    assert _clustered_visual_count(1000, MOVED_CEILINGS["a third"]) == 40
    assert _clustered_visual_count(1000, MOVED_CEILINGS["three times"]) == 360
