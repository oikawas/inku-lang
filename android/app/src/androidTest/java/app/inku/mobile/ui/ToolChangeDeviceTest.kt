package app.inku.mobile.ui

import android.content.Context
import android.content.ContextWrapper
import android.graphics.Bitmap
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.InkuApplication
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.data.refinement.PaintSeeds
import app.inku.mobile.data.refinement.RefinementParent
import app.inku.mobile.data.refinement.ToolChangeMode
import app.inku.mobile.data.lineage.LineagePlanner
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.AndroidWorkPipeline
import app.inku.mobile.testing.pipelineFixtureResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** JNI, live dialog, and persistence against a disposable DB/files/prefs only. */
@RunWith(AndroidJUnit4::class)
class ToolChangeDeviceTest {
    @get:Rule val ui = createAndroidComposeRule<ComponentActivity>()
    private var database: InkuDatabase? = null
    private var repository: InkuRepository? = null
    private var app: InkuApplication? = null
    private var store: ViewModelStore? = null
    private var vm: InkuViewModel? = null
    private var files: File? = null
    private val preferences = mutableSetOf<String>()
    private val target = InstrumentationRegistry.getInstrumentation().targetContext

    private fun isolatedApplication(): InkuApplication {
        val id = UUID.randomUUID().toString()
        val root = File(target.cacheDir, "tool-change-test-" + id).apply { mkdirs() }
        files = root
        val application = InkuApplication()
        val context = object : ContextWrapper(target) {
            override fun getApplicationContext(): Context = application
            override fun getFilesDir() = File(root, "files").apply { mkdirs() }
            override fun getCacheDir() = File(root, "cache").apply { mkdirs() }
            override fun getSharedPreferences(name: String, mode: Int): android.content.SharedPreferences {
                val ownName = "tool-test-" + id + "-" + name
                preferences += ownName
                return target.getSharedPreferences(ownName, mode)
            }
        }
        ContextWrapper::class.java.getDeclaredMethod("attachBaseContext", Context::class.java)
            .apply { isAccessible = true }.invoke(application, context)
        app = application
        return application
    }

    @After fun cleanup() = runBlocking {
        withContext(Dispatchers.Main) { store?.clear() }
        repository?.close()
        app?.applicationScope?.cancel()
        delay(300)
        database?.close()
        files?.deleteRecursively()
        preferences.forEach { target.deleteSharedPreferences(it) }
    }

    private fun await(condition: (InkuUiState) -> Boolean) {
        ui.waitUntil(30_000) { condition(requireNotNull(vm).state.value) }
    }

