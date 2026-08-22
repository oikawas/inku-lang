"""Contract tests for deterministic palette color assignment."""

from __future__ import annotations

import re

import pytest

from inku_server.color_catalogs import COLOR_CATALOGS, render_color_map_for_catalog
from inku_server.render_engines.default.determinism import _seed_for_instruction
from inku_server.renderer import (
    COLOR_MAP,
    _hint_hues,
    _resolve_color,
    _work_color_assignment,
    render,
)
from inku_server.schema import Instruction, Score


ABSTRACT_COLORS = (
    "white",
    "black",
    "blue",
    "red",
    "green",
    "gray",
    "yellow",
    "orange",
    "purple",
)


def _catalog_map(catalog_id: str) -> dict[str, str]:
    catalog_map = render_color_map_for_catalog(catalog_id)
    assert catalog_map is not None
    return {**COLOR_MAP, **catalog_map}


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_catalog_assigns_distinct_achromatic_roles(catalog: dict) -> None:
    catalog_id = str(catalog["id"])
    assignment = _work_color_assignment(_catalog_map(catalog_id), 12345, catalog_id)

    assert len({assignment[color].lower() for color in ("black", "gray", "white")}) == 3


# Every shipped catalog now carries exactly three achromatic colors, so no real
# catalog can exercise the anti-collapse rule any more -- the witness for it has
# to be built here or the rule goes untested. `desert_mineral`, which used to be
# that witness, was retired with engine 18.
SPARSE_ACHROMATIC_CATALOG = {
    "map": {
        "black": "#101010",
        "gray": "#7a7a7a",
        "white": "#f7f7f7",
        "red": "#b03a2e",
        "orange": "#b9671e",
        "yellow": "#b8901f",
        "green": "#2f6b3a",
        "blue": "#2c3e91",
        "purple": "#6a4d94",
    },
    # One achromatic entry, and it matches none of the three map values.
    "palette": {
        "Single Ash": "#3d3d3d",
        "Only Red": "#b03a2e",
        "Only Blue": "#2c3e91",
    },
}


def _sparse_achromatic_map() -> dict[str, str]:
    catalog = SPARSE_ACHROMATIC_CATALOG
    cmap = {**COLOR_MAP, **catalog["map"]}
    for name, code in catalog["palette"].items():
        cmap[f"palette:{name}"] = code
    return cmap


def test_a_single_achromatic_palette_color_does_not_collapse_the_three_roles() -> None:
    cmap = _sparse_achromatic_map()

    assignment = _work_color_assignment(cmap, 12345, "sparse_achromatic")

    # The one palette ash goes to the nearest role by lightness; the other two
    # keep the catalog's own map values instead of repeating it.
    assert {color: assignment[color] for color in ("black", "gray", "white")} == {
        "black": "#3d3d3d",
        "gray": "#7a7a7a",
        "white": "#f7f7f7",
    }
    assert len({assignment[color] for color in ("black", "gray", "white")}) == 3


def test_hint_matching_uses_ascii_words_and_cjk_substrings() -> None:
    assert _hint_hues("deep blue wash") == {"blue"}
    assert _hint_hues("vertical restored blur constraint") == set()
    assert _hint_hues("桜色の薄い層") == {"red"}


def test_hint_resolution_uses_the_requested_band_and_fallback_assignment() -> None:
    cmap = _catalog_map("default")
    assignment = _work_color_assignment(cmap, 12345, "default")

    assert _resolve_color(
        "black", "deep blue", cmap, work_assignment=assignment
    ) == assignment["blue"]
    assert _resolve_color(
        "black", "桜色", cmap, work_assignment=assignment
    ) == assignment["red"]
    assert _resolve_color(
        "black", "purple", cmap, work_assignment=assignment
    ) == assignment["purple"]
    assert _resolve_color(
        "black", "umber earth", cmap, work_assignment=assignment
    ) == assignment["orange"]


def test_work_assignment_is_stable_for_one_hundred_resolutions() -> None:
    cmap = _catalog_map("ink_porcelain")
    expected = _work_color_assignment(cmap, 12345, "ink_porcelain")

    assert [
        _work_color_assignment(cmap, 12345, "ink_porcelain")
        for _ in range(100)
    ] == [expected] * 100


def test_instruction_performance_seed_does_not_enter_work_color_assignment() -> None:
    instruction = Instruction(
        primitive="line",
        **{"from": (0.1, 0.5)},
        to=(0.9, 0.5),
        color="red",
    )
    cmap = _catalog_map("ink_porcelain")
    assignment = _work_color_assignment(cmap, 12345, "ink_porcelain")

    first_performance_seed = _seed_for_instruction(instruction, 1)
    second_performance_seed = _seed_for_instruction(instruction, 2)
    resolved_before = _resolve_color("red", None, cmap, work_assignment=assignment)
    resolved_after = _resolve_color("red", None, cmap, work_assignment=assignment)

    assert first_performance_seed != second_performance_seed
    assert resolved_before == resolved_after == assignment["red"]


def test_catalog_id_participates_in_multi_candidate_choice() -> None:
    cmap = _catalog_map("ink_porcelain")

    assert (
        _work_color_assignment(cmap, 12345, "ink_porcelain")["red"]
        != _work_color_assignment(cmap, 12345, "default")["red"]
    )


def test_background_and_marks_use_the_same_work_assignment() -> None:
    score = Score(
        background="red",
        instructions=[
            Instruction(
                primitive="line",
                **{"from": (0.1, 0.35)},
                to=(0.9, 0.35),
                color="black",
            ),
            Instruction(
                primitive="line",
                **{"from": (0.1, 0.65)},
                to=(0.9, 0.65),
                color="black",
            ),
        ],
    )
    cmap = _catalog_map("ink_porcelain")
    assignment = _work_color_assignment(cmap, 12345, "ink_porcelain")

    svg = render(
        score,
        color_map=cmap,
        catalog_id="ink_porcelain",
        render_seed=12345,
        svg_profile="editable",
    )

    background = re.search(r'<rect[^>]*id="background"[^>]*/>', svg)
    assert background is not None
    assert f'fill="{assignment["red"]}"' in background.group()
    assert len(re.findall(rf'stroke="{re.escape(assignment["black"])}"', svg)) >= 2
