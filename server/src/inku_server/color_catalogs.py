"""Server-owned color catalog definitions."""

from __future__ import annotations

from typing import Any

DEFAULT_COLOR_CATALOG_ID = "default"
COLOR_KEYS = (
    "white", "black", "gray", "red", "orange", "yellow", "green", "blue", "purple",
)

# The swatch strip shown in the UI is a view of `map`, chromatic keys first.
# Android draws the same array twice -- the first four entries in one screen and
# the first eight in another -- so an achromatic-first order would spend those
# slots on black, gray, and white and leave the band colors off screen.
SWATCH_KEY_ORDER = (
    "red", "orange", "yellow", "green", "blue", "purple", "black", "gray", "white",
)

# Catalogs that were renamed. Works saved before a rename still carry the old
# id, and this table is the only thing that can read it back.
#
# It is a nameplate table, never a color one. The colors a work was drawn in
# live in that work's own snapshot, and the id is also seed material for the
# chromatic work-color assignment (renderer._WORK_COLOR_SEED_FIELDS), so
# rewriting the id a work was DRAWN with would repaint it out of the very same
# map -- measured 2026-08-09: 38-70% of seeds land on a different assignment
# across these nine pairs. Hence the migration that uses this touches the
# display column only, and this table is otherwise read at display time.
RENAMED_COLOR_CATALOG_IDS: dict[str, str] = {
    "japanese": "ink_season",
    "mexican": "vivid_material",
    "indian": "dye_earth",
    "british": "weathered_heritage",
    "egyptian": "desert_mineral",
    "impressionism": "open_air_light",
    "greek": "sea_stone",
    "renaissance": "fresco_study",
    "nordic": "cool_material",
    "chinese": "ink_porcelain",
}

