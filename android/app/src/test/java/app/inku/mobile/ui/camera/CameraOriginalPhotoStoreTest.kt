package app.inku.mobile.ui.camera

import java.io.File
import java.io.RandomAccessFile
import java.nio.file.Files
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class CameraOriginalPhotoStoreTest {
    @get:Rule val temporaryFolder = TemporaryFolder()

    @Test
    fun originalSurvivesStageCleanupAndStoreRecreationUntilPermanentDeletion() {
        val root = temporaryFolder.newFolder("files")
        val source = temporaryFolder.newFile("camera.jpg").apply { writeBytes(byteArrayOf(1, 7, 3, 9)) }
        val store = CameraOriginalPhotoStore(root)
        store.cleanupStagedOnce()
        val stage = store.stage(source)
        val saved = store.persist("../../history/with/slashes", stage)
        assertArrayEquals(source.readBytes(), saved.readBytes())
        assertTrue(stage.exists()) // A failed Room save can retry with the same input.
        store.deleteStaged(stage)
        source.delete()

        val reopened = CameraOriginalPhotoStore(root)
        val abandoned = reopened.stage(saved)
        reopened.cleanupStagedOnce()
        assertTrue(abandoned.exists()) // Another live ViewModel does not erase an active input.
        reopened.cleanupStaged()
        assertFalse(abandoned.exists())
        assertArrayEquals(byteArrayOf(1, 7, 3, 9), reopened.savedPhoto("../../history/with/slashes")!!.readBytes())
        assertTrue(saved.parentFile == File(root, "original-photos").canonicalFile)
        reopened.deleteSaved("../../history/with/slashes")
        assertNull(reopened.savedPhoto("../../history/with/slashes"))
        assertNull(reopened.savedPhoto("legacy-work"))
    }

    @Test
    fun cancellationAndUnsafePathsCannotDeleteOrReplaceOtherFiles() {
        val root = temporaryFolder.newFolder("private")
        val source = temporaryFolder.newFile("keep.jpg").apply { writeBytes(byteArrayOf(6)) }
        val store = CameraOriginalPhotoStore(root)
        val staged = store.stage(source)
        val saved = store.persist("work", staged)
        val second = temporaryFolder.newFile("other.jpg").apply { writeBytes(byteArrayOf(8)) }
        val otherStage = store.stage(second)
        store.persist("work", otherStage)
        assertArrayEquals(byteArrayOf(6), saved.readBytes())
        store.deleteStaged(source)
        store.deleteStaged(saved)
        assertTrue(source.exists())
        assertTrue(saved.exists())
        val link = File(saved.parentFile, "pending-link.image")
        Files.createSymbolicLink(link.toPath(), source.toPath())
        assertFalse(store.isOwnedPhoto(link))
        assertThrows(IllegalArgumentException::class.java) { store.persist("other", link) }
        store.cleanupStaged()
        assertFalse(staged.exists())
        assertFalse(otherStage.exists())
        assertTrue(source.exists())
    }

    @Test
    fun oversizedOriginalIsRejectedBeforeCopying() {
        val root = temporaryFolder.newFolder("bounded")
        val source = temporaryFolder.newFile("large.image")
        RandomAccessFile(source, "rw").use { it.setLength(64L * 1024L * 1024L + 1L) }
        assertThrows(IllegalArgumentException::class.java) { CameraOriginalPhotoStore(root).stage(source) }
        assertTrue(File(root, "original-photos").listFiles().orEmpty().isEmpty())
    }
}
