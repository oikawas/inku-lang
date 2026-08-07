package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity
import kotlin.reflect.full.memberProperties
import kotlin.reflect.full.valueParameters
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

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
        expandedDdl = "青い線を一本引く。",
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
            RefinementElement.Variation to null,
        ).forEach { (element, words) ->
            val plan = RefinementPlanner.plan(element, parent, seedText = words)
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

    /** 「4案では可能な限り異なるカタログを使う」. */
    @Test
    fun t3_fourColourCandidatesUseFourDifferentCatalogues() {
        val available = listOf("default", "ink_season", "vivid_material", "sea_stone", "moss_bark")
        val ids = RefinementPlanner.catalogCandidateIds("ink_season", available, 4)

        assertEquals(4, ids.size)
        assertEquals("all four differ", 4, ids.toSet().size)
        assertFalse("the parent's own catalogue is not offered", ids.contains("ink_season"))
    }

    // ── T-5 ────────────────────────────────────────────────

    /**
     * Each element declares the edge the server registers for it, with the
     * metadata keys web writes. The names are checked one by one rather than as
     * a count: a metadata map with the right size and the wrong spelling would
     * be recorded and never read again.
     */
    @Test
    fun t5_allFiveElementsDeclareTheirEdgeAndItsMetadata() {
        val parent = parent()

        val touch = RefinementPlanner.plan(RefinementElement.Touch, parent, seedText = "しずかに")
        assertEquals("touch_change", touch.derivationKind)
        assertEquals(setOf("render_seed_from", "render_seed_to", "seed_text"), touch.derivationMetadata.keys)
        assertEquals("4242", touch.derivationMetadata["render_seed_from"])
        assertNotEquals(touch.derivationMetadata["render_seed_from"], touch.derivationMetadata["render_seed_to"])

        val layout = RefinementPlanner.plan(RefinementElement.Layout, parent)
        assertEquals("layout_change", layout.derivationKind)
        assertEquals(setOf("composition_seed"), layout.derivationMetadata.keys)
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

        val variation = RefinementPlanner.plan(RefinementElement.Variation, parent, amplitude = VariationAmplitude.Large)
        assertEquals("variation", variation.derivationKind)
        assertEquals(setOf("variation_amplitude", "variation_seed"), variation.derivationMetadata.keys)
        assertEquals("large", variation.derivationMetadata["variation_amplitude"])
        assertEquals(variation.seeds.variationSeed, variation.derivationMetadata["variation_seed"])
    }

    /** Every kind named above is one the server registers. */
    @Test
    fun t5_theFiveKindsAreTheServersOwn() {
        val registered = app.inku.mobile.data.model.DerivationKindRegistry.KINDS
        RefinementElement.entries.forEach { element ->
            assertTrue("${element.derivationKind} is a server kind", registered.contains(element.derivationKind))
        }
        assertEquals("five elements, five distinct kinds", 5, RefinementElement.entries.map { it.derivationKind }.toSet().size)
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
        val seed = SeedFactory.renderSeedFromText("しずかに")!!
        val stored = java.lang.Long.toUnsignedString(seed)
        val readBack = PaintSeeds.of(parentItem(renderSeed = stored)).renderSeed

        assertEquals(seed, readBack)
        assertEquals(stored, java.lang.Long.toUnsignedString(readBack!!))
    }

    /** The same words are the same touch -- which is why four of them is refused. */
    @Test
    fun theSameWordsGiveTheSameTouchSeed() {
        assertEquals(SeedFactory.renderSeedFromText("しずかに"), SeedFactory.renderSeedFromText(" しずかに "))
        assertNotEquals(SeedFactory.renderSeedFromText("しずかに"), SeedFactory.renderSeedFromText("はげしく"))
        assertNull("no words, no seed", SeedFactory.renderSeedFromText("   "))
    }
}
