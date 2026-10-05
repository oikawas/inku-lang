package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.LineageNodeEntity
import app.inku.mobile.data.lineage.LineageDeclaration
import app.inku.mobile.data.model.ColorCatalogs
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.pipeline.RecomposeMode
import app.inku.mobile.ui.i18n.InkuFailure
import app.inku.mobile.ui.i18n.InkuStringsJa
import kotlin.reflect.full.memberProperties
import kotlin.reflect.full.valueParameters
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

/**
 * T-1, T-3 and T-5: what one round of refinement decides, before anything is
 * drawn.
 *
 * The plan is a pure function, so these read the decision itself rather than a
 * drawing that happens to look right.
 */
class RefinementPlanTest {

    private fun parentItem(
        catalogId: String = "ink_season",
        canvasAspect: String = "16:9",
        renderSeed: String? = "4242",
        compositionSeed: String? = "77",
        interpretationSeed: String? = "parent-reading",
    ) = HistoryItemEntity(
        id = "parent",
        createdAt = 1L,
        updatedAt = 1L,
        originalInput = "青い線を引く",
        normalizedDdl = "青い線を一本引く。",
        scoreJson = """{"version":"0.1.0","canvas":"square","background":"white","instructions":[]}""",
        displaySvg = "<svg/>",
        stage1Model = "stage1",
        stage2Model = "stage2",
        renderMetadataJson = "{}",
        renderHash = "rh3:parent",
        renderHashShort = "AAAA",
        colorCatalogId = catalogId,
        canvasAspect = canvasAspect,
        starred = false,
        trashed = false,
        elapsedMs = 0L,
        tokenMetadataJson = null,
        renderSeed = renderSeed,
        compositionSeed = compositionSeed,
        interpretationSeed = interpretationSeed,
    )

    private fun parent(item: HistoryItemEntity = parentItem()) = RefinementParent.of(item, item.originalInput)

    // ── T-1 ────────────────────────────────────────────────

    /**
     * The exclusivity is a property of the type, not of a check that could be
     * forgotten. `plan` takes one [RefinementElement]; there is no overload, no
     * collection parameter and no field holding more than one, so "touch and
     * colour at once" cannot be written down in the first place.
     */
    @Test
    fun t1_theElementIsOneValueAndCannotBeACollection() {
        val planFunctions = RefinementPlanner::class.members.filter { it.name == "plan" }
        assertEquals("there is exactly one way in", 1, planFunctions.size)

        val elementParam = planFunctions.single().valueParameters.single { it.name == "element" }
        assertEquals(
            "the element parameter is the enum itself",
            RefinementElement::class,
            elementParam.type.classifier,
        )
        assertTrue(
            "no parameter of plan() accepts more than one element",
            planFunctions.single().valueParameters.none { param ->
                val name = param.type.toString()
                name.contains("Collection") || name.contains("List") || name.contains("Set") || name.contains("Array")
            },
        )

        val elementProperty = RefinementPlan::class.memberProperties.single { it.name == "element" }
        assertEquals(RefinementElement::class, elementProperty.returnType.classifier)
        assertTrue(
            "the plan holds no second element anywhere",
            RefinementPlan::class.memberProperties.count { it.returnType.classifier == RefinementElement::class } == 1,
        )
    }

    // ── T-3 ────────────────────────────────────────────────

    /**
     * 「色以外のすべての推敲は、次回描画の設定ではなく表示中の親作品の実効カタログと
     * キャンバスを継承する」.
     *
     * The parent here is deliberately set to a catalogue and a canvas that the
     * describe screen is *not* on: `nextDrawCatalog` / `nextDrawCanvas` below are
     * what a plan built from the current selection would have picked. With the
     * two the same, an implementation that read either one would be green.
     */
    @Test
    fun t3_everythingButColourInheritsTheParentsCatalogAndCanvas() {
        val nextDrawCatalog = "vivid_material"
        val nextDrawCanvas = "square"
        val parent = parent(parentItem(catalogId = "ink_season", canvasAspect = "16:9"))
        assertNotEquals("the parent differs from the next-draw setting", nextDrawCatalog, parent.catalogId)
        assertNotEquals(nextDrawCanvas, parent.canvasAspect)

        listOf(
            RefinementElement.Touch to "しずかに",
            RefinementElement.Layout to null,
            RefinementElement.Reading to null,
        ).forEach { (element, words) ->
            val plan = RefinementPlanner.plan(element, parent, seedText = words, textSeed = WORD_SEED)
            assertEquals("$element keeps the parent's catalogue", parent.catalogId, plan.catalogId)
            assertEquals("$element keeps the parent's canvas", parent.canvasAspect, plan.canvasAspect)
            assertNotEquals("$element did not read the next-draw catalogue", nextDrawCatalog, plan.catalogId)
        }
    }

