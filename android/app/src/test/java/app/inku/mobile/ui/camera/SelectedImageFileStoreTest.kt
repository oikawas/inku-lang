package app.inku.mobile.ui.camera

import java.io.ByteArrayInputStream
import java.io.File
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SelectedImageFileStoreTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun importsAndDeletesOnlyItsOwnedTemporaryImage() {
        val cache = temporaryFolder.newFolder("cache")
        val store = SelectedImageFileStore(cache)
        val bytes = byteArrayOf(1, 2, 3, 4)

        val selected = store.importImage(ByteArrayInputStream(bytes))
        val outside = File(cache, "outside.jpg").apply { writeBytes(byteArrayOf(9)) }

        assertArrayEquals(bytes, selected.readBytes())
        assertTrue(store.delete(selected))
        assertFalse(selected.exists())
        assertFalse(store.delete(outside))
        assertTrue(outside.exists())
    }

    @Test
    fun emptySelectionFailsWithoutLeavingAnOwnedFile() {
        val cache = temporaryFolder.newFolder("cache")
        val store = SelectedImageFileStore(cache)

        val failure = runCatching { store.importImage(ByteArrayInputStream(byteArrayOf())) }.exceptionOrNull()

        assertTrue(failure is IllegalArgumentException)
        assertTrue(File(cache, "selected-images").listFiles().orEmpty().isEmpty())
    }

    @Test
    fun staleCleanupDoesNotTouchFilesOutsideTheOwnedDirectory() {
        val cache = temporaryFolder.newFolder("cache")
        val store = SelectedImageFileStore(cache)
        val selected = store.importImage(ByteArrayInputStream(byteArrayOf(1)))
        val outside = File(cache, "keep.jpg").apply { writeBytes(byteArrayOf(2)) }

        store.cleanupStaleImages()

        assertFalse(selected.exists())
        assertTrue(outside.exists())
    }

    @Test
    fun importRejectsOversizedPickerInputAndRemovesThePartialCopy() {
        val cache = temporaryFolder.newFolder("oversized-cache")
        val store = SelectedImageFileStore(cache)

        assertThrows(IllegalArgumentException::class.java) {
            store.importImage(ByteArrayInputStream(ByteArray(9)), maxBytes = 8L)
        }
        assertTrue(File(cache, "selected-images").listFiles().orEmpty().isEmpty())
    }

    @Test
    fun importAcceptsInputAtTheExactLimit() {
        val cache = temporaryFolder.newFolder("exact-limit-cache")
        val expected = byteArrayOf(1, 2, 3, 4)
        val store = SelectedImageFileStore(cache)

        val file = store.importImage(ByteArrayInputStream(expected), maxBytes = expected.size.toLong())

        assertArrayEquals(expected, file.readBytes())
    }
}
