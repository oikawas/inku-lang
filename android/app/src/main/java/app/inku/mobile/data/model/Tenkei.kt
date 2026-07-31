package app.inku.mobile.data.model

data class TenkeiItem(
    val id: String,
    val labelJa: String,
)

val TenkeiOptions = listOf(
    TenkeiItem("auto", "自動"),
    TenkeiItem("none", "なし"),
    TenkeiItem("moon", "月"),
    TenkeiItem("cloud", "雲"),
    TenkeiItem("bird", "鳥"),
    TenkeiItem("mountain", "山"),
    TenkeiItem("water", "水"),
)
