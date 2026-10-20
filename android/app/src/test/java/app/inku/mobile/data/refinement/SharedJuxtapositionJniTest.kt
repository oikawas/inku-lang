package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.CoreIdentityJson
import java.io.File
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The shared juxtaposition cases (`server/tests/data/juxtaposition-cases.json`)
 * cross Android's call into the production JNI library and answer as the core
 * and Server do. The table's `first_sentence` and `language` rows have no
 * action of their own; the core reaches them through `gather`.
 */
class SharedJuxtapositionJniTest {
    private val cases: JSONObject by lazy {
        val identityCases = File(requireNotNull(System.getProperty("inku.identityCases")))
        JSONObject(identityCases.resolveSibling("juxtaposition-cases.json").readText())
    }

    private fun rows(section: String): List<JSONObject> {
        val array = cases.getJSONArray(section)
        return (0 until array.length()).map(array::getJSONObject)
    }

    private fun ok(outcome: SharedJuxtaposition.Outcome, why: String): JSONObject = when (outcome) {
        is SharedJuxtaposition.Outcome.Ok -> outcome.value
        is SharedJuxtaposition.Outcome.Refused -> throw AssertionError("$why: refused ${outcome.detail}")
    }

    private fun strings(array: JSONArray): List<String> = (0 until array.length()).map(array::getString)

    private fun sources(request: JSONObject): List<SharedJuxtaposition.Source> {
        val array = request.getJSONArray("sources")
        return (0 until array.length()).map { array.getJSONObject(it) }
            .map { SharedJuxtaposition.Source(it.getString("id"), it.getString("text")) }
    }

    private fun gather(request: JSONObject, limit: Int, seed: ULong = 7u): JSONArray = SharedJuxtaposition.gather(
        sources(request), request.getString("description"), strings(request.getJSONArray("lineage")),
        strings(request.getJSONArray("added")), strings(request.getJSONArray("exclude")), seed, limit,
    )

    @Test
    fun everySharedPairIsOneSentenceOrTwoAsTheCoreSays() {
        val table = rows("same")
        assertEquals(8, table.size)
        for (row in table) {
            val answer = ok(SharedJuxtaposition.call("same", JSONObject().put("a", row.getString("a")).put("b", row.getString("b"))),
                row.getString("why"))
            assertEquals(row.getString("why"), row.getBoolean("same"), answer.getBoolean("same"))
        }
    }

    @Test
    fun everySharedJoinAddsTheSentenceAsWebDid() {
        val table = rows("join")
        assertEquals(13, table.size)
        for (row in table) {
            val answer = ok(SharedJuxtaposition.call("join", JSONObject()
                .put("description", row.getString("description")).put("sentence", row.getString("sentence"))), row.toString())
            assertEquals(row.toString(), row.getString("joined"), answer.getString("joined"))
        }
    }

    @Test
    fun everySharedGatheringKeepsTheSentencesServerKept() {
        val table = rows("gather")
        assertEquals(5, table.size)
        for (row in table) {
            val why = row.getString("why")
            val request = row.getJSONObject("request")
            val kept = row.getJSONObject("kept")
            val drawn = gather(request, request.getInt("limit"))
            assertEquals(why, row.getInt("count"), drawn.length())
            for (index in 0 until drawn.length()) {
                val candidate = drawn.getJSONObject(index)
                assertEquals("$why: ${candidate.getString("sentence")}",
                    CoreIdentityJson.canonical(kept.getJSONArray(candidate.getString("sentence"))),
                    CoreIdentityJson.canonical(candidate.getJSONArray("history_ids")))
            }
            val everything = gather(request, 10_000)
            assertEquals(why, kept.length(), everything.length())
        }
    }

    @Test
    fun aSeedAboveTheSignedRangeCrossesAsItsDecimal() {
        val request = rows("gather")[2].getJSONObject("request")
        fun order(seed: ULong) = (0 until 10).map { gather(request, 10, seed).getJSONObject(it).getString("id") }
        assertEquals(order(ULong.MAX_VALUE), order(ULong.MAX_VALUE))
        assertTrue(order(ULong.MAX_VALUE) != order(ULong.MAX_VALUE - 1u))
    }

    @Test
    fun everySharedAnswerIsCheckedAsServerCheckedIt() {
        val table = rows("check")
        assertEquals(8, table.size)
        for (row in table) {
            val why = row.getString("why")
            val request = row.getJSONObject("request")
            val outcome = SharedJuxtaposition.check(request.getString("language"), request.getString("answer"),
                request.getJSONArray("candidates"), request.getString("description"))
            val expected = row.optJSONArray("choices")
            if (expected == null) {
                assertTrue("$why: $outcome", outcome is SharedJuxtaposition.Outcome.Refused)
                assertEquals(why, row.getString("detail"), (outcome as SharedJuxtaposition.Outcome.Refused).detail)
                continue
            }
            val choices = SharedJuxtaposition.choices(ok(outcome, why))
            assertEquals(why, expected.length(), choices.size)
            choices.forEachIndexed { index, choice ->
                val want = expected.getJSONObject(index)
                assertEquals(why, want.getString("sentence"), choice.sentence)
                assertEquals(why, want.getString("reason"), choice.reason)
                assertEquals(why, strings(want.getJSONArray("history_ids")), choice.historyIds)
                assertEquals(why, want.getInt("rank"), choice.rank)
                assertEquals(why, want.getDouble("position"), choice.position, 0.0)
                assertEquals(why, want.getString("joined"), choice.joined)
            }
        }
    }

    @Test
    fun everySharedPromptIsTheTextServerSent() {
        val table = rows("prompt")
        assertEquals(2, table.size)
        for (row in table) {
            val request = row.getJSONObject("request")
            val (system, text) = SharedJuxtaposition.prompt(request.getString("language"), request.getString("description"),
                strings(request.getJSONArray("lineage")), request.getJSONArray("candidates"),
                request.optString("resend").takeIf { !request.isNull("resend") })
            assertEquals(row.getString("why"), row.getString("system"), system)
            assertEquals(row.getString("why"), row.getString("text"), text)
        }
    }

    @Test
    fun aRequestTheCoreCannotReadIsAnError() {
        assertThrows(IllegalArgumentException::class.java) {
            SharedJuxtaposition.call("gather", JSONObject().put("sources", JSONArray()))
        }
    }

    @Test
    fun theChildRecordsWhatWebRecords() {
        val choice = JuxtapositionChoice("一文3。", "三つ目", listOf("w3"), 1, 0.4, "今の記述。一文3。")
        val metadata = juxtapositionMetadata(choice, JuxtapositionResult(listOf(choice), 12, "openai:gpt-vision"))
        assertEquals(
            CoreIdentityJson.canonical(JSONObject("""{"juxtaposition":{"sentence":"一文3。","history_ids":["w3"],"rank":1,""" +
                """"reason":"三つ目","position":0.4,"candidates":12,"model":"openai:gpt-vision"}}""")),
            CoreIdentityJson.canonical(metadata),
        )
    }
}