_CATALOG_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "default",
        "name": "inku Default",
        "sub": "neutral baseline",
        "sub_ja": "ニュートラルな基準値",
        "map": {"white": "#ffffff", "black": "#111111", "gray": "#888888", "red": "#a2342a", "orange": "#b9671e", "yellow": "#b8901f", "green": "#2f6b3a", "blue": "#2c3e91", "purple": "#6a4d94"},
        "palette": [
            {"name": "Black", "name_ja": "黒", "code": "#111111"},
            {"name": "White", "name_ja": "白", "code": "#ffffff"},
            {"name": "Gray", "name_ja": "灰", "code": "#888888"},
            {"name": "Red", "name_ja": "赤", "code": "#a2342a"},
            {"name": "Green", "name_ja": "緑", "code": "#2f6b3a"},
            {"name": "Blue", "name_ja": "青", "code": "#2c3e91"},
            {"name": "Yellow", "name_ja": "黄", "code": "#b8901f"},
            {"name": "Orange", "name_ja": "橙", "code": "#b9671e"},
            {"name": "Purple", "name_ja": "紫", "code": "#6a4d94"},
            {"name": "Deep Red", "name_ja": "深い赤", "code": "#7c2f26"},
        ],
    },
    {
        "id": "ink_season",
        "name": "Ink & Season",
        "sub": "ink, paper, seasonal accents",
        "sub_ja": "墨、紙、季節の差し色",
        "map": {"white": "#fffffb", "black": "#141210", "gray": "#595857", "red": "#d3381c", "orange": "#ffb61e", "yellow": "#847a2e", "green": "#007b43", "blue": "#165e83", "purple": "#a591c5"},
        "palette": [
            {"name": "Pine Soot", "name_ja": "松煙", "code": "#141210"},
            {"name": "Warm Paper", "name_ja": "胡粉", "code": "#fffffb"},
            {"name": "Soft Soot", "name_ja": "消墨", "code": "#595857"},
            {"name": "Vermilion Accent", "name_ja": "朱", "code": "#d3381c"},
            {"name": "Evergreen", "name_ja": "常磐", "code": "#007b43"},
            {"name": "Indigo Shade", "name_ja": "藍", "code": "#165e83"},
            {"name": "Uguisu", "name_ja": "鶯", "code": "#847a2e"},
            {"name": "Golden Flower", "name_ja": "山吹", "code": "#ffb61e"},
            {"name": "Pale Violet", "name_ja": "藤紫", "code": "#a591c5"},
            {"name": "Madder", "name_ja": "茜", "code": "#8c2d1d"},
        ],
    },
    {
        "id": "fresco_study",
        "name": "Fresco Study",
        "sub": "sunlit wall, dry earth, warm shadow",
        "sub_ja": "日なたの壁、乾いた土、温かい陰",
        "map": {"white": "#f5f1e8", "black": "#4a342e", "gray": "#8a8178", "red": "#c7432f", "orange": "#b06a2f", "yellow": "#c39a2b", "green": "#4f7942", "blue": "#1f4e8c", "purple": "#71487c"},
        "palette": [
            {"name": "Umber Shadow", "name_ja": "アンバーの影", "code": "#4a342e"},
            {"name": "Plaster White", "name_ja": "漆喰の白", "code": "#f5f1e8"},
            {"name": "Warm Stone", "name_ja": "温かい石", "code": "#8a8178"},
            {"name": "Red Earth", "name_ja": "赤土", "code": "#c7432f"},
            {"name": "Green Earth", "name_ja": "緑土", "code": "#4f7942"},
            {"name": "Deep Blue Pigment", "name_ja": "深い青顔料", "code": "#1f4e8c"},
            {"name": "Yellow Ocher", "name_ja": "黄土", "code": "#c39a2b"},
            {"name": "Raw Sienna", "name_ja": "シエナ土", "code": "#b06a2f"},
            {"name": "Manganese Violet", "name_ja": "マンガン紫", "code": "#71487c"},
            {"name": "Burnt Earth", "name_ja": "焼けた土", "code": "#a0522d"},
        ],
    },
    {
        "id": "open_air_light",
        "name": "Open-Air Light",
        "sub": "soft light, sky, reflected shade",
        "sub_ja": "柔らかな光、空、反射する陰",
        "map": {"white": "#fdfeff", "black": "#43474e", "gray": "#afa6bd", "red": "#ee8fa2", "orange": "#f0b184", "yellow": "#a3bd5b", "green": "#4e8372", "blue": "#82c7de", "purple": "#4b4a78"},
        "palette": [
            {"name": "River Stone", "name_ja": "川石", "code": "#43474e"},
            {"name": "Zinc White", "name_ja": "亜鉛華", "code": "#fdfeff"},
            {"name": "Lilac Gray", "name_ja": "ライラック灰", "code": "#afa6bd"},
            {"name": "Rose Light", "name_ja": "薔薇色の光", "code": "#ee8fa2"},
            {"name": "Outdoor Green", "name_ja": "戸外の緑", "code": "#4e8372"},
            {"name": "Sky Blue", "name_ja": "空色", "code": "#82c7de"},
            {"name": "Young Grass", "name_ja": "若草", "code": "#a3bd5b"},
            {"name": "Apricot Shade", "name_ja": "杏の陰", "code": "#f0b184"},
            {"name": "Violet Gray Shade", "name_ja": "菫灰の陰", "code": "#4b4a78"},
            {"name": "Sunlit Yellow", "name_ja": "陽だまりの黄", "code": "#ffce00"},
        ],
    },
    {
        "id": "ink_porcelain",
        "name": "Ink & Porcelain",
        "sub": "clear light, ink, sharp mineral accents",
        "sub_ja": "澄んだ光、墨、冴えた鉱物の差し色",
        "map": {"white": "#fffdfa", "black": "#1a1a1b", "gray": "#4b4b4f", "red": "#c91f24", "orange": "#b5642c", "yellow": "#d6a01d", "green": "#00896c", "blue": "#0057a8", "purple": "#6a4c8c"},
        "palette": [
            {"name": "Ink Black", "name_ja": "墨の黒", "code": "#1a1a1b"},
            {"name": "Porcelain White", "name_ja": "磁器の白", "code": "#fffdfa"},
            {"name": "Kiln Soot", "name_ja": "窯の煤", "code": "#4b4b4f"},
            {"name": "Cinnabar Red", "name_ja": "辰砂の赤", "code": "#c91f24"},
            {"name": "Jade Green", "name_ja": "翡翠の緑", "code": "#00896c"},
            {"name": "Porcelain Blue", "name_ja": "磁器の青", "code": "#0057a8"},
            {"name": "Mineral Gold", "name_ja": "鉱物の金", "code": "#d6a01d"},
            {"name": "Copper Overglaze", "name_ja": "銅の上絵", "code": "#b5642c"},
            {"name": "Mineral Violet", "name_ja": "鉱物の紫", "code": "#6a4c8c"},
            {"name": "Bright Vermilion", "name_ja": "明るい朱", "code": "#ff4d00"},
        ],
    },
    {
        "id": "cool_material",
        "name": "Cool Material",
        "sub": "cool light, wood, stone",
        "sub_ja": "冷たい光、木、石",
        "map": {"white": "#fcfcfc", "black": "#26282a", "gray": "#95a5a6", "red": "#6f4340", "orange": "#a98467", "yellow": "#4b5d43", "green": "#3a544a", "blue": "#4f8fb8", "purple": "#575168"},
        "palette": [
            {"name": "Graphite", "name_ja": "石墨", "code": "#26282a"},
            {"name": "Snow Light", "name_ja": "雪の光", "code": "#fcfcfc"},
            {"name": "Granite Gray", "name_ja": "花崗岩の灰", "code": "#95a5a6"},
            {"name": "Rowan Berry", "name_ja": "ナナカマドの実", "code": "#6f4340"},
            {"name": "Spruce", "name_ja": "唐檜", "code": "#3a544a"},
            {"name": "Muted Sea", "name_ja": "鈍い海色", "code": "#4f8fb8"},
            {"name": "Moss Wood", "name_ja": "苔むした木", "code": "#4b5d43"},
            {"name": "Clay Brown", "name_ja": "粘土の茶", "code": "#a98467"},
            {"name": "Slate Violet", "name_ja": "粘板岩の紫", "code": "#575168"},
            {"name": "Midnight Blue", "name_ja": "真夜中の青", "code": "#2c3e50"},
        ],
    },
    {
        "id": "dye_earth",
        "name": "Dye & Earth",
        "sub": "textile dye, earth, rain shade",
        "sub_ja": "布の染料、土、雨の陰",
        "map": {"white": "#fffaf0", "black": "#2b2736", "gray": "#8d7f73", "red": "#b7285f", "orange": "#e8862e", "yellow": "#d6b72a", "green": "#33684a", "blue": "#006c8f", "purple": "#d83fb1"},
        "palette": [
            {"name": "Iron Mordant", "name_ja": "鉄媒染", "code": "#2b2736"},
            {"name": "Warm Cotton", "name_ja": "温かな綿", "code": "#fffaf0"},
            {"name": "Wet Earth", "name_ja": "濡れた土", "code": "#8d7f73"},
            {"name": "Deep Rose Dye", "name_ja": "深い薔薇染め", "code": "#b7285f"},
            {"name": "Indigo-Leaf Green", "name_ja": "藍葉の緑", "code": "#33684a"},
            {"name": "Peacock Blue", "name_ja": "孔雀青", "code": "#006c8f"},
            {"name": "Yellow Dye", "name_ja": "黄色の染料", "code": "#d6b72a"},
            {"name": "Saffron Dye", "name_ja": "サフラン染め", "code": "#e8862e"},
            {"name": "Bright Pink", "name_ja": "明るい桃色", "code": "#d83fb1"},
            {"name": "Leaf Dye", "name_ja": "葉の染料", "code": "#6b7d3a"},
        ],
    },
    {
        "id": "vivid_material",
        "name": "Vivid Material",
        "sub": "vivid pigment, lime, stone",
        "sub_ja": "鮮やかな顔料、ライム、石",
        "map": {"white": "#f4f4f4", "black": "#1c1c1c", "gray": "#7d6f66", "red": "#f50087", "orange": "#ff9800", "yellow": "#c7a000", "green": "#008f39", "blue": "#73c2fb", "purple": "#8a4fc9"},
        "palette": [
            {"name": "Volcanic Black", "name_ja": "火山の黒", "code": "#1c1c1c"},
            {"name": "Lime White", "name_ja": "ライムの白", "code": "#f4f4f4"},
            {"name": "Urban Stone", "name_ja": "都市の石", "code": "#7d6f66"},
            {"name": "Vivid Rose", "name_ja": "鮮やかな薔薇色", "code": "#f50087"},
            {"name": "Fresh Green", "name_ja": "新鮮な緑", "code": "#008f39"},
            {"name": "Bright Blue", "name_ja": "明るい青", "code": "#73c2fb"},
            {"name": "Deep Cadmium Yellow", "name_ja": "深いカドミウム黄", "code": "#c7a000"},
            {"name": "Orange Marigold", "name_ja": "橙の花", "code": "#ff9800"},
            {"name": "Cobalt Violet", "name_ja": "コバルト紫", "code": "#8a4fc9"},
            {"name": "Sun Yellow", "name_ja": "太陽の黄", "code": "#fff200"},
        ],
    },
    {
        "id": "weathered_heritage",
        "name": "Weathered Heritage",
        "sub": "fog, brick, wool, rain",
        "sub_ja": "霧、煉瓦、羊毛、雨",
        "map": {"white": "#dcdcdc", "black": "#1f2933", "gray": "#708090", "red": "#b93a32", "orange": "#9e6428", "yellow": "#9b8342", "green": "#004225", "blue": "#4169e1", "purple": "#7b6293"},
        "palette": [
            {"name": "Charcoal", "name_ja": "木炭", "code": "#1f2933"},
            {"name": "Fog Light", "name_ja": "霧の光", "code": "#dcdcdc"},
            {"name": "Slate Gray", "name_ja": "粘板岩の灰", "code": "#708090"},
            {"name": "Brick Red", "name_ja": "煉瓦の赤", "code": "#b93a32"},
            {"name": "Deep Green", "name_ja": "深い緑", "code": "#004225"},
            {"name": "Rain Blue", "name_ja": "雨の青", "code": "#4169e1"},
            {"name": "Tarnished Brass", "name_ja": "くすんだ真鍮", "code": "#9b8342"},
            {"name": "Iron Rust", "name_ja": "鉄錆", "code": "#9e6428"},
            {"name": "Heather", "name_ja": "ヒース", "code": "#7b6293"},
            {"name": "Wet Moss", "name_ja": "濡れた苔", "code": "#48684d"},
        ],
    },
    {
        "id": "sea_stone",
        "name": "Sea & Stone",
        "sub": "sea light, stone, dry earth",
        "sub_ja": "海の光、石、乾いた土",
        "map": {"white": "#f2f7f7", "black": "#10141a", "gray": "#b2beb5", "red": "#e2725b", "orange": "#c97a45", "yellow": "#808000", "green": "#2e613b", "blue": "#005bae", "purple": "#191970"},
        "palette": [
            {"name": "Abyss Dark", "name_ja": "深海の闇", "code": "#10141a"},
            {"name": "Sea Foam White", "name_ja": "泡の白", "code": "#f2f7f7"},
            {"name": "Stone Gray", "name_ja": "石の灰", "code": "#b2beb5"},
            {"name": "Clay Red", "name_ja": "粘土の赤", "code": "#e2725b"},
            {"name": "Sea Kelp Green", "name_ja": "海藻の緑", "code": "#2e613b"},
            {"name": "Deep Sea", "name_ja": "深い海", "code": "#005bae"},
            {"name": "Dry Olive", "name_ja": "乾いたオリーブ", "code": "#808000"},
            {"name": "Coral Orange", "name_ja": "珊瑚の橙", "code": "#c97a45"},
            {"name": "Night Sea", "name_ja": "夜の海", "code": "#191970"},
            {"name": "Pale Sea", "name_ja": "淡い海", "code": "#89cff0"},
        ],
    },
    {
        "id": "moss_bark",
        "name": "Moss & Bark",
        "sub": "bark, leaf, moss, dappled light",
        "sub_ja": "樹皮、葉、苔、木漏れ日",
        "map": {"white": "#f2efe8", "black": "#181a17", "gray": "#9ba39e", "red": "#9c3330", "orange": "#7d5531", "yellow": "#d5ae43", "green": "#3e5a41", "blue": "#43798a", "purple": "#57355f"},
        "palette": [
            {"name": "Forest Dark", "name_ja": "森の闇", "code": "#181a17"},
            {"name": "Birch Bark", "name_ja": "白樺の肌", "code": "#f2efe8"},
            {"name": "Morning Fog", "name_ja": "朝霧の灰", "code": "#9ba39e"},
            {"name": "Ripe Berry", "name_ja": "熟した実", "code": "#9c3330"},
            {"name": "Moss", "name_ja": "苔", "code": "#3e5a41"},
            {"name": "Ravine Water", "name_ja": "沢の水", "code": "#43798a"},
            {"name": "Dappled Light", "name_ja": "木漏れ日", "code": "#d5ae43"},
            {"name": "Bark", "name_ja": "樹皮", "code": "#7d5531"},
            {"name": "Wild Grape", "name_ja": "山葡萄", "code": "#57355f"},
            {"name": "New Leaf", "name_ja": "若葉", "code": "#5da55f"},
        ],
    },
    {
        "id": "neon_plate",
        "name": "Neon & Plate",
        "sub": "discharge tube, printing plate, coating",
        "sub_ja": "放電管、印刷版、被膜",
        "map": {"white": "#f4f8fb", "black": "#0d0d10", "gray": "#777c82", "red": "#e5004b", "orange": "#ff8514", "yellow": "#e3b800", "green": "#00c853", "blue": "#2f52d9", "purple": "#7a2fd0"},
        "palette": [
            {"name": "Unlit Pixel", "name_ja": "消灯画素", "code": "#0d0d10"},
            {"name": "Diffuser White", "name_ja": "拡散板の白", "code": "#f4f8fb"},
            {"name": "Housing Gray", "name_ja": "筐体の灰", "code": "#777c82"},
            {"name": "Signal Red", "name_ja": "標識の赤", "code": "#e5004b"},
            {"name": "Emitter Green", "name_ja": "発光体の緑", "code": "#00c853"},
            {"name": "Discharge Blue", "name_ja": "放電の青", "code": "#2f52d9"},
            {"name": "Halftone Yellow", "name_ja": "網点の黄", "code": "#e3b800"},
            {"name": "Safety Coating", "name_ja": "安全被膜", "code": "#ff8514"},
            {"name": "Tube Violet", "name_ja": "放電管の菫", "code": "#7a2fd0"},
            {"name": "Cyan Plate", "name_ja": "シアン版", "code": "#00b7eb"},
        ],
    },
    {
        "id": "lantern_dew",
        "name": "Lantern & Dew",
        "sub": "night air, lantern, dew",
        "sub_ja": "夜気、灯火、露",
        "map": {"white": "#e6e8ec", "black": "#121216", "gray": "#4d4e54", "red": "#6d2a23", "orange": "#c78c33", "yellow": "#c9b34a", "green": "#2b4234", "blue": "#1e2e52", "purple": "#453a6e"},
        "palette": [
            {"name": "New Moon", "name_ja": "新月の黒", "code": "#121216"},
            {"name": "Dew White", "name_ja": "露の白", "code": "#e6e8ec"},
            {"name": "Night Air", "name_ja": "夜気の灰", "code": "#4d4e54"},
            {"name": "Ember", "name_ja": "熾火の赤", "code": "#6d2a23"},
            {"name": "Night Moss", "name_ja": "夜の苔", "code": "#2b4234"},
            {"name": "Night Indigo", "name_ja": "夜の藍", "code": "#1e2e52"},
            {"name": "Firefly", "name_ja": "蛍の黄", "code": "#c9b34a"},
            {"name": "Lantern Amber", "name_ja": "灯火の琥珀", "code": "#c78c33"},
            {"name": "Twilight Violet", "name_ja": "薄明の菫", "code": "#453a6e"},
            {"name": "Mulberry", "name_ja": "桑の実", "code": "#402445"},
        ],
    },
)


