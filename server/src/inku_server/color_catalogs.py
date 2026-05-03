"""Server-owned color catalog definitions."""

from __future__ import annotations

from typing import Any

DEFAULT_COLOR_CATALOG_ID = "default"
COLOR_KEYS = ("white", "black", "blue", "red", "green", "gray")

COLOR_CATALOGS: tuple[dict[str, Any], ...] = (
    {
        "id": "default",
        "name": "inku Default",
        "sub": "neutral baseline",
        "sub_ja": "ニュートラルな基準値",
        "map": {"white": "#ffffff", "black": "#111111", "blue": "#2c3e91", "red": "#a2342a", "green": "#2f6b3a", "gray": "#888888"},
        "swatches": ["#111111", "#ffffff", "#2c3e91", "#a2342a", "#2f6b3a", "#888888", "#555555", "#eeeeee"],
        "palette": [
            {"name": "Black", "name_ja": "黒", "code": "#111111"},
            {"name": "White", "name_ja": "白", "code": "#ffffff"},
            {"name": "Blue", "name_ja": "青", "code": "#2c3e91"},
            {"name": "Red", "name_ja": "赤", "code": "#a2342a"},
            {"name": "Green", "name_ja": "緑", "code": "#2f6b3a"},
            {"name": "Gray", "name_ja": "灰", "code": "#888888"},
            {"name": "Ink Shade", "name_ja": "インクの影", "code": "#555555"},
            {"name": "Paper", "name_ja": "紙", "code": "#eeeeee"},
        ],
    },
    {
        "id": "ink_season",
        "name": "Ink & Season",
        "sub": "ink, paper, seasonal accents",
        "sub_ja": "墨、紙、季節の差し色",
        "map": {"black": "#111111", "white": "#fffffb", "red": "#d3381c", "blue": "#165e83", "green": "#007b43", "gray": "#595857"},
        "swatches": ["#111111", "#fffffb", "#d3381c", "#165e83", "#007b43", "#595857", "#a591c5", "#ffb61e"],
        "palette": [
            {"name": "Deep Ink", "name_ja": "墨", "code": "#111111"},
            {"name": "Warm Paper", "name_ja": "胡粉", "code": "#fffffb"},
            {"name": "Vermilion Accent", "name_ja": "朱", "code": "#d3381c"},
            {"name": "Indigo Shade", "name_ja": "藍", "code": "#165e83"},
            {"name": "Evergreen", "name_ja": "常磐", "code": "#007b43"},
            {"name": "Soft Soot", "name_ja": "消墨", "code": "#595857"},
            {"name": "Pale Violet", "name_ja": "藤紫", "code": "#a591c5"},
            {"name": "Golden Flower", "name_ja": "山吹", "code": "#ffb61e"},
        ],
    },
    {
        "id": "fresco_study",
        "name": "Fresco Study",
        "sub": "plaster, pigment, warm stone",
        "sub_ja": "漆喰、顔料、温かい石",
        "map": {"black": "#4a342e", "white": "#f5f1e8", "red": "#c7432f", "blue": "#1f4e8c", "green": "#4f7942", "gray": "#8a8178"},
        "swatches": ["#8a8178", "#1f4e8c", "#c7432f", "#f7e89f", "#4f7942", "#a0522d", "#f5f1e8", "#4a342e"],
        "palette": [
            {"name": "Warm Stone", "name_ja": "温かい石", "code": "#8a8178"},
            {"name": "Deep Blue Pigment", "name_ja": "深い青顔料", "code": "#1f4e8c"},
            {"name": "Red Earth", "name_ja": "赤土", "code": "#c7432f"},
            {"name": "Soft Yellow", "name_ja": "柔らかな黄", "code": "#f7e89f"},
            {"name": "Green Earth", "name_ja": "緑土", "code": "#4f7942"},
            {"name": "Burnt Earth", "name_ja": "焼けた土", "code": "#a0522d"},
            {"name": "Plaster White", "name_ja": "漆喰の白", "code": "#f5f1e8"},
            {"name": "Umber Shadow", "name_ja": "アンバーの影", "code": "#4a342e"},
        ],
    },
    {
        "id": "open_air_light",
        "name": "Open-Air Light",
        "sub": "soft light, sky, reflected shade",
        "sub_ja": "柔らかな光、空、反射する陰",
        "map": {"black": "#4b4a78", "white": "#ffffff", "red": "#ee8fa2", "blue": "#82c7de", "green": "#4e8372", "gray": "#afa6bd"},
        "swatches": ["#4b4a78", "#ee8fa2", "#ffce00", "#4e8372", "#afa6bd", "#82c7de", "#ffffff", "#fbceb1"],
        "palette": [
            {"name": "Violet Gray Shade", "name_ja": "菫灰の陰", "code": "#4b4a78"},
            {"name": "Rose Light", "name_ja": "薔薇色の光", "code": "#ee8fa2"},
            {"name": "Sunlit Yellow", "name_ja": "陽だまりの黄", "code": "#ffce00"},
            {"name": "Outdoor Green", "name_ja": "戸外の緑", "code": "#4e8372"},
            {"name": "Lilac Gray", "name_ja": "ライラック灰", "code": "#afa6bd"},
            {"name": "Sky Blue", "name_ja": "空色", "code": "#82c7de"},
            {"name": "Clear White", "name_ja": "澄んだ白", "code": "#ffffff"},
            {"name": "Apricot Light", "name_ja": "杏の光", "code": "#fbceb1"},
        ],
    },
    {
        "id": "ink_porcelain",
        "name": "Ink & Porcelain",
        "sub": "ink, porcelain, mineral accents",
        "sub_ja": "墨、磁器、鉱物の差し色",
        "map": {"black": "#1a1a1b", "white": "#fffdfa", "red": "#c91f24", "blue": "#0057a8", "green": "#00896c", "gray": "#4b4b4f"},
        "swatches": ["#c91f24", "#d6a01d", "#00896c", "#0057a8", "#6a4c8c", "#fffdfa", "#1a1a1b", "#ff4d00"],
        "palette": [
            {"name": "Cinnabar Red", "name_ja": "辰砂の赤", "code": "#c91f24"},
            {"name": "Mineral Gold", "name_ja": "鉱物の金", "code": "#d6a01d"},
            {"name": "Jade Green", "name_ja": "翡翠の緑", "code": "#00896c"},
            {"name": "Porcelain Blue", "name_ja": "磁器の青", "code": "#0057a8"},
            {"name": "Mineral Violet", "name_ja": "鉱物の紫", "code": "#6a4c8c"},
            {"name": "Porcelain White", "name_ja": "磁器の白", "code": "#fffdfa"},
            {"name": "Ink Black", "name_ja": "墨の黒", "code": "#1a1a1b"},
            {"name": "Bright Vermilion", "name_ja": "明るい朱", "code": "#ff4d00"},
        ],
    },
    {
        "id": "cool_material",
        "name": "Cool Material",
        "sub": "cool light, wood, stone",
        "sub_ja": "冷たい光、木、石",
        "map": {"black": "#2c3e50", "white": "#fcfcfc", "red": "#a98467", "blue": "#4f8fb8", "green": "#4b5d43", "gray": "#95a5a6"},
        "swatches": ["#fcfcfc", "#2c3e50", "#4b5d43", "#95a5a6", "#e5e8e8", "#4f8fb8", "#f4d03f", "#a98467"],
        "palette": [
            {"name": "Snow Light", "name_ja": "雪の光", "code": "#fcfcfc"},
            {"name": "Midnight Blue", "name_ja": "真夜中の青", "code": "#2c3e50"},
            {"name": "Moss Wood", "name_ja": "苔むした木", "code": "#4b5d43"},
            {"name": "Granite Gray", "name_ja": "花崗岩の灰", "code": "#95a5a6"},
            {"name": "Pale Birch", "name_ja": "淡い白樺", "code": "#e5e8e8"},
            {"name": "Muted Sea", "name_ja": "鈍い海色", "code": "#4f8fb8"},
            {"name": "Low Sun", "name_ja": "低い太陽", "code": "#f4d03f"},
            {"name": "Clay Brown", "name_ja": "粘土の茶", "code": "#a98467"},
        ],
    },
    {
        "id": "dye_earth",
        "name": "Dye & Earth",
        "sub": "textile dye, earth, rain shade",
        "sub_ja": "布の染料、土、雨の陰",
        "map": {"black": "#2b2736", "white": "#fffaf0", "red": "#b7285f", "blue": "#006c8f", "green": "#6b7d3a", "gray": "#8d7f73"},
        "swatches": ["#e8862e", "#d6b72a", "#b7285f", "#6b7d3a", "#006c8f", "#d83fb1", "#8d7f73", "#fffaf0"],
        "palette": [
            {"name": "Saffron Dye", "name_ja": "サフラン染め", "code": "#e8862e"},
            {"name": "Yellow Dye", "name_ja": "黄色の染料", "code": "#d6b72a"},
            {"name": "Deep Rose Dye", "name_ja": "深い薔薇染め", "code": "#b7285f"},
            {"name": "Leaf Dye", "name_ja": "葉の染料", "code": "#6b7d3a"},
            {"name": "Peacock Blue", "name_ja": "孔雀青", "code": "#006c8f"},
            {"name": "Bright Pink", "name_ja": "明るい桃色", "code": "#d83fb1"},
            {"name": "Wet Earth", "name_ja": "濡れた土", "code": "#8d7f73"},
            {"name": "Warm Cotton", "name_ja": "温かな綿", "code": "#fffaf0"},
        ],
    },
    {
        "id": "desert_mineral",
        "name": "Desert Mineral",
        "sub": "mineral, linen, desert shadow",
        "sub_ja": "鉱物、麻布、乾いた陰",
        "map": {"black": "#1c1b18", "white": "#f1e4c8", "red": "#b31b1b", "blue": "#1f4b8f", "green": "#1c8a68", "gray": "#8f8878"},
        "swatches": ["#1f4b8f", "#c9ad57", "#b31b1b", "#1c8a68", "#f1e4c8", "#1c1b18", "#bd6f2c", "#e8e4c9"],
        "palette": [
            {"name": "Deep Mineral Blue", "name_ja": "深い鉱物青", "code": "#1f4b8f"},
            {"name": "Muted Gold", "name_ja": "鈍い金", "code": "#c9ad57"},
            {"name": "Red Mineral", "name_ja": "赤い鉱物", "code": "#b31b1b"},
            {"name": "Malachite Green", "name_ja": "孔雀石の緑", "code": "#1c8a68"},
            {"name": "Dry Paper", "name_ja": "乾いた紙", "code": "#f1e4c8"},
            {"name": "Basalt Black", "name_ja": "玄武岩の黒", "code": "#1c1b18"},
            {"name": "Desert Ochre", "name_ja": "砂地の黄土", "code": "#bd6f2c"},
            {"name": "Linen Light", "name_ja": "麻布の光", "code": "#e8e4c9"},
        ],
    },
    {
        "id": "vivid_material",
        "name": "Vivid Material",
        "sub": "vivid pigment, lime, stone",
        "sub_ja": "鮮やかな顔料、ライム、石",
        "map": {"black": "#1c1c1c", "white": "#f4f4f4", "red": "#f50087", "blue": "#73c2fb", "green": "#008f39", "gray": "#7d6f66"},
        "swatches": ["#f50087", "#73c2fb", "#008f39", "#ff9800", "#7d6f66", "#fff200", "#f4f4f4", "#1c1c1c"],
        "palette": [
            {"name": "Vivid Rose", "name_ja": "鮮やかな薔薇色", "code": "#f50087"},
            {"name": "Bright Blue", "name_ja": "明るい青", "code": "#73c2fb"},
            {"name": "Fresh Green", "name_ja": "新鮮な緑", "code": "#008f39"},
            {"name": "Orange Marigold", "name_ja": "橙の花", "code": "#ff9800"},
            {"name": "Urban Stone", "name_ja": "都市の石", "code": "#7d6f66"},
            {"name": "Sun Yellow", "name_ja": "太陽の黄", "code": "#fff200"},
            {"name": "Lime White", "name_ja": "ライムの白", "code": "#f4f4f4"},
            {"name": "Volcanic Black", "name_ja": "火山の黒", "code": "#1c1c1c"},
        ],
    },
    {
        "id": "weathered_heritage",
        "name": "Weathered Heritage",
        "sub": "fog, brick, wool, rain",
        "sub_ja": "霧、煉瓦、羊毛、雨",
        "map": {"black": "#1f2933", "white": "#fffdd0", "red": "#b93a32", "blue": "#4169e1", "green": "#004225", "gray": "#708090"},
        "swatches": ["#004225", "#4169e1", "#708090", "#b93a32", "#8b8589", "#fffdd0", "#dcdcdc", "#1f2933"],
        "palette": [
            {"name": "Deep Green", "name_ja": "深い緑", "code": "#004225"},
            {"name": "Rain Blue", "name_ja": "雨の青", "code": "#4169e1"},
            {"name": "Slate Gray", "name_ja": "粘板岩の灰", "code": "#708090"},
            {"name": "Brick Red", "name_ja": "煉瓦の赤", "code": "#b93a32"},
            {"name": "Wool Gray", "name_ja": "羊毛の灰", "code": "#8b8589"},
            {"name": "Cream", "name_ja": "クリーム", "code": "#fffdd0"},
            {"name": "Fog Light", "name_ja": "霧の光", "code": "#dcdcdc"},
            {"name": "Charcoal", "name_ja": "木炭", "code": "#1f2933"},
        ],
    },
    {
        "id": "sea_stone",
        "name": "Sea & Stone",
        "sub": "sea light, stone, dry earth",
        "sub_ja": "海の光、石、乾いた土",
        "map": {"black": "#191970", "white": "#ffffff", "red": "#e2725b", "blue": "#005bae", "green": "#808000", "gray": "#b2beb5"},
        "swatches": ["#ffffff", "#89cff0", "#005bae", "#b2beb5", "#808000", "#f9d71c", "#e2725b", "#191970"],
        "palette": [
            {"name": "Clear White", "name_ja": "澄んだ白", "code": "#ffffff"},
            {"name": "Pale Sea", "name_ja": "淡い海", "code": "#89cff0"},
            {"name": "Deep Sea", "name_ja": "深い海", "code": "#005bae"},
            {"name": "Stone Gray", "name_ja": "石の灰", "code": "#b2beb5"},
            {"name": "Dry Olive", "name_ja": "乾いたオリーブ", "code": "#808000"},
            {"name": "Sun Yellow", "name_ja": "太陽の黄", "code": "#f9d71c"},
            {"name": "Clay Red", "name_ja": "粘土の赤", "code": "#e2725b"},
            {"name": "Night Sea", "name_ja": "夜の海", "code": "#191970"},
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
