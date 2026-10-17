package app.inku.mobile.data.refinement

import app.inku.mobile.data.DdlSource
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.drawnWild
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.data.model.workColorSnapshot
import app.inku.mobile.pipeline.RecomposeMode
import app.inku.mobile.ui.i18n.inkuError

/**
 * The one intervention a round of refinement makes.
 *
 * A refinement selects color catalog or layout.
 * That is why this is an enum and not a set
 * of flags -- 「系譜の各辺を単一の介入として説明可能にするため」, and a lineage edge
 * whose cause is two things at once cannot be labelled with one kind.
 */
enum class RefinementElement(val id: String, val derivationKind: String) {
    Color("color", "catalog_change"),
    Layout("layout", "layout_change"),
    ;

    companion object {
        fun byId(id: String?): RefinementElement? = entries.firstOrNull { it.id == id }
    }
}

/**
 * Which drawing path a candidate takes.
 *
 * The names are the repository's entry points, which are in turn the server's
 * three routes: re-render the Score that is already there, compose a new Score
 * from the DDL that is already there, or read the description again from the top.
 */
enum class RefinementRoute {
    RenderFromScore,
    ComposeFromDdl,
    Paint,
}

/**
 * The work a refinement hangs off, read off its history row.
 *
 * Everything here comes from the *stored* work. Nothing reads the describe
 * screen: SPEC `:614` -- 「色以外のすべての推敲は、次回描画の設定ではなく表示中の
 * 親作品の実効カタログとキャンバスを継承する」 -- and a plan built from the current
 * selection would hand back a candidate in a colour the parent never had.
 */
data class RefinementParent(
    val historyId: String,
    val lineageNodeId: String?,
    val description: String,
    val ddl: String,
    val scoreJson: String,
    val catalogId: String,
    val canvasAspect: String,
    val stage1Model: String,
    val stage2Model: String,
    val seeds: PaintSeeds,
    /**
     * The 写生 (Stage 0.5) prose the parent was painted from, and the grain it
     * was cut at. A refinement varies a stage *after* 0.5, so it inherits the
     * prose rather than asking the layer for a new one -- web hands the same
     * string to every candidate (`sketchText: sketchTextFor(source)`,
     * +page.svelte:5116). Drawing a refinement from the raw description instead
     * would make it a refinement of a work nobody made.
     */
    val sketchText: String? = null,
    val sketchGrain: String? = null,
    val workColorSnapshot: WorkColorSnapshot? = null,
    /** Wild as the parent was drawn; a candidate inherits it like web's `effectiveRefineWild`. */
    val renderWild: Boolean = false,
) {
    companion object {
        /**
         * @param description the prose to paint from. The caller strips the
         *   bookkeeping a batch or demo line put in front of `originalInput`,
         *   the way `descriptionChanged` already does; the server reads its
         *   `source_text` column for the same string, and this client has none.
         */
        fun of(item: HistoryItemEntity, description: String): RefinementParent = RefinementParent(
            historyId = item.id,
            lineageNodeId = item.lineageNodeId,
            description = description,
            ddl = item.normalizedDdl.orEmpty(),
            scoreJson = item.scoreJson,
            catalogId = item.colorCatalogId,
            canvasAspect = item.canvasAspect,
            stage1Model = item.stage1Model ?: "",
            stage2Model = item.stage2Model ?: "",
            seeds = PaintSeeds.of(item),
            sketchText = item.sketchText,
            sketchGrain = item.sketchGrain,
            workColorSnapshot = workColorSnapshot(item.renderMetadataJson),
            renderWild = item.drawnWild,
        )
    }
}

/**
 * One candidate's orders: which road to take, what to hold still, what to vary,
 * and what the lineage edge will say.
 *
 * [seeds] is the whole answer to "what is fixed and what moves". A field that
 * carries the parent's value is fixed; a field that carries a new value is the
 * one thing this round varies. There is no second place where a seed is decided.
 */
