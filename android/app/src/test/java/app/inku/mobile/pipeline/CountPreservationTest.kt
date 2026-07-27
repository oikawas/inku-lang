package app.inku.mobile.pipeline

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A count the description stated outright is not a governor's to thin.
 *
 * `count_preservation.json` holds 50 cases run through the server's three count-touching
 * passes in the order the port runs them. Two kinds are in it and both are needed: 38
 * literal cases whose requested count must survive verbatim, and 12 represented cases
 * asking for 240 or more, which Stage 2 already stood in for at 110 and which must be
 * left at 110. Waving everything through breaks the represented side; representing
 * everything breaks the literal side. A check that reads only one kind passes either way.
 */
class CountPreservationTest {

    private val pipeline = LocalFallbackPipeline()

    private fun corpus(): JSONObject {
        val stream = javaClass.getResourceAsStream("/server_reference/count_preservation.json")
            ?: error("Resource /server_reference/count_preservation.json not found")
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }

    private fun instructionsOf(score: JSONObject): List<JSONObject> {
        val array = score.optJSONArray("instructions") ?: JSONArray()
        return (0 until array.length()).map { array.getJSONObject(it) }
    }

    private fun countsAfterPasses(case: JSONObject): List<Int> {
        val score = case.getJSONObject("score")
        val result = pipeline.applyDensityPassesForParity(
            instructions = instructionsOf(score),
            ddl = case.getString("ddl"),
            background = score.optString("background", "white"),
        )
        return result.map { it.optJSONObject("arrangement")?.optInt("count", 1) ?: 1 }
    }

    private fun expectedOf(case: JSONObject): List<Int> {
        val array = case.getJSONArray("expected_counts")
        return (0 until array.length()).map { array.getInt(it) }
    }

    @Test
    fun testEveryCaseMatchesTheServerCountsExactly() {
        val cases = corpus().getJSONArray("cases")
        val failures = mutableListOf<String>()
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            val actual = countsAfterPasses(case)
            val expected = expectedOf(case)
            if (actual != expected) {
                failures += "${case.getString("id")} (${case.getString("kind")}, " +
                    "requested ${case.getInt("requested")}): expected $expected but was $actual"
            }
        }
        // Report every case, not the first: a test that stops at the first mismatch hides
        // whether one kind is broken or both.
        assertTrue("Count mismatches:\n" + failures.joinToString("\n"), failures.isEmpty())
    }

    @Test
    fun testTheLiteralSideIsCounted() {
        val root = corpus()
        val cases = root.getJSONArray("cases")
        var literal = 0
        var survives = 0
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            if (case.getString("kind") != "literal") continue
            literal += 1
            if (countsAfterPasses(case) == listOf(case.getInt("requested"))) survives += 1
        }
        assertEquals("literal case count", root.getInt("literal_total"), literal)
        assertEquals(
            "every literal request must survive verbatim",
            root.getInt("literal_requested_survives"),
            survives,
        )
    }

    @Test
    fun testTheRepresentedSideIsCounted() {
        val root = corpus()
        val cases = root.getJSONArray("cases")
        val representative = root.getInt("representative_count")
        var represented = 0
        var atRepresentative = 0
        for (i in 0 until cases.length()) {
            val case = cases.getJSONObject(i)
            if (case.getString("kind") != "represented") continue
            represented += 1
            assertTrue(
                "${case.getString("id")} must be a request too large to count",
                case.getInt("requested") >= ServerScoreCounts.LITERAL_COUNT_THRESHOLD,
            )
            if (countsAfterPasses(case) == listOf(representative)) atRepresentative += 1
        }
        assertEquals("represented case count", root.getInt("represented_total"), represented)
        assertEquals(
            "every represented group must stay at the stand-in count",
            represented,
            atRepresentative,
        )
    }

    /**
     * The corpus is silent about two of the three things stage 5 changes: across all 50
     * cases the grid skip and the total-budget rewrite are never entered (measured against
     * the server: 0 cases move in either pass). These pin them directly.
     */
    @Test
    fun testAGridIsNeverThinned() {
        val grid = JSONObject()
            .put("primitive", "square")
            .put("position", JSONArray(listOf(0.1, 0.1)))
            .put("size", JSONArray(listOf(0.05, 0.05)))
            .put(
                "arrangement",
                JSONObject().put("count", 900).put("layout", "grid").put("rows", 30).put("cols", 30),
            )
        val out = pipeline.applyDensityPassesForParity(
            listOf(grid),
            ddl = "静かな画面に小さな四角を九百個で敷き詰める。",
            background = "white",
        )
        assertEquals("a grid keeps its count", listOf(900), out.map { it.getJSONObject("arrangement").getInt("count") })
    }

    @Test
    fun testTheTotalBudgetRepresentsTheLargestGroupFirstAndNeverRaisesACount() {
        // 380 + 120 = 500, over the 400 budget. The old proportional pass shrank both and
        // could raise the smaller group; the large one must give way and the small one
        // must come through whole and never larger than it was asked to be.
        fun group(count: Int, y: Double) = JSONObject()
            .put("primitive", "circle")
            .put("center", JSONArray(listOf(0.5, y)))
            .put("radius", 0.02)
            .put("arrangement", JSONObject().put("count", count).put("layout", "scatter"))

        val out = pipeline.applyDensityPassesForParity(
            listOf(group(380, 0.3), group(120, 0.7)),
            ddl = "小さな円を散らす。",
            background = "white",
        )
        val counts = out.map { it.getJSONObject("arrangement").getInt("count") }
        assertTrue("the total must come under budget", counts.sum() <= 400)
        assertTrue("no group may be raised above what it asked for", counts[0] <= 380 && counts[1] <= 120)
        assertTrue("the large group must give way first", counts[0] < 380)
        assertEquals("the small group stays literal", 120, counts[1])
    }

    @Test
    fun testExplicitCountsAreReadFromBothLanguages() {
        // Kanji and English number words; a bare digit grep finds neither.
        assertTrue(239 in ServerScoreCounts.explicitCountsFromDdl("黒いペンの小さな円を二百三十九個散らす。"))
        assertTrue(99 in ServerScoreCounts.explicitCountsFromDdl("短い線を上から下へ九十九本散らす。"))
        assertTrue(
            120 in ServerScoreCounts.explicitCountsFromDdl("Scatter one hundred twenty small black pen circles."),
        )
        // The number word must belong to a counted object, not to anything nearby.
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("Fill background with white."))
    }

    @Test
    fun testTheStandInBandCountsAsFollowingTheRequest() {
        // 110 is not the requested 240, but it is the stand-in the prompt asks for when the
        // request is too large to count. This is the whole represented side.
        assertTrue(ServerScoreCounts.countFollowsDdlRequest(110, setOf(240)))
        assertTrue(ServerScoreCounts.countFollowsDdlRequest(239, setOf(239)))
        // Below the literal threshold there is no stand-in to honour.
        assertTrue(!ServerScoreCounts.countFollowsDdlRequest(110, setOf(30)))
        assertTrue(!ServerScoreCounts.countFollowsDdlRequest(200, setOf(240)))
    }
}
