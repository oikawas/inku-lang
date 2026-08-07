package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.LocalFallbackPipeline
import app.inku.mobile.pipeline.PaintRequest
import app.inku.mobile.pipeline.WebDdlExpander
import java.security.MessageDigest
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * T-2, T-4 and T-11: the five arguments reach something, and what they reach
 * agrees with the server.
 *
 * The expectations in [SERVER_VARIATION] were baked by calling the server's own
 * `ddl_expander.expand_intermediate_ddl`
 * (`cli/out2/859-v2.11.4-android-refines-expectations/`), and the colour
 * judgment by calling `renderer.render` with two catalogues over one Score. They
 * are the server's values, and the port reproduces them.
 *
 * Everything here goes through `renderFromScore`, the one pipeline entry that
 * logs nothing: `android.util.Log` is not available to a JVM test, so the other
 * two entries are exercised on the device instead.
 */
class RefinementSeedWiringTest {

    private val pipeline = LocalFallbackPipeline()

    /** The Score `bake_catalog.py` drew: one red line, one blue circle. */
    private val score = """
        {"version":"0.1.0","canvas":"square","background":"white","instructions":[
          {"primitive":"line","from":[0.2,0.5],"to":[0.8,0.5],"color":"red","weight":"brush_thick"},
          {"primitive":"circle","center":[0.75,0.25],"radius":0.12,"color":"blue","weight":"pen"}
        ]}
    """.trimIndent()

    private fun request(
        catalogId: String = "default",
        renderSeed: Long? = 4242L,
        compositionSeed: Long? = null,
        interpretationSeed: String? = null,
        variationAmplitude: String? = null,
        variationSeed: Long? = null,
    ) = PaintRequest(
        description = "赤い線と青い円",
        stage1Model = "stage1",
        stage2Model = "stage2",
        colorCatalogId = catalogId,
        canvasAspect = "square",
        autoRepair = false,
        renderSeed = renderSeed,
        compositionSeed = compositionSeed,
        interpretationSeed = interpretationSeed,
        variationAmplitude = variationAmplitude,
        variationSeed = variationSeed,
    )

