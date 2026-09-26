package app.inku.mobile.data.refinement

/**
 * The three model comparison modes (`state.svelte.ts:135`, SPEC `:616`).
 *
 * `common` sends the chosen model to both stages; each fixed mode holds one
 * stage on the fixed model and sends the chosen one to the other.
 */
enum class ModelCompareMode(val id: String) {
    Common("common"),
    Stage1Fixed("stage1_fixed"),
    Stage2Fixed("stage2_fixed"),
    ;

    companion object {
        val Default = Common

        fun byId(id: String?): ModelCompareMode = entries.firstOrNull { it.id == id } ?: Default
    }
}

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
     * Which model each stage gets, written as the two lines web decides it with
     * (`state.svelte.ts:275-277`).
     */
    fun stage1ModelFor(mode: ModelCompareMode, fixedModel: String, model: String): String =
        if (mode == ModelCompareMode.Stage1Fixed) fixedModel else model

    fun stage2ModelFor(mode: ModelCompareMode, fixedModel: String, model: String): String =
        if (mode == ModelCompareMode.Stage2Fixed) fixedModel else model

    /**
     * Whether a model may not be chosen: the target work's own pair, and only
     * that pair (`isModelInspectionChoiceBlocked`, `state.svelte.ts:210-211`).
     *
     * In a fixed mode a model the target used is still selectable, as long as
     * the pair it makes with the fixed side differs from the target's.
     */
    fun isModelChoiceBlocked(
        mode: ModelCompareMode,
        fixedModel: String,
        model: String,
        targetStage1Model: String,
        targetStage2Model: String,
    ): Boolean = when (mode) {
        ModelCompareMode.Common -> model == targetStage1Model || model == targetStage2Model
        ModelCompareMode.Stage1Fixed -> fixedModel == targetStage1Model && model == targetStage2Model
        ModelCompareMode.Stage2Fixed -> model == targetStage1Model && fixedModel == targetStage2Model
    }

    /**
     * A comparison redraws the description from the top, so it carries none of
     * the parent's seeds: a held render seed would hand every model the same
     * performance and hide the difference the comparison exists to show. web
     * sends none either -- `interpretOne` / `composeOne` with no seed fields.
     */
    fun modelPlan(
        mode: ModelCompareMode,
        fixedModel: String,
        model: String,
        parent: RefinementParent,
    ): RefinementPlan {
        val stage1 = stage1ModelFor(mode, fixedModel, model)
        val stage2 = stage2ModelFor(mode, fixedModel, model)
        return RefinementPlan(
            element = null,
            route = RefinementRoute.Paint,
            catalogId = parent.catalogId,
            canvasAspect = parent.canvasAspect,
            seeds = PaintSeeds(),
            derivationKind = MODEL_COMPARISON_KIND,
            derivationMetadata = mapOf(
                "comparison_mode" to mode.id,
                "compared_model" to model,
                "stage1_model" to stage1,
                "stage2_model" to stage2,
            ),
            stage1Model = stage1,
            stage2Model = stage2,
        )
    }


}
