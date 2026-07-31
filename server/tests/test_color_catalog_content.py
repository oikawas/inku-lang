"""Contract tests for the engine-18 color catalog content.

Engine 18 moves data and nothing else: thirteen catalogs, each with exactly
three achromatic and seven chromatic colors, a nine-key map drawn from the
palette, and a swatch strip derived from that map. These tests pin the shape of
that data by value, because a catalog table is the kind of thing a later edit
can quietly unbalance -- one hex nudged past the chroma floor empties a band.
"""

from __future__ import annotations

import pytest

from inku_server.color_catalogs import (
    COLOR_CATALOGS,
    COLOR_KEYS,
    SWATCH_KEY_ORDER,
    color_catalog_ids,
    get_color_catalog,
    render_color_map_for_catalog,
)
from inku_server.renderer import (
    _OKLCH_CHROMA_FLOOR,
    _oklch_from_hex,
    _work_color_assignment,
    COLOR_MAP,
)


ACHROMATIC_KEYS = ("black", "gray", "white")
CHROMATIC_KEYS = ("red", "orange", "yellow", "green", "blue", "purple")

EXPECTED_CATALOG_IDS = (
    "default",
    "ink_season",
    "fresco_study",
    "open_air_light",
    "ink_porcelain",
    "cool_material",
    "dye_earth",
    "vivid_material",
    "weathered_heritage",
    "sea_stone",
    "moss_bark",
    "neon_plate",
    "lantern_dew",
)

RETIRED_CATALOG_IDS = (
    "desert_mineral",
    "japanese",
    "mexican",
    "indian",
    "british",
    "egyptian",
    "greek",
    "impressionism",
    "nordic",
    "renaissance",
)


def _is_chromatic(hex_value: str) -> bool:
    oklch = _oklch_from_hex(hex_value)
    assert oklch is not None, hex_value
    return oklch[1] >= _OKLCH_CHROMA_FLOOR


def test_color_keys_are_the_nine_abstract_colors() -> None:
    assert len(COLOR_KEYS) == 9
    assert COLOR_KEYS == (
        "white", "black", "gray", "red", "orange", "yellow", "green", "blue", "purple",
    )


def test_catalog_ids_and_order() -> None:
    assert color_catalog_ids() == EXPECTED_CATALOG_IDS


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_catalog_holds_three_achromatic_and_seven_chromatic_colors(
    catalog: dict,
) -> None:
    palette = catalog["palette"]
    codes = [str(color["code"]) for color in palette]

    assert len(palette) == 10
    assert len(set(codes)) == 10, f"duplicate hex in {catalog['id']}"

    chromatic = [code for code in codes if _is_chromatic(code)]
    achromatic = [code for code in codes if not _is_chromatic(code)]
    assert len(achromatic) == 3, f"{catalog['id']} achromatic: {achromatic}"
    assert len(chromatic) == 7, f"{catalog['id']} chromatic: {chromatic}"


def test_no_hex_is_reused_across_catalogs() -> None:
    codes = [
        str(color["code"])
        for catalog in COLOR_CATALOGS
        for color in catalog["palette"]
    ]

    assert len(codes) == 130
    assert len(set(codes)) == 130


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_map_key_names_a_color_from_the_same_palette(catalog: dict) -> None:
    codes = {str(color["code"]) for color in catalog["palette"]}

    assert set(catalog["map"]) == set(COLOR_KEYS)
    for key in COLOR_KEYS:
        assert catalog["map"][key] in codes, (catalog["id"], key)


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_the_first_four_swatches_are_chromatic(catalog: dict) -> None:
    # Android draws `swatches.take(4)` in one screen, so the leading four slots
    # decide whether that strip shows a catalog's colors or its grays. Asserted
    # against the chroma floor rather than against SWATCH_KEY_ORDER, which would
    # only restate how the list was built.
    swatches = catalog["swatches"]

    assert len(swatches) == 9
    assert [_is_chromatic(hex_value) for hex_value in swatches[:4]] == [True] * 4
    assert [_is_chromatic(hex_value) for hex_value in swatches[:8]].count(False) == 2


def test_swatch_key_order_leads_with_the_six_bands() -> None:
    assert SWATCH_KEY_ORDER[:6] == CHROMATIC_KEYS
    assert SWATCH_KEY_ORDER[6:] == ACHROMATIC_KEYS


@pytest.mark.parametrize("catalog_id", EXPECTED_CATALOG_IDS)
def test_every_catalog_map_carries_ten_palette_entries(catalog_id: str) -> None:
    color_map = render_color_map_for_catalog(catalog_id)

    assert color_map is not None
    assert sum(1 for key in color_map if key.startswith("palette:")) == 10


def test_sea_stone_purple_stands_in_with_night_sea() -> None:
    # sea_stone is the one catalog left without a color in the purple band, by
    # the author's ruling. The renderer's nearest-band stand-in must answer with
    # Night Sea, which is also its blue -- that collision is the ruling, not a
    # defect.
    color_map = render_color_map_for_catalog("sea_stone")
    assert color_map is not None
    cmap = {**COLOR_MAP, **color_map}

    assignment = _work_color_assignment(cmap, 12345, "sea_stone")

    assert assignment["purple"] == "#191970"
    assert assignment["blue"] == "#191970"


@pytest.mark.parametrize("catalog_id", RETIRED_CATALOG_IDS)
def test_retired_catalog_ids_resolve_to_nothing(catalog_id: str) -> None:
    assert get_color_catalog(catalog_id) is None
    assert render_color_map_for_catalog(catalog_id) is None
