"""Public contracts for the nine-word abstract color vocabulary."""

from __future__ import annotations

from typing import get_args

import pytest

from inku_server import composer, saijiki
from inku_server.color_catalogs import COLOR_CATALOGS, COLOR_KEYS, render_color_map_for_catalog
from inku_server.language_support.en import COERCE_MARKERS as EN_COERCE_MARKERS
from inku_server.language_support.ja import COERCE_MARKERS as JA_COERCE_MARKERS
from inku_server.renderer import render
from inku_server.schema import Color, Instruction, Score


EXPECTED_COLORS = (
    "white", "black", "blue", "red", "green", "gray", "yellow", "orange", "purple",
)


def test_color_literal_and_tool_schema_have_nine_stable_values() -> None:
    assert get_args(Color) == EXPECTED_COLORS
    properties = composer._score_tool_schema()["properties"]["instructions"]["items"][
        "properties"
    ]
    assert properties["color"]["enum"] == list(EXPECTED_COLORS)


def test_saved_six_color_score_still_validates() -> None:
    score = Score.model_validate(
        {
            "instructions": [
                {"primitive": "line", "from": [0.1, 0.5], "to": [0.9, 0.5], "color": color}
                for color in EXPECTED_COLORS[:6]
            ]
        }
    )
    assert tuple(item.color for item in score.instructions) == EXPECTED_COLORS[:6]


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda catalog: catalog["id"])
def test_all_catalogs_resolve_every_abstract_color(catalog: dict[str, object]) -> None:
    color_map = render_color_map_for_catalog(str(catalog["id"]))
    assert color_map is not None
    assert set(COLOR_KEYS) <= set(color_map)


def test_saijiki_color_words_have_paired_surfaces_and_score_values() -> None:
    expected_pairs = tuple(
        zip(("白", "黒", "青", "赤", "緑", "灰", "黄", "橙", "紫"), EXPECTED_COLORS, strict=True)
    )
    ja = next(item for item in saijiki.display_categories("ja") if item["key"] == "iro")
    en = next(item for item in saijiki.display_categories("en") if item["key"] == "iro")
    assert tuple(zip(ja["words"], en["words"], strict=True)) == expected_pairs


def test_color_markers_have_nine_entries_without_cross_matching() -> None:
    ja = JA_COERCE_MARKERS["color_markers"]
    en = EN_COERCE_MARKERS["color_markers"]
    assert len(ja) == len(en) == 9
    assert {value for tokens, value in ja if "金" in tokens} == {"yellow"}
    assert {value for tokens, value in en if "lantern" in tokens} == {"orange"}


@pytest.mark.parametrize("background", ("yellow", "orange", "purple"))
def test_new_background_colors_render_through_the_public_boundary(background: str) -> None:
    score = Score(
        background=background,
        instructions=[
            Instruction(primitive="line", **{"from": (0.1, 0.5)}, to=(0.9, 0.5), color="black")
        ],
    )
    color_map = render_color_map_for_catalog("ink_season")
    assert color_map is not None
    svg = render(score, color_map=color_map, catalog_id="ink_season", render_seed=1)
    assert color_map[background] in svg
