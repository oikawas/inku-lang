package app.inku.mobile.data.model

data class DerivationKindInfo(
    val kind: String,
    val labelJa: String,
)

object DerivationKindRegistry {
    // The server's `LINEAGE_DERIVATION_KINDS` (db.py:50), sorted, exactly as
    // the baked `lineage_wiring.json` carries it. The six kinds no screen
    // here reaches yet are still listed: which operations exist is the
    // server's judgment, not the client's. (`sketch_grain_change` is the
    // sixth -- there is no 写生 layer on this client.)
    val KINDS: List<String> = listOf(
        "age_change",
        "canvas_aspect_change",
        "catalog_change",
        "ddl_edit",
        "description_edit",
        "external_seed_change",
        "hacho_change",
        "language_comparison",
        "layout_change",
        "model_comparison",
        "reinterpretation",
        "render_engine_change",
        "renga_reply",
        "replay",
        "sketch_grain_change",
        "touch_change",
        "variation",
    )

    private val LABELS_JA: Map<String, String> = mapOf(
        "age_change" to "経年",
        "canvas_aspect_change" to "キャンバス変更",
        "catalog_change" to "色",
        "ddl_edit" to "DDL編集",
        "description_edit" to "記述編集",
        "external_seed_change" to "外部の種",
        "hacho_change" to "破調",
        "language_comparison" to "言語",
        "layout_change" to "構図",
        "model_comparison" to "モデル",
        "reinterpretation" to "解釈",
        "render_engine_change" to "描画エンジン",
        "renga_reply" to "連歌の付句",
        "replay" to "再描画",
        "sketch_grain_change" to "写生の区切り",
        "touch_change" to "タッチ",
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