def _with_swatches(catalog: dict[str, Any]) -> dict[str, Any]:
    """Derive the swatch strip from `map` so the two cannot drift apart."""
    color_map: dict[str, str] = catalog["map"]
    return {
        "id": catalog["id"],
        "name": catalog["name"],
        "sub": catalog["sub"],
        "sub_ja": catalog["sub_ja"],
        "map": color_map,
        "swatches": [color_map[key] for key in SWATCH_KEY_ORDER],
        "palette": catalog["palette"],
    }


COLOR_CATALOGS: tuple[dict[str, Any], ...] = tuple(
    _with_swatches(catalog) for catalog in _CATALOG_DEFINITIONS
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


def current_color_catalog_id(catalog_id: str | None) -> str | None:
    """Today's id for a possibly-renamed one.

    Returns None when nothing current answers to it -- a retired catalog. That
    is a fact about the nameplate only: a work carrying a retired id still
    draws, because its colors come from its own snapshot.
    """
    if catalog_id is None:
        return DEFAULT_COLOR_CATALOG_ID
    resolved = RENAMED_COLOR_CATALOG_IDS.get(catalog_id, catalog_id)
    return resolved if get_color_catalog(resolved) is not None else None


def render_color_map_for_catalog(catalog_id: str | None) -> dict[str, str] | None:
    catalog = get_color_catalog(catalog_id)
    if catalog is None:
        return None
    color_map: dict[str, str] = dict(catalog["map"])
    for color in catalog["palette"]:
        color_map[f"palette:{color['name']}"] = color["code"]
    return color_map
