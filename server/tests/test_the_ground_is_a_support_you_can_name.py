"""Acceptance for the seven supports a work can be made on.

Contract `the-ground-is-a-support-you-can-name`. The ground field already held
six values before this, but only three of them ever arrived and the picture
barely changed for any of them: Stage 1 rewrote 和紙 as 紙, `charcoal_ground`
appeared in neither prompt, and the renderer told the supports apart by nothing
more than the shape of a noise filter. Production carried 0 works on washi out
of 3,086 and 0 on a charcoal ground.

What is here is what a deterministic layer decides: the table, the category, and
the drawing. Whether a model asked for washi actually writes `washi` is measured
by running the pipeline and reported as a reach rate, not asserted here -- an
acceptance placed on an LLM is a coin toss with a green light on it (I-234).
"""

from __future__ import annotations

import hashlib
import re
from typing import get_args

import pytest

from inku_server import saijiki
from inku_server.renderer import GROUND_BYTE_BUDGET, SVG_PROFILES, render
from inku_server.schema import GroundMaterial, Score

# The supports that draw something. `plain` is the absence of a ground, so it is
# read out of the product's own enum rather than listed by hand here -- a
# hand-copied list stays green from the day the enum moves.
SUPPORTS = tuple(value for value in get_args(GroundMaterial) if value != "plain")

_GROUND_GROUP = re.compile(r'<g id="layer_01_canvas_ground".*?</g>', re.S)
_PATTERN = re.compile(r'<pattern id="gp\d+".*?</pattern>', re.S)
_GRADIENT = re.compile(
    r'<(?:linear|radial)Gradient id="gg\d+".*?</(?:linear|radial)Gradient>', re.S
)


# One seed for every support, used where the claim is about the drawing.
#
# ⚠ `_texture_seed` hashes the ground spec, and the material is part of it, so
# two supports get different grain positions even when they run the exact same
# code. Left derived, a check that "the seven differ" passes with all seven
# drawn by one builder -- measured 2026-08-14, when swapping `drawing_paper` to
# the paper builder reddened nothing at all. `test_ground_seed.py` had already
# written this warning down for a narrower case.
_PINNED_SEED = 13579


def _score(material: str, *, seed: int | None = None) -> Score:
    ground: dict = {"material": material}
    if seed is not None:
        ground["seed"] = seed
    return Score.model_validate(
        {
            "canvas": {"aspect": "square", "ground": ground},
            "instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}],
        }
    )


def _ground_layer(svg: str) -> str:
    """Everything the ground puts in the file: the group and its definitions.

    Measured together because a pattern is two halves -- a definition in
    `<defs>` and a rectangle that fills with it -- and counting only one half
    would report a cost the file does not have.
    """
    group = _GROUND_GROUP.search(svg)
    return (
        (group.group(0) if group else "")
        + "".join(_PATTERN.findall(svg))
        + "".join(_GRADIENT.findall(svg))
    )


# --- T-1: the table ---------------------------------------------------------


def test_ground_material_lists_eight_supports() -> None:
    """T-1. Eight values: the seven supports plus the absence of one."""
    values = get_args(GroundMaterial)
    assert len(values) == 8
    assert "canvas" in values
    assert "drawing_paper" in values
    # `canvas.ground.material="canvas"` nests the word inside itself and reads
    # oddly, and it is still the value: canvas is the only general word for the
    # thing (author's ruling, 2026-08-14).
    assert values[0] == "plain"


# --- T-2: the category ------------------------------------------------------


def test_the_ji_category_carries_exactly_the_ground_materials() -> None:
    """T-2. The saijiki says exactly what the enum offers, minus `plain`.

    Both sides are read from the product at run time. A test that listed the
    seven words itself would go on passing the day after the enum moved, and
    what it guarded would be the drift.
    """
    category = next(c for c in saijiki.SAIJIKI if c.key == "ji")
    assert category.name_ja == "じ"
    assert category.name_en == "grounds"
    assert len(category.words) == 7
    # Like おもて, this category says how the support is rather than what to
    # place, so the plugin closure never quotes it.
    assert category.marker_class is None
    assert {word.score_value for word in category.words} == set(SUPPORTS)
    # 「キャンバス」 is already the sheet's own proportion in the web UI, so the
    # support is spelled 「カンバス」 and the two never collide on one screen.
    surfaces = {word.surface_ja for word in category.words}
    assert "カンバス" in surfaces
    assert "キャンバス" not in surfaces
    # Asking for no ground is not a word you can say.
    assert "無地" not in surfaces


