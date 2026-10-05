package app.inku.mobile.data.refinement

import app.inku.mobile.data.DdlSource
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.drawnWild
import app.inku.mobile.data.model.WorkColorSnapshot
import app.inku.mobile.data.model.workColorSnapshot
import app.inku.mobile.pipeline.RecomposeMode
import app.inku.mobile.ui.i18n.InkuStrings
import app.inku.mobile.ui.i18n.inkuError

/**
 * The one intervention a round of refinement makes.
 *
 * A refinement selects one of touch, layout, reading, or color catalog.
 * That is why this is an enum and not a set
 * of flags -- 「系譜の各辺を単一の介入として説明可能にするため」, and a lineage edge
 * whose cause is two things at once cannot be labelled with one kind.
 */
enum class RefinementElement(val id: String, val derivationKind: String) {
    Touch("touch", "touch_change"),
    Layout("layout", "layout_change"),
    Reading("reading", "reinterpretation"),
    Color("color", "catalog_change"),
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
    /** `null` for a comparison candidate: it varies the model, which is not one of the four elements. */
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
     *   there is no way to spell "touch and colour" here, which is what makes
     *   the exclusivity a property of the type rather than of a check.
     * @param newCatalogId the catalogue to apply, for the colour refinement only.
     */
    fun plan(
        element: RefinementElement,
        parent: RefinementParent,
        newCatalogId: String? = null,
        seedText: String? = null,
        recomposeMode: RecomposeMode = RecomposeMode.Principled,
    ): RefinementPlan = when (element) {
        // The Score, the DDL, the canvas and the catalogue all stay; only the
        // performance is played again. web derives the seed from the words the
        // author typed (`renderWordTouchCandidate`), so the same words always
        // give the same touch.
        RefinementElement.Touch -> {
            val to = seedText?.let { SeedFactory.renderSeedFromText(it) }
                ?: inkuError { it.refinementTouchWordsRequired }
            RefinementPlan(
                element = element,
                route = RefinementRoute.RenderFromScore,
                catalogId = parent.catalogId,
                canvasAspect = parent.canvasAspect,
                seeds = parent.seeds.copy(renderSeed = to, seedText = seedText.trim()),
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf(
                    "render_seed_from" to parent.seeds.renderSeed?.let { unsigned(it) },
                    "render_seed_to" to unsigned(to),
                    "seed_text" to seedText.trim(),
                ),
            )
        }

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
                seeds = PaintSeeds(compositionSeed = seed, interpretationSeed = parent.seeds.interpretationSeed),
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf("composition_seed" to seed, "recompose_mode" to recomposeMode.id),
                recomposeMode = recomposeMode,
            )
        }

        // 「読み取りは一つの上流介入として扱い、その結果として配置とタッチを下流工程
        // で再生成する」-- so neither the composition seed nor the render seed is
        // carried: they are downstream of the reading, and holding them would
        // pin what the SPEC says is regenerated.
        RefinementElement.Reading -> {
            val seed = SeedFactory.newInterpretationSeed()
            RefinementPlan(
                element = element,
                route = RefinementRoute.Paint,
                catalogId = parent.catalogId,
                canvasAspect = parent.canvasAspect,
                seeds = PaintSeeds(interpretationSeed = seed),
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf("interpretation_seed" to seed),
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
     * How many candidates the element can offer.
     *
     * Touch is the one that cannot fan out: its seed comes from the words, so
     * four candidates would be four copies of one drawing. web says so in the
     * same place and refuses (`generateVariationCandidates`, `+page.svelte:5245`).
     */
    fun maxCandidates(element: RefinementElement): Int =
        if (element == RefinementElement.Touch) 1 else 4

    val TOUCH_FANOUT_REFUSAL: (InkuStrings) -> String = { it.refinementTouchFanoutRefusal }

    /**
     * Refuses a round the parent cannot feed, in web's order
     * (`generateVariationCandidates`, `generateModelCandidates`). [element] is
     * `null` for the model comparison.
     *
     * A colour change replays the saved Score and a layout draws the saved DDL,
     * so neither needs a description: a work drawn from hand-written DDL can
     * still take them. Touch, reading and the model comparison keep the
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

    private fun unsigned(seed: Long): String = java.lang.Long.toUnsignedString(seed)
}
