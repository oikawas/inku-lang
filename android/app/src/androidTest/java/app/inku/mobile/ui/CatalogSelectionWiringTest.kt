package app.inku.mobile.ui

import android.app.Application
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.HistoryItemEntity
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The drawing paths reach the pipeline with the catalogue the settings name,
 * and nothing else decides it (ledger I-103).
 *
 * `ColorCatalogSelectionDeterminismTest` on the JVM drives `CatalogSelection`
 * directly and stays green whether or not anything calls it -- the version of
 * it that shipped with I-081 was green while the random pick sat in the demo
 * path. Seeing the wiring needs the real `InkuViewModel` and the real
 * `InkuRepository`, which need a context and a database, so it happens here on
 * the device.
 *
 * This is the counterpart of the server's `test_color_auto_select`, which
 * drives `/api/paint` and replaces only `_ask_model`: the whole run is real
 * except the language model, and the catalogue the run used is read back from
 * what was saved.
 *
 * Four of the five call sites are covered: the draw path's `composeFromDdl`,
 * `drawFromDdl`, the demo `paint` and the batch `paint`. The fifth is the draw
 * path's `interpret`, whose catalogue argument was measured to reach nothing
 * but a log line -- putting a random pick there changes no drawing and no test
 * can see it. Making it observable is a question about the layer, not about
 * this gate, and is on the ledger.
 */
@RunWith(AndroidJUnit4::class)
class CatalogSelectionWiringTest {

    /**
     * Answers every request with the text it was given, so that two runs of two
     * descriptions stay two pictures. A model that answered with one fixed
     * sentence made every run render the same score, and the second save was
     * refused by the unique render hash.
     *
     * Nothing here reaches a real model, which is the point: this stands in the
     * place the server's acceptance puts `_ask_model`.
     */
    private object EchoModel : ModelProvider {
        override val providerId: String = "test"

