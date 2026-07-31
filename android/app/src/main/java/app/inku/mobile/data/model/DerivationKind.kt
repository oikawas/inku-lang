package app.inku.mobile.data.model

data class DerivationKindInfo(
    val kind: String,
    val labelJa: String,
)

object DerivationKindRegistry {
    val KINDS: List<String> = listOf(
        "touch_change",
        "layout_change",
        "catalog_change",
        "reinterpretation",
        "model_comparison",
        "language_comparison",
        "ddl_edit",
        "description_edit",
        "replay",
        "canvas_aspect_change",
        "variation",
    )

    private val LABELS_JA: Map<String, String> = mapOf(
        "touch_change" to "タッチ",
        "layout_change" to "構図",
        "catalog_change" to "色",
        "reinterpretation" to "解釈",
        "model_comparison" to "モデル",
        "language_comparison" to "言語",
        "ddl_edit" to "DDL編集",
        "description_edit" to "記述編集",
        "replay" to "再描画",
        "canvas_aspect_change" to "キャンバス変更",
        "variation" to "変奏",
    )

    fun labelJa(kind: String?): String {
        if (kind.isNullOrEmpty()) return "起点"
        return LABELS_JA[kind] ?: "不明"
    }

    val ALL_INFOS: List<DerivationKindInfo> = KINDS.map { kind ->
        DerivationKindInfo(kind = kind, labelJa = labelJa(kind))
    }
}
