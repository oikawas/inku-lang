package app.inku.mobile.data

import java.io.File
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Test

class StaleThumbnailFilesTest {
    @Test
    fun onlyUnreferencedEarlierFormatFilesThatAreNotFreshAreStale() {
        val dir = Files.createTempDirectory("thumbnails").toFile()
        try {
            val old = System.currentTimeMillis() - 60 * 60_000L
            fun file(name: String, modified: Long = old) = File(dir, name).apply { writeText("x"); setLastModified(modified) }
            val stale = file("aaaa.webp")
            val stillReferenced = file("bbbb.webp")
            val fresh = file("cccc.webp", modified = System.currentTimeMillis())
            val current = file("dddd-rgba2.webp")

            val found = staleThumbnailFiles(
                files = listOf(stale, stillReferenced, fresh, current),
                referenced = setOf(stillReferenced.canonicalPath),
                currentSuffix = "-rgba2.webp",
                cutoffMillis = System.currentTimeMillis() - 10 * 60_000L,
            )

            assertEquals(listOf(stale), found)
        } finally {
            dir.deleteRecursively()
        }
    }
}