# --- T-3 through T-7: the drawing -------------------------------------------


@pytest.mark.parametrize("material", SUPPORTS)
def test_every_support_is_drawn_with_a_pattern(material: str) -> None:
    """T-3. Each support puts at least one tile in the file."""
    svg = render(_score(material), render_seed=123)
    assert _PATTERN.findall(svg)


@pytest.mark.parametrize("material", SUPPORTS)
def test_the_three_profiles_draw_the_same_ground(material: str) -> None:
    """T-4. The support does not depend on which file you exported.

    It used to: `display` got a `feTurbulence` rectangle and the other two got
    a scatter of dots, so the same work was made on a different sheet depending
    on the profile.
    """
    score = _score(material)
    drawn = {
        profile: _ground_layer(render(score, render_seed=123, svg_profile=profile))
        for profile in sorted(SVG_PROFILES)
    }
    assert len(set(drawn.values())) == 1, {k: len(v) for k, v in drawn.items()}


@pytest.mark.parametrize("material", SUPPORTS)
def test_the_ground_needs_no_filter_in_any_profile(material: str) -> None:
    """T-5. No profile reaches for a filter to draw the support.

    T-4 alone would stay green if all three profiles used the same filter, and
    `compat` exists precisely because a filter is what some readers cannot
    draw. A pattern is neither a filter nor a clip path, so all three carry it.
    """
    score = _score(material)
    for profile in sorted(SVG_PROFILES):
        svg = render(score, render_seed=123, svg_profile=profile)
        layer = _ground_layer(svg)
        # A tile in each profile, not merely a group: the group carries the tone
        # rectangle whether or not anything is drawn on it, so `assert layer`
        # alone stays green for a support that silently draws nothing.
        assert _PATTERN.findall(svg), profile
        assert "filter" not in layer, profile


@pytest.mark.parametrize("material", SUPPORTS)
def test_every_ground_stays_inside_the_budget(material: str) -> None:
    """T-6. One support's ground fits in 24 KB (author's ruling, 2026-08-14)."""
    svg = render(_score(material), render_seed=123)
    size = len(_ground_layer(svg))
    assert size <= GROUND_BYTE_BUDGET, size


def test_the_seven_supports_differ_from_one_another() -> None:
    """T-7. Seven supports, seven grounds.

    This says they are not the same file, not that a reader can tell them
    apart. Legibility was settled by eye across sixteen runs and cannot be
    asserted; distinctness can, and it is what catches a support quietly
    falling through to another one's branch.
    """
    digests = {
        material: hashlib.sha256(
            _ground_layer(
                render(_score(material, seed=_PINNED_SEED), render_seed=123)
            ).encode("utf-8")
        ).hexdigest()
        for material in SUPPORTS
    }
    assert len(set(digests.values())) == len(SUPPORTS), digests


# --- T-8: what is not asked for is not drawn --------------------------------


def test_a_score_without_a_ground_draws_no_ground_layer() -> None:
    """T-8. No ground sentence, no ground -- in any profile.

    A support added from the mood of a scene changes the picture of a work
    nobody asked to change.
    """
    without = Score.model_validate(
        {"instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}]}
    )
    plain = Score.model_validate(
        {
            "canvas": {"aspect": "square", "ground": {"material": "plain"}},
            "instructions": [{"primitive": "line", "from": [0.0, 0.5], "to": [1.0, 0.5]}],
        }
    )
    for score in (without, plain):
        for profile in sorted(SVG_PROFILES):
            svg = render(score, render_seed=123, svg_profile=profile)
            assert "layer_01_canvas_ground" not in svg
            assert not _PATTERN.findall(svg)
