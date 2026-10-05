package app.inku.mobile.pipeline

import org.json.JSONObject

sealed interface PipelineSketchRequest {
    data object Off : PipelineSketchRequest
    data object On : PipelineSketchRequest
    data class Supplied(val text: String) : PipelineSketchRequest

    fun toJson(): JSONObject = when (this) {
        Off -> JSONObject().put("mode", "off")
        On -> JSONObject().put("mode", "on")
        is Supplied -> JSONObject().put("mode", "supplied").put("text", text)
    }

    companion object {
        fun from(input: SketchInput): PipelineSketchRequest =
            input.text?.trim()?.takeIf(String::isNotEmpty)?.let(::Supplied)
                ?: if (input.requested) On else Off
    }
}

/** Sketch state projected from the shared snapshot, including an in-flight request. */
data class PipelineSketchResult(val text: String? = null, val state: String = "off") {
    companion object {
        fun from(record: JSONObject?): PipelineSketchResult {
            if (record == null) return PipelineSketchResult()
            val text = record.optString("text").takeUnless { record.isNull("text") || it.isBlank() }
            return PipelineSketchResult(text, record.requiredString("state"))
        }
    }
}

data class PipelineModelSelection(
    val stage1ModelId: String,
    val stage2ModelId: String,
    // Same bound as the server manifest's `stage1_max_tokens`.
    val stage1MaxTokens: Int = 2048,
    val holeMaxTokens: Int = 2048,
    val chatGptSession: app.inku.mobile.llm.ChatGptSessionRef? = null,
)

sealed interface PipelineAuthoring {
    data class Description(
        val text: String,
        val autoCatalog: Boolean,
        val sketch: PipelineSketchRequest = PipelineSketchRequest.Off,
    ) : PipelineAuthoring
    data class DirectDdl(val source: String) : PipelineAuthoring
}

data class PipelineStartRequest(
    val ownerId: String,
    val configJson: String,
    val authoring: PipelineAuthoring,
    val models: PipelineModelSelection,
    val context: AuthoringContext,
    /** Host-only saved options; Rust never receives or interprets these bytes. */
    val hostContextJson: String = "{}",
)

data class PipelineExecutionContext(
    val snapshotJson: String,
    val configJson: String,
    val models: PipelineModelSelection,
    val authoringContext: AuthoringContext,
    val hostContextJson: String,
    val renderedJson: String?,
    /** Model time per stage in ms, as the server's `metrics` (`sketch`, `catalog`, `stage1`, `composition`, `stage2`). */
    val metrics: Map<String, Long> = emptyMap(),
)

/**
 * The last failed model attempt of a run, as the server's view keeps
 * `provider_failure`; a later success clears it. [detail] is
 * `credentials_unavailable` when the model has no API key.
 */
data class PipelineProviderFailure(
    val failure: String,
    val stage: String,
    val attempt: Int,
    val elapsedMs: Long,
    val detail: String? = null,
)

/**
 * The drawing the server saves before a known-hole completion is asked for
 * (`pipeline_api.py` `_drain`), and again when a run stops with a Score it
 * never drew: the host draws the Score as it stands and saves that work.
 */
interface SafePerformancePort {
    /** The render command for [view]'s delivered Score; null when it cannot be drawn. */
    fun renderCommand(view: PipelineView): PipelineCommand.Render?

    /** Saves the drawn [view]; saving the same drawing again finds the work saved first. */
    suspend fun save(view: PipelineView)
}

sealed interface PipelineCommand {
    data class CommitUserDdl(val expectedRevision: String, val source: String) : PipelineCommand
    data class GenerateFromDescription(
        val expectedRevision: String,
        val description: String,
        val autoCatalog: Boolean,
        val sketch: PipelineSketchRequest = PipelineSketchRequest.Off,
    ) : PipelineCommand
    data class ApprovePatch(val expectedRevision: String, val proposalDigest: String) : PipelineCommand
    data class DeclinePatch(val proposalDigest: String) : PipelineCommand
    data class Render(val optionsJson: String, val clipJson: String) : PipelineCommand
    data object Cancel : PipelineCommand
}

data class PipelinePatchProposal(
    val proposalDigest: String,
    val baseRevision: String,
    val patchJson: String,
    val candidateDdl: String,
)

/** UI projection only. The durable resume token remains the opaque stored state. */
data class PipelineView(
    val executionId: String,
    val variationId: String,
    val sequence: String,
    val revision: String,
    val origin: String,
    val authority: String,
    val phaseTag: String,
    val visibleDdl: String?,
    val scoreJson: String?,
    val deliveryJson: String?,
    val renderedJson: String?,
    val patchProposal: PipelinePatchProposal?,
    val busy: Boolean,
    val terminal: Boolean,
    val eventsJson: String,
    val description: String? = null,
    val hostContextJson: String = "{}",
    val models: PipelineModelSelection? = null,
    val sketch: PipelineSketchResult = PipelineSketchResult(),
    /** Why a stopped run stopped (`needs_user_edit` / `failed` only), as web's `pipelineAttentionReason`. */
    val phaseReason: String? = null,
    val providerFailure: PipelineProviderFailure? = null,
)

class PipelineHostException(
    val code: String,
    cause: Throwable? = null,
) : IllegalStateException(code, cause)

/**
 * The model call a run waits on: this attempt of at most so many.
 *
 * Read from the shared core (`providerAttempt`), which keeps each stage's retry
 * policy, so a first attempt that timed out reads as a retry rather than a slow
 * answer (the Server review's W4, web `providerAttemptText`).
 */
data class ProviderAttempt(
    val executionId: String,
    val action: String,
    val attempt: Int,
    val maxAttempts: Int,
) {
    val isRetry: Boolean get() = attempt > 1

    companion object {
        /** The core's report, or null for none, a broken snapshot, or an answer that cannot be read. */
        fun fromReport(executionId: String, report: ByteArray): ProviderAttempt? = runCatching {
            val value = JSONObject(report.toString(Charsets.UTF_8)).optJSONObject("provider_attempt")
                ?: return null
            val attempt = value.getInt("attempt")
            val maxAttempts = value.getInt("max_attempts")
            if (attempt < 1 || maxAttempts < attempt) return null
            ProviderAttempt(executionId, value.getString("action"), attempt, maxAttempts)
        }.getOrNull()
    }
}
