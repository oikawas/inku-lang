package app.inku.mobile.llm

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class LocalModelFileBoundaryTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun nativeModelLoadingAcceptsOnlyFilesInsideTheOwnedModelsDirectory() {
        val filesDir = temporaryFolder.newFolder("files")
        val modelDir = File(filesDir, "models").apply { mkdirs() }
        val owned = File(modelDir, "owned.litertlm").apply { writeText("model") }
        val outside = temporaryFolder.newFile("outside.litertlm").apply { writeText("model") }

        assertEquals(owned.canonicalFile, ownedLocalModelFileOrNull(filesDir, owned.absolutePath))
        assertNull(ownedLocalModelFileOrNull(filesDir, outside.absolutePath))
        assertNull(ownedLocalModelFileOrNull(filesDir, File(modelDir, "missing.litertlm").absolutePath))
    }
}
