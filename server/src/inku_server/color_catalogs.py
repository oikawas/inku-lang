"""Server-owned color catalog definitions."""

from __future__ import annotations

from typing import Any

DEFAULT_COLOR_CATALOG_ID = "default"
COLOR_KEYS = ("white", "black", "blue", "red", "green", "gray")

COLOR_CATALOGS: tuple[dict[str, Any], ...] = (
    {
        "id": "default",
        "name": "inku Default",
        "sub": "規定値",
        "map": {"white": "#ffffff", "black": "#111111", "blue": "#2c3e91", "red": "#a2342a", "green": "#2f6b3a", "gray": "#888888"},
        "swatches": ["#111111", "#ffffff", "#2c3e91", "#a2342a", "#2f6b3a", "#888888", "#555555", "#eeeeee"],
        "palette": [
            {"name": "Black", "code": "#111111"},
            {"name": "White", "code": "#ffffff"},
            {"name": "Blue", "code": "#2c3e91"},
            {"name": "Red", "code": "#a2342a"},
            {"name": "Green", "code": "#2f6b3a"},
            {"name": "Gray", "code": "#888888"},
            {"name": "Ink Shade", "code": "#555555"},
            {"name": "Paper", "code": "#eeeeee"},
        ],
    },
    {
        "id": "ink_season",
        "name": "Ink & Season",
        "sub": "ink, paper, seasonal accents",
        "map": {"black": "#111111", "white": "#fffffb", "red": "#d3381c", "blue": "#165e83", "green": "#007b43", "gray": "#595857"},
        "swatches": ["#111111", "#fffffb", "#d3381c", "#165e83", "#007b43", "#595857", "#a591c5", "#ffb61e"],
        "palette": [
            {"name": "Deep Ink", "code": "#111111"},
            {"name": "Warm Paper", "code": "#fffffb"},
            {"name": "Vermilion Accent", "code": "#d3381c"},
            {"name": "Indigo Shade", "code": "#165e83"},
            {"name": "Evergreen", "code": "#007b43"},
            {"name": "Soft Soot", "code": "#595857"},
            {"name": "Pale Violet", "code": "#a591c5"},
            {"name": "Golden Flower", "code": "#ffb61e"},
        ],
    },
    {
        "id": "fresco_study",
        "name": "Fresco Study",
        "sub": "plaster, pigment, warm stone",
        "map": {"black": "#4a342e", "white": "#f5f1e8", "red": "#c7432f", "blue": "#1f4e8c", "green": "#4f7942", "gray": "#8a8178"},
        "swatches": ["#8a8178", "#1f4e8c", "#c7432f", "#f7e89f", "#4f7942", "#a0522d", "#f5f1e8", "#4a342e"],
        "palette": [
            {"name": "Warm Stone", "code": "#8a8178"},
            {"name": "Deep Blue Pigment", "code": "#1f4e8c"},
            {"name": "Red Earth", "code": "#c7432f"},
            {"name": "Soft Yellow", "code": "#f7e89f"},
            {"name": "Green Earth", "code": "#4f7942"},
            {"name": "Burnt Earth", "code": "#a0522d"},
            {"name": "Plaster White", "code": "#f5f1e8"},
            {"name": "Umber Shadow", "code": "#4a342e"},
        ],
    },
    {
        "id": "open_air_light",
        "name": "Open-Air Light",
        "sub": "soft light, sky, reflected shade",
        "map": {"black": "#2f2d66", "white": "#ffffff", "red": "#ff9fb0", "blue": "#87ceeb", "green": "#40826d", "gray": "#b8a6c9"},
        "swatches": ["#2f2d66", "#ff9fb0", "#ffce00", "#40826d", "#b8a6c9", "#87ceeb", "#ffffff", "#fbceb1"],
        "palette": [
            {"name": "Deep Violet Shade", "code": "#2f2d66"},
            {"name": "Rose Light", "code": "#ff9fb0"},
            {"name": "Sunlit Yellow", "code": "#ffce00"},
            {"name": "Outdoor Green", "code": "#40826d"},
            {"name": "Lilac Gray", "code": "#b8a6c9"},
            {"name": "Sky Blue", "code": "#87ceeb"},
            {"name": "Clear White", "code": "#ffffff"},
            {"name": "Apricot Light", "code": "#fbceb1"},
        ],
    },
    {
        "id": "ink_porcelain",
        "name": "Ink & Porcelain",
        "sub": "ink, porcelain, mineral accents",
        "map": {"black": "#1a1a1b", "white": "#fffdfa", "red": "#c91f24", "blue": "#0057a8", "green": "#00896c", "gray": "#4b4b4f"},
        "swatches": ["#c91f24", "#d6a01d", "#00896c", "#0057a8", "#6a4c8c", "#fffdfa", "#1a1a1b", "#ff4d00"],
        "palette": [
            {"name": "Cinnabar Red", "code": "#c91f24"},
            {"name": "Mineral Gold", "code": "#d6a01d"},
            {"name": "Jade Green", "code": "#00896c"},
            {"name": "Porcelain Blue", "code": "#0057a8"},
            {"name": "Mineral Violet", "code": "#6a4c8c"},
            {"name": "Porcelain White", "code": "#fffdfa"},
            {"name": "Ink Black", "code": "#1a1a1b"},
            {"name": "Bright Vermilion", "code": "#ff4d00"},
        ],
    },
    {
        "id": "cool_material",
        "name": "Cool Material",
        "sub": "cool light, wood, stone",
        "map": {"black": "#2c3e50", "white": "#fcfcfc", "red": "#a98467", "blue": "#4f8fb8", "green": "#4b5d43", "gray": "#95a5a6"},
        "swatches": ["#fcfcfc", "#2c3e50", "#4b5d43", "#95a5a6", "#e5e8e8", "#4f8fb8", "#f4d03f", "#a98467"],
        "palette": [
            {"name": "Snow Light", "code": "#fcfcfc"},
            {"name": "Midnight Blue", "code": "#2c3e50"},
            {"name": "Moss Wood", "code": "#4b5d43"},
            {"name": "Granite Gray", "code": "#95a5a6"},
            {"name": "Pale Birch", "code": "#e5e8e8"},
            {"name": "Muted Sea", "code": "#4f8fb8"},
            {"name": "Low Sun", "code": "#f4d03f"},
            {"name": "Clay Brown", "code": "#a98467"},
        ],
    },
    {
        "id": "dye_earth",
        "name": "Dye & Earth",
        "sub": "textile dye, earth, rain shade",
        "map": {"black": "#1f1b2e", "white": "#fffaf0", "red": "#c2185b", "blue": "#006c8f", "green": "#6b7d3a", "gray": "#8d7f73"},
        "swatches": ["#ff9933", "#d6b72a", "#c2185b", "#6b7d3a", "#006c8f", "#fc0fc0", "#8d7f73", "#fffaf0"],
        "palette": [
            {"name": "Saffron Dye", "code": "#ff9933"},
            {"name": "Yellow Dye", "code": "#d6b72a"},
            {"name": "Deep Rose Dye", "code": "#c2185b"},
            {"name": "Leaf Dye", "code": "#6b7d3a"},
            {"name": "Peacock Blue", "code": "#006c8f"},
            {"name": "Bright Pink", "code": "#fc0fc0"},
            {"name": "Wet Earth", "code": "#8d7f73"},
            {"name": "Warm Cotton", "code": "#fffaf0"},
        ],
    },
    {
        "id": "desert_mineral",
        "name": "Desert Mineral",
        "sub": "mineral, linen, desert shadow",
        "map": {"black": "#0a0a0a", "white": "#f5deb3", "red": "#b31b1b", "blue": "#123499", "green": "#0b8f6a", "gray": "#9c8f7a"},
        "swatches": ["#123499", "#d8b64c", "#b31b1b", "#0b8f6a", "#f5deb3", "#0a0a0a", "#cc7722", "#e8e4c9"],
        "palette": [
            {"name": "Deep Mineral Blue", "code": "#123499"},
            {"name": "Muted Gold", "code": "#d8b64c"},
            {"name": "Red Mineral", "code": "#b31b1b"},
            {"name": "Malachite Green", "code": "#0b8f6a"},
            {"name": "Dry Paper", "code": "#f5deb3"},
            {"name": "Basalt Black", "code": "#0a0a0a"},
            {"name": "Desert Ochre", "code": "#cc7722"},
            {"name": "Linen Light", "code": "#e8e4c9"},
        ],
    },
    {
        "id": "vivid_material",
        "name": "Vivid Material",
        "sub": "vivid pigment, lime, stone",
        "map": {"black": "#1c1c1c", "white": "#f4f4f4", "red": "#f50087", "blue": "#73c2fb", "green": "#008f39", "gray": "#7d6f66"},
        "swatches": ["#f50087", "#73c2fb", "#008f39", "#ff9800", "#7d6f66", "#fff200", "#f4f4f4", "#1c1c1c"],
        "palette": [
            {"name": "Vivid Rose", "code": "#f50087"},
            {"name": "Bright Blue", "code": "#73c2fb"},
            {"name": "Fresh Green", "code": "#008f39"},
            {"name": "Orange Marigold", "code": "#ff9800"},
            {"name": "Urban Stone", "code": "#7d6f66"},
            {"name": "Sun Yellow", "code": "#fff200"},
            {"name": "Lime White", "code": "#f4f4f4"},
            {"name": "Volcanic Black", "code": "#1c1c1c"},
        ],
    },
    {
        "id": "weathered_heritage",
        "name": "Weathered Heritage",
        "sub": "fog, brick, wool, rain",
        "map": {"black": "#1f2933", "white": "#fffdd0", "red": "#b93a32", "blue": "#4169e1", "green": "#004225", "gray": "#708090"},
        "swatches": ["#004225", "#4169e1", "#708090", "#b93a32", "#8b8589", "#fffdd0", "#dcdcdc", "#1f2933"],
        "palette": [
            {"name": "Deep Green", "code": "#004225"},
            {"name": "Rain Blue", "code": "#4169e1"},
            {"name": "Slate Gray", "code": "#708090"},
            {"name": "Brick Red", "code": "#b93a32"},
            {"name": "Wool Gray", "code": "#8b8589"},
            {"name": "Cream", "code": "#fffdd0"},
            {"name": "Fog Light", "code": "#dcdcdc"},
            {"name": "Charcoal", "code": "#1f2933"},
        ],
    },
    {
        "id": "sea_stone",
        "name": "Sea & Stone",
        "sub": "sea light, stone, dry earth",
        "map": {"black": "#191970", "white": "#ffffff", "red": "#e2725b", "blue": "#005bae", "green": "#808000", "gray": "#b2beb5"},
        "swatches": ["#ffffff", "#89cff0", "#005bae", "#b2beb5", "#808000", "#f9d71c", "#e2725b", "#191970"],
        "palette": [
            {"name": "Clear White", "code": "#ffffff"},
            {"name": "Pale Sea", "code": "#89cff0"},
            {"name": "Deep Sea", "code": "#005bae"},
            {"name": "Stone Gray", "code": "#b2beb5"},
            {"name": "Dry Olive", "code": "#808000"},
            {"name": "Sun Yellow", "code": "#f9d71c"},
            {"name": "Clay Red", "code": "#e2725b"},
            {"name": "Night Sea", "code": "#191970"},
        ],
    },
)


def color_catalog_ids() -> tuple[str, ...]:
    return tuple(str(catalog["id"]) for catalog in COLOR_CATALOGS)


def color_catalogs() -> list[dict[str, Any]]:
    return [dict(catalog) for catalog in COLOR_CATALOGS]


def get_color_catalog(catalog_id: str | None) -> dict[str, Any] | None:
    resolved = catalog_id or DEFAULT_COLOR_CATALOG_ID
    for catalog in COLOR_CATALOGS:
        if catalog["id"] == resolved:
            return dict(catalog)
    return None


def render_color_map_for_catalog(catalog_id: str | None) -> dict[str, str] | None:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        return None
    color_map: dict[str, str] = dict(catalog["map"])
    for color in catalog["palette"]:
        color_map[f"palette:{color['name']}"] = color["code"]
    return color_map
