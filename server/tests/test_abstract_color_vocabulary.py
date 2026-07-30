"""Contract tests for the nine-word abstract color vocabulary."""

from __future__ import annotations

from typing import get_args

import pytest

from inku_server import composer, saijiki
from inku_server.color_catalogs import COLOR_CATALOGS, render_color_map_for_catalog
from inku_server.language_support.en import COERCE_MARKERS as EN_COERCE_MARKERS
from inku_server.language_support.ja import COERCE_MARKERS as JA_COERCE_MARKERS
from inku_server.renderer import COLOR_MAP, _hue_from_hex, _resolve_color, render
from inku_server.schema import Color, Instruction, Score


EXPECTED_COLORS = (
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
NEW_DEFAULTS = {
    "yellow": "#a18308",
    "orange": "#a95a00",
    "purple": "#583a84",
}


def test_color_literal_and_tool_schema_have_nine_stable_values() -> None:
    assert get_args(Color) == EXPECTED_COLORS

    properties = composer._score_tool_schema()["properties"]["instructions"]["items"][
        "properties"
    ]
    assert len(properties) == 25
    assert list(properties).index("color") == 17
    assert properties["color"]["enum"] == list(EXPECTED_COLORS)


def test_saved_six_color_score_still_validates() -> None:
    saved = {
        "background": "white",
        "instructions": [
            {
                "primitive": "line",
                "from": [0.1, 0.5],
                "to": [0.9, 0.5],
                "color": color,
            }
            for color in EXPECTED_COLORS[:6]
        ],
    }

    score = Score.model_validate(saved)

    assert tuple(instruction.color for instruction in score.instructions) == EXPECTED_COLORS[:6]


def test_new_default_colors_classify_as_themselves() -> None:
    assert {color: COLOR_MAP[color] for color in NEW_DEFAULTS} == NEW_DEFAULTS
    assert {
        color: _hue_from_hex(hex_value) for color, hex_value in NEW_DEFAULTS.items()
    } == {color: color for color in NEW_DEFAULTS}


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda catalog: catalog["id"])
def test_all_catalogs_resolve_all_nine_colors(catalog: dict[str, object]) -> None:
    catalog_map = render_color_map_for_catalog(str(catalog["id"]))
    cmap = {**COLOR_MAP, **(catalog_map or {})}

    assert {
        color: _resolve_color(color, None, cmap) for color in EXPECTED_COLORS
    }.keys() == set(EXPECTED_COLORS)


def test_saijiki_color_words_have_paired_surfaces_and_score_values() -> None:
    expected_pairs = (
        ("白", "white"),
        ("黒", "black"),
        ("青", "blue"),
        ("赤", "red"),
        ("緑", "green"),
        ("灰", "gray"),
        ("黄", "yellow"),
        ("橙", "orange"),
        ("紫", "purple"),
    )
    ja = next(category for category in saijiki.display_categories("ja") if category["key"] == "iro")
    en = next(category for category in saijiki.display_categories("en") if category["key"] == "iro")

    assert tuple(zip(ja["words"], en["words"], strict=True)) == expected_pairs
    assert saijiki.color_for_surface() == {
        surface: value for pair in expected_pairs for surface, value in (pair, (pair[1], pair[1]))
    }


def _values_matching(text: str, markers: tuple[tuple[tuple[str, ...], str], ...]) -> set[str]:
    return {value for tokens, value in markers if any(token in text for token in tokens)}


def test_color_markers_have_nine_entries_without_cross_matching_new_words() -> None:
    ja = JA_COERCE_MARKERS["color_markers"]
    en = EN_COERCE_MARKERS["color_markers"]

    assert len(ja) == len(en) == 9
    assert ja[-3:] == (
        (("黄", "金"), "yellow"),
        (("橙", "蜜柑", "灯火"), "orange"),
        (("紫", "菫", "藤"), "purple"),
    )
    assert en[-3:] == (
        (("yellow", "gold"), "yellow"),
        (("orange", "lantern"), "orange"),
        (("purple", "violet", "lilac"), "purple"),
    )
    assert _values_matching("金", ja) == {"yellow"}
    assert _values_matching("lantern", en) == {"orange"}
    assert _values_matching("藤", ja) == {"purple"}


@pytest.mark.parametrize("background", ("yellow", "orange", "purple"))
def test_new_background_colors_render(background: str) -> None:
    score = Score(
        background=background,
        instructions=[
            Instruction(
                primitive="line",
                **{"from": (0.1, 0.5)},
                to=(0.9, 0.5),
                color="black",
            )
        ],
    )

    svg = render(score, render_seed=1)

    assert f'fill="{COLOR_MAP[background]}"' in svg
