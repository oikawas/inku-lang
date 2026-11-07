package app.inku.mobile.data.db

import app.inku.mobile.pipeline.SharedPipelineHost
import java.util.Base64
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Schema 15 keeps a work in two tables; nothing is lost or swapped on the way. */
class HistoryPayloadSplitTest {
    @Test
    fun everyFieldOfAWorkReachesTheRowOrThePayloadUnderItsOwnName() {
        val work = HistoryItemEntity(
            id = "id", createdAt = 1, updatedAt = 2, originalInput = "input", normalizedDdl = "ddl",
            scoreJson = "{\"score\":1}", displaySvg = "<svg/>", stage1Model = "m1", stage2Model = "m2",
            renderMetadataJson = "{\"meta\":1}", renderHash = "hash", renderHashShort = "short",
            colorCatalogId = "catalog", catalogMode = "mode", canvasAspect = "square", starred = true,
            trashed = false, elapsedMs = 3, tokenMetadataJson = "{\"tokens\":1}", thumbnailPath = "thumb",
            thumbnailWidth = 4, thumbnailHeight = 5, renderWild = true, lineageNodeId = "node",
            renderSeed = "rs", compositionSeed = "cs", interpretationSeed = "is", variationAmplitude = "va",
            variationSeed = "vs", seedText = "st", instructionLangRequested = "auto",
            instructionLangResolved = "ja", sourceText = "source", sketchText = "sketch", sketchGrain = "grain",
            sketchState = "on", ddlSourceOrigin = "origin",
        )
        val halves = listOf(work.row(), work.payload())
        val names = mutableSetOf<String>()
        for (half in halves) {
            for (field in half.javaClass.declaredFields.filterNot { java.lang.reflect.Modifier.isStatic(it.modifiers) }) {
                field.isAccessible = true
                val source = HistoryItemEntity::class.java.getDeclaredField(field.name).also { it.isAccessible = true }
                assertEquals(field.name, source.get(work), field.get(half))
                names += field.name
            }
        }
        val all = HistoryItemEntity::class.java.declaredFields
            .filterNot { java.lang.reflect.Modifier.isStatic(it.modifiers) }.map { it.name }.toSet()
        assertEquals("every field is kept, the id in both", all, names)
    }

    @Test
    fun theStoredPhaseIsReadWithoutLoadingTheRun() {
        fun state(tag: String, schema: String = "inku.android-pipeline-execution.v1") = JSONObject()
            .put("schema", schema)
            .put("snapshot_base64", Base64.getEncoder().encodeToString(
                JSONObject().put("phase", JSONObject().put("tag", tag)).toString().toByteArray()))
            .toString().toByteArray()
        assertEquals("completed", SharedPipelineHost.storedPhaseTag(state("completed")))
        assertEquals("needs_user_edit", SharedPipelineHost.storedPhaseTag(state("needs_user_edit")))
        assertNull(SharedPipelineHost.storedPhaseTag(state("completed", schema = "other")))
        assertNull(SharedPipelineHost.storedPhaseTag("not json".toByteArray()))
    }
}
