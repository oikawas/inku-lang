package app.inku.mobile.ui.camera

import app.inku.mobile.data.db.ProviderSettingEntity

internal const val CAMERA_NIM_PROVIDER_ID = "nvidia"
internal const val CAMERA_NIM_MODEL_ID = "nvidia:google/gemma-4-31b-it"
internal const val CAMERA_NIM_CATALOG_ID = "vivid_material"

/** Immutable run values used only while drawing an editable camera description. */
internal data class CameraNimDrawRoute(
    val stage1ModelId: String = CAMERA_NIM_MODEL_ID,
    val stage2ModelId: String = CAMERA_NIM_MODEL_ID,
    val catalogId: String = CAMERA_NIM_CATALOG_ID,
    val sketchRequested: Boolean = false,
    val autoSelectCatalog: Boolean = false,
    val autoRepair: Boolean = false,
)

internal object CameraNimDrawRouting {
    fun forState(state: CameraCaptureState): CameraNimDrawRoute? =
        if (state == CameraCaptureState.ReadyToEdit) CameraNimDrawRoute() else null
}

internal enum class CameraNimProviderIssue {
    MissingOrDisabled,
    BaseUrlMissing,
    ApiKeyMissing,
}

internal fun CameraNimDrawRoute.providerIssue(
    providers: List<ProviderSettingEntity>,
): CameraNimProviderIssue? {
    val provider = providers.firstOrNull { it.providerId == CAMERA_NIM_PROVIDER_ID }
        ?.takeIf { it.isEnabled }
        ?: return CameraNimProviderIssue.MissingOrDisabled
    if (provider.baseUrl.isNullOrBlank()) return CameraNimProviderIssue.BaseUrlMissing
    if (provider.encryptedApiKey.isNullOrBlank()) return CameraNimProviderIssue.ApiKeyMissing
    return null
}

/** Clear only a camera description that is still eligible for the fixed draw route. */
internal fun CameraCaptureState.clearCameraOrigin(): CameraCaptureState =
    if (this == CameraCaptureState.ReadyToEdit) CameraCaptureState.Idle else this
