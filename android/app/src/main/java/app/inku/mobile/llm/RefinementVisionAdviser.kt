package app.inku.mobile.llm

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

internal const val REFINEMENT_VISION_ACTION = "refinement_vision_advice"
internal const val REFINEMENT_ADVICE_TOOL = "submit_refinement_advice"

data class RefinementVisionRequest(
    val modelId: String,
    val instruction: String,
    val direction: String,
    val enabledKinds: List<String>,
    val languageCode: String,
    val imagePng: ByteArray,
    val timeoutMs: Long = 120_000L,
)

data class RefinementVisionAdvice(
    val observation: String,
    val nextDirection: String,
    val suggestedKind: String,
    val model: String,
)

/** One bounded visual observation. The caller owns image preparation and the final human choice. */
class RefinementVisionAdviser(
    private val provider: ModelProvider,
    private val chatGptSession: ChatGptSessionRef? = null,
) {
    suspend fun advise(request: RefinementVisionRequest): RefinementVisionAdvice {
        val kinds = request.enabledKinds.filter { it in ALLOWED_KINDS }
        require(kinds.isNotEmpty()) { "At least one refinement kind is required" }
        RefinementVisionImage.requirePng768(request.imagePng)
        require(request.timeoutMs > 0) { "Positive refinement timeout required" }
        val context = JSONObject()
            .put("allowed_suggested_kinds", JSONArray(kinds))
            .put("constraints", JSONObject()
                .put("human_makes_final_choice", true)
                .put("no_accept_reject", true)
                .put("no_ranking", true)
                .put("no_score", true))
            .put("instruction", request.instruction)
            .put("user_direction", request.direction)
        val english = request.languageCode == "en"
        val message = (if (english) {
            "Observe this generation and return bounded refinement advice. Context:\n"
        } else {
            "この世代を観察し、限定された推敲助言を返してください。文脈:\n"
        }) + context
        val response = provider.generate(ModelRequest(
            modelId = request.modelId,
            prompt = message,
            temperature = 0.35,
            maxTokens = 320,
            systemInstruction = if (english) ENGLISH_SYSTEM else JAPANESE_SYSTEM,
            tool = ModelTool(REFINEMENT_ADVICE_TOOL, "Submit bounded visual refinement advice.", ADVICE_SCHEMA),
            timeoutMs = request.timeoutMs,
            pipelineAction = REFINEMENT_VISION_ACTION,
            imagePng = request.imagePng,
            chatGptSession = chatGptSession,
        ))
        return parseAdvice(response.text, request.modelId, kinds)
    }

    private fun parseAdvice(raw: String, model: String, kinds: List<String>): RefinementVisionAdvice {
        // Server accepts a JSON object inside a fence or prose, from first brace to last.
        val text = raw.trim()
        val start = text.indexOf('{')
        val end = text.lastIndexOf('}')
        val body = if (start >= 0 && end > start) text.substring(start, end + 1) else text
        val parsed = try {
            JSONObject(body)
        } catch (error: JSONException) {
            throw IllegalArgumentException("Vision model returned invalid refinement advice JSON", error)
        }
        fun field(name: String): String = parsed.opt(name)
            .takeUnless { it == null || it == JSONObject.NULL }?.toString()?.trim().orEmpty()
        val observation = field("observation")
        val nextDirection = field("next_direction")
        require(observation.isNotEmpty() && nextDirection.isNotEmpty()) {
            "Vision model returned empty refinement advice"
        }
        val suggested = field("suggested_kind").takeIf { it in kinds } ?: kinds.first()
        return RefinementVisionAdvice(
            observation = observation.takeCodePoints(2000),
            nextDirection = nextDirection.takeCodePoints(2000),
            suggestedKind = suggested,
            model = model,
        )
    }

    private fun String.takeCodePoints(limit: Int): String =
        if (codePointCount(0, length) <= limit) this else substring(0, offsetByCodePoints(0, limit))

    private companion object {
        val ALLOWED_KINDS = setOf("catalog_change", "layout_change")
        const val ENGLISH_SYSTEM = "You are a visual adviser in a bounded artwork-refinement loop. Observe only visible facts and " +
            "alignment with the supplied instruction. Never score, rank, accept, reject, praise, or condemn. " +
            "Suggest one concrete direction to try next without claiming it is better. Return JSON only with " +
            "observation, next_direction, and suggested_kind."
        const val JAPANESE_SYSTEM = "あなたは世代数を限定した作品推敲ループの視覚的助言者です。画像に見える事実と、与えられた指示との対応だけを観察してください。" +
            "点数、順位、合否、称賛、否定を行わず、より良いと断定せずに次に試す具体的な方向を一つ提案してください。" +
            "observation、next_direction、suggested_kindを持つJSONだけを返してください。"
        const val ADVICE_SCHEMA = """{"type":"object","properties":{"observation":{"type":"string"},"next_direction":{"type":"string"},"suggested_kind":{"type":"string"}},"required":["observation","next_direction","suggested_kind"],"additionalProperties":false}"""
    }
}
