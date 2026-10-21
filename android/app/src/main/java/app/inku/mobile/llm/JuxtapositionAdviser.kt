package app.inku.mobile.llm

import app.inku.mobile.data.refinement.JuxtapositionResult
import app.inku.mobile.data.refinement.SharedJuxtaposition
import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import org.json.JSONArray

internal const val JUXTAPOSITION_VISION_ACTION = "juxtaposition_vision"

/** Only juxtaposition sends an image and asks for plain assistant text. */
internal fun isVisionTextAction(action: String?): Boolean = action == JUXTAPOSITION_VISION_ACTION

data class JuxtapositionRequest(
    val modelId: String,
    /** The work's description with its labels removed: what the model reads. */
    val description: String,
    /** The description as the work keeps it, labels and all: what each pick is joined to. */
    val written: String,
    /** The lineage's descriptions, root to the work, labels removed. */
    val lineage: List<String>,
    /** The candidates `gather` returned, as the core wrote them. */
    val candidates: JSONArray,
    val languageCode: String,
    val imagePng: ByteArray,
    val timeoutMs: Long = 120_000L,
)

/** Fewer than four sentences to choose from, or an answer refused twice. */
class JuxtapositionException(message: String, val tooFew: Boolean = false) : RuntimeException(message)

/**
 * Four sentences a Vision model would add, in the order it picked them
 * (Server's `suggest_juxtaposition`). An answer the core refuses -- a sentence
 * not offered, one named twice, an empty reason -- is sent back once with the
 * reason; a second refusal is an error.
 */
class JuxtapositionAdviser(
    private val provider: ModelProvider,
    private val chatGptSession: ChatGptSessionRef? = null,
    private val binding: SharedPipelineBinding = NativePipelineBridge,
) {
    suspend fun suggest(request: JuxtapositionRequest): JuxtapositionResult {
        if (request.candidates.length() < SharedJuxtaposition.CHOICES) {
            throw JuxtapositionException("not enough candidate sentences", tooFew = true)
        }
        RefinementVisionImage.requirePng768(request.imagePng)
        require(request.timeoutMs > 0) { "Positive juxtaposition timeout required" }
        var reason: String? = null
        repeat(2) {
            val (system, text) = SharedJuxtaposition.prompt(request.languageCode, request.description,
                request.lineage, request.candidates, reason, binding)
            val answer = provider.generate(ModelRequest(
                modelId = request.modelId,
                prompt = text,
                temperature = 0.35,
                maxTokens = 1200,
                systemInstruction = system,
                timeoutMs = request.timeoutMs,
                pipelineAction = JUXTAPOSITION_VISION_ACTION,
                imagePng = request.imagePng,
                chatGptSession = chatGptSession,
            )).text
            when (val checked = SharedJuxtaposition.check(request.languageCode, answer, request.candidates,
                request.written, binding)) {
                is SharedJuxtaposition.Outcome.Ok -> return JuxtapositionResult(
                    choices = SharedJuxtaposition.choices(checked.value),
                    candidates = checked.value.getInt("candidates"),
                    model = request.modelId,
                )
                is SharedJuxtaposition.Outcome.Refused -> reason = checked.detail
            }
        }
        throw JuxtapositionException(reason.orEmpty())
    }
}
