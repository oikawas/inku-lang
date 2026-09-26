package app.inku.mobile.ui

import android.app.Application
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.inku.mobile.data.InkuRepository
import app.inku.mobile.data.db.InkuDatabase
import app.inku.mobile.llm.ModelProvider
import app.inku.mobile.llm.ModelRequest
import app.inku.mobile.llm.ModelResponse
import app.inku.mobile.pipeline.PipelineHostPolicy
import app.inku.mobile.testing.pipelineFixtureResponse
import app.inku.mobile.ui.i18n.InkuStringsJa
import java.io.IOException
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The running row names the model call a drawing waits on (the Server review's W4).
 *
 * Stage 1 has a per-attempt timeout and a retry budget, and the row showed only
 * the elapsed time, so a first attempt that had timed out looked like a slow
 * answer. The attempt comes from the shared core in the packaged library, so
 * this drives the real pipeline: the first Stage 1 call is dropped, the second
 * is held, and while it is held the row has to say that it is a retry.
 */
@RunWith(AndroidJUnit4::class)
class RunStatusAttemptTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<ComponentActivity>()

    /** Drops the first Stage 1 call and holds the second until [release]. */
    private class DroppingStage1Model : ModelProvider {
        override val providerId: String = "test-dropping"
        val stage1Calls = AtomicInteger(0)
        val release = CompletableDeferred<Unit>()
        val actions = CopyOnWriteArrayList<String>()

        override suspend fun generate(request: ModelRequest): ModelResponse {
            actions += request.pipelineAction ?: "no-action"
            if (request.pipelineAction == STAGE1_ACTION) {
                when (stage1Calls.incrementAndGet()) {
                    1 -> throw IOException("the first Stage 1 call is dropped")
                    2 -> release.await()
                }
            }
            return pipelineFixtureResponse(request)
        }
    }

    private lateinit var database: InkuDatabase
    private lateinit var repository: InkuRepository
    private lateinit var model: DroppingStage1Model
    private lateinit var viewModel: InkuViewModel
    private val store = ViewModelStore()

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, InkuDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        model = DroppingStage1Model()
        repository = InkuRepository(context, database, modelProviderOverride = model)
        val application = context.applicationContext as Application
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                InkuViewModel(application, repositoryOverride = repository) as T
        }
        viewModel = ViewModelProvider(store, factory)[InkuViewModel::class.java]
    }

    @After
    fun tearDown() = runBlocking {
        model.release.complete(Unit)
        withContext(Dispatchers.Main) {
            viewModel.stopDrawing()
            store.clear()
        }
        // `onCleared` closes the repository on the application scope; the
        // database goes last so that nothing is still reading it.
        delay(SETTLE_AFTER_CLEAR_MS)
        repository.close()
        database.close()
    }

    @Test
    fun aRetriedStage1ReadsAsARetryInTheRunningRow() {
        composeTestRule.setContent {
            val state by viewModel.state.collectAsState()
            RunStatusRow(state, viewModel)
        }
        composeTestRule.runOnIdle {
            viewModel.setSelectedModel(STAGE_MODEL)
            viewModel.setCatalog(CATALOG)
            viewModel.setPrompt(PROMPT)
        }
        // `state` is combined and shared, so a setter's value arrives a hop later.
        composeTestRule.waitUntil(TIMEOUT_MS) {
            val state = viewModel.state.value
            state.selectedModelId == STAGE_MODEL && state.selectedCatalogId == CATALOG && state.prompt == PROMPT
        }
        composeTestRule.runOnIdle { viewModel.draw() }

        val retry = InkuStringsJa.runStatusRetrying(2, PipelineHostPolicy().maximumProviderAttempts)
        fun rowShowsRetry() =
            composeTestRule.onAllNodesWithText(retry, substring = true).fetchSemanticsNodes().isNotEmpty()
        // The retry reads as one from the start of its delay, before the second
        // call is made, so the row is watched first and the call counted after.
        try {
            composeTestRule.waitUntil(TIMEOUT_MS) { rowShowsRetry() }
            composeTestRule.waitUntil(TIMEOUT_MS) { model.stage1Calls.get() == 2 }
        } catch (timeout: Throwable) {
            val state = viewModel.state.value
            throw AssertionError(
                "no held retry; row=${rowShowsRetry()} drawing=${state.isDrawing} message=${state.message} " +
                    "calls=${model.actions} attempt=${repository.providerAttempt.value}",
                timeout,
            )
        }
        assertTrue("still a retry while the second call is held", rowShowsRetry())
        assertEquals(2, repository.providerAttempt.value?.attempt)

        model.release.complete(Unit)
        composeTestRule.waitUntil(TIMEOUT_MS) { !viewModel.state.value.isDrawing }
        assertNull("a run that has finished waits on nothing", repository.providerAttempt.value)
    }

    private companion object {
        /** The effect tag the host passes on as the request's action name. */
        const val STAGE1_ACTION = "generate_normalized_ddl"
        const val STAGE_MODEL = "test-stage-model"
        const val CATALOG = "ink_season"
        const val PROMPT = "夕暮れに鳥が二羽"
        const val TIMEOUT_MS = 60_000L
        const val SETTLE_AFTER_CLEAR_MS = 500L
    }
}