    /** The colour refinement is the one that changes the catalogue -- and only it. */
    @Test
    fun t3_theColourRefinementChangesTheCatalogueAndNothingElse() {
        val parent = parent()
        val plan = RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "vivid_material")

        assertEquals("vivid_material", plan.catalogId)
        assertNotEquals(parent.catalogId, plan.catalogId)
        assertEquals("the canvas is still the parent's", parent.canvasAspect, plan.canvasAspect)
        // 「親作品のDDL・Score・キャンバス・配置seed・render seed を固定し」.
        assertEquals("the render seed is held", parent.seeds.renderSeed, plan.seeds.renderSeed)
        assertEquals("the composition seed is held", parent.seeds.compositionSeed, plan.seeds.compositionSeed)
        assertEquals("the reading is held", parent.seeds.interpretationSeed, plan.seeds.interpretationSeed)
        assertEquals("the Score is replayed, not recomposed", RefinementRoute.RenderFromScore, plan.route)
    }

    /** Applying the catalogue the work already has is not a refinement. */
    @Test
    fun t3_theColourRefinementRefusesTheParentsOwnCatalogue() {
        val parent = parent(parentItem(catalogId = "ink_season"))
        val error = runCatching { RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "ink_season") }
        assertTrue(error.isFailure)
    }

    /**
     * SPEC.ja.md :644 -- 「対象作品の色カタログを除く全色カタログで同じScoreを描いた
     * 候補をカタログ一覧の順に並べる」, web's `otherCatalogIds`: every other
     * catalogue, in the list's order, whatever count is chosen.
     */
    @Test
    fun t3_theColourChangeOffersEveryOtherCatalogueInListOrder() {
        val available = ColorCatalogs.all.map { it.id }
        val ids = RefinementPlanner.catalogCandidateIds("ink_season", available)

        assertEquals(available.filter { it != "ink_season" }, ids)
        assertFalse("the parent's own catalogue is not offered", ids.contains("ink_season"))
        assertEquals("a second round is the same list", ids, RefinementPlanner.catalogCandidateIds("ink_season", available))
    }

    // ── T-5 ────────────────────────────────────────────────

    /**
     * Each element declares the edge the server registers for it, with the
     * metadata keys web writes. The names are checked one by one rather than as
     * a count: a metadata map with the right size and the wrong spelling would
     * be recorded and never read again.
     */
    @Test
    fun t5_allFourElementsDeclareTheirEdgeWithoutInheritingRetiredVariation() {
        val oldItem = parentItem().copy(variationAmplitude = "large", variationSeed = "7")
        val parent = parent(oldItem)
        assertEquals(listOf("touch", "layout", "reading", "color"), RefinementElement.entries.map { it.id })
        assertNull(RefinementElement.byId("variation"))

        val touch = RefinementPlanner.plan(RefinementElement.Touch, parent, seedText = "しずかに", textSeed = WORD_SEED)
        assertEquals("touch_change", touch.derivationKind)
        assertEquals(setOf("render_seed_from", "render_seed_to", "seed_text"), touch.derivationMetadata.keys)
        assertEquals("4242", touch.derivationMetadata["render_seed_from"])
        assertNotEquals(touch.derivationMetadata["render_seed_from"], touch.derivationMetadata["render_seed_to"])

        val layout = RefinementPlanner.plan(RefinementElement.Layout, parent)
        assertEquals("layout_change", layout.derivationKind)
        assertEquals(setOf("composition_seed", "recompose_mode"), layout.derivationMetadata.keys)
        assertEquals(layout.seeds.compositionSeed, layout.derivationMetadata["composition_seed"])

        val reading = RefinementPlanner.plan(RefinementElement.Reading, parent)
        assertEquals("reinterpretation", reading.derivationKind)
        assertEquals(setOf("interpretation_seed"), reading.derivationMetadata.keys)
        assertEquals(reading.seeds.interpretationSeed, reading.derivationMetadata["interpretation_seed"])

        // SPEC :678 -- 「色変更は系譜の catalog_change として変更前後のcatalog IDを記録する」.
        val color = RefinementPlanner.plan(RefinementElement.Color, parent, newCatalogId = "vivid_material")
        assertEquals("catalog_change", color.derivationKind)
        assertEquals(setOf("catalog_id_from", "catalog_id_to"), color.derivationMetadata.keys)
        assertEquals("ink_season", color.derivationMetadata["catalog_id_from"])
        assertEquals("vivid_material", color.derivationMetadata["catalog_id_to"])

        listOf(touch, layout, reading, color).forEach { plan ->
            assertFalse(plan.derivationMetadata.containsKey("variation_amplitude"))
            assertFalse(plan.derivationMetadata.containsKey("variation_seed"))
        }
        assertEquals("large", oldItem.variationAmplitude)
        assertEquals("7", oldItem.variationSeed)
    }

    /** A selected candidate declares the same mode and seed when its edge is written. */
    @Test
    fun aLayoutCandidateKeepsItsSelectedModeAndSeedOnTheSavedEdge() {
        val parent = parent()
        val defaultPlan = RefinementPlanner.plan(RefinementElement.Layout, parent)
        assertEquals(RecomposeMode.Principled, defaultPlan.recomposeMode)
        assertEquals("principled", defaultPlan.derivationMetadata["recompose_mode"])

        val chosen = RefinementPlanner.plan(RefinementElement.Layout, parent, recomposeMode = RecomposeMode.Chance)
        assertEquals(RecomposeMode.Chance, chosen.recomposeMode)
        val write = LineagePlanner.plan(
            nodeId = "chosen", edgeId = "chosen-edge", historyId = "chosen-work", at = 1L,
            descriptionHash = "description", renderHash = "render", historyVisibility = null,
            declaration = LineageDeclaration("parent-node", chosen.derivationKind, chosen.derivationMetadata),
            parentNode = LineageNodeEntity(id = "parent-node", rootNodeId = "root-node"),
        )
        val metadata = JSONObject(write.edge!!.metadataJson)
        assertEquals("layout_change", write.edge!!.derivationKind)
        assertEquals("chance", metadata.getString("recompose_mode"))
        assertEquals(chosen.seeds.compositionSeed, metadata.getLong("composition_seed"))
        assertNotEquals(parent.seeds.compositionSeed, chosen.seeds.compositionSeed)
    }

    /** Every active kind is one the server registers. */
    @Test
    fun t5_theFourKindsAreTheServersOwn() {
        val registered = app.inku.mobile.data.model.DerivationKindRegistry.KINDS
        RefinementElement.entries.forEach { element ->
            assertTrue("${element.derivationKind} is a server kind", registered.contains(element.derivationKind))
        }
        assertEquals("four elements, four distinct kinds", 4, RefinementElement.entries.map { it.derivationKind }.toSet().size)
    }

    // ── the reading is upstream ────────────────────────────

    /**
     * 「読み取りは一つの上流介入として扱い、その結果として配置とタッチを下流工程で
     * 再生成する」: holding the parent's composition or render seed would pin the
     * two things the SPEC says are made again.
     */
    @Test
    fun theReadingRegeneratesWhatIsDownstreamOfIt() {
        val plan = RefinementPlanner.plan(RefinementElement.Reading, parent())

        assertNull("the layout is regenerated", plan.seeds.compositionSeed)
        assertNull("the touch is regenerated", plan.seeds.renderSeed)
        assertEquals(RefinementRoute.Paint, plan.route)
    }

    /** The touch is the one element that cannot fan out; the others can. */
    @Test
    fun onlyTheTouchRefusesFourCandidates() {
        assertEquals(1, RefinementPlanner.maxCandidates(RefinementElement.Touch))
        RefinementElement.entries.filter { it != RefinementElement.Touch }.forEach {
            assertEquals("$it can offer four", 4, RefinementPlanner.maxCandidates(it))
        }
    }

    /** A work saved before the seed columns existed reports no seeds, not zeros. */
    @Test
    fun aWorkWithNoStoredSeedsReportsNoneRatherThanZero() {
        val seeds = PaintSeeds.of(parentItem(renderSeed = null, compositionSeed = null, interpretationSeed = null))

        assertNull(seeds.renderSeed)
        assertNull(seeds.compositionSeed)
        assertNull(seeds.interpretationSeed)
    }

    /**
     * A touch seed can be larger than `Long.MAX_VALUE`, and the column holds it
     * as text. Reading it back has to give the same 64 bits, or a saved work
     * would replay as a different performance.
     */
    @Test
    fun aTouchSeedAboveTheSignedRangeSurvivesTheRoundTrip() {
        val seed = WORD_SEED("しずかに")!!.renderSeed
        val stored = java.lang.Long.toUnsignedString(seed)
        val readBack = PaintSeeds.of(parentItem(renderSeed = stored)).renderSeed

        assertEquals(seed, readBack)
        assertEquals(stored, java.lang.Long.toUnsignedString(readBack!!))
    }

    /** The touch takes the words and the seed the shared rule gives them. */
    @Test
    fun theTouchUsesTheSharedRulesSeedAndWords() {
        val touch = RefinementPlanner.plan(RefinementElement.Touch, parent(), seedText = " しずかに ", textSeed = WORD_SEED)
        assertEquals(WORD_SEED("しずかに")!!.renderSeed, touch.seeds.renderSeed)
        assertEquals("しずかに", touch.seeds.seedText)
    }

    private companion object {
        /** The shared rule is tested in Rust; here it is scripted, with a seed past Long.MAX_VALUE. */
        val WORD_SEED: (String) -> TextSeed? = { words ->
            words.trim().takeIf(String::isNotEmpty)?.let {
                TextSeed(java.lang.Long.parseUnsignedLong("14859340650796947346"), it)
            }
        }
    }

    // ── what the parent must have ─────────────────────────

    /**
     * web's order (`generateVariationCandidates`, `generateModelCandidates`):
     * a colour and a layout need no description; touch, reading and the model
     * comparison do; everything but colour needs the DDL. The refusal is read
     * as the sentence it carries, so a refusal for the wrong reason fails too.
     */
    private fun refusal(element: RefinementElement?, parent: RefinementParent): String? = try {
        RefinementPlanner.requireSource(element, parent)
        null
    } catch (failure: InkuFailure) {
        failure.text(InkuStringsJa)
    }

    @Test
    fun aWorkWithoutADescriptionCanStillChangeItsColourAndLayout() {
        val parent = RefinementParent.of(parentItem(), description = "")

        assertNull(refusal(RefinementElement.Color, parent))
        assertNull(refusal(RefinementElement.Layout, parent))
        assertEquals(InkuStringsJa.refinementNeedsDescription, refusal(RefinementElement.Touch, parent))
        assertEquals(InkuStringsJa.refinementNeedsDescription, refusal(RefinementElement.Reading, parent))
        assertEquals("the model comparison reads the description", InkuStringsJa.refinementNeedsDescription, refusal(null, parent))
    }

    @Test
    fun everythingButColourNeedsTheDdlAndTheDescriptionIsAskedFirst() {
        val noDdl = parentItem().copy(normalizedDdl = " \n")
        val described = RefinementParent.of(noDdl, noDdl.originalInput)
        val bare = RefinementParent.of(noDdl, description = "")

        assertNull(refusal(RefinementElement.Color, bare))
        assertEquals(InkuStringsJa.refinementNeedsDdl, refusal(RefinementElement.Layout, bare))
        assertEquals("the description is asked first", InkuStringsJa.refinementNeedsDescription, refusal(RefinementElement.Touch, bare))
        assertEquals(InkuStringsJa.refinementNeedsDdl, refusal(RefinementElement.Touch, described))
        assertEquals(InkuStringsJa.refinementNeedsDdl, refusal(RefinementElement.Reading, described))
        assertEquals(InkuStringsJa.refinementNeedsDdl, refusal(RefinementElement.Layout, described))
        assertNull("the model comparison draws from the description alone", refusal(null, described))
    }
}
