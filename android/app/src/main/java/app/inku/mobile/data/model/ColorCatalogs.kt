package app.inku.mobile.data.model

data class ColorCatalog(
    val id: String,
    val name: String,
    val sub: String,
    val map: Map<String, String>,
    val swatches: List<String>,
) {
    val renderMap: Map<String, String>
        get() = map + ColorCatalogs.paletteFor(id).mapKeys { "palette:${it.key}" }
}

object ColorCatalogs {
    val all = listOf(
        ColorCatalog("default", "inku Default", "neutral baseline", mapOf("white" to "#ffffff", "black" to "#111111", "blue" to "#2c3e91", "red" to "#a2342a", "green" to "#2f6b3a", "gray" to "#888888"), listOf("#111111", "#ffffff", "#2c3e91", "#a2342a", "#2f6b3a", "#888888", "#555555", "#eeeeee")),
        ColorCatalog("ink_season", "Ink & Season", "ink, paper, seasonal accents", mapOf("black" to "#111111", "white" to "#fffffb", "red" to "#d3381c", "blue" to "#165e83", "green" to "#007b43", "gray" to "#595857"), listOf("#111111", "#fffffb", "#d3381c", "#165e83", "#007b43", "#595857", "#a591c5", "#ffb61e")),
        ColorCatalog("fresco_study", "Fresco Study", "plaster, pigment, warm stone", mapOf("black" to "#4a342e", "white" to "#f5f1e8", "red" to "#c7432f", "blue" to "#1f4e8c", "green" to "#4f7942", "gray" to "#8a8178"), listOf("#8a8178", "#1f4e8c", "#c7432f", "#f7e89f", "#4f7942", "#a0522d", "#f5f1e8", "#4a342e")),
        ColorCatalog("open_air_light", "Open-Air Light", "soft light, sky, reflected shade", mapOf("black" to "#4b4a78", "white" to "#ffffff", "red" to "#ee8fa2", "blue" to "#82c7de", "green" to "#4e8372", "gray" to "#afa6bd"), listOf("#4b4a78", "#ee8fa2", "#ffce00", "#4e8372", "#afa6bd", "#82c7de", "#ffffff", "#fbceb1")),
        ColorCatalog("ink_porcelain", "Ink & Porcelain", "ink, porcelain, mineral accents", mapOf("black" to "#1a1a1b", "white" to "#fffdfa", "red" to "#c91f24", "blue" to "#0057a8", "green" to "#00896c", "gray" to "#4b4b4f"), listOf("#c91f24", "#d6a01d", "#00896c", "#0057a8", "#6a4c8c", "#fffdfa", "#1a1a1b", "#ff4d00")),
        ColorCatalog("cool_material", "Cool Material", "cool light, wood, stone", mapOf("black" to "#2c3e50", "white" to "#fcfcfc", "red" to "#a98467", "blue" to "#4f8fb8", "green" to "#4b5d43", "gray" to "#95a5a6"), listOf("#fcfcfc", "#2c3e50", "#4b5d43", "#95a5a6", "#e5e8e8", "#4f8fb8", "#f4d03f", "#a98467")),
        ColorCatalog("dye_earth", "Dye & Earth", "textile dye, earth, rain shade", mapOf("black" to "#2b2736", "white" to "#fffaf0", "red" to "#b7285f", "blue" to "#006c8f", "green" to "#6b7d3a", "gray" to "#8d7f73"), listOf("#e8862e", "#d6b72a", "#b7285f", "#6b7d3a", "#006c8f", "#d83fb1", "#8d7f73", "#fffaf0")),
        ColorCatalog("desert_mineral", "Desert Mineral", "mineral, linen, desert shadow", mapOf("black" to "#1c1b18", "white" to "#f1e4c8", "red" to "#b31b1b", "blue" to "#1f4b8f", "green" to "#1c8a68", "gray" to "#8f8878"), listOf("#1f4b8f", "#c9ad57", "#b31b1b", "#1c8a68", "#f1e4c8", "#1c1b18", "#bd6f2c", "#e8e4c9")),
        ColorCatalog("vivid_material", "Vivid Material", "vivid pigment, lime, stone", mapOf("black" to "#1c1c1c", "white" to "#f4f4f4", "red" to "#f50087", "blue" to "#73c2fb", "green" to "#008f39", "gray" to "#7d6f66"), listOf("#f50087", "#73c2fb", "#008f39", "#ff9800", "#7d6f66", "#fff200", "#f4f4f4", "#1c1c1c")),
        ColorCatalog("weathered_heritage", "Weathered Heritage", "fog, brick, wool, rain", mapOf("black" to "#1f2933", "white" to "#fffdd0", "red" to "#b93a32", "blue" to "#4169e1", "green" to "#004225", "gray" to "#708090"), listOf("#004225", "#4169e1", "#708090", "#b93a32", "#8b8589", "#fffdd0", "#dcdcdc", "#1f2933")),
        ColorCatalog("sea_stone", "Sea & Stone", "sea light, stone, dry earth", mapOf("black" to "#191970", "white" to "#ffffff", "red" to "#e2725b", "blue" to "#005bae", "green" to "#808000", "gray" to "#b2beb5"), listOf("#ffffff", "#89cff0", "#005bae", "#b2beb5", "#808000", "#f9d71c", "#e2725b", "#191970")),
    )

