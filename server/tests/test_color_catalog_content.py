"""Host-owned structural contracts for color catalog data."""

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


EXPECTED_CATALOG_IDS = (
    "default", "ink_season", "fresco_study", "open_air_light", "ink_porcelain",
    "cool_material", "dye_earth", "vivid_material", "weathered_heritage",
    "sea_stone", "moss_bark", "neon_plate", "lantern_dew",
)
RETIRED_CATALOG_IDS = (
    "desert_mineral", "japanese", "mexican", "indian", "british", "egyptian",
    "greek", "impressionism", "nordic", "renaissance",
)


def test_color_keys_and_catalog_order_are_stable() -> None:
    assert COLOR_KEYS == (
        "white", "black", "gray", "red", "orange", "yellow", "green", "blue", "purple",
    )
    assert color_catalog_ids() == EXPECTED_CATALOG_IDS


@pytest.mark.parametrize("catalog", COLOR_CATALOGS, ids=lambda item: item["id"])
def test_every_catalog_has_unique_palette_entries_and_a_complete_map(catalog: dict) -> None:
    codes = [str(color["code"]) for color in catalog["palette"]]
    assert len(codes) == len(set(codes)) == 10
    assert set(catalog["map"]) == set(COLOR_KEYS)
    assert set(catalog["map"].values()) <= set(codes)
    assert len(catalog["swatches"]) == len(COLOR_KEYS)


def test_no_hex_is_reused_across_catalogs() -> None:
    codes = [
        str(color["code"])
        for catalog in COLOR_CATALOGS
        for color in catalog["palette"]
    ]
    assert len(codes) == len(set(codes)) == 130


def test_swatch_order_leads_with_the_six_chromatic_roles() -> None:
    assert SWATCH_KEY_ORDER[:6] == ("red", "orange", "yellow", "green", "blue", "purple")
    assert SWATCH_KEY_ORDER[6:] == ("black", "gray", "white")


@pytest.mark.parametrize("catalog_id", EXPECTED_CATALOG_IDS)
def test_render_map_carries_the_palette_entries(catalog_id: str) -> None:
    color_map = render_color_map_for_catalog(catalog_id)
    assert color_map is not None
    assert sum(key.startswith("palette:") for key in color_map) == 10


@pytest.mark.parametrize("catalog_id", RETIRED_CATALOG_IDS)
def test_retired_catalog_ids_resolve_to_nothing(catalog_id: str) -> None:
    assert get_color_catalog(catalog_id) is None
    assert render_color_map_for_catalog(catalog_id) is None
