package app.inku.mobile.ui.camera

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import app.inku.mobile.data.model.CameraInputProvenance
import java.io.File
import java.io.InputStream
import java.io.OutputStream

enum class CameraInputSource {
    Camera,
    PhotoPicker,
}

sealed interface CameraCaptureState {
    data object Idle : CameraCaptureState
    data object ChoosingSource : CameraCaptureState
    data object AwaitingOverwriteConfirmation : CameraCaptureState
    data object Capturing : CameraCaptureState
    data object PickingPhoto : CameraCaptureState
    data object PreparingImage : CameraCaptureState
    data object LoadingLocalModel : CameraCaptureState
    data object AnalyzingLocally : CameraCaptureState
    data object InterpretingWithNim : CameraCaptureState
    data object ComposingWithNim : CameraCaptureState
    data object Rendering : CameraCaptureState
    data object Saving : CameraCaptureState
    data class Completed(val historyId: String) : CameraCaptureState
    data object Cancelling : CameraCaptureState
    data class ReadyToEdit(val inputProvenance: CameraInputProvenance) : CameraCaptureState
    data class Failed(
        val reason: CameraFailure,
        val canRetryNim: Boolean = false,
    ) : CameraCaptureState
    data object Cancelled : CameraCaptureState
}

enum class CameraFailure {
    ModelNotReady,
    CaptureUnavailable,
    PhotoPickerUnavailable,
    EmptyImage,
    DecodeFailed,
    AnalysisFailed,
    EmptyResult,
    InvalidDdl,
    NimNotReady,
    NimFailed,
    NimFailedDirectDdl,
}

internal val CameraCaptureState.locksCameraInteraction: Boolean
    get() = when (this) {
        CameraCaptureState.PreparingImage,
        CameraCaptureState.LoadingLocalModel,
        CameraCaptureState.AnalyzingLocally,
        CameraCaptureState.InterpretingWithNim,
        CameraCaptureState.ComposingWithNim,
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

/** Owns only temporary copies of images explicitly returned by Photo Picker. */
class SelectedImageFileStore(cacheRoot: File) {
    private val imageDir = File(cacheRoot, SELECTED_IMAGE_DIRECTORY)

    fun importImage(input: InputStream, maxBytes: Long = MAX_SELECTED_IMAGE_BYTES): File {
        require(maxBytes > 0L) { "Selected-image byte limit must be positive." }
        cleanupStaleImages()
        check(imageDir.isDirectory || imageDir.mkdirs()) { "Selected-image cache is unavailable." }
        val file = File.createTempFile(FILE_PREFIX, FILE_SUFFIX, imageDir)
        try {
            input.use { source ->
                file.outputStream().buffered().use { output ->
                    copySelectedImageAtMost(source, output, maxBytes)
                }
            }
            require(file.length() > 0L) { "The selected image is empty." }
            return file
        } catch (error: Throwable) {
            file.delete()
            throw error
        }
    }

    fun delete(file: File?): Boolean {
        if (file == null || !isOwnedImage(file)) return false
        return !file.exists() || file.delete()
    }

    fun cleanupStaleImages() {
        imageDir.listFiles()
            ?.filter(::isOwnedImage)
            ?.forEach(File::delete)
    }

    private fun isOwnedImage(file: File): Boolean = runCatching {
        file.isFile &&
            file.name.startsWith(FILE_PREFIX) &&
            file.name.endsWith(FILE_SUFFIX) &&
            file.canonicalFile.parentFile == imageDir.canonicalFile
    }.getOrDefault(false)

    private companion object {
        private const val SELECTED_IMAGE_DIRECTORY = "selected-images"
        private const val FILE_PREFIX = "inku-selected-"
        private const val FILE_SUFFIX = ".image"
    }
}

private const val MAX_SELECTED_IMAGE_BYTES = 64L * 1024L * 1024L

private fun copySelectedImageAtMost(input: InputStream, output: OutputStream, maxBytes: Long) {
    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
    var copied = 0L
    while (true) {
        val read = input.read(buffer)
        if (read < 0) return
        if (copied > maxBytes - read) {
            throw IllegalArgumentException("The selected image is too large.")
        }
        output.write(buffer, 0, read)
        copied += read
    }
}
