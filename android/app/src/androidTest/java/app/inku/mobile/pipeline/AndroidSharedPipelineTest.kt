package app.inku.mobile.pipeline

import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.llm.VisionOutputMode
import app.inku.mobile.llm.VisionPrompts
import java.io.File
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** One real JNI + Room path; the model transport is deterministic and local to the test. */
@RunWith(AndroidJUnit4::class)
class AndroidSharedPipelineTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private var database: InkuDatabase? = null
    private var repository: InkuRepository? = null

    @After
    fun tearDown(): Unit = runBlocking {
        repository?.close()
        database?.close()
    }

    @Test
    fun bundledMacroReachesScoreThroughNormalAuthoring() = runBlocking {
        val provider = ScriptedProvider()
        val db = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .build().also { database = it }
        val repo = InkuRepository(context, db, modelProviderOverride = provider)
            .also { repository = it }
        val memoryBefore = android.os.Debug.MemoryInfo().also { android.os.Debug.getMemoryInfo(it) }
        val started = android.os.SystemClock.elapsedRealtime()
        val work = repo.paint(
            description = "Young leaves and a mirror pair",
            catalogId = "default", canvasAspect = "square",
            stage1ModelId = MODEL, stage2ModelId = MODEL,
            seeds = PaintSeeds(renderSeed = 77L, compositionSeed = 17L),
            instructionLang = "en", uiLang = "en",
        )
        val elapsed = android.os.SystemClock.elapsedRealtime() - started
        val memoryAfter = android.os.Debug.MemoryInfo().also { android.os.Debug.getMemoryInfo(it) }
        assertEquals(1, provider.requests.size)
        assertEquals(STEP16_DDL, work.normalizedDdl)
        assertTrue(work.displaySvg.startsWith("<svg"))
        val score = JSONObject(work.scoreJson)
        assertTrue(score.getJSONArray("instructions").length() > 0)
        assertTrue(score.getJSONArray("repetition_groups").length() > 0)
        assertEquals(1, score.getJSONArray("mirror_relations").length())
        val diagnostics = JSONObject(work.renderMetadataJson).getJSONObject("pipeline_diagnostics")
        assertEquals(0, diagnostics.getJSONArray("relation_omissions").length())
        assertEquals(0, diagnostics.getJSONArray("resource_omissions").length())
        assertEquals(0, diagnostics.getJSONObject("render_diagnostics").getJSONArray("diagnostics").length())
        val managed = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, work.id)!!
        val config = JSONObject(managed.forkContextJson!!).getJSONObject("config")
        assertEquals("description_authoritative", managed.authority)
        File(context.cacheDir, "step16-shared-pipeline.json").writeText(
            JSONObject()
                .put("schema", "inku.android-shared-pipeline-evidence.v1")
                .put("binding", JSONObject(NativePipelineBridge.versionReport()))
                .put("description", work.originalInput)
                .put("normalized_ddl", work.normalizedDdl)
                .put("config", config)
                .put("score", score)
                .put("macro_repetition_groups", score.getJSONArray("repetition_groups").length())
                .put("mirror_relations", score.getJSONArray("mirror_relations").length())
                .put("relation_omissions", diagnostics.getJSONArray("relation_omissions").length())
                .put("render_seed", "77").put("composition_seed", "17")
                .put("authoring_elapsed_ms", elapsed)
                .put("pss_before_kib", memoryBefore.totalPss)
                .put("pss_after_kib", memoryAfter.totalPss)
                .put("svg_bytes", work.displaySvg.toByteArray(Charsets.UTF_8).size)
                .toString(),
        )
    }

    /**
     * Device-only seam check for the camera DDL prompt: this calls the packaged JNI library,
     * then verifies that the Kotlin camera prompt keeps the returned shared prefix and appends
     * only its camera-specific boundary. It deliberately performs no model, Room, or render work.
     */
    @Test
    fun cameraDdlV2UsesPackagedSharedProjectionAndCameraBoundary() {
        val version = JSONObject(NativePipelineBridge.versionReport())
        assertEquals("1.1.0", version.getString("binding_version"))
        assertEquals("1.0.0", version.getString("protocol_version"))
        assertEquals("camera-ddl-v2", VisionPrompts.versionFor(VisionOutputMode.DDL))

        val jaProjection = NativePipelineBridge.stage1SystemProjection("ja")
        val enProjection = NativePipelineBridge.stage1SystemProjection("en")
        val jaCameraPrompt = VisionPrompts.forLanguage("ja", VisionOutputMode.DDL)
        val enCameraPrompt = VisionPrompts.forLanguage("en", VisionOutputMode.DDL)

        assertFalse(jaProjection.contains("JSON"))
        assertFalse(enProjection.contains("JSON"))
        assertFalse(jaProjection.contains("normalized_ddl"))
        assertFalse(enProjection.contains("normalized_ddl"))
        assertTrue(jaCameraPrompt.startsWith(jaProjection))
        assertTrue(enCameraPrompt.startsWith(enProjection))
        assertTrue(jaCameraPrompt.contains("# カメラ入力境界"))
        assertTrue(enCameraPrompt.contains("# Camera input boundary"))
    }

    @Test
    fun nativeSharedPipelineSavesEditsForksAndReplaysExactScore() = runBlocking {
        val provider = ScriptedProvider()
        val db = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .build()
            .also { database = it }
        val repo = InkuRepository(context, db, modelProviderOverride = provider)
            .also { repository = it }
        val seeds = PaintSeeds(renderSeed = 77L, compositionSeed = 17L)

        val first = repo.paint(
            description = "One quiet black circle",
            catalogId = "default",
            canvasAspect = "pixel9_landscape_safe",
            stage1ModelId = MODEL,
            stage2ModelId = MODEL,
            seeds = seeds,
            instructionLang = "en",
            uiLang = "en",
        )

        assertEquals(1, provider.requests.size)
        assertEquals("new paper after a legacy selection uses the canonical default", "square", first.canvasAspect)
        assertTrue(first.displaySvg.startsWith("<svg"))
        assertTrue(JSONObject(first.scoreJson).getJSONArray("instructions").length() > 0)
        val firstMetadata = JSONObject(first.renderMetadataJson)
        val executionId = firstMetadata.getString("pipeline_execution_id")
        val firstManaged = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, first.id)
        assertNotNull(firstManaged)
        assertEquals("description_authoritative", firstManaged!!.authority)
        assertEquals("1", firstManaged.revision)
        val firstContext = JSONObject(firstManaged.forkContextJson!!)
        File(context.cacheDir, "step14-shared-pipeline.json").writeText(
            JSONObject()
                .put("schema", "inku.android-shared-pipeline-evidence.v1")
                .put("binding", JSONObject(NativePipelineBridge.versionReport()))
                .put("description", first.originalInput)
                .put("normalized_ddl", first.normalizedDdl)
                .put("config", firstContext.getJSONObject("config"))
                .put("score", JSONObject(first.scoreJson))
                .put("render_seed", "77")
                .put("composition_seed", "17")
                .toString(),
        )

        val edited = repo.composeFromDdl(
            description = first.originalInput,
            ddl = EDITED_DDL,
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = MODEL,
            stage2ModelId = MODEL,
            seeds = seeds,
            instructionLang = "en",
            uiLang = "en",
            executionId = executionId,
        )

        assertEquals("a complete direct edit needs no model transport", 1, provider.requests.size)
        val editedManaged = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, edited.id)
        assertNotNull(editedManaged)
        assertEquals("ddl_authoritative", editedManaged!!.authority)
        assertEquals("2", editedManaged.revision)
        assertEquals(firstManaged.variationId, editedManaged.variationId)
        assertEquals(EDITED_DDL, edited.normalizedDdl)

        val regenerated = repo.paint(
            description = "One quiet blue circle",
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = MODEL,
            stage2ModelId = MODEL,
            seeds = seeds,
            instructionLang = "en",
            uiLang = "en",
            parentHistoryId = edited.id,
        )
        val regeneratedManaged = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, regenerated.id)
        assertNotNull(regeneratedManaged)
        assertEquals("description_authoritative", regeneratedManaged!!.authority)
        assertNotEquals(editedManaged.variationId, regeneratedManaged.variationId)
        val editedPolicy = JSONObject(editedManaged.forkContextJson!!)
            .getJSONObject("config")
            .getJSONObject("compiler")
            .getJSONObject("hard_resource_policy")
            .toString()
        val regeneratedPolicy = JSONObject(regeneratedManaged.forkContextJson!!)
            .getJSONObject("config")
            .getJSONObject("compiler")
            .getJSONObject("hard_resource_policy")
            .toString()
        assertEquals(
            "a description fork keeps its independently stored resource authority",
            editedPolicy,
            regeneratedPolicy,
        )

        val replay = repo.renderFromScore(
            description = edited.originalInput,
            scoreJson = edited.scoreJson,
            catalogId = "default",
            canvasAspect = "square",
            stage1ModelId = MODEL,
            stage2ModelId = MODEL,
            seeds = seeds,
            parentHistoryId = edited.id,
        )
        assertEquals(JSONObject(edited.scoreJson).toString(), JSONObject(replay.scoreJson).toString())
        assertEquals(edited.displaySvg, replay.displaySvg)
        assertEquals(edited.normalizedDdl, replay.normalizedDdl)
        val replayManaged = repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, replay.id)!!
        assertEquals(editedManaged.variationId, replayManaged.variationId)
        assertEquals(editedManaged.revision, replayManaged.revision)
        assertEquals("ddl_authoritative", replayManaged.authority)
    }

    private class ScriptedProvider : ModelProvider {
        override val providerId = "fixture"
        val requests = mutableListOf<ModelRequest>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            requests += request
            val ddl = if (request.prompt.contains("Young leaves and a mirror pair")) {
                STEP16_DDL
            } else if (request.prompt.contains("One quiet blue circle")) {
                "place one blue circle at center."
            } else {
                "place one black circle at center."
            }
            return ModelResponse(JSONObject().put("normalized_ddl", ddl).toString(), request.modelId)
        }
    }

    private companion object {
        const val MODEL = "fixture:model"
        const val EDITED_DDL = "place one red circle at center."
        const val STEP16_DDL = "Nature.若葉. Place a small diagonal red arc at top. Place a blue arc at bottom, mirrored with the previous shape."
    }
}