    private val byId = all.associateBy { it.id }

    fun get(id: String?): ColorCatalog = byId[id] ?: byId.getValue("default")

    fun paletteFor(id: String): Map<String, String> = when (id) {
        "ink_season" -> mapOf("Deep Ink" to "#111111", "Warm Paper" to "#fffffb", "Vermilion Accent" to "#d3381c", "Indigo Shade" to "#165e83", "Evergreen" to "#007b43", "Soft Soot" to "#595857", "Pale Violet" to "#a591c5", "Golden Flower" to "#ffb61e")
        "fresco_study" -> mapOf("Warm Stone" to "#8a8178", "Deep Blue Pigment" to "#1f4e8c", "Red Earth" to "#c7432f", "Soft Yellow" to "#f7e89f", "Green Earth" to "#4f7942", "Burnt Earth" to "#a0522d", "Plaster White" to "#f5f1e8", "Umber Shadow" to "#4a342e")
        "open_air_light" -> mapOf("Violet Gray Shade" to "#4b4a78", "Rose Light" to "#ee8fa2", "Sunlit Yellow" to "#ffce00", "Outdoor Green" to "#4e8372", "Lilac Gray" to "#afa6bd", "Sky Blue" to "#82c7de", "Clear White" to "#ffffff", "Apricot Light" to "#fbceb1")
        "ink_porcelain" -> mapOf("Cinnabar Red" to "#c91f24", "Mineral Gold" to "#d6a01d", "Jade Green" to "#00896c", "Porcelain Blue" to "#0057a8", "Mineral Violet" to "#6a4c8c", "Porcelain White" to "#fffdfa", "Ink Black" to "#1a1a1b", "Bright Vermilion" to "#ff4d00")
        "cool_material" -> mapOf("Snow Light" to "#fcfcfc", "Midnight Blue" to "#2c3e50", "Moss Wood" to "#4b5d43", "Granite Gray" to "#95a5a6", "Pale Birch" to "#e5e8e8", "Muted Sea" to "#4f8fb8", "Low Sun" to "#f4d03f", "Clay Brown" to "#a98467")
        "dye_earth" -> mapOf("Saffron Dye" to "#e8862e", "Yellow Dye" to "#d6b72a", "Deep Rose Dye" to "#b7285f", "Leaf Dye" to "#6b7d3a", "Peacock Blue" to "#006c8f", "Bright Pink" to "#d83fb1", "Wet Earth" to "#8d7f73", "Warm Cotton" to "#fffaf0")
        "desert_mineral" -> mapOf("Deep Mineral Blue" to "#1f4b8f", "Muted Gold" to "#c9ad57", "Red Mineral" to "#b31b1b", "Malachite Green" to "#1c8a68", "Dry Paper" to "#f1e4c8", "Basalt Black" to "#1c1b18", "Desert Ochre" to "#bd6f2c", "Linen Light" to "#e8e4c9")
        "vivid_material" -> mapOf("Vivid Rose" to "#f50087", "Bright Blue" to "#73c2fb", "Fresh Green" to "#008f39", "Orange Marigold" to "#ff9800", "Urban Stone" to "#7d6f66", "Sun Yellow" to "#fff200", "Lime White" to "#f4f4f4", "Volcanic Black" to "#1c1c1c")
        "weathered_heritage" -> mapOf("Deep Green" to "#004225", "Rain Blue" to "#4169e1", "Slate Gray" to "#708090", "Brick Red" to "#b93a32", "Wool Gray" to "#8b8589", "Cream" to "#fffdd0", "Fog Light" to "#dcdcdc", "Charcoal" to "#1f2933")
        "sea_stone" -> mapOf("Clear White" to "#ffffff", "Pale Sea" to "#89cff0", "Deep Sea" to "#005bae", "Stone Gray" to "#b2beb5", "Dry Olive" to "#808000", "Sun Yellow" to "#f9d71c", "Clay Red" to "#e2725b", "Night Sea" to "#191970")
        else -> mapOf("Black" to "#111111", "White" to "#ffffff", "Blue" to "#2c3e91", "Red" to "#a2342a", "Green" to "#2f6b3a", "Gray" to "#888888", "Ink Shade" to "#555555", "Paper" to "#eeeeee")
    }
}
