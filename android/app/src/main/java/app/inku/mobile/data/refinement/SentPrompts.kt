package app.inku.mobile.data.refinement

import org.json.JSONObject

enum class PromptStage { Sketch, Stage1, Composition, Laws, Colors, Stage2 }

data class SentPrompt(
    val system: String,
    val message: String?,
    val promptId: String,
    val promptDigest: String,
    val instructionLanguage: String,
    val attempt: Int,
)

sealed interface SentPrompts {
    data object NotRecorded : SentPrompts
    data object Unavailable : SentPrompts
    data class Recorded(
        val stages: Set<PromptStage>,
        val prompts: Map<PromptStage, SentPrompt?>,
    ) : SentPrompts
}

/** The immutable record copied from the execution sidecar when this work was saved. */
fun sentPromptsFromHistoryRecord(
    metadataJson: String,
    executionId: String,
    variationId: String,
    revision: String,
): SentPrompts = runCatching {
    val metadata = JSONObject(metadataJson)
    if (!metadata.has("sent_system_prompts")) return SentPrompts.NotRecorded
    if (metadata.optString("sent_prompt_execution_id") != executionId ||
        metadata.optString("sent_prompt_variation_id") != variationId ||
        metadata.optString("sent_prompt_revision") != revision
    ) return SentPrompts.Unavailable
    val prompts = metadata.optJSONObject("sent_system_prompts") ?: return SentPrompts.NotRecorded
    val stages = metadata.optJSONArray("sent_system_prompt_stages")
        ?.let { array -> (0 until array.length()).map { array.optString(it) }.toSet() }
        ?: setOf("stage1", "stage2")
    val names = linkedMapOf(
        PromptStage.Sketch to "sketch",
        PromptStage.Stage1 to "stage1",
        PromptStage.Composition to "composition",
        PromptStage.Laws to "laws",
        PromptStage.Colors to "colors",
        PromptStage.Stage2 to "stage2",
    )
    val records = names.mapValues { (_, name) ->
        prompts.optJSONObject(name)?.let { prompt ->
            SentPrompt(
                system = prompt.getString("system"),
                message = prompt.optString("message").takeIf(String::isNotBlank),
                promptId = prompt.getString("prompt_id"),
                promptDigest = prompt.getString("prompt_digest"),
                instructionLanguage = prompt.getString("instruction_language"),
                attempt = prompt.getInt("attempt"),
            )
        }
    }
    SentPrompts.Recorded(names.filterValues { it in stages }.keys, records)
}.getOrElse { SentPrompts.Unavailable }
