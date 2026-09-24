package app.inku.mobile.ui.camera

import app.inku.mobile.llm.MAX_VISION_SOURCE_IMAGE_BYTES
import java.io.File
import java.security.MessageDigest

/** Private, local-only source photos. History IDs never become filesystem paths. */
class CameraOriginalPhotoStore(filesRoot: File) {
    private val directory = File(filesRoot.canonicalFile, "original-photos")

    fun stage(source: File): File {
        check(directory.canonicalFile == directory) { "Photo storage is invalid." }
        require(source.isFile && source.length() in 1..MAX_VISION_SOURCE_IMAGE_BYTES)
        check(directory.isDirectory || directory.mkdirs()) { "Photo storage is unavailable." }
        val staged = File.createTempFile("pending-", ".image", directory)
        try {
            source.inputStream().use { input ->
                staged.outputStream().use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    var copied = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        require(copied <= MAX_VISION_SOURCE_IMAGE_BYTES - count) { "The original photo is too large." }
                        output.write(buffer, 0, count)
                        copied += count
                    }
                }
            }
            check(staged.length() > 0L) { "The original photo is empty." }
            return staged
        } catch (error: Throwable) {
            staged.delete()
            throw error
        }
    }

    /** Keeps the staged source available if the associated history save must be retried. */
    fun persist(historyId: String, staged: File): File {
        require(isOwnedPhoto(staged) && staged.name.startsWith("pending-"))
        val target = fileFor(historyId)
        require(target.canonicalFile == target) { "Photo target is invalid." }
        if (target.exists()) {
            require(isOwnedPhoto(target) && target.length() > 0L)
            return target
        }
        val copy = stage(staged)
        try {
            check(copy.renameTo(target)) { "The original photo could not be saved." }
            return target
        } finally {
            copy.delete()
        }
    }

    fun savedPhoto(historyId: String): File? = fileFor(historyId).takeIf { isOwnedPhoto(it) && it.length() > 0L }

    fun deleteSaved(historyId: String) {
        savedPhoto(historyId)?.delete()
    }

    fun deleteStaged(file: File?) {
        file?.takeIf { isOwnedPhoto(it) && it.name.startsWith("pending-") }?.delete()
    }

    fun cleanupStaged() {
        directory.listFiles()?.forEach(::deleteStaged)
    }

    /** Clear process-death leftovers only once, without disturbing another live ViewModel. */
    fun cleanupStagedOnce() {
        synchronized(cleanedDirectories) {
            if (cleanedDirectories.add(directory.path)) cleanupStaged()
        }
    }

    private fun fileFor(historyId: String): File {
        require(historyId.isNotBlank())
        val digest = MessageDigest.getInstance("SHA-256").digest(historyId.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return File(directory, "$digest.image")
    }

    fun isOwnedPhoto(file: File): Boolean = runCatching {
        directory.canonicalFile == directory && file.isFile && file.canonicalFile == file.absoluteFile &&
            file.canonicalFile.parentFile == directory &&
            file.name.endsWith(".image")
    }.getOrDefault(false)

    private companion object {
        val cleanedDirectories = mutableSetOf<String>()
    }
}
