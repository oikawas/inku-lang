package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The data-layer half of "a fill is one request, however it is written" ([I-248]).
 *
 * Coerce derives each spelling from the other, the texture vocabulary carries the
 * word, and the schema offers it to Stage 2. None of this is visible to the frozen
 * corpus -- the corpus is replayed straight into the renderer and never passes
 * through coerce -- so every gate here is stated as a property, with the control
 * that must not move beside it.
 */
class AFillIsOneRequestCoerceTest {

    private fun coerce(source: JSONObject): JSONObject = ServerScoreCoercer.coerceInstruction(
        source = source,
        ddl = "",
        background = "white",
        detectColorKey = { _, _ -> "black" },
        detectWeightKey = { "pen" },
        visibleForeground = { _, _ -> "black" },
    )

    private fun square(build: JSONObject.() -> Unit): JSONObject = JSONObject()
        .put("primitive", "square")
        .put("position", JSONArray(listOf(0.3, 0.3)))
        .put("size", JSONArray(listOf(0.2, 0.2)))
        .put("weight", "pen")
        .put("color", "black")
        .apply(build)

    private fun surface(texture: String): JSONObject = JSONObject().put("texture", texture)

    /** T-136: `solid` derives the boolean, and an instruction already filled is left alone. */
    @Test
    fun testASolidSurfaceDerivesTheFilledBoolean() {
        val derived = coerce(square { put("surface", surface("solid")) })
        assertTrue("solid must derive filled=true", derived.optBoolean("filled", false))
        assertEquals("the surface word must survive the derivation", "solid", derived.getJSONObject("surface").optString("texture"))

        val alreadyFilled = coerce(square { put("filled", true); put("surface", surface("solid")) })
        assertTrue("an instruction already filled must stay filled", alreadyFilled.optBoolean("filled", false))
        assertEquals("and must keep saying solid", "solid", alreadyFilled.getJSONObject("surface").optString("texture"))
    }

    /** T-137: the boolean derives the word, and a real texture is never overwritten. */
    @Test
    fun testAFilledShapeDerivesTheSolidSurfaceWord() {
        val derived = coerce(square { put("filled", true) })
        assertEquals(
            "filled=true with no surface must derive texture=solid",
            "solid",
            derived.getJSONObject("surface").optString("texture"),
        )

        val fromNone = coerce(square { put("filled", true); put("surface", surface("none")) })
        assertEquals(
            "a surface that says none must be filled in the same way",
            "solid",
            fromNone.getJSONObject("surface").optString("texture"),
        )

        val hatched = coerce(square { put("filled", true); put("surface", surface("hatch")) })
        assertEquals(
            "a real texture must not be overwritten by the derivation",
            "hatch",
            hatched.getJSONObject("surface").optString("texture"),
        )
    }

    /** T-138: a line has no interior, so neither statement means anything on one. */
    @Test
    fun testTheDerivationDoesNotReachALine() {
        val line = coerce(
            JSONObject()
                .put("primitive", "line")
                .put("from", JSONArray(listOf(0.1, 0.5)))
                .put("to", JSONArray(listOf(0.9, 0.5)))
                .put("weight", "pen")
                .put("color", "black")
                .put("filled", true)
        )
        assertFalse("a line must not be given a surface it cannot show", line.has("surface"))
    }

    /** T-139: the vocabulary carries `solid`, and still drops a word it has never heard. */
    @Test
    fun testTheVocabularyCarriesSolidAndStillDropsAWordItDoesNotKnow() {
        val solid = coerce(square { put("surface", surface("solid")) })
        assertEquals("solid must survive the texture vocabulary", "solid", solid.getJSONObject("surface").optString("texture"))

        val unknown = coerce(square { put("surface", surface("marble")) })
        assertEquals(
            "a word outside the vocabulary must still fall to none",
            "none",
            unknown.getJSONObject("surface").optString("texture"),
        )
    }

    /**
     * T-140: the two copies of the texture vocabulary agree, in the same order.
     *
     * The port has no way to read the server's schema at run time, so this measures
     * the two copies against each other rather than against a list written out by
     * hand -- a hand-written expectation would go on being green from the day the
     * server added a tenth word, guarding the stale copy instead of the agreement.
     * Whether the pair agrees with `SurfaceTexture` in `schema.py` is the server
     * suite's business (§5 of the contract).
     */
    @Test
    fun testTheSchemaOffersExactlyTheTexturesTheCoercerKeeps() {
        val schema = ServerScoreSchemaJson.parameters
        val marker = "\"texture\":{"
        val at = schema.indexOf(marker)
        assertTrue("the schema must declare a texture field", at >= 0)
        val enumAt = schema.indexOf("\"enum\":[", at)
        assertTrue("the texture field must offer an enum", enumAt >= 0)
        val close = schema.indexOf(']', enumAt)
        val offered = schema.substring(enumAt + "\"enum\":[".length, close)
            .split(',')
            .map { it.trim().trim('"') }

        assertEquals(
            "the schema's texture enum and the coercer's allowlist must be the same words in the same order",
            ServerScoreCoercer.surfaceTextures.toList(),
            offered,
        )
        assertTrue("solid must be one of them", "solid" in offered)
    }

    /**
     * T-141: the tempering of an oversized filled shape reads the request, not the
     * boolean.
     *
     * Driven straight at the tempering rather than through `normalizeServerScore`,
     * because coerce derives `filled=true` from `solid` one step earlier: down that
     * road the gate would stay green with the tempering back on the boolean, and
     * measure nothing. That the tempering sits in the production chain at all is
     * pinned separately by [FilledShapeTemperingWiringTest].
     */
    @Test
    fun testTheTemperingReadsTheRequestNotTheBoolean() {
        val temper = LocalFallbackPipeline::class.java.getDeclaredMethod(
            "temperUnintentionalFilledShape",
            JSONObject::class.java,
            String::class.java,
        ).apply { isAccessible = true }

        fun tempered(sizeW: Double, sizeH: Double): JSONObject = temper.invoke(
            LocalFallbackPipeline(),
            JSONObject()
                .put("primitive", "square")
                .put("center", JSONArray(listOf(0.5, 0.5)))
                .put("size", JSONArray(listOf(sizeW, sizeH)))
                .put("surface", JSONObject().put("texture", "solid"))
                .put("style", "solid")
                .put("weight", "pen")
                .put("mode", "additive")
                .put("color", "black"),
            "四角を描く",
        ) as JSONObject

        val large = tempered(0.6, 0.5)
        assertEquals("a large shape asking for a fill with the surface word must be tempered", 0.36, large.getJSONArray("size").getDouble(0), 0.001)
        assertEquals("a large shape asking for a fill with the surface word must be tempered", 0.30, large.getJSONArray("size").getDouble(1), 0.001)

        val small = tempered(0.2, 0.2)
        assertEquals("a shape under the threshold must not be tempered", 0.2, small.getJSONArray("size").getDouble(0), 0.001)
        assertEquals("a shape under the threshold must not be tempered", 0.2, small.getJSONArray("size").getDouble(1), 0.001)
    }
}
