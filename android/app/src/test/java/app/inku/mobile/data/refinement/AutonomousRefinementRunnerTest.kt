package app.inku.mobile.data.refinement

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AutonomousRefinementRunnerTest {
    private class Store : AutonomousRunStore {
        val runs = linkedMapOf<String, String>()
        override suspend fun all() = runs.values.map(::JSONObject)
        override suspend fun save(run: JSONObject) { runs[run.getString("id")] = run.toString() }
    }

    private open class Host : AutonomousHost {
        val promoted = mutableListOf<String>()
        val metadata = mutableMapOf<String, JSONObject>()
        val directions = mutableListOf<JSONObject>()
        var settingsSeen: AutonomousSettings? = null
        var lawsUnavailable = false
        var choosing = 0
        var drawn = 0
        val basis = JSONObject("""{"main_law":"B2","main_layer":0,"laws":{"B2":{"targets":[{"layer":0,"at":"point_ul"}]}},"reason":"置く"}""")
        val white = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 100 100\"><rect width=\"100\" height=\"100\" fill=\"white\"/></svg>"
        val black = white.replace("white", "black")
        override suspend fun work(id: String) = AutonomousWork(id, if (id == "parent") white else black,
            JSONObject().put("description_locked", id.startsWith("laws")).put("ddl_work", false), if (id == "parent") null else basis)
        override suspend fun laws(parent: String, settings: AutonomousSettings, language: String, direction: JSONObject,
            onSaved: suspend (AutonomousWork) -> Unit) {
            directions += direction
            settingsSeen = settings
            if (lawsUnavailable) throw AutonomousMoveFailure("unavailable", "no_law")
            withContext(NonCancellable) { onSaved(work("laws-${++drawn}")) }
        }
        override suspend fun juxtapose(parent: String, settings: AutonomousSettings, language: String, exclude: List<String>): JuxtapositionResult {
            choosing++
            return JuxtapositionResult((1..4).map { JuxtapositionChoice("一文$it。", "足す", listOf("other-$it"), it, 0.5, "元の記述。一文$it。") }, 10, settings.modelId)
        }
        override suspend fun drawJuxtaposition(parent: String, settings: AutonomousSettings, language: String,
            choice: JuxtapositionChoice, result: JuxtapositionResult, onSaved: suspend (AutonomousWork) -> Unit) {
            val id = "juxtaposition-${++drawn}"
            metadata[id] = JSONObject(juxtapositionMetadata(choice, result)).put("edited_from_history_id", parent)
            withContext(NonCancellable) { onSaved(work(id)) }
        }
        override suspend fun annotate(child: String, metadata: JSONObject) {
            val merged = this.metadata.getOrPut(child) { JSONObject() }
            metadata.keys().forEach { merged.put(it, metadata.get(it)) }
        }
        override suspend fun promote(child: String) { promoted += child }
    }

    private suspend fun ended(runner: AutonomousRefinementRunner): JSONObject = withTimeout(5000) {
        JSONObject(requireNotNull(runner.updates.first { it != null && JSONObject(it).optString("state") != "running" }))
    }

    @Test
    fun aLawsMoveKeepsTheCoreRecordAndPromotesOnlyItsLastKeptChild() = runBlocking {
        val host = Host(); val scope = CoroutineScope(coroutineContext + SupervisorJob()); val store = Store()
        try {
            val runner = AutonomousRefinementRunner(host, store, scope)
            val settings = AutonomousSettings(moves = 1, useJuxtaposition = false, modelId = "fixture:model", direction = " 涼しげに ")
            runner.start("parent", settings, "ja")
            val run = ended(runner)
            assertEquals("moves_done", run.getString("stop_reason"))
            assertEquals(listOf("laws-1"), host.promoted)
            assertEquals(settings, host.settingsSeen)
            assertTrue(host.directions.single().has("cards"))
            val record = host.metadata.getValue("laws-1").getJSONObject("ai_move")
            assertEquals("laws", record.getString("kind"))
            assertEquals("kept", record.getString("outcome"))
            assertEquals("fixture:model", record.getString("model"))
            assertEquals("涼しげに", record.getString("note"))
        } finally { scope.cancel() }
    }

    @Test
    fun aJuxtapositionMoveKeepsTheSentenceAndMoveTogether() = runBlocking {
        val host = Host(); val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val runner = AutonomousRefinementRunner(host, Store(), scope)
            runner.start("parent", AutonomousSettings(moves = 1, useLaws = false, modelId = "fixture:model"), "ja")
            val run = ended(runner)
            assertEquals("moves_done", run.getString("stop_reason"))
            val metadata = host.metadata.getValue("juxtaposition-1")
            assertEquals("parent", metadata.getString("edited_from_history_id"))
            assertEquals("juxtaposition", metadata.getJSONObject("ai_move").getString("kind"))
            assertEquals("一文1。", metadata.getJSONObject("juxtaposition").getString("sentence"))
            assertEquals(listOf("juxtaposition-1"), host.promoted)
        } finally { scope.cancel() }
    }

    @Test
    fun aTurnReusesItsFourSentencesAndLeavesInvisibleChildrenInTheLineageOnly() = runBlocking {
        val host = object : Host() {
            override suspend fun work(id: String) = super.work(id).copy(svg = white)
        }
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val runner = AutonomousRefinementRunner(host, Store(), scope)
            runner.start("parent", AutonomousSettings(moves = 1, useLaws = false, modelId = "fixture:model"), "ja")
            val run = ended(runner)
            assertEquals(1, host.choosing)
            assertTrue(host.drawn > 1)
            assertTrue(host.promoted.isEmpty())
            assertFalse(run.has("last_kept_history_id"))
            assertEquals((1..host.drawn).map { "一文$it。" }.toSet(),
                host.metadata.values.map { it.getJSONObject("juxtaposition").getString("sentence") }.toSet())
            assertTrue(host.metadata.values.all { it.getJSONObject("ai_move").getString("outcome") == "not_visible" })
        } finally { scope.cancel() }
    }

    @Test
    fun stoppingDuringTheSaveBoundaryStillRecordsAndPromotesTheSavedChild() = runBlocking {
        val saved = CompletableDeferred<Unit>(); val finishSave = CompletableDeferred<Unit>()
        val host = object : Host() {
            override suspend fun laws(parent: String, settings: AutonomousSettings, language: String,
                direction: JSONObject, onSaved: suspend (AutonomousWork) -> Unit) {
                withContext(NonCancellable) {
                    saved.complete(Unit); finishSave.await(); onSaved(work("laws-1"))
                }
            }
        }
        val scope = CoroutineScope(coroutineContext + SupervisorJob()); val store = Store()
        try {
            val runner = AutonomousRefinementRunner(host, store, scope)
            runner.start("parent", AutonomousSettings(moves = 5, useJuxtaposition = false, modelId = "fixture:model"), "ja")
            withTimeout(5000) { saved.await() }
            runner.stop(); finishSave.complete(Unit)
            val run = ended(runner)
            assertEquals("stopped", run.getString("stop_reason"))
            assertEquals("laws-1", run.getString("last_kept_history_id"))
            assertTrue(host.metadata.getValue("laws-1").has("ai_move"))
            assertEquals(listOf("laws-1"), host.promoted)
        } finally { scope.cancel() }
    }

    @Test
    fun anotherRunIsRejectedAndStopCancelsTheMoveInFlight() = runBlocking {
        val entered = CompletableDeferred<Unit>(); val cancelled = CompletableDeferred<Unit>()
        val host = object : Host() {
            override suspend fun laws(parent: String, settings: AutonomousSettings, language: String,
                direction: JSONObject, onSaved: suspend (AutonomousWork) -> Unit) {
                entered.complete(Unit)
                try { kotlinx.coroutines.awaitCancellation() } finally { cancelled.complete(Unit) }
            }
        }
        val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            val runner = AutonomousRefinementRunner(host, Store(), scope)
            val settings = AutonomousSettings(moves = 1, useJuxtaposition = false, modelId = "fixture:model")
            runner.start("parent", settings, "ja")
            withTimeout(5000) { entered.await() }
            try {
                runner.start("parent", settings, "ja")
                fail("a second run must be refused")
            } catch (error: IllegalStateException) { assertEquals("autonomous_run_running", error.message) }
            runner.stop()
            withTimeout(5000) { cancelled.await() }
            assertEquals("stopped", ended(runner).getString("stop_reason"))
            assertTrue(host.promoted.isEmpty())
        } finally { scope.cancel() }
    }

    @Test
    fun aRestartMarksTheRunInterruptedAndShowsItsLastKeptChild() = runBlocking {
        val store = Store(); val host = Host(); val scope = CoroutineScope(coroutineContext + SupervisorJob())
        try {
            store.save(JSONObject("""{"id":"cut-off","history_id":"parent","state":"running","turns":[],"created_at":1,"last_kept_history_id":"laws-1"}"""))
            val runner = AutonomousRefinementRunner(host, store, scope)
            runner.recover()
            assertEquals("interrupted", runner.forHistory("parent")!!.getString("stop_reason"))
            assertEquals(listOf("laws-1"), host.promoted)
        } finally { scope.cancel() }
    }
}
