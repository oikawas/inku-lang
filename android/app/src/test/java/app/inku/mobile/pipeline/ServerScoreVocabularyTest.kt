package app.inku.mobile.pipeline

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The color vocabulary and the declaration order, which nothing else watches.
 *
 * The renderer can draw `yellow`, `orange` and `purple` without any of this:
 * a Score that already carries the word reaches the ink. What decides whether
 * the word can ever arrive is the embedded tool schema (Stage 2 only writes
 * what it is offered) and the coercer (which drops what it does not recognise).
 * Both are plain lists, and a list that is six long fails quietly.
 */
class ServerScoreVocabularyTest {

    private val contract: JSONObject by lazy {
        val stream = javaClass.getResourceAsStream("/server_reference/score_schema_contract.json")
            ?: error("score_schema_contract.json not found")
        JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun expectedEnum(name: String): List<String> {
        val array = contract.getJSONObject("enums").getJSONArray(name)
        return (0 until array.length()).map { array.getString(it) }
    }

    /** Reads the enum the embedded schema declares for a property, in order. */
    private fun declaredEnum(propertyKey: String): List<String> {
        val schema = ServerScoreSchemaJson.parameters
        val at = schema.indexOf(propertyKey)
        assertTrue("$propertyKey is not declared at all", at >= 0)
        val enumAt = schema.indexOf("\"enum\":[", at)
        assertTrue("$propertyKey declares no enum", enumAt >= 0)
        val close = schema.indexOf("]", enumAt)
        return schema.substring(enumAt + 8, close)
            .split(",")
            .map { it.trim().trim('"') }
    }

    @Test
    fun testTheSchemaOffersEveryAbstractColorTheServerOffers() {
        assertEquals(expectedEnum("color"), declaredEnum("\"color\":{"))
        assertEquals(expectedEnum("background"), declaredEnum("\"background\":{"))
        assertEquals(expectedEnum("color_cycle"), declaredEnum("\"color_cycle\":{"))
    }

    /**
     * The port's schema is smaller than the server's on purpose, so this asks
     * for a subsequence, not equality. It still pins `thinness` to the end,
     * where Stage 2 actually fills it.
     */
    /**
     * `center` and `radius` are declared on Presence and Arrangement too, so
     * the search has to start inside the Instruction block or the first hit is
     * a different field with the same name.
     */
    private fun instructionBlock(): String {
        val schema = ServerScoreSchemaJson.parameters
        val start = schema.indexOf("\"instructions\":{")
        assertTrue("the schema declares no instructions", start >= 0)
        val end = schema.indexOf("\"required\":[\"primitive\"]", start)
        assertTrue("the Instruction block has no end marker", end > start)
        return schema.substring(start, end)
    }

    @Test
    fun testTheDeclaredFieldsKeepTheServerOrder() {
        val schema = instructionBlock()
        val expected = contract.getJSONArray("instruction_property_order")
        val positions = mutableListOf<Pair<String, Int>>()
        for (i in 0 until expected.length()) {
            val name = expected.getString(i)
            val at = schema.indexOf("\"$name\":{")
            if (at >= 0) positions.add(name to at)
        }
        assertTrue("the schema declares almost nothing", positions.size >= 20)
        val outOfOrder = positions.zipWithNext()
            .filter { (a, b) -> a.second > b.second }
            .map { (a, b) -> "${a.first} must come before ${b.first}" }
        assertEquals(outOfOrder.joinToString("\n"), 0, outOfOrder.size)
    }

    @Test
    fun testTheSchemaDeclaresTheMachinesNote() {
        val schema = ServerScoreSchemaJson.parameters
        assertTrue("the note field is missing", schema.contains("\"note\":{"))
        assertTrue(
            "the note description must match the server",
            schema.contains(contract.getJSONObject("descriptions").getString("note")),
        )
    }

    @Test
    fun testTheCoercerKeepsEveryAbstractColorAndDropsTheRest() {
        val kept = mutableListOf<String>()
        for (color in expectedEnum("color")) {
            val coerced = ServerScoreCoercer.coerceInstruction(
                source = JSONObject().put("primitive", "circle").put("color", color),
                ddl = "",
                background = "white",
                detectColorKey = { _, _ -> color },
                detectWeightKey = { "pen" },
                visibleForeground = { _, _ -> color },
            )
            if (coerced.optString("color") == color) kept.add(color)
        }
        assertEquals(expectedEnum("color"), kept)

        val unknown = ServerScoreCoercer.coerceInstruction(
            source = JSONObject().put("primitive", "circle").put("color", "chartreuse"),
            ddl = "",
            background = "white",
            detectColorKey = { _, _ -> "chartreuse" },
            detectWeightKey = { "pen" },
            visibleForeground = { _, _ -> "chartreuse" },
        )
        assertEquals(
            "a word outside the vocabulary must not survive",
            "black",
            unknown.optString("color"),
        )
    }
}
