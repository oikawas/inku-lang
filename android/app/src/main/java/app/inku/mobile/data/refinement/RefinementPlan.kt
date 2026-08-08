package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity

/**
 * The one intervention a round of refinement makes.
 *
 * SPEC `:614` and `:678`: 「推敲要素はタッチ・配置・読み取り・色カタログ・変奏の
 * 5 種類から一度に 1 種類だけを選択する」. That is why this is an enum and not a set
 * of flags -- 「系譜の各辺を単一の介入として説明可能にするため」, and a lineage edge
 * whose cause is two things at once cannot be labelled with one kind.
 */
enum class RefinementElement(val id: String, val labelJa: String, val derivationKind: String) {
    Touch("touch", "タッチ", "touch_change"),
    Layout("layout", "配置", "layout_change"),
    Reading("reading", "読み取り", "reinterpretation"),
    Color("color", "色カタログ", "catalog_change"),
    Variation("variation", "変奏", "variation"),
    ;

    companion object {
        fun byId(id: String?): RefinementElement? = entries.firstOrNull { it.id == id }
    }
}

/** 強度. Shown only under the variation radio, and only there (SPEC `:614`). */
enum class VariationAmplitude(val id: String, val labelJa: String) {
    Small("small", "控えめ"),
    Medium("medium", "中庸"),
    Large("large", "大胆"),
    ;

    companion object {
        /** 既定は中庸. */
        val Default = Medium

        fun byId(id: String?): VariationAmplitude = entries.firstOrNull { it.id == id } ?: Default
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
            ddl = item.normalizedDdl,
            scoreJson = item.scoreJson,
            catalogId = item.colorCatalogId,
            canvasAspect = item.canvasAspect,
            stage1Model = item.stage1Model ?: "",
            stage2Model = item.stage2Model ?: "",
            seeds = PaintSeeds.of(item),
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
    /** `null` for a comparison candidate: those vary a model or a language, neither of which is one of the five elements. */
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
     *
     * The two languages are separate because they are two requests: the stages
     * are asked one at a time, exactly as web asks them (`interpretOne(...,
     * job.stage1Lang)` then `composeOne(..., job.stage2Lang)`,
     * `state.svelte.ts:432-435`). There is no single "language per stage" key on
     * either side.
     */
    val stage1Model: String? = null,
    val stage2Model: String? = null,
    val stage1Lang: String? = null,
    val stage2Lang: String? = null,
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
     * @param amplitude read only when [element] is [RefinementElement.Variation].
     * @param newCatalogId the catalogue to apply, for the colour refinement only.
     */
    fun plan(
        element: RefinementElement,
        parent: RefinementParent,
        amplitude: VariationAmplitude = VariationAmplitude.Default,
        newCatalogId: String? = null,
        seedText: String? = null,
    ): RefinementPlan = when (element) {
        // The Score, the DDL, the canvas and the catalogue all stay; only the
        // performance is played again. web derives the seed from the words the
        // author typed (`renderWordTouchCandidate`), so the same words always
        // give the same touch.
        RefinementElement.Touch -> {
            val to = seedText?.let { SeedFactory.renderSeedFromText(it) }
                ?: error("タッチを変える言葉を入力してください。")
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
                derivationMetadata = mapOf("composition_seed" to seed),
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
                ?: error("別の色カタログがありません。")
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

        // 「variation_amplitude と variation_seed は揃って初めて有効」: the pair goes
        // to Stage 1.5 together or the expander builds no plan at all.
        RefinementElement.Variation -> {
            val seed = SeedFactory.newVariationSeeds(1).first()
            RefinementPlan(
                element = element,
                route = RefinementRoute.ComposeFromDdl,
                catalogId = parent.catalogId,
                canvasAspect = parent.canvasAspect,
                seeds = PaintSeeds(
                    compositionSeed = parent.seeds.compositionSeed,
                    interpretationSeed = parent.seeds.interpretationSeed,
                    variationAmplitude = amplitude.id,
                    variationSeed = seed,
                ),
                derivationKind = element.derivationKind,
                derivationMetadata = mapOf(
                    "variation_amplitude" to amplitude.id,
                    "variation_seed" to seed,
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

    const val TOUCH_FANOUT_REFUSAL = "同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。"

    /**
     * The catalogues four colour candidates use. 「4案では可能な限り異なるカタログ
     * を使う」: the parent's own is excluded and the rest are shuffled, so a
     * second round is not the same four.
     */
    fun catalogCandidateIds(currentId: String, available: List<String>, count: Int): List<String> {
        val others = available.filter { it.isNotBlank() && it != currentId }.shuffled()
        if (others.isEmpty()) error("別の色カタログがありません。")
        return List(count) { index -> others[index % others.size] }
    }

    private fun unsigned(seed: Long): String = java.lang.Long.toUnsignedString(seed)
}
