package app.inku.mobile.data.model

/**
 * A derivation kind, without its wording.
 *
 * The label used to live here as `labelJa`, which fixed the lineage panel in
 * one language. Which operations exist is the server's judgment and stays here;
 * what they are CALLED is interface wording and lives in `InkuStrings`.
 */
data class DerivationKindInfo(
    val kind: String,
)

object DerivationKindRegistry {
    // Kinds this client records or keeps readable, in sorted order. Retired
    // Touch edges stay distinct from the new tool_change / Touches operation.
    val KINDS: List<String> = listOf(
        "age_change",
        "canvas_aspect_change",
        "catalog_change",
        "color_arrangement_change",
        "ddl_edit",
        "description_edit",
        "external_seed_change",
        "ground_change",
        "hacho_change",
        "language_comparison",
        "layout_change",
        "model_comparison",
        "reinterpretation",
        "render_engine_change",
        "renga_reply",
        "replay",
        "sketch_grain_change",
        "tool_change",
        "touch_change",
        "variation",
    )

    val ALL_INFOS: List<DerivationKindInfo> = KINDS.map { kind -> DerivationKindInfo(kind = kind) }
}
