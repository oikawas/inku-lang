package app.inku.mobile.ui.camera

internal enum class CameraDevelopmentEffect {
    PhotoPreparing,
    PhotoReading,
    GrainAndForms,
    VividColorFields,
    OutlineSettling,
    Saving,
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
        CameraCaptureState.PreparingImage -> Triple(
            "写真を準備しています", "Preparing your photo", CameraDevelopmentEffect.PhotoPreparing,
        )
        CameraCaptureState.LoadingLocalModel -> Triple(
            "写真を見る準備をしています", "Getting ready to examine your photo", CameraDevelopmentEffect.PhotoPreparing,
        )
        CameraCaptureState.AnalyzingLocally -> Triple(
            "写真の内容を調べています", "Examining your photo", CameraDevelopmentEffect.PhotoReading,
        )
        CameraCaptureState.InterpretingStage1 -> Triple(
            "絵の構図を考えています",
            "Planning the composition",
            CameraDevelopmentEffect.GrainAndForms,
        )
        CameraCaptureState.Composing -> Triple(
            "色と形を組み立てています",
            "Building the colors and forms",
            CameraDevelopmentEffect.VividColorFields,
        )
        CameraCaptureState.Rendering -> Triple(
            "絵を仕上げています", "Finishing the work", CameraDevelopmentEffect.OutlineSettling,
        )
        CameraCaptureState.Saving -> Triple(
            "作品を保存しています", "Saving your work", CameraDevelopmentEffect.Saving,
        )
        is CameraCaptureState.Completed -> Triple(
            "現像できました",
            "Developed",
            CameraDevelopmentEffect.FinalArtwork,
        )
        CameraCaptureState.Cancelling -> Triple(
            "取り消しています",
            "Cancelling",
            CameraDevelopmentEffect.PhotoPreparing,
        )
        is CameraCaptureState.Failed -> Triple(
            if (state.reason.isDrawFailure) "現像に失敗しました" else "画像処理に失敗しました",
            if (state.reason.isDrawFailure) "Development failed" else "Image processing failed",
            if (state.reason.isDrawFailure) CameraDevelopmentEffect.OutlineSettling else CameraDevelopmentEffect.PhotoPreparing,
        )
        else -> return null
    }
    return CameraDevelopmentPresentation(
        message = if (isJapanese) words.first else words.second,
        effect = words.third,
        animationsEnabled = animationsEnabled,
        showCancel = state !is CameraCaptureState.Completed,
        showRetry = state is CameraCaptureState.Failed && state.canRetryDraw,
    )
}

private val CameraFailure.isDrawFailure: Boolean
    get() = this == CameraFailure.DrawFailed

internal data class CameraOriginalPhotoWords(
    val label: String,
    val enlarge: String,
    val close: String,
)

internal fun cameraOriginalPhotoWords(isJapanese: Boolean): CameraOriginalPhotoWords =
    if (isJapanese) {
        CameraOriginalPhotoWords("元の写真", "元の写真を拡大", "閉じる")
    } else {
        CameraOriginalPhotoWords("Original photo", "Enlarge original photo", "Close")
    }
