package app.inku.mobile.ui.camera

import app.inku.mobile.data.db.ModelAssetEntity
import app.inku.mobile.data.db.ProviderSettingEntity
import app.inku.mobile.data.model.CameraInputProvenance
import app.inku.mobile.llm.RoutingModelProvider
import app.inku.mobile.pipeline.SketchInput

/**
 * The drawing settings a camera run was started with. They are read once when
 * the capture begins, so a later settings change does not alter a run or its
 * retry.
 */
internal data class CameraDrawSettings(
    val stage1ModelId: String,
    val stage2ModelId: String,
    val catalogId: String,
    val sketchRequested: Boolean,
)

/** Immutable run values used while drawing one camera result. */
internal data class CameraDrawRoute(
    val inputProvenance: CameraInputProvenance,
    val settings: CameraDrawSettings,
) {
    val stage1ModelId: String get() = settings.stage1ModelId
    val stage2ModelId: String get() = settings.stage2ModelId
    val catalogId: String get() = settings.catalogId
    val sketch: SketchInput get() = SketchInput(requested = settings.sketchRequested)
    val autoRepair: Boolean get() = true
}

internal object CameraDrawRouting {
    fun provenanceFor(state: CameraCaptureState): CameraInputProvenance? =
        (state as? CameraCaptureState.ReadyToEdit)?.inputProvenance
}

internal enum class ModelReadinessIssue {
    LocalModelNotReady,
    ProviderMissingOrDisabled,
    BaseUrlMissing,
    ApiKeyMissing,
}

/**
 * Checks, before a capture, that [modelId] can run: a local model must be
 * downloaded, and a remote model's provider must be enabled with a Base URL and,
 * where the service requires one, an API key.
 */
internal fun modelReadinessIssue(
    modelId: String,
    providers: List<ProviderSettingEntity>,
    assets: List<ModelAssetEntity>,
): ModelReadinessIssue? {
    if (modelId.startsWith("local-litert-lm:")) {
        return if (assets.any { it.modelId == modelId && it.downloadState == "ready" }) {
            null
        } else {
            ModelReadinessIssue.LocalModelNotReady
        }
    }
    val provider = RoutingModelProvider.resolveProviderForRouting(providers, modelId)
        ?.takeIf { it.isEnabled && !it.isDefaultLocal }
        ?: return ModelReadinessIssue.ProviderMissingOrDisabled
    if (provider.baseUrl.isNullOrBlank()) return ModelReadinessIssue.BaseUrlMissing
    if (provider.requiresApiKey() && provider.encryptedApiKey.isNullOrBlank()) {
        return ModelReadinessIssue.ApiKeyMissing
    }
    return null
}

private fun ProviderSettingEntity.requiresApiKey(): Boolean =
    kind == "gemini" || kind == "anthropic" || providerId in setOf("openai", "nvidia")

/** Clear only a camera description that is still eligible for the camera draw route. */
internal fun CameraCaptureState.clearCameraOrigin(): CameraCaptureState =
    when (this) {
        is CameraCaptureState.ReadyToEdit,
        is CameraCaptureState.Completed,
        is CameraCaptureState.Failed,
        CameraCaptureState.Cancelled,
        -> CameraCaptureState.Idle
        else -> this
    }