    /** `geometry_only` in `bake_catalog.py`: blank out everything that carries a colour. */
    private fun geometryOnly(svg: String): String = svg
        .replace(Regex("""(fill|stroke|stop-color|flood-color)="[^"]*""""), """$1="X"""")
        .replace(Regex("#[0-9a-fA-F]{3,6}"), "#XXX")

    private fun colorsIn(svg: String): Set<String> =
        Regex("#[0-9a-fA-F]{6}").findAll(svg).map { it.value.lowercase() }.toSet()

    // ── T-2 ────────────────────────────────────────────────

    /**
     * 「色カタログ変更は親作品のDDL・Score・キャンバス・配置seed・render seed を固定し、
     * 現在とは異なるcatalog IDだけを適用する」.
     *
     * Both halves are stated, and they have to be: "the geometry does not move"
     * alone is passed by an implementation that draws nothing new at all, and
     * "the colours differ" alone is passed by one that redraws from scratch.
     * The baked run says the same two things -- 幾何 sha `f9a2a14e0cd6` for both
     * catalogues, 全体 sha `170546bdc363` against `ffad9dbb35e1`.
     */
    @Test
    fun t2_theColourRefinementMovesTheColoursAndNotTheGeometry() {
        val default = pipeline.renderFromScore(score, request(catalogId = "default"))
        val vivid = pipeline.renderFromScore(score, request(catalogId = "vivid_material"))

        assertEquals(
            "the drawing itself is untouched by the catalogue",
            geometryOnly(default.displaySvg),
            geometryOnly(vivid.displaySvg),
        )
        assertNotEquals("the SVG as a whole is not the same", default.displaySvg, vivid.displaySvg)
        assertNotEquals("and it is the colours that differ", colorsIn(default.displaySvg), colorsIn(vivid.displaySvg))
        // The baked run reports the catalogues' own inks. `catalog_id` alone
        // decides nothing on the server -- the colour map does -- and a port
        // that only relabelled would still be byte-identical here.
        assertTrue("default paints its red", colorsIn(default.displaySvg).contains("#a2342a"))
        assertTrue("vivid paints its rose", colorsIn(vivid.displaySvg).contains("#f50087"))
        assertFalse("the two do not share the red", colorsIn(vivid.displaySvg).contains("#a2342a"))
    }

    /** 同じカタログは再現するか: True. The seed is held, so the touch is the same touch. */
    @Test
    fun t2_theSameCatalogueTwiceIsTheSameDrawing() {
        val once = pipeline.renderFromScore(score, request(catalogId = "default"))
        val twice = pipeline.renderFromScore(score, request(catalogId = "default"))

        assertEquals(once.displaySvg, twice.displaySvg)
        assertEquals(once.renderHash, twice.renderHash)
    }

    /** Changing only the catalogue still changes the render hash -- the work is a new work. */
    @Test
    fun t2_theTwoCataloguesHashDifferently() {
        val default = pipeline.renderFromScore(score, request(catalogId = "default"))
        val vivid = pipeline.renderFromScore(score, request(catalogId = "vivid_material"))

        assertNotEquals(default.renderHash, vivid.renderHash)
    }

    // ── T-4 ────────────────────────────────────────────────

    /** What the server's expander answered, amplitude and seed to sha256(12). */
    private val serverVariation = listOf(
        Triple(null, null as Long?, "ca6cd37fdc87"),
        Triple("small", 7L, "c90c77aa4ef4"),
        Triple("medium", 7L, "0e29e8afd1b0"),
        Triple("small", 8L, "a2b6be9ceba9"),
        Triple("large", 7L, "338761eb9646"),
    )

    private val variationDdl = "画面の中央に太い墨の線を一本引く。右上に小さな円を三つ散らす。"

    private fun expand(amplitude: String?, seed: Long?): String = WebDdlExpander.expandIntermediateDdl(
        variationDdl,
        lang = "ja",
        variationAmplitude = amplitude,
        variationSeed = seed,
    )

    private fun sha12(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray()).joinToString("") { "%02x".format(it) }.take(12)

    /**
     * SPEC `:1140`: 「同じ記述 + 同じ vary 値 + 同じ performance seed は同じ出力を
     * 再現する」. Each row is the server's answer for that pair, not a value this
     * port wrote down for itself.
     */
    @Test
    fun t4_theSamePairAlwaysExpandsTheSameWay() {
        serverVariation.forEach { (amplitude, seed, expected) ->
            assertEquals(
                "amplitude=$amplitude seed=$seed",
                expected,
                sha12(expand(amplitude, seed)),
            )
            assertEquals(
                "and again, for the same pair",
                expected,
                sha12(expand(amplitude, seed)),
            )
        }
    }

    /**
     * The other direction, twice over. Without it, an expander that ignored both
     * arguments and returned a constant would pass the test above -- it would
     * simply return the same thing every time.
     */
    @Test
    fun t4_changingEitherHalfOfThePairChangesTheExpansion() {
        val small7 = sha12(expand("small", 7L))

        assertNotEquals("the seed alone moves it", small7, sha12(expand("small", 8L)))
        assertNotEquals("the amplitude alone moves it", small7, sha12(expand("medium", 7L)))
        assertNotEquals("and so does the largest", small7, sha12(expand("large", 7L)))
        assertNotEquals("a variation is not the unvaried expansion", small7, sha12(expand(null, null)))
    }

    /** 「両方そろって初めて有効」-- one half on its own does nothing at all. */
    @Test
    fun t4_halfAPairIsNoVariation() {
        val none = sha12(expand(null, null))

        assertEquals("an amplitude with no seed", none, sha12(expand("small", null)))
        assertEquals("a seed with no amplitude", none, sha12(expand(null, 7L)))
        assertEquals("an amplitude the server does not know", none, sha12(expand("enormous", 7L)))
    }

    // ── T-11 ───────────────────────────────────────────────

    /**
     * Every one of the five is consumed: changing it changes the Score, the SVG
     * or the metadata. An argument whose only consumer is a log line is invisible
     * to any test, which is how [I-142] happened.
     */
    @Test
    fun t11_theRenderSeedIsConsumed() {
        val a = pipeline.renderFromScore(score, request(renderSeed = 4242L))
        val b = pipeline.renderFromScore(score, request(renderSeed = 9999L))

        assertNotEquals("the performance differs", a.displaySvg, b.displaySvg)
        assertNotEquals(a.renderHash, b.renderHash)
        assertEquals("and it is reported back", 4242L, a.renderSeed)
        assertEquals(4242L, JSONObject(a.renderMetadataJson).getLong("render_seed"))
    }

    /**
     * `null` and `0` take the same road, because the server's
     * `render_metadata.get("render_seed") or new_render_seed()` is a truthiness
     * test: a zero is falsy there and a fresh seed is drawn. Two runs with no
     * seed therefore differ, and so do two runs with zero.
     */
    @Test
    fun t11_theRenderSeedIsAllocatedWhenNoneIsGivenAndWhenItIsZero() {
        val first = pipeline.renderFromScore(score, request(renderSeed = null))
        val second = pipeline.renderFromScore(score, request(renderSeed = null))
        val zero = pipeline.renderFromScore(score, request(renderSeed = 0L))

        assertNotEquals("an unnamed seed is a new seed each time", first.renderSeed, second.renderSeed)
        assertNotEquals("zero is not a seed either", 0L, zero.renderSeed)
        listOf(first, second, zero).forEach {
            assertNotEquals("something was drawn with", null, it.renderSeed)
            assertEquals(it.renderSeed, JSONObject(it.renderMetadataJson).getLong("render_seed"))
        }
    }

    /**
     * The composition seed reaches Stage 1.5 and changes nothing there -- and
     * that is the server's behaviour, not a gap in the port.
     *
     * `_expand_ja` / `_expand_en` still take `composition_seed`
     * (`ddl_expander.py:549`, `:576`) and neither body reads it: the axes it
     * used to steer were staffage, folded away in v2.11.0, and focus is decided
     * from the text and the variation plan. So the layout refinement gets its
     * new layout from Stage 2 being asked again, and the seed is the record of
     * which asking it was.
     *
     * This is stated rather than left out so that the day the server revives the
     * argument, the port's silence is a red test instead of a quiet divergence.
     */
    @Test
    fun t11_theCompositionSeedReachesStage1_5AndTheServerIgnoresItThere() {
        val a = WebDdlExpander.expandIntermediateDdl(variationDdl, lang = "ja", varySeed = 11L)
        val b = WebDdlExpander.expandIntermediateDdl(variationDdl, lang = "ja", varySeed = 12L)
        val none = WebDdlExpander.expandIntermediateDdl(variationDdl, lang = "ja", varySeed = null)

        assertEquals("the server reads no composition seed in Stage 1.5", sha12(a), sha12(b))
        assertEquals("nor does it read its absence", sha12(none), sha12(a))
    }

    /** What the composition seed *is* good for: it is carried to the save. */
    @Test
    fun t11_theCompositionSeedIsCarriedToTheSave() {
        val drawn = pipeline.renderFromScore(score, request(compositionSeed = 4711L))

        assertEquals(4711L, drawn.compositionSeed)
    }

    /**
     * The variation amplitude and the variation seed are the pair T-4 measured;
     * this states that the pair travels through [PaintRequest] rather than only
     * through a direct call to the expander.
     */
    @Test
    fun t11_theVariationPairTravelsOnTheRequest() {
        val small = request(variationAmplitude = "small", variationSeed = 7L)
        val large = request(variationAmplitude = "large", variationSeed = 7L)

        assertEquals("small", small.variationAmplitude)
        assertEquals(7L, small.variationSeed)
        // Carried through to the result, which is what the save records.
        val drawn = pipeline.renderFromScore(score, small)
        assertEquals("small", drawn.variationAmplitude)
        assertEquals(7L, drawn.variationSeed)
        assertNotEquals(small.variationAmplitude, large.variationAmplitude)
    }

    /**
     * The reading seed is recorded, not obeyed: the server treats it as an
     * opaque identifier for an explicit re-interpretation
     * (`render.py:190`) and never feeds it to a model. What has to be true is
     * that it survives to the save.
     */
    @Test
    fun t11_theInterpretationSeedIsCarriedToTheSave() {
        val drawn = pipeline.renderFromScore(score, request(interpretationSeed = "reading-1"))

        assertEquals("reading-1", drawn.interpretationSeed)
    }
}
