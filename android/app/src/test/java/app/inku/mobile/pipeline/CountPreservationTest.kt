package app.inku.mobile.pipeline

import app.inku.mobile.ReferenceCorpus
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A count the description stated outright is not a governor's to thin.
 *
 * `count_preservation.json` holds the cases run through the server's three count-touching
 * passes in the order the port runs them. Two kinds are in it and both are needed: the
 * literal cases whose requested count must survive verbatim, and the represented ones
 * asking for 240 or more, which Stage 2 already stood in for at 110 and which must be
 * left at 110. Waving everything through breaks the represented side; representing
 * everything breaks the literal side. A check that reads only one kind passes either way.
 * The counts of each kind are read from the corpus rather than written here, because a
 * number in a comment goes stale the day a case is added.
 *
 * One case (`en-numeral-99`) states its count as an English numeral. Every other case
 * states its count in words, so before ruling B ([I-204]) the whole corpus passed against
 * a reader that could not read a numeral at all.
 */
class CountPreservationTest {

    private val pipeline = LocalFallbackPipeline()

    private fun corpus(): JSONObject = ReferenceCorpus.json("count_preservation.json")

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

    /**
     * Ruling B ([I-204]): a numeral is a count, and the noun that follows is not asked
     * about. Condition for condition against `_explicit_counts_from_ddl` in `counts.py`.
     */
    @Test
    fun testTheEnglishPathReadsANumeral() {
        assertEquals(setOf(12), ServerScoreCounts.explicitCountsFromDdl("Draw 12 circles."))
        assertEquals(setOf(233), ServerScoreCounts.explicitCountsFromDdl("Draw 233 marks."))
        assertEquals(
            setOf(40),
            ServerScoreCounts.explicitCountsFromDdl("Line up 40 short horizontal red strokes."),
        )
    }

    @Test
    fun testTheEnglishPathDoesNotRequireANounItKnows() {
        // `petals` was never in the 32-word table the reader used to require.
        assertEquals(setOf(12), ServerScoreCounts.explicitCountsFromDdl("Draw twelve petals."))
    }

    @Test
    fun testTheJapanesePathDidNotMove() {
        // No counter, so still unread: a bare numeral in Japanese is an angle or a
        // fraction as often as it is a count, and that needs its own ruling.
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("十二の円を描く。"))
        assertEquals(setOf(12), ServerScoreCounts.explicitCountsFromDdl("円を12個描く。"))
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("立方体の向き: 30度回転。"))
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("画面下1/3に灰色の線を引く。"))
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("下草を50散らす。"))
    }

    /**
     * T-18: the port answers "how many did the description say" the way the server does.
     *
     * The expected values are generated from the server implementation into
     * `count_preservation.json`, never written here. A table written here would go on
     * passing from the day the server rule next moves, and freeze the drift in place --
     * which is exactly what the twenty-one-kanji table this replaced was doing.
     */
    @Test
    fun testTheCountHintMatchesTheServer() {
        val cases = corpus().getJSONArray("count_hint_cases")
        assertEquals(6, cases.length())
        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val ddl = case.getString("ddl")
            val lang = if (case.isNull("lang")) null else case.getString("lang")
            val separates = case.getString("separates")

            val expectedHint = if (case.isNull("count_hint")) null else case.getInt("count_hint")
            assertEquals("$ddl ($separates)", expectedHint, ServerScoreSemantics.countHintFromDdl(ddl, lang))

            val expected = case.getJSONArray("explicit_counts")
            val expectedCounts = (0 until expected.length()).map { expected.getInt(it) }.toSet()
            assertEquals("$ddl ($separates)", expectedCounts, ServerScoreCounts.explicitCountsFromDdl(ddl, lang))
        }
    }

    /**
     * T-19: the hand-written kanji table is gone, and the shared reader answers instead.
     *
     * The table read the first digit run anywhere in the description with none of the
     * exclusions, so these three answered 0, 30 and 1 before.
     */
    @Test
    fun testTheHandWrittenKanjiTableIsGone() {
        val semantics = ServerScoreSemantics::class.java
        val source = semantics.declaredMethods.count { it.name == "countHintFromDdl" }
        assertTrue("countHintFromDdl must still exist on ServerScoreSemantics", source > 0)

        assertEquals(null, ServerScoreSemantics.countHintFromDdl("Place a circle of radius 0.11 here."))
        assertEquals(null, ServerScoreSemantics.countHintFromDdl("\u7acb\u65b9\u4f53\u306e\u5411\u304d: 30\u5ea6\u56de\u8ee2"))
        // A number the twenty-one-entry table had no row for, and could not have read.
        assertEquals(43, ServerScoreSemantics.countHintFromDdl("\u7dda\u3092\u56db\u5341\u4e09\u672c\u4e26\u3079\u308b\u3002"))
    }

    @Test
    fun testADigitInsideAnotherNumberIsNotACount() {
        assertEquals(
            emptySet<Int>(),
            ServerScoreCounts.explicitCountsFromDdl("Place a circle of radius 0.11 in the lower-right focus."),
        )
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("Cover 1/3 of the field in gray."))
        assertEquals(emptySet<Int>(), ServerScoreCounts.explicitCountsFromDdl("Leave 40% of the field empty."))
    }

    @Test
    fun testExplicitCountsAreReadFromBothLanguages() {
        // Kanji and English number words; a bare digit grep finds neither.
        assertTrue(239 in ServerScoreCounts.explicitCountsFromDdl("黒いペンの小さな円を二百三十九個散らす。"))
        assertTrue(99 in ServerScoreCounts.explicitCountsFromDdl("短い線を上から下へ九十九本散らす。"))
        assertTrue(
            120 in ServerScoreCounts.explicitCountsFromDdl("Scatter one hundred twenty small black pen circles."),
        )
        // A description that states no number states no count. (Until ruling B the reader
        // also asked what was being counted; it no longer does, on either side.)
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
