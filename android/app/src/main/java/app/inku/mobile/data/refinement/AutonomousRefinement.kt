package app.inku.mobile.data.refinement

import app.inku.mobile.pipeline.NativePipelineBridge
import app.inku.mobile.pipeline.SharedPipelineBinding
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class AutonomousSettings(
    val moves: Int = 5,
    val useLaws: Boolean = true,
    val useJuxtaposition: Boolean = true,
    val modelId: String = "",
    val direction: String = "",
    val wildOverride: Boolean? = null,
) {
    val allowedKinds: List<String> get() = buildList {
        if (useLaws) add("laws")
        if (useJuxtaposition) add("juxtaposition")
    }
    fun toJson(language: String): JSONObject = JSONObject().put("moves", moves)
        .put("kinds", JSONArray(allowedKinds)).put("model", modelId)
        .put("note", direction.trim().ifEmpty { null } ?: JSONObject.NULL)
        .put("language", language).put("wild", wildOverride ?: JSONObject.NULL)

    companion object {
        fun fromJson(value: JSONObject): AutonomousSettings {
            val kinds = value.getJSONArray("kinds")
            val names = (0 until kinds.length()).map(kinds::getString)
            return AutonomousSettings(value.getInt("moves"), "laws" in names, "juxtaposition" in names,
                value.optString("model"), value.opt("note") as? String ?: "",
                value.opt("wild") as? Boolean)
        }
    }
}

/** Thin transport: Kotlin never chooses moves, thresholds, or provenance fields. */
object SharedAutonomousRefinement {
    fun call(action: String, fields: JSONObject, binding: SharedPipelineBinding = NativePipelineBridge): JSONObject {
        val request = JSONObject(fields.toString()).put("action", action)
        val answer = JSONObject(binding.autonomousRefine(request.toString().encodeToByteArray()).toString(Charsets.UTF_8))
        require(!answer.has("error")) { "autonomous refinement: ${answer.optString("error")}" }
        require(answer.optString("schema") == "inku.autonomous-refine.v1") { "autonomous refinement schema mismatch" }
        require(answer.optString("outcome") == "ok") { "${answer.optString("reason")}: ${answer.optString("detail")}" }
        return answer
    }
}

data class AutonomousWork(val id: String, val svg: String, val facts: JSONObject, val basis: JSONObject?)

/** A failed move, classified by the host's actual pipeline phase. */
class AutonomousMoveFailure(val outcome: String, val reason: String) : Exception(reason)

interface AutonomousHost {
    suspend fun work(id: String): AutonomousWork
    suspend fun laws(parent: String, settings: AutonomousSettings, language: String, direction: JSONObject,
        onSaved: suspend (AutonomousWork) -> Unit)
    suspend fun juxtapose(parent: String, settings: AutonomousSettings, language: String, exclude: List<String>): JuxtapositionResult
    suspend fun drawJuxtaposition(parent: String, settings: AutonomousSettings, language: String,
        choice: JuxtapositionChoice, result: JuxtapositionResult, onSaved: suspend (AutonomousWork) -> Unit)
    suspend fun annotate(child: String, metadata: JSONObject)
    suspend fun promote(child: String)
}

interface AutonomousRunStore {
    suspend fun all(): List<JSONObject>
    suspend fun save(run: JSONObject)
}

