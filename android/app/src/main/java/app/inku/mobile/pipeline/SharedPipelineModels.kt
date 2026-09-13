package app.inku.mobile.pipeline

data class PipelineModelSelection(
    val stage1ModelId: String,
    val stage2ModelId: String,
    val stage1MaxTokens: Int = 1024,
    val holeMaxTokens: Int = 2048,
)

sealed interface PipelineAuthoring {
    data class Description(val text: String, val autoCatalog: Boolean) : PipelineAuthoring
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
)

sealed interface PipelineCommand {
    data class CommitUserDdl(val expectedRevision: String, val source: String) : PipelineCommand
    data class GenerateFromDescription(
        val expectedRevision: String,
        val description: String,
        val autoCatalog: Boolean,
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
)

class PipelineHostException(
    val code: String,
    cause: Throwable? = null,
) : IllegalStateException(code, cause)