        override suspend fun generate(request: ModelRequest): ModelResponse =
            ModelResponse(text = request.prompt, modelId = request.modelId)
    }

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var viewModel: InkuViewModel
    private lateinit var store: ViewModelStore
    private lateinit var scope: CoroutineScope
    private var collection: Job? = null

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val application = context.applicationContext as Application
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        repository = InkuRepository(context, database, modelProviderOverride = EchoModel)
        // Held in a store rather than built by hand: the view model starts work
        // of its own that outlives a test method, and only `clear()` cancels it.
        // Left running, it goes on reading a database the next test has already
        // closed.
        store = ViewModelStore()
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                InkuViewModel(application, repositoryOverride = repository) as T
        }
        viewModel = ViewModelProvider(store, factory)[InkuViewModel::class.java]
        // `state` is shared with `WhileSubscribed`, and every drawing path reads
        // `state.value`. Without a collector it would stay at the initial
        // `InkuUiState()` and the settings written below would never be seen.
        scope = CoroutineScope(Dispatchers.Main)
        collection = scope.launch { viewModel.state.collect { } }
    }

    @After
    fun tearDown() = runBlocking {
        viewModel.stopDrawing()
        collection?.cancel()
        scope.cancel()
        withContext(Dispatchers.Main) { store.clear() }
        // `onCleared` closes the repository on the application scope; the
        // database goes last so that nothing is still reading it.
        delay(SETTLE_AFTER_CLEAR_MS)
        // Closing it here as well is what makes the wait above a belt rather
        // than the guarantee: this one blocks until the scheduled thumbnail
        // write is on disk, so the close below cannot land on top of it.
        repository.close()
        database.close()
    }

    private suspend fun settle(what: String, condition: () -> Boolean) {
        withTimeout(TIMEOUT_MS) {
            while (!condition()) {
                delay(POLL_MS)
            }
        }
    }

    /** Puts the settings in a known state: a chosen catalogue and models that stay local. */
    private suspend fun useCatalog(catalogId: String) {
        viewModel.setSelectedModel(STAGE_MODEL)
        viewModel.setCatalog(catalogId)
        settle("the settings to reach the shared state") {
            viewModel.state.value.selectedCatalogId == catalogId &&
                viewModel.state.value.selectedModelId == STAGE_MODEL
        }
    }

    /**
     * `state` is combined and shared, so a setter's value arrives a hop later.
     * A draw started before the hop would use the previous prompt and land on
     * the render hash the previous run already saved.
     */
    private suspend fun promptFor(run: String) {
        viewModel.setPrompt(run)
        settle("the prompt to reach the shared state") { viewModel.state.value.prompt == run }
    }

    private suspend fun awaitSavedRuns(count: Int): List<HistoryItemEntity> {
        var rows: List<HistoryItemEntity> = emptyList()
        try {
            settle("the drawing to be saved") {
                rows = runBlocking { database.historyDao().listActive(20, 0).first() }
                rows.size >= count
            }
        } catch (timeout: Exception) {
            throw AssertionError(
                "no drawing was saved within ${TIMEOUT_MS}ms; last message was " +
                    "\"${viewModel.state.value.message}\"",
                timeout,
            )
        }
        return rows
    }

    @Test
    fun t1_theDrawPathReachesThePipelineWithTheChosenCatalogue() = runBlocking {
        useCatalog("ink_season")
        promptFor("配線を見る 一")
        viewModel.draw()

        val saved = awaitSavedRuns(1)

        assertEquals("ink_season", saved.first().colorCatalogId)
    }

    @Test
    fun t2_theDdlPathReachesThePipelineWithTheChosenCatalogue() = runBlocking {
        useCatalog("fresco_study")
        promptFor("配線を見る 二")
        viewModel.drawFromDdl()

        val saved = awaitSavedRuns(1)

        assertEquals("fresco_study", saved.first().colorCatalogId)
    }

    @Test
    fun t3_theDemoPathReachesThePipelineWithTheChosenCatalogue() = runBlocking {
        // The random pick I-081 removed lived in this path, so a gate that
        // skipped it would leave the one place it happened uncovered.
        useCatalog("open_air_light")
        viewModel.startDemo()

        val saved = awaitSavedRuns(1)
        viewModel.stopDrawing()

        assertEquals("open_air_light", saved.first().colorCatalogId)
        assertEquals("open_air_light", viewModel.state.value.demoCurrentCatalogId)
    }

    @Test
    fun t4_theBatchPathReachesThePipelineWithTheChosenCatalogue() = runBlocking {
        // The fourth of the five call sites. Its catalogue is read once for the
        // whole batch, so a line that chose again would show up as two
        // catalogues across the two rows.
        useCatalog("cool_material")
        viewModel.setBatchText("赤い円を5個、横に並べる\n黒い太筆の線を3本、斜めに置く")
        settle("the batch text to reach the shared state") {
            viewModel.state.value.batchText.lines().size == 2
        }
        viewModel.runBatch()

        val saved = awaitSavedRuns(2)

        assertTrue(
            "every line of the batch must use the catalogue the settings name, got " +
                saved.map { it.colorCatalogId },
            saved.all { it.colorCatalogId == "cool_material" },
        )
    }

    @Test
    fun t5_repeatedRunsOfOneSettingAllReachTheSameCatalogue() = runBlocking {
        // Two runs, not two reads of one value: a path that chose again per run
        // is what this has to be able to see.
        // The two runs have to draw different pictures: the render hash is
        // unique in history_items, so a second run that reached the same score
        // would not be saved at all.
        useCatalog("ink_porcelain")
        promptFor("赤い円を5個、横に並べる")
        viewModel.draw()
        awaitSavedRuns(1)
        settle("the first run to finish") { !viewModel.state.value.isDrawing }
        promptFor("黒い太筆の線を3本、斜めに置く")
        viewModel.draw()

        val saved = awaitSavedRuns(2)

        assertEquals(2, saved.size)
        assertTrue(
            "every run must use the catalogue the settings name, got " +
                saved.map { it.colorCatalogId },
            saved.all { it.colorCatalogId == "ink_porcelain" },
        )
    }

    private companion object {
        /** Not provider-qualified, so Stage 1 and Stage 2 may fall back locally. */
        const val STAGE_MODEL = "test-stage-model"
        const val TIMEOUT_MS = 90_000L
        const val POLL_MS = 200L
        const val SETTLE_AFTER_CLEAR_MS = 500L
    }
}
