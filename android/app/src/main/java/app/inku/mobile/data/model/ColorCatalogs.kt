package app.inku.mobile.data.model

data class ColorCatalog(
    val id: String,
    val name: String,
    val sub: String,
    val map: Map<String, String>,
) {
    val swatches: List<String> = ColorCatalogs.SWATCH_KEY_ORDER.mapNotNull { map[it] }

    val renderMap: Map<String, String>
        get() = map + ColorCatalogs.paletteFor(id).mapKeys { "palette:${it.key}" }
}

object ColorCatalogs {
    val SWATCH_KEY_ORDER = listOf(
        "red", "orange", "yellow", "green", "blue", "purple", "black", "gray", "white"
    )

    val all = listOf(
        ColorCatalog(
            "default", "inku Default", "neutral baseline",
            mapOf("white" to "#ffffff", "black" to "#111111", "gray" to "#888888", "red" to "#a2342a", "orange" to "#b9671e", "yellow" to "#b8901f", "green" to "#2f6b3a", "blue" to "#2c3e91", "purple" to "#6a4d94")
        ),
        ColorCatalog(
            "ink_season", "Ink & Season", "ink, paper, seasonal accents",
            mapOf("white" to "#fffffb", "black" to "#141210", "gray" to "#595857", "red" to "#d3381c", "orange" to "#ffb61e", "yellow" to "#847a2e", "green" to "#007b43", "blue" to "#165e83", "purple" to "#a591c5")
        ),
        ColorCatalog(
            "fresco_study", "Fresco Study", "sunlit wall, dry earth, warm shadow",
            mapOf("white" to "#f5f1e8", "black" to "#4a342e", "gray" to "#8a8178", "red" to "#c7432f", "orange" to "#b06a2f", "yellow" to "#c39a2b", "green" to "#4f7942", "blue" to "#1f4e8c", "purple" to "#71487c")
        ),
        ColorCatalog(
            "open_air_light", "Open-Air Light", "soft light, sky, reflected shade",
            mapOf("white" to "#fdfeff", "black" to "#43474e", "gray" to "#afa6bd", "red" to "#ee8fa2", "orange" to "#f0b184", "yellow" to "#a3bd5b", "green" to "#4e8372", "blue" to "#82c7de", "purple" to "#4b4a78")
        ),
        ColorCatalog(
            "ink_porcelain", "Ink & Porcelain", "clear light, ink, sharp mineral accents",
            mapOf("white" to "#fffdfa", "black" to "#1a1a1b", "gray" to "#4b4b4f", "red" to "#c91f24", "orange" to "#b5642c", "yellow" to "#d6a01d", "green" to "#00896c", "blue" to "#0057a8", "purple" to "#6a4c8c")
        ),
        ColorCatalog(
            "cool_material", "Cool Material", "cool light, wood, stone",
            mapOf("white" to "#fcfcfc", "black" to "#26282a", "gray" to "#95a5a6", "red" to "#6f4340", "orange" to "#a98467", "yellow" to "#4b5d43", "green" to "#3a544a", "blue" to "#4f8fb8", "purple" to "#575168")
        ),
        ColorCatalog(
            "dye_earth", "Dye & Earth", "textile dye, earth, rain shade",
            mapOf("white" to "#fffaf0", "black" to "#2b2736", "gray" to "#8d7f73", "red" to "#b7285f", "orange" to "#e8862e", "yellow" to "#d6b72a", "green" to "#33684a", "blue" to "#006c8f", "purple" to "#d83fb1")
        ),
        ColorCatalog(
            "vivid_material", "Vivid Material", "vivid pigment, lime, stone",
            mapOf("white" to "#f4f4f4", "black" to "#1c1c1c", "gray" to "#7d6f66", "red" to "#f50087", "orange" to "#ff9800", "yellow" to "#c7a000", "green" to "#008f39", "blue" to "#73c2fb", "purple" to "#8a4fc9")
        ),
        ColorCatalog(
            "weathered_heritage", "Weathered Heritage", "fog, brick, wool, rain",
            mapOf("white" to "#dcdcdc", "black" to "#1f2933", "gray" to "#708090", "red" to "#b93a32", "orange" to "#9e6428", "yellow" to "#9b8342", "green" to "#004225", "blue" to "#4169e1", "purple" to "#7b6293")
        ),
        ColorCatalog(
            "sea_stone", "Sea & Stone", "sea light, stone, dry earth",
            mapOf("white" to "#f2f7f7", "black" to "#10141a", "gray" to "#b2beb5", "red" to "#e2725b", "orange" to "#c97a45", "yellow" to "#808000", "green" to "#2e613b", "blue" to "#005bae", "purple" to "#191970")
        ),
        ColorCatalog(
            "moss_bark", "Moss & Bark", "bark, leaf, moss, dappled light",
            mapOf("white" to "#f2efe7", "black" to "#181a17", "gray" to "#9ba39e", "red" to "#9c3330", "orange" to "#7d5531", "yellow" to "#d5ae43", "green" to "#3e5a41", "blue" to "#43798a", "purple" to "#57355f")
        ),
        ColorCatalog(
            "neon_plate", "Neon & Plate", "discharge tube, printing plate, coating",
            mapOf("white" to "#f4f8fb", "black" to "#0d0d10", "gray" to "#777c82", "red" to "#e5004b", "orange" to "#ff8514", "yellow" to "#e3b800", "green" to "#00c853", "blue" to "#2f52d9", "purple" to "#7a2fd0")
        ),
        ColorCatalog(
            "lantern_dew", "Lantern & Dew", "night air, lantern, dew",
            mapOf("white" to "#e6e8ec", "black" to "#121216", "gray" to "#4d4e54", "red" to "#6d2a23", "orange" to "#c78c33", "yellow" to "#c9b34a", "green" to "#2b4234", "blue" to "#1e2e52", "purple" to "#453a6e")
        ),
    )

