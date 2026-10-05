package app.inku.mobile.data.refinement

/**
 * What a model comparison candidate records as its `comparison_mode`. One model
 * draws both stages (2026-09-30, the author), so each compared model runs Stage 1
 * and Stage 2 alike; the modes that held one stage fixed are gone, and every new
 * candidate says `common`, as web's do (`state.svelte.ts`).
 */
const val MODEL_COMPARISON_MODE = "common"

/**
 * The lineage edge a model comparison candidate is saved under. Works saved as
 * `language_comparison` before the language comparison was retired (the web on
 * 2026-08-29, here on 2026-09-26) keep their own kind and stay readable.
 */
const val MODEL_COMPARISON_KIND = "model_comparison"

/**
 * Builds the orders for one comparison candidate.
 *
 * These are [RefinementPlan]s like any other: the comparisons ride the refinement
 * skeleton rather than owning a second one, so a candidate they produce is drawn,
 * previewed, saved and counted by the same code (SPEC `:688` -- 「比較のロジックを
 * 複製しない」).
 */
object ComparisonPlanner {

    /**
     * Whether a model may not be chosen: one the target work drew with. A work
     * drawn before the stages shared a model may name two, and either is already
     * on the canvas (`isModelInspectionChoiceBlocked`, `state.svelte.ts`).
     */
    fun isModelChoiceBlocked(
        model: String,
        targetStage1Model: String,
        targetStage2Model: String,
    ): Boolean = model == targetStage1Model || model == targetStage2Model

    /**
     * A comparison redraws the description from the top with another model,
     * and the plan sets no seed of its own. It is not seedless: the candidate is
     * drawn with the parent as `parentHistoryId`, and `prepare`
     * (AndroidWorkPipeline) then takes the parent's saved `render_seed`, and
     * its saved composition seed with the configuration, so the models are
     * compared under the parent's performance. A parent with no saved context
     * gets a new render seed.
     */
    fun modelPlan(
        model: String,
        parent: RefinementParent,
    ): RefinementPlan = RefinementPlan(
        element = null,
        route = RefinementRoute.Paint,
        catalogId = parent.catalogId,
        canvasAspect = parent.canvasAspect,
        seeds = PaintSeeds(),
        derivationKind = MODEL_COMPARISON_KIND,
        derivationMetadata = mapOf(
            "comparison_mode" to MODEL_COMPARISON_MODE,
            "compared_model" to model,
            "stage1_model" to model,
            "stage2_model" to model,
        ),
        stage1Model = model,
        stage2Model = model,
    )
}
