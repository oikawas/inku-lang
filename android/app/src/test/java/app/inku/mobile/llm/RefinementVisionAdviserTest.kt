package app.inku.mobile.llm

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class RefinementVisionAdviserTest {
    private class AnsweringProvider(var answer: String) : ModelProvider {
        override val providerId = "test"
        val requests = mutableListOf<ModelRequest>()
        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            return ModelResponse(answer, request.modelId)
        }
    }

    private fun request(kinds: List<String> = listOf("layout_change")) = RefinementVisionRequest(
        modelId = "test:vision",
        instruction = "a quiet circle",
        direction = "leave more space",
        enabledKinds = kinds,
        languageCode = "en",
        imageJpeg = byteArrayOf(1, 2, 3),
    )

    @Test
    fun adviceRequestCarriesBoundedObservationContextImageAndAnswerTool() = runBlocking {
        val provider = AnsweringProvider("""Here is the advice:
            ```json
            {"observation":"A circle sits low.","next_direction":"Move it upward.","suggested_kind":"other"}
            ```""")
        val session = ChatGptSessionRef("profile-a", 7)
        val advice = RefinementVisionAdviser(provider, session).advise(request(listOf("unknown", "layout_change")))
        assertEquals("A circle sits low.", advice.observation)
        assertEquals("Move it upward.", advice.nextDirection)
        assertEquals("layout_change", advice.suggestedKind)
        assertEquals("test:vision", advice.model)

        val sent = provider.requests.single()
        assertEquals(REFINEMENT_VISION_ACTION, sent.pipelineAction)
        assertEquals(REFINEMENT_ADVICE_TOOL, sent.tool?.name)
        assertEquals(320, sent.maxTokens)
        assertEquals(0.35, sent.temperature, 0.0)
        assertEquals(120_000L, sent.timeoutMs)
        assertEquals(session, sent.chatGptSession)
        assertTrue(sent.imageJpeg!!.contentEquals(byteArrayOf(1, 2, 3)))
        assertTrue(sent.systemInstruction!!.contains("Never score, rank, accept, reject"))
        val context = JSONObject(sent.prompt.substringAfter("Context:\n"))
        assertEquals("a quiet circle", context.getString("instruction"))
        assertEquals("leave more space", context.getString("user_direction"))
        assertEquals("layout_change", context.getJSONArray("allowed_suggested_kinds").getString(0))
        assertEquals(1, context.getJSONArray("allowed_suggested_kinds").length())
        val constraints = context.getJSONObject("constraints")
        for (key in listOf("no_score", "no_ranking", "no_accept_reject", "human_makes_final_choice")) {
            assertTrue(constraints.getBoolean(key))
        }
    }

    @Test
    fun emptyAdviceAndNoAllowedKindsFailWithoutAcceptingOrSendingThem() {
        val provider = AnsweringProvider("""{"observation":" ","next_direction":"Try a line","suggested_kind":"layout_change"}""")
        val adviser = RefinementVisionAdviser(provider)
        assertThrows(IllegalArgumentException::class.java) { runBlocking { adviser.advise(request()) } }
        assertEquals(1, provider.requests.size)
        provider.answer = """{"observation":"A circle","next_direction":" ","suggested_kind":"layout_change"}"""
        assertThrows(IllegalArgumentException::class.java) { runBlocking { adviser.advise(request()) } }
        assertEquals(2, provider.requests.size)
        assertThrows(IllegalArgumentException::class.java) {
            runBlocking { adviser.advise(request(listOf("unknown"))) }
        }
        assertEquals(2, provider.requests.size)
        provider.answer = "not json"
        assertThrows(IllegalArgumentException::class.java) { runBlocking { adviser.advise(request()) } }
    }

    @Test
    fun adviceFieldsAreLimitedToTwoThousandUnicodeCharacters() = runBlocking {
        val long = "😀".repeat(2001)
        val provider = AnsweringProvider(JSONObject()
            .put("observation", long)
            .put("next_direction", long)
            .put("suggested_kind", "layout_change").toString())
        val advice = RefinementVisionAdviser(provider).advise(request())
        assertEquals(2000, advice.observation.codePointCount(0, advice.observation.length))
        assertEquals(2000, advice.nextDirection.codePointCount(0, advice.nextDirection.length))
        assertFalse(advice.observation.endsWith("\uD83D"))
    }
}
