package app.inku.mobile.llm

import java.net.SocketTimeoutException
import java.util.Base64
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import android.util.Log
import app.inku.mobile.data.catalogRequest
import kotlin.concurrent.withLock
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import org.json.JSONObject

/** How often the session and publication are checked again while an answer streams. */
private const val STREAM_CHECK_INTERVAL_NANOS = 1_000_000_000L

/**
 * One locally hosted Android user. Profiles remain separate by verified sub and client ID.
 *
 * Every procedure — sign-in, using and refreshing the token, the model list,
 * sign-out, deletion, selection, pausing and resuming — is the shared core's
 * (`chatgpt_flow_start`/`chatgpt_flow_next`, step 5): it answers what to do
 * next and [runFlow] does it. The locks are the core's three: `edit` guards the
 * store's reads and writes, `refresh` a token's refresh, `wire` the ChatGPT wire.
 */
class ChatGptPlanManager internal constructor(
    private val store: ChatGptCredentialStore,
    private val scope: CoroutineScope,
    private val http: ChatGptHttp = UrlConnectionChatGptHttp(),
    private val modelPolicy: () -> ChatGptModelPolicy = { ChatGptModelPolicy() },
    private val diagnostic: (String) -> Unit = { Log.w("InkuProvider", it) },
    private val foreground: StateFlow<Boolean> = MutableStateFlow(true),
    private val authorizationTimeoutMs: Long? = null,
    private val now: () -> Long = System::currentTimeMillis,
) : ModelProvider {
    override val providerId: String = CHATGPT_PROVIDER
    private val mutableState = MutableStateFlow(ChatGptPlanView())
    val state: StateFlow<ChatGptPlanView> = mutableState.asStateFlow()
    /**
     * The core's `edit` lock. Held only while the store is read and written
     * (never across a send), so it stays on one thread; the non-suspending
     * readers of the store take it too.
     */
    private val edit = ReentrantLock()
    private val refreshMutex = Mutex()
    private val wireMutex = Mutex()
    private var authorization: Authorization? = null

    /** A sign-in in progress: its loopback listener, and the host's own deadline when a test sets one. */
    private class Authorization(val callback: ChatGptCallbackServer, val hostDeadline: Long?) {
        val trace = DiagnosticTrace()
        @Volatile var cancelled = false
        var job: Job? = null
        fun check() { if (cancelled) throw ChatGptException("chatgpt_cancelled") }
    }

    private class DiagnosticTrace {
        var stage = "listener"
            private set
        var status: Int? = null
            private set
        fun enter(value: String) { stage = value; status = null }
        fun response(value: Int) { status = value }
    }

    private fun logFailure(trace: DiagnosticTrace, error: Exception) {
        runCatching { diagnostic(ChatGptDiagnostic.line(trace.stage, trace.status, error)) }
    }

    init { updateView() }

    private fun seconds(): Double = now() / 1000.0

    private fun updateView(errorCode: String? = null, revocationUnconfirmed: Boolean = false): Unit = edit.withLock {
        try {
            val saved = store.read()
            val profiles = saved.getJSONObject("profiles")
            val activeId = saved.optString("active").takeIf(String::isNotEmpty)
            val active = activeId?.let(profiles::optJSONObject)
            val cache = active?.optJSONObject("catalog")?.optJSONArray("models")
            val items = profiles.keys().asSequence().map { id -> id to profiles.getJSONObject(id) }.toList()
            val finished = items.filter { (_, item) -> item.has("sub") }.map { (id, item) ->
                ChatGptProfileView(id, item.optString("label", "ChatGPT / " + item.optString("client_id").takeLast(8)),
                    item.optString("state", "reauthentication_required"), item.planAllowed(), item.stringList("scopes"))
            }
            // An unfinished registration: the core keeps it under `registrations_pending`;
            // one saved before step 5 is still among the profiles, without `sub`.
            val pendingStore = saved.optJSONObject("registrations_pending") ?: JSONObject()
            val unfinished = items.filterNot { (_, item) -> item.has("sub") }.map { (id, item) ->
                ChatGptPendingRegistration(id, item.optString("client_id").takeIf(String::isNotEmpty))
            } + pendingStore.keys().asSequence().map { id ->
                ChatGptPendingRegistration(id, pendingStore.optJSONObject(id)?.optString("client_id")?.takeIf(String::isNotEmpty))
            }
            val pending = authorization != null
            mutableState.value = ChatGptPlanView(
                profiles = finished, pendingRegistrations = unfinished,
                activeProfileId = activeId, pending = pending,
                errorCode = errorCode, revocationUnconfirmed = revocationUnconfirmed,
                models = cache?.let { (0 until it.length()).map { i -> it.getJSONObject(i).let { model -> ChatGptModel(model.getString("id"), model.getString("label")) } } },
                publishedModels = active?.stringList("published_models") ?: emptyList(),
                activeSession = active?.takeIf { it.has("sub") }?.sessionRef(),
                connection = catalogRequest("sign_in_connection_view",
                    chatGptConnectionRequest(finished, unfinished, activeId, pending, errorCode, revocationUnconfirmed)),
            )
        } catch (_: Exception) {
            mutableState.value = ChatGptPlanView(errorCode = "chatgpt_storage_unavailable")
        }
    }

    // -----------------------------------------------------------------------
    // The procedure driver.

    /**
     * Runs one core procedure to its end and answers its `done`; its `failed`
     * is thrown with the core's code, class and next action. A lock still held
     * when it stops early is released.
     */
    private suspend fun runFlow(name: String, input: JSONObject, attempt: Authorization? = null,
                                trace: DiagnosticTrace? = null, opened: ((String) -> Unit)? = null): JSONObject {
        var answer = ChatGptCore.call("chatgpt_flow_start", JSONObject().put("flow", name).put("input", input).put("now", seconds()))
        val held = ArrayList<String>()
        try {
            while (true) {
                attempt?.check()
                val todo = answer.getJSONObject("todo")
                val result: JSONObject = when (todo.getString("todo")) {
                    "done" -> return todo
                    "failed" -> throw chatGptFailure(todo)
                    "acquire" -> {
                        val lock = todo.getString("lock")
                        val acquired = acquire(lock, todo.getDouble("deadline"))
                        if (acquired) held += lock
                        JSONObject().put("acquired", acquired)
                    }
                    "release" -> { val lock = todo.getString("lock"); held.remove(lock); release(lock); JSONObject() }
                    "read" -> JSONObject().put("value", coreStore(store.read()))
                    "write" -> { trace?.enter("store"); store.write(hostStore(todo.getJSONObject("value"))); JSONObject() }
                    "random" -> chatGptRandom(todo.getJSONObject("bytes"))
                    "host_id" -> JSONObject().put("host_id", edit.withLock { store.hostId() })
                    "listen" -> JSONObject().put("port", requireNotNull(attempt).callback.port)
                    "open" -> { opened?.invoke(todo.getString("url")); JSONObject() }
                    "await_callback" -> {
                        trace?.enter("callback")
                        val sign = requireNotNull(attempt)
                        val deadline = minOf((todo.getDouble("deadline") * 1000).toLong(), sign.hostDeadline ?: Long.MAX_VALUE)
                        val head = sign.callback.await(deadline, now) { sign.cancelled || authorization !== sign }
                        JSONObject().put("head_base64", head?.let { Base64.getEncoder().encodeToString(it) } ?: JSONObject.NULL)
                    }
                    "respond" -> {
                        attempt?.callback?.respond(todo.getInt("status"), todo.getJSONObject("headers"), todo.getString("body"))
                        JSONObject()
                    }
                    "http" -> flowHttp(todo, attempt, trace)
                    "verify" -> {
                        trace?.enter("identity")
                        JSONObject().put("valid", verifyChatGptSignature(todo.getString("alg"), todo.getJSONObject("key"),
                            todo.getString("signing_input"), todo.getString("signature")))
                    }
                    "offset" -> JSONObject().put("seconds", localOffsetSeconds(todo.getString("local")))
                    else -> throw ChatGptException("chatgpt_auth_unavailable")
                }
                answer = ChatGptCore.call("chatgpt_flow_next", JSONObject().put("state", answer.get("state"))
                    .put("result", result).put("now", seconds()))
            }
        } finally {
            held.asReversed().forEach(::release)
        }
    }

    private suspend fun acquire(lock: String, deadline: Double): Boolean {
        val wait = ((deadline * 1000).toLong() - now()).coerceAtLeast(0)
        return when (lock) {
            "edit" -> edit.tryLock(wait, TimeUnit.MILLISECONDS)
            "refresh" -> withTimeoutOrNull(wait.coerceAtLeast(1)) { refreshMutex.lock() } != null
            "wire" -> withTimeoutOrNull(wait.coerceAtLeast(1)) { wireMutex.lock() } != null
            else -> false
        }
    }

    private fun release(lock: String) {
        when (lock) {
            "edit" -> edit.unlock()
            "refresh" -> refreshMutex.unlock()
            "wire" -> wireMutex.unlock()
        }
    }

    /** `http`: sent within the core's deadline and bounds; a failure of the connection itself is one of the core's three kinds. */
    private suspend fun flowHttp(todo: JSONObject, attempt: Authorization?, trace: DiagnosticTrace?): JSONObject {
        val purpose = todo.getString("purpose")
        trace?.enter(when (purpose) { "token_exchange", "token_refresh", "revocation" -> "token"; "models" -> "catalog"; else -> purpose })
        val deadline = (todo.getDouble("deadline") * 1000).toLong()
        if (purpose == "token_exchange") {
            // Android 17 stops a background app's network in about five seconds,
            // so the code is exchanged once inku is in front again.
            val until = minOf(deadline, attempt?.hostDeadline ?: Long.MAX_VALUE)
            val remaining = until - now()
            if (remaining <= 0 || withTimeoutOrNull(remaining) { foreground.first { it } } == null) {
                throw ChatGptException("chatgpt_cancelled")
            }
            attempt?.check()
        }
        val headers = todo.getJSONObject("headers")
        val send = ChatGptSend(todo.getString("url"), todo.getString("method"),
            headers.keys().asSequence().associateWith(headers::getString), "Authorization", "",
            todo.getDouble("answer_limit").toInt(), todo.getDouble("error_limit").toInt(),
            todo.optString("request_id_header").takeIf(String::isNotEmpty))
        return try {
            val response = http.request(send.url, send.method, body = if (todo.has("body")) todo.getString("body") else null,
                timeoutMs = (deadline - now()).coerceAtLeast(1), check = { attempt?.check() }, send = send)
            trace?.response(response.status)
            JSONObject().put("status", response.status).put("body", response.body).put("request_id", response.requestId ?: JSONObject.NULL)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: ChatGptException) {
            if (error.code != "chatgpt_response_too_large") throw error
            JSONObject().put("transport", "too_large")
        }
        catch (_: SocketTimeoutException) { JSONObject().put("transport", "timeout") }
        // Any other failure of the send itself, as step 4 names an unknown one.
        catch (_: Exception) { JSONObject().put("transport", "unavailable") }
    }

    // -----------------------------------------------------------------------
    // Sign-in.

    fun cancelAuthorization(): Unit = edit.withLock {
        authorization?.let { it.cancelled = true; it.callback.close(); it.job?.cancel() }
        authorization = null
        updateView()
    }

    /**
     * Starts the core's `login` and answers the URL to open in Chrome. The rest
     * runs on: the callback is answered as soon as it is taken (the core's
     * `respond_before_exchange`), and the code is exchanged once inku is in front.
     */
    suspend fun authorize(profileId: String? = null, consent: Boolean = false, japanese: Boolean = true): String {
        val attempt = Authorization(ChatGptCallbackServer(), authorizationTimeoutMs?.let { now() + it })
        val count = edit.withLock {
            val busy = if (authorization != null) 1 else 0
            if (busy == 0) { authorization = attempt; updateView() }
            busy
        }
        val input = JSONObject().put("profile_id", profileId ?: JSONObject.NULL).put("consent", consent)
            .put("language", if (japanese) "ja" else "en").put("pending_count", count).put("owner_count", count)
            .put("respond_before_exchange", true)
        val opened = CompletableDeferred<String>()
        attempt.job = scope.launch(Dispatchers.IO) {
            try {
                val done = runFlow("login", input, attempt, attempt.trace) { opened.complete(it) }
                val id = done.getString("profile_id")
                finishAuthorization(attempt, null)
                val ref = edit.withLock { store.read().getJSONObject("profiles").getJSONObject(id).sessionRef() }
                // The person's own list, as the manual refresh fetches it.
                launch {
                    try { refreshPinnedModels(ref, logFailure = true) }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: ChatGptException) { /* Refresh reports its own failure. */ }
                }
            } catch (cancelled: CancellationException) {
                opened.completeExceptionally(cancelled)
                finishAuthorization(attempt, null)
                throw cancelled
            } catch (error: Exception) {
                if (opened.isCompleted) logFailure(attempt.trace, error) else opened.completeExceptionally(error)
                finishAuthorization(attempt, (error as? ChatGptException)?.code ?: "chatgpt_auth_unavailable")
            } finally {
                attempt.callback.close()
            }
        }
        return opened.await()
    }

    private fun finishAuthorization(attempt: Authorization, code: String?): Unit = edit.withLock {
        if (authorization === attempt) { authorization = null; updateView(code) }
    }

    fun browserUnavailable() { cancelAuthorization(); updateView("chatgpt_browser_unavailable") }

    // -----------------------------------------------------------------------
    // Registrations.

    suspend fun selectProfile(id: String) {
        cancelAuthorization()
        runFlow("select", JSONObject().put("profile_id", id))
        updateView()
    }

    fun pinSession(): ChatGptSessionRef = edit.withLock {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(value.optString("active")) ?: throw ChatGptException("chatgpt_not_connected")
        checkSession(profile.sessionRef())
        profile.sessionRef()
    }

    internal fun checkSession(ref: ChatGptSessionRef): JSONObject = edit.withLock {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(ref.profileId) ?: throw ChatGptException("chatgpt_not_connected")
        ChatGptCore.call("chatgpt_auth_session", JSONObject().put("profile", ChatGptCore.toCore(profile)).put("generation", ref.generation))
        profile
    }

    /** 「接続状態を確認」: reads the saved registrations again and clears the last failure (Web `load`). */
    fun reload() = updateView()

    /** 「利用枠を確認して再試行」: a registration a usage limit paused goes back to `connected` (the core's `resume`). */
    suspend fun retryQuota(id: String) {
        runFlow("resume", JSONObject().put("profile_id", id))
        updateView()
    }

    suspend fun refreshModels(): List<String> {
        val active = edit.withLock {
            val value = store.read()
            value.getJSONObject("profiles").optJSONObject(value.optString("active")) ?: throw ChatGptException("chatgpt_not_connected")
        }
        // A deliberate refresh can check whether the usage window has reopened.
        if (active.optString("state") == "quota") retryQuota(active.getString("id"))
        return refreshPinnedModels(pinSession())
    }

    /** The core's `catalog`, fetched again (it waits its own deadline, 15 seconds) and kept under the `edit` lock. */
    private suspend fun refreshPinnedModels(ref: ChatGptSessionRef, logFailure: Boolean = false): List<String> {
        try {
            val done = runFlow("catalog", JSONObject().put("profile_id", ref.profileId).put("generation", ref.generation).put("force", true))
            updateView()
            val models = done.getJSONArray("models")
            return (0 until models.length()).map { models.getJSONObject(it).getString("id") }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            if (logFailure) logFailure(DiagnosticTrace().apply { enter("catalog") }, error)
            val safe = error as? ChatGptException ?: chatGptTransportFailure(error)
            updateView()
            reportFailure(ref, safe.code); throw safe
        }
    }

    fun publishModels(ref: ChatGptSessionRef, models: List<String>, purposes: JSONObject? = null): Unit = edit.withLock {
        ChatGptCore.call("chatgpt_auth_publication_input", JSONObject().put("profile_id", ref.profileId)
            .put("generation", ref.generation).put("selected", JSONArray(models)).put("model_purposes", purposes ?: JSONObject.NULL))
        val profile = checkSession(ref)
        val value = store.read()
        ChatGptCore.call("chatgpt_auth_publication_active", JSONObject().put("active", value.optString("active")).put("profile_id", ref.profileId))
        val policy = modelPolicy()
        val input = ChatGptCore.toCore(profile, policy.purposes)
        val updated = ChatGptCore.call("chatgpt_publication_update", JSONObject().put("profile", input)
            .put("selected", JSONArray(models)).put("model_purposes", purposes ?: JSONObject.NULL).put("assessments", policy.assessments)).getJSONObject("profile")
        updated.remove("model_purposes")
        value.getJSONObject("profiles").put(ref.profileId, ChatGptCore.fromCore(updated))
        store.write(value); http.cancelAll(); updateView()
    }

    suspend fun signOut(id: String): Boolean {
        cancelAuthorization()
        try {
            val done = runFlow("sign_out", JSONObject().put("profile_id", id))
            http.cancelAll()
            val confirmed = done.optBoolean("revocation_confirmed")
            updateView(revocationUnconfirmed = !confirmed)
            return confirmed
        } catch (cancelled: CancellationException) { updateView(revocationUnconfirmed = true); throw cancelled }
    }

    suspend fun deleteProfile(id: String) {
        cancelAuthorization()
        val done = runFlow("delete", JSONObject().put("profile_id", id))
        http.cancelAll()
        updateView(revocationUnconfirmed = !done.optBoolean("revocation_confirmed"))
    }

    // -----------------------------------------------------------------------
    // Drawing.

    /** The core's `access`: the token, refreshed when it is old (under `refresh`). */
    private suspend fun accessToken(ref: ChatGptSessionRef, deadline: Double): String {
        try {
            return runFlow("access", JSONObject().put("profile_id", ref.profileId).put("generation", ref.generation)
                .put("deadline", deadline)).getString("access_token")
        } finally { updateView() }
    }

    override suspend fun generate(request: ModelRequest): ModelResponse {
        // Validate the operation before opening any connection, including catalog retrieval.
        val built = chatGptRequest(request)
        val ref = request.chatGptSession ?: throw ChatGptException("chatgpt_session_required")
        val started = System.nanoTime()
        val timeoutMs = request.timeoutMs ?: 60_000
        val deadline = seconds() + timeoutMs / 1000.0
        try {
            return withTimeout(timeoutMs) {
                val slug = request.modelId.removePrefix("chatgpt:")
                // The core's `catalog`: the cached list, or fetched under the `wire` lock.
                runFlow("catalog", JSONObject().put("profile_id", ref.profileId).put("generation", ref.generation)
                    .put("force", false).put("deadline", deadline))
                updateView()
                val policy = modelPolicy()
                fun check() {
                    val profile = checkSession(ref)
                    val publication = ChatGptCore.call("chatgpt_publication", JSONObject().put("profile", ChatGptCore.toCore(profile, policy.purposes))
                        .put("assessments", policy.assessments)).getJSONObject("publication")
                    val purpose = chatGptPurpose(request.pipelineAction)
                    if (!ChatGptCore.call("chatgpt_offered", JSONObject().put("models", publication.getJSONArray("models"))
                            .put("model", slug).put("purpose", purpose)).getBoolean("offered")) throw ChatGptException("chatgpt_model_not_offered")
                }
                check()
                // The transport asks before and after every read of the stream;
                // each full check reads the encrypted store and calls the core
                // four times. During the stream it runs at most once a second;
                // the checks before the request and after the answer stay whole,
                // and a session change cancels the connection on its own.
                var lastCheck = System.nanoTime()
                fun streamCheck() {
                    val now = System.nanoTime()
                    if (now - lastCheck < STREAM_CHECK_INTERVAL_NANOS) return
                    check()
                    lastCheck = now
                }
                val token = accessToken(ref, deadline)
                wireMutex.withLock {
                    // Refinement advice reads Server's Vision text stream; drawing
                    // effects still require their completed namespace function.
                    val stream = ChatGptStream(built, request.onReceivedBytes)
                    // Where, with which headers and bounds: the core's answer for this body.
                    val response = http.request(built.send.url, built.send.method, token, built.body, timeoutMs = timeoutMs,
                        check = ::streamCheck, onChunk = stream::feed, send = built.send)
                    if (response.status !in 200..299) throw chatGptHttpError(response)
                    val text = stream.finish(); check()
                    ModelResponse(text, request.modelId, stream.usage?.optInt("input_tokens")?.takeIf { it > 0 },
                        stream.usage?.optInt("output_tokens")?.takeIf { it > 0 }, (System.nanoTime() - started) / 1_000_000)
                }
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (error: Exception) {
            // A stopped drawing disconnects the socket, and the read under it
            // throws an IOException rather than the cancellation. Reported, it
            // showed a red "could not complete" beside 「停止しました」.
            if (!currentCoroutineContext().isActive) throw CancellationException("stopped").apply { initCause(error) }
            // Public codes only. The core names what the answer was (an error
            // body, a stream it could not read); the connection's own failure is
            // its `chatgpt_transport`: a timeout is not a dropped connection.
            val safe = error as? ChatGptException ?: chatGptTransportFailure(error)
            pauseForFailure(ref, safe.code)
            reportFailure(ref, safe.code)
            throw safe
        }
    }

    /** A connection's own failure as the core names it: a timeout, else unavailable (any other I/O or unknown failure). */
    private fun chatGptTransportFailure(error: Exception): ChatGptException =
        chatGptTransport(if (error is SocketTimeoutException) "timeout" else "unavailable")

    private fun reportFailure(ref: ChatGptSessionRef, code: String): Unit = edit.withLock {
        val value = store.read()
        val profile = value.getJSONObject("profiles").optJSONObject(ref.profileId)
        if (value.optString("active") == ref.profileId && profile != null &&
            (profile.optLong("generation") == ref.generation || profile.optLong("generation") == ref.generation + 1 &&
                profile.optString("state") in setOf("quota", "reauthentication_required"))) updateView(code)
    }

    /** A usage limit the answer named pauses the registration (the core's `pause`). */
    private suspend fun pauseForFailure(ref: ChatGptSessionRef, code: String) {
        if (!ChatGptCore.call("chatgpt_auth_quota_failure", JSONObject().put("code", code)).getBoolean("pause")) return
        runCatching { runFlow("pause", JSONObject().put("profile_id", ref.profileId).put("generation", ref.generation).put("code", code)) }
        updateView()
    }
}
