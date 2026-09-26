package app.inku.mobile.llm

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

    @Test
    fun aWithdrawnModelTakesItsFilesAndEngineCachesButNoOtherModels() {
        val filesDir = temporaryFolder.newFolder("files")
        val cacheDir = temporaryFolder.newFolder("cache")
        val modelDir = File(filesDir, "models").apply { mkdirs() }
        val engineCache = File(cacheDir, "litert-lm").apply { mkdirs() }
        val withdrawn = listOf(
            File(modelDir, "withdrawn.litertlm"),
            File(modelDir, "withdrawn.litertlm.part"),
            File(engineCache, "withdrawn.litertlm_1_2.bin"),
            File(engineCache, "withdrawn.litertlm.vision_adapter.xnnpack_cache_1"),
        ).onEach { it.writeText("x") }
        val offered = listOf(File(modelDir, "offered.litertlm"), File(engineCache, "offered.litertlm_1_2.bin"))
            .onEach { it.writeText("x") }

        // A row left mid-download points at the `.part`; the finished file goes with it.
        deleteWithdrawnModelFiles(filesDir, cacheDir, File(modelDir, "withdrawn.litertlm.part").path)

        assertFalse(withdrawn.any(File::exists))
        assertTrue(offered.all(File::exists))
    }
}
