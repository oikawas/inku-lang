package app.inku.mobile.data.model

import app.inku.mobile.llm.VisionAnalysisRequest
import app.inku.mobile.llm.VisionAnalysisResult
import app.inku.mobile.llm.VisionOutputMode
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraInputProvenanceTest {
    @Test
    fun analysisSnapshotSerializesOnlyTheApprovedAuditFields() {
        val snapshot = CameraInputProvenance.fromAnalysis(
            request = request(),
            result = VisionAnalysisResult(
                text = "赤い円が見える。",
                modelId = "local-litert-lm:gemma-4-e2b",
                elapsedMs = 321L,
            ),
        )

        val stored = JSONObject(mergeInputProvenance("""{"render_engine_id":"inku-svg"}""", snapshot))
        val provenance = stored.getJSONObject("input_provenance")

        assertEquals("inku-svg", stored.getString("render_engine_id"))
        assertEquals("camera", provenance.getString("origin"))
        assertEquals("local_description_to_nim", provenance.getString("route"))
        assertEquals("local-litert-lm", provenance.getString("vision_provider_id"))
        assertEquals("local-litert-lm:gemma-4-e2b", provenance.getString("vision_model_id"))
        assertEquals("camera-description-v1", provenance.getString("vision_prompt_version"))
        assertEquals("description", provenance.getString("vision_output_mode"))
        assertEquals(720, provenance.getInt("normalized_image_width"))
        assertEquals(1280, provenance.getInt("normalized_image_height"))
        assertEquals(8, provenance.length())
        listOf("text", "image", "uri", "path", "filename", "exif", "location", "digest", "captured_at").forEach {
            assertFalse("must not persist $it", provenance.has(it))
        }
    }

    @Test
    fun directDdlSnapshotUsesItsOwnBackwardCompatibleRouteAndPromptVersion() {
        val snapshot = CameraInputProvenance.fromAnalysis(
            request = request().copy(outputMode = VisionOutputMode.DDL),
            result = result().copy(text = "青い円を右上に置く。"),
        )
        val parsed = cameraInputProvenance(mergeInputProvenance("{}", snapshot))
            ?: error("direct DDL provenance missing")

        assertEquals(CameraInputRoute.LocalDdlToNimStage2, parsed.route)
        assertEquals(CameraVisionOutputMode.Ddl, parsed.visionOutputMode)
        assertEquals("camera-ddl-v1", parsed.visionPromptVersion)
    }

    @Test
    fun existingInputProvenanceFailsClosedWithoutOverwritingRendererMetadata() {
        val failure = runCatching {
            mergeInputProvenance(
                """{"input_provenance":{"origin":"other"}}""",
                CameraInputProvenance.fromAnalysis(request(), result()),
            )
        }.exceptionOrNull()

        assertTrue(failure is IllegalStateException)

        val ordinarySaveFailure = runCatching {
            mergeInputProvenance(
                JSONObject("""{"input_provenance":{"origin":"spoofed"}}"""),
                provenance = null,
            )
        }.exceptionOrNull()
        assertTrue(ordinarySaveFailure is IllegalStateException)
    }

    @Test
    fun parserAcceptsOnlyCompleteCameraObjectsWithPositiveIntegerDimensions() {
        val valid = mergeInputProvenance("{}", CameraInputProvenance.fromAnalysis(request(), result()))
        assertEquals(CameraInputOrigin.Camera, cameraInputProvenance(valid)?.origin)

        assertNull(cameraInputProvenance("{}"))
        assertNull(cameraInputProvenance("""{"input_provenance":"camera"}"""))
        assertNull(cameraInputProvenance(valid.replace("1280", "0")))
        assertNull(cameraInputProvenance(valid.replace("720", "\"720\"")))
        assertNull(cameraInputProvenance(valid.replace("local_description_to_nim", "unsupported")))
    }

    private fun request() = VisionAnalysisRequest(
        normalizedJpeg = byteArrayOf(1, 2, 3),
        width = 720,
        height = 1280,
        languageCode = "ja",
    )

    private fun result() = VisionAnalysisResult(
        text = "赤い円が見える。",
        modelId = "local-litert-lm:gemma-4-e2b",
        elapsedMs = 321L,
    )
}
