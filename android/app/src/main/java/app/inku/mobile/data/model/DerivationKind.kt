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
    // The server's `LINEAGE_DERIVATION_KINDS` (db.py:50), sorted, exactly as
    // the baked `lineage_wiring.json` carries it. The five kinds no screen
    // here reaches yet are still listed: which operations exist is the
    // server's judgment, not the client's. (`sketch_grain_change` used to be a
    // sixth; the 写生 layer arrived with contract 5/5 and the describe screen
    // writes that edge now -- `SubmitDerivationKind.forDescribeSubmit`.)
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

    val ALL_INFOS: List<DerivationKindInfo> = KINDS.map { kind -> DerivationKindInfo(kind = kind) }
}
