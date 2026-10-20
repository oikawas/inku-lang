package app.inku.mobile.llm

import app.inku.mobile.data.refinement.SharedJuxtaposition
import java.io.File
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/** The flow Server's `suggest_juxtaposition` runs, with the production core and a recording provider. */
class JuxtapositionAdviserTest {
    private class AnsweringProvider(private val answers: MutableList<String>) : ModelProvider {
        override val providerId = "test"
        val requests = mutableListOf<ModelRequest>()
        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            return ModelResponse(answers.removeAt(0), request.modelId)
        }
    }

    private val checks: List<JSONObject> by lazy {
        val identityCases = File(requireNotNull(System.getProperty("inku.identityCases")))
        val array = JSONObject(identityCases.resolveSibling("juxtaposition-cases.json").readText()).getJSONArray("check")
        (0 until array.length()).map(array::getJSONObject)
    }
    private val accepted get() = checks.first { it.has("choices") }
    private val refused get() = checks.first { it.has("detail") && it.getJSONObject("request").getString("language") == "ja" }

    private fun request(candidates: JSONArray = accepted.getJSONObject("request").getJSONArray("candidates")) = JuxtapositionRequest(
        modelId = "test:vision",
        description = "今の記述。",
        written = "3. 今の記述。",
        lineage = listOf("根の記述。", "今の記述。"),
        candidates = candidates,
        languageCode = "ja",
        imagePng = refinementPngHeader(),
    )

    @Test
    fun theCorePromptGoesWithThePngAndEachPickIsJoinedToTheLabelledDescription() = runBlocking {
        val provider = AnsweringProvider(mutableListOf(accepted.getJSONObject("request").getString("answer")))
        val session = ChatGptSessionRef("profile-a", 7)
        val sent = request()
        val result = JuxtapositionAdviser(provider, session).suggest(sent)

        val asked = provider.requests.single()
        val (system, text) = SharedJuxtaposition.prompt("ja", "今の記述。", sent.lineage, sent.candidates, null)
        assertEquals(system, asked.systemInstruction)
        assertEquals(text, asked.prompt)
        assertEquals(JUXTAPOSITION_VISION_ACTION, asked.pipelineAction)
        assertEquals(0.35, asked.temperature, 0.0)
        assertEquals(1200, asked.maxTokens)
        assertEquals(120_000L, asked.timeoutMs)
        assertEquals(session, asked.chatGptSession)
        assertArrayEquals(refinementPngHeader(), asked.imagePng)

        assertEquals("test:vision", result.model)
        assertEquals(sent.candidates.length(), result.candidates)
        assertEquals(4, result.choices.size)
        // The model read the description without its label; the child keeps it.
        result.choices.forEach { assertEquals("3. 今の記述。${it.sentence}", it.joined) }
    }

    @Test
    fun aRefusedAnswerIsSentBackOnceWithTheReason() = runBlocking {
        val provider = AnsweringProvider(mutableListOf(
            refused.getJSONObject("request").getString("answer"),
            accepted.getJSONObject("request").getString("answer"),
        ))
        val result = JuxtapositionAdviser(provider).suggest(request())
        assertEquals(2, provider.requests.size)
        assertTrue(provider.requests[1].prompt.contains(refused.getString("detail")))
        assertEquals(4, result.choices.size)
    }

    @Test
    fun aSecondRefusalIsAnErrorWithTheReason() {
        val answer = refused.getJSONObject("request").getString("answer")
        val provider = AnsweringProvider(mutableListOf(answer, answer))
        val error = assertThrows(JuxtapositionException::class.java) {
            runBlocking { JuxtapositionAdviser(provider).suggest(request()) }
        }
        assertEquals(refused.getString("detail"), error.message)
        assertEquals(false, error.tooFew)
        assertEquals(2, provider.requests.size)
    }

    @Test
    fun fewerThanFourCandidatesSendNothing() {
        val provider = AnsweringProvider(mutableListOf())
        val three = JSONArray((0 until 3).map { accepted.getJSONObject("request").getJSONArray("candidates").get(it) })
        val error = assertThrows(JuxtapositionException::class.java) {
            runBlocking { JuxtapositionAdviser(provider).suggest(request(three)) }
        }
        assertTrue(error.tooFew)
        assertTrue(provider.requests.isEmpty())
    }

    @Test
    fun onlyTheTwoVisionActionsCarryAPng() {
        val png = refinementPngHeader()
        val juxtaposition = ModelRequest(modelId = "m", prompt = "p", temperature = 0.35, maxTokens = 1200,
            pipelineAction = JUXTAPOSITION_VISION_ACTION, imagePng = png)
        assertEquals("image/png", juxtaposition.imagePayload()!!.mimeType)
        assertTrue(isVisionTextAction(JUXTAPOSITION_VISION_ACTION))
        assertTrue(isVisionTextAction(REFINEMENT_VISION_ACTION))
        assertEquals(false, isVisionTextAction("generate_normalized_ddl"))
        assertThrows(IllegalArgumentException::class.java) {
            ModelRequest(modelId = "m", prompt = "p", temperature = 0.35, maxTokens = 1200,
                pipelineAction = "generate_normalized_ddl", imagePng = png).imagePayload()
        }
    }
}
