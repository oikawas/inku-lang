package app.inku.mobile.pipeline

import org.json.JSONObject

/** Positions and states projected from the core, never matched or classified by Kotlin. */
data class CompletionRangeState(val start: Int, val end: Int, val state: String)

internal fun completionRangeStates(
    binding: SharedPipelineBinding,
    configJson: String,
    source: String,
    completionRangesJson: String?,
): List<CompletionRangeState> {
    if (completionRangesJson == null) return emptyList()
    return try {
        val input = JSONObject().put("config", JSONObject(configJson)).put("source", source)
            .put("completion_ranges", JSONObject(completionRangesJson))
        val output = JSONObject(binding.completionRangeStates(input.toString().encodeToByteArray()).toString(Charsets.UTF_8))
        if (output.optString("schema") != "inku.completion-range-states.v1") return emptyList()
        val ranges = output.optJSONArray("ranges") ?: return emptyList()
        (0 until ranges.length()).mapNotNull { index ->
            val range = ranges.optJSONObject(index) ?: return@mapNotNull null
            val start = range.optInt("utf16_start", -1)
            val end = range.optInt("utf16_end", -1)
            val state = range.optString("state")
            if (start < 0 || end <= start || end > source.length ||
                state !in setOf("completed", "numbers_changed", "words_changed")) null
            else CompletionRangeState(start, end, state)
        }
    } catch (_: org.json.JSONException) {
        emptyList()
    } catch (_: UnsatisfiedLinkError) {
        // A saved work can be opened with an older native binary.
        emptyList()
    }
}
