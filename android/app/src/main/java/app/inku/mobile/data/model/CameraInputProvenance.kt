package app.inku.mobile.data.model

import app.inku.mobile.llm.VisionAnalysisRequest
import app.inku.mobile.llm.VisionAnalysisResult
import app.inku.mobile.llm.VisionOutputMode
import app.inku.mobile.llm.VisionPrompts
import org.json.JSONObject

internal const val INPUT_PROVENANCE_KEY = "input_provenance"
private const val LOCAL_VISION_PROVIDER_ID = "local-litert-lm"

enum class CameraInputOrigin(val wireValue: String) {
    Camera("camera"),
}

enum class CameraInputRoute(val wireValue: String) {
    LocalDescriptionToNim("local_description_to_nim"),
    LocalDdlToNimStage2("local_ddl_to_nim_stage2"),
}

enum class CameraVisionOutputMode(val wireValue: String) {
    Description("description"),
    Ddl("ddl"),
}

/** Immutable, non-image audit data captured at the local Vision boundary. */
data class CameraInputProvenance(
    val origin: CameraInputOrigin,
    val route: CameraInputRoute,
    val visionProviderId: String,
    val visionModelId: String,
    val visionPromptVersion: String,
    val visionOutputMode: CameraVisionOutputMode,
    val normalizedImageWidth: Int,
    val normalizedImageHeight: Int,
) {
    init {
        require(visionProviderId.isNotBlank())
        require(visionModelId.isNotBlank())
        require(visionPromptVersion.isNotBlank())
        require(normalizedImageWidth > 0)
        require(normalizedImageHeight > 0)
    }

    internal fun toJson(): JSONObject = JSONObject()
        .put("origin", origin.wireValue)
        .put("route", route.wireValue)
        .put("vision_provider_id", visionProviderId)
        .put("vision_model_id", visionModelId)
        .put("vision_prompt_version", visionPromptVersion)
        .put("vision_output_mode", visionOutputMode.wireValue)
        .put("normalized_image_width", normalizedImageWidth)
        .put("normalized_image_height", normalizedImageHeight)

    companion object {
        fun fromAnalysis(
            request: VisionAnalysisRequest,
            result: VisionAnalysisResult,
        ): CameraInputProvenance = CameraInputProvenance(
            origin = CameraInputOrigin.Camera,
            route = when (request.outputMode) {
                VisionOutputMode.DESCRIPTION -> CameraInputRoute.LocalDescriptionToNim
                VisionOutputMode.DDL -> CameraInputRoute.LocalDdlToNimStage2
            },
            visionProviderId = LOCAL_VISION_PROVIDER_ID,
            visionModelId = result.modelId,
            visionPromptVersion = VisionPrompts.versionFor(request.outputMode),
            visionOutputMode = when (request.outputMode) {
                VisionOutputMode.DESCRIPTION -> CameraVisionOutputMode.Description
                VisionOutputMode.DDL -> CameraVisionOutputMode.Ddl
            },
            normalizedImageWidth = request.width,
            normalizedImageHeight = request.height,
        )
    }
}

/** Owns the reserved key for every save, including saves without provenance. */
internal fun mergeInputProvenance(
    renderMetadata: JSONObject,
    provenance: CameraInputProvenance?,
): JSONObject {
    check(!renderMetadata.has(INPUT_PROVENANCE_KEY)) { "$INPUT_PROVENANCE_KEY already exists" }
    provenance?.let { renderMetadata.put(INPUT_PROVENANCE_KEY, it.toJson()) }
    return renderMetadata
}

internal fun mergeInputProvenance(
    renderMetadataJson: String,
    provenance: CameraInputProvenance,
): String = JSONObject(renderMetadataJson)
    .let { mergeInputProvenance(it, provenance) }
    .toString()

/** Strict reader: malformed or non-camera audit data is invisible to the UI. */
internal fun cameraInputProvenance(renderMetadataJson: String): CameraInputProvenance? = runCatching {
    val metadata = JSONObject(renderMetadataJson)
    val value = metadata.opt(INPUT_PROVENANCE_KEY) as? JSONObject ?: return null

    fun requiredString(key: String): String = (value.opt(key) as? String)
        ?.trim()
        ?.takeIf { it.isNotEmpty() }
        ?: error("missing or invalid $key")
    fun requiredPositiveInt(key: String): Int = (value.opt(key) as? Int)
        ?.takeIf { it > 0 }
        ?: error("missing or invalid $key")

    val origin = CameraInputOrigin.entries.singleOrNull {
        it.wireValue == requiredString("origin")
    } ?: error("unsupported origin")
    val route = CameraInputRoute.entries.singleOrNull {
        it.wireValue == requiredString("route")
    } ?: error("unsupported route")
    val outputMode = CameraVisionOutputMode.entries.singleOrNull {
        it.wireValue == requiredString("vision_output_mode")
    } ?: error("unsupported output mode")

    CameraInputProvenance(
        origin = origin,
        route = route,
        visionProviderId = requiredString("vision_provider_id"),
        visionModelId = requiredString("vision_model_id"),
        visionPromptVersion = requiredString("vision_prompt_version"),
        visionOutputMode = outputMode,
        normalizedImageWidth = requiredPositiveInt("normalized_image_width"),
        normalizedImageHeight = requiredPositiveInt("normalized_image_height"),
    )
}.getOrNull()
