package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.InstructionLanguage

/**
 * Which of the two inspections a round of comparison is.
 *
 * The kind is carried rather than inferred, because it is the one thing the
 * lineage edge is named after and the branch that names it lives in exactly one
 * place ([ComparisonPlanner.derivationKindFor], the port of web's single line at
 * `state.svelte.ts:546`).
 */
enum class ComparisonKind { Model, Language }

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

/** One Stage 1 × Stage 2 language pair, the unit the language inspection selects. */
data class LanguageCombo(val stage1: String, val stage2: String) {
    val id: String get() = "$stage1:$stage2"

    companion object {
        /**
         * The four pairs, in the order `CanvasPanel.svelte:978-988` lists them.
         *
         * The language inspection selects pairs with checkboxes rather than one
         * of three modes. SPEC `:686` says it has the same three modes model
         * comparison has; the reference implementation does not, and the
         * reference implementation is what this follows (SPEC `:614`).
         */
        val ALL: List<LanguageCombo> = InstructionLanguage.entries.flatMap { stage1 ->
            InstructionLanguage.entries.map { stage2 -> LanguageCombo(stage1.code, stage2.code) }
        }

        fun byId(id: String?): LanguageCombo? = ALL.firstOrNull { it.id == id }
    }
}

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
     * The one place the two comparison edges are told apart.
     *
     * web spells the same branch on one line
     * (`derivationKind: parent ? (kind === 'language' ? 'language_comparison' :
     * 'model_comparison') : null`, `state.svelte.ts:546`). Splitting it in two
     * would let one of the kinds be right while the other is a constant.
     */
    fun derivationKindFor(kind: ComparisonKind): String =
        if (kind == ComparisonKind.Language) "language_comparison" else "model_comparison"

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

    /** The target work's own pair, and only that one (`state.svelte.ts:373-375`). */
    fun isLanguageComboBlocked(combo: LanguageCombo, targetLang: String): Boolean =
        combo.stage1 == targetLang && combo.stage2 == targetLang

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
            derivationKind = derivationKindFor(ComparisonKind.Model),
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

    /**
     * `comparison_mode` is `common` for every language candidate
     * (`state.svelte.ts:469`): the pairs are the selection here, so there is no
     * mode to record and web records the default rather than inventing one.
     */
    fun languagePlan(combo: LanguageCombo, parent: RefinementParent): RefinementPlan = RefinementPlan(
        element = null,
        route = RefinementRoute.Paint,
        catalogId = parent.catalogId,
        canvasAspect = parent.canvasAspect,
        seeds = PaintSeeds(),
        derivationKind = derivationKindFor(ComparisonKind.Language),
        derivationMetadata = mapOf(
            "comparison_mode" to ModelCompareMode.Common.id,
            "stage1_language" to combo.stage1,
            "stage2_language" to combo.stage2,
        ),
        stage1Lang = combo.stage1,
        stage2Lang = combo.stage2,
    )
}
