package app.inku.mobile.ui.camera

internal enum class CameraDevelopmentEffect {
    PaperExposure,
    GrainAndForms,
    VividColorFields,
    OutlineSettling,
    FinalArtwork,
}

internal data class CameraDevelopmentPresentation(
    val message: String,
    val effect: CameraDevelopmentEffect,
    val animationsEnabled: Boolean,
    val politeLiveRegion: Boolean = true,
    val showCancel: Boolean = true,
    val showRetry: Boolean = false,
)

internal fun cameraDevelopmentPresentation(
    state: CameraCaptureState,
    isJapanese: Boolean,
    animationsEnabled: Boolean,
): CameraDevelopmentPresentation? {
    val words = when (state) {
        CameraCaptureState.PreparingImage,
        CameraCaptureState.LoadingLocalModel,
        CameraCaptureState.AnalyzingLocally,
        -> Triple("光を読み取っています", "Reading the light", CameraDevelopmentEffect.PaperExposure)
        CameraCaptureState.InterpretingWithNim -> Triple(
            "かたちを起こしています",
            "Bringing out the forms",
            CameraDevelopmentEffect.GrainAndForms,
        )
        CameraCaptureState.ComposingWithNim -> Triple(
            "色と配置を定着させています",
            "Fixing color and placement",
            CameraDevelopmentEffect.VividColorFields,
        )
        CameraCaptureState.Rendering,
        CameraCaptureState.Saving,
        -> Triple("現像しています", "Developing", CameraDevelopmentEffect.OutlineSettling)
        is CameraCaptureState.Completed -> Triple(
            "現像できました",
            "Developed",
            CameraDevelopmentEffect.FinalArtwork,
        )
        CameraCaptureState.Cancelling -> Triple(
            "取り消しています",
            "Cancelling",
            CameraDevelopmentEffect.PaperExposure,
        )
        is CameraCaptureState.Failed -> Triple(
            if (state.reason.isNimFailure) "現像に失敗しました" else "撮影処理に失敗しました",
            if (state.reason.isNimFailure) "Development failed" else "Camera processing failed",
            if (state.reason.isNimFailure) CameraDevelopmentEffect.OutlineSettling else CameraDevelopmentEffect.PaperExposure,
        )
        else -> return null
    }
    return CameraDevelopmentPresentation(
        message = if (isJapanese) words.first else words.second,
        effect = words.third,
        animationsEnabled = animationsEnabled,
        showCancel = state !is CameraCaptureState.Completed,
        showRetry = state is CameraCaptureState.Failed && state.canRetryNim,
    )
}

private val CameraFailure.isNimFailure: Boolean
    get() = this == CameraFailure.NimFailed || this == CameraFailure.NimFailedDirectDdl