    private fun capture(name: String) {
        ui.waitForIdle()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        automation.waitForIdle(500, 5_000)
        val file = File(target.getExternalFilesDir(null), name)
        val bitmap = requireNotNull(automation.takeScreenshot())
        file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    @Test fun fourOptionsReplaceOnRequestWithoutModelsAndSavedTouchChildrenRemainManaged() = runBlocking {
        val application = isolatedApplication()
        val db = Room.inMemoryDatabaseBuilder(application, InkuDatabase::class.java).allowMainThreadQueries().build()
        database = db
        var parentIsReady = false
        var candidateModelCalls = 0
        val repo = InkuRepository(application, db, modelProviderOverride = object : ModelProvider {
            override val providerId = "tool-fixture"
            override suspend fun generate(request: ModelRequest): ModelResponse {
                if (parentIsReady) { candidateModelCalls++; error("A touch change must not call a model") }
                return pipelineFixtureResponse(request)
            }
        })
        repository = repo
        val parent = repo.composeFromDdl(
            description = "tool parent",
            ddl = "背景を白で埋める。\n青の細筆の線を3個引く。\n赤の大きな円を1個置く。",
            catalogId = "ink_season", canvasAspect = "square",
            stage1ModelId = "test-stage1", stage2ModelId = "test-stage2",
            seeds = PaintSeeds(renderSeed = 4242L, compositionSeed = 77L),
        )
        parentIsReady = true
        val parentManaged = requireNotNull(repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, parent.id))
        assertNotNull(parentManaged.forkContextJson)
        val createdStore = ViewModelStore()
        store = createdStore
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = InkuViewModel(application, repo) as T
        }
        vm = ViewModelProvider(createdStore, factory)[InkuViewModel::class.java]
        ui.setContent { InkuApp(requireNotNull(vm)) }
        ui.runOnIdle { requireNotNull(vm).openWorkActions(parent) }
        await { it.workActionsTarget?.id == parent.id }
        ui.onNodeWithTag(TOOL_CHANGE_ENTRY_TAG).performClick()
        await { it.toolChangeOpen }
        ui.onNodeWithTag(TOOL_CHANGE_DIALOG_TAG).assertIsDisplayed()
        ui.runOnIdle {
            assertFalse(requireNotNull(vm).state.value.refinementBusy)
            assertTrue(requireNotNull(vm).state.value.refinementCandidates.isEmpty())
            assertEquals(ToolChangeMode.Uniform, requireNotNull(vm).state.value.toolChangeMode)
        }
        ui.onNodeWithText("すべての文を同じ筆記具にする").assertIsDisplayed()
        ui.onNodeWithText("文ごとに違う筆記具にする").assertIsDisplayed()
        ui.onNodeWithText("替え方を選んで「4案を作る」を押すと、筆記具を替えた4案を並べます。もう一度押すと、並んでいる案を捨てて新しい4案に替えます。")
            .assertIsDisplayed()
        capture("tool-change-manual-empty-20261014.png")
        ui.onNodeWithTag(TOOL_CHANGE_GENERATE_TAG).performScrollTo().performClick()
        await { !it.refinementBusy && it.refinementCandidates.size == 4 }
        ui.onNodeWithTag(TOOL_CHANGE_DIALOG_TAG).assertIsDisplayed()
        val first = requireNotNull(vm).state.value.refinementCandidates
        assertTrue(first.all { it.plan.toolChange?.mode == ToolChangeMode.Uniform })
        assertEquals(4, first.map { it.label }.toSet().size)
        db.openHelper.readableDatabase.query("SELECT COUNT(*) FROM history_items").use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals(1, cursor.getInt(0))
        }
        val parentScore = LineagePlanner.canonicalJson(JSONObject(parent.scoreJson))
        assertEquals(parentScore, LineagePlanner.canonicalJson(JSONObject(requireNotNull(repo.getHistoryById(parent.id)).scoreJson)))
        assertTrue(first.all { it.pipelineResult?.renderSeed == 4242L })
        // Unsaved options are asked about (2026-10-18); declining keeps them.
        ui.runOnIdle { requireNotNull(vm).closeToolChange() }
        assertTrue(requireNotNull(vm).state.value.toolChangeOpen)
        assertEquals(DiscardConfirm.Candidates(4), requireNotNull(vm).state.value.discardConfirm)
        ui.runOnIdle { requireNotNull(vm).cancelDiscard() }
        assertEquals(first.map { it.id }, requireNotNull(vm).state.value.refinementCandidates.map { it.id })
        capture("tool-change-manual-uniform-20261014.png")
        ui.onNodeWithTag("tool-mode-per_sentence").performScrollTo().performClick()
        ui.runOnIdle {
            assertFalse(requireNotNull(vm).state.value.refinementBusy)
            assertEquals(first.map { it.id }, requireNotNull(vm).state.value.refinementCandidates.map { it.id })
            requireNotNull(vm).previewRefinementCandidate(first.first().id)
        }
        ui.onNodeWithTag(TOOL_CHANGE_GENERATE_TAG).performScrollTo().performClick()
        await { !it.refinementBusy && it.refinementCandidates.size == 4 && it.refinementCandidates.first().id != first.first().id }
        val all = requireNotNull(vm).state.value.refinementCandidates
        assertTrue(first.map { it.id }.toSet().intersect(all.map { it.id }.toSet()).isEmpty())
        assertNull(requireNotNull(vm).state.value.refinementPreviewId)
        assertTrue(all.all { candidate ->
            candidate.plan.toolChange!!.mode == ToolChangeMode.PerSentence &&
                candidate.plan.toolChange!!.changes.all { it.from != it.to } && candidate.label.startsWith("文ごと ")
        })
        ui.onNodeWithText(all.first().label).performScrollTo().assertIsDisplayed()
        val changed = all.first().plan.toolChange!!.changes.first()
        val words = all.first().plan.toolChange!!.source.tools.associateBy { it.value }
        val line = "${changed.index + 1}: ${words.getValue(changed.from).ja} → ${words.getValue(changed.to).ja}"
        ui.onAllNodesWithText(line).onFirst().performScrollTo().assertIsDisplayed()
        ui.onNodeWithText(all.first().renderHashShort).performScrollTo().assertIsDisplayed()
        ui.onAllNodesWithText(line).onFirst().assertIsDisplayed()
        capture("tool-change-manual-per-sentence-20261014.png")
        ui.onAllNodesWithTag(REFINE_SAVE_TAG).onFirst().performScrollTo().performClick()
        await { it.refinementCandidates.first().saveState == RefinementSaveState.Saved }
        val childId = requireNotNull(requireNotNull(vm).state.value.refinementCandidates.first().savedHistoryId)
        val child = requireNotNull(repo.getHistoryById(childId))
        assertEquals(parent.sourceText ?: parent.originalInput, child.sourceText)
        assertEquals(4242L, java.lang.Long.parseUnsignedLong(requireNotNull(child.renderSeed)))
        assertNotEquals(parent.normalizedDdl, child.normalizedDdl)
        assertEquals(LineagePlanner.canonicalJson(JSONObject(all.first().scoreJson)), LineagePlanner.canonicalJson(JSONObject(child.scoreJson)))
        val managed = requireNotNull(repo.readManagedHistory(AndroidWorkPipeline.OWNER_ID, child.id))
        assertNull(managed.warning)
        assertEquals("ddl_authoritative", managed.authority)
        assertNotEquals(parentManaged.variationId, managed.variationId)
        assertNotNull(managed.forkContextJson)
        val options = repo.toolChangeOptions(RefinementParent.of(child, child.sourceText.orEmpty()), ToolChangeMode.Uniform)
        assertTrue(options.isNotEmpty())
        db.openHelper.readableDatabase.query(
            "SELECT derivation_kind, metadata_json FROM lineage_edges WHERE child_node_id = ?",
            arrayOf(child.lineageNodeId),
        ).use { cursor ->
            assertTrue(cursor.moveToFirst())
            assertEquals("tool_change", cursor.getString(0))
            val metadata = JSONObject(cursor.getString(1))
            assertEquals("per_sentence", metadata.getString("tool_mode"))
            assertTrue(metadata.getJSONArray("changes").length() > 0)
            assertTrue(metadata.getJSONObject("tools").length() > 0)
        }
        assertEquals(0, candidateModelCalls)
        ui.runOnIdle { requireNotNull(vm).closeToolChange(discard = true) }
        await { !it.toolChangeOpen }
    }
}
