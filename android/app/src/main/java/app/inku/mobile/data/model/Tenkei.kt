package app.inku.mobile.data.model

// Staffage level (tenkei, v1.97). Mirrors web/src/lib/tenkei.ts, which is the
// single source for the level values and labels. The level says how much
// staffage the model may add -- it is not a list of motifs.
data class TenkeiItem(
    val id: String,
    val labelJa: String,
    val hintJa: String,
)

val TenkeiOptions = listOf(
    TenkeiItem("none", "なし", "入力に書かれた要素だけを描く"),
    TenkeiItem("sparse", "控えめ", "添景は控えめに、主題より小さく薄く"),
    TenkeiItem("auto", "おまかせ", "現行のまま（添景をAIに任せる）"),
)

const val DEFAULT_TENKEI = "auto"

// Artworks saved before v1.97 have no level recorded; treat them as 'auto'.
fun normalizeTenkei(value: String?): String =
    if (value == "none" || value == "sparse" || value == "auto") value else DEFAULT_TENKEI