    private val byId = all.associateBy { it.id }

    fun get(id: String?): ColorCatalog = byId[id] ?: byId.getValue("default")

    fun paletteFor(id: String): Map<String, String> = when (id) {
        "default" -> mapOf("Black" to "#111111", "White" to "#ffffff", "Gray" to "#888888", "Red" to "#a2342a", "Green" to "#2f6b3a", "Blue" to "#2c3e91", "Yellow" to "#b8901f", "Orange" to "#b9671e", "Purple" to "#6a4d94", "Deep Red" to "#7c2f26")
        "ink_season" -> mapOf("Pine Soot" to "#141210", "Warm Paper" to "#fffffb", "Soft Soot" to "#595857", "Vermilion Accent" to "#d3381c", "Evergreen" to "#007b43", "Indigo Shade" to "#165e83", "Uguisu" to "#847a2e", "Golden Flower" to "#ffb61e", "Pale Violet" to "#a591c5", "Madder" to "#8c2d1d")
        "fresco_study" -> mapOf("Umber Shadow" to "#4a342e", "Plaster White" to "#f5f1e8", "Warm Stone" to "#8a8178", "Red Earth" to "#c7432f", "Green Earth" to "#4f7942", "Deep Blue Pigment" to "#1f4e8c", "Yellow Ocher" to "#c39a2b", "Raw Sienna" to "#b06a2f", "Manganese Violet" to "#71487c", "Burnt Earth" to "#a0522d")
        "open_air_light" -> mapOf("River Stone" to "#43474e", "Zinc White" to "#fdfeff", "Lilac Gray" to "#afa6bd", "Rose Light" to "#ee8fa2", "Outdoor Green" to "#4e8372", "Sky Blue" to "#82c7de", "Young Grass" to "#a3bd5b", "Apricot Shade" to "#f0b184", "Violet Gray Shade" to "#4b4a78", "Sunlit Yellow" to "#ffce00")
        "ink_porcelain" -> mapOf("Ink Black" to "#1a1a1b", "Porcelain White" to "#fffdfa", "Kiln Soot" to "#4b4b4f", "Cinnabar Red" to "#c91f24", "Jade Green" to "#00896c", "Porcelain Blue" to "#0057a8", "Mineral Gold" to "#d6a01d", "Copper Overglaze" to "#b5642c", "Mineral Violet" to "#6a4c8c", "Bright Vermilion" to "#ff4d00")
        "cool_material" -> mapOf("Graphite" to "#26282a", "Snow Light" to "#fcfcfc", "Granite Gray" to "#95a5a6", "Rowan Berry" to "#6f4340", "Spruce" to "#3a544a", "Muted Sea" to "#4f8fb8", "Moss Wood" to "#4b5d43", "Clay Brown" to "#a98467", "Slate Violet" to "#575168", "Midnight Blue" to "#2c3e50")
        "dye_earth" -> mapOf("Iron Mordant" to "#2b2736", "Warm Cotton" to "#fffaf0", "Wet Earth" to "#8d7f73", "Deep Rose Dye" to "#b7285f", "Indigo-Leaf Green" to "#33684a", "Peacock Blue" to "#006c8f", "Yellow Dye" to "#d6b72a", "Saffron Dye" to "#e8862e", "Bright Pink" to "#d83fb1", "Leaf Dye" to "#6b7d3a")
        "vivid_material" -> mapOf("Volcanic Black" to "#1c1c1c", "Lime White" to "#f4f4f4", "Urban Stone" to "#7d6f66", "Vivid Rose" to "#f50087", "Fresh Green" to "#008f39", "Bright Blue" to "#73c2fb", "Deep Cadmium Yellow" to "#c7a000", "Orange Marigold" to "#ff9800", "Cobalt Violet" to "#8a4fc9", "Sun Yellow" to "#fff200")
        "weathered_heritage" -> mapOf("Charcoal" to "#1f2933", "Fog Light" to "#dcdcdc", "Slate Gray" to "#708090", "Brick Red" to "#b93a32", "Deep Green" to "#004225", "Rain Blue" to "#4169e1", "Tarnished Brass" to "#9b8342", "Iron Rust" to "#9e6428", "Heather" to "#7b6293", "Wet Moss" to "#48684d")
        "sea_stone" -> mapOf("Abyss Dark" to "#10141a", "Sea Foam White" to "#f2f7f7", "Stone Gray" to "#b2beb5", "Clay Red" to "#e2725b", "Sea Kelp Green" to "#2e613b", "Deep Sea" to "#005bae", "Dry Olive" to "#808000", "Coral Orange" to "#c97a45", "Night Sea" to "#191970", "Pale Sea" to "#89cff0")
        "moss_bark" -> mapOf("Forest Dark" to "#181a17", "Birch Bark" to "#f2efe8", "Morning Fog" to "#9ba39e", "Ripe Berry" to "#9c3330", "Moss" to "#3e5a41", "Ravine Water" to "#43798a", "Dappled Light" to "#d5ae43", "Bark" to "#7d5531", "Wild Grape" to "#57355f", "New Leaf" to "#5da55f")
        "neon_plate" -> mapOf("Unlit Pixel" to "#0d0d10", "Diffuser White" to "#f4f8fb", "Housing Gray" to "#777c82", "Signal Red" to "#e5004b", "Emitter Green" to "#00c853", "Discharge Blue" to "#2f52d9", "Halftone Yellow" to "#e3b800", "Safety Coating" to "#ff8514", "Tube Violet" to "#7a2fd0", "Cyan Plate" to "#00b7eb")
        "lantern_dew" -> mapOf("New Moon" to "#121216", "Dew White" to "#e6e8ec", "Night Air" to "#4d4e54", "Ember" to "#6d2a23", "Night Moss" to "#2b4234", "Night Indigo" to "#1e2e52", "Firefly" to "#c9b34a", "Lantern Amber" to "#c78c33", "Twilight Violet" to "#453a6e", "Mulberry" to "#402445")
        else -> mapOf("Black" to "#111111", "White" to "#ffffff", "Gray" to "#888888", "Red" to "#a2342a", "Green" to "#2f6b3a", "Blue" to "#2c3e91", "Yellow" to "#b8901f", "Orange" to "#b9671e", "Purple" to "#6a4d94", "Deep Red" to "#7c2f26")
    }
}