/** One app-owned run survives a dialog; persisted running runs recover as interrupted. */
class AutonomousRefinementRunner(
    private val host: AutonomousHost,
    private val store: AutonomousRunStore,
    private val scope: CoroutineScope,
    private val core: (String, JSONObject) -> JSONObject = { action, fields -> SharedAutonomousRefinement.call(action, fields) },
) {
    private val mutex = Mutex()
    private var recovered = false
    private var job: Job? = null
    @Volatile private var stopping = false
    private val state = MutableStateFlow<String?>(null)
    val updates = state.asStateFlow()

    private suspend fun publish(run: JSONObject) {
        if (stopping && run.optString("state") == "running") run.put("stopping", true)
        store.save(run)
        state.value = run.toString()
    }

    private suspend fun recoverLocked() {
        if (recovered) return
        for (run in store.all()) {
            if (run.optString("state") == "running") {
                run.put("state", "interrupted").put("stop_reason", "interrupted").remove("current")
                publish(run)
            }
            // Promotion is idempotent, including a crash between finish and promotion.
            (run.opt("last_kept_history_id") as? String)?.let { host.promote(it) }
        }
        recovered = true
    }

    suspend fun recover() = mutex.withLock { recoverLocked() }

    suspend fun forHistory(id: String): JSONObject? = mutex.withLock {
        recoverLocked()
        store.all().filter { it.optString("history_id") == id }.maxByOrNull { it.getLong("created_at") }
    }

    suspend fun start(id: String, settings: AutonomousSettings, language: String) = mutex.withLock {
        recoverLocked()
        check(job?.isActive != true) { "autonomous_run_running" }
        require(settings.moves in 1..10 && settings.allowedKinds.isNotEmpty() && settings.modelId.isNotBlank())
        require(settings.direction.trim().codePointCount(0, settings.direction.trim().length) <= 1000)
        val parent = host.work(id)
        require(parent.svg.isNotBlank()) { "autonomous_source_has_no_image" }
        val run = JSONObject().put("id", UUID.randomUUID().toString()).put("history_id", id)
            .put("state", "running").put("settings", settings.toJson(language))
            .put("turns", JSONArray()).put("created_at", System.currentTimeMillis())
        stopping = false
        publish(run)
        job = scope.launch { drive(run, parent, settings, language) }
    }

    suspend fun stop() = mutex.withLock {
        stopping = true
        state.value?.let(::JSONObject)?.takeIf { it.optString("state") == "running" }?.let {
            it.put("stopping", true)
            state.value = it.toString()
        }
        job?.cancel()
    }

    private suspend fun finish(run: JSONObject, state: String, reason: String) {
        run.put("state", state).put("stop_reason", reason).remove("current")
        run.remove("stopping")
        publish(run)
        (run.opt("last_kept_history_id") as? String)?.let { host.promote(it) }
    }

    private suspend fun drive(run: JSONObject, original: AutonomousWork, settings: AutonomousSettings, language: String) {
        var parent = original
        val answers = mutableMapOf<Int, JuxtapositionResult>()
        try {
            while (true) {
                currentCoroutineContext().ensureActive()
                if (stopping) throw CancellationException("stopped")
                val turns = run.getJSONArray("turns")
                val answer = core("next", JSONObject().put("moves", settings.moves).put("kinds", JSONArray(settings.allowedKinds))
                    .put("parent", parent.facts).put("note", settings.direction.trim().ifEmpty { null } ?: JSONObject.NULL)
                    .put("turns", coreTurns(turns)))
                answer.optJSONObject("stop")?.let { finish(run, "done", it.getString("reason")); return }
                val step = answer.getJSONObject("next")
                run.put("current", step)
                publish(run)
                val taken = take(run, parent, settings, language, step, answers)
                if (!taken.has("history_id")) add(run, step, taken)
                if (taken.getString("outcome") == "kept") {
                    parent = host.work(taken.getString("history_id"))
                }
                run.remove("current")
                publish(run)
            }
        } catch (_: CancellationException) {
            withContext(NonCancellable) { finish(run, "stopped", "stopped") }
        } catch (error: Exception) {
            withContext(NonCancellable) {
                run.put("error", (error.message ?: error.javaClass.simpleName).take(500))
                finish(run, "failed", "failed")
            }
        }
    }

    private suspend fun add(run: JSONObject, step: JSONObject, taken: JSONObject) {
        val turns = run.getJSONArray("turns")
        val turn = step.getInt("turn")
        while (turns.length() < turn) turns.put(JSONObject().put("attempts", JSONArray()))
        turns.getJSONObject(turn - 1).getJSONArray("attempts").put(taken.put("attempt", step.getInt("attempt")))
        if (taken.optString("outcome") == "kept") run.put("last_kept_history_id", taken.getString("history_id"))
        run.remove("current")
        publish(run)
    }

    private suspend fun take(run: JSONObject, parent: AutonomousWork, settings: AutonomousSettings, language: String,
        step: JSONObject, answers: MutableMap<Int, JuxtapositionResult>): JSONObject {
        val kind = step.getString("kind")
        val taken = JSONObject().put("kind", kind)
        var moved: JSONObject? = null
        var recorded = false
        // Called inside the host's non-cancellable save boundary. Stop can
        // cancel the model request, but cannot abandon a child already saved.
        val onSaved: suspend (AutonomousWork) -> Unit = { child ->
            val measured = core("measure", JSONObject().put("before", parent.svg).put("after", child.svg))
            val outcome = if (measured.getBoolean("passes")) "kept" else "not_visible"
            val record = JSONObject().put("run", run.getString("id")).put("turn", step.getInt("turn"))
                .put("moves", settings.moves).put("attempt", step.getInt("attempt")).put("kind", kind)
                .put("model", settings.modelId).put("outcome", outcome).put("share", measured.get("share"))
                .put("note", settings.direction.trim().ifEmpty { null } ?: JSONObject.NULL)
            if (kind == "laws") {
                val basis = requireNotNull(child.basis) { "laws child keeps no laws basis" }
                val direction = step.getJSONObject("direction")
                val laws = JSONObject()
                listOf("main_law", "main_layer", "laws", "reason").forEach { laws.put(it, basis.get(it)) }
                laws.put("excluded", direction.optJSONArray("exclude") ?: JSONArray())
                    .put("cards", direction.optString("cards", "as_usual"))
                record.put("laws", laws)
                taken.put("main_law", basis.getString("main_law"))
            } else record.put("juxtaposition", moved)
            host.annotate(child.id, core("record", record).getJSONObject("metadata"))
            taken.put("outcome", outcome).put("share", measured.get("share")).put("history_id", child.id)
            add(run, step, taken)
            recorded = true
        }
        try {
            if (kind == "laws") {
                host.laws(parent.id, settings, language, step.getJSONObject("direction"), onSaved)
            } else {
                val turn = step.getInt("turn")
                if (!step.optBoolean("reuse") || turn !in answers) {
                    answers[turn] = host.juxtapose(parent.id, settings, language, strings(step.getJSONArray("exclude")))
                }
                val result = answers.getValue(turn)
                val choice = result.choices[step.getInt("rank") - 1]
                moved = JSONObject().put("sentence", choice.sentence).put("history_ids", JSONArray(choice.historyIds))
                    .put("rank", choice.rank).put("position", choice.position).put("reason", choice.reason)
                    .put("candidates", result.candidates)
                taken.put("sentence", choice.sentence).put("rank", choice.rank)
                host.drawJuxtaposition(parent.id, settings, language, choice, result, onSaved)
            }
        } catch (failure: AutonomousMoveFailure) {
            check(!recorded) { "a saved child cannot become an unavailable move" }
            return taken.put("outcome", failure.outcome).put("reason", failure.reason)
        }
        check(recorded) { "host did not record its saved child" }
        return taken
    }
    companion object {
        private val TURN_KEYS = listOf("kind", "outcome", "reason", "share", "main_law", "sentence", "rank")
        fun strings(array: JSONArray): List<String> = (0 until array.length()).map(array::getString)
        fun coreTurns(turns: JSONArray): JSONArray = JSONArray((0 until turns.length()).map { turn ->
            val attempts = turns.getJSONObject(turn).getJSONArray("attempts")
            JSONObject().put("attempts", JSONArray((0 until attempts.length()).map { index ->
                val from = attempts.getJSONObject(index)
                JSONObject().also { to -> TURN_KEYS.forEach { key -> if (from.has(key) && !from.isNull(key)) to.put(key, from.get(key)) } }
            }))
        })
    }
}
