package app.inku.mobile.ui.camera

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import app.inku.mobile.data.model.CameraInputProvenance
import java.io.File

/**
 * One pending capture: the app-owned [file] the in-app camera writes, and its
 * FileProvider [uri] for the system camera fallback.
 */
data class CameraCaptureRequest(val file: File, val uri: Uri)

sealed interface CameraCaptureState {
    data object Idle : CameraCaptureState
    data object Capturing : CameraCaptureState
    data object PreparingImage : CameraCaptureState
    data object LoadingLocalModel : CameraCaptureState
    data object AnalyzingLocally : CameraCaptureState
    data object WritingDescription : CameraCaptureState
    data object InterpretingStage1 : CameraCaptureState
    data object Composing : CameraCaptureState
    data object Rendering : CameraCaptureState
    data object Saving : CameraCaptureState
    data class Completed(val historyId: String) : CameraCaptureState
    data object Cancelling : CameraCaptureState
    data class ReadyToEdit(val inputProvenance: CameraInputProvenance) : CameraCaptureState
    data class Failed(
        val reason: CameraFailure,
        val canRetryDraw: Boolean = false,
    ) : CameraCaptureState
    data object Cancelled : CameraCaptureState
}

enum class CameraFailure {
    ModelNotReady,
    CaptureUnavailable,
    EmptyImage,
    DecodeFailed,
    AnalysisFailed,
    EmptyResult,
    DescriptionFailed,
    DrawModelNotReady,
    DrawFailed,
}

internal val CameraCaptureState.locksCameraInteraction: Boolean
    get() = when (this) {
        CameraCaptureState.PreparingImage,
        CameraCaptureState.LoadingLocalModel,
        CameraCaptureState.AnalyzingLocally,
        CameraCaptureState.WritingDescription,
        CameraCaptureState.InterpretingStage1,
        CameraCaptureState.Composing,
        CameraCaptureState.Rendering,
        CameraCaptureState.Saving,
        CameraCaptureState.Cancelling,
        -> true
        else -> false
    }

/** Owns only ephemeral camera files under cacheDir/camera. */
class CameraCaptureFileStore(private val context: Context) {
    private val cameraDir: File
        get() = File(context.cacheDir, CAMERA_DIRECTORY)

    fun createPendingCapture(): File {
        cleanupStaleCaptures()
        check(cameraDir.isDirectory || cameraDir.mkdirs()) { "Camera cache is unavailable." }
        return File.createTempFile(FILE_PREFIX, FILE_SUFFIX, cameraDir)
    }

    fun contentUri(file: File): Uri = FileProvider.getUriForFile(
        context,
        "${context.packageName}.fileprovider",
        file,
    )

    fun delete(file: File?) {
        file?.takeIf(::isOwnedCapture)?.delete()
    }

    fun cleanupStaleCaptures() {
        cameraDir.listFiles()
            ?.filter(::isOwnedCapture)
            ?.forEach(File::delete)
    }

    private fun isOwnedCapture(file: File): Boolean = runCatching {
        file.isFile &&
            file.name.startsWith(FILE_PREFIX) &&
            file.name.endsWith(FILE_SUFFIX) &&
            file.canonicalFile.parentFile == cameraDir.canonicalFile
    }.getOrDefault(false)

    private companion object {
        private const val CAMERA_DIRECTORY = "camera"
        private const val FILE_PREFIX = "inku-camera-"
        private const val FILE_SUFFIX = ".jpg"
    }
}