data class RefinementPlan(
    /** Null for a model comparison or a saved-Score action outside the two ordinary elements. */
    val element: RefinementElement?,
    val route: RefinementRoute,
    val catalogId: String,
    val canvasAspect: String,
    val seeds: PaintSeeds,
    val derivationKind: String,
    val derivationMetadata: Map<String, Any?>,
    /**
     * What a comparison candidate overrides. `null` is "the parent's", which is
     * every field for an ordinary refinement.
     */
    val stage1Model: String? = null,
    val stage2Model: String? = null,
    val recomposeMode: RecomposeMode? = null,
    val toolChange: ToolChangeOption? = null,
    /** A saved-Score variant changes these bytes without recompiling its DDL. */
    val scoreOverrideJson: String? = null,
    val ddlOverride: String? = null,
    val workColorSnapshotOverride: WorkColorSnapshot? = null,
    /** Null keeps the saved parent's Wild setting. */
    val renderWildOverride: Boolean? = null,
)

/**
 * Builds the orders for one candidate.
 *
 * The truth table is SPEC `:614` / `:678` and the derivation kinds the server
 * registers, written out once so that the screen, the save and the tests all
 * read the same decision.
 */
object RefinementPlanner {

    /**
     * @param element the single intervention. One value, never a collection:
     *   there is no way to spell "layout and colour" here, which is what makes
     *   the exclusivity a property of the type rather than of a check.
     * @param newCatalogId the catalogue to apply, for the colour refinement only.
     */
    fun plan(
        element: RefinementElement,
        parent: RefinementParent,
        newCatalogId: String? = null,
        recomposeMode: RecomposeMode = RecomposeMode.Principled,
    ): RefinementPlan = when (element) {
        // A new composition seed goes to Stage 1.5, which is where the server
        // spends it (`_call_compose_detail`). The render seed is left unset so a
        // new one is drawn: web's `/api/compose` sends none either.
        RefinementElement.Layout -> {
            val seed = SeedFactory.newCompositionSeed(setOfNotNull(parent.seeds.compositionSeed))
            RefinementPlan(
                element = element,
                route = RefinementRoute.ComposeFromDdl,
                catalogId = parent.catalogId,
                canvasAspect = parent.canvasAspect,
                seeds = PaintSeeds(compositionSeed = seed),
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf("composition_seed" to seed, "recompose_mode" to recomposeMode.id),
                recomposeMode = recomposeMode,
            )
        }

        // 「色カタログ変更は親作品のDDL・Score・キャンバス・配置seed・render seed を
        // 固定し、現在とは異なるcatalog IDだけを適用する」. Every seed is the parent's;
        // the catalogue is the only thing that differs.
        RefinementElement.Color -> {
            val to = newCatalogId?.takeIf { it.isNotBlank() && it != parent.catalogId }
                ?: inkuError { it.refinementNoOtherCatalog }
            RefinementPlan(
                element = element,
                route = RefinementRoute.RenderFromScore,
                catalogId = to,
                canvasAspect = parent.canvasAspect,
                seeds = parent.seeds,
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf(
                    "catalog_id_from" to parent.catalogId,
                    "catalog_id_to" to to,
                ),
            )
        }

    }

    /**
     * Refuses a round the parent cannot feed, in web's order
     * (`generateVariationCandidates`, `generateModelCandidates`). [element] is
     * `null` for the model comparison.
     *
     * A colour change replays the saved Score and a layout draws the saved DDL,
     * so neither needs a description: a work drawn from hand-written DDL can
     * still take them. The model comparison keeps the
     * description guard -- before it, a route through Stage 1 sent the core an
     * empty description and the panel showed its bare `schema_violation`.
     * Every element but colour then needs the DDL, as web asks for it.
     */
    fun requireSource(element: RefinementElement?, parent: RefinementParent) {
        val needsDescription = element != RefinementElement.Color && element != RefinementElement.Layout
        if (needsDescription && parent.description.isBlank()) inkuError { it.refinementNeedsDescription }
        if (element != null && element != RefinementElement.Color && !DdlSource.hasBody(parent.ddl)) {
            inkuError { it.refinementNeedsDdl }
        }
    }

    /**
     * The catalogues the colour change draws: every one but the parent's, in
     * the catalogue list's order (SPEC.ja.md :644, web's `otherCatalogIds`).
     * The author compares them all side by side instead of a random few, so
     * the 1 案 / 4 案 count does not apply and no model is asked.
     */
    fun catalogCandidateIds(currentId: String, available: List<String>): List<String> {
        val others = available.filter { it.isNotBlank() && it != currentId }
        if (others.isEmpty()) inkuError { it.refinementNoOtherCatalog }
        return others
    }

}
