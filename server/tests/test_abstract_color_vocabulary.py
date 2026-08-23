"""Contract tests for the nine-word abstract color vocabulary."""

from __future__ import annotations

from typing import get_args

import pytest

from inku_server import composer, saijiki
from inku_server.color_catalogs import COLOR_CATALOGS, render_color_map_for_catalog
from inku_server.language_support.en import COERCE_MARKERS as EN_COERCE_MARKERS
from inku_server.language_support.ja import COERCE_MARKERS as JA_COERCE_MARKERS
from inku_server.render_engines.default.palette import (
    COLOR_MAP,
    _hue_from_hex,
    _resolve_color,
    _work_color_assignment,
)
from inku_server.renderer import render
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

EXPECTED_WORK_ASSIGNMENTS = {
    "default": {
        "white": "#ffffff", "black": "#111111", "blue": "#2c3e91",
        "red": "#a2342a", "green": "#2f6b3a", "gray": "#888888",
        "yellow": "#b8901f", "orange": "#b9671e", "purple": "#6a4d94",
    },
    "ink_season": {
        "white": "#fffffb", "black": "#141210", "blue": "#165e83",
        "red": "#8c2d1d", "green": "#007b43", "gray": "#595857",
        "yellow": "#847a2e", "orange": "#ffb61e", "purple": "#a591c5",
    },
    "fresco_study": {
        "white": "#f5f1e8", "black": "#4a342e", "blue": "#1f4e8c",
        "red": "#a0522d", "green": "#4f7942", "gray": "#8a8178",
        "yellow": "#c39a2b", "orange": "#b06a2f", "purple": "#71487c",
    },
    "open_air_light": {
        "white": "#fdfeff", "black": "#43474e", "blue": "#82c7de",
        "red": "#ee8fa2", "green": "#4e8372", "gray": "#afa6bd",
        "yellow": "#ffce00", "orange": "#f0b184", "purple": "#4b4a78",
    },
    "ink_porcelain": {
        "white": "#fffdfa", "black": "#1a1a1b", "blue": "#0057a8",
        "red": "#c91f24", "green": "#00896c", "gray": "#4b4b4f",
        "yellow": "#d6a01d", "orange": "#b5642c", "purple": "#6a4c8c",
    },
    "cool_material": {
        "white": "#fcfcfc", "black": "#26282a", "blue": "#4f8fb8",
        "red": "#6f4340", "green": "#3a544a", "gray": "#95a5a6",
        "yellow": "#4b5d43", "orange": "#a98467", "purple": "#575168",
    },
    "dye_earth": {
        "white": "#fffaf0", "black": "#2b2736", "blue": "#006c8f",
        "red": "#b7285f", "green": "#33684a", "gray": "#8d7f73",
        "yellow": "#d6b72a", "orange": "#e8862e", "purple": "#d83fb1",
    },
    "vivid_material": {
        "white": "#f4f4f4", "black": "#1c1c1c", "blue": "#73c2fb",
        "red": "#f50087", "green": "#008f39", "gray": "#7d6f66",
        "yellow": "#fff200", "orange": "#ff9800", "purple": "#8a4fc9",
    },
    "weathered_heritage": {
        "white": "#dcdcdc", "black": "#1f2933", "blue": "#4169e1",
        "red": "#b93a32", "green": "#004225", "gray": "#708090",
        "yellow": "#9b8342", "orange": "#9e6428", "purple": "#7b6293",
    },
    "sea_stone": {
        "white": "#f2f7f7", "black": "#10141a", "blue": "#191970",
        "red": "#e2725b", "green": "#2e613b", "gray": "#b2beb5",
        "yellow": "#808000", "orange": "#c97a45", "purple": "#191970",
    },
    "moss_bark": {
        "white": "#f2efe8", "black": "#181a17", "blue": "#43798a",
        "red": "#9c3330", "green": "#3e5a41", "gray": "#9ba39e",
        "yellow": "#d5ae43", "orange": "#7d5531", "purple": "#57355f",
    },
    "neon_plate": {
        "white": "#f4f8fb", "black": "#0d0d10", "blue": "#2f52d9",
        "red": "#e5004b", "green": "#00c853", "gray": "#777c82",
        "yellow": "#e3b800", "orange": "#ff8514", "purple": "#7a2fd0",
    },
    "lantern_dew": {
        "white": "#e6e8ec", "black": "#121216", "blue": "#1e2e52",
        "red": "#6d2a23", "green": "#2b4234", "gray": "#4d4e54",
        "yellow": "#c9b34a", "orange": "#c78c33", "purple": "#453a6e",
    },
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
    catalog_id = str(catalog["id"])
    catalog_map = render_color_map_for_catalog(catalog_id)
    cmap = {**COLOR_MAP, **(catalog_map or {})}
    assignment = _work_color_assignment(cmap, 12345, catalog_id)

    resolved = {
        color: _resolve_color(color, None, cmap, work_assignment=assignment)
        for color in EXPECTED_COLORS
    }

    assert resolved == EXPECTED_WORK_ASSIGNMENTS[catalog_id]
    assert len({resolved[color] for color in ("white", "black", "gray")}) == 3


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
    catalog_map = render_color_map_for_catalog("ink_season")
    cmap = {**COLOR_MAP, **(catalog_map or {})}
    assignment = _work_color_assignment(cmap, 1, "ink_season")

    svg = render(
        score,
        color_map=cmap,
        catalog_id="ink_season",
        render_seed=1,
    )

    assert f'fill="{assignment[background]}"' in svg
