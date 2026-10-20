package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import org.json.JSONArray
import org.json.JSONObject

/**
 * Juxtaposition (取り合わせ, SPEC §7.8): a sentence from the author's other
 * works, added after a work's description.
 *
 * The rules are the shared core's (`inku-pipeline/src/juxtaposition.rs`):
 * which sentences are offered, the prompt, how an answer is checked and how the
 * chosen sentence is joined. This object carries the requests to the core; it
 * sends nothing and saves nothing.
 */
internal object SharedJuxtaposition {
    const val SCHEMA = "inku.juxtaposition.v1"

    /** How many sentences the model picks. */
    const val CHOICES = 4

    /** At most this many candidates go out (Server's `candidate_limit` default). */
    const val CANDIDATE_LIMIT = 400

    /** A work that may lend its description's first sentence; labels already removed. */
    data class Source(val id: String, val text: String)

    /** The answer of an `ok` call, or why the core refused the request. */
    sealed interface Outcome {
        data class Ok(val value: JSONObject) : Outcome
        data class Refused(val reason: String, val detail: String) : Outcome
    }

    fun call(action: String, fields: JSONObject, binding: SharedPipelineBinding = NativePipelineBridge): Outcome {
        val request = JSONObject(fields.toString()).put("action", action)
        val answer = JSONObject(binding.juxtaposition(request.toString().encodeToByteArray()).toString(Charsets.UTF_8))
        if (answer.has("error")) throw IllegalArgumentException("juxtaposition request failed: ${answer.getString("error")}")
        require(answer.optString("schema") == SCHEMA) { "juxtaposition schema mismatch" }
        return when (answer.optString("outcome")) {
            "ok" -> Outcome.Ok(answer)
            "refused" -> Outcome.Refused(answer.getString("reason"), answer.getString("detail"))
            else -> throw IllegalArgumentException("juxtaposition outcome missing")
        }
    }

    private fun ok(action: String, fields: JSONObject, binding: SharedPipelineBinding): JSONObject =
        when (val outcome = call(action, fields, binding)) {
            is Outcome.Ok -> outcome.value
            is Outcome.Refused -> throw IllegalArgumentException(outcome.detail)
        }

    /**
     * At most [limit] candidates, in the order the core draws from [seed]. Each
     * is kept as the core wrote it, because `prompt` and `check` read it back.
     */
    fun gather(
        sources: List<Source>,
        description: String,
        lineage: List<String>,
        added: List<String>,
        exclude: List<String>,
        seed: ULong,
        limit: Int = CANDIDATE_LIMIT,
        binding: SharedPipelineBinding = NativePipelineBridge,
    ): JSONArray = ok("gather", JSONObject()
        .put("sources", JSONArray(sources.map { JSONObject().put("id", it.id).put("text", it.text) }))
        .put("description", description)
        .put("lineage", JSONArray(lineage))
        .put("added", JSONArray(added))
        .put("exclude", JSONArray(exclude))
        // A decimal string: a JSON number cannot carry every 64-bit seed through org.json.
        .put("seed", seed.toString())
        .put("limit", limit), binding).getJSONArray("candidates")

    /** The system prompt and the message, with the reason the last answer was refused. */
    fun prompt(
        language: String,
        description: String,
        lineage: List<String>,
        candidates: JSONArray,
        resend: String?,
        binding: SharedPipelineBinding = NativePipelineBridge,
    ): Pair<String, String> {
        val answer = ok("prompt", JSONObject()
            .put("language", language)
            .put("description", description)
            .put("lineage", JSONArray(lineage))
            .put("candidates", candidates)
            .put("resend", resend ?: JSONObject.NULL), binding)
        return answer.getString("system") to answer.getString("text")
    }

    /**
     * The model's four picks, or the core's refusal. [written] is the
     * description as the work keeps it, labels and all: each pick is joined to it.
     */
    fun check(
        language: String,
        answer: String,
        candidates: JSONArray,
        written: String,
        binding: SharedPipelineBinding = NativePipelineBridge,
    ): Outcome = call("check", JSONObject()
        .put("language", language)
        .put("answer", answer)
        .put("candidates", candidates)
        .put("description", written), binding)

    fun choices(value: JSONObject): List<JuxtapositionChoice> {
        val array = value.getJSONArray("choices")
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            val ids = item.getJSONArray("history_ids")
            JuxtapositionChoice(
                sentence = item.getString("sentence"),
                reason = item.getString("reason"),
                historyIds = (0 until ids.length()).map(ids::getString),
                rank = item.getInt("rank"),
                position = item.getDouble("position"),
                joined = item.getString("joined"),
            )
        }
    }
}

data class JuxtapositionChoice(
    val sentence: String,
    val reason: String,
    val historyIds: List<String>,
    val rank: Int,
    /** Where the sentence stood in the shuffled list the model read: 0 the head, 1 the tail. */
    val position: Double,
    /** The work's description with the sentence after it, labels and all. */
    val joined: String,
)

data class JuxtapositionResult(val choices: List<JuxtapositionChoice>, val candidates: Int, val model: String)

/**
 * What the child records, as Web's `juxtapositionMetadata`. The lineage's
 * `sentence` is read back so that the same sentence is not offered again.
 */
fun juxtapositionMetadata(choice: JuxtapositionChoice, result: JuxtapositionResult): Map<String, Any?> = mapOf(
    "juxtaposition" to mapOf(
        "sentence" to choice.sentence,
        "history_ids" to choice.historyIds,
        "rank" to choice.rank,
        "reason" to choice.reason,
        "position" to choice.position,
        "candidates" to result.candidates,
        "model" to result.model,
    ),
)
